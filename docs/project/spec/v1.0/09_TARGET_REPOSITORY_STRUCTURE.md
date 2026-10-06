# 09 — Target Repository Structure

The final repository should converge on this structure. Equivalent moves are allowed only when they preserve the same contracts and improve project-native ergonomics.

```text
agent-reliability-runtime/
├─ AGENTS.md
├─ README.md
├─ LICENSE
├─ SECURITY.md
├─ CONTRIBUTING.md
├─ pyproject.toml
├─ uv.lock
├─ compose.yaml
├─ .env.example
├─ .gitignore
├─ alembic.ini
├─ migrations/
├─ src/agent_reliability_runtime/
│  ├─ api/
│  ├─ cli.py
│  ├─ graph/
│  ├─ contracts/
│  ├─ providers/
│  ├─ retrieval/
│  ├─ mcp/
│  ├─ policy/
│  ├─ memory/
│  ├─ persistence/
│  ├─ observability/
│  ├─ audit/
│  └─ demo_state/
├─ mcp_server/
│  └─ opsdesk/
├─ data/
│  ├─ knowledge/
│  └─ seed/
├─ evals/
│  ├─ scenarios/
│  ├─ retrieval/
│  ├─ expected/
│  └─ runner/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ e2e/
│  ├─ security/
│  └─ meta/
├─ web/
│  ├─ package.json
│  ├─ package-lock.json
│  ├─ src/
│  └─ public/replays/
├─ artifacts/
│  ├─ accepted-replays/
│  └─ acceptance-receipts/
├─ scripts/
│  ├─ bootstrap.py
│  ├─ verify.py
│  ├─ reset_demo.py
│  └─ export_replays.py
├─ docs/project/
│  ├─ README.md
│  ├─ PRODUCT.md
│  ├─ ARCHITECTURE.md
│  ├─ DEVELOPMENT.md
│  ├─ VERIFICATION.md
│  ├─ SECURITY.md
│  ├─ EVALS.md
│  ├─ DEMO.md
│  └─ decisions/
└─ .github/workflows/
   ├─ ci.yml
   └─ demo-build.yml
```

## Toolchain

- Python 3.12
- `uv` for Python dependency locking/execution
- Node.js 24 LTS for the web app
- npm with committed lockfile for the web app
- Docker Compose for PostgreSQL/pgvector and optional local observability sink
- GitHub Actions

Do not introduce a monorepo orchestrator, task runner or package manager solely for aesthetics.

## Repo-native truth

`AGENTS.md` stays short and navigational. Detailed durable contracts live in `docs/project/`. Architecture decisions that materially differ from this specification require an ADR with evidence and contract impact.
