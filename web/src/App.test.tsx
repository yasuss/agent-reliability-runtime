import { renderToStaticMarkup } from 'react-dom/server';
import { expect, test } from 'vitest';
import { App } from './App';

test('Static Evidence Demo is recorded-only and has no prompt input', () => {
  const html = renderToStaticMarkup(<App />);
  expect(html).toContain('Recorded acceptance replay');
  expect(html).toContain('Static Evidence Demo');
  expect(html).toContain('No live inference occurs');
  expect(html).not.toMatch(/<(input|textarea|form)\b/);
});
