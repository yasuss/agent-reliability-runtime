"""B10 trigger calibration and preservation of the accepted B00 CI checks."""

import copy
import importlib
import re
from pathlib import Path
from typing import Any

import pytest


def workflow_contract(workflow: dict[str, Any]) -> None:
    assert workflow["on"]["push"]["branches"] == ["main", "codex/**", "release/**"]
    assert set(workflow["on"]["pull_request"]["branches"]) == {"main", "codex/**"}
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    assert set(jobs) == {"static-unit", "database", "web-e2e", "release-audit"}
    static = jobs["static-unit"]
    assert static["strategy"] == {
        "fail-fast": "false",
        "matrix": {"os": ["ubuntu-latest", "windows-latest", "macos-latest"]},
    }
    assert static["runs-on"] == "${{ matrix.os }}"
    assert [step["run"] for step in static["steps"] if "run" in step] == [
        "uv run python scripts/verify.py --scope static-unit"
    ]
    db = jobs["database"]
    assert db["runs-on"] == "ubuntu-latest"
    assert db["env"] == {
        "ARR_TEST_DATABASE_URL": "postgresql+psycopg://arr:local-development-fixture@127.0.0.1:5432/arr"
    }
    assert [step["run"] for step in db["steps"] if "run" in step] == [
        "uv sync --locked",
        "uv run python scripts/verify.py --scope db",
        "uv run pytest",
        "docker compose down --volumes",
    ]
    assert db["steps"][-1]["if"] == "always()"
    web = jobs["web-e2e"]
    assert web["runs-on"] == "ubuntu-latest"
    assert [step["run"] for step in web["steps"] if "run" in step] == [
        "npm --prefix web ci",
        "npx --prefix web playwright install --with-deps chromium",
        "npm --prefix web exec -- playwright test --config web/playwright.config.ts",
    ]
    audit = jobs["release-audit"]
    assert audit["runs-on"] == "ubuntu-latest"
    assert audit["permissions"] == {"contents": "read", "actions": "read"}
    assert [step["run"] for step in audit["steps"] if "run" in step] == [
        "uv sync --locked",
        "uv run python scripts/verify_release.py",
        "uv run python scripts/audit_public_release.py",
        "uv run python scripts/verify_docs.py",
        "uv run python docs/project/spec/v1.0/scripts/validate_spec.py",
        "uv run python scripts/secret_scan.py",
    ]
    accepted_pins = {
        "actions/checkout": "d23441a48e516b6c34aea4fa41551a30e30af803",
        "astral-sh/setup-uv": "37802adc94f370d6bfd71619e3f0bf239e1f3b78",
        "actions/setup-node": "249970729cb0ef3589644e2896645e5dc5ba9c38",
    }
    for job in jobs.values():
        for step in job["steps"]:
            if "uses" in step:
                action, sha = step["uses"].split("@")
                assert re.fullmatch("[0-9a-f]{40}", sha)
                assert accepted_pins[action] == sha
                if action == "astral-sh/setup-uv":
                    assert step["with"] == {
                        "version": "0.12.23",
                        "python-version": "3.12",
                    }
                if action == "actions/setup-node":
                    assert step["with"] == {"node-version": "24"}


def test_workflow_contract_good_bad_and_valid_alternate() -> None:
    # PyYAML is already locked transitively; BaseLoader preserves YAML's 'on'
    # key instead of YAML 1.1 coercion to bool. No new dependency is introduced.
    yaml = importlib.import_module("yaml")
    source = (
        Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"
    ).read_text()
    good = yaml.load(source, Loader=yaml.BaseLoader)
    workflow_contract(good)
    alternate = copy.deepcopy(good)
    alternate["on"]["pull_request"]["branches"].reverse()
    workflow_contract(alternate)
    bad_trigger = copy.deepcopy(good)
    bad_trigger["on"]["push"]["branches"] = ["codex/b00-repository-foundation"]
    with pytest.raises(AssertionError):
        workflow_contract(bad_trigger)
    bad_check = copy.deepcopy(good)
    bad_check["jobs"]["database"]["steps"] = bad_check["jobs"]["database"]["steps"][:-2]
    with pytest.raises(AssertionError):
        workflow_contract(bad_check)
