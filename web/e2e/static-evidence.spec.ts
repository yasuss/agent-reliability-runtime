import { expect, test } from '@playwright/test';

test('critical static evidence path is complete and backend-free', async ({ page }) => {
  const failed: string[] = [];
  const requests: string[] = [];
  page.on('requestfailed', (request) => failed.push(`${request.url()} ${request.failure()?.errorText ?? ''}`));
  page.on('request', (request) => requests.push(request.url()));
  await page.emulateMedia({ reducedMotion: 'reduce' });

  await page.goto('/#/');
  await expect(page.getByText('Recorded acceptance replay', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Inspect reliability evidence without running the system.' })).toBeVisible();
  await expect(page.getByText('5 curated accepted replays')).toBeVisible();
  await expect(page.locator('input, textarea, form')).toHaveCount(0);

  await page.goto('/#/replays');
  await expect(page.getByRole('heading', { name: 'Evidence gallery' })).toBeVisible();
  await expect(page.locator('.replay-card')).toHaveCount(5);

  await page.goto('/#/replays/approval-side-effect');
  await page.locator('details').evaluateAll((nodes) => nodes.forEach((node) => { node.open = true; }));
  await expect(page.getByText('Human decision').first()).toBeVisible();
  await expect(page.getByText('Trusted policy boundary').first()).toBeVisible();
  await expect(page.getByText('Verified environment').first()).toBeVisible();

  await page.goto('/#/replays/process-restart-exactly-once');
  await page.locator('details').evaluateAll((nodes) => nodes.forEach((node) => { node.open = true; }));
  await expect(page.getByText('recovery.resumed').first()).toBeVisible();
  await expect(page.getByText('replayed=true', { exact: false })).toBeVisible();

  await page.goto('/#/replays/memory-poisoning-blocked');
  await page.locator('details').evaluateAll((nodes) => nodes.forEach((node) => { node.open = true; }));
  await expect(page.getByText('External / untrusted data').first()).toBeVisible();
  await expect(page.getByText('Verified evaluation').first()).toBeVisible();

  expect(failed, failed.join('\\n')).toEqual([]);
  const pageOrigin = new URL(page.url()).origin;
  expect(requests.filter((url) => new URL(url).origin !== pageOrigin), requests.join('\\n')).toEqual([]);
  expect(requests.some((url) => /\/api\/|ollama|localhost:\d{4,5}/i.test(url))).toBe(false);
});
