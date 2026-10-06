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
