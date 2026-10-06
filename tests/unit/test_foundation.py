import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_reliability_runtime.api import Health, app
from scripts.commands import run_commands


def test_liveness_boundary() -> None:
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/api/v1/runs").status_code == 405


def test_health_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Health.model_validate({"status": "ok", "authorization": True})


def test_command_runner_success_and_failure(tmp_path: Path) -> None:
    run_commands([[sys.executable, "-c", "pass"]], root=tmp_path)
    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_commands(
            [
                [sys.executable, "-c", "raise SystemExit(7)"],
                [sys.executable, "-c", "open('must-not-exist', 'w').close()"],
            ],
            root=tmp_path,
        )
    assert failure.value.returncode == 7
    assert not (tmp_path / "must-not-exist").exists()


def test_secret_scan_cli_calibration(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "secret_scan.py"
    fixture = tmp_path / "fixture.txt"
    for content, expected, reason in [
        ("fictional clean data", 0, "0 findings"),
        ("gh" + "p_" + "a" * 40, 1, "github-token"),
        ("AK" + "IA" + "A" * 16, 1, "aws-access-key"),
        ("-----BEGIN " + "PRIVATE KEY-----", 1, "private-key"),
        ("ARR_" + "FORBIDDEN_SECRET_negative", 1, "forbidden-marker"),
        ("public identifier: gh_example", 0, "0 findings"),
    ]:
        fixture.write_text(content, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(script), "--directory", str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == expected
        assert reason in result.stdout
        if expected:
            assert content not in result.stdout
