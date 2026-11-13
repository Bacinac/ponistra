import { expect, test } from './fixtures';

test('the code workspace is closed to everyone but its owner, signed out or not', async ({
  page,
  browser,
  baseURL,
}) => {
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: 'Moduli' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Projekti' })).toHaveCount(0);
  await page.goto('/code/');
  await expect(page).toHaveURL(/\/$/);

  const stranger = await browser.newContext({ baseURL });
  const outside = await stranger.newPage();
  await outside.goto('/code/');
  await expect(outside).toHaveURL(/\/$/);
  await stranger.close();
});
