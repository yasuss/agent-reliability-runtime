import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest

from scripts import verify_behavior_provenance as provenance
from scripts.verify_behavior_provenance import (
    ACCEPTED_SOURCE_SHA,
    REFACTOR_BASE_SHA,
    REVIEWED_VITE_FROM,
    REVIEWED_VITE_TO,
    SCENARIO_SHA,
    V21_BASE_SHA,
    check,
    surface_errors,
    v21_surface_errors,
    validate_reviewed_web_dependency_transition,
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
            "SECURITY.md",
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


def test_v21_surface_allowlist_calibration() -> None:
    assert V21_BASE_SHA == "77574ee445e97fe282a62c2528b2c250e6998ddb"
    assert not v21_surface_errors(
        {
            "README.md",
            "src/agent_reliability_runtime/core/ports.py",
            "release/RELEASE_NOTES_2.1.0.md",
            "uv.lock",
        }
    )
    for path in (
        "src/agent_reliability_runtime/demo/local.py",
        "src/agent_reliability_runtime/adapters/langgraph/graph.py",
        "web/package.json",
        "migrations/versions/new.py",
        "docs/project/spec/v1.0/00_PRODUCT_CONTRACT.md",
        "data/seed/new.json",
        "release/RELEASE_NOTES_1.0.0.md",
    ):
        assert v21_surface_errors({path}), path


def _web_fixtures() -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
]:
    before_package = json.loads(provenance.blob(REFACTOR_BASE_SHA, "web/package.json"))
    before_lock = json.loads(
        provenance.blob(REFACTOR_BASE_SHA, "web/package-lock.json")
    )
    current_package = deepcopy(before_package)
    current_lock = deepcopy(before_lock)
    current_package["devDependencies"]["vite"] = REVIEWED_VITE_TO
    current_lock["packages"][""]["devDependencies"]["vite"] = REVIEWED_VITE_TO
    vite = current_lock["packages"]["node_modules/vite"]
    vite["version"] = REVIEWED_VITE_TO
    vite["resolved"] = "https://registry.npmjs.org/vite/-/vite-8.3.3.tgz"
    vite["integrity"] = (
        "sha512-cTAldKPImjg6c+gk48U19POPn3GCBzZwpdsN8ZMEEcbpes+6/wvfqUd0C2y3qYY4wsj8PwgFwrZ/1jBPVttMSg=="
    )
    return before_package, before_lock, current_package, current_lock


def test_reviewed_web_dependency_paths_are_authorized() -> None:
    assert not surface_errors({"web/package.json", "web/package-lock.json"})
    for path in (
        "web/src/App.tsx",
        "web/new-file.txt",
        "web/public/replays/index.json",
        "SECURITY.md",
    ):
        if path == "SECURITY.md":
            assert not surface_errors({path}), path
        else:
            assert surface_errors({path}), path


def test_exact_reviewed_vite_transition_passes() -> None:
    before_package, before_lock, current_package, current_lock = _web_fixtures()
    assert before_package["devDependencies"]["vite"] == REVIEWED_VITE_FROM
    assert (
        validate_reviewed_web_dependency_transition(
            before_package, before_lock, current_package, current_lock
        )
        == []
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda package, lock: package["devDependencies"].__setitem__("vite", "8.3.4"),
        lambda package, lock: package["dependencies"].__setitem__("react", "19.2.9"),
        lambda package, lock: lock["packages"].__setitem__(
            "node_modules/extra", {"version": "1.0.0"}
        ),
        lambda package, lock: lock["packages"]["node_modules/react"].__setitem__(
            "version", "19.2.9"
        ),
        lambda package, lock: lock.__setitem__("name", "changed-web"),
    ],
)
def test_unreviewed_web_mutations_fail(
    mutation: Callable[[dict[str, Any], dict[str, Any]], None],
) -> None:
    before_package, before_lock, current_package, current_lock = _web_fixtures()
    mutation(current_package, current_lock)
    assert validate_reviewed_web_dependency_transition(
        before_package, before_lock, current_package, current_lock
    )


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
