import type { Locator, Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { pageAt, pdfFile, upload } from './helpers/pdf';

const lease = () =>
  pdfFile({
    pages: [
      [
        { text: 'Ugovor o najmu prostora', top: 100 },
        { text: 'Cijena najma je tisucu eura mjesecno.', top: 140 },
      ],
      [{ text: 'Potpis najmoprimca', top: 100 }],
    ],
  });

async function select(page: Page, words: Locator): Promise<void> {
  await words.scrollIntoViewIfNeeded();
  await words.selectText();
  await expect(page.getByRole('toolbar', { name: 'Odabrani tekst' })).toBeVisible();
}

/** Drags from point to point, each relative to the words, which are scrolled into view first. */
async function drag(page: Page, from: Locator, points: [number, number][]): Promise<void> {
  await from.scrollIntoViewIfNeeded();
  const box = (await from.boundingBox())!;
  const [[x, y], ...rest] = points;
  await page.mouse.move(box.x + x, box.y + y);
  await page.mouse.down();
  for (const [toX, toY] of rest) await page.mouse.move(box.x + toX, box.y + toY, { steps: 5 });
  await page.mouse.up();
}

test('a file takes highlights, drawings and comments beside it, live, and gives them in its copy', async ({
  page,
  context,
}) => {
  await upload(page, 'Najam s bilješkama', lease());
  const first = pageAt(page, 1);
  const second = pageAt(page, 2);
  const panel = page.getByRole('complementary', { name: 'Komentari' });
  await expect(first.locator('.textLayer')).toContainText('Cijena najma');

  await select(page, first.locator('.textLayer span', { hasText: 'Cijena najma' }));
  await page.getByRole('button', { name: 'Istakni: Zelena' }).click();
  const highlight = first.getByRole('button', { name: 'Isticanje' });
  await expect(highlight).toHaveCount(1);
  await expect(page.getByRole('toolbar', { name: 'Odabrani tekst' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Crtaj' }).click();
  const pen = page.getByRole('toolbar', { name: 'Olovka' });
  await pen.getByRole('button', { name: 'Plava' }).click();
  await pen.getByRole('button', { name: 'Debelo' }).click();
  const signature = second.locator('.textLayer span', { hasText: 'Potpis' });
  await drag(page, signature, [
    [0, 40],
    [60, 70],
    [120, 40],
  ]);
  const drawing = second.locator('[data-mark]');
  await expect(drawing).toHaveCount(1);
  await page.keyboard.press('Control+z');
  await expect(drawing).toHaveCount(0);
  await page.keyboard.press('Control+Shift+z');
  await expect(drawing).toHaveCount(1);
  await pen.getByRole('button', { name: 'Završi' }).click();
  await expect(pen).toHaveCount(0);

  await select(page, first.locator('.textLayer span', { hasText: 'Ugovor o najmu' }));
  await page
    .getByRole('toolbar', { name: 'Odabrani tekst' })
    .getByRole('button', { name: 'Komentiraj' })
    .click();
  await expect(panel.getByRole('region', { name: 'Novi komentar' })).toContainText(
    'Ugovor o najmu prostora',
  );
  await page.keyboard.type('Je li prostor opremljen?');
  await page.keyboard.press('Control+Enter');
  await expect(panel.getByRole('article', { name: 'Ugovor o najmu prostora' })).toContainText(
    'Je li prostor opremljen?',
  );
  await expect(first.locator('[data-thread]')).toHaveCount(1);

  await page.getByRole('button', { name: 'Komentar na stranici' }).click();
  await expect(page.getByText('Kliknite mjesto na stranici')).toBeVisible();
  await signature.scrollIntoViewIfNeeded();
  const signed = (await signature.boundingBox())!;
  await page.mouse.click(signed.x + signed.width + 40, signed.y);
  await expect(panel.getByRole('region', { name: 'Novi komentar' })).toContainText('Stranica 2');
  await page.keyboard.type('Potpisati i ovjeriti.');
  await page.keyboard.press('Control+Enter');
  await expect(panel.getByRole('article', { name: 'Stranica 2' })).toContainText(
    'Potpisati i ovjeriti.',
  );
  await expect(second.getByRole('button', { name: 'Prikaži komentar' })).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'Komentari 2' })).toBeVisible();

  const other = await context.newPage();
  await other.goto(page.url());
  await expect(pageAt(other, 1).getByRole('button', { name: 'Isticanje' })).toHaveCount(1);
  await expect(pageAt(other, 2).locator('[data-mark]')).toHaveCount(1);
  await pageAt(other, 1).getByRole('button', { name: 'Isticanje' }).click();
  await other.getByRole('toolbar', { name: 'Odabrana bilješka' }).getByText('Ukloni').click();
  await expect(highlight).toHaveCount(0);
  await other.keyboard.press('Control+z');
  await expect(highlight).toHaveCount(1);

  await page.bringToFront();
  const downloading = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Preuzmi', exact: true }).click();
  const noted = await (await downloading).createReadStream();
  const bytes = Buffer.concat(await noted.toArray()).toString('latin1');
  for (const subtype of ['/Highlight', '/Ink', '/Text']) expect(bytes).toContain(subtype);
  expect(bytes).toContain('Je li prostor opremljen?');

  await page.getByRole('button', { name: 'Najam s bilješkama', exact: true }).click();
  await expect(page.getByRole('menuitem', { name: 'Otvori zasebno' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: 'Preuzmi izvornik' })).toBeVisible();
});
