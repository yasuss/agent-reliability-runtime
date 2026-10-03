import { renderToStaticMarkup } from 'react-dom/server';
import { expect, test } from 'vitest';
import { App } from './App';

test('shell labels its foundation status and offers no prompt input', () => {
  const html = renderToStaticMarkup(<App />);
  expect(html).toContain('Repository foundation');
  expect(html).toContain('No agent execution or acceptance replays');
  expect(html).not.toMatch(/<(input|textarea|form)\b/);
});
