import type { Browser } from '@playwright/test';
import { expect, test } from './fixtures';
import { pageAt, scannedFile, upload } from './helpers/pdf';

/** Pages of text photographed as a scanner would, at 150 dpi. */
async function scan(browser: Browser, pages: string[][]): Promise<Buffer[]> {
  const context = await browser.newContext({
    viewport: { width: 1240, height: 1754 },
    deviceScaleFactor: 1,
  });
  const sheet = await context.newPage();
  const jpegs: Buffer[] = [];
  for (const lines of pages) {
    await sheet.setContent(
      '<body style="margin:150px;font:32px/1.6 serif;color:#000;background:#fff">' +
        lines.map((line) => `<p>${line}</p>`).join('') +
        '</body>',
    );
    jpegs.push(await sheet.screenshot({ type: 'jpeg', quality: 90 }));
  }
  await context.close();
  return jpegs;
}

test('scanned pages are read while the file is open, which then shows the same page with its text', async ({
  page,
  browser,
}) => {
  test.slow();
  const pages = Array.from({ length: 12 }, (_, at) =>
    Array.from({ length: 20 }, (_, line) => `Stranica ${at + 1}, redak ${line + 1}: održavanje`),
  );
  pages[8][3] = 'Rok isporuke je petnaest dana.';
  const scanned = scannedFile(await scan(browser, pages));
  await upload(page, 'Sken', scanned);
  const status = page.getByRole('status');
  await expect(status).toHaveText('Prepoznavanje teksta…', { timeout: 90_000 });
  const at = page.getByRole('textbox', { name: 'Stranica' });
  await at.fill('9');
  await at.press('Enter');

  await expect(status).toHaveText('', { timeout: 60_000 });
  await expect(pageAt(page, 9).locator('.textLayer')).toContainText('Stranica 9, redak 1');
  await expect(at).toHaveValue('9');
  await page.keyboard.press('ControlOrMeta+f');
  await page.getByRole('searchbox', { name: 'Traži u datoteci' }).fill('isporuke');
  await expect(page.getByText('1 od 1')).toBeVisible();

  await page.getByRole('button', { name: 'Sken', exact: true }).click();
  const downloading = page.waitForEvent('download');
  await page.getByRole('menuitem', { name: 'Preuzmi izvornik' }).click();
  const original = await (await downloading).createReadStream();
  expect(Buffer.concat(await original.toArray()).equals(scanned)).toBe(true);
});

test('a signed scan is left unread, and says why', async ({ page, browser }) => {
  test.slow();
  await upload(page, 'Potpisano', scannedFile(await scan(browser, [['Potpisani zapisnik']]), true));
  await expect(page.getByRole('status')).toHaveText(
    'Tekst se ne prepoznaje: datoteka je digitalno potpisana.',
    { timeout: 90_000 },
  );
  await expect(pageAt(page, 1).locator('.textLayer')).toHaveText('');
});
