import { expect, test } from './fixtures';

test('what another tab changes shows at once where it is already open', async ({
  page,
  context,
}) => {
  const name = `Vesna Daljinska ${Date.now()}`;
  const elsewhere = await context.newPage();

  await page.goto('/contacts');
  await elsewhere.goto('/contacts');
  await elsewhere.getByRole('button', { name: 'Novi kontakt' }).click();
  const made = elsewhere.getByRole('dialog', { name: 'Novi kontakt' });
  await made.getByLabel('Ime', { exact: true }).fill('Vesna');
  await made.getByLabel('Prezime', { exact: true }).fill(name.slice('Vesna '.length));
  await made.getByRole('button', { name: 'Spremi' }).click();
  const row = page.getByRole('link', { name: new RegExp(name) });
  await expect(row).toBeVisible();

  const card = elsewhere.getByRole('article', { name });
  await card.getByRole('button', { name: 'Dodaj u omiljene' }).click();
  await expect(row.getByRole('img', { name: 'Omiljeni kontakt' })).toBeVisible();
  await card.getByRole('button', { name: 'Radnje' }).click();
  await elsewhere.getByRole('menuitem', { name: 'Izbriši kontakt' }).click();
  await elsewhere
    .getByRole('alertdialog', { name: 'Izbrisati kontakt?' })
    .getByRole('button', { name: 'Izbriši kontakt' })
    .click();
  await expect(row).toHaveCount(0);

  await page.goto('/documents');
  await elsewhere.goto('/documents');
  await elsewhere.getByRole('button', { name: 'Novo' }).click();
  await elsewhere.getByRole('menuitem', { name: 'Nova mapa' }).click();
  const folder = elsewhere.getByRole('dialog', { name: 'Nova mapa' });
  await folder.getByLabel('Naziv', { exact: true }).fill(name);
  await folder.getByRole('button', { name: 'Izradi' }).click();
  await expect(page.getByRole('row', { name: new RegExp(name) })).toBeVisible();
  await elsewhere.close();
});
