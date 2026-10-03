"""Deterministic provider contract oracles; no live model or network needed."""

import asyncio
import copy
import json
import traceback
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from agent_reliability_runtime.providers.contracts import (
    ChatMessage,
    ChatProvider,
    ChatRequest,
    EmbeddingProvider,
    EmbeddingRequest,
    ModelSettings,
    ToolCall,
    ToolDefinition,
)
from agent_reliability_runtime.providers.http import (
    HTTPProviderConfig,
    OllamaEmbeddingProvider,
    OpenAICompatibleChatProvider,
    ProviderConfigurationError,
    ProviderHTTPError,
    ProviderProtocolError,
    ProviderTransportError,
)

KEY = "fictional-provider-credential"
CHAT: dict[str, Any] = {
    "model": "stub-model",
    "choices": [
        {
            "message": {"role": "assistant", "content": "fixture answer"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
}
EMBED: dict[str, Any] = {
    "model": "stub-embedding",
    "embeddings": [[1.0, 2.0], [3.0, 4.0]],
    "prompt_eval_count": 7,
}


def config(*, chat: bool = True) -> HTTPProviderConfig:
    return HTTPProviderConfig(
        provider_id="stub",
        model_id="stub-model" if chat else "stub-embedding",
        base_url="http://vllm.test:8000/v1/" if chat else "http://ollama.test:11434",
        api_key=SecretStr(KEY) if chat else None,
        timeout_seconds=5,
    )


def request() -> ChatRequest:
    return ChatRequest(
        messages=(ChatMessage(role="user", content="fictional question"),),
        tools=(
            ToolDefinition(
                name="fixture",
                parameters={
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                },
            ),
        ),
        settings=ModelSettings(temperature=0, max_tokens=32),
        trace_context={"fixture": "local-only"},
    )


def chat_call(body: Any) -> Any:
    provider: ChatProvider = OpenAICompatibleChatProvider(
        config(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=json.dumps(body).encode())
        ),
    )
    return asyncio.run(provider.complete(request()))


def embed_call(body: Any) -> Any:
    provider: EmbeddingProvider = OllamaEmbeddingProvider(
        config(chat=False),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=json.dumps(body).encode())
        ),
    )
    return asyncio.run(provider.embed(EmbeddingRequest(inputs=("one", "two"))))


def test_provider_normal_chat_usage_and_generic_vllm_request() -> None:
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        assert str(req.url) == "http://vllm.test:8000/v1/chat/completions"
        assert req.headers["Authorization"] == "Bearer " + KEY
        payload = json.loads(req.content)
        assert payload == {
            "model": "stub-model",
            "messages": [{"role": "user", "content": "fictional question"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "fixture",
                        "description": "",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                        },
                    },
                }
            ],
            "stream": False,
            "temperature": 0,
            "max_tokens": 32,
        }
        assert req.extensions["timeout"] == {
            "connect": 5,
            "read": 5,
            "write": 5,
            "pool": 5,
        }
        return httpx.Response(200, json=CHAT)

    provider = OpenAICompatibleChatProvider(
        config(), transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(provider.complete(request()))
    assert result.text == "fixture answer" and result.tool_calls == ()
    assert result.provider_id == "stub" and result.model_id == "stub-model"
    assert result.usage is not None and result.usage.total_tokens == 14
    assert result.finish_reason == "stop" and result.metadata == {} and len(seen) == 1
    assert KEY not in repr(config()) and KEY not in repr(provider)


@pytest.mark.parametrize("arguments", ['{"city":"Berlin"}', {"city": "Berlin"}])
def test_provider_multiple_tool_calls_and_valid_argument_alternate(
    arguments: Any,
) -> None:
    body = copy.deepcopy(CHAT)
    body["choices"][0] = {
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "fixture", "arguments": arguments},
                },
                {
                    "type": "function",
                    "function": {"name": "alternate", "arguments": "{}"},
                },
            ],
        },
        "finish_reason": "tool_calls",
    }
    result = chat_call(body)
    assert result.text is None and len(result.tool_calls) == 2
    assert result.tool_calls[0].arguments == {"city": "Berlin"}
    assert (
        result.tool_calls[0].call_id == "call-1"
        and result.tool_calls[1].call_id is None
    )
    assert result.tool_calls[1].arguments == {}  # Parsing never executes anything.


def test_provider_absent_partial_usage_and_safe_metadata() -> None:
    body = copy.deepcopy(CHAT)
    body.pop("usage")
    body["secret_metadata"] = KEY
    result = chat_call(body)
    assert result.usage is None and result.metadata == {} and KEY not in repr(result)
    body["usage"] = {"prompt_tokens": 4}
    usage = chat_call(body).usage
    assert (
        usage.input_tokens == 4
        and usage.output_tokens is None
        and usage.total_tokens is None
    )


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {},
        {"model": "stub", "choices": []},
        {
            "model": "stub",
            "choices": [{"message": {"role": "assistant"}, "finish_reason": "stop"}],
        },
        {"model": "stub", "choices": [{"message": "invalid", "finish_reason": "stop"}]},
        {
            "model": "stub",
            "choices": [
                {"message": {"role": "user", "content": "bad"}, "finish_reason": "stop"}
            ],
        },
        {**CHAT, "usage": {"prompt_tokens": -1}},
        {**CHAT, "usage": {"total_tokens": True}},
        {**CHAT, "choices": CHAT["choices"] * 2},
    ],
)
def test_provider_malformed_chat_shape_fails_closed(bad: Any) -> None:
    with pytest.raises(ProviderProtocolError, match="malformed chat"):
        chat_call(bad)


@pytest.mark.parametrize(
    "args", ["{broken", "[]", "null", "true", "1", '"text"', '{"n":NaN}', [1], True]
)
def test_provider_malformed_tool_arguments_fail(args: Any) -> None:
    body = copy.deepcopy(CHAT)
    body["choices"][0]["message"]["tool_calls"] = [
        {"type": "function", "function": {"name": "fixture", "arguments": args}}
    ]
    with pytest.raises(ProviderProtocolError):
        chat_call(body)


@pytest.mark.parametrize("embedding", [False, True])
@pytest.mark.parametrize("status", [302, 400, 401, 429, 500, 503])
def test_provider_http_failure_is_sanitized_and_never_retried(
    embedding: bool, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(
            status,
            text="Authorization: Bearer " + KEY,
            headers={"Location": "http://other.test"},
        )

    with pytest.raises(ProviderHTTPError) as caught:
        if embedding:
            provider = OllamaEmbeddingProvider(
                config(chat=False), transport=httpx.MockTransport(handler)
            )
            asyncio.run(provider.embed(EmbeddingRequest(inputs=("one", "two"))))
        else:
            asyncio.run(
                OpenAICompatibleChatProvider(
                    config(), transport=httpx.MockTransport(handler)
                ).complete(request())
            )
    assert caught.value.status_code == status and len(seen) == 1
    assert (
        KEY
        not in str(caught.value)
        + repr(caught.value)
        + "".join(traceback.format_exception(caught.value))
        + caplog.text
    )


@pytest.mark.parametrize(
    "error_type", [httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout]
)
@pytest.mark.parametrize("embedding", [False, True])
def test_provider_transport_error_sanitized_no_retry(
    error_type: type[httpx.RequestError],
    embedding: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        raise error_type(KEY, request=req)

    with pytest.raises(ProviderTransportError) as caught:
        if embedding:
            asyncio.run(
                OllamaEmbeddingProvider(
                    config(chat=False), transport=httpx.MockTransport(handler)
                ).embed(EmbeddingRequest(inputs=("one",)))
            )
        else:
            asyncio.run(
                OpenAICompatibleChatProvider(
                    config(), transport=httpx.MockTransport(handler)
                ).complete(request())
            )
    assert len(seen) == 1
    assert caught.value.__context__ is None and caught.value.__cause__ is None
    assert (
        KEY
        not in str(caught.value)
        + repr(caught.value)
        + "".join(traceback.format_exception(caught.value))
        + caplog.text
    )


@pytest.mark.parametrize("embedding", [False, True])
def test_provider_invalid_json_diagnostic_does_not_echo_body(embedding: bool) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=KEY))
    with pytest.raises(ProviderProtocolError, match="not valid JSON") as caught:
        if embedding:
            asyncio.run(
                OllamaEmbeddingProvider(config(chat=False), transport=transport).embed(
                    EmbeddingRequest(inputs=("one",))
                )
            )
        else:
            asyncio.run(
                OpenAICompatibleChatProvider(config(), transport=transport).complete(
                    request()
                )
            )
    assert KEY not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None and caught.value.__cause__ is None


def test_provider_embedding_good_and_valid_alternate() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert str(req.url) == "http://ollama.test:11434/api/embed"
        assert "Authorization" not in req.headers
        assert json.loads(req.content) == {
            "model": "stub-embedding",
            "input": ["one", "two"],
            "truncate": False,
        }
        return httpx.Response(200, json=EMBED)

    result = asyncio.run(
        OllamaEmbeddingProvider(
            config(chat=False), transport=httpx.MockTransport(handler)
        ).embed(EmbeddingRequest(inputs=("one", "two")))
    )
    assert (
        result.dimension == 2 and len(result.vectors) == 2 and result.input_tokens == 7
    )
    assert result.provider_id == "stub" and result.model_id == "stub-embedding"
    alternate = {"model": "alias-model", "embeddings": [[-1, 0, 1], [2, 3, 4]]}
    result = embed_call(alternate)
    assert (
        result.dimension == 3
        and result.input_tokens is None
        and result.model_id == "alias-model"
    )


@pytest.mark.parametrize(
    "vectors",
    [
        [],
        [[]],
        [[], []],
        [[1.0]],
        [[1.0], [2.0, 3.0]],
        [[float("nan")], [1.0]],
        [[float("inf")], [1.0]],
        [[float("-inf")], [1.0]],
        [[True], [1.0]],
        [["1"], [2.0]],
        [[None], [2.0]],
    ],
)
def test_provider_embedding_invalid_batch_and_finiteness(vectors: Any) -> None:
    with pytest.raises(ProviderProtocolError, match="malformed embedding"):
        embed_call({**EMBED, "embeddings": vectors})


@pytest.mark.parametrize(
    "override",
    [
        {"base_url": "bad"},
        {"base_url": "http://user:password@stub/v1"},
        {"base_url": "http://stub/v1?token=private"},
        {"base_url": "http://stub/v1#secret"},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": True},
        {"model_id": ""},
        {"api_key": SecretStr("bad\nheader")},
    ],
)
def test_provider_configuration_fails_before_io(override: dict[str, Any]) -> None:
    with pytest.raises(ProviderConfigurationError):
        HTTPProviderConfig(
            **{
                "provider_id": "stub",
                "model_id": "stub-model",
                "base_url": "http://stub/v1",
                **override,
            }
        )


def test_provider_strict_contracts_and_message_roundtrip() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"messages": [], "extra": True})
    with pytest.raises(ValidationError):
        EmbeddingRequest(inputs=())
    with pytest.raises(ValidationError):
        ModelSettings(max_tokens=-1)
    with pytest.raises(ValidationError):
        ToolDefinition(name="bad", parameters={"type": "array"})
    with pytest.raises(ProviderConfigurationError):
        OpenAICompatibleChatProvider(
            HTTPProviderConfig(
                provider_id="stub", model_id="stub", base_url="http://stub"
            )
        )
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=CHAT)

    calls = (ToolCall(call_id="call-1", name="fixture", arguments={"city": "Berlin"}),)
    req = ChatRequest(
        messages=(
            ChatMessage(role="assistant", tool_calls=calls),
            ChatMessage(role="tool", content="safe fixture", tool_call_id="call-1"),
        )
    )
    asyncio.run(
        OpenAICompatibleChatProvider(
            config(), transport=httpx.MockTransport(handler)
        ).complete(req)
    )
    assert json.loads(
        seen[0]["messages"][0]["tool_calls"][0]["function"]["arguments"]
    ) == {"city": "Berlin"}
    assert seen[0]["messages"][1]["tool_call_id"] == "call-1"
