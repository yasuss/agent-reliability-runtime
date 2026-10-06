# Debugging and proof validity
For material failures classify the correct object first: PRODUCT, TEST_HARNESS, PROOF_ARCHITECTURE, CI_ENVIRONMENT, PROCESS_TOOLING, DEPENDENCY_OR_VENDOR, DOCUMENTATION_OR_CONTRACT, UNKNOWN.

Then: reproduce -> inspect full error/context -> identify invariant -> one falsifiable hypothesis -> one discriminating bounded local experiment. Discard failed hypotheses; do not stack speculative workarounds.

A test is proof only if its oracle can fail for the intended invariant at the minimum effective layer. New decision-making verifiers need a known-good PASS, a known-bad FAIL for the intended reason, and actual invocation proof.
