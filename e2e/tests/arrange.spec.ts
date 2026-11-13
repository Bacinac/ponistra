import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { pageAt, pdfFile, upload } from './helpers/pdf';

const made = (...texts: string[]) => pdfFile({ pages: texts.map((text) => [{ text, top: 72 }]) });

const TURNED = '2, okrenuta za 90°';

const sheets = (page: Page) =>
  page.getByRole('listbox', { name: 'Stranice datoteke' }).getByRole('option');

async function shape(page: Page, number: number): Promise<'portrait' | 'landscape'> {
  const box = (await pageAt(page, number).boundingBox())!;
  return box.width > box.height ? 'landscape' : 'portrait';
}

test('pages are turned, removed and reordered, kept only once saved as a new file', async ({
  page,
}) => {
  await upload(page, 'Raspored', made('Jedan', 'Dva', 'Tri'));
  await expect(pageAt(page, 1).locator('.textLayer')).toContainText('Jedan');
  await page.getByRole('button', { name: 'Stranice', exact: true }).click();
  await expect(sheets(page)).toHaveText(['1', '2', '3']);

  await sheets(page).nth(1).click();
  await page.getByRole('button', { name: 'Okreni udesno' }).click();
  await sheets(page).nth(2).click();
  await page.keyboard.press('Delete');
  await expect(sheets(page)).toHaveText(['1', TURNED]);
  await sheets(page)
    .nth(1)
    .dragTo(sheets(page).nth(0), { targetPosition: { x: 4, y: 40 } });
  await expect(sheets(page)).toHaveText([TURNED, '1']);
  await page.keyboard.press('ControlOrMeta+z');
  await expect(sheets(page)).toHaveText(['1', TURNED]);
  await page.keyboard.press('ControlOrMeta+Shift+z');
  await expect(sheets(page)).toHaveText([TURNED, '1']);
  await expect(sheets(page).nth(0)).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('Alt+ArrowRight');
  await expect(sheets(page)).toHaveText(['1', TURNED]);
  await page.keyboard.press('Alt+ArrowLeft');
  await expect(sheets(page)).toHaveText([TURNED, '1']);

  await page.getByRole('button', { name: 'Stranice', exact: true }).click();
  const leave = page.getByRole('alertdialog', { name: 'Odbaciti promjene stranica?' });
  await leave.getByRole('button', { name: 'Odustani' }).click();
  await expect(sheets(page)).toHaveText([TURNED, '1']);

  await page.getByRole('button', { name: 'Spremi kao novu datoteku…' }).click();
  const named = page.getByRole('dialog', { name: 'Spremi kao novu datoteku' });
  await expect(named.getByLabel('Naziv')).toHaveValue('Kopija – Raspored');
  await named.getByLabel('Naziv').fill('Preslagano');
  await named.getByRole('button', { name: 'Izradi' }).click();

  await expect(page.getByRole('navigation', { name: 'Putanja' })).toContainText('Preslagano');
  await expect(page.getByText('od 2')).toBeVisible();
  await expect(pageAt(page, 1).locator('.textLayer')).toContainText('Dva');
  await expect(pageAt(page, 2).locator('.textLayer')).toContainText('Jedan');
  expect(await shape(page, 1)).toBe('landscape');
  expect(await shape(page, 2)).toBe('portrait');

  await page.goto('/documents');
  await expect(page.getByRole('row', { name: /Raspored/ })).toHaveCount(1);
  await expect(page.getByRole('row', { name: /Preslagano/ })).toHaveCount(1);
});

test('pages of another file are taken in and the chosen ones extracted', async ({ page }) => {
  await upload(page, 'Dodatak', made('Cetiri', 'Pet'));
  await upload(page, 'Osnova', made('Jedan', 'Dva'));
  await page.getByRole('button', { name: 'Stranice', exact: true }).click();
  await expect(sheets(page)).toHaveText(['1', '2']);

  await sheets(page).nth(0).click();
  await page.getByRole('button', { name: 'Dodaj stranice' }).click();
  await page.getByRole('menuitem', { name: 'Iz Ponistre…' }).click();
  await page
    .getByRole('dialog', { name: 'Dodaj stranice iz datoteke' })
    .getByText('Dodatak')
    .click();
  await expect(sheets(page)).toHaveText(['Osnova · 1', 'Dodatak · 1', 'Dodatak · 2', 'Osnova · 2']);
  await expect(page.getByText('Odabrano: 2 od 4')).toBeVisible();

  await page.getByRole('button', { name: 'Izdvoji odabrane…' }).click();
  const named = page.getByRole('dialog', { name: 'Izdvoji odabrane stranice' });
  await expect(named.getByLabel('Naziv')).toHaveValue('Kopija – Osnova');
  await named.getByLabel('Naziv').fill('Izdvojeno');
  await named.getByRole('button', { name: 'Izradi' }).click();

  await expect(page.getByRole('navigation', { name: 'Putanja' })).toContainText('Izdvojeno');
  await expect(page.getByText('od 2')).toBeVisible();
  await expect(pageAt(page, 1).locator('.textLayer')).toContainText('Cetiri');
  await expect(pageAt(page, 2).locator('.textLayer')).toContainText('Pet');
});

test('files chosen in a folder are joined into one, in the order set', async ({ page }) => {
  await upload(page, 'Prvi dio', made('Prva'));
  await upload(page, 'Drugi dio', made('Druga'));
  await page.goto('/documents');
  await page.getByRole('row', { name: /Prvi dio/ }).click({ modifiers: ['ControlOrMeta'] });
  await page.getByRole('row', { name: /Drugi dio/ }).click({ modifiers: ['ControlOrMeta'] });
  await page.getByRole('button', { name: 'Spoji u jednu datoteku…' }).click();

  const join = page.getByRole('dialog', { name: 'Spoji u jednu datoteku' });
  const order = join.getByRole('listitem');
  await expect(order).toHaveText([/^Drugi dio/, /^Prvi dio/]);
  await join.getByRole('button', { name: 'Pomakni dolje: Drugi dio' }).click();
  await expect(order).toHaveText([/^Prvi dio/, /^Drugi dio/]);
  await join.getByLabel('Naziv').fill('Cjelina');
  await join.getByRole('button', { name: 'Spoji', exact: true }).click();

  await expect(page.getByRole('navigation', { name: 'Putanja' })).toContainText('Cjelina');
  await expect(page.getByText('od 2')).toBeVisible();
  await expect(pageAt(page, 1).locator('.textLayer')).toContainText('Prva');
  await expect(pageAt(page, 2).locator('.textLayer')).toContainText('Druga');
});

test('a file locked by a password keeps its pages as they are', async ({ page }) => {
  await upload(page, 'Tajno', pdfFile({ pages: [[{ text: 'Jedan', top: 72 }]], password: 'x' }));
  await page
    .getByRole('dialog', { name: 'Datoteka je zaštićena lozinkom' })
    .getByRole('button', { name: 'Odustani' })
    .click();
  const arrange = page.getByRole('button', { name: 'Stranice', exact: true });
  await expect(arrange).toBeDisabled();
  await expect(arrange).toHaveAttribute('title', /zaštićena lozinkom/);
});
