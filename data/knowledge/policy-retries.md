# Retry and Recovery Policy

Transient read failures may be retried within a bounded retry budget. A side effect with an ambiguous outcome must be reconciled through its idempotency/effect receipt before any repeat execution.
