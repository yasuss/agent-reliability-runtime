# Changelog

## 2.0.0

- Separate reusable framework-neutral core from framework/service adapters and OpsDesk demo.
- Expose seven typed implemented extension ports and four planned interface-only ports.
- Add VerificationStatus PASS/FAIL/PARTIAL; current OpsDesk behavior remains unchanged.
- Preserve behavior and external dependencies without upgrades or schema migrations.
- Break internal Python import paths; retain CLI, MCP server and Quickstart entry points.
- Keep static web and recorded replay bytes unchanged; no Vercel redeploy.
- Defer dependency extras to a later release.


## 1.0.0

Initial published release summary for the local-first Agent Reliability Runtime.

- durable LangGraph execution backed by PostgreSQL checkpoints;
- trusted policy, exact approvals and idempotent effect receipts;
- scoped governed memory, correlated OTel/audit evidence and deterministic evaluation;
- Static Evidence Demo with five integrity-checked recorded replay/receipt pairs;
- Apache-2.0 licensing and documented security/contribution guidance.

Version 1.0.0 was published as the immutable v1.0.0 Git tag and GitHub release.
