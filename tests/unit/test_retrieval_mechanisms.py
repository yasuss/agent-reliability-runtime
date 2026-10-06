"""Good/bad/alternate controls for B30's deterministic pure mechanisms."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_reliability_runtime.contracts.domain import chunk_id, document_id
from agent_reliability_runtime.providers.contracts import EmbeddingResult
from agent_reliability_runtime.retrieval.contracts import Evidence, validate_citations
from agent_reliability_runtime.retrieval.evaluation import (
    calibrate_checkers,
    require_gates,
    score_query,
)
from agent_reliability_runtime.retrieval.service import fuse, validated_vectors
from agent_reliability_runtime.retrieval.text import plan_source, read_source


def evidence(number: int) -> Evidence:
    plan = plan_source(
        f"calibration/source-{number}.md", f"# Source {number}\nbody".encode()
    )
    chunk = plan.chunks[0]
    return Evidence(
        evidence_id=chunk.chunk_id,
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        document_digest=chunk.document_digest,
        title=plan.document.title,
        source_path=plan.document.source_path,
        content=chunk.content,
        lexical_rank=None,
        vector_rank=1,
        rrf_score=1 / 61,
    )


def test_normalization_and_identity_controls(tmp_path: Path) -> None:
    lf = b"# First\nsection\n## Second\nother\n"
    expected = plan_source("data/knowledge/a.md", lf)
    for variant in (lf.replace(b"\n", b"\r\n"), lf.replace(b"\n", b"\r")):
        assert plan_source("data/knowledge/a.md", variant) == expected
    assert expected.document.document_id == document_id("data/knowledge/a.md")
    assert expected.document.content_digest == hashlib.sha256(lf).hexdigest()
    assert expected.chunks[0].chunk_id == chunk_id(
        expected.document.document_id, expected.document.content_digest, 0
    )
    assert (
        plan_source("other/a.md", lf).document.document_id
        != expected.document.document_id
    )
    changed = plan_source("data/knowledge/a.md", lf + b"changed")
    assert changed.chunks[0].chunk_id != expected.chunks[0].chunk_id
    with pytest.raises(UnicodeDecodeError):
        plan_source("data/a.md", b"\xff")
    for path in ("../escape.md", "data\\a.md", "/a.md", "data/a.pdf"):
        with pytest.raises(ValueError):
            plan_source(path, lf)
    with pytest.raises(ValueError):
        plan_source("empty.txt", b" \r\n")
    with pytest.raises(ValueError):
        read_source(tmp_path, "../escape.md")
    plain = plan_source("plain_name.txt", b"# Not Markdown\ntext")
    assert plain.document.title == "plain name"


def test_heading_boundaries_and_exact_split_overlap() -> None:
    plan = plan_source("a.md", b"# One\none\n## Two\ntwo\n### Three\nthree")
    assert len(plan.chunks) == 3
    assert [c.content for c in plan.chunks] == [
        "# One\none",
        "## Two\ntwo",
        "### Three\nthree",
    ]
    assert plan.document.title == "One"
    for length in (1199, 1200, 1201, 3600):
        content = b"x" * length
        result = plan_source("a.txt", content)
        assert len(result.chunks) == (
            1 if length <= 1200 else (2 if length == 1201 else 4)
        )
        assert all(len(c.content) <= 1200 for c in result.chunks)
        for before, after in zip(result.chunks, result.chunks[1:]):
            assert before.content[-150:] == after.content[:150]
    long = plan_source("a.md", ("# One\n" + "ab " * 1300 + "\n## Two\nend").encode())
    assert all(c.content.startswith("# One\n") for c in long.chunks[:-1])
    assert all("## Two" not in c.content for c in long.chunks[:-1])
    assert long.chunks[-1].content == "## Two\nend"
    assert long == plan_source(
        "a.md", ("# One\n" + "ab " * 1300 + "\n## Two\nend").encode()
    )
    alternate = plan_source("a.md", b"preface\n## Only H2\ntext")
    assert alternate.document.title == "a" and len(alternate.chunks) == 2
    with pytest.raises(ValueError):
        plan_source("a.md", ("# " + "h" * 1100 + "\n" + "body" * 400).encode())


def test_vectors_good_bad_alternate() -> None:
    def result(values: tuple[float, ...]) -> EmbeddingResult:
        return EmbeddingResult(provider_id="fake", model_id="fake", vectors=(values,))

    assert len(validated_vectors(result((1.0,) * 1024), 1)[0]) == 1024
    assert validated_vectors(result((-2.0,) + (0.0,) * 1023), 1)[0][0] == -2
    for bad in ((1.0,) * 3, (0.0,) * 1024, (1e100,) * 1024, (1e-100,) * 1024):
        with pytest.raises(ValueError):
            validated_vectors(result(bad), 1)
    with pytest.raises(ValueError):
        validated_vectors(result((1.0,) * 1024), 2)
    for value in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValidationError):
            result((value,) * 1024)
        malformed = EmbeddingResult.model_construct(
            provider_id="fake", model_id="fake", vectors=((value,) * 1024,)
        )
        with pytest.raises(ValidationError):
            validated_vectors(malformed, 1)


def test_rrf_exact_formula_ties_limits_and_bad_lane() -> None:
    ranked = fuse(["b", "a"], ["a", "b"])
    assert [r[0] for r in ranked] == ["a", "b"]
    assert ranked[0] == ("a", 2, 1, 1 / 62 + 1 / 61)
    assert fuse([], ["x"]) == [("x", None, 1, 1 / 61)]
    assert fuse(["x"], []) == [("x", 1, None, 1 / 61)]
    assert fuse([], []) == []
    assert len(fuse([str(i) for i in range(20)], [])) == 6
    with pytest.raises(ValueError):
        fuse(["a", "a"], ["a"])


def test_citation_and_recall_calibration() -> None:
    pool = [evidence(i) for i in range(8)]
    assert all(calibrate_checkers(pool).values())
    with pytest.raises(ValueError):
        calibrate_checkers(pool[:6])
    validate_citations([], [])
    with pytest.raises(ValueError):
        validate_citations([pool[0].evidence_id], [])
    with pytest.raises(ValueError):
        require_gates(float("nan"), 1)
    with pytest.raises(ValueError):
        require_gates(1, 0.99)
    assert score_query(pool[0].source_path, list(reversed(pool))).recall_at_6 == 0
    assert score_query(pool[0].source_path, pool).hit_at_1 == 1
    with pytest.raises(ValidationError):
        Evidence.model_validate(pool[0].model_dump() | {"evidence_id": "a" * 64})


def test_corpus_and_fixture_are_exact_locked_copies() -> None:
    root = Path(__file__).resolve().parents[2]
    names = sorted((root / "data/knowledge").glob("*"))
    assert len(names) == 6
    for path in names:
        assert (
            path.read_bytes()
            == (
                root / "docs/project/spec/v1.0/fixtures/knowledge" / path.name
            ).read_bytes()
        )
    fixture = root / "evals/retrieval/fixture.json"
    assert (
        hashlib.sha256(fixture.read_bytes()).hexdigest()
        == "c6dc4cbc960f6b9a22297aad2e9523bee90a3147b612b94dfedccfbfd976d8a4"
    )
    data = json.loads(fixture.read_bytes())
    assert len(data["queries"]) == 12
    assert data["metric_gate"]["expected_source_document_recall_at_6_min"] == 0.9
