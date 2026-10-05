"""Committed fail-closed calibration for the B110 replay collection."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.verify_b110_replays import verify_collection

ROOT = Path(__file__).resolve().parents[2]
COLLECTION = ROOT / "web/public/replays"


def _copy_collection(tmp_path: Path) -> Path:
    target = tmp_path / "replays"
    shutil.copytree(COLLECTION, target)
    return target


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_committed_collection_passes() -> None:
    result = verify_collection(COLLECTION)
    assert result == {
        "entries": 5,
        "receipt_gates_pass": 5,
        "source_git_sha": "83514ebad336dbd6faf1b790c597ec8037be0874",
    }


def test_changed_receipt_byte_fails_closed(tmp_path: Path) -> None:
    target = _copy_collection(tmp_path)
    receipt = target / "grounded-read/receipt.json"
    data = bytearray(receipt.read_bytes())
    data[-2] ^= 1
    receipt.write_bytes(bytes(data))
    with pytest.raises(ValueError):
        verify_collection(target)


def test_foreign_source_sha_fails_closed(tmp_path: Path) -> None:
    target = _copy_collection(tmp_path)
    manifest_path = target / "index.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["accepted_source_git_sha"] = "0" * 40
    _write_json(manifest_path, manifest)
    with pytest.raises(ValueError):
        verify_collection(target)


def test_sixth_replay_manifest_entry_fails_closed(tmp_path: Path) -> None:
    target = _copy_collection(tmp_path)
    manifest_path = target / "index.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    extra = dict(manifest["entries"][-1])
    extra["slug"] = "sixth-replay"
    manifest["entries"].append(extra)
    _write_json(manifest_path, manifest)
    with pytest.raises(ValueError):
        verify_collection(target)


def test_removed_s08_recovery_event_fails_closed(tmp_path: Path) -> None:
    target = _copy_collection(tmp_path)
    replay_path = target / "process-restart-exactly-once/replay.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay["events"] = [
        event for event in replay["events"] if event["type"] != "recovery.resumed"
    ]
    _write_json(replay_path, replay)
    with pytest.raises(ValueError):
        verify_collection(target)


def test_secret_marker_fails_closed(tmp_path: Path) -> None:
    target = _copy_collection(tmp_path)
    replay_path = target / "grounded-read/replay.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay["events"][0]["summary"] = "ARR_" + "FORBIDDEN_" + "SECRET_CALIBRATION"
    _write_json(replay_path, replay)
    with pytest.raises(ValueError):
        verify_collection(target)


def test_wrong_replay_mode_fails_closed(tmp_path: Path) -> None:
    target = _copy_collection(tmp_path)
    replay_path = target / "grounded-read/replay.json"
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay["mode"] = "live"
    _write_json(replay_path, replay)
    with pytest.raises(ValueError):
        verify_collection(target)
