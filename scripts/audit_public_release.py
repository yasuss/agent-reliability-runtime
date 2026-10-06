"""Privacy-safe full-history and Actions exposure audit for release review."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(
        rb"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"
    ),
    "aws-access-key": re.compile(rb"\bAKIA[A-Z0-9]{16}\b"),
    "openai-key": re.compile(rb"\bsk-[A-Za-z0-9]{20,}\b"),
}
NOREPLY = re.compile(r"(?:@users\.noreply\.github\.com|@github\.com)$", re.I)


def run(*args: str, check: bool = True) -> bytes:
    return (
        subprocess.check_output(args, cwd=ROOT, stderr=subprocess.DEVNULL)
        if check
        else subprocess.run(args, cwd=ROOT, capture_output=True).stdout
    )


def history_blobs() -> list[tuple[str, str]]:
    rows = (
        run("git", "rev-list", "--objects", "--all")
        .decode(errors="replace")
        .splitlines()
    )
    seen: set[str] = set()
    result = []
    for row in rows:
        parts = row.split(" ", 1)
        oid = parts[0]
        path = parts[1] if len(parts) == 2 else ""
        if oid not in seen:
            seen.add(oid)
            result.append((oid, path))
    return result


def audit(*, include_actions: bool = True) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    for path in run("git", "ls-files").decode(errors="replace").splitlines():
        if Path(path).name in {".env", ".env.local", ".env.production"} or Path(
            path
        ).suffix in {".pem", ".key"}:
            findings.append({"class": "tracked-credential-file", "path": path})
    objects = history_blobs()
    batch = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=ROOT,
        input=b"".join(f"{oid}\n".encode() for oid, _ in objects),
        capture_output=True,
        check=False,
    )
    stream = memoryview(batch.stdout)
    offset = 0
    for oid, path in objects:
        end = batch.stdout.find(b"\n", offset)
        if end < 0:
            break
        header = batch.stdout[offset:end]
        offset = end + 1
        if not header or b" missing" in header:
            continue
        try:
            size = int(header.split()[-1])
        except (ValueError, IndexError):
            continue
        blob = stream[offset : offset + size]
        offset += size + 1
        for label, pattern in PATTERNS.items():
            if pattern.search(blob):
                findings.append({"class": label, "path": path or oid})
    metadata_commits = 0
    metadata_identities: set[str] = set()
    for row in (
        run("git", "log", "--all", "--format=%H%x00%ae%x00%ce")
        .decode(errors="replace")
        .splitlines()
    ):
        parts = row.split("\x00")
        if len(parts) != 3:
            continue
        author, committer = parts[1], parts[2]
        bad = [value for value in (author, committer) if not NOREPLY.search(value)]
        if bad:
            metadata_commits += 1
            metadata_identities.update("non-noreply" for _ in bad)
    workflow_secret_refs = []
    for workflow_path in (ROOT / ".github/workflows").glob("*.y*ml"):
        if "secrets." in workflow_path.read_text(encoding="utf-8", errors="ignore"):
            workflow_secret_refs.append(workflow_path.relative_to(ROOT).as_posix())
    action_runs: list[dict[str, object]] = []
    action_log_findings = 0
    if include_actions:
        gh = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--limit",
                "1000",
                "--json",
                "databaseId,conclusion,event,url",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if gh.returncode != 0:
            return {
                "state": "FAIL_UNSCANNED_HISTORY",
                "reason": "GitHub Actions history unavailable",
                "secret_findings": findings,
            }
        try:
            runs = json.loads(gh.stdout)
        except json.JSONDecodeError:
            return {
                "state": "FAIL_UNSCANNED_HISTORY",
                "reason": "GitHub Actions history was not machine-readable",
                "secret_findings": findings,
            }
        for item in runs:
            run_id = str(item.get("databaseId"))
            log = subprocess.run(
                ["gh", "run", "view", run_id, "--log"], cwd=ROOT, capture_output=True
            ).stdout
            for label, pattern in PATTERNS.items():
                if pattern.search(log):
                    action_log_findings += 1
            action_runs.append(
                {
                    "id": item.get("databaseId"),
                    "conclusion": item.get("conclusion"),
                    "event": item.get("event"),
                    "url": item.get("url"),
                }
            )
    if workflow_secret_refs:
        findings.extend(
            {"class": "workflow-secret-reference", "path": path}
            for path in workflow_secret_refs
        )
    if action_log_findings:
        findings.append(
            {"class": "actions-log-secret-pattern", "count": str(action_log_findings)}
        )
    if findings:
        state = "FAIL_SECRET_EXPOSURE"
    elif metadata_commits:
        state = "PASS_WITH_METADATA_REVIEW_REQUIRED"
    else:
        state = "PASS"
    return {
        "state": state,
        "secret_findings": findings,
        "non_noreply_distinct_count": len(metadata_identities),
        "non_noreply_commit_count": metadata_commits,
        "actions_runs": action_runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-actions", action="store_true")
    args = parser.parse_args()
    result = audit(include_actions=not args.skip_actions)
    print(json.dumps(result, sort_keys=True))
    return 1 if result["state"].startswith("FAIL_") else 0


if __name__ == "__main__":
    raise SystemExit(main())
