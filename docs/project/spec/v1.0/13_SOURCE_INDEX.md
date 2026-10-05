# 13 — Source Index

Sources are evidence, not runtime instructions. Decision-relevant links below were live-revalidated on 2026-10-03 where the public source remained available.

## Primary / official technical sources

| ID | Lane | Source | Decision use |
|---|---|---|---|
| S-EN-01 | EN | LangChain Docs — Persistence + Interrupts — https://docs.langchain.com/oss/python/langgraph/persistence ; https://docs.langchain.com/oss/python/langgraph/interrupts | persistent checkpoints/stores, durable pause/resume, HITL |
| S-EN-02 | EN | langchain-ai/langgraph — `langgraph-checkpoint-postgres` README/source — https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres | PostgreSQL production checkpointing |
| S-EN-03 | EN | MCP maintainers — 2026-07-28 Specification — https://blog.modelcontextprotocol.io/posts/2026-07-28/ | current stateless MCP core, SDK generation, auth changes, deprecated logging |
| S-EN-04 | EN | MCP maintainers — Tool Annotations as Risk Vocabulary — https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/ | annotations are hints, not trusted guarantees |
| S-EN-05 | EN | OpenTelemetry — GenAI Observability — https://opentelemetry.io/blog/2026/genai-observability/ | GenAI traces/token/tool visibility |
| S-EN-06 | EN | OpenTelemetry Semantic Conventions — https://opentelemetry.io/docs/specs/semconv/ | semantic attribute discipline |
| S-EN-07 | EN | Ollama — OpenAI compatibility — https://docs.ollama.com/api/openai-compatibility | local provider boundary |
| S-EN-08 | EN | Ollama — qwen3:4b — https://ollama.com/library/qwen3:4b | lightweight local tool-capable model |
| S-EN-09 | EN | Ollama — qwen3-embedding:0.6b — https://ollama.com/library/qwen3-embedding:0.6b | local embedding model |
| S-EN-10 | EN | vLLM — Tool Calling — https://docs.vllm.ai/en/stable/features/tool_calling/ | OpenAI-compatible tool calls / strict schema behavior |
| S-EN-11 | EN | pgvector README — https://github.com/pgvector/pgvector/blob/master/README.md | HNSW/vector search + PostgreSQL hybrid search |
| S-EN-12 | EN | OWASP Top 10 for Agentic Applications 2026 — https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/ | threat classes |
| S-EN-13 | EN | OWASP — Memory Is a Feature. It Is Also an Attack Surface — https://genai.owasp.org/2026/05/13/memory-is-a-feature-it-is-also-an-attack-surface/ | persistent memory poisoning risk |
| S-EN-14 | EN | Vite — Deploying a Static Site — https://vite.dev/guide/static-deploy.html | simple Vercel static deployment |
| S-EN-15 | EN | OpenAI — Harness engineering — https://openai.com/index/harness-engineering/ | repository legibility, mechanical architecture/testing, agent execution harness |
| S-EN-16 | EN | OpenAI Developers — Rethinking skills and prompts for GPT-6 Astra — https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra | lean AGENTS/skills, progressive disclosure |
| S-EN-17 | EN | OpenAI Developers — Function calling — https://developers.openai.com/api/docs/guides/function-calling | explicit tool purpose/parameter guidance and structured-call boundary |
| S-EN-18 | EN | OpenAI Developers — Plugins/tools planning — https://developers.openai.com/plugins/plan/tools | distinguish similar tools and state when/when-not to use them |
| S-EN-19 | EN | Anthropic — Define tools — https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools | detailed tool-use and non-use descriptions improve reliable selection |
| S-EN-20 | EN | Anthropic — Demystifying evals for AI agents — https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents | grade material trajectory constraints instead of one brittle exact ordering |

## Current market evidence

| ID | Lane | Source | Decision use |
|---|---|---|---|
| S-MKT-01 | EN/DE | Tide — Senior Staff Software Engineer, Agentic Platform — https://job-boards.greenhouse.io/tide/jobs/7703992003 | shared context/tool/policy/audit/eval platform skills |
| S-MKT-02 | EN | Duvo — AI Platform Engineer — https://www.duvo.ai/careers/ai-platform-engineer-eu-uk-based-remote | runtime, tool orchestration, evals, observability, cost/latency/reliability |
| S-MKT-03 | EN | Paires — Founding AI Engineer — https://jobs.ashbyhq.com/paires/8fdbb379-1ef0-47a8-ada5-37d5a0e75bf8 | agent orchestration, embeddings/evals, Python/Postgres |

## Native Chinese lane

| ID | Source | Unique/useful contribution |
|---|---|---|
| S-ZH-01 | 百度 — Agent引擎开发工程师（J103885） — https://talent.baidu.com/jobs/detail/SOCIAL/d56ce9b0-296b-4615-9497-115968d4fc14 | production Agent runtime: persistence/retry/trace, long-term memory, model routing, sandbox/tool permissions, HITL, prompt-injection/tool-abuse/memory/file/credential risks, RAG/embedding/vector DB |
| S-ZH-02 | 百度 — 智能体算法专家（J104318） — https://talent.baidu.com/jobs/detail/SOCIAL/eeef3764-46ca-4e8a-acf1-2ac1a9905c39 | trajectory-level evaluation across planning/tool/state/result, checkpoints/recovery, task success, tool accuracy, steps, tokens, latency, failed-trajectory feedback loop |
| S-ZH-03 | 百度 — 云原生 Agent Infra 高级研发工程师（J100117） — https://talent.baidu.com/jobs/detail/SOCIAL/4b326f6b-2c39-461c-ae64-69b4201c680e | sandbox/gateway/observability, runtime governance, recovery, MCP/SDK/Skill interfaces and OTel/Langfuse-class observability in production Agent Infra |

## Native Japanese lane

| ID | Source | Unique/useful contribution |
|---|---|---|
| S-JA-01 | NTT DATA — AIエージェントを“使える戦力”に変えるハーネスエンジニアリング — https://www.nttdata.com/jp/ja/trends/data-insight/2026/0625/ | knowledge/execution/constraint/verification/operations harness separation |
| S-JA-02 | Ubie — セキュリティ分析AIエージェント実装にみるハーネスエンジニアリング — https://zenn.dev/ubie_dev/articles/sec-agent-harness-eng | production harness lessons from a security agent |
| S-JA-03 | 大和総研 — AIという新メンバーを迎える前にすべきこと — https://www.dir.co.jp/report/column/20260618_012440.html | review/quality burden shifts as agent throughput rises |

## German lane

| ID | Source | Unique/useful contribution |
|---|---|---|
| S-DE-01 | Fraunhofer IAO — KI-Agenten verstehen und anwenden — https://www.digital.iao.fraunhofer.de/de/publikationen/KI-Agenten-verstehen-und-anwenden.html | start protected/small, control mechanisms and risk/complexity framing |
| S-DE-02 | Microsoft Techwiese — Sicherheitskontrollen für KI-Agenten: MCP-Erweiterungen — https://www.microsoft.com/de-de/techwiese/news/sicherheitskontrollen-fuer-ki-agenten-mcp-erweiterungen-fuer-net.aspx | startup/runtime MCP governance signal |

## Research saturation conclusion

Additional sources were stopped once they ceased changing the main design choices: single durable agent graph, external deterministic policy, exact approval/effects, layered evals, OTel, local model portability, Postgres/pgvector and static evidence demo.
