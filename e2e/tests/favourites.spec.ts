import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';

test('a document kept at hand is found on its own page and on the day', async ({ page }) => {
  const title = `Omiljeni ugovor ${Date.now()}`;
  const address = await newDocument(page, title);
  await page.goto(address);
  await page.getByRole('button', { name: 'Dodaj u omiljeno' }).click();
  await expect(page.getByRole('button', { name: 'Ukloni iz omiljenog' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  await page.goto('/favourites');
  const row = page.getByRole('row').filter({ hasText: title });
  await expect(row).toBeVisible();
  await expect(row.getByRole('img', { name: 'Omiljeno' })).toBeVisible();

  await page.goto('/');
  await expect(page.getByRole('region', { name: 'Omiljeno' })).toContainText(title);

  await page.goto('/favourites');
  await row.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Ukloni iz omiljenog' }).click();
  await expect(row).toBeHidden();
  await expect(page.getByText('U omiljenom još nema ničega.')).toBeVisible();
});
