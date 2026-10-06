"""Local checks reused verbatim in CI."""

import argparse
import subprocess
import sys

from commands import run_commands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["static-unit", "db", "all"], default="all")
    args = parser.parse_args()
    commands: list[list[str]] = []
    if args.scope in {"static-unit", "all"}:
        commands += [
            ["uv", "sync", "--locked"],
            ["uv", "run", "ruff", "format", "--check", "."],
            ["uv", "run", "ruff", "check", "."],
            ["uv", "run", "mypy", "src", "mcp_server", "tests"],
            ["uv", "run", "python", "scripts/verify_docs.py"],
            [
                "uv",
                "run",
                "python",
                "docs/project/spec/v1.0/scripts/validate_spec.py",
            ],
            ["uv", "run", "python", "scripts/verify_release.py"],
            ["uv", "run", "python", "scripts/verify_behavior_provenance.py"],
            ["uv", "run", "pytest", "tests/unit"],
            ["npm", "--prefix", "web", "ci"],
            ["npm", "--prefix", "web", "run", "lint"],
            ["npm", "--prefix", "web", "run", "typecheck"],
            ["npm", "--prefix", "web", "test", "--", "--run"],
            ["npm", "--prefix", "web", "run", "build"],
        ]
    if args.scope in {"db", "all"}:
        commands += [
            ["docker", "compose", "config", "--quiet"],
            ["docker", "compose", "up", "-d", "db", "--wait", "--wait-timeout", "90"],
            ["uv", "run", "alembic", "upgrade", "head"],
            ["uv", "run", "python", "scripts/setup_checkpoints.py"],
            ["uv", "run", "pytest", "tests/integration"],
        ]
    commands.append(["uv", "run", "python", "scripts/secret_scan.py"])
    try:
        run_commands(commands)
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
