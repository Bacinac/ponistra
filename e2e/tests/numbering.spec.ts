import { expect, test } from './fixtures';
import { addTabs, newDocument } from './helpers/nodes';

test('headings number by the styles, on through the tabs, and start again where asked', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  const address = await newDocument(page, 'Ugovor s brojevima');
  await addTabs(page, address, ['Prilozi']);
  await page.goto(address);
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('# Uvod');
  await page.keyboard.press('Enter');
  await page.keyboard.type('## Cilj');
  await page.keyboard.press('Enter');
  await page.keyboard.type('# Cijene');
  const prices = editor.locator('h1').nth(1);
  await expect(prices).toHaveText('Cijene');
  await expect(editor.locator('[data-number]')).toHaveCount(0);

  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Tema i stilovi…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Tema i stilovi' });
  await dialog.getByRole('checkbox', { name: 'Numeriraj naslove (1., 1.1., 1.1.1.)' }).check();
  await dialog.getByRole('button', { name: 'Naslov 2' }).click();
  await expect(dialog.getByLabel('Brojevi', { exact: true })).toHaveValue('1');
  await expect(dialog.getByRole('checkbox', { name: /S brojevima viših naslova/ })).toBeChecked();
  await expect(dialog.locator('figure [data-number]')).toHaveAttribute('data-number', '1.1.');
  await dialog.getByRole('button', { name: 'Primijeni' }).click();
  await expect(dialog).toHaveCount(0);

  await expect(editor.locator('h1').first()).toHaveAttribute('data-number', '1.');
  await expect(editor.locator('h2')).toHaveAttribute('data-number', '1.1.');
  await expect(prices).toHaveAttribute('data-number', '2.');
  await expect(prices).toHaveText('Cijene');
  const tabs = page.getByRole('navigation', { name: 'Kartice' });
  await expect(tabs.getByRole('list', { name: 'Naslovi' }).getByRole('link')).toHaveText([
    '1. Uvod',
    '1.1. Cilj',
    '2. Cijene',
  ]);

  await prices.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Počni brojati od 1' }).click();
  await expect(prices).toHaveAttribute('data-number', '1.');
  await prices.click({ button: 'right' });
  await expect(page.getByRole('menuitem', { name: 'Počni brojati od 1' })).toHaveCount(0);
  await page.getByRole('menuitem', { name: 'Nastavi brojanje' }).click();
  await expect(prices).toHaveAttribute('data-number', '2.');

  await page.keyboard.press('Control+a');
  await prices.click({ button: 'right' });
  await page.getByRole('menuitem', { name: /^Kopiraj(?! poveznicu)/ }).click();
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe('1. Uvod\n\n1.1. Cilj\n\n2. Cijene');

  await tabs.getByRole('link', { name: 'Prilozi' }).click();
  const appendix = page.locator('.ProseMirror').first();
  await expect(appendix).not.toContainText('Uvod');
  await appendix.click();
  await page.keyboard.type('# Troškovnik');
  await expect(appendix.locator('h1')).toHaveAttribute('data-number', '3.');
});
