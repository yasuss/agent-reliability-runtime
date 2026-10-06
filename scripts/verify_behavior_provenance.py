"""Prove that the candidate inherits the accepted live behavior surface."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_SOURCE_SHA = "83514ebad336dbd6faf1b790c597ec8037be0874"
SCENARIO_SHA = "ad14a89fb5816f2eea2ab700394df4b231191cb466e4b326437d035e34f475f9"
PROTECTED_PREFIXES = (
    "src/agent_reliability_runtime/",
    "mcp_server/",
    "migrations/",
    "data/knowledge/",
    "docs/project/spec/v1.0/fixtures/scenarios/",
    "docs/project/spec/v1.0/fixtures/knowledge/",
)
PROTECTED_SINGLETONS = (
    "compose.yaml",
    "alembic.ini",
    "scripts/setup_checkpoints.py",
    "scripts/probe_providers.py",
    "scripts/reset_demo.py",
)


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def tree_paths(revision: str) -> set[str]:
    return set(git("ls-tree", "-r", "--name-only", revision).decode().splitlines())


def protected(path: str) -> bool:
    return path in PROTECTED_SINGLETONS or path.startswith(PROTECTED_PREFIXES)


def blob(revision: str, path: str) -> bytes:
    return git("show", f"{revision}:{path}")


def scenario_digest() -> str:
    directory = ROOT / "docs/project/spec/v1.0/fixtures/scenarios"
    files = [
        {"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p.read_bytes())}
        for p in sorted(directory.glob("*.json"))
    ]
    canonical = json.dumps(
        files, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return sha(canonical)


def dependency_sets(revision: str) -> tuple[set[str], set[tuple[str, str]]]:
    pyproject = tomllib.loads(blob(revision, "pyproject.toml").decode())
    runtime = set(pyproject.get("project", {}).get("dependencies", []))
    lock = tomllib.loads(blob(revision, "uv.lock").decode())
    packages = {
        (str(item["name"]), str(item["version"]))
        for item in lock.get("package", [])
        if item.get("name") != "agent-reliability-runtime"
    }
    return runtime, packages


def check() -> list[str]:
    errors: list[str] = []
    candidate = git("rev-parse", "HEAD").decode().strip()
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ACCEPTED_SOURCE_SHA, candidate],
        cwd=ROOT,
        capture_output=True,
    )
    if ancestry.returncode != 0:
        errors.append("accepted source is not an ancestor")

    accepted_paths = {
        path for path in tree_paths(ACCEPTED_SOURCE_SHA) if protected(path)
    }
    candidate_paths = {path for path in tree_paths(candidate) if protected(path)}
    if accepted_paths != candidate_paths:
        errors.extend(
            f"protected path set drift: {path}"
            for path in sorted(accepted_paths ^ candidate_paths)
        )
    for path in sorted(accepted_paths & candidate_paths):
        if sha(blob(ACCEPTED_SOURCE_SHA, path)) != sha(blob(candidate, path)):
            errors.append(f"protected byte drift: {path}")

    try:
        accepted_runtime, accepted_lock = dependency_sets(ACCEPTED_SOURCE_SHA)
        candidate_runtime, candidate_lock = dependency_sets(candidate)
    except (KeyError, subprocess.CalledProcessError, tomllib.TOMLDecodeError) as error:
        errors.append(f"dependency provenance unavailable: {type(error).__name__}")
    else:
        if accepted_runtime != candidate_runtime:
            errors.append(
                "Python runtime dependency set drift: "
                f"{sorted(accepted_runtime ^ candidate_runtime)}"
            )
        if accepted_lock != candidate_lock:
            errors.append(
                "resolved uv.lock external package drift: "
                f"{sorted(accepted_lock ^ candidate_lock)}"
            )

    if scenario_digest() != SCENARIO_SHA:
        errors.append("scenario-set digest drift")
    return errors


def main() -> int:
    errors = check()
    payload: dict[str, Any] = {
        "state": "FAIL" if errors else "PASS",
        "accepted_source_sha": ACCEPTED_SOURCE_SHA,
        "candidate_sha": git("rev-parse", "HEAD").decode().strip(),
        "protected_changed_paths": [
            error.removeprefix("protected path set drift: ")
            for error in errors
            if error.startswith("protected path set drift:")
        ]
        + [
            error.removeprefix("protected byte drift: ")
            for error in errors
            if error.startswith("protected byte drift:")
        ],
        "errors": errors,
        "scenario_set_sha256": SCENARIO_SHA,
    }
    print(json.dumps(payload, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
