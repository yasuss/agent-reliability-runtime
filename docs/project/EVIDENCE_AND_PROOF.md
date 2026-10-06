# Evidence & Proof

This readable map follows the machine-readable [PROOF_INDEX](PROOF_INDEX.json).
Each claim points to at least one tracked executable test, script or replay.

| Claim ID | Observable proof |
| --- | --- |
| `provider-boundary` | `tests/unit/test_providers.py`, `scripts/probe_providers.py` |
| `hybrid-retrieval-citations` | `tests/unit/test_retrieval_mechanisms.py`, `tests/integration/test_retrieval.py`, `scripts/probe_retrieval.py` |
| `mcp-five-tools` | `tests/unit/test_opsdesk_contracts.py`, `tests/integration/test_opsdesk_protocol.py`, `scripts/probe_opsdesk.py` |
| `deterministic-policy` | `tests/unit/test_policy.py`, `scripts/probe_policy_effects.py` |
| `exact-approval` | `tests/integration/test_policy_effects.py`, `tests/unit/test_policy.py` |
| `idempotent-side-effects` | `tests/integration/test_policy_effects.py`, `tests/integration/test_eval_evidence.py` |
| `durable-restart` | `tests/integration/test_durable_runtime.py`, `scripts/probe_runtime.py` |
| `governed-memory` | `tests/integration/test_memory.py`, `scripts/probe_memory.py` |
| `otel-audit` | `tests/unit/test_observability_contracts.py`, `tests/integration/test_observability.py` |
| `eval-harness` | `tests/unit/test_evals_contracts.py`, `tests/unit/test_campaign.py`, `scripts/run_r10_heldout.py` |
| `adversarial-scenarios` | `tests/integration/test_mandatory_scenarios.py`, `docs/project/B100_MANDATORY_SCENARIOS.md` |
| `static-evidence-demo` | `scripts/verify_b110_replays.py`, `tests/unit/test_b110_replay_integrity.py`, `web/e2e/static-evidence.spec.ts` |

The B110 replay verifier binds static replay bytes to an accepted B100 source
SHA and receipt gates. Runtime claims remain grounded in executable tests and
real PostgreSQL/stdio proofs rather than documentation assertions.
