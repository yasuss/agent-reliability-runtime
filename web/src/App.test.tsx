import { renderToStaticMarkup } from 'react-dom/server';
import { expect, test } from 'vitest';
import { App, Landing } from './App';

test('Static Evidence Demo is recorded-only and has no prompt input', () => {
  const html = renderToStaticMarkup(<App />);
  expect(html).toContain('Recorded acceptance replay');
  expect(html).toContain('Static Evidence Demo');
  expect(html).toContain('No live inference occurs');
  expect(html).not.toMatch(/<(input|textarea|form)\b/);
});


test('Landing binds technical documentation links to the accepted source SHA', () => {
  const html = renderToStaticMarkup(<Landing manifest={{ accepted_source_git_sha: '83514ebad336dbd6faf1b790c597ec8037be0874', entries: [] }} />);
  expect(html).toContain('https://github.com/yasuss/agent-reliability-runtime/blob/83514ebad336dbd6faf1b790c597ec8037be0874/docs/project/spec/v1.0/02_ARCHITECTURE.md');
  expect(html).toContain('https://github.com/yasuss/agent-reliability-runtime/blob/83514ebad336dbd6faf1b790c597ec8037be0874/docs/project/spec/v1.0/05_SECURITY_AND_TRUST.md');
  expect(html).toContain('https://github.com/yasuss/agent-reliability-runtime/blob/83514ebad336dbd6faf1b790c597ec8037be0874/docs/project/B90_EVAL_HARNESS.md');
  expect(html).not.toContain('/blob/main/');
  expect(html).toContain('Backend dependency');
});
