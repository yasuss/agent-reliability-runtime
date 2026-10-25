"""Verify the release contract using only the Python standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

BASE_SHA = "3c1389bdb0b358c8232ed07caccf14932f7da727"
VERSION = "2.1.0"
CURRENT_RELEASE_TAG = f"v{VERSION}"
V20_RELEASE_SHA = "77574ee445e97fe282a62c2528b2c250e6998ddb"
WEB_VERSION = "1.0.0"
RELEASE_NOTES_PATH = f"release/RELEASE_NOTES_{VERSION}.md"
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
REVIEWED_NPM_DELTA = {
    ("node_modules/vite", "8.3.2"),
    ("node_modules/vite", "8.3.3"),
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


def behavior_provenance_errors() -> list[str]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.verify_behavior_provenance import check

    return check()


def validate_current_release_tag_state(
    *,
    tag_sha: str | None,
    candidate_sha: str,
    tag_is_ancestor: bool | None,
    tag_version: str | None,
    release_notes_present: bool | None,
    require_unreleased: bool,
) -> list[str]:
    """Validate the current-version tag for either release lifecycle phase."""

    del candidate_sha
    if tag_sha is None:
        return []
    if require_unreleased:
        return [f"{CURRENT_RELEASE_TAG} tag exists before release"]

    errors: list[str] = []
    if tag_is_ancestor is not True:
        errors.append(f"{CURRENT_RELEASE_TAG} tag is not an ancestor of candidate HEAD")
    if tag_version != VERSION:
        errors.append(f"{CURRENT_RELEASE_TAG} tagged project version mismatch")
    if release_notes_present is not True:
        errors.append(f"{CURRENT_RELEASE_TAG} release notes missing")
    return errors


def _current_release_tag_state(
    *, require_unreleased: bool
) -> tuple[str | None, str, bool | None, str | None, bool | None, list[str]]:
    """Collect tag state without allowing malformed tag data to escape uncaught."""

    del require_unreleased
    candidate_sha = ""
    collector_errors: list[str] = []
    try:
        candidate_sha = git("rev-parse", "HEAD").decode().strip()
    except (subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        collector_errors.append(f"candidate HEAD could not be resolved: {exc}")

    tag_result = subprocess.run(
        [
            "git",
            "rev-parse",
            "--verify",
            f"refs/tags/{CURRENT_RELEASE_TAG}^{{commit}}",
        ],
        cwd=ROOT,
        capture_output=True,
    )
    if tag_result.returncode != 0:
        return None, candidate_sha, None, None, None, collector_errors
    try:
        tag_sha = tag_result.stdout.decode().strip()
    except UnicodeDecodeError as exc:
        collector_errors.append(
            f"{CURRENT_RELEASE_TAG} tag SHA is not valid UTF-8: {exc}"
        )
        return None, candidate_sha, None, None, None, collector_errors

    tag_is_ancestor = False
    if candidate_sha:
        tag_is_ancestor = (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", tag_sha, candidate_sha],
                cwd=ROOT,
                capture_output=True,
            ).returncode
            == 0
        )

    tag_version: str | None = None
    try:
        tagged_pyproject = git("show", f"{tag_sha}:pyproject.toml")
        tag_version = tomllib.loads(tagged_pyproject.decode("utf-8"))["project"].get(
            "version"
        )
    except (
        subprocess.CalledProcessError,
        UnicodeDecodeError,
        tomllib.TOMLDecodeError,
        KeyError,
        TypeError,
    ) as exc:
        collector_errors.append(
            f"{CURRENT_RELEASE_TAG} tagged pyproject.toml could not be read: {exc}"
        )

    release_notes_present = (
        subprocess.run(
            ["git", "cat-file", "-e", f"{tag_sha}:{RELEASE_NOTES_PATH}"],
            cwd=ROOT,
            capture_output=True,
        ).returncode
        == 0
    )
    return (
        tag_sha,
        candidate_sha,
        tag_is_ancestor,
        tag_version,
        release_notes_present,
        collector_errors,
    )


def current_release_tag_errors(*, require_unreleased: bool) -> list[str]:
    (
        tag_sha,
        candidate_sha,
        tag_is_ancestor,
        tag_version,
        release_notes_present,
        collector_errors,
    ) = _current_release_tag_state(require_unreleased=require_unreleased)
    return collector_errors + validate_current_release_tag_state(
        tag_sha=tag_sha,
        candidate_sha=candidate_sha,
        tag_is_ancestor=tag_is_ancestor,
        tag_version=tag_version,
        release_notes_present=release_notes_present,
        require_unreleased=require_unreleased,
    )


def check(*, require_unreleased: bool = False) -> list[str]:
    errors: list[str] = []
    errors.extend(
        f"behavior provenance: {error}" for error in behavior_provenance_errors()
    )
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
        package.get("version") != WEB_VERSION
        or lock.get("version") != WEB_VERSION
        or lock.get("packages", {}).get("", {}).get("version") != WEB_VERSION
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
    for required in (
        "SECURITY.md",
        "CONTRIBUTING.md",
        "web/vercel.json",
        "release/RELEASE_NOTES_2.0.0.md",
        RELEASE_NOTES_PATH,
    ):
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
    if uv_delta:
        errors.append(f"unreviewed dependency drift: uv={sorted(uv_delta)}")
    if npm_delta != REVIEWED_NPM_DELTA:
        errors.append(
            "unreviewed dependency drift: "
            f"npm={sorted(npm_delta)} expected={sorted(REVIEWED_NPM_DELTA)}"
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
            "release/RELEASE_NOTES_2.0.0.md",
            RELEASE_NOTES_PATH,
        )
    )
    version_pattern = re.escape(VERSION)
    if re.search(
        rf"(?i)(?:v?{version_pattern} (?:tag (?:created|published)|"
        rf"(?:is |already )?(?:tagged|published|released))|"
        rf"(?:tagged|published|released) (?:v?{version_pattern})|"
        rf"published (?:GitHub )?release[^\n]{{0,30}}v?{version_pattern})",
        public,
    ):
        errors.append("premature release-action claim")
    try:
        if git("rev-parse", "refs/tags/v2.0.0").decode().strip() != V20_RELEASE_SHA:
            errors.append("v2.0.0 predecessor tag mismatch")
    except subprocess.CalledProcessError:
        errors.append("v2.0.0 predecessor tag is missing")
    errors.extend(current_release_tag_errors(require_unreleased=require_unreleased))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if (
        not re.search(r"Apache(?: License)? 2\.0", readme)
        or "SECURITY.md" not in readme
    ):
        errors.append("README release links")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-unreleased",
        action="store_true",
        help="require the current release tag to be absent before publication",
    )
    args = parser.parse_args()
    errors = check(require_unreleased=args.require_unreleased)
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
                "v20_release_sha": V20_RELEASE_SHA,
                "release_notes": RELEASE_NOTES_PATH,
                "scenario_set_sha256": SCENARIO_SHA,
                "protected_paths": len(protected_paths()),
                "require_unreleased": args.require_unreleased,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
