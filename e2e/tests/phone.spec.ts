import { expect, test } from './fixtures';

const ANDROID =
  'Mozilla/5.0 (Linux; Android 16; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36';

test('a computer shows the code a phone scans, and sees the phone take it', async ({ page }) => {
  await page.goto('/settings/app-passwords');
  await expect(page.getByRole('heading', { name: 'Android aplikacija' })).toBeVisible();
  const made = page.waitForResponse('**/api/device/pairing');
  await page.getByRole('button', { name: 'Poveži telefon' }).click();
  const { code } = await (await made).json();
  const dialog = page.getByRole('dialog', { name: 'Poveži telefon' });
  await expect(dialog.getByRole('img', { name: 'Kod za povezivanje telefona' })).toBeVisible();
  await expect(dialog.getByRole('link')).toHaveCount(0);

  const claimed = await page.request.post('/api/device/claim', { data: { code } });
  expect(claimed.status()).toBe(201);
  await expect(dialog).toContainText('Telefon je povezan: Android');
  const again = await page.request.post('/api/device/claim', { data: { code } });
  expect(await again.json()).toEqual({ error: 'invalid_code' });
});

test.describe('on an Android phone', () => {
  test.use({ userAgent: ANDROID });

  test('the phone downloads the app and opens it with the code', async ({ page, baseURL }) => {
    await page.goto('/settings/app-passwords');
    const made = page.waitForResponse('**/api/device/pairing');
    await page.getByRole('button', { name: 'Poveži telefon' }).click();
    const { id, code } = await (await made).json();
    const dialog = page.getByRole('dialog', { name: 'Poveži telefon' });
    await expect(
      dialog.getByRole('link', { name: 'Preuzmi aplikaciju (v0.1.14, 2,1 MB)' }),
    ).toHaveAttribute('href', '/android/ponistra.apk');
    const link = await dialog.getByRole('link', { name: 'Otvori aplikaciju' }).getAttribute('href');
    const [address, intent] = link!.split('#Intent;');
    const query = new URL(address.replace('intent://', 'ponistra://')).searchParams;
    expect([query.get('origin'), query.get('code')]).toEqual([new URL(baseURL!).origin, code]);
    expect(intent.split(';')).toEqual([
      'scheme=ponistra',
      'package=biz.boskovic.ponistra',
      `S.browser_fallback_url=${encodeURIComponent(`${new URL(baseURL!).origin}/connect#${encodeURIComponent(code)}`)}`,
      'end',
    ]);

    const removed = page.waitForRequest(
      (request) =>
        request.method() === 'DELETE' && request.url().endsWith(`/api/app-passwords/${id}`),
    );
    await dialog.getByRole('button', { name: 'Zatvori' }).click();
    await removed;
  });

  test('a scanned code opens the app before any sign-in', async ({ browser, baseURL }) => {
    const context = await browser.newContext({ baseURL, userAgent: ANDROID });
    const page = await context.newPage();
    await page.goto('/connect#12%3A1tC5Xh%3Asig');
    await expect(page.getByRole('heading', { name: 'Android aplikacija' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Otvori aplikaciju' })).toHaveAttribute(
      'href',
      /^intent:\/\/connect\?origin=.+&code=12%3A1tC5Xh%3Asig#Intent;/,
    );
    await context.close();
  });
});

test('a computer that opens a scanned code is sent to an Android phone', async ({ page }) => {
  await page.goto('/connect#12%3A1tC5Xh%3Asig');
  await expect(
    page.getByText('Aplikacija postoji samo za Android.', { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole('link', { name: 'Otvori aplikaciju' })).toHaveCount(0);
});
