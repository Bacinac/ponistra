import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';

test('an address names what it opens, is read by its id and follows a rename', async ({ page }) => {
  const address = await newDocument(page, 'Ugovor o najmu');
  expect(address).toMatch(/^\/d\/ugovor-o-najmu-[0-9A-Za-z]{22}$/);
  const id = address.slice(-22);

  await page.goto(`/d/stari-naziv-${id}`);
  await expect(page).toHaveURL(address);
  await expect(page).toHaveTitle('Ugovor o najmu – Ponistra');

  await page.getByRole('button', { name: 'Nova kartica' }).click();
  await expect(page).toHaveURL(new RegExp(`${address}/[0-9A-Za-z]{22}$`));
  const tabs = page.getByRole('navigation', { name: 'Kartice' });
  await tabs.getByRole('link').last().click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Preimenuj' }).click();
  await page.getByRole('dialog').getByLabel('Naziv').fill('Prilog A');
  await page.getByRole('dialog').getByRole('button', { name: 'Spremi' }).click();
  await expect(page).toHaveURL(new RegExp(`${address}/prilog-a-[0-9A-Za-z]{22}$`));

  // The live change brings the new name before the rename's own answer.
  await page.route(/\/api\/nodes\/[^/]+$/, async (route) => {
    if (route.request().method() !== 'PATCH') return route.fallback();
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, 2000));
    await route.fulfill({ response });
  });
  const crumbs = page.getByRole('navigation', { name: 'Putanja' });
  await crumbs.getByRole('button', { name: 'Ugovor o najmu' }).click();
  await page.getByRole('menuitem', { name: 'Preimenuj' }).click();
  await page.getByRole('dialog').getByLabel('Naziv').fill('Ugovor o zakupu');
  await page.getByRole('dialog').getByRole('button', { name: 'Spremi' }).click();
  const renamed = `/d/ugovor-o-zakupu-${id}`;
  await expect(page).toHaveURL(new RegExp(`${renamed}/prilog-a-[0-9A-Za-z]{22}$`));
  await expect(page).toHaveTitle('Ugovor o zakupu – Ponistra');

  await tabs.getByRole('link', { name: 'Kartica bez naziva' }).click();
  await expect(page).toHaveURL(renamed);

  for (const wrong of [`/d/${id.slice(1)}`, `/d/${'x'.repeat(22)}`]) {
    await page.goto(wrong);
    await expect(page.getByText('Ova stavka ne postoji ili je u smeću.')).toBeVisible();
  }
});
