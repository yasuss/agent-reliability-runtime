"""Small async HTTP providers with bounded, credential-free failure diagnostics."""

import json
import math
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, ValidationError

from agent_reliability_runtime.contracts.domain import Counter, Identifier
from agent_reliability_runtime.providers.contracts import (
    ChatRequest,
    ChatResult,
    EmbeddingRequest,
    EmbeddingResult,
    ToolCall,
    Usage,
)


class ProviderError(Exception):
    """Provider boundary failure; carries no raw request/response or credential."""


class ProviderConfigurationError(ProviderError):
    pass


class ProviderTransportError(ProviderError):
    pass


class ProviderHTTPError(ProviderError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"provider HTTP status {status_code}")


class ProviderProtocolError(ProviderError):
    pass


@dataclass(frozen=True)
class HTTPProviderConfig:
    provider_id: str
    model_id: str
    base_url: str
    api_key: SecretStr | None = field(default=None, repr=False)
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        try:
            url = httpx.URL(self.base_url)
            valid = (
                url.scheme in {"http", "https"}
                and bool(url.host)
                and not url.userinfo
                and not url.query
                and not url.fragment
                and bool(self.provider_id.strip())
                and bool(self.model_id.strip())
                and not isinstance(self.timeout_seconds, bool)
                and math.isfinite(self.timeout_seconds)
                and self.timeout_seconds > 0
                and (self.api_key is None or isinstance(self.api_key, SecretStr))
            )
            if self.api_key is not None:
                key = self.api_key.get_secret_value()
                valid = valid and bool(key) and all(32 < ord(c) < 127 for c in key)
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise ProviderConfigurationError("invalid provider configuration") from None


class _WireModel(BaseModel):
    # Ignore vendor extensions without retaining them in neutral results.
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class _Function(_WireModel):
    name: Identifier
    arguments: str | dict[str, JsonValue]


class _Call(_WireModel):
    id: Identifier | None = None
    type: Literal["function"]
    function: _Function


class _Message(_WireModel):
    role: Literal["assistant"]
    content: str | None = None
    tool_calls: list[_Call] = Field(default_factory=list)


class _Choice(_WireModel):
    message: _Message
    finish_reason: Identifier


class _Usage(_WireModel):
    prompt_tokens: Counter | None = None
    completion_tokens: Counter | None = None
    total_tokens: Counter | None = None


class _ChatResponse(_WireModel):
    model: Identifier
    choices: Annotated[list[_Choice], Field(min_length=1, max_length=1)]
    usage: _Usage | None = None


class _EmbeddingResponse(_WireModel):
    model: Identifier
    embeddings: Annotated[
        list[list[Annotated[float, Field(strict=True)]]], Field(min_length=1)
    ]
    prompt_eval_count: Counter | None = None


async def _post(
    config: HTTPProviderConfig,
    endpoint: str,
    payload: dict[str, Any],
    transport: httpx.AsyncBaseTransport | None,
) -> Any:
    headers = {}
    if config.api_key is not None:
        headers["Authorization"] = "Bearer " + config.api_key.get_secret_value()
    response = None
    try:
        async with httpx.AsyncClient(
            timeout=config.timeout_seconds,
            transport=transport,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                config.base_url.rstrip("/") + endpoint, json=payload, headers=headers
            )
    except httpx.RequestError:
        pass
    if response is None:
        # Raise outside except: even hidden __context__ must not retain a raw
        # HTTPX exception containing credential-bearing request headers.
        raise ProviderTransportError("provider transport or timeout failure")
    if not 200 <= response.status_code < 300:
        # Never echo upstream bodies/headers/URL or attach HTTPStatusError.
        raise ProviderHTTPError(response.status_code)
    try:
        return response.json()
    except ValueError:
        pass
    raise ProviderProtocolError("provider response is not valid JSON")


class OpenAICompatibleChatProvider:
    def __init__(
        self,
        config: HTTPProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not httpx.URL(config.base_url).path.rstrip("/").endswith("/v1"):
            raise ProviderConfigurationError("chat base_url must end in /v1")
        self.config = config
        self._transport = transport

    async def complete(self, request: ChatRequest) -> ChatResult:
        invalid = False
        try:
            request = ChatRequest.model_validate(request.model_dump())
        except ValidationError:
            invalid = True
        if invalid:
            raise ProviderConfigurationError("invalid chat request")
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            item: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.tool_call_id is not None:
                item["tool_call_id"] = message.tool_call_id
            if message.tool_calls:
                if any(call.call_id is None for call in message.tool_calls):
                    raise ProviderConfigurationError("message tool calls require IDs")
                item["tool_calls"] = [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, allow_nan=False),
                        },
                    }
                    for call in message.tool_calls
                ]
            messages.append(item)
        payload: dict[str, Any] = {
            "model": self.config.model_id,
            "messages": messages,
            "stream": False,
            **request.settings.model_dump(exclude_none=True),
        }
        if request.tools:
            payload["tools"] = [
                {"type": "function", "function": tool.model_dump()}
                for tool in request.tools
            ]
        data = await _post(self.config, "/chat/completions", payload, self._transport)
        try:
            wire = _ChatResponse.model_validate(data)
            choice = wire.choices[0]
            if choice.message.content is None and not choice.message.tool_calls:
                raise ValueError("chat message has neither content nor tool calls")
            calls = []
            for call in choice.message.tool_calls:
                args = call.function.arguments
                if isinstance(args, str):
                    args = json.loads(args)
                calls.append(
                    ToolCall(call_id=call.id, name=call.function.name, arguments=args)
                )
            usage = (
                None
                if wire.usage is None
                else Usage(
                    input_tokens=wire.usage.prompt_tokens,
                    output_tokens=wire.usage.completion_tokens,
                    total_tokens=wire.usage.total_tokens,
                )
            )
            return ChatResult(
                text=choice.message.content,
                tool_calls=tuple(calls),
                finish_reason=choice.finish_reason,
                provider_id=self.config.provider_id,
                model_id=wire.model,
                usage=usage,
            )
        except (ValueError, TypeError):
            pass
        raise ProviderProtocolError("malformed chat response")


class OllamaEmbeddingProvider:
    def __init__(
        self,
        config: HTTPProviderConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        invalid = False
        try:
            request = EmbeddingRequest.model_validate(request.model_dump())
        except ValidationError:
            invalid = True
        if invalid:
            raise ProviderConfigurationError("invalid embedding request")
        data = await _post(
            self.config,
            "/api/embed",
            {
                "model": self.config.model_id,
                "input": list(request.inputs),
                # Preserve exact input instead of silently accepting truncation.
                "truncate": False,
            },
            self._transport,
        )
        try:
            wire = _EmbeddingResponse.model_validate(data)
            if len(wire.embeddings) != len(request.inputs):
                raise ValueError("embedding count mismatch")
            return EmbeddingResult(
                provider_id=self.config.provider_id,
                model_id=wire.model,
                vectors=tuple(tuple(vector) for vector in wire.embeddings),
                input_tokens=wire.prompt_eval_count,
            )
        except (ValueError, TypeError):
            pass
        raise ProviderProtocolError("malformed embedding response")
