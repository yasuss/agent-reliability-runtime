"""Verify the release-candidate contract using only the Python standard library."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = "4cc3f9fdaeb5e3061e2f87a7aab0abaf6c92b265"
VERSION = "1.0.0"
LICENSE_SHA = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
SCENARIO_SHA = "ad14a89fb5816f2eea2ab700394df4b231191cb466e4b326437d035e34f475f9"
ACCEPTED_SOURCE_SHA = "83514ebad336dbd6faf1b790c597ec8037be0874"
DOCS_SOURCE_SHA = "520e7abd7f0ce332e1f6907a0cfc472f9737519e"
VERCEL = {
    "$schema": "https://openapi.vercel.sh/vercel.json",
    "framework": "vite",
    "installCommand": "npm ci",
    "buildCommand": "npm run build",
    "outputDirectory": "dist",
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def base_blob(path: str) -> bytes:
    return git("show", f"{BASE_SHA}:{path}")


def dependency_sets() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    current = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    before = tomllib.loads(base_blob("uv.lock").decode("utf-8"))

    def uv_packages(value: dict[str, Any]) -> set[tuple[str, str]]:
        return {
            (p["name"], p["version"])
            for p in value.get("package", [])
            if p["name"] != "agent-reliability-runtime"
        }

    cweb = json.loads((ROOT / "web/package-lock.json").read_text(encoding="utf-8"))
    bweb = json.loads(base_blob("web/package-lock.json"))

    def npm_packages(value: dict[str, Any]) -> set[tuple[str, str]]:
        result = set()
        for path, entry in value.get("packages", {}).items():
            if path and "version" in entry:
                result.add((path, str(entry["version"])))
        return result

    return uv_packages(current) ^ uv_packages(before), npm_packages(
        cweb
    ) ^ npm_packages(bweb)


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


def protected_paths() -> list[str]:
    names = git("ls-tree", "-r", "--name-only", BASE_SHA).decode().splitlines()
    return [
        n
        for n in names
        if n.startswith("docs/project/spec/v1.0/fixtures/scenarios/")
        or (
            n.startswith("web/public/replays/")
            and Path(n).name in {"replay.json", "receipt.json"}
        )
    ]


def check() -> list[str]:
    errors: list[str] = []
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    if (
        pyproject.get("version") != VERSION
        or "foundation only" in pyproject.get("description", "").lower()
    ):
        errors.append("pyproject version/description")
    package = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "web/package-lock.json").read_text(encoding="utf-8"))
    if (
        package.get("version") != VERSION
        or lock.get("version") != VERSION
        or lock.get("packages", {}).get("", {}).get("version") != VERSION
    ):
        errors.append("web package versions")
    uv = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    roots = [
        p for p in uv.get("package", []) if p.get("name") == "agent-reliability-runtime"
    ]
    if len(roots) != 1 or roots[0].get("version") != VERSION:
        errors.append("uv.lock project version")
    if (
        sha((ROOT / "LICENSE").read_bytes()) != LICENSE_SHA
        or "Apache License\n                           Version 2.0"
        not in (ROOT / "LICENSE").read_text(encoding="utf-8")
    ):
        errors.append("canonical Apache-2.0 LICENSE")
    for required in ("SECURITY.md", "CONTRIBUTING.md", "web/vercel.json"):
        if not (ROOT / required).is_file():
            errors.append(f"missing {required}")
    if json.loads((ROOT / "web/vercel.json").read_text(encoding="utf-8")) != VERCEL:
        errors.append("web/vercel.json contract")
    if scenario_digest() != SCENARIO_SHA:
        errors.append("scenario-set digest")
    for protected_path in protected_paths():
        if sha((ROOT / protected_path).read_bytes()) != sha(base_blob(protected_path)):
            errors.append(f"protected byte drift: {protected_path}")
    if ACCEPTED_SOURCE_SHA not in (ROOT / "web/public/replays/index.json").read_text(
        encoding="utf-8"
    ):
        errors.append("accepted replay source provenance")
    if DOCS_SOURCE_SHA not in (ROOT / "web/src/App.tsx").read_text(encoding="utf-8"):
        errors.append("documentation snapshot link")
    uv_delta, npm_delta = dependency_sets()
    if uv_delta or npm_delta:
        errors.append(
            "dependency upgrade detected: "
            f"uv={sorted(uv_delta)} npm={sorted(npm_delta)}"
        )
    for doc_path in list((ROOT / "docs/project").rglob("*.md")) + list(
        (ROOT / "docs/project").rglob("*.json")
    ):
        if "docs/internal" in doc_path.as_posix():
            continue
        text = doc_path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\b(?:B\d{2}|R\d+|G\d+)\b", text):
            errors.append(f"public delivery identifier: {doc_path.relative_to(ROOT)}")
    public = "\n".join(
        (ROOT / p).read_text(encoding="utf-8", errors="ignore")
        for p in (
            "README.md",
            "docs/project/RELEASE_AND_DEPLOYMENT.md",
            "release/RELEASE_NOTES_1.0.0.md",
        )
    )
    if re.search(
        r"(?i)(?:repository is public|published release|"
        r"production deployment is live|v1\.0\.0 tag created)",
        public,
    ):
        errors.append("premature release-action claim")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if (
        not re.search(r"Apache(?: License)? 2\.0", readme)
        or "SECURITY.md" not in readme
    ):
        errors.append("README release links")
    return errors


def main() -> int:
    errors = check()
    if errors:
        print("Release verifier: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        json.dumps(
            {
                "state": "PASS",
                "version": VERSION,
                "base_sha": BASE_SHA,
                "scenario_set_sha256": SCENARIO_SHA,
                "protected_paths": len(protected_paths()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
