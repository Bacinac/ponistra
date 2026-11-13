import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';
import { cellTexts, insertTable, tab } from './helpers/tables';

test('a tab is searched in its text and cells, and replaced at once as one change', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Probno traženje'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Čaj i čajnik.');
  await page.keyboard.press('Enter');
  await insertTable(page, '2 × 2');
  await page.keyboard.type('čaj');
  await tab(page, 'B1');
  await page.keyboard.type('kava');
  const table = page.locator('.ponistra-table');

  await page.keyboard.press('Control+f');
  const sought = page.getByRole('searchbox', { name: 'Pronađi' });
  await expect(sought).toBeFocused();
  await sought.fill('čaj');
  const bar = page.getByRole('search');
  await expect(bar).toContainText('/ 3');
  await expect(editor.locator('.ponistra-hit')).toHaveCount(2);
  await page.getByRole('button', { name: 'Samo cijele riječi' }).click();
  await expect(bar).toContainText('2 / 2');
  await page.getByRole('button', { name: 'Samo cijele riječi' }).click();
  await expect(bar).toContainText('/ 3');

  await page.getByRole('button', { name: 'Zamjena' }).click();
  await page.getByRole('textbox', { name: 'Zamijeni s' }).fill('chai');
  await page.getByRole('button', { name: 'Zamijeni sve' }).click();
  await expect(editor.locator('p').first()).toHaveText('chai i chainik.');
  await expect.poll(() => cellTexts(table)).toEqual(['chai', 'kava', '', '']);
  await expect(bar).toContainText('Nema rezultata');

  await page.keyboard.press('Escape');
  await expect(bar).toHaveCount(0);
  await page.keyboard.press('Control+z');
  await expect(editor.locator('p').first()).toHaveText('Čaj i čajnik.');
  await expect.poll(() => cellTexts(table)).toEqual(['čaj', 'kava', '', '']);
});
