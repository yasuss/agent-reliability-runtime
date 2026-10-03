"""Install locked dependencies and explicitly initialize the local development DB."""

import subprocess
import sys

from commands import run_commands

if __name__ == "__main__":
    try:
        run_commands(
            [
                ["uv", "python", "install", "3.12", "--no-bin", "--no-registry"],
                ["uv", "sync", "--locked"],
                ["npm", "--prefix", "web", "ci"],
                ["docker", "compose", "config", "--quiet"],
                [
                    "docker",
                    "compose",
                    "up",
                    "-d",
                    "db",
                    "--wait",
                    "--wait-timeout",
                    "90",
                ],
                ["uv", "run", "alembic", "upgrade", "head"],
            ]
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
