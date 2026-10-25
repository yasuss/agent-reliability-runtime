"""Preserve accepted ancestry and immutable inputs around the v2 refactor.

Source bytes deliberately move. The complete behavior suite, rather than a
claim of source byte equivalence, establishes behavior preservation.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_SOURCE_SHA = "83514ebad336dbd6faf1b790c597ec8037be0874"
REFACTOR_BASE_SHA = "3c1389bdb0b358c8232ed07caccf14932f7da727"
SCENARIO_SHA = "ad14a89fb5816f2eea2ab700394df4b231191cb466e4b326437d035e34f475f9"
PROTECTED_PREFIXES = (
    "docs/project/spec/v1.0/",
    "migrations/versions/",
    "web/",
    "data/knowledge/",
    "data/seed/",
)
PROTECTED_SINGLETONS = (
    "compose.yaml",
    "alembic.ini",
)

AUTHORIZED_PREFIXES = (
    "src/agent_reliability_runtime/",
    "mcp_server/",
    "scripts/",
    "tests/",
    "docs/",
    ".agents/skills/agent-reliability-runtime/",
)
AUTHORIZED_SINGLETONS = {
    "AGENTS.md",
    "README.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "uv.lock",
    "migrations/env.py",
    "release/RELEASE_NOTES_2.0.0.md",
    # User-authorized bounded correction: historical v1 verification plumbing.
    ".github/workflows/ci.yml",
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def tree_paths(revision: str) -> set[str]:
    return set(git("ls-tree", "-r", "--name-only", revision).decode().splitlines())


def protected(path: str) -> bool:
    return path in PROTECTED_SINGLETONS or path.startswith(PROTECTED_PREFIXES)


def surface_errors(paths: set[str]) -> list[str]:
    errors = []
    for path in sorted(paths):
        if protected(path):
            errors.append(f"protected byte/path drift: {path}")
        elif path not in AUTHORIZED_SINGLETONS and not path.startswith(
            AUTHORIZED_PREFIXES
        ):
            errors.append(f"unauthorized refactor path: {path}")
    return errors


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


def dependency_sets(revision: str | None) -> tuple[set[str], set[tuple[str, str]]]:
    def contents(path: str) -> bytes:
        return blob(revision, path) if revision else (ROOT / path).read_bytes()

    pyproject = tomllib.loads(contents("pyproject.toml").decode())
    runtime = set(pyproject.get("project", {}).get("dependencies", []))
    runtime.add(json.dumps(pyproject.get("dependency-groups", {}), sort_keys=True))
    lock = tomllib.loads(contents("uv.lock").decode())
    packages = {
        (str(item["name"]), json.dumps(item, sort_keys=True))
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

    if (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", REFACTOR_BASE_SHA, candidate],
            cwd=ROOT,
            capture_output=True,
        ).returncode
        != 0
    ):
        errors.append("refactor baseline is not an ancestor")
    # Include staged, unstaged, deleted and new files before the single commit;
    # on clean CI this same comparison binds the candidate commit itself.
    changed = set(
        git("diff", "--name-only", "--no-renames", REFACTOR_BASE_SHA)
        .decode()
        .splitlines()
    )
    changed.update(
        git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    )
    errors.extend(surface_errors(changed))

    try:
        accepted_runtime, accepted_lock = dependency_sets(REFACTOR_BASE_SHA)
        candidate_runtime, candidate_lock = dependency_sets(None)
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
        "refactor_base_sha": REFACTOR_BASE_SHA,
        "candidate_sha": git("rev-parse", "HEAD").decode().strip(),
        "protected_changed_paths": [
            error.removeprefix("protected byte/path drift: ")
            for error in errors
            if error.startswith("protected byte/path drift:")
        ],
        "errors": errors,
        "scenario_set_sha256": SCENARIO_SHA,
    }
    print(json.dumps(payload, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
