from pathlib import Path

import pytest

from scripts.verify_release import (
    BASE_SHA,
    RELEASE_NOTES_PATH,
    REVIEWED_NPM_DELTA,
    SCENARIO_SHA,
    V20_RELEASE_SHA,
    VERSION,
    WEB_VERSION,
    check,
    scenario_digest,
    validate_current_release_tag_state,
)


def test_release_contract_is_green() -> None:
    assert check() == []
    assert check(require_unreleased=True) == []


def test_current_release_tag_absent_pre_release() -> None:
    assert (
        validate_current_release_tag_state(
            tag_sha=None,
            candidate_sha="candidate",
            tag_is_ancestor=None,
            tag_version=None,
            release_notes_present=None,
            require_unreleased=True,
        )
        == []
    )


def test_current_release_tag_present_pre_release_is_rejected() -> None:
    errors = validate_current_release_tag_state(
        tag_sha="tag",
        candidate_sha="candidate",
        tag_is_ancestor=True,
        tag_version="2.1.0",
        release_notes_present=True,
        require_unreleased=True,
    )
    assert any("tag exists before release" in error for error in errors)


def test_current_release_tag_valid_after_release() -> None:
    assert (
        validate_current_release_tag_state(
            tag_sha="tag",
            candidate_sha="candidate",
            tag_is_ancestor=True,
            tag_version="2.1.0",
            release_notes_present=True,
            require_unreleased=False,
        )
        == []
    )


@pytest.mark.parametrize(
    ("tag_is_ancestor", "tag_version", "release_notes_present"),
    [
        (False, "2.1.0", True),
        (True, "2.0.0", True),
        (True, "2.1.0", False),
    ],
)
def test_current_release_tag_inconsistent_after_release_fails(
    tag_is_ancestor: bool,
    tag_version: str,
    release_notes_present: bool,
) -> None:
    errors = validate_current_release_tag_state(
        tag_sha="tag",
        candidate_sha="candidate",
        tag_is_ancestor=tag_is_ancestor,
        tag_version=tag_version,
        release_notes_present=release_notes_present,
        require_unreleased=False,
    )
    assert errors


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
    assert VERSION == "2.1.0"
    assert V20_RELEASE_SHA == "77574ee445e97fe282a62c2528b2c250e6998ddb"
    assert RELEASE_NOTES_PATH == "release/RELEASE_NOTES_2.1.0.md"
    assert WEB_VERSION == "1.0.0"
    assert scenario_digest() == SCENARIO_SHA
    assert Path("LICENSE").is_file()


def test_predecessor_tag_is_validated() -> None:
    from scripts import verify_release

    assert verify_release.git("rev-parse", "refs/tags/v2.0.0").decode().strip() == (
        verify_release.V20_RELEASE_SHA
    )


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
