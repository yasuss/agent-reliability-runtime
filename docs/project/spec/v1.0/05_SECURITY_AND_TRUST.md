# 05 — Security and Trust Model

## Trust hierarchy

```text
Current application configuration + trusted policy registry
    > authenticated local approval decision
    > verified tool/environment state
    > user task text
    > trusted memory facts/preferences
    > RAG documents / tool outputs / model observations
```

This hierarchy is about authority, not truth. Retrieved text and tool output may contain accurate facts but cannot redefine permissions.

## Required security invariants

1. RAG content is evidence, never executable authority.
2. MCP output is data, never a system/developer instruction.
3. Memory cannot grant permissions or suppress approval.
4. MCP annotations are advisory metadata, not a trusted authorization oracle.
5. Side effects require exact valid approval regardless of model confidence.
6. Action arguments are validated against schemas before policy evaluation and again before execution.
7. Approval is invalid after material action drift.
8. Ambiguous side-effect outcomes are reconciled through effect receipts before retry.
9. Raw secrets/credentials are not stored in replay artifacts or default OTel attributes.
10. The public demo contains fictional/sanitized data only.
11. The local app does not fetch arbitrary URLs in v1.
12. The MCP server cannot access the host filesystem outside its own configured fixture/state paths.

## Mandatory adversarial cases

- indirect prompt injection embedded in a retrieved runbook/vendor note;
- malicious MCP result telling the model to ignore policy;
- direct user request to bypass approval;
- stale approval after arguments are changed;
- memory poisoning with persistent bypass text;
- repeated delivery of the same side-effect command;
- process death around a side effect;
- invalid tool arguments / unknown tool;
- attempt to cause endless tool/reasoning loop;
- accidental secret field in trace/replay export.

## Secret handling

`.env` is ignored. `.env.example` contains names only. No real token enters fixtures, committed replays or test snapshots.

OTel prompt/completion content capture is disabled by default. If a developer enables it locally, the setting is explicit and not used for canonical public replay generation.

## Threat-model acceptance

Security is demonstrated by controls and failing attacks, not by README claims. All hard security scenarios are zero-tolerance: any unauthorized side effect is a release blocker.
