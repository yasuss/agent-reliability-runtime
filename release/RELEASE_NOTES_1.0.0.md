# Agent Reliability Runtime 1.0.0

## Release notes

Agent Reliability Runtime 1.0.0 is the first public semantic release of a
local-first, durable and inspectable tool-using agent runtime.

The release includes PostgreSQL-backed checkpoints, trusted policy and exact
approvals, idempotent effect receipts, governed memory, OTel/audit evidence,
deterministic evaluation and a static recorded-replay viewer. The documented
runtime/configuration/tool/evidence contracts form the public v1 interface;
arbitrary internal Python symbols are not guaranteed API.

The repository is public and licensed under Apache-2.0. The v1.0.0 tag points to
the independently verified release commit. The Static Evidence Demo is deployed
as a backend-free recorded-replay viewer. No PyPI or npm package is published as
part of this release.

See [release operations](../docs/project/RELEASE_AND_DEPLOYMENT.md),
[SECURITY.md](../SECURITY.md) and [CHANGELOG.md](../CHANGELOG.md).
