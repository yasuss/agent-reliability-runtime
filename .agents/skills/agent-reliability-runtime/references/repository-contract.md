# Repository / branch contract
- Provider/repository: GitHub `yasuss/agent-reliability-runtime`.
- Baseline observed by Architect on 2026-10-03: private, default branch metadata `main`, Git repository empty (no commits), push/admin available to connected account.
- Because an empty Git repository has no branchable commit, the B00 task explicitly authorizes **one empty seed commit** on `main`, then all implementation happens on `codex/b00-repository-foundation` and is proposed through a PR.
- After the seed, no direct feature pushes to `main`, no force push, no history rewriting.
- Before every task: compare live branch/HEAD/remote state with task baseline. Drift => `BASELINE_DRIFT_REQUIRES_REVALIDATION`.
- The current private-repository plan did not expose GitHub rulesets to the Architect (live API returned a plan/visibility 403). Do not pretend server-side rules are present. Use process-level branch discipline and CI evidence until a later user-approved release/hosting decision changes that.
- Merge/release/publication is never implied by task completion and requires the applicable approval boundary.
