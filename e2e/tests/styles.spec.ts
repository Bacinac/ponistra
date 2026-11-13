import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';

test('the theme and styles dialog restyles the document for everyone', async ({
  page,
  context,
}) => {
  const url = await newDocument(page, 'Probni stilovi');
  await page.goto(url);
  const editor = page.locator('.ProseMirror');
  await editor.click();
  await page.keyboard.type('Uvod u ponudu');
  const first = editor.locator('p').first();
  await expect(first).toHaveCSS('font-family', /^"?Inter"?,/);

  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Tema i stilovi…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Tema i stilovi' });
  await dialog.getByLabel('Font teksta', { exact: true }).selectOption('IBM Plex Serif');
  await dialog.getByRole('button', { name: 'Novi stil' }).click();
  await dialog.getByLabel('Naziv').fill('Napomena');
  await dialog.getByRole('checkbox', { name: 'Kurziv' }).check();
  await expect(dialog.locator('figure [data-style]')).toHaveCSS('font-style', 'italic');
  await dialog.getByRole('button', { name: 'Primijeni' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(first).toHaveCSS('font-family', /^"?IBM Plex Serif"?,/);
  expect(await page.evaluate(() => document.fonts.load('16px "IBM Plex Serif"'))).toHaveLength(1);

  await editor.click();
  await page.getByLabel('Stil odlomka').selectOption({ label: 'Napomena' });
  await expect(editor.locator('p[data-style]')).toHaveCSS('font-style', 'italic');

  const other = await context.newPage();
  await other.goto(url);
  const theirs = other.locator('.ProseMirror p[data-style]');
  await expect(theirs).toContainText('Uvod u ponudu');
  await expect(theirs).toHaveCSS('font-style', 'italic');
  await expect(theirs).toHaveCSS('font-family', /^"?IBM Plex Serif"?,/);
});
