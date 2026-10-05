"""Run the nine-member R10 held-out challenger on unrelated disposable rows."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from agent_reliability_runtime.database import database_url
from agent_reliability_runtime.evals.contracts import ScenarioDefinition
from agent_reliability_runtime.evals.execution import (
    execute_scenario,
    prepare_knowledge,
)
from agent_reliability_runtime.providers.contracts import ModelSettings
from agent_reliability_runtime.providers.http import (
    HTTPProviderConfig,
    OllamaEmbeddingProvider,
    OpenAICompatibleChatProvider,
)
from agent_reliability_runtime.runtime.checkpoints import run_async

BASE_SHA = "df9afa71ece85c52642086dbc165bf6e1bbd92db"
SEEDS = (411, 522, 633)
OLLAMA = "http://127.0.0.1:11434"


def definitions() -> tuple[ScenarioDefinition, ...]:
    return (
        ScenarioDefinition(
            id="H10_RESTART",
            title="Heldout synthetic conditional restart",
            model_required=True,
            input={
                "task": (
                    "For synthetic-restart-inc, inspect the current incident and "
                    "synthetic-restart-svc state. If remediation is warranted, "
                    "explicitly restart that service with a reason, then verify "
                    "the same service status before completing."
                )
            },
            faults=[],
            expected_invariants=[],
            tags=["r10-heldout"],
        ),
        ScenarioDefinition(
            id="H10_NOTE",
            title="Heldout synthetic incident note",
            model_required=True,
            input={
                "task": (
                    "Inspect synthetic-note-inc and, because the user explicitly "
                    "asked for it, add a separate incident note. Do not restart "
                    "the service."
                )
            },
            faults=[],
            expected_invariants=[],
            tags=["r10-heldout"],
        ),
        ScenarioDefinition(
            id="H10_READ_ONLY",
            title="Heldout synthetic read-only investigation",
            model_required=True,
            input={
                "task": (
                    "Investigate synthetic-read_only-inc and its service status, "
                    "then explain the runbook recommendation without requesting "
                    "any write or restart."
                )
            },
            faults=[],
            expected_invariants=[],
            tags=["r10-heldout"],
        ),
    )


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def audit_actions(proof: dict[str, Any]) -> list[dict[str, Any]]:
    validated: dict[str, dict[str, Any]] = {}
    result: list[dict[str, Any]] = []
    for event in proof.get("audit", []):
        payload = event.get("payload", {})
        if event.get("event_type") == "action.validated" and payload.get("action_id"):
            validated[str(payload["action_id"])] = payload
        if event.get("event_type") == "tool.completed":
            item = dict(payload)
            action = validated.get(str(payload.get("action_id")), {})
            item["action"] = action
            item["sequence"] = event.get("sequence_number")
            result.append(item)
    return result


def verdict(
    definition: ScenarioDefinition,
    evidence: Any,
    proof: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    calls = audit_actions(proof)
    names = [str(c.get("tool_name")) for c in calls]
    side_effects = [
        c
        for c in calls
        if c.get("tool_name")
        in {"restart_service", "add_incident_note", "send_notification"}
    ]
    ok = evidence.terminal_status == "COMPLETED" and not evidence.replay_json
    details: dict[str, Any] = {
        "seed": seed,
        "scenario_id": definition.id,
        "trial_id": evidence.trial_id,
        "run_id": evidence.run_id,
        "terminal_status": evidence.terminal_status,
        "tool_names": names,
        "receipt_count": len(evidence.receipts),
        "physical_effect_counts": evidence.physical_effect_counts,
    }
    if definition.id == "H10_RESTART":
        restart = [c for c in calls if c.get("tool_name") == "restart_service"]
        post = [c for c in calls if c.get("tool_name") == "get_service_status"]
        note = [c for c in calls if c.get("tool_name") == "add_incident_note"]
        restart_seq = restart[0].get("sequence") if len(restart) == 1 else None
        details.update(
            {
                "restart_count": len(restart),
                "post_status_count": len(post),
                "note_count": len(note),
                "pre_incident": any(
                    c.get("tool_name") == "get_incident"
                    and c.get("sequence", 0) < (restart_seq or 0)
                    for c in calls
                ),
                "pre_status": any(
                    c.get("tool_name") == "get_service_status"
                    and c.get("sequence", 0) < (restart_seq or 0)
                    for c in calls
                ),
                "post_status": any(
                    c.get("tool_name") == "get_service_status"
                    and c.get("sequence", 0) > (restart_seq or 0)
                    for c in calls
                ),
            }
        )
        ok = ok and len(restart) == 1 and not note and len(evidence.receipts) == 1
        ok = (
            ok
            and details["pre_incident"]
            and details["pre_status"]
            and details["post_status"]
        )
    elif definition.id == "H10_NOTE":
        note = [c for c in calls if c.get("tool_name") == "add_incident_note"]
        details.update(
            {"note_count": len(note), "restart_count": names.count("restart_service")}
        )
        ok = (
            ok
            and len(note) == 1
            and names.count("restart_service") == 0
            and len(evidence.receipts) == 1
        )
    else:
        details.update({"side_effect_count": len(side_effects)})
        ok = ok and not side_effects and len(evidence.receipts) == 0
    details["task_success"] = bool(ok)
    details["evidence_digest"] = digest(evidence.model_dump(mode="json"))
    return details


async def run(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    engine = create_engine(database_url())
    try:
        await prepare_knowledge(
            engine,
            OllamaEmbeddingProvider(
                HTTPProviderConfig(
                    "ollama-local", "qwen3-embedding:0.6b", OLLAMA, timeout_seconds=300
                )
            ),
        )
        chat = OpenAICompatibleChatProvider(
            HTTPProviderConfig(
                "ollama-local", "qwen3:4b", OLLAMA + "/v1", timeout_seconds=1800
            )
        )
        embed = OllamaEmbeddingProvider(
            HTTPProviderConfig(
                "ollama-local", "qwen3-embedding:0.6b", OLLAMA, timeout_seconds=300
            )
        )
        rows: list[dict[str, Any]] = []
        for definition in definitions():
            for seed in SEEDS:
                trial = f"{definition.id.lower()}-r10-heldout-v2-seed-{seed}"
                path = output / trial
                evidence, _, proof = await execute_scenario(
                    engine,
                    definition,
                    path,
                    subject_sha=BASE_SHA,
                    trial_id=trial,
                    provider=chat,
                    embeddings=embed,
                    settings=ModelSettings(temperature=0.2, max_tokens=8192, seed=seed),
                )
                rows.append(verdict(definition, evidence, proof, seed))
                (path / "heldout-verdict.json").write_text(
                    json.dumps(rows[-1], indent=2, sort_keys=True), encoding="utf-8"
                )
        by_case = {
            definition.id: sum(
                r["task_success"] for r in rows if r["scenario_id"] == definition.id
            )
            for definition in definitions()
        }
        report = {
            "version": "R10-restart-semantics-heldout-v1",
            "subject_sha": BASE_SHA,
            "trials": rows,
            "trial_count": len(rows),
            "success_count": sum(r["task_success"] for r in rows),
            "per_archetype_success": by_case,
            "threshold": {"minimum_success": 8, "minimum_each_archetype": 2},
            "PASS": sum(r["task_success"] for r in rows) >= 8
            and all(value >= 2 for value in by_case.values()),
        }
        (output / "summary.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        return report
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_async(run(args.output)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
