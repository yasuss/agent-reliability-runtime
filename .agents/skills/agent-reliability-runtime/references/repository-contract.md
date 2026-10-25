# Repository / branch contract
- GitHub repository: `yasuss/agent-reliability-runtime`, public with protected main.
- Current task baseline and branch instructions must be validated against live refs before edits.
- For the v2 refactor, start from exact main `3c1389bdb0b358c8232ed07caccf14932f7da727` on `codex/v2-core-boundaries`.
- All edits and required local verification precede one implementation commit, one push and one PR.
- No direct feature push to main, force push or history rewrite.
- The immutable historical v1.0.0 tag is `e9fd3d29a969d66ad907ff5f7d0ea0055ed7ae2a`.
- Merge/tag/release/deployment follow independent acceptance; they are not task completion actions.
- Baseline drift requires revalidation. Never invent branch-protection or remote CI evidence.
