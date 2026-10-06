import json

from scripts.audit_public_release import audit, metadata_summary


def test_public_audit_is_privacy_safe_and_secret_free() -> None:
    result = audit(include_actions=False)
    assert result["state"] in {"PASS", "PASS_WITH_METADATA_REVIEW_REQUIRED"}
    assert not result["secret_findings"]
    assert "non_noreply_commit_count" in result
    assert "non_noreply_distinct_count" in result


def test_distinct_metadata_control_is_count_only() -> None:
    first = "Alice.Example@Example.Invalid"
    second = "bob@example.invalid"
    commits, distinct = metadata_summary(
        [(first, first), (second, "noreply@users.noreply.github.com")]
    )
    serialized = json.dumps(
        {"non_noreply_commit_count": commits, "non_noreply_distinct_count": distinct}
    )
    assert commits == 2
    assert distinct == 2
    assert first.casefold() not in serialized
    assert second.casefold() not in serialized
