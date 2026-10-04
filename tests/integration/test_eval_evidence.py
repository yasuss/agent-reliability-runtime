"""Small real-evidence compatibility proof; not the B100 scenario campaign."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from agent_reliability_runtime.demo_state.reset import reset_demo
from agent_reliability_runtime.evals.adapter import capture, environment_snapshot
from agent_reliability_runtime.evals.calibration import replace
from agent_reliability_runtime.evals.contracts import TrialExpectations
from agent_reliability_runtime.evals.harness import evaluate
from agent_reliability_runtime.evals.receipts import make_receipt, validate_receipt
from agent_reliability_runtime.evals.scenarios import IDS, load_scenarios
from agent_reliability_runtime.mcp.client import OpsDeskMCPClient
from agent_reliability_runtime.mcp.contracts import ReceiptEnvelope
from agent_reliability_runtime.observability import AuditTrail
from agent_reliability_runtime.policy import Action
from agent_reliability_runtime.replay import export_replay
from agent_reliability_runtime.retrieval.service import ingest, retrieve
from agent_reliability_runtime.retrieval.text import plan_source
from agent_reliability_runtime.runtime.checkpoints import run_async, setup_checkpoints
from agent_reliability_runtime.runtime.service import open_runtime
from scripts.runtime_proof_support import (
    Embeddings,
    ScriptedProvider,
    context_for,
    run_record,
)

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def test_actual_read_approval_effect_retrieval_replay(
    isolated_db: tuple[Engine, Config], tmp_path: Path
) -> None:
    engine, _ = isolated_db
    records = []

    async def exercise() -> None:
        await setup_checkpoints(engine.url)
        reset_demo(engine, confirm_development_reset=True)
        await ingest(
            engine,
            Embeddings(),
            plan_source(
                "fixture/eval-runbook.md",
                b"# Checkout\nSafe incident diagnosis and notification.",
            ),
        )
        retrieved = list(await retrieve(engine, Embeddings(), "checkout incident"))
        assert retrieved
        async with OpsDeskMCPClient(
            ROOT, engine.url.render_as_string(hide_password=False)
        ) as client:
            for mode, scenario in [("read", IDS[0]), ("side", IDS[8])]:
                actions = []

                async def hook(state: dict[str, Any], raw: dict[str, Any]) -> None:
                    actions.append(Action.model_validate(state["action"]))

                before = environment_snapshot(engine)
                ctx = context_for(
                    engine, client, ScriptedProvider(mode), fault_hook=hook
                )
                run = run_record("b90-" + mode).model_copy(
                    update={"scenario_id": scenario}
                )
                async with open_runtime(ctx, engine.url) as runtime:
                    state = await runtime.start(run)
                    if mode == "side":
                        assert state["status"] == "WAITING_APPROVAL"
                        approval_id = state["approval_id"]
                        ctx.gateway.approvals.decide(approval_id, approved=True)
                        state = await runtime.resume(run.run_id, "continue")
                    assert state["status"] == "COMPLETED"
                evidence = capture(
                    engine,
                    run_id=run.run_id,
                    scenario_id=scenario,
                    subject_sha="a" * 40,
                    trial_id="real-" + mode,
                    actions=actions,
                    before=before,
                    retrieved=retrieved,
                    cited_ids=[retrieved[0].evidence_id],
                    final_answer="Safe result",
                )
                mutations: dict[str, Literal["added", "changed", "deleted"]] = (
                    {
                        "demo_notifications/"
                        + evidence.receipts[0].logical_identity: "added"
                    }
                    if mode == "side"
                    else {}
                )
                expected = TrialExpectations(
                    retrieval_applies=True,
                    expected_sources=["fixture/eval-runbook.md"],
                    required_tools=[
                        "get_service_status" if mode == "read" else "send_notification"
                    ],
                    required_approval_states=[]
                    if mode == "read"
                    else ["PENDING", "APPROVED"],
                    expected_effects=0 if mode == "read" else 1,
                    expected_mutations=mutations,
                )
                definition = next(s for s in load_scenarios()[0] if s.id == scenario)
                result = evaluate(definition, evidence, expected)
                assert result.task_success, result.model_dump()
                receipt = make_receipt(
                    result, lambda: datetime(2026, 10, 4, tzinfo=UTC)
                )
                validate_receipt(receipt, "a" * 40)
                path = tmp_path / (mode + ".json")
                export_replay(engine, run.run_id, receipt, "a" * 40, path)
                with_replay = replace(evidence, replay_json=path.read_text())
                assert evaluate(definition, with_replay, expected).task_success
                bad_citation = replace(evidence, cited_ids=["0" * 64])
                assert (
                    "citation_subset"
                    in evaluate(
                        definition, bad_citation, expected
                    ).hard_invariant_failures
                )
                bad_replay = json.loads(path.read_bytes())
                bad_replay["events"][0]["summary"] = "ARR_" + "FORBIDDEN_SECRET_real"
                assert (
                    "secret_replay"
                    in evaluate(
                        definition,
                        replace(evidence, replay_json=json.dumps(bad_replay)),
                        expected,
                    ).hard_invariant_failures
                )
                if mode == "side":
                    bypass = replace(evidence, approvals=[])
                    assert (
                        "approval_exactness"
                        in evaluate(
                            definition, bypass, expected
                        ).hard_invariant_failures
                    )
                    duplicate = replace(
                        evidence,
                        physical_effect_counts={
                            evidence.receipts[0].logical_identity: 2
                        },
                    )
                    assert (
                        "duplicate_effect"
                        in evaluate(
                            definition, duplicate, expected
                        ).hard_invariant_failures
                    )
                    # Actual same-key reconciliation through the accepted Gateway;
                    # no second mutation, original receipt returned replayed.
                    envelope = ReceiptEnvelope.model_validate(
                        (
                            await ctx.gateway.execute(actions[0], approval_id)
                        ).model_dump()
                    )
                    assert envelope.replayed
                    AuditTrail(engine).append(
                        run.run_id,
                        "tool.completed",
                        {
                            "tool_name": "send_notification",
                            "risk_class": "SIDE_EFFECT",
                            "success": True,
                            "receipt_id": envelope.receipt_id,
                            "result_digest": envelope.result_digest,
                            "replayed": True,
                        },
                    )
                    alternate = capture(
                        engine,
                        run_id=run.run_id,
                        scenario_id=scenario,
                        subject_sha="a" * 40,
                        trial_id="real-replay",
                        actions=actions,
                        before=before,
                        retrieved=retrieved,
                        cited_ids=[retrieved[0].evidence_id],
                    )
                    assert evaluate(definition, alternate, expected).task_success
                    assert (
                        len(alternate.receipts) == 1
                        and sum(alternate.physical_effect_counts.values()) == 1
                    )
                records.append(
                    {
                        "mode": mode,
                        "evidence": evidence.model_dump(mode="json"),
                        "result": result.model_dump(mode="json"),
                        "receipt": receipt,
                        "manifest": json.loads(
                            path.with_suffix(".json.manifest.json").read_bytes()
                        ),
                    }
                )

    run_async(exercise())
    (tmp_path / "eval-real-evidence-proof.json").write_text(
        json.dumps(records, indent=2)
    )
