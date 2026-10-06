# State Integrity / Recovery Protocol

Activate when verification/bootstrap steps can leave persistent artifacts, exact-state claims are material, execution is resumed after interruption, or an operational failure may be recoverable without changing the accepted task decisions.

## Exact-state model

Separate:

```text
SUBJECT_STATE
OPERATIONAL_RESIDUE
```

Do not assume earlier gates are side-effect free.

Rules:
- arbitrary/unclassified extras fail closed;
- never blanket-ignore residue that can influence later execution or acceptance;
- executable/semantically active residue must be included in the integrity boundary or later execution must be forced to the exact accepted subject state;
- narrowly classified operational residue may be separately hashed/sealed/redirected/isolated when retention is safe;
- do not require deletion if deletion is not the proof goal and retention can be proven inert or contained;
- do require cleanup/containment when retained state can affect behavior or violate the task/security contract.

## Bounded recovery

A recovery addendum may be followed only when it is bound to the original task/package identity and the live baseline, and it does not change:

```text
scope/non-goals
architecture
security/trust boundary
material prerequisites
approved dependencies/services
proof oracle / acceptance meaning
compatibility claim
release strategy / approval boundary
```

If any surface changes:
```text
STOP = ARCHITECT_DECISION_REQUIRED
```

Recovery evidence must preserve the original failure, state which steps were replaced/skipped, and report deviations. Do not silently broaden an allowlist or weaken acceptance to obtain PASS.

## Resume after interruption

Reconstruct actual execution state:

```text
EXECUTED_PASS
EXECUTED_FAIL
NOT_RUN
UNKNOWN_RECHECK_REQUIRED
```

Planned/mentioned work is not executed evidence. Recheck live drift and unconfirmed/materially stale state, then continue from the last safe proven state.
