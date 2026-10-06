# Agent Reliability Runtime 1.0.0

## Candidate notes

This draft records the first semantic release candidate for a local-first,
durable and inspectable tool-using agent runtime.

The candidate includes PostgreSQL-backed checkpoints, trusted policy and exact
approvals, idempotent effect receipts, governed memory, OTel/audit evidence,
deterministic evaluation and a static recorded-replay viewer. The documented
runtime/configuration/tool/evidence contracts form the public v1 interface;
arbitrary internal Python symbols are not guaranteed API.

The repository is licensed under Apache-2.0. No PyPI or npm package is
published by this candidate. No repository visibility change, tag, GitHub
release or Vercel deployment is performed during candidate preparation.

See [release operations](../docs/project/RELEASE_AND_DEPLOYMENT.md), the
[public release checklist](../docs/project/PUBLIC_RELEASE_CHECKLIST.md),
[SECURITY.md](../SECURITY.md) and [CHANGELOG.md](../CHANGELOG.md).
