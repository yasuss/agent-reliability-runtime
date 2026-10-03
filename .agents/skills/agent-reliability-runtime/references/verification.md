# Verification contract
Use cheap -> expensive evidence and bind release claims to the exact candidate.

For B00, the current task package is authoritative. Later release gates remain G0-G14 in `docs/project/spec/v1.0/11_ACCEPTANCE_GATES.md`.

Rules:
- actual command output, not "should pass";
- focused checks before broad checks;
- local typecheck/lint/unit/build before push;
- migrations must be proven from an empty DB;
- cross-platform claims distinguish TESTED from EXPECTED;
- changed behavior stales affected replay/eval evidence;
- required same-tree FAIL is retained until root cause/stability evidence resolves it;
- exact pushed SHA and terminal remote checks are required where the task asks for remote evidence;
- remote-red code remediation stops for Architect unless the task explicitly authorizes a bounded loop.
