"""Validate the locked specification against Git blobs, never worktree bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

PREFIX = "docs/project/spec/v1.0/"
MANIFEST = "PACKAGE_MANIFEST.json"
CHECKSUM = "PACKAGE_MANIFEST.sha256"
CATALOG_IDS = {
    "VC-FOUNDATION",
    "VC-SCOPE",
    "VC-PROVIDER-BOUNDARY",
    "VC-PERSISTENCE-RETRIEVAL",
    "VC-MCP-BOUNDARY",
    "VC-TRUSTED-EXECUTION",
    "VC-DURABLE-RUNTIME",
    "VC-GOVERNED-MEMORY",
    "VC-OBSERVABILITY-AUDIT",
    "VC-EVALUATION-HARNESS",
    "VC-RELIABILITY-ACCEPTANCE",
    "VC-STATIC-EVIDENCE",
    "VC-PORTABILITY",
    "VC-RELEASE-INTEGRITY",
}


def git_bytes(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)


def tracked_paths(root: Path, source: str) -> set[str]:
    if source == "index":
        data = git_bytes(root, "ls-files", "-z")
    elif source == "HEAD":
        data = git_bytes(root, "ls-tree", "-r", "-z", "--name-only", "HEAD")
    else:
        raise ValueError("source must be HEAD or index")
    return {p.decode("utf-8") for p in data.split(b"\0") if p}


def read_blob(root: Path, path: str, source: str) -> bytes:
    ref = ":" + path if source == "index" else "HEAD:" + path
    return git_bytes(root, "show", ref)


def payload_paths(paths: set[str]) -> list[str]:
    return sorted(
        p[len(PREFIX) :]
        for p in paths
        if p.startswith(PREFIX) and p[len(PREFIX) :] not in {MANIFEST, CHECKSUM}
    )


def manifest_bytes(root: Path, source: str = "index") -> bytes:
    entries = []
    for path in payload_paths(tracked_paths(root, source)):
        blob = read_blob(root, PREFIX + path, source)
        entries.append(
            {
                "path": path,
                "size": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
    return (
        json.dumps({"package": "context", "files": entries}, indent=2) + "\n"
    ).encode("utf-8")


def validate_manifest(root: Path, source: str) -> list[str]:
    errors = []
    actual_paths = tracked_paths(root, source)
    raw = read_blob(root, PREFIX + MANIFEST, source)
    declared = json.loads(raw)
    checksum = read_blob(root, PREFIX + CHECKSUM, source).decode("ascii").strip()
    if checksum != hashlib.sha256(raw).hexdigest() + "  " + MANIFEST:
        errors.append("manifest checksum mismatch")
    if declared.get("package") != "context" or not isinstance(
        declared.get("files"), list
    ):
        return errors + ["invalid manifest structure"]
    seen = set()
    for entry in declared["files"]:
        path = entry.get("path")
        if not isinstance(path, str) or path in seen:
            errors.append("invalid or duplicate manifest path")
            continue
        seen.add(path)
        if path not in payload_paths(actual_paths):
            errors.append(f"extra manifest path: {path}")
            continue
        raw_blob = read_blob(root, PREFIX + path, source)
        if type(entry.get("size")) is not int or entry["size"] != len(raw_blob):
            errors.append(
                f"manifest size mismatch: {path}: declared {entry.get('size')} "
                f"actual {len(raw_blob)}"
            )
        if entry.get("sha256") != hashlib.sha256(raw_blob).hexdigest():
            errors.append(f"manifest hash mismatch: {path}")
    for path in sorted(set(payload_paths(actual_paths)) - seen):
        errors.append(f"missing manifest path: {path}")
    return errors


def validate_traceability(
    requirements: dict[str, Any], catalog: dict[str, Any], paths: set[str]
) -> list[str]:
    errors = []
    rows = requirements.get("requirements", [])
    entries = catalog.get("entries", [])
    req_ids = [row.get("id") for row in rows]
    vc_ids = [entry.get("id") for entry in entries]
    if len(req_ids) != len(set(req_ids)) or set(req_ids) != {
        f"ARR-{n:03d}" for n in range(1, 27)
    }:
        errors.append("requirements must contain exactly the unique locked ARR IDs")
    if catalog.get("version") != "verification-catalog-v1":
        errors.append("invalid verification catalog version")
    if len(vc_ids) != len(set(vc_ids)) or set(vc_ids) != CATALOG_IDS:
        errors.append("catalog must contain exactly the unique semantic VC IDs")
    by_id = {
        entry["id"]: entry for entry in entries if isinstance(entry.get("id"), str)
    }
    reverse = {id: set() for id in by_id}
    for row in rows:
        id = row.get("id")
        ids = row.get("verification_ids")
        if (
            not isinstance(ids, list)
            or not ids
            or any(not isinstance(v, str) for v in ids)
        ):
            errors.append(f"{id}: nonempty verification_ids required")
            continue
        if len(set(ids)) != len(ids) or any(v not in by_id for v in ids):
            errors.append(f"{id}: unknown or duplicate verification ID")
            continue
        for v in ids:
            reverse[v].add(id)
        summary = "; ".join(
            by_id[v].get("title", "") + ": " + ", ".join(by_id[v].get("methods", []))
            for v in ids
        )
        if (
            row.get("acceptance") != summary
            or "acceptance gate" in row.get("acceptance", "").lower()
        ):
            errors.append(f"{id}: acceptance must derive from catalog title/methods")
    for id, entry in by_id.items():
        for field in ("title", "methods", "requirement_ids", "proof_paths"):
            if not entry.get(field):
                errors.append(f"{id}: missing {field}")
        methods = entry.get("methods", [])
        if not isinstance(methods, list) or any(
            not isinstance(m, str) or not m.strip() or "acceptance gate" in m.lower()
            for m in methods
        ):
            errors.append(f"{id}: invalid concrete verification methods")
        declared = entry.get("requirement_ids", [])
        if len(declared) != len(set(declared)) or set(declared) != reverse[id]:
            errors.append(f"{id}: bidirectional requirement mapping mismatch")
        executable = False
        for proof in entry.get("proof_paths", []):
            if not isinstance(proof, str):
                errors.append(f"{id}: invalid proof path")
                continue
            p = PurePosixPath(proof)
            if p.is_absolute() or ".." in p.parts or proof not in paths:
                errors.append(f"{id}: missing/untracked/unsafe proof: {proof}")
            if p.suffix in {".py", ".ts", ".tsx"} or (
                "replays" in p.parts and p.suffix == ".json"
            ):
                executable = True
        if not executable:
            errors.append(f"{id}: no executable test/script/replay proof")
    return errors


def validate_spec(root: Path, source: str = "HEAD") -> list[str]:
    try:
        paths = tracked_paths(root, source)
        errors = validate_manifest(root, source)

        def load(path: str) -> Any:
            return json.loads(read_blob(root, PREFIX + path, source))

        errors.extend(
            validate_traceability(
                load("requirements/REQUIREMENTS.json"),
                load("requirements/VERIFICATION_CATALOG.json"),
                paths,
            )
        )
        for n in range(1, 13):
            prefix = PREFIX + f"fixtures/scenarios/S{n:02d}_"
            matches = [p for p in paths if p.startswith(prefix) and p.endswith(".json")]
            if len(matches) != 1:
                errors.append(f"S{n:02d}: exactly one scenario required")
                continue
            obj = json.loads(read_blob(root, matches[0], source))
            if obj.get("id") != PurePosixPath(matches[0]).stem or not obj.get(
                "expected_invariants"
            ):
                errors.append(f"S{n:02d}: scenario identity/invariants mismatch")
        backlog = read_blob(root, PREFIX + "10_ENGINEERING_BACKLOG.md", source).decode(
            "utf-8"
        )
        if re.search(r"\b(?:days?|weeks?)\s+[0-9]+", backlog, re.I):
            errors.append("calendar-tied backlog")
        scope = (
            read_blob(root, PREFIX + "01_SCOPE_AND_NON_GOALS.md", source)
            .decode("utf-8")
            .lower()
        )
        demo = read_blob(root, PREFIX + "08_DEMO_UX.md", source).decode("utf-8").lower()
        if "multi-agent" not in scope or "no public arbitrary prompt field" not in demo:
            errors.append("scope/demo non-goals missing")
        return errors
    except (
        OSError,
        subprocess.CalledProcessError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as error:
        return [f"invalid Git-blob specification: {type(error).__name__}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["HEAD", "index"], default="HEAD")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[5]
    )
    args = parser.parse_args()
    errors = validate_spec(args.root, args.source)
    for error in errors:
        print("FAIL: " + error)
    if not errors:
        print(
            f"PASS: {args.source} Git-blob manifest, 26 requirements, "
            "14 verification methods, 12 scenarios"
        )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
