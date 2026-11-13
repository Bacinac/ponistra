import { expect, test } from './fixtures';

test('the app is installable: a manifest with its icons, and a service worker at the root', async ({
  page,
  request,
}) => {
  const manifest = await request.get('/manifest.webmanifest');
  expect(manifest.headers()['content-type']).toContain('application/manifest+json');
  const given = (await manifest.json()) as {
    id: string;
    display: string;
    start_url: string;
    icons: { src: string; purpose: string }[];
  };
  expect([given.id, given.display, given.start_url]).toEqual(['/', 'standalone', '/']);
  expect(given.icons.map((icon) => icon.purpose)).toEqual(['any', 'any', 'maskable']);
  for (const icon of given.icons) {
    expect(icon.src).toMatch(/^\/[\w-]+\.png\?[0-9a-f]{12}$/);
    const fetched = await request.get(icon.src);
    expect(fetched.ok(), icon.src).toBe(true);
    expect(fetched.headers()['content-type']).toBe('image/png');
  }
  const english = (await (await request.get('/manifest.en.webmanifest')).json()) as {
    lang: string;
    shortcuts: { name: string }[];
  };
  expect([english.lang, english.shortcuts[0].name]).toEqual(['en', 'New note']);
  const worker = await request.get('/sw.js');
  expect(worker.headers()['content-type']).toContain('javascript');

  await page.goto('/');
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
    'href',
    '/manifest.webmanifest',
  );
  const scope = await page.evaluate(async () => (await navigator.serviceWorker.ready).scope);
  expect(scope).toBe(`${new URL(page.url()).origin}/`);
});
