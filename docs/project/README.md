# Project Documentation & Operational Guidance

This directory describes the current v2 implementation. Current topology and
extension contracts live in [Architecture](ARCHITECTURE.md) and
[Extension points](../extension-points.md). `spec/v1.0/` is immutable historical
behavior/security acceptance evidence; it does not define the v2 file topology.
An accepted current task contract governs scoped changes; preserved semantics
remain constrained by the historical acceptance baseline and executable tests.

## Canonical entry points

- [Architecture](ARCHITECTURE.md) — topology, trust and durability.
- [Operations](OPERATIONS.md) — local procedures and cleanup.
- [Verification](VERIFICATION.md) — deterministic, database, provider, replay
  and CI gates.
- [Support Matrix](SUPPORT_MATRIX.md) — TESTED/EXPECTED/CONTRACT_ONLY/
  NOT_CLAIMED boundaries.
- [Limitations](LIMITATIONS.md) — explicit non-goals and evidence limits.
- [Evidence & Proof](EVIDENCE_AND_PROOF.md) — readable capability map.
- [Machine-readable PROOF_INDEX](PROOF_INDEX.json) — claim-to-proof paths.

## Deeper references

- [Product and scope](spec/v1.0/00_PRODUCT_CONTRACT.md)
- [Security and trust](spec/v1.0/05_SECURITY_AND_TRUST.md)
- [Retrieval and Citation Integrity](RETRIEVAL_AND_CITATIONS.md)
- [OpsDesk MCP Boundary](OPSDESK_MCP.md)
- [Trusted Execution](TRUSTED_EXECUTION.md)
- [Durable Runtime](DURABLE_RUNTIME.md)
- [Governed Memory](GOVERNED_MEMORY.md)
- [Observability and Audit](OBSERVABILITY_AND_AUDIT.md)
- [Evaluation Harness](EVALUATION_HARNESS.md)
- [Reliability Acceptance](RELIABILITY_ACCEPTANCE.md)
- [Static Evidence Demo](STATIC_EVIDENCE_DEMO.md)
- [Release and Deployment Operations](RELEASE_AND_DEPLOYMENT.md)
- [Requirement traceability](spec/v1.0/requirements/REQUIREMENTS.json)
- [Verification catalog](spec/v1.0/requirements/VERIFICATION_CATALOG.json)

The component pages explain the current implementation. The historical v1
requirements and verification catalog remain evidence for the immutable
`v1.0.0` tree; current v2 capability-to-proof paths are defined by
`PROOF_INDEX.json`.
