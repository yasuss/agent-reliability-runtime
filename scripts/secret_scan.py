"""Deterministic UTF-8 source scan; not a replacement for credential review."""

import argparse
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    "forbidden-marker": re.compile("ARR_" + "FORBIDDEN_SECRET_[A-Za-z0-9]+"),
}


def scan(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append(f"{path}: {label}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    if args.directory:
        paths = [p for p in args.directory.rglob("*") if p.is_file()]
    else:
        names = (
            subprocess.check_output(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
            )
            .decode()
            .split("\0")
        )
        paths = [Path(name) for name in names if name]
    findings = scan(paths)
    for finding in findings:
        print(finding)  # Never include matched secret contents.
    print(f"Secret scan: {len(findings)} findings / {len(paths)} files")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
