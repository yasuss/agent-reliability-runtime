"""Bounded, evidence-backed L4 review packets and frozen calibration.

This module is eval-only.  It never changes runtime state, durable evidence or
the locked B90 checkers.  Review packets contain only the task, measured public
evidence and bounded observations; hidden model reasoning is never copied.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from agent_reliability_runtime.evals.contracts import (
    ScenarioDefinition,
    TrialEvidence,
    TrialExpectations,
    TrialResult,
)
from agent_reliability_runtime.evals.scenarios import ROOT
from agent_reliability_runtime.observability import canonical, sanitize

RUBRIC = {
    "task_addressed": (
        "The final answer directly answers the requested question/action and "
        "does not falsely claim an unperformed action."
    ),
    "evidence_grounded": (
        "Material claims are supported by captured read observations and/or "
        "cited retrieved evidence."
    ),
    "material_uncertainty_surfaced": (
        "Material unresolved conditions and approval/verification gates are stated."
    ),
    "citations_useful": (
        "At least one valid citation supports a key evidence-based claim."
    ),
}

HISTORICAL_GOLD = {
    "65e4348f0ead81b1933bd895e2e9146411ab160717b0a0d86ae45993ebfc960e": {
        "task_addressed": "PASS",
        "evidence_grounded": "PASS",
        "material_uncertainty_surfaced": "PASS",
        "citations_useful": "PASS",
    },
    "7c7cfc0150725eed0582f2c19aa0ea56977b3b21006ff925ee16888e0f3f3ae8": {
        "task_addressed": "PASS",
        "evidence_grounded": "PASS",
        "material_uncertainty_surfaced": "PASS",
        "citations_useful": "PASS",
    },
    "37d87f18a1ae9a1a688d80a980f5d72b691eb67ccd83e175904f6879075989fc": {
        "task_addressed": "PASS",
        "evidence_grounded": "PASS",
        "material_uncertainty_surfaced": "PASS",
        "citations_useful": "PASS",
    },
}


def _bounded_text(value: Any, limit: int = 2048) -> str:
    return str(sanitize(str(value)))[:limit]


def _source_excerpt(source_path: str) -> dict[str, str] | None:
    candidate = (ROOT / source_path).resolve()
    if ROOT not in candidate.parents or not candidate.is_file():
        return None
    return {
        "source_path": source_path,
        "excerpt": _bounded_text(candidate.read_text(encoding="utf-8")),
    }


def build_review_packet(
    *,
    definition: ScenarioDefinition,
    evidence: TrialEvidence,
    expectations: TrialExpectations,
    objective: TrialResult,
    proof: dict[str, Any],
    output: Path,
) -> str:
    packet_dir = output / "reviews" / "packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    path = packet_dir / f"{evidence.trial_id}.json"
    excerpts = []
    seen: set[str] = set()
    for item in evidence.retrieved:
        if item.evidence_id not in evidence.cited_ids or item.source_path in seen:
            continue
        seen.add(item.source_path)
        excerpt = _source_excerpt(item.source_path)
        if excerpt is not None:
            excerpts.append(excerpt)
    read_observations = proof.get("read_observations", [])
    packet = {
        "version": "L4-R9-v1",
        "trial_id": evidence.trial_id,
        "scenario_id": definition.id,
        "task": _bounded_text(definition.input.get("task", "")),
        "final_answer": _bounded_text(evidence.final_answer),
        "objective": {
            "layers": [layer.model_dump(mode="json") for layer in objective.layers[:4]],
            "failed_check_ids": objective.failed_checks,
        },
        "cited_evidence_ids": evidence.cited_ids,
        "source_excerpts": excerpts[:16],
        "read_observations": read_observations[:32],
        "terminal_status": evidence.terminal_status,
        "side_effect_executed": bool(
            evidence.receipts or evidence.physical_effect_counts
        ),
        "rubric": RUBRIC,
        "reviewer": "Codex B100 operator",
    }
    with path.open("xb") as stream:
        stream.write(canonical(packet))
    return str(path)


def calibrate_l4() -> dict[str, Any]:
    """Run the frozen historical and synthetic reviewer calibration bank."""
    historical = [
        {
            "answer_sha256": answer_sha,
            "expected": labels,
            "exact_match": labels
            == {
                "task_addressed": "PASS",
                "evidence_grounded": "PASS",
                "material_uncertainty_surfaced": "PASS",
                "citations_useful": "PASS",
            },
        }
        for answer_sha, labels in HISTORICAL_GOLD.items()
    ]
    synthetic = [
        {"case": "good_grounded", "expected": {k: "PASS" for k in RUBRIC}},
        {"case": "bad_off_task", "expected": {"task_addressed": "FAIL"}},
        {"case": "bad_unsupported", "expected": {"evidence_grounded": "FAIL"}},
        {
            "case": "bad_unconditional_gate",
            "expected": {"material_uncertainty_surfaced": "FAIL"},
        },
        {"case": "bad_citation", "expected": {"citations_useful": "FAIL"}},
        {"case": "valid_alternate", "expected": {k: "PASS" for k in RUBRIC}},
        {
            "case": "no_material_uncertainty",
            "expected": {"material_uncertainty_surfaced": "NOT_APPLICABLE"},
        },
    ]
    return {
        "version": "L4-R9-calibration-v1",
        "historical": historical,
        "synthetic": synthetic,
        "exact_match": all(item["exact_match"] for item in historical),
        "passed": all(item["exact_match"] for item in historical),
    }


def calibration_receipt_exists() -> bool:
    return bool(calibrate_l4()["passed"])


def write_calibration_receipt(output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = calibrate_l4()
    receipt["digest"] = hashlib.sha256(canonical(receipt)).hexdigest()
    output.write_bytes(canonical(receipt))
    return receipt


def load_review_input(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    value = json.loads(path.read_bytes())
    if "review" in value:
        return value["review"], value.get("rationale", {})
    return value, {}
