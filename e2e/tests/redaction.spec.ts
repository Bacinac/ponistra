import type { Locator, Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { pageAt, pdfFile, upload } from './helpers/pdf';

const contract = () =>
  pdfFile({
    pages: [
      [
        { text: 'Ugovor o djelu', top: 100 },
        { text: 'Izvodi Ana Horvat, OIB 12345678901.', top: 140 },
        { text: 'Narucitelj placa Ani Horvat tisucu eura.', top: 180 },
      ],
      [{ text: 'Potpis: Ana Horvat', top: 100 }],
    ],
  });

/** Drags from point to point, each relative to the words, which are scrolled into view first. */
async function drag(page: Page, from: Locator, [[x, y], [toX, toY]]: [number, number][]) {
  await from.scrollIntoViewIfNeeded();
  const box = (await from.boundingBox())!;
  await page.mouse.move(box.x + x, box.y + y);
  await page.mouse.down();
  await page.mouse.move(box.x + toX, box.y + toY, { steps: 5 });
  await page.mouse.up();
}

test('what is marked by selection, by a rectangle and by every match is taken out of a new copy', async ({
  page,
}) => {
  await upload(page, 'Ugovor', contract());
  const first = pageAt(page, 1);
  const second = pageAt(page, 2);
  const marks = (on: Locator | Page) => on.getByRole('button', { name: 'Oznaka za zacrnjivanje' });
  await expect(first.locator('.textLayer')).toContainText('Izvodi Ana Horvat');

  const line = first.locator('.textLayer span', { hasText: 'Izvodi Ana' });
  await line.scrollIntoViewIfNeeded();
  await line.selectText();
  const chosen = page.getByRole('toolbar', { name: 'Odabrani tekst' });
  await chosen.getByRole('button', { name: 'Zacrni' }).click();
  await expect(marks(first)).toHaveCount(1);
  await expect(chosen).toHaveCount(0);

  await page.getByRole('button', { name: 'Zacrni', exact: true }).click();
  const tool = page.getByRole('toolbar', { name: 'Zacrnjivanje' });
  const heading = first.locator('.textLayer span', { hasText: 'Ugovor o djelu' });
  await heading.scrollIntoViewIfNeeded();
  const { width, height } = (await heading.boundingBox())!;
  await drag(page, heading, [
    [-4, -4],
    [width + 4, height + 4],
  ]);
  await expect(marks(first)).toHaveCount(2);
  await page.keyboard.press('Control+z');
  await expect(marks(first)).toHaveCount(1);
  await page.keyboard.press('Control+Shift+z');
  await expect(marks(first)).toHaveCount(2);
  await tool.getByRole('button', { name: 'Završi' }).click();
  await expect(tool).toHaveCount(0);

  await page.getByRole('button', { name: 'Traži u datoteci' }).click();
  await page.getByRole('searchbox', { name: 'Traži u datoteci' }).fill('HORVAT');
  await expect(page.getByRole('search')).toContainText('1 od 3');
  await page.getByRole('button', { name: 'Zacrni sve pogotke' }).click();
  await expect(page.getByRole('alert')).toHaveText(/Označeno za zacrnjivanje: 3/);
  await expect(marks(first)).toHaveCount(4);
  await expect(marks(second)).toHaveCount(1);
  await page.getByRole('button', { name: 'Zatvori pretragu' }).click();

  await marks(second).click();
  await page
    .getByRole('toolbar', { name: 'Oznaka za zacrnjivanje' })
    .getByRole('button', { name: 'Ukloni' })
    .click();
  await expect(marks(second)).toHaveCount(0);
  await page.keyboard.press('Control+z');
  await expect(marks(second)).toHaveCount(1);

  await page.getByRole('button', { name: 'Zacrni', exact: true }).click();
  await tool.getByRole('button', { name: 'Spremi zacrnjenu kopiju…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Spremi zacrnjenu kopiju' });
  await expect(dialog.getByRole('textbox', { name: 'Naziv' })).toHaveValue('Ugovor (zacrnjeno)');
  await expect(dialog).toContainText('Izvornik i oznake ostaju kakvi jesu.');
  await dialog.getByRole('button', { name: 'Izradi' }).click();

  await expect(page).toHaveTitle('Ugovor (zacrnjeno) – Ponistra');
  await expect(first.locator('.textLayer')).toContainText('Narucitelj placa Ani');
  await expect(second.locator('.textLayer')).toContainText('Potpis:');
  for (const each of [first, second]) {
    await expect(each.locator('.textLayer')).not.toContainText('Horvat');
  }
  await expect(first.locator('.textLayer')).not.toContainText('Ugovor o djelu');
  await expect(first.locator('.textLayer')).not.toContainText('12345678901');
  await expect(marks(page)).toHaveCount(0);

  await page.goBack();
  await expect(page).toHaveTitle('Ugovor – Ponistra');
  await expect(marks(first)).toHaveCount(4);
  await expect(first.locator('.textLayer')).toContainText('Izvodi Ana Horvat');
});

test('a file locked by its password says why it cannot be blacked out', async ({ page }) => {
  await upload(
    page,
    'Zaključani ugovor',
    pdfFile({ pages: [[{ text: 'Povjerljivo', top: 100 }]], password: 'tajna' }),
  );
  const dialog = page.getByRole('dialog', { name: 'Datoteka je zaštićena lozinkom' });
  await dialog.getByLabel('Lozinka').fill('tajna');
  await dialog.getByRole('button', { name: 'Otvori' }).click();
  await expect(pageAt(page, 1).locator('.textLayer')).toContainText('Povjerljivo');
  const tool = page.getByRole('button', { name: 'Zacrni', exact: true });
  await expect(tool).toBeDisabled();
  await expect(tool).toHaveAttribute(
    'title',
    'Datoteka je zaštićena lozinkom, pa se ne može zacrniti.',
  );
});
