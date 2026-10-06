# 08 — Static Evidence Demo

## Objective

A technical reviewer should understand the project thesis and inspect strong evidence in a few minutes without installing anything or supplying an API key.

## Public deployment

React + TypeScript + Vite static site deployed to Vercel.

No backend, database, LLM or secret is required at the public URL.

A persistent badge must state **Recorded acceptance replay** or equivalent. The UI must not imply live inference.

## Required pages/views

### Landing

Must show:

- thesis: production agents are harder to retry, evaluate, observe and secure than to demo;
- concise architecture diagram;
- exact capability list;
- links to source repository, architecture, threat model and eval methodology;
- evidence summary generated from accepted replay receipts.

### Scenario gallery

Expose at least these five curated accepted replays:

1. grounded read-only task;
2. approval-bound side effect;
3. prompt-injection attempt blocked;
4. process restart + exactly-once side effect;
5. poisoned memory ignored for authorization.

### Run detail

Show an ordered timeline with expandable steps:

- request
- retrieved evidence
- model decision summary (not hidden chain-of-thought)
- proposed tool + validated arguments
- policy decision
- approval record when applicable
- tool result/effect receipt
- recovery event when applicable
- final response
- eval assertions and verdict

The page should visibly distinguish **model-produced**, **external/untrusted data**, **trusted policy**, **human decision** and **verified environment state**.

## Explicit non-features

- no public arbitrary prompt field;
- no login;
- no live edit of traces;
- no fake streaming;
- no decorative dashboard metrics without an evidence artifact.

## Visual standard

Professional, restrained, high-contrast and readable. The UI is an evidence viewer, not a consumer chat product. Accessibility basics (keyboard focus, semantic controls, contrast, reduced-motion respect) are mandatory.
