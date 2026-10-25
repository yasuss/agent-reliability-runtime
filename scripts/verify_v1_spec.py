"""Validate the immutable v1 artifact against its exact historical Git tree."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_V1_SHA = "e9fd3d29a969d66ad907ff5f7d0ea0055ed7ae2a"


def historical_paths() -> set[str]:
    return set(
        subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", HISTORICAL_V1_SHA], cwd=ROOT
        )
        .decode()
        .splitlines()
    )


def main() -> int:
    tag = (
        subprocess.check_output(
            ["git", "rev-parse", "refs/tags/v1.0.0^{commit}"], cwd=ROOT
        )
        .decode()
        .strip()
    )
    if tag != HISTORICAL_V1_SHA:
        print("FAIL: immutable v1.0.0 tag drift", file=sys.stderr)
        return 1
    # A disposable local checkout preserves the validator's original HEAD/blob
    # oracle. No network, manifest edits or historical proof-path aliases.
    with tempfile.TemporaryDirectory(prefix="arr-v1-spec-") as directory:
        snapshot = Path(directory) / "snapshot"
        subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--shared",
                "--no-checkout",
                str(ROOT),
                str(snapshot),
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(snapshot),
                "-c",
                "core.autocrlf=false",
                "checkout",
                "--quiet",
                "--detach",
                HISTORICAL_V1_SHA,
            ],
            check=True,
        )
        result = subprocess.run(
            [
                sys.executable,
                str(snapshot / "docs/project/spec/v1.0/scripts/validate_spec.py"),
                "--root",
                str(snapshot),
            ],
            check=False,
        )
    if result.returncode == 0:
        print(f"PASS: historical v1.0.0 spec/traceability at {HISTORICAL_V1_SHA}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
