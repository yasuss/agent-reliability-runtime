"""Calibration tests for the stdlib-only documentation verifier."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.verify_docs import REQUIRED_CLAIMS, verify_docs


def _fixture(root: Path) -> None:
    (root / "docs/project").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "tests/proof.py").write_text("# proof\n", encoding="utf-8")
    required_commands = """
python scripts/bootstrap.py
uv run python scripts/reset_demo.py --confirm-development-reset
uv run python scripts/verify.py --scope all
"""
    claim_table = "\n".join(f"| {claim_id} |" for claim_id in sorted(REQUIRED_CLAIMS))
    (root / "README.md").write_text(
        "# Project\n\n"
        "## What it is\n## Reliability properties\n## Architecture at a glance\n"
        "## Quickstart\n"
        + required_commands
        + "\n## Optional live local model path\n## Verification\n"
        "## Static Evidence Demo\n## Support and limitations\n## Documentation map\n"
        "[Architecture](docs/project/ARCHITECTURE.md#flow)\n"
        "[Proof](docs/project/EVIDENCE_AND_PROOF.md)\n" + claim_table,
        encoding="utf-8",
    )
    for name in (
        "ARCHITECTURE",
        "OPERATIONS",
        "VERIFICATION",
        "LIMITATIONS",
        "EVIDENCE_AND_PROOF",
    ):
        (root / f"docs/project/{name}.md").write_text(
            f"# {name}\n\n[Home](../../README.md)\n", encoding="utf-8"
        )
    rows = "\n".join(
        f"| {surface} | {status} |"
        for surface, status in {
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
        }.items()
    )
    (root / "docs/project/SUPPORT_MATRIX.md").write_text(
        "# Support Matrix\n\n| Surface | Status |\n| --- | --- |\n" + rows + "\n",
        encoding="utf-8",
    )
    (root / "docs/project/PROOF_INDEX.json").write_text(
        json.dumps(
            {
                "version": "PROOF-INDEX-v1",
                "claims": [
                    {
                        "id": claim_id,
                        "claim": claim_id,
                        "proof_paths": ["tests/proof.py"],
                        "proof_kind": "test",
                    }
                    for claim_id in sorted(REQUIRED_CLAIMS)
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def docs_fixture(tmp_path: Path) -> Path:
    _fixture(tmp_path)
    return tmp_path


def assert_passes(root: Path) -> None:
    assert verify_docs(root) == []


def test_documentation_baseline_and_anchor_link_pass(docs_fixture: Path) -> None:
    assert_passes(docs_fixture)


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        (
            "missing-link",
            lambda root: (root / "README.md").write_text(
                (root / "README.md").read_text(encoding="utf-8")
                + "\n[Missing](docs/project/nope.md)\n",
                encoding="utf-8",
            ),
        ),
        (
            "missing-proof",
            lambda root: (root / "docs/project/PROOF_INDEX.json").write_text(
                (root / "docs/project/PROOF_INDEX.json")
                .read_text(encoding="utf-8")
                .replace("tests/proof.py", "tests/missing.py", 1),
                encoding="utf-8",
            ),
        ),
        (
            "duplicate-claim",
            lambda root: (root / "docs/project/PROOF_INDEX.json").write_text(
                json.dumps(
                    json.loads(
                        (root / "docs/project/PROOF_INDEX.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    | {
                        "claims": json.loads(
                            (root / "docs/project/PROOF_INDEX.json").read_text(
                                encoding="utf-8"
                            )
                        )["claims"]
                        + [
                            json.loads(
                                (root / "docs/project/PROOF_INDEX.json").read_text(
                                    encoding="utf-8"
                                )
                            )["claims"][0]
                        ]
                    }
                ),
                encoding="utf-8",
            ),
        ),
        (
            "missing-required-claim",
            lambda root: (root / "docs/project/PROOF_INDEX.json").write_text(
                json.dumps(
                    {
                        "version": "PROOF-INDEX-v1",
                        "claims": [],
                    }
                ),
                encoding="utf-8",
            ),
        ),
        (
            "invalid-support-status",
            lambda root: (root / "docs/project/SUPPORT_MATRIX.md").write_text(
                (root / "docs/project/SUPPORT_MATRIX.md")
                .read_text(encoding="utf-8")
                .replace("| TESTED |", "| BROKEN |", 1),
                encoding="utf-8",
            ),
        ),
        (
            "forbidden-positioning",
            lambda root: (root / "docs/project/ARCHITECTURE.md").write_text(
                (root / "docs/project/ARCHITECTURE.md").read_text(encoding="utf-8")
                + "\nportfolio\n",
                encoding="utf-8",
            ),
        ),
        (
            "stale-wording",
            lambda root: (root / "docs/project/ARCHITECTURE.md").write_text(
                (root / "docs/project/ARCHITECTURE.md").read_text(encoding="utf-8")
                + "\nThis remains later tasks.\n",
                encoding="utf-8",
            ),
        ),
    ],
)
def test_broken_controls_fail(
    name: str, mutate: Callable[[Path], object], docs_fixture: Path
) -> None:
    del name
    mutate(docs_fixture)
    assert verify_docs(docs_fixture)


def test_public_legacy_identifiers_fail(docs_fixture: Path) -> None:
    path = docs_fixture / "docs/project/ARCHITECTURE.md"
    path.write_text(
        path.read_text(encoding="utf-8") + "\nB100 R10 G8\n", encoding="utf-8"
    )
    assert verify_docs(docs_fixture)


def test_public_stage_filename_fails(docs_fixture: Path) -> None:
    (docs_fixture / "docs/project/B100_OLD.md").write_text("# old\n", encoding="utf-8")
    assert verify_docs(docs_fixture)


def test_internal_history_and_scenario_ids_are_allowed(docs_fixture: Path) -> None:
    history = docs_fixture / "docs/internal/acceptance-history"
    history.mkdir(parents=True)
    (history / "record.md").write_text("B100 R10 G8\n", encoding="utf-8")
    architecture = docs_fixture / "docs/project/ARCHITECTURE.md"
    architecture.write_text(
        architecture.read_text(encoding="utf-8")
        + "\nS02 durable verification obligation\n",
        encoding="utf-8",
    )
    assert_passes(docs_fixture)


def test_semantic_alternate_public_surface_passes(docs_fixture: Path) -> None:
    architecture = docs_fixture / "docs/project/ARCHITECTURE.md"
    architecture.write_text(
        architecture.read_text(encoding="utf-8")
        + "\nTrusted execution and durable recovery remain inspectable.\n",
        encoding="utf-8",
    )
    assert_passes(docs_fixture)
