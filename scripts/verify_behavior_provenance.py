"""Preserve accepted ancestry and immutable inputs around the v2 refactor.

Source bytes deliberately move. The complete behavior suite, rather than a
claim of source byte equivalence, establishes behavior preservation.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from copy import deepcopy
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
REVIEWED_WEB_DEPENDENCY_FILES = frozenset(
    {
        "web/package.json",
        "web/package-lock.json",
    }
)
REVIEWED_VITE_FROM = "8.3.2"
REVIEWED_VITE_TO = "8.3.3"
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
    *REVIEWED_WEB_DEPENDENCY_FILES,
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def tree_paths(revision: str) -> set[str]:
    return set(git("ls-tree", "-r", "--name-only", revision).decode().splitlines())


def protected(path: str) -> bool:
    return path in PROTECTED_SINGLETONS or (
        path not in REVIEWED_WEB_DEPENDENCY_FILES
        and path.startswith(PROTECTED_PREFIXES)
    )


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


def validate_reviewed_web_dependency_transition(
    before_package: dict[str, Any],
    before_lock: dict[str, Any],
    current_package: dict[str, Any],
    current_lock: dict[str, Any],
) -> list[str]:
    """Accept only the reviewed Vite patch and reject every other web drift."""

    errors: list[str] = []
    expected_package = deepcopy(before_package)
    before_dev = before_package.get("devDependencies", {})
    current_dev = current_package.get("devDependencies", {})
    if before_dev.get("vite") != REVIEWED_VITE_FROM:
        errors.append("baseline web/package.json Vite version is not 8.3.2")
    expected_package.setdefault("devDependencies", {})["vite"] = REVIEWED_VITE_TO
    if current_package != expected_package:
        errors.append("web/package.json differs beyond the reviewed Vite transition")
    if current_dev.get("vite") != REVIEWED_VITE_TO:
        errors.append("web/package.json Vite version is not 8.3.3")

    before_packages = before_lock.get("packages")
    current_packages = current_lock.get("packages")
    if not isinstance(before_packages, dict) or not isinstance(current_packages, dict):
        return errors + ["package-lock.json packages object is missing"]
    if set(before_lock) - {"packages"} != set(current_lock) - {"packages"}:
        errors.append("package-lock.json top-level keys drifted")
    for key in set(before_lock) | set(current_lock):
        if key != "packages" and before_lock.get(key) != current_lock.get(key):
            errors.append(f"package-lock.json top-level field drift: {key}")
    if set(before_packages) != set(current_packages):
        errors.append("package-lock.json package-key set drifted")

    before_root = before_packages.get("")
    current_root = current_packages.get("")
    if not isinstance(before_root, dict) or not isinstance(current_root, dict):
        errors.append("package-lock.json root package entry is missing")
    else:
        expected_root = deepcopy(before_root)
        expected_root.setdefault("devDependencies", {})["vite"] = REVIEWED_VITE_TO
        if current_root != expected_root:
            errors.append(
                "package-lock.json root entry differs beyond the reviewed "
                "Vite transition"
            )

    vite_path = "node_modules/vite"
    before_vite = before_packages.get(vite_path)
    current_vite = current_packages.get(vite_path)
    if not isinstance(before_vite, dict) or not isinstance(current_vite, dict):
        return errors + ["package-lock.json Vite entry is missing"]
    for key in set(before_packages) | set(current_packages):
        if key not in {"", vite_path} and before_packages.get(
            key
        ) != current_packages.get(key):
            errors.append(f"package-lock.json unrelated package drift: {key}")
    if before_vite.get("version") != REVIEWED_VITE_FROM:
        errors.append("baseline lock Vite version is not 8.3.2")
    if current_vite.get("version") != REVIEWED_VITE_TO:
        errors.append("current lock Vite version is not 8.3.3")
    if (
        current_vite.get("resolved")
        != "https://registry.npmjs.org/vite/-/vite-8.3.3.tgz"
    ):
        errors.append("current lock Vite tarball is not the reviewed 8.3.3 artifact")
    if not current_vite.get("integrity"):
        errors.append("current lock Vite integrity is missing")
    ignored = {"version", "resolved", "integrity"}
    before_semantic = {k: v for k, v in before_vite.items() if k not in ignored}
    current_semantic = {k: v for k, v in current_vite.items() if k not in ignored}
    if before_semantic != current_semantic:
        errors.append("Vite lock metadata drifted beyond version/resolved/integrity")
    return errors


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
        before_package = json.loads(blob(REFACTOR_BASE_SHA, "web/package.json"))
        before_lock = json.loads(blob(REFACTOR_BASE_SHA, "web/package-lock.json"))
        current_package = json.loads(
            (ROOT / "web/package.json").read_text(encoding="utf-8")
        )
        current_lock = json.loads(
            (ROOT / "web/package-lock.json").read_text(encoding="utf-8")
        )
        errors.extend(
            f"reviewed web dependency transition: {error}"
            for error in validate_reviewed_web_dependency_transition(
                before_package, before_lock, current_package, current_lock
            )
        )
    except (json.JSONDecodeError, KeyError, subprocess.CalledProcessError) as error:
        errors.append(
            f"reviewed web dependency transition unavailable: {type(error).__name__}"
        )

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
