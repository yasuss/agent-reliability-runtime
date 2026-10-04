"""Fail-closed exporter and validator for the two exact locked schema subsets."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine

from agent_reliability_runtime.observability import (
    AuditTrail,
    canonical,
    public_safe,
    read_run,
    sanitize,
)

SCHEMAS = Path(__file__).resolve().parents[2] / "docs/project/spec/v1.0/schemas"
KEYWORDS = {
    "$schema",
    "$id",
    "type",
    "additionalProperties",
    "required",
    "properties",
    "const",
    "enum",
    "pattern",
    "minLength",
    "minimum",
    "minItems",
    "items",
}


def validate(value: Any, schema: dict[str, Any]) -> None:
    if set(schema) - KEYWORDS:
        raise ValueError("unsupported locked schema keyword")
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int}
    if kind and (kind not in types or type(value) is not types[kind]):
        raise ValueError("schema type mismatch")
    if "const" in schema and value != schema["const"]:
        raise ValueError("schema const mismatch")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("schema enum mismatch")
    if isinstance(value, dict):
        if not set(schema.get("required", [])) <= set(value):
            raise ValueError("schema missing field")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key])
            else:
                additional = schema.get("additionalProperties", True)
                if additional is False:
                    raise ValueError("schema extra field")
                if isinstance(additional, dict):
                    validate(item, additional)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ValueError("schema array too short")
        for item in value:
            if "items" in schema:
                validate(item, schema["items"])
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError("schema string too short")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise ValueError("schema pattern mismatch")
    if type(value) is int and value < schema.get("minimum", value):
        raise ValueError("schema minimum mismatch")


def locked_validate(value: Any, name: str) -> None:
    if name not in {"replay", "acceptance_receipt"}:
        raise ValueError("unknown locked schema")
    validate(value, json.loads((SCHEMAS / (name + ".schema.json")).read_text()))


def accepted_receipt(receipt: dict[str, Any], source_sha: str) -> str:
    locked_validate(receipt, "acceptance_receipt")
    gates = list(receipt["gates"].values())
    if (
        receipt["git_sha"] != source_sha
        or not gates
        or "PASS" not in gates
        or not set(gates) <= {"PASS", "NOT_APPLICABLE"}
    ):
        raise ValueError("receipt is not accepted for source SHA")
    return hashlib.sha256(canonical(receipt)).hexdigest()


def write_candidate(
    candidate: dict[str, Any], manifest: dict[str, Any], output: Path
) -> None:
    # Public byte checker follows schema validation, before any artifact write.
    locked_validate(candidate, "replay")
    data = canonical(candidate)
    public_safe(data)
    sidecar = output.with_suffix(output.suffix + ".manifest.json")
    manifest = dict(manifest, replay_sha256=hashlib.sha256(data).hexdigest())
    mdata = canonical(manifest)
    public_safe(mdata)
    temp = output.with_name(output.name + "." + uuid4().hex + ".tmp")
    mtemp = sidecar.with_name(sidecar.name + "." + uuid4().hex + ".tmp")
    try:
        temp.write_bytes(data)
        mtemp.write_bytes(mdata)
        temp.replace(output)
        mtemp.replace(sidecar)
    finally:
        temp.unlink(missing_ok=True)
        mtemp.unlink(missing_ok=True)


def export_replay(
    engine: Engine, run_id: str, receipt: dict[str, Any], source_sha: str, output: Path
) -> None:
    digest = accepted_receipt(receipt, source_sha)
    with engine.connect() as con:
        run = read_run(con, run_id)
    if (
        run is None
        or run.scenario_id is None
        or run.status
        not in {"COMPLETED", "REJECTED", "FAILED", "BUDGET_EXCEEDED", "CANCELLED"}
    ):
        raise ValueError("run is not an exportable terminal scenario")
    audit = AuditTrail(engine).list(run_id)
    if not audit or [e.sequence_number for e in audit] != list(
        range(1, len(audit) + 1)
    ):
        raise ValueError("audit sequence gap")
    events = [{"seq": 1, "type": "request", "summary": sanitize(run.request_text)}]
    for event in audit:
        events.append(
            {
                "seq": len(events) + 1,
                "type": event.event_type,
                "summary": event.event_type,
                "data": sanitize(event.payload),
            }
        )
    events.append(
        {
            "seq": len(events) + 1,
            "type": "eval.acceptance",
            "summary": "Accepted evaluation receipt",
            "data": {"gates": receipt["gates"], "receipt_digest": digest},
        }
    )
    replay = {
        "schema_version": "1.0",
        "run_id": run_id,
        "scenario_id": run.scenario_id,
        "mode": "recorded_acceptance_replay",
        "source_git_sha": source_sha,
        "eval_receipt_digest": digest,
        "events": events,
        "final_status": run.status.value,
    }
    write_candidate(
        replay,
        {
            "source_run_id": run_id,
            "source_git_sha": source_sha,
            "acceptance_receipt_digest": digest,
        },
        output,
    )
