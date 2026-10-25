from pathlib import Path

import pytest

from scripts.verify_release import (
    BASE_SHA,
    REVIEWED_NPM_DELTA,
    SCENARIO_SHA,
    VERSION,
    WEB_VERSION,
    check,
    scenario_digest,
)


def test_release_contract_is_green() -> None:
    assert check() == []


def test_release_contract_rejects_unreviewed_npm_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import verify_release

    monkeypatch.setattr(
        verify_release,
        "dependency_sets",
        lambda: (set(), set(REVIEWED_NPM_DELTA) | {("node_modules/other", "1.0.0")}),
    )
    assert any("unreviewed dependency drift" in error for error in check())


def test_release_contract_is_bound_to_accepted_baseline() -> None:
    assert BASE_SHA == "3c1389bdb0b358c8232ed07caccf14932f7da727"
    assert VERSION == "2.0.0"
    assert WEB_VERSION == "1.0.0"
    assert scenario_digest() == SCENARIO_SHA
    assert Path("LICENSE").is_file()


def test_local_api_documentation_prescribes_loopback_only_startup() -> None:
    command = (
        "uv run uvicorn agent_reliability_runtime.demo.api:app "
        "--host 127.0.0.1 --port 8000"
    )
    warning = "Do not bind it to `0.0.0.0`, a LAN interface, or a public interface"
    for path in (
        Path("docs/project/OPERATIONS.md"),
        Path("docs/project/LIMITATIONS.md"),
    ):
        text = path.read_text(encoding="utf-8")
        assert command in text
        assert warning in " ".join(text.split())
