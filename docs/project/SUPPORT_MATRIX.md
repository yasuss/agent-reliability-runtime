# Support Matrix

Statuses distinguish retained execution evidence from a portable contract.

| Surface | Status | Proof context |
| --- | --- | --- |
| Windows 10 Pro local + Ollama qwen3:4b acceptance | TESTED | Accepted local provider and reliability acceptance evidence |
| Windows 11 local end-to-end | EXPECTED | Target platform; no accepted live run |
| Ubuntu GitHub-hosted static/unit | TESTED | Exact-head CI matrix |
| Ubuntu GitHub-hosted PostgreSQL integration | TESTED | Exact-head CI database job |
| macOS GitHub-hosted static/unit | TESTED | Exact-head CI matrix |
| macOS live local Ollama/full DB agent | EXPECTED | Portable local path; no accepted run |
| vLLM OpenAI-compatible provider | CONTRACT_ONLY | Deterministic wire-contract tests |
| generic cloud OpenAI-compatible live acceptance | NOT_CLAIMED | No accepted cloud campaign |
| Static Evidence Demo Chromium on Ubuntu CI | TESTED | Playwright critical path |
| live public chat/inference | NOT_CLAIMED | Static viewer has no live backend |

TESTED identifies a retained execution context. EXPECTED identifies a targeted
portable path without that execution evidence. CONTRACT_ONLY identifies an
interface proof, and NOT_CLAIMED is outside the accepted v1 evidence.
