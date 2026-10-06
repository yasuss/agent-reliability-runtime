"""Explicit local-only B20 model acceptance. Never run automatically in CI."""

import argparse
import asyncio
import hashlib
import json
import subprocess

import httpx
from pydantic import SecretStr

from agent_reliability_runtime.providers.contracts import (
    ChatMessage,
    ChatRequest,
    EmbeddingRequest,
    ModelSettings,
)
from agent_reliability_runtime.providers.http import (
    HTTPProviderConfig,
    OllamaEmbeddingProvider,
    OpenAICompatibleChatProvider,
)


async def probe(base_url: str) -> dict[str, object]:
    url = httpx.URL(base_url)
    if url.host not in {"127.0.0.1", "localhost", "::1"} or url.path not in {"", "/"}:
        raise ValueError("acceptance requires the local Ollama server root URL")
    config = HTTPProviderConfig(
        provider_id="ollama-local",
        model_id="qwen3:4b",
        base_url=base_url + "/v1",
        api_key=SecretStr("ollama"),
        timeout_seconds=300,
    )
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        version = await client.get(base_url + "/api/version")
        version.raise_for_status()
        tags = await client.get(base_url + "/api/tags")
        tags.raise_for_status()
        models = {item["name"]: item for item in tags.json()["models"]}
        evidence = []
        for name in ("qwen3:4b", "qwen3-embedding:0.6b"):
            item = models[name]
            if item.get("remote_model") or not item.get("digest"):
                raise ValueError(
                    "acceptance requires locally available model artifacts"
                )
            evidence.append(
                {key: item[key] for key in ("name", "digest", "size", "details")}
            )
    chat = await OpenAICompatibleChatProvider(config).complete(
        ChatRequest(
            messages=(
                ChatMessage(
                    role="user",
                    content=(
                        "Reply with one short sentence confirming this is "
                        "a local provider test. /no_think"
                    ),
                ),
            ),
            settings=ModelSettings(temperature=0, max_tokens=2048),
        )
    )
    if (
        chat.provider_id != "ollama-local"
        or chat.model_id != "qwen3:4b"
        or not chat.text
        or not chat.text.strip()
    ):
        raise AssertionError(
            "live chat result must have identity and nonempty usable text"
        )
    embedding = await OllamaEmbeddingProvider(
        HTTPProviderConfig(
            provider_id="ollama-local",
            model_id="qwen3-embedding:0.6b",
            base_url=base_url,
            timeout_seconds=300,
        )
    ).embed(
        EmbeddingRequest(
            inputs=(
                "Fictional checkout service is degraded.",
                "Fictional search service is healthy.",
            )
        )
    )
    if (
        embedding.provider_id != "ollama-local"
        or embedding.model_id != "qwen3-embedding:0.6b"
        or len(embedding.vectors) != 2
    ):
        raise AssertionError("live embedding identity/count mismatch")
    return {
        "subject_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "ollama_version": version.json()["version"],
        "local_models": evidence,
        "chat_endpoint": base_url + "/v1/chat/completions",
        "embedding_endpoint": base_url + "/api/embed",
        "chat_result": chat.model_dump(mode="json"),
        "embedding_result": {
            "provider_id": embedding.provider_id,
            "model_id": embedding.model_id,
            "count": len(embedding.vectors),
            "dimension": embedding.dimension,
            "input_tokens": embedding.input_tokens,
            "vectors_sha256": hashlib.sha256(
                json.dumps(embedding.vectors).encode()
            ).hexdigest(),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(probe(args.base_url.rstrip("/"))), indent=2))
