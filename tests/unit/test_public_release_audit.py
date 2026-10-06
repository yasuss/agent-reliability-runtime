from scripts.audit_public_release import audit


def test_public_audit_is_privacy_safe_and_secret_free() -> None:
    result = audit(include_actions=False)
    assert result["state"] in {"PASS", "PASS_WITH_METADATA_REVIEW_REQUIRED"}
    assert not result["secret_findings"]
    assert "non_noreply_commit_count" in result
    assert "non_noreply_distinct_count" in result
