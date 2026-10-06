from scripts.verify_behavior_provenance import ACCEPTED_SOURCE_SHA, SCENARIO_SHA, check


def test_accepted_behavior_provenance_is_green() -> None:
    assert ACCEPTED_SOURCE_SHA == "83514ebad336dbd6faf1b790c597ec8037be0874"
    assert (
        SCENARIO_SHA
        == "ad14a89fb5816f2eea2ab700394df4b231191cb466e4b326437d035e34f475f9"
    )
    assert check() == []
