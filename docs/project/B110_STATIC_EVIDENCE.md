# Static Evidence Demo

The Static Evidence Demo is a static, recorded view of accepted reliability evidence. It is intentionally independent of the runtime: the browser reads five integrity-checked replay and receipt pairs from Vite's public assets and performs no live inference or backend request.

The collection covers a grounded read, an approval-bound side effect, a blocked prompt-injection attempt, process recovery with exactly one effect, and poisoned-memory authorization isolation. Each detail view labels external data, model-produced summaries, trusted policy decisions, human decisions, verified environment observations, recovery, and evaluation separately.

The manifest and every replay/receipt pair are verified by `scripts/verify_b110_replays.py`. The verifier binds all bytes to accepted B100 source SHA `83514ebad336dbd6faf1b790c597ec8037be0874`, checks the locked schemas and receipt gates, requires the S08 recovery event and replayed tool completion, and fails closed on raw prompts, arguments, hidden reasoning, or secret markers.

The browser critical path runs against a production Vite build with Chromium. It checks the landing view, five-card gallery, S02/S08/S10 detail labels, reduced motion, absence of arbitrary prompt input, and same-origin static-only network behavior.
