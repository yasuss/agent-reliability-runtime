# ARR 2.0.0 release notes

- Separate reusable framework-neutral core from framework/service adapters and OpsDesk demo.
- Expose seven typed implemented extension ports and four planned interface-only ports.
- Add VerificationStatus PASS/FAIL/PARTIAL; current OpsDesk behavior remains unchanged.
- Preserve behavior and external dependencies without upgrades or schema migrations.
- Break internal Python import paths; retain CLI, MCP server and Quickstart entry points.
- Keep static web and recorded replay bytes unchanged; no Vercel redeploy.
- Defer dependency extras to a later release.

Candidate pending independent Architect acceptance. No tag or release action is performed by this refactor.
