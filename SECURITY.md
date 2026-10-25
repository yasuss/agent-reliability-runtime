# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 2.x | Yes |
| 1.x | No — upgrade to 2.x |

## Reporting a vulnerability

Please do not publish exploit details or credentials in a normal issue. Use GitHub
private vulnerability reporting when available. If that channel is unavailable,
open a minimal issue that contains no sensitive details and asks the maintainers
to provide a private reporting channel.

Use fictional demo data only. Development Compose credentials are fixtures, not
security secrets, and must never be reused in a deployment. Never commit API
keys, tokens, private keys, `.env` files or extracted production data.

The design and runtime controls are documented in
[Security and Trust](docs/project/spec/v1.0/05_SECURITY_AND_TRUST.md),
[Trusted Execution](docs/project/TRUSTED_EXECUTION.md) and
[Observability and Audit](docs/project/OBSERVABILITY_AND_AUDIT.md).

No response-time SLA is promised. Reports are reviewed through the available
private channel and handled according to impact and reproducibility.
