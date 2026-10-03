import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import JsonValue, ValidationError

from agent_reliability_runtime.contracts.domain import (
    Approval,
    ApprovalStatus,
    AuditEvent,
    DemoIncident,
    DemoIncidentNote,
    DemoNotification,
    DemoSeed,
    DemoService,
    EffectReceipt,
    KnowledgeChunk,
    KnowledgeDocument,
    Memory,
    Run,
    RunStatus,
    action_digest,
    chunk_id,
    document_id,
    transition_approval,
    transition_run,
)
from agent_reliability_runtime.demo_state.reset import load_seed

NOW = datetime(2026, 10, 3, tzinfo=UTC)
DIGEST = "a" * 64


def run_values() -> dict[str, Any]:
    return dict(
        run_id="run-1",
        workspace_id="local",
        user_id="developer",
        request_text="fictional request",
        provider_id="fixture",
        model_id="fixture",
        policy_version="v1",
        status="CREATED",
        created_at=NOW,
        updated_at=NOW,
    )


def approval_values() -> dict[str, Any]:
    args: dict[str, JsonValue] = {"service_id": "checkout-api", "reason": "fictional"}
    return dict(
        approval_id="approval-1",
        run_id="run-1",
        action_id="action-1",
        tool_name="restart_service",
        normalized_args=args,
        action_digest=action_digest("run-1", "restart_service", args, "v1"),
        policy_version="v1",
        risk_class="SIDE_EFFECT",
        status="PENDING",
        created_at=NOW,
    )


def contract_examples() -> list[tuple[Any, dict[str, Any]]]:
    doc = document_id("data/knowledge/runbook.md")
    return [
        (Run, run_values()),
        (Approval, approval_values()),
        (
            EffectReceipt,
            dict(
                receipt_id="receipt-1",
                run_id="run-1",
                tool_name="fixture",
                idempotency_key="key-1",
                action_digest=DIGEST,
                result_digest=DIGEST,
                applied_at=NOW,
            ),
        ),
        (
            AuditEvent,
            dict(
                event_id="event-1",
                run_id="run-1",
                sequence_number=1,
                event_type="SAFE_FIXTURE",
                payload={"status": "ok"},
                timestamp=NOW,
            ),
        ),
        (
            Memory,
            dict(
                memory_id="memory-1",
                workspace_id="local",
                user_id="developer",
                kind="OBSERVATION",
                provenance="MODEL_OBSERVATION",
                content="fictional",
                created_at=NOW,
                updated_at=NOW,
            ),
        ),
        (
            KnowledgeDocument,
            dict(
                document_id=doc,
                source_path="data/knowledge/runbook.md",
                content_digest=DIGEST,
                title="Runbook",
                metadata={"safe": True},
            ),
        ),
        (
            KnowledgeChunk,
            dict(
                chunk_id=chunk_id(doc, DIGEST, 0),
                document_id=doc,
                document_digest=DIGEST,
                ordinal=0,
                content="fictional",
            ),
        ),
        (DemoService, dict(service_id="checkout-api", status="degraded")),
        (
            DemoIncident,
            dict(
                incident_id="INC-1001",
                service_id="checkout-api",
                summary="fixture",
                status="open",
            ),
        ),
        (
            DemoNotification,
            dict(
                notification_id="notice-1",
                channel="demo",
                message="fictional",
                created_at=NOW,
            ),
        ),
        (
            DemoIncidentNote,
            dict(
                note_id="note-1",
                incident_id="INC-1001",
                note="fictional",
                created_at=NOW,
            ),
        ),
        (DemoSeed, dict(services=[], incidents=[])),
    ]


@pytest.mark.parametrize("model,values", contract_examples())
def test_contract_valid_invalid_extra_and_roundtrip(
    model: Any, values: dict[str, Any]
) -> None:
    record = model.model_validate(values)
    assert model.model_validate_json(record.model_dump_json()) == record
    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate({**values, "authority": True})
    required = next(
        name for name, field in model.model_fields.items() if field.is_required()
    )
    with pytest.raises(ValidationError, match="missing"):
        model.model_validate(
            {key: value for key, value in values.items() if key != required}
        )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("status", "BOGUS"),
        ("model_steps", -1),
        ("tool_steps", -1),
        ("model_steps", True),
        ("tool_steps", "1"),
        ("created_at", NOW.replace(tzinfo=None)),
    ],
)
def test_run_contract_invalid(field: str, bad: Any) -> None:
    with pytest.raises(ValidationError):
        Run.model_validate({**run_values(), field: bad})


def test_run_transition_boundary_and_utc() -> None:
    run = Run.model_validate(run_values())
    alternate = NOW.astimezone(timezone(timedelta(hours=2)))
    assert (
        Run.model_validate({**run_values(), "created_at": alternate}).created_at == NOW
    )
    for status in RunStatus:
        final = transition_run(run, status, at=NOW, reason="fixture")
        if status in {RunStatus.CREATED, RunStatus.RUNNING, RunStatus.WAITING_APPROVAL}:
            assert (
                transition_run(final, RunStatus.RUNNING, at=NOW).status
                == RunStatus.RUNNING
            )
        else:
            for nonterminal in (
                RunStatus.CREATED,
                RunStatus.RUNNING,
                RunStatus.WAITING_APPROVAL,
            ):
                with pytest.raises(ValueError, match="terminal"):
                    transition_run(final, nonterminal, at=NOW)
    with pytest.raises(ValidationError, match="terminal_reason"):
        Run.model_validate({**run_values(), "status": "FAILED"})
    with pytest.raises(ValidationError, match="frozen_instance"):
        run.run_id = "changed"


def test_action_digest_contract_order_drift_and_known_answer() -> None:
    args: dict[str, Any] = {"z": {"b": 2, "a": 1}, "a": ["é", True, None]}
    canonical = (
        '{"normalized_args":{"a":["é",true,null],"z":{"a":1,"b":2}},'
        '"policy_version":"v1","run_id":"r","tool_name":"t"}'
    )
    expected = hashlib.sha256(canonical.encode()).hexdigest()
    assert action_digest("r", "t", args, "v1") == expected
    assert (
        action_digest("r", "t", {"a": args["a"], "z": {"a": 1, "b": 2}}, "v1")
        == expected
    )
    for variant in [
        ("r2", "t", args, "v1"),
        ("r", "t2", args, "v1"),
        ("r", "t", {"z": 3}, "v1"),
        ("r", "t", args, "v2"),
    ]:
        assert action_digest(*variant) != expected
    with pytest.raises(ValueError):
        action_digest("r", "t", {"n": float("nan")}, "v1")


@pytest.mark.parametrize(
    "field,bad",
    [
        ("status", "BOGUS"),
        ("risk_class", "READ_ONLY"),
        ("action_digest", "A" * 64),
        ("action_digest", "a" * 63),
        ("action_digest", "b" * 64),
        ("normalized_args", {"drift": True}),
    ],
)
def test_approval_contract_invalid(field: str, bad: Any) -> None:
    with pytest.raises(ValidationError):
        Approval.model_validate({**approval_values(), field: bad})


def test_approval_contract_immutability_and_no_resurrection() -> None:
    approval = Approval.model_validate(approval_values())
    with pytest.raises(ValidationError, match="frozen_instance"):
        approval.action_digest = "b" * 64
    for status in ApprovalStatus:
        changed = transition_approval(approval, status, at=NOW)
        assert changed.action_digest == approval.action_digest
        if status in {ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}:
            with pytest.raises(ValueError, match="resurrected"):
                transition_approval(changed, ApprovalStatus.APPROVED, at=NOW)


@pytest.mark.parametrize(
    "model,field,bad",
    [
        (EffectReceipt, "result_digest", "invalid"),
        (AuditEvent, "sequence_number", 0),
        (AuditEvent, "sequence_number", -1),
        (Memory, "kind", "BOGUS"),
        (Memory, "provenance", "BOGUS"),
        (Memory, "trust", "BOGUS"),
        (Memory, "content", ""),
        (KnowledgeDocument, "source_path", "../outside.md"),
        (KnowledgeDocument, "source_path", "C:/outside.md"),
        (KnowledgeDocument, "source_path", "/outside.md"),
        (KnowledgeDocument, "content_digest", "invalid"),
        (KnowledgeChunk, "ordinal", -1),
        (KnowledgeChunk, "chunk_id", "drift"),
    ],
)
def test_other_contract_invalid(model: Any, field: str, bad: Any) -> None:
    values = next(values for cls, values in contract_examples() if cls is model)
    with pytest.raises(ValidationError):
        model.model_validate({**values, field: bad})


def test_memory_contract_model_observation_defaults_untrusted() -> None:
    values = next(values for cls, values in contract_examples() if cls is Memory)
    assert Memory.model_validate(values).trust == "UNTRUSTED"
    assert (
        Memory.model_validate(
            {
                **values,
                "kind": "PREFERENCE",
                "provenance": "USER_EXPLICIT",
                "trust": "TRUSTED",
            }
        ).trust
        == "TRUSTED"
    )


def test_knowledge_contract_identity_is_deterministic_and_version_bound() -> None:
    doc = document_id("data/knowledge/runbook.md")
    assert doc == document_id("data/knowledge/runbook.md")
    assert doc != document_id("data/knowledge/alternate.md")
    assert chunk_id(doc, DIGEST, 0) != chunk_id(doc, "b" * 64, 0)
    assert chunk_id(doc, DIGEST, 0) != chunk_id(doc, DIGEST, 1)


def test_seed_contract_drift_and_valid_alternate() -> None:
    root = Path(__file__).resolve().parents[2]
    locked = json.loads(
        (root / "docs/project/spec/v1.0/fixtures/demo_state.json").read_text()
    )
    assert load_seed().model_dump() == locked
    # Same logical fixture with alternate whitespace/key ordering is accepted.
    assert (
        DemoSeed.model_validate_json(json.dumps(locked, sort_keys=True)).model_dump()
        == locked
    )
    bad = json.loads(json.dumps(locked))
    bad["services"][0]["status"] = "fixture-drift"
    with pytest.raises(AssertionError):
        assert DemoSeed.model_validate(bad).model_dump() == locked
