# Contributing

Read `AGENTS.md` and [the project documentation map](docs/project/README.md).
Keep changes within the documented v1 scope and propose them through a pull
request to `main`. Explain the behavior and verification impact in the PR.

Behavior changes must update the relevant documentation and executable
verification. Preserve trusted policy, exact approval, idempotent receipts,
durable checkpoints, non-authorizing memory/retrieval/MCP boundaries and the
static-only demo contract. Do not weaken an acceptance oracle to make a failing
implementation pass.

Run the applicable local checks before push, including `python scripts/verify.py`
and the documented database or browser gates. Keep credentials, private keys,
`.env` files and sensitive logs out of commits.

For security reports, follow [SECURITY.md](SECURITY.md) instead of publishing
exploit details in a normal issue.
