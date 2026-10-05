import { useEffect, useMemo, useState } from 'react';

type ReplayEvent = { seq: number; type: string; summary: string; data?: Record<string, unknown> };
type Replay = { scenario_id: string; source_git_sha: string; final_status: string; events: ReplayEvent[] };
type Receipt = { gates: Record<string, string> };
type Entry = { slug: string; scenario_id: string; replay_sha256: string; receipt_sha256: string; source_git_sha: string };
type Manifest = { accepted_source_git_sha: string; entries: Entry[] };

const repository = 'https://github.com/yasuss/agent-reliability-runtime';
const trustLabels: Record<string, string> = {
  request: 'External request',
  'retrieval.completed': 'External / untrusted data',
  'memory.read': 'External / untrusted data',
  'model.completed': 'Model-produced',
  'action.validated': 'Trusted policy boundary',
  'policy.evaluated': 'Trusted policy boundary',
  'approval.waiting': 'Human decision',
  'approval.resumed': 'Human decision',
  'tool.completed': 'Verified environment',
  'recovery.resumed': 'Trusted recovery',
  'run.finalized': 'Trusted runtime',
  'eval.acceptance': 'Verified evaluation',
};
const titles: Record<string, string> = {
  'grounded-read': 'Grounded read',
  'approval-side-effect': 'Approval-bound side effect',
  'prompt-injection-blocked': 'Prompt-injection attempt blocked',
  'process-restart-exactly-once': 'Process restart and exactly-once effect',
  'memory-poisoning-blocked': 'Poisoned memory ignored for authorization',
};

function route(): string[] {
  if (typeof window === 'undefined') return [];
  const value = window.location.hash.replace(/^#\/?/, '');
  return value ? value.split('/') : [];
}
function pretty(value: unknown): string { return JSON.stringify(value, null, 2); }

function Header() {
  return <header className="site-header"><a className="wordmark" href="#/">Agent Reliability Runtime</a><nav aria-label="Primary navigation"><a href="#/">Overview</a><a href="#/replays">Evidence gallery</a></nav></header>;
}
function TruthLabel() {
  return <aside className="truth-label" aria-label="Evidence mode"><strong>Recorded acceptance replay</strong><span>Static evidence only. No live inference occurs in this browser.</span></aside>;
}
function Loading({ message = 'Loading recorded evidence…' }: { message?: string }) { return <p role="status" className="status">{message}</p>; }

export function Landing({ manifest }: { manifest: Manifest | null }) {
  const count = manifest?.entries.length ?? 0;
  const source = manifest?.accepted_source_git_sha.slice(0, 12) ?? '…';
  const sourceRef = manifest?.accepted_source_git_sha ?? '';
  const docBase = `${repository}/blob/${sourceRef}`;
  return <><section className="hero"><p className="eyebrow">Static Evidence Demo</p><h1>Inspect reliability evidence without running the system.</h1><p className="lede">A recorded, integrity-checked view of correctness, durability, safety, observability and evaluation boundaries in a local-first agent runtime.</p><div className="hero-actions"><a className="button" href="#/replays">Explore evidence</a><a className="quiet-link" href={repository}>View source repository</a></div></section><section className="section-grid" aria-labelledby="architecture-heading"><div><p className="eyebrow">Architecture</p><h2 id="architecture-heading">One inspectable path from request to evidence</h2><ol className="architecture"><li><span>01</span><strong>External request</strong><small>Untrusted input enters the runtime.</small></li><li><span>02</span><strong>Policy and approval</strong><small>Trusted boundaries gate side effects.</small></li><li><span>03</span><strong>Durable execution</strong><small>PostgreSQL-backed recovery preserves exactly-once effects.</small></li><li><span>04</span><strong>Evaluation receipt</strong><small>Hard invariants bind the accepted result.</small></li></ol></div><aside className="summary-card" aria-labelledby="summary-heading"><p className="eyebrow">Evidence summary</p><h2 id="summary-heading">{count} curated accepted replays</h2><dl><div><dt>Source SHA</dt><dd><code>{source}</code></dd></div><div><dt>Backend dependency</dt><dd>None</dd></div><div><dt>Inference</dt><dd>Recorded only</dd></div></dl></aside></section><section className="section-grid links-grid" aria-labelledby="methods-heading"><div><p className="eyebrow">Read the project</p><h2 id="methods-heading">Technical context</h2></div><div className="doc-links"><a href={`${docBase}/docs/project/spec/v1.0/02_ARCHITECTURE.md`}>Architecture contract <span>↗</span></a><a href={`${docBase}/docs/project/spec/v1.0/05_SECURITY_AND_TRUST.md`}>Threat model <span>↗</span></a><a href={`${docBase}/docs/project/B90_EVAL_HARNESS.md`}>Evaluation methodology <span>↗</span></a></div></section></>;
}
function Gallery({ entries }: { entries: Entry[] }) { return <section aria-labelledby="gallery-heading"><div className="section-heading"><div><p className="eyebrow">Curated collection</p><h1 id="gallery-heading">Evidence gallery</h1></div><p className="section-note">Five accepted stories, each preserved as replay and receipt bytes.</p></div><div className="gallery">{entries.map((entry, index) => <a className="replay-card" href={`#/replays/${entry.slug}`} key={entry.slug}><span className="card-number">0{index + 1}</span><h2>{titles[entry.slug] ?? entry.scenario_id}</h2><p>{entry.scenario_id.replaceAll('_', ' ').toLowerCase()}</p><span className="card-link">Open detail →</span></a>)}</div></section>; }
function EventTimeline({ events }: { events: ReplayEvent[] }) { return <ol className="timeline">{events.map((event) => <li key={`${event.seq}-${event.type}`}><div className="timeline-marker" aria-hidden="true">{String(event.seq).padStart(2, '0')}</div><details><summary><span className="event-type">{event.type}</span><span className="event-summary">{event.summary}</span><span className="trust-chip">{trustLabels[event.type] ?? 'Recorded runtime event'}</span></summary><div className="event-meta">{event.data && <pre>{pretty(event.data)}</pre>}</div></details></li>)}</ol>; }
function Detail({ entry, replay, receipt }: { entry: Entry; replay: Replay; receipt: Receipt }) { const replayed = replay.events.some((event) => event.type === 'tool.completed' && event.data?.replayed === true); return <section aria-labelledby="detail-heading"><a className="back-link" href="#/replays">← Back to gallery</a><div className="detail-heading"><div><p className="eyebrow">{entry.scenario_id}</p><h1 id="detail-heading">{titles[entry.slug] ?? entry.scenario_id}</h1></div><span className="verdict">Accepted · {replay.final_status}</span></div><div className="detail-grid"><article className="panel"><h2>Recorded run timeline</h2><p className="panel-intro">Each step is a bounded projection of the accepted replay. Expand a step to inspect its sanitized data.</p>{replayed && <p className="proof-callout"><strong>replayed=true</strong> · exactly-once receipt evidence</p>}<EventTimeline events={replay.events} /></article><aside className="panel receipt-panel"><h2>Acceptance receipt</h2><p>Replay bytes are bound to the accepted source and verified gates.</p><dl><div><dt>Source</dt><dd><code>{replay.source_git_sha.slice(0, 12)}</code></dd></div>{Object.entries(receipt.gates).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd className={value === 'PASS' ? 'pass' : ''}>{value}</dd></div>)}</dl><p className="safe-note">Model summaries are shown without hidden reasoning. External retrieval and memory remain explicitly untrusted.</p></aside></div></section>; }

export function App() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [replays, setReplays] = useState<Record<string, { replay: Replay; receipt: Receipt }>>({});
  const [currentRoute, setCurrentRoute] = useState(route);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { fetch('/replays/index.json').then((response) => { if (!response.ok) throw new Error('Manifest unavailable'); return response.json() as Promise<Manifest>; }).then(setManifest).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'Evidence unavailable')); }, []);
  useEffect(() => { const onHash = () => setCurrentRoute(route()); window.addEventListener('hashchange', onHash); return () => window.removeEventListener('hashchange', onHash); }, []);
  const slug = currentRoute[0] === 'replays' ? currentRoute[1] : undefined;
  useEffect(() => { const entry = manifest?.entries.find((item) => item.slug === slug); if (!entry || replays[entry.slug]) return; Promise.all([fetch(`/replays/${entry.slug}/replay.json`).then((response) => response.json() as Promise<Replay>), fetch(`/replays/${entry.slug}/receipt.json`).then((response) => response.json() as Promise<Receipt>)]).then(([replay, receipt]) => setReplays((current) => ({ ...current, [entry.slug]: { replay, receipt } }))).catch(() => setError('Replay unavailable')); }, [manifest, slug, replays]);
  const content = useMemo(() => { if (error) return <p role="alert" className="status error">{error}</p>; if (!manifest) return <Loading />; if (currentRoute[0] !== 'replays') return <Landing manifest={manifest} />; if (!slug) return <Gallery entries={manifest.entries} />; const entry = manifest.entries.find((item) => item.slug === slug); const loaded = entry && replays[entry.slug]; if (!entry) return <p role="alert" className="status error">Replay not found.</p>; if (!loaded) return <Loading message="Loading replay detail…" />; return <Detail entry={entry} replay={loaded.replay} receipt={loaded.receipt} />; }, [currentRoute, error, manifest, replays, slug]);
  return <><Header /><main><TruthLabel />{content}</main><footer><span>Static Evidence Demo · Recorded acceptance replay</span><a href={repository}>Source ↗</a></footer></>;
}
