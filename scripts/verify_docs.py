"""Verify the repository's canonical documentation and proof index.

This is deliberately structural: it validates references and claim boundaries
without trying to infer runtime correctness from prose.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CANONICAL_DOCS = (
    "README.md",
    "docs/project/ARCHITECTURE.md",
    "docs/project/OPERATIONS.md",
    "docs/project/VERIFICATION.md",
    "docs/project/SUPPORT_MATRIX.md",
    "docs/project/LIMITATIONS.md",
    "docs/project/EVIDENCE_AND_PROOF.md",
    "docs/project/PROOF_INDEX.json",
)
REQUIRED_CLAIMS = {
    "provider-boundary",
    "hybrid-retrieval-citations",
    "mcp-five-tools",
    "deterministic-policy",
    "exact-approval",
    "idempotent-side-effects",
    "durable-restart",
    "governed-memory",
    "otel-audit",
    "eval-harness",
    "adversarial-scenarios",
    "static-evidence-demo",
}
ALLOWED_SUPPORT_STATUSES = {
    "TESTED",
    "EXPECTED",
    "CONTRACT_ONLY",
    "NOT_CLAIMED",
}
REQUIRED_SUPPORT_ROWS = {
    "Windows 10 Pro local + Ollama qwen3:4b acceptance": "TESTED",
    "Windows 11 local end-to-end": "EXPECTED",
    "Ubuntu GitHub-hosted static/unit": "TESTED",
    "Ubuntu GitHub-hosted PostgreSQL integration": "TESTED",
    "macOS GitHub-hosted static/unit": "TESTED",
    "macOS live local Ollama/full DB agent": "EXPECTED",
    "vLLM OpenAI-compatible provider": "CONTRACT_ONLY",
    "generic cloud OpenAI-compatible live acceptance": "NOT_CLAIMED",
    "Static Evidence Demo Chromium on Ubuntu CI": "TESTED",
    "live public chat/inference": "NOT_CLAIMED",
}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FORBIDDEN_POSITIONING_RE = re.compile(
    r"(?i)(?:recruiter|hiring\s+manager|portfolio|staff[- ]level|"
    r"seniority\s+signal|showcase\s+expertise|career\s+positioning|"
    r"principal[- ]level|searching\s+for\s+a\s+job)"
)
STALE_RE = re.compile(
    r"(?i)(?:remain(?:s)?\s+later\s+tasks|future\s+work|R4\s+campaign|"
    r"pending\s+review\s+blocks\s+the\s+next\s+trial|"
    r"G3\+.*not\s+claimed)"
)
LEGACY_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:B(?:00|10|20|30|40|50|60|70|80|90|100|110|120|130)"
    r"|R(?:10|[1-9])|G(?:1[0-4]|[0-9]))(?![A-Za-z0-9])"
)
PUBLIC_TEXT_EXTENSIONS = {".md", ".json", ".py", ".ts", ".tsx"}
COMPATIBILITY_STUBS = {
    Path("docs/project/spec/v1.0/10_ENGINEERING_BACKLOG.md"),
    Path("docs/project/spec/v1.0/11_ACCEPTANCE_GATES.md"),
    Path("docs/project/spec/v1.0/14_ORCHESTRATOR_HANDOFF.md"),
}
SEMANTIC_COMPONENT_DOCS = (
    "README",
    "RETRIEVAL_AND_CITATIONS",
    "OPSDESK_MCP",
    "TRUSTED_EXECUTION",
    "DURABLE_RUNTIME",
    "GOVERNED_MEMORY",
    "OBSERVABILITY_AND_AUDIT",
    "EVALUATION_HARNESS",
    "RELIABILITY_ACCEPTANCE",
    "STATIC_EVIDENCE_DEMO",
)
MECHANICAL_PATH_RE = re.compile(
    r"_(?:POLICY_EFFECTS|DURABLE_RUNTIME|GOVERNED_MEMORY|OBSERVABILITY_AUDIT|"
    r"EVAL_HARNESS|MANDATORY_SCENARIOS|STATIC_EVIDENCE)\.md"
)
STALE_CURRENT_RE = re.compile(
    r"(?i)(?:Multiple model tool calls fail closed|"
    r"no governed memory (?:or observability )?completion is claimed here|"
    r"later graph\s+connection|empty\s+`load_memory`\s+placeholder|"
    r"POST run/approval control endpoints remain later scope)"
)


def _canonical_paths(root: Path) -> list[Path]:
    return [root / path for path in CANONICAL_DOCS]


def _public_surface_paths(root: Path) -> list[Path]:
    paths = [root / "README.md"]
    project = root / "docs" / "project"
    paths.extend(sorted(path for path in project.rglob("*") if path.is_file()))
    return [
        path
        for path in paths
        if path.exists()
        and path.suffix.lower() in PUBLIC_TEXT_EXTENSIONS
        and "docs/internal" not in path.as_posix()
    ]


def _legacy_surface_errors(root: Path) -> list[str]:
    errors: list[str] = []
    history_root = (root / "docs/internal/acceptance-history").resolve()
    public_paths = _public_surface_paths(root)
    for path in public_paths:
        relative = path.relative_to(root)
        if re.match(
            r"^B(?:00|10|20|30|40|50|60|70|80|90|100|110|120|130)(?:_|\.)", path.name
        ):
            errors.append(f"legacy public filename: {relative}")
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            if LEGACY_TOKEN_RE.search(line):
                errors.append(f"legacy public identifier: {relative}:{line_number}")
        for raw_target in LINK_RE.findall(text):
            target = raw_target.split("#", 1)[0].split("?", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(history_root)
            except ValueError:
                continue
            if relative not in COMPATIBILITY_STUBS:
                errors.append(
                    f"public link into internal history: {relative}: {raw_target}"
                )
    for path in (root / "web/src").rglob("*") if (root / "web/src").exists() else ():
        if not path.is_file() or path.suffix.lower() not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            if LEGACY_TOKEN_RE.search(line):
                errors.append(
                    f"legacy Static Evidence UI identifier: "
                    f"{path.relative_to(root)}:{line_number}"
                )
    return errors


def _project_facing_markdown(root: Path) -> list[Path]:
    paths = [root / "README.md"]
    project = root / "docs" / "project"
    paths.extend(sorted(project.rglob("*.md")))
    return [path for path in paths if path.exists()]


def _relative_link_failures(root: Path, paths: list[Path]) -> list[str]:
    failures: list[str] = []
    root_resolved = root.resolve()
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for raw_target in LINK_RE.findall(text):
            target = raw_target.split("#", 1)[0].split("?", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                failures.append(
                    f"{path.relative_to(root)}: link escapes root: {raw_target}"
                )
                continue
            if not resolved.exists():
                failures.append(f"{path.relative_to(root)}: missing link: {raw_target}")
    return failures


def _proof_index_errors(root: Path, index_path: Path) -> list[str]:
    errors: list[str] = []
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"PROOF_INDEX unreadable: {error}"]
    if index.get("version") != "PROOF-INDEX-v1":
        errors.append("PROOF_INDEX version must be PROOF-INDEX-v1")
    claims = index.get("claims")
    if not isinstance(claims, list):
        return errors + ["PROOF_INDEX claims must be a list"]
    seen: set[str] = set()
    for position, entry in enumerate(claims):
        if not isinstance(entry, dict):
            errors.append(f"PROOF_INDEX entry {position} must be an object")
            continue
        claim_id = entry.get("id")
        if not isinstance(claim_id, str) or not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", claim_id
        ):
            errors.append(f"PROOF_INDEX entry {position} has invalid id")
        elif claim_id in seen:
            errors.append(f"duplicate proof claim id: {claim_id}")
        else:
            seen.add(claim_id)
        if not isinstance(entry.get("claim"), str) or not entry["claim"].strip():
            errors.append(f"PROOF_INDEX entry {position} has no claim")
        proof_paths = entry.get("proof_paths")
        if not isinstance(proof_paths, list) or not proof_paths:
            errors.append(f"PROOF_INDEX entry {claim_id!r} has no proof paths")
            continue
        proof_kind = entry.get("proof_kind")
        if proof_kind not in {"test", "script", "replay", "mixed"}:
            errors.append(f"PROOF_INDEX entry {claim_id!r} has invalid proof_kind")
        executable = False
        for proof_path in proof_paths:
            if (
                not isinstance(proof_path, str)
                or not proof_path
                or Path(proof_path).is_absolute()
            ):
                errors.append(f"invalid proof path in {claim_id!r}: {proof_path!r}")
                continue
            resolved = (root / proof_path).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                errors.append(f"proof path escapes root in {claim_id!r}: {proof_path}")
                continue
            if not resolved.is_file():
                errors.append(f"missing proof path in {claim_id!r}: {proof_path}")
            if (
                resolved.suffix.lower() in {".py", ".json", ".ts", ".tsx"}
                or "replays" in resolved.parts
            ):
                executable = True
        if not executable:
            errors.append(f"claim {claim_id!r} lacks executable/test/replay proof")
    missing = sorted(REQUIRED_CLAIMS - seen)
    errors.extend(f"missing required proof claim: {claim_id}" for claim_id in missing)
    return errors


def _support_matrix_errors(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if len(columns) < 2 or columns[0].lower() == "surface":
            continue
        if all(set(column) <= {"-", ":", " "} for column in columns):
            continue
        rows[columns[0]] = columns[1]
        if columns[1] not in ALLOWED_SUPPORT_STATUSES:
            errors.append(f"invalid support status for {columns[0]!r}: {columns[1]!r}")
    for surface, status in REQUIRED_SUPPORT_ROWS.items():
        if rows.get(surface) != status:
            errors.append(f"support row mismatch: {surface!r} must be {status}")
    return errors


def verify_docs(root: Path) -> list[str]:
    """Return structural documentation errors for *root*."""

    errors: list[str] = []
    paths = _canonical_paths(root)
    errors.extend(
        f"missing canonical document: {path.relative_to(root)}"
        for path in paths
        if not path.is_file()
    )
    if errors:
        return errors

    errors.extend(
        f"missing semantic component document: docs/project/{name}.md"
        for name in SEMANTIC_COMPONENT_DOCS
        if not (root / f"docs/project/{name}.md").is_file()
    )
    markdown_paths = _project_facing_markdown(root)
    errors.extend(_relative_link_failures(root, markdown_paths))
    errors.extend(_proof_index_errors(root, root / "docs/project/PROOF_INDEX.json"))
    errors.extend(_support_matrix_errors(root / "docs/project/SUPPORT_MATRIX.md"))
    errors.extend(_legacy_surface_errors(root))

    project_docs = _project_facing_markdown(root)
    for path in project_docs:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            location = f"{path.relative_to(root)}:{line_number}"
            if FORBIDDEN_POSITIONING_RE.search(line):
                errors.append(f"forbidden project-facing wording: {location}")
            if STALE_RE.search(line) or STALE_CURRENT_RE.search(line):
                errors.append(f"stale documentation wording: {location}")
            if MECHANICAL_PATH_RE.search(line):
                errors.append(f"mechanical replacement path: {location}")
        if STALE_CURRENT_RE.search(text):
            errors.append(
                f"stale current-component statement: {path.relative_to(root)}"
            )
        if re.search(
            r"https?://github\.com/yasuss/agent-reliability-runtime/blob/main(?:[/)#\s]|$)",
            text,
        ):
            errors.append(f"mutable blob/main link in {path.relative_to(root)}")

    readme = (root / "README.md").read_text(encoding="utf-8")
    quickstart = (
        "python scripts/bootstrap.py",
        "uv run python scripts/reset_demo.py --confirm-development-reset",
        "uv run python scripts/verify.py --scope all",
    )
    positions = [readme.find(command) for command in quickstart]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        errors.append("README quickstart commands are missing or out of order")
    for claim_id in sorted(REQUIRED_CLAIMS):
        if claim_id not in readme:
            errors.append(f"README has no proof-index mapping for {claim_id}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    errors = verify_docs(args.root.resolve())
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("Documentation verifier: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
