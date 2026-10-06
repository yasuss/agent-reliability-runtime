"""Fail-fast command execution shared by bootstrap and verification."""

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_commands(commands: Sequence[Sequence[str]], root: Path = ROOT) -> None:
    for command in commands:
        executable = shutil.which(command[0])
        if executable is None:
            raise FileNotFoundError(f"Required executable unavailable: {command[0]}")
        print("RUN " + " ".join(command), flush=True)
        subprocess.run([executable, *command[1:]], cwd=root, check=True)
