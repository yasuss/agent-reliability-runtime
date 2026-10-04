"""Real PostgreSQL scope/profile/API and transient checkpoint memory proofs."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, func, select

from agent_reliability_runtime.api import create_app
from agent_reliability_runtime.contracts.domain import MemoryKind
from agent_reliability_runtime.memory import MemoryError, MemoryStore
from agent_reliability_runtime.persistence import schema
from agent_reliability_runtime.persistence.records import insert_snapshot
from agent_reliability_runtime.runtime.checkpoints import run_async
from scripts.probe_memory import graph_proof, no_marker
from scripts.runtime_proof_support import run_record

pytestmark = pytest.mark.integration


def test_creation_profiles_scopes_and_physical_delete(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    now = datetime.now(UTC)
    ids = iter(["z", "a", "b", "c", "foreign-user", "foreign-workspace", "optional"])
    store = MemoryStore(engine, clock=lambda: now, id_factory=lambda: next(ids))
    with engine.begin() as con:
        insert_snapshot(con, run_record("source"))
        insert_snapshot(
            con, run_record("foreign-source").model_copy(update={"user_id": "foreign"})
        )
    pref = store.user_explicit("local", "test", "preference")
    fact = store.user_explicit("local", "test", "fact", kind=MemoryKind.VERIFIED_FACT)
    tool = store.tool_verified(
        "local",
        "test",
        "verified",
        source_run_id="source",
        source_tool_name="get_incident",
    )
    model = store.model_observation(
        "local", "test", "observation", source_run_id="source"
    )
    assert (pref.kind, pref.provenance, pref.trust) == (
        "PREFERENCE",
        "USER_EXPLICIT",
        "TRUSTED",
    )
    assert (
        fact.kind == tool.kind == "VERIFIED_FACT" and tool.provenance == "TOOL_VERIFIED"
    )
    assert tool.trust == "TRUSTED" and tool.source_tool_name == "get_incident"
    assert (model.kind, model.provenance, model.trust, model.source_tool_name) == (
        "OBSERVATION",
        "MODEL_OBSERVATION",
        "UNTRUSTED",
        None,
    )
    other_user = store.user_explicit("local", "other", "private user")
    other_workspace = store.user_explicit("other", "test", "private workspace")
    optional = store.user_explicit(
        "local", "test", "same-scope source", source_run_id="source"
    )
    assert optional.provenance == "USER_EXPLICIT"
    ordered = [fact, tool, model, optional, pref]
    assert store.list("local", "test") == ordered
    assert store.resolve(
        "local",
        "test",
        [
            pref.memory_id,
            fact.memory_id,
            other_user.memory_id,
            other_workspace.memory_id,
        ],
    ) == [fact, pref]
    assert store.resolve("other", "other", [pref.memory_id]) == []
    for foreign in (other_user, other_workspace):
        assert store.get("local", "test", foreign.memory_id) is None
        assert not store.delete("local", "test", foreign.memory_id)
        assert (
            store.get(foreign.workspace_id, foreign.user_id, foreign.memory_id)
            == foreign
        )
    assert store.delete("local", "test", pref.memory_id)
    with engine.connect() as con:
        assert (
            con.scalar(
                select(func.count())
                .select_from(schema.memories)
                .where(schema.memories.c.memory_id == pref.memory_id)
            )
            == 0
        )
    assert not store.delete("local", "test", "absent")


@pytest.mark.parametrize(
    "bad",
    [
        "kind",
        "trusted_model",
        "model_tool",
        "unknown_tool",
        "missing_run",
        "foreign_run",
        "user_foreign",
        "missing_tool",
        "missing_model_run",
        "blank",
    ],
)
def test_bad_profiles_rejected_before_persistence(
    isolated_db: tuple[Engine, Config], bad: str
) -> None:
    engine, _ = isolated_db
    with engine.begin() as con:
        insert_snapshot(
            con, run_record("foreign").model_copy(update={"workspace_id": "other"})
        )
    store = MemoryStore(engine)
    with pytest.raises((MemoryError, ValidationError, TypeError)):
        if bad == "kind":
            store.user_explicit("local", "test", "bad", kind=MemoryKind.OBSERVATION)
        elif bad in {"trusted_model", "model_tool", "missing_model_run"}:
            extras: dict[str, Any] = {"source_run_id": "foreign"}
            if bad == "trusted_model":
                extras["trust"] = "TRUSTED"
            elif bad == "model_tool":
                extras["source_tool_name"] = "get_incident"
            else:
                extras = {}
            store.model_observation("local", "test", "bad", **extras)
        elif bad == "user_foreign":
            store.user_explicit("local", "test", "bad", source_run_id="foreign")
        elif bad == "blank":
            store.user_explicit("", "test", "bad")
        else:
            args: dict[str, Any] = {
                "source_run_id": "foreign" if bad == "foreign_run" else "absent",
                "source_tool_name": "unknown"
                if bad == "unknown_tool"
                else "get_incident",
            }
            if bad == "missing_run":
                args.pop("source_run_id")
            if bad == "missing_tool":
                args.pop("source_tool_name")
            store.tool_verified("local", "test", "bad", **args)
    with engine.connect() as con:
        assert con.scalar(select(func.count()).select_from(schema.memories)) == 0


def test_api_scope_order_validation_and_health(
    isolated_db: tuple[Engine, Config],
) -> None:
    engine, _ = isolated_db
    now = datetime.now(UTC)
    store = MemoryStore(engine, clock=lambda: now)
    first = store.user_explicit("w", "u", "first")
    later = MemoryStore(engine, clock=lambda: now + timedelta(seconds=1)).user_explicit(
        "w", "u", "later"
    )
    foreign = store.user_explicit("w", "v", "private")
    with TestClient(create_app(engine)) as client:
        own = {"workspace_id": "w", "user_id": "u"}
        assert client.get("/healthz").json() == {"status": "ok"}
        response = client.get("/api/v1/memory", params=own)
        assert [x["memory_id"] for x in response.json()] == [
            first.memory_id,
            later.memory_id,
        ]
        assert (
            client.get(
                "/api/v1/memory", params={"workspace_id": "absent", "user_id": "u"}
            ).json()
            == []
        )
        assert (
            client.get(
                "/api/v1/memory", params={"workspace_id": "w", "user_id": ""}
            ).status_code
            == 422
        )
        assert client.get("/api/v1/memory").status_code == 422
        missing = client.delete("/api/v1/memory/missing", params=own)
        other = client.delete("/api/v1/memory/" + foreign.memory_id, params=own)
        assert (
            missing.status_code == other.status_code == 404
            and missing.json() == other.json()
        )
        assert (
            client.delete("/api/v1/memory/" + first.memory_id, params=own).status_code
            == 204
        )
        assert client.post("/api/v1/memory", json={}).status_code == 405


@pytest.mark.parametrize("mode", ["personalize", "untrusted", "trusted"])
def test_memory_graph_and_delete_after_checkpoint(
    isolated_db: tuple[Engine, Config], mode: str
) -> None:
    result = run_async(graph_proof(isolated_db[0], mode))
    assert result["mode"] == mode


def test_checkpoint_leakage_checker_calibration() -> None:
    no_marker({"memory_ids": ["m1"], "messages": []}, "POISON_MARKER")
    with pytest.raises(AssertionError):
        no_marker({"messages": [{"content": "POISON_MARKER"}]}, "POISON_MARKER")
    no_marker({"messages": [], "memory_ids": ["m1"]}, "POISON_MARKER")
