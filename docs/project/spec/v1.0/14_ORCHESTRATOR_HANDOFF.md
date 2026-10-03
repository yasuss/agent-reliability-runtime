# 14 — Orchestrator Handoff

## Intended execution environment

User will operate with:

- `UNIVERSAL_ARCHITECT_ORCHESTRATOR_INIT_PACKAGE_v1.3`
- `UNIVERSAL_CODEX_SKILL_TEMPLATE_PACKAGE_v1.3`
- ChatGPT/Architect + Codex + user

This project package does not replace those universal packages.

## Greenfield state

No new production repository is assumed to exist yet. Before Codex implementation, Architect must revalidate:

1. intended GitHub repo state/branch;
2. current versions/compatibility of LangGraph, MCP Python SDK, FastAPI, pgvector, Ollama, OpenTelemetry and Vite;
3. current Codex skill/AGENTS semantics from the actual universal v1.3 package;
4. no material user requirement has changed.

Do not reopen locked product choices merely because a library minor version changed. Adapt implementation details while preserving contracts.

## Recommended Architect outputs

Compile the user's universal Codex template with the companion `PROJECT_CODEX_COMPILATION_INPUT_agent-reliability-runtime_v1.0.zip`.

Then issue self-contained execution task packages from `B00` onward. A task may combine adjacent backlog units only when the proof surface stays clear and no major decision becomes hidden.

## Required stop/escalation conditions

Return to Architect/user rather than broadening when:

- a locked hard invariant is not realizable with the chosen stack;
- current MCP/LangGraph semantics materially contradict the specification;
- implementation would require live paid cloud services;
- public demo appears to require a backend to meet the locked UX (it should not);
- a real security/reliability acceptance failure suggests architectural rather than local repair;
- a proposal would add multi-agent, Kubernetes, real external credentials or another explicitly excluded scope.

## Release workflow

Codex implements and validates locally. Remote CI is independent evidence, not the first compiler. Architect reviews actual repo/diff/CI and asks what could still be materially wrong. Before merge/release, user receives and performs the focused manual checklist from G14 and explicitly approves.
