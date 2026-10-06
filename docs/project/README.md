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
- [reliability acceptance mandatory scenarios](reliability acceptance_MANDATORY_SCENARIOS.md)
- [Static Evidence Demo Static Evidence Demo](Static Evidence Demo_STATIC_EVIDENCE.md)
- [evaluation harness contracts](evaluation harness_EVAL_HARNESS.md)

Stage and component documents remain useful implementation references. The
canonical pages above are the operational starting point.
