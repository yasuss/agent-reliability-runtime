# ARR 2.0.0 release notes

- Separate reusable framework-neutral core from framework/service adapters and OpsDesk demo.
- Expose seven typed implemented extension ports and four planned interface-only ports.
- Add VerificationStatus PASS/FAIL/PARTIAL; current OpsDesk behavior remains unchanged.
- Preserve runtime/Python dependencies and database schema/migrations.
- Patch Vite development/build tooling from 8.3.2 to 8.3.3 to resolve the reviewed
  upstream advisories; static application output remains unchanged.
- Break internal Python import paths; retain CLI, MCP server and Quickstart entry points.
- Keep the historical static replay deployment unchanged; no production Vercel
  redeploy is required.
- Defer dependency extras to a later release.
