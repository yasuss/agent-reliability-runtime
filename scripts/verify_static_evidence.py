"""Fail-closed verifier for the five B110 Static Evidence Demo replays."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from agent_reliability_runtime.observability import canonical, public_safe
from agent_reliability_runtime.replay import locked_validate

ACCEPTED_SHA = "83514ebad336dbd6faf1b790c597ec8037be0874"
EXPECTED = (
    ("grounded-read", "S01_READ_ONLY_GROUNDED"),
    ("approval-side-effect", "S02_APPROVAL_REQUIRED"),
    ("prompt-injection-blocked", "S05_RAG_PROMPT_INJECTION"),
    ("process-restart-exactly-once", "S08_PROCESS_KILL_RESUME"),
    ("memory-poisoning-blocked", "S10_MEMORY_POISONING"),
)
FORBIDDEN_KEYS = {
    "prompt",
    "messages",
    "raw_prompt",
    "raw_arguments",
    "arguments",
    "reasoning",
    "chain_of_thought",
    "credentials",
    "authorization",
    "api_key",
    "password",
    "token",
    "secret",
}
SECRET_PATTERNS = (
    re.compile(r"ARR_FORBIDDEN_SECRET_[A-Za-z0-9_]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
)


def _walk_public(value: Any) -> None:
    if isinstance(value, dict):
        if {str(key).lower() for key in value} & FORBIDDEN_KEYS:
            raise ValueError("forbidden public replay field")
        for key, item in value.items():
            if any(pattern.search(str(key)) for pattern in SECRET_PATTERNS):
                raise ValueError("secret-like replay key")
            _walk_public(item)
    elif isinstance(value, list):
        for item in value:
            _walk_public(item)
    elif isinstance(value, str) and any(
        pattern.search(value) for pattern in SECRET_PATTERNS
    ):
        raise ValueError("secret-like replay value")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def verify_collection(root: Path) -> dict[str, Any]:
    manifest = _read_json(root / "index.json")
    if (
        manifest.get("schema_version") != "b110-index-v1"
        or manifest.get("accepted_source_git_sha") != ACCEPTED_SHA
    ):
        raise ValueError("manifest version or source SHA mismatch")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or [e.get("slug") for e in entries] != [
        s for s, _ in EXPECTED
    ]:
        raise ValueError("manifest must contain the exact five entries in order")
    for entry, (slug, scenario_id) in zip(entries, EXPECTED, strict=True):
        if (
            entry.get("source_git_sha") != ACCEPTED_SHA
            or entry.get("scenario_id") != scenario_id
        ):
            raise ValueError(f"{slug}: provenance mismatch")
        replay_path, receipt_path = (
            root / slug / "replay.json",
            root / slug / "receipt.json",
        )
        replay_bytes, receipt_bytes = (
            replay_path.read_bytes(),
            receipt_path.read_bytes(),
        )
        if hashlib.sha256(replay_bytes).hexdigest() != entry.get(
            "replay_sha256"
        ) or hashlib.sha256(receipt_bytes).hexdigest() != entry.get("receipt_sha256"):
            raise ValueError(f"{slug}: byte digest mismatch")
        replay, receipt = _read_json(replay_path), _read_json(receipt_path)
        locked_validate(replay, "replay")
        locked_validate(receipt, "acceptance_receipt")
        if (
            replay["eval_receipt_digest"]
            != hashlib.sha256(canonical(receipt)).hexdigest()
        ):
            raise ValueError(f"{slug}: receipt binding mismatch")
        if (
            replay["source_git_sha"] != ACCEPTED_SHA
            or receipt["git_sha"] != ACCEPTED_SHA
        ):
            raise ValueError(f"{slug}: provenance mismatch")
        if (
            receipt["gates"].get("TASK_SUCCESS") != "PASS"
            or receipt["gates"].get("HARD_INVARIANTS") != "PASS"
        ):
            raise ValueError(f"{slug}: acceptance gates are not PASS")
        if (
            slug == "process-restart-exactly-once"
            and replay["final_status"] != "COMPLETED"
        ):
            raise ValueError("S08 replay is not completed")
        events = replay["events"]
        if [event["seq"] for event in events] != list(range(1, len(events) + 1)):
            raise ValueError(f"{slug}: event sequence is not contiguous")
        types = [event["type"] for event in events]
        if slug == "process-restart-exactly-once":
            if "recovery.resumed" not in types or "eval.acceptance" not in types:
                raise ValueError("S08 recovery/evaluation evidence missing")
            if not any(
                event["type"] == "tool.completed"
                and event.get("data", {}).get("replayed") is True
                for event in events
            ):
                raise ValueError("S08 replayed tool completion missing")
        _walk_public(replay)
        _walk_public(receipt)
        public_safe(replay_bytes)
        public_safe(receipt_bytes)
    return {
        "entries": len(entries),
        "receipt_gates_pass": len(entries),
        "source_git_sha": ACCEPTED_SHA,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root", type=Path, nargs="?", default=Path("web/public/replays")
    )
    args = parser.parse_args()
    print(json.dumps(verify_collection(args.root), sort_keys=True))


if __name__ == "__main__":
    main()
