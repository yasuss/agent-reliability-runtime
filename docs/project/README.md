# Project Documentation & Operational Guidance

This directory is the navigation layer for the current implementation. The
locked v1 contract under `spec/v1.0/` remains authoritative for exact semantics.

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
- [Public Release Checklist](PUBLIC_RELEASE_CHECKLIST.md)
- [Requirement traceability](spec/v1.0/requirements/REQUIREMENTS.json)
- [Verification catalog](spec/v1.0/requirements/VERIFICATION_CATALOG.json)

The component pages explain the current implementation; the catalog connects
each locked requirement to a named verification method and tracked proof.
