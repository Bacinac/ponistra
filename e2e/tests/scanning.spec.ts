import type { Browser } from '@playwright/test';
import { expect, test } from './fixtures';
import { pageAt } from './helpers/pdf';

/** A sheet of text photographed askew on a dark desk. */
async function photographed(browser: Browser, lines: string[]): Promise<Buffer> {
  const context = await browser.newContext({
    viewport: { width: 1200, height: 1600 },
    deviceScaleFactor: 1,
  });
  const desk = await context.newPage();
  await desk.setContent(
    '<body style="margin:0;height:1600px;background:#2b2622;display:grid;place-items:center">' +
      '<div style="width:840px;height:1188px;padding:90px;box-sizing:border-box;' +
      'background:linear-gradient(90deg,#c9c6bf,#f4f2ee);transform:rotate(-6deg);' +
      'font:30px/1.6 serif;color:#111">' +
      lines.map((line) => `<p>${line}</p>`).join('') +
      '</div></body>',
  );
  const photo = await desk.screenshot({ type: 'jpeg', quality: 90 });
  await context.close();
  return photo;
}

test('pages photographed are outlined, straightened and kept as one PDF with their text', async ({
  page,
  browser,
}) => {
  test.slow();
  const photo = await photographed(browser, [
    'Zapisnik o primopredaji',
    'Rok isporuke je petnaest dana.',
  ]);
  await page.goto('/documents');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Skeniraj…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Skeniranje' });
  for (let taken = 0; taken < 2; taken++) {
    const chooser = page.waitForEvent('filechooser');
    await dialog.getByRole('button', { name: 'Dodaj fotografije…' }).click();
    await (await chooser).setFiles({ name: 'stranica.jpg', mimeType: 'image/jpeg', buffer: photo });
    await expect(dialog.getByRole('button', { name: 'Gornji lijevi kut' })).toBeVisible();
  }
  await expect(dialog.getByRole('list', { name: 'Stranice' }).getByRole('listitem')).toHaveCount(2);

  const corner = dialog.getByRole('button', { name: 'Donji desni kut' });
  const before = await corner.boundingBox();
  await corner.press('ArrowLeft');
  await expect.poll(async () => (await corner.boundingBox())?.x).toBeLessThan(before!.x);

  await dialog.getByRole('textbox', { name: 'Naziv' }).fill('Primopredaja');
  await dialog.getByRole('button', { name: 'Spremi PDF' }).click();
  await expect(page).toHaveURL(/\/p\//, { timeout: 120_000 });
  await expect(pageAt(page, 2)).toBeAttached();
  await expect(pageAt(page, 1).locator('.textLayer')).toContainText('petnaest', {
    timeout: 60_000,
  });
});
