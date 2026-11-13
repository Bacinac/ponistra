import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';

test('notes are written beside their marks, numbered across tabs and found', async ({ page }) => {
  await page.goto(await newDocument(page, 'Probne bilješke'));
  const editor = page.locator('.ProseMirror').first();
  const marks = page.locator('sup.ponistra-note');
  const insert = async (name: string) => {
    await page.getByRole('button', { name: 'Umetni' }).click();
    await page.getByRole('menuitem', { name, exact: true }).click();
  };

  await editor.click();
  await page.keyboard.type('Rok plaćanja ');
  await insert('Fusnota');
  const first = page.getByRole('textbox', { name: 'Fusnota 1' });
  await expect(first).toBeFocused();
  await page.keyboard.type('trideset dana od isporuke');
  await page.getByRole('button', { name: 'Fusnota 1' }).click();
  await expect(editor).toBeFocused();
  await page.keyboard.type('i cijena');
  await insert('Završna bilješka');
  await page.keyboard.type('Izvor: cjenik');
  await page.keyboard.press('Escape');
  await expect(editor).toBeFocused();
  await page.keyboard.type(' vrijede.');

  await expect(editor.locator('p')).toHaveText('Rok plaćanja i cijena vrijede.');
  await expect(marks.first()).toHaveAttribute('data-marker', '1');
  expect(await marks.first().evaluate((mark) => mark.previousSibling?.textContent)).toBe(
    'Rok plaćanja',
  );
  await expect(marks.last()).toHaveAttribute('data-marker', 'i');
  await expect(page.getByRole('region', { name: 'Fusnote' })).toHaveText(
    '1trideset dana od isporuke',
  );
  await expect(page.getByRole('region', { name: 'Završne bilješke' })).toHaveText('iIzvor: cjenik');

  await marks.first().click();
  await expect(first).toBeFocused();
  await page.keyboard.type(' u gotovini');
  await expect(first).toHaveText('trideset dana od isporuke u gotovini');

  await page.getByRole('button', { name: 'Nova kartica' }).click();
  await expect(editor).not.toContainText('Rok plaćanja');
  await editor.click();
  await page.keyboard.type('Jamstvo');
  await insert('Fusnota');
  await expect(page.getByRole('textbox', { name: 'Fusnota 2' })).toBeFocused();
  await page.keyboard.type('dvije godine');
  await page.getByRole('button', { name: 'Bilješka' }).click();
  await page
    .getByRole('menuitem', { name: 'Brojevi bilježaka u ovoj kartici počinju od 1' })
    .click();
  await expect(marks).toHaveAttribute('data-marker', '1');
  await page.getByRole('textbox', { name: 'Fusnota 1' }).click();
  await page.getByRole('button', { name: 'Bilješka' }).click();
  await page
    .getByRole('menuitem', { name: 'Brojevi bilježaka nastavljaju se iz prethodnih kartica' })
    .click();
  await expect(marks).toHaveAttribute('data-marker', '2');

  await expect
    .poll(
      async () => {
        const response = await page.request.get('/api/search?q=gotovini');
        return (await response.json()).documents.length;
      },
      { timeout: 20_000 },
    )
    .toBe(1);
  await page.goto('/');
  await page.getByRole('combobox', { name: 'Pretraži' }).fill('gotovini');
  const hit = page.getByRole('option', { name: /Probne bilješke/ });
  await expect(hit).toContainText('Fusnota');
  await hit.click();
  const found = page.locator('.ponistra-notes li.ponistra-found');
  await expect(found).toContainText('trideset dana od isporuke u gotovini');
  await expect(found).toBeInViewport();
});
