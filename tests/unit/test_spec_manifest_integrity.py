"""Git-blob specification and bidirectional traceability calibration."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest


def _validator() -> ModuleType:
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "spec_integrity", root / "docs/project/spec/v1.0/scripts/validate_spec.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _write_manifest(root: Path, raw: bytes) -> None:
    directory = root / "docs/project/spec/v1.0"
    (directory / "PACKAGE_MANIFEST.json").write_bytes(raw)
    (directory / "PACKAGE_MANIFEST.sha256").write_bytes(
        (hashlib.sha256(raw).hexdigest() + "  PACKAGE_MANIFEST.json\n").encode()
    )
    _git(root, "add", "docs/project/spec/v1.0")


@pytest.fixture
def git_fixture(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "core.autocrlf", "false")
    _git(tmp_path, "config", "user.name", "Calibration")
    _git(tmp_path, "config", "user.email", "calibration@example.invalid")
    directory = tmp_path / "docs/project/spec/v1.0"
    directory.mkdir(parents=True)
    # Exact known size: a CRLF worktree has 3695 bytes, LF index has 3626.
    blob = b"x\n" * 69 + b"x" * (3626 - 138)
    (directory / "00_PRODUCT_CONTRACT.md").write_bytes(blob)
    _git(tmp_path, "add", ".")
    _write_manifest(tmp_path, _validator().manifest_bytes(tmp_path))
    _git(tmp_path, "commit", "-m", "Locked calibration payload")
    return tmp_path


def test_index_generation_and_head_validation_ignore_dirty_crlf_worktree(
    git_fixture: Path,
) -> None:
    validator = _validator()
    before = validator.manifest_bytes(git_fixture)
    path = git_fixture / "docs/project/spec/v1.0/00_PRODUCT_CONTRACT.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert path.stat().st_size == 3695
    assert validator.manifest_bytes(git_fixture) == before
    assert validator.validate_manifest(git_fixture, "index") == []
    assert validator.validate_manifest(git_fixture, "HEAD") == []
    path.write_bytes(b"new staged payload\n")
    _git(git_fixture, "add", str(path))
    assert validator.validate_manifest(git_fixture, "index")
    assert validator.validate_manifest(git_fixture, "HEAD") == []


@pytest.mark.parametrize(
    "mutation", ["crlf", "hash", "missing", "extra", "duplicate", "checksum"]
)
def test_corrupt_manifest_controls_fail(git_fixture: Path, mutation: str) -> None:
    validator = _validator()
    raw = validator.manifest_bytes(git_fixture)
    manifest = json.loads(raw)
    if mutation == "crlf":
        manifest["files"][0]["size"] = 3695
    elif mutation == "hash":
        manifest["files"][0]["sha256"] = "0" * 64
    elif mutation == "missing":
        manifest["files"] = []
    elif mutation == "extra":
        manifest["files"].append({"path": "extra.md", "size": 0, "sha256": "0" * 64})
    elif mutation == "duplicate":
        manifest["files"].append(manifest["files"][0])
    raw = (json.dumps(manifest) + "\n").encode()
    _write_manifest(git_fixture, raw)
    if mutation == "checksum":
        (git_fixture / "docs/project/spec/v1.0/PACKAGE_MANIFEST.sha256").write_bytes(
            b"wrong\n"
        )
        _git(git_fixture, "add", ".")
    errors = validator.validate_manifest(git_fixture, "index")
    assert errors
    if mutation == "crlf":
        assert any("declared 3695 actual 3626" in error for error in errors)
    _git(git_fixture, "commit", "-m", "Corrupt control")
    assert validator.validate_manifest(git_fixture, "HEAD")


def _trace_fixture() -> tuple[dict[str, object], dict[str, object], set[str]]:
    root = Path(__file__).resolve().parents[2]
    directory = root / "docs/project/spec/v1.0/requirements"
    requirements = json.loads(
        (directory / "REQUIREMENTS.json").read_text(encoding="utf-8")
    )
    catalog = json.loads(
        (directory / "VERIFICATION_CATALOG.json").read_text(encoding="utf-8")
    )
    paths = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    return requirements, catalog, paths


def test_traceability_good_and_independent_valid_alternate() -> None:
    validator = _validator()
    requirements, catalog, paths = _trace_fixture()
    assert validator.validate_traceability(requirements, catalog, paths) == []
    alternate = copy.deepcopy(catalog)
    alternate["entries"][0]["proof_paths"] = ["tests/unit/test_contracts.py"]  # type: ignore[index]
    assert validator.validate_traceability(requirements, alternate, paths) == []


@pytest.mark.parametrize(
    "mutation", ["unknown", "reverse", "generic", "missing-proof", "no-executable"]
)
def test_traceability_broken_controls_fail(mutation: str) -> None:
    requirements, catalog, paths = _trace_fixture()
    rows = requirements["requirements"]
    entries = catalog["entries"]
    if mutation == "unknown":
        rows[0]["verification_ids"] = ["VC-UNKNOWN"]  # type: ignore[index]
    elif mutation == "reverse":
        entries[0]["requirement_ids"] = []  # type: ignore[index]
    elif mutation == "generic":
        rows[0]["acceptance"] = "acceptance gate"  # type: ignore[index]
    elif mutation == "missing-proof":
        paths.discard(entries[0]["proof_paths"][0])  # type: ignore[index]
    else:
        entries[0]["proof_paths"] = ["docs/project/ARCHITECTURE.md"]  # type: ignore[index]
    assert _validator().validate_traceability(requirements, catalog, paths)
