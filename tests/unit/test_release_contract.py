from pathlib import Path

from scripts.verify_release import (
    BASE_SHA,
    SCENARIO_SHA,
    VERSION,
    check,
    scenario_digest,
)


def test_release_contract_is_green() -> None:
    assert check() == []


def test_release_contract_is_bound_to_accepted_baseline() -> None:
    assert BASE_SHA == "4cc3f9fdaeb5e3061e2f87a7aab0abaf6c92b265"
    assert VERSION == "1.0.0"
    assert scenario_digest() == SCENARIO_SHA
    assert Path("LICENSE").is_file()


def test_local_api_documentation_prescribes_loopback_only_startup() -> None:
    command = (
        "uv run uvicorn agent_reliability_runtime.api:app --host 127.0.0.1 --port 8000"
    )
    warning = "Do not bind it to `0.0.0.0`, a LAN interface, or a public interface"
    for path in (
        Path("docs/project/OPERATIONS.md"),
        Path("docs/project/LIMITATIONS.md"),
    ):
        text = path.read_text(encoding="utf-8")
        assert command in text
        assert warning in " ".join(text.split())
