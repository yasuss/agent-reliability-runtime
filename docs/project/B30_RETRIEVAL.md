# B30 retrieval

Run `uv run python -m agent_reliability_runtime.cli ingest SOURCE_PATH...` with
normalized repository-relative paths. For the complete corpus in PowerShell:

```powershell
$sources = Get-ChildItem data/knowledge -File | ForEach-Object {
    "data/knowledge/$($_.Name)"
}
uv run python -m agent_reliability_runtime.cli ingest $sources
```

The database must already be migrated. The developer command uses the existing
local Ollama adapter and does not provision models.

Ingestion accepts strict UTF-8 `.md`/`.txt`, normalizes newlines before SHA-256,
and reuses B10's path/version/ordinal identities. Markdown ATX heading sections
are split independently. Sections over 1200 characters repeat their heading,
prefer newline then space breaks in the final quarter, and overlap body text by
150 characters. Short sections have no overlap. H1 supplies the title; plain text
and Markdown without H1 use the filename stem with hyphens/underscores replaced.
Full embeddings are validated before a transaction begins. Per-source advisory
locks serialize writes; failed inference or failed persistence preserves the
previous version. An unchanged complete version is a no-op; pre-B30 null-vector
rows are re-embedded without changing their identity.

Migration `0003_retrieval` adds nullable `VECTOR(1024)`, generated stored English
`tsvector`, and a GIN text index. It invokes no provider. Downgrade removes only
these retrieval columns/index; the B10 domain tables remain. No ANN index exists.
The official [pgvector Python adapter](https://github.com/pgvector/pgvector-python)
provides SQLAlchemy binding/cosine operators. The preflight against server 0.8.6
confirmed that 0.5.0 requires list input and delegates SQL dimension checking to
PostgreSQL; project code validates finite, nonzero float32 vectors before binding.

Retrieval embeds a query once, reads both lanes and evidence in one PostgreSQL
repeatable-read snapshot, and joins chunks to the current document digest.
Lexical top 20 uses
[PostgreSQL websearch and rank](https://www.postgresql.org/docs/18/textsearch-controls.html);
vector top 20 uses exact cosine. Both break ties by chunk ID ascending. Python
RRF uses one-based ranks and k=60; the final six sort by score descending then
chunk ID. Evidence snapshots carry source identity, title, text, digest and lane
ranks. Their text is untrusted data. The pure citation validator admits only IDs
from the exact supplied retrieval result, including rejecting other existing DB
IDs. No generation, tool, policy, agent or memory behavior is added.

For live acceptance, create a unique disposable Compose project/volume, migrate,
and run from a clean exact candidate:

```text
uv run python scripts/probe_retrieval.py --output ABSOLUTE_EXTERNAL_EVIDENCE_PATH.json
```

The probe requires the accepted local `qwen3-embedding:0.6b` artifact digest and
1024 dimensions. It retains exact SHA, corpus/fixture/result digests, every query's
ranked evidence, unchanged re-ingestion, changed-digest rehearsal, and checker
calibration. Corpus digest is SHA-256 of sorted compact JSON mapping source paths
to normalized-content SHA-256. Result digest hashes the same canonical JSON
encoding of the payload excluding its own digest field. Recall@6 >=0.90 and
citation validity 100% are gates; hit@1 and MRR are diagnostics. Temporary
distractors give >6 distinct sources: arbitrary top-six fails, a valid alternate
ranking passes, stale snapshots and non-retrieved citations fail. Deliberate stale
DB reinsertion also fails the existing exact-version FK without disabling it.
Tests/CI use deterministic providers and real PostgreSQL; live model evidence is
separate. Delete only the disposable project volume after retaining proof.
