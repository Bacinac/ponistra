import { expect, test } from './fixtures';

test('a note is made in one move, named by its first line and kept at hand', async ({ page }) => {
  const first = `Kupiti papir ${Date.now()}`;
  await page.goto('/notes');
  await page.getByRole('button', { name: 'Nova bilješka' }).click();
  await expect(page).toHaveURL(/\/d\//);
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type(first);
  await page.keyboard.press('Enter');
  await page.keyboard.type('za pisač u uredu');

  await page
    .getByRole('navigation', { name: 'Moduli' })
    .getByRole('link', { name: 'Dokumenti' })
    .click();
  await page
    .getByRole('navigation', { name: 'Mape' })
    .getByRole('link', { name: 'Bilješke' })
    .click();
  await expect(page).toHaveURL(/\/notes$/);
  const cards = page.getByRole('list', { name: 'Bilješke' }).getByRole('listitem');
  const card = cards.filter({ hasText: first });
  await expect(async () => {
    await page.reload();
    await expect(card.getByRole('link', { name: first })).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 60_000 });
  await expect(card).toContainText('za pisač u uredu');

  await card.getByRole('button', { name: 'Dodaj u omiljeno' }).click();
  await expect(card.getByRole('button', { name: 'Ukloni iz omiljenog' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(cards.first()).toContainText(first);
  await card.getByRole('button', { name: 'Ukloni iz omiljenog' }).click();
  await expect(card.getByRole('button', { name: 'Dodaj u omiljeno' })).toBeVisible();

  await card.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Premjesti u smeće' }).click();
  await expect(card).toHaveCount(0);
  await page.goto('/trash');
  await expect(page.getByText(first)).toBeVisible();
});

test('Alt+N makes a note from any page', async ({ page }) => {
  await page.goto('/documents');
  await expect(page.getByRole('link', { name: 'Moji dokumenti' }).first()).toBeVisible();
  await page.keyboard.press('Alt+KeyN');
  await expect(page).toHaveURL(/\/d\//);
  await expect(page.locator('.ProseMirror').first()).toBeVisible();
});
