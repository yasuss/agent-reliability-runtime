import pytest

from scripts import verify_behavior_provenance as provenance
from scripts.verify_behavior_provenance import (
    ACCEPTED_SOURCE_SHA,
    REFACTOR_BASE_SHA,
    SCENARIO_SHA,
    check,
    surface_errors,
)


def test_accepted_behavior_provenance_is_green() -> None:
    assert ACCEPTED_SOURCE_SHA == "83514ebad336dbd6faf1b790c597ec8037be0874"
    assert (
        SCENARIO_SHA
        == "ad14a89fb5816f2eea2ab700394df4b231191cb466e4b326437d035e34f475f9"
    )
    assert check() == []


def test_refactor_surface_calibration() -> None:
    assert REFACTOR_BASE_SHA == "3c1389bdb0b358c8232ed07caccf14932f7da727"
    assert not surface_errors(
        {
            "src/agent_reliability_runtime/core/policy.py",
            "docs/extension-points.md",
            "migrations/env.py",
            "uv.lock",
            "release/RELEASE_NOTES_2.0.0.md",
        }
    )
    for path in (
        "web/src/App.tsx",
        "web/new-file.txt",
        "migrations/versions/new.py",
        "docs/project/spec/v1.0/00_PRODUCT_CONTRACT.md",
        "data/seed/new.json",
        "data/knowledge/new.md",
        "compose.yaml",
        "alembic.ini",
        ".github/workflows/unauthorized.yml",
        "release/RELEASE_NOTES_1.0.0.md",
    ):
        assert surface_errors({path}), path


@pytest.mark.parametrize("kind", ["runtime", "lock"])
def test_external_dependency_drift_fails(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    original = provenance.dependency_sets

    def drift(revision: str | None) -> tuple[set[str], set[tuple[str, str]]]:
        runtime, lock = original(revision)
        if revision is None:
            if kind == "runtime":
                runtime.add("forbidden-new-dependency==1.0")
            else:
                lock.add(("forbidden-resolution", "changed"))
        return runtime, lock

    monkeypatch.setattr(provenance, "dependency_sets", drift)
    assert any("drift" in error for error in provenance.check())
