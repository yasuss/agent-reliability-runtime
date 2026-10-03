"""Real PostgreSQL oracles; every test uses an isolated disposable schema."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import (
    Connection,
    DateTime,
    Engine,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from agent_reliability_runtime.contracts.domain import (
    Approval,
    ApprovalStatus,
    AuditEvent,
    EffectReceipt,
    KnowledgeChunk,
    KnowledgeDocument,
    Memory,
    Run,
    RunStatus,
    action_digest,
    chunk_id,
    document_id,
)
from agent_reliability_runtime.demo_state.reset import load_seed, reset_demo
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.persistence.records import (
    insert_snapshot,
    set_approval_status,
    set_run_status,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 3, tzinfo=UTC)
DIGEST = "a" * 64
TABLE_NAMES = {
    "runs",
    "approvals",
    "effect_receipts",
    "audit_events",
    "memories",
    "knowledge_documents",
    "knowledge_chunks",
    "demo_incidents",
    "demo_services",
    "demo_notifications",
    "demo_incident_notes",
}


@pytest.fixture
def isolated_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Engine, Config]]:
    raw_url = os.environ.get("ARR_TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail("ARR_TEST_DATABASE_URL must explicitly select a disposable test DB")
    name = "test_b10_" + uuid4().hex
    admin = create_engine(raw_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{name}"'))
    url = make_url(raw_url).update_query_dict({"options": f"-csearch_path={name}"})
    monkeypatch.setenv("ARR_DATABASE_URL", url.render_as_string(hide_password=False))
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    engine = create_engine(url)
    try:
        command.upgrade(cfg, "head")
        yield engine, cfg
    finally:
        engine.dispose()
        with admin.begin() as connection:
            # Only this test's fresh random schema; never public or other state.
            connection.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
        admin.dispose()


def run_record(run_id: str = "run-1") -> Run:
    return Run(
        run_id=run_id,
        workspace_id="local",
        user_id="developer",
        request_text="fictional",
        provider_id="fixture",
        model_id="fixture",
        policy_version="v1",
        status=RunStatus.CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def expect_constraint(connection: Connection, statement: Any, name: str) -> None:
    with pytest.raises(IntegrityError) as caught:
        with connection.begin_nested():
            connection.execute(statement)
    assert getattr(getattr(caught.value.orig, "diag"), "constraint_name") == name


def test_schema_exact_tables_types_constraints_and_metadata(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == TABLE_NAMES | {"alembic_version"}
    with engine.connect() as c:
        assert c.scalar(text("SHOW server_version")).startswith("18.")
        assert (
            c.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            == "0.8.6"
        )
        assert compare_metadata(MigrationContext.configure(c), schema.metadata) == []
    for table in TABLE_NAMES:
        for column in inspector.get_columns(table):
            if column["name"] in {
                "created_at",
                "updated_at",
                "applied_at",
                "timestamp",
                "decided_at",
                "expires_at",
            }:
                assert isinstance(column["type"], DateTime) and column["type"].timezone
            if column["name"] in {"normalized_args", "payload", "metadata"}:
                assert isinstance(column["type"], JSONB)
        for fk in inspector.get_foreign_keys(table):
            assert fk["name"] and fk["options"].get("ondelete") != "CASCADE"
    effect_columns = {
        column["name"]: column for column in inspector.get_columns("effect_receipts")
    }
    assert not effect_columns["tool_name"]["nullable"]
    assert not effect_columns["idempotency_key"]["nullable"]
    assert "uq_effect_receipts_identity" in {
        c["name"] for c in inspector.get_unique_constraints("effect_receipts")
    }


def test_migration_roundtrip_b00_and_reupgrade(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, cfg = isolated_db
    command.downgrade(cfg, "0001_foundation")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    with engine.connect() as c:
        assert (
            c.scalar(text("SELECT version_num FROM alembic_version"))
            == "0001_foundation"
        )
        assert (
            c.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            == "0.8.6"
        )
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
    assert set(inspect(engine).get_table_names()) == TABLE_NAMES | {"alembic_version"}
    with engine.connect() as c:
        assert compare_metadata(MigrationContext.configure(c), schema.metadata) == []


def test_effect_uniqueness_real_db_rejection_and_valid_alternates(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    with engine.begin() as c:
        insert_snapshot(c, run_record())
        values = dict(
            receipt_id="effect-1",
            run_id="run-1",
            tool_name="fixture",
            idempotency_key="key-1",
            action_digest=DIGEST,
            result_digest=DIGEST,
            applied_at=NOW,
        )
        insert_snapshot(c, EffectReceipt.model_validate(values))
        expect_constraint(
            c,
            schema.effect_receipts.insert().values(
                **{**values, "receipt_id": "effect-2"}
            ),
            "uq_effect_receipts_identity",
        )
        expect_constraint(
            c,
            schema.effect_receipts.insert().values(
                **{**values, "receipt_id": "effect-3", "action_digest": "b" * 64}
            ),
            "uq_effect_receipts_identity",
        )
        for identity in (
            {"receipt_id": "alternate-1", "tool_name": "other-tool"},
            {"receipt_id": "alternate-2", "idempotency_key": "other-key"},
        ):
            insert_snapshot(c, EffectReceipt.model_validate({**values, **identity}))
        assert len(c.execute(select(schema.effect_receipts)).all()) == 3


def test_audit_sequence_positive_unique_append_only(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    with engine.begin() as c:
        insert_snapshot(c, run_record())
        insert_snapshot(c, run_record("run-2"))
        values = dict(
            event_id="event-1",
            run_id="run-1",
            sequence_number=1,
            event_type="SAFE_FIXTURE",
            payload={"status": "ok"},
            timestamp=NOW,
        )
        event = AuditEvent.model_validate(values)
        insert_snapshot(c, event)
        expect_constraint(
            c,
            schema.audit_events.insert().values(**{**values, "event_id": "event-2"}),
            "uq_audit_events_sequence",
        )
        expect_constraint(
            c,
            schema.audit_events.insert().values(
                **{**values, "event_id": "event-3", "sequence_number": 0}
            ),
            "ck_audit_events_sequence",
        )
        insert_snapshot(
            c,
            AuditEvent.model_validate(
                {**values, "event_id": "event-4", "sequence_number": 2}
            ),
        )
        insert_snapshot(
            c,
            AuditEvent.model_validate(
                {**values, "event_id": "event-5", "run_id": "run-2"}
            ),
        )
        assert c.execute(
            select(schema.audit_events.c.sequence_number)
            .where(schema.audit_events.c.run_id == "run-1")
            .order_by(schema.audit_events.c.sequence_number)
        ).scalars().all() == [1, 2]
        assert (
            c.execute(
                select(schema.audit_events.c.payload).where(
                    schema.audit_events.c.event_id == "event-1"
                )
            ).scalar_one()
            == event.payload
        )


@pytest.mark.parametrize(
    "table,field,bad,constraint",
    [
        ("runs", "status", "BOGUS", "ck_runs_status"),
        ("runs", "model_steps", -1, "ck_runs_model_steps"),
        ("runs", "tool_steps", -1, "ck_runs_tool_steps"),
        ("approvals", "status", "BOGUS", "ck_approvals_status"),
        ("approvals", "risk_class", "READ_ONLY", "ck_approvals_risk"),
        ("approvals", "action_digest", "invalid", "ck_approvals_digest"),
        ("memories", "kind", "BOGUS", "ck_memories_kind"),
        ("memories", "provenance", "BOGUS", "ck_memories_provenance"),
        ("memories", "trust", "BOGUS", "ck_memories_trust"),
    ],
)
def test_schema_invalid_checks(
    isolated_db: tuple[Engine, Config],
    table: str,
    field: str,
    bad: Any,
    constraint: str,
) -> None:
    engine, _ = isolated_db
    with engine.begin() as c:
        insert_snapshot(c, run_record())
        if table == "approvals":
            insert_snapshot(c, approval_record())
        if table == "memories":
            insert_snapshot(c, memory_record())
        target = schema.metadata.tables[table]
        expect_constraint(c, target.update().values(**{field: bad}), constraint)


def approval_record() -> Approval:
    return Approval(
        approval_id="approval-1",
        run_id="run-1",
        action_id="action-1",
        tool_name="fixture",
        normalized_args={"fixture": True},
        action_digest=action_digest("run-1", "fixture", {"fixture": True}, "v1"),
        policy_version="v1",
        risk_class="SIDE_EFFECT",
        status=ApprovalStatus.PENDING,
        created_at=NOW,
    )


def memory_record() -> Memory:
    return Memory.model_validate(
        dict(
            memory_id="memory-1",
            workspace_id="local",
            user_id="developer",
            kind="OBSERVATION",
            provenance="MODEL_OBSERVATION",
            content="safe fixture",
            created_at=NOW,
            updated_at=NOW,
            source_run_id="run-1",
        )
    )


def test_contract_persistence_lifecycle_and_json_revalidation(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    with engine.begin() as c:
        insert_snapshot(c, run_record())
        set_run_status(c, "run-1", RunStatus.FAILED, at=NOW, reason="fictional failure")
        with pytest.raises(ValueError, match="terminal"):
            set_run_status(c, "run-1", RunStatus.RUNNING, at=NOW)
        approval = approval_record()
        insert_snapshot(c, approval)
        set_approval_status(c, "approval-1", ApprovalStatus.REJECTED, at=NOW)
        with pytest.raises(ValueError, match="resurrected"):
            set_approval_status(c, "approval-1", ApprovalStatus.APPROVED, at=NOW)
        stored = c.execute(select(schema.approvals)).mappings().one()
        assert stored["action_digest"] == approval.action_digest
        assert stored["created_at"] == NOW
        approval.normalized_args["fixture"] = False
        with pytest.raises(ValueError, match="canonical action"):
            insert_snapshot(c, approval)
        # FK forbids deleting a run with retained approval evidence.
        expect_constraint(c, schema.runs.delete(), "fk_approvals_run_id_runs")


def test_schema_knowledge_exact_version_and_uniqueness(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    doc = document_id("data/knowledge/fixture.md")
    document = KnowledgeDocument(
        document_id=doc,
        source_path="data/knowledge/fixture.md",
        content_digest=DIGEST,
        title="Fixture",
    )
    chunk = KnowledgeChunk(
        chunk_id=chunk_id(doc, DIGEST, 0),
        document_id=doc,
        document_digest=DIGEST,
        ordinal=0,
        content="fictional",
    )
    with engine.begin() as c:
        insert_snapshot(c, document)
        insert_snapshot(c, chunk)
        expect_constraint(
            c,
            schema.knowledge_chunks.insert().values(
                **{
                    **chunk.model_dump(),
                    "chunk_id": "mismatch",
                    "document_digest": "b" * 64,
                }
            ),
            "fk_knowledge_chunks_document_version",
        )
        expect_constraint(
            c,
            schema.knowledge_chunks.insert().values(
                **{**chunk.model_dump(), "chunk_id": "duplicate"}
            ),
            "uq_knowledge_chunks_ordinal",
        )
        expect_constraint(
            c,
            schema.knowledge_documents.insert().values(
                **{**document.model_dump(), "document_id": "other"}
            ),
            "uq_knowledge_documents_path",
        )
        insert_snapshot(
            c,
            KnowledgeChunk(
                chunk_id=chunk_id(doc, DIGEST, 1),
                document_id=doc,
                document_digest=DIGEST,
                ordinal=1,
                content="alternate",
            ),
        )


def snapshot(engine: Engine, names: set[str]) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as c:
        return {
            name: [
                dict(row)
                for row in c.execute(
                    select(schema.metadata.tables[name]).order_by(
                        *schema.metadata.tables[name].primary_key.columns
                    )
                ).mappings()
            ]
            for name in sorted(names)
        }


def assert_reset_oracle(
    demo: dict[str, list[dict[str, Any]]],
    evidence: dict[str, list[dict[str, Any]]],
    before: dict[str, list[dict[str, Any]]],
) -> None:
    seed = load_seed().model_dump()
    assert demo == {
        "demo_services": sorted(seed["services"], key=lambda row: row["service_id"]),
        "demo_incidents": sorted(seed["incidents"], key=lambda row: row["incident_id"]),
        "demo_notifications": [],
        "demo_incident_notes": [],
    }
    assert evidence == before


def test_reset_twice_exact_fixture_preserves_every_non_demo_table(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    with pytest.raises(ValueError, match="confirmation"):
        reset_demo(engine)
    with engine.begin() as c:
        insert_snapshot(c, run_record())
        insert_snapshot(c, approval_record())
        insert_snapshot(c, memory_record())
        insert_snapshot(
            c,
            EffectReceipt(
                receipt_id="receipt-1",
                run_id="run-1",
                tool_name="fixture",
                idempotency_key="key-1",
                action_digest=DIGEST,
                result_digest=DIGEST,
                applied_at=NOW,
            ),
        )
        insert_snapshot(
            c,
            AuditEvent(
                event_id="event-1",
                run_id="run-1",
                sequence_number=1,
                event_type="SAFE",
                payload={"safe": True},
                timestamp=NOW,
            ),
        )
        doc = document_id("data/knowledge/fixture.md")
        insert_snapshot(
            c,
            KnowledgeDocument(
                document_id=doc,
                source_path="data/knowledge/fixture.md",
                content_digest=DIGEST,
                title="Fixture",
            ),
        )
        insert_snapshot(
            c,
            KnowledgeChunk(
                chunk_id=chunk_id(doc, DIGEST, 0),
                document_id=doc,
                document_digest=DIGEST,
                ordinal=0,
                content="fixture",
            ),
        )
        c.execute(
            schema.demo_services.insert().values(
                service_id="residue", status="fictional"
            )
        )
        c.execute(
            schema.demo_incidents.insert().values(
                incident_id="residue",
                service_id="residue",
                summary="residue",
                status="closed",
            )
        )
        c.execute(
            schema.demo_incident_notes.insert().values(
                note_id="residue", incident_id="residue", note="residue", created_at=NOW
            )
        )
        c.execute(
            schema.demo_notifications.insert().values(
                notification_id="residue",
                channel="demo",
                message="residue",
                created_at=NOW,
            )
        )
    demo_names = {name for name in TABLE_NAMES if name.startswith("demo_")}
    other_names = TABLE_NAMES - demo_names
    before = snapshot(engine, other_names)
    reset_demo(engine, confirm_development_reset=True)
    first = snapshot(engine, demo_names)
    assert_reset_oracle(first, snapshot(engine, other_names), before)
    reset_demo(engine, confirm_development_reset=True)
    assert snapshot(engine, demo_names) == first
    assert_reset_oracle(
        snapshot(engine, demo_names), snapshot(engine, other_names), before
    )
    # Intentionally bad actual DB state must fail the same reset oracle.
    with engine.begin() as c:
        c.execute(schema.runs.update().values(request_text="sentinel corruption"))
    with pytest.raises(AssertionError):
        assert_reset_oracle(first, snapshot(engine, other_names), before)
    with engine.begin() as c:
        c.execute(schema.demo_services.update().values(status="fixture drift"))
    with pytest.raises(AssertionError):
        assert_reset_oracle(snapshot(engine, demo_names), before, before)
