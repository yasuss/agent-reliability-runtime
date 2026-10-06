"""Stable semantic envelope: legacy compatibility and explicit bad-input errors."""

import asyncio
import copy
import inspect
import json

import pytest

from agent_reliability_runtime.evals.execution import ScriptedScenarioProvider
from agent_reliability_runtime.evals.scenarios import load_scenarios
from agent_reliability_runtime.providers.contracts import ChatMessage, ChatRequest
from agent_reliability_runtime.retrieval.contracts import Evidence
from agent_reliability_runtime.runtime.prompt_context import (
    RETRIEVAL_PREFIX,
    parse_retrieval_context,
    render_retrieval_context,
)


def evidence() -> dict[str, object]:
    return Evidence(
        evidence_id="a" * 64,
        chunk_id="a" * 64,
        document_id="b" * 64,
        document_digest="c" * 64,
        title="Synthetic",
        source_path="synthetic.md",
        content="Disposable grounded facts",
        lexical_rank=1,
        vector_rank=1,
        rrf_score=0.01,
    ).model_dump(mode="json")


def test_round_trip_legacy_and_no_durable_mutation() -> None:
    raw = [evidence()]
    before = copy.deepcopy(raw)
    text = render_retrieval_context(raw)
    assert RETRIEVAL_PREFIX == "Untrusted retrieval evidence: "
    assert text.startswith(RETRIEVAL_PREFIX)
    projected = parse_retrieval_context(text)
    assert projected is not None
    assert projected == [
        {
            "ref": "E1",
            "citation_token": "[E1]",
            **{k: raw[0][k] for k in ("title", "source_path", "content")},
        }
    ]
    assert parse_retrieval_context(RETRIEVAL_PREFIX + json.dumps(raw)) == raw
    assert raw == before and "citation_token" not in raw[0]
    assert parse_retrieval_context("Ordinary user prose") is None


@pytest.mark.parametrize("payload", ["{", "{}", "[1]", '[{"evidence_id":"short"}]'])
def test_malformed_context_is_bounded(payload: str) -> None:
    with pytest.raises(ValueError, match="^malformed retrieval context$"):
        parse_retrieval_context(RETRIEVAL_PREFIX + payload)


def test_foreign_projected_token_rejected() -> None:
    with pytest.raises(ValueError, match="malformed retrieval context"):
        parse_retrieval_context(
            RETRIEVAL_PREFIX
            + json.dumps([evidence() | {"citation_token": f"[evidence:{'d' * 64}]"}])
        )


def test_scripted_missing_context_explicit_and_no_duplicate_literal() -> None:
    provider = ScriptedScenarioProvider(load_scenarios()[0][0])
    request = ChatRequest(
        messages=(
            ChatMessage(role="user", content="Disposable"),
            ChatMessage(role="tool", content="{}", tool_call_id="read-1"),
            ChatMessage(role="tool", content="{}", tool_call_id="read-2"),
        )
    )
    with pytest.raises(AssertionError, match="^retrieval context missing$"):
        asyncio.run(provider.complete(request))
    assert RETRIEVAL_PREFIX not in inspect.getsource(ScriptedScenarioProvider)
