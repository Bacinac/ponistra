import { createHash } from 'node:crypto';
import { expect, test } from './fixtures';
import { openLocation, removeLocation } from './helpers/locations';

test('Files: a typed address, search by name, properties with a checksum, a bookmark and two panes', async ({
  page,
}) => {
  const stamp = Date.now();
  const name = `Poslužitelj ${stamp}`;
  const folder = `Mapa ${stamp}`;
  const file = `popis ${stamp}.txt`;
  const text = 'Prvi redak';

  const tree = await openLocation(page, name);
  const pane = page.getByRole('region', { name });
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Nova mapa' }).click();
  await page.getByLabel('Naziv').fill(folder);
  await page.getByRole('button', { name: 'Izradi' }).click();
  await pane.getByRole('row').filter({ hasText: folder }).click();
  await expect(pane.getByText('Mapa je prazna.')).toBeVisible();
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (
    await chooser
  ).setFiles([{ name: file, mimeType: 'text/plain', buffer: Buffer.from(text) }]);
  const row = pane.getByRole('row').filter({ hasText: file });
  await expect(row).toBeVisible();

  const address = pane.getByRole('navigation', { name: 'Adresa' });
  await address.getByRole('button', { name: 'Upiši put' }).focus();
  await page.keyboard.press('Enter');
  const typed = pane.getByRole('textbox', { name: 'Adresa' });
  await expect(typed).toHaveValue(`/${folder}`);
  await typed.fill('/');
  await typed.press('Enter');
  const made = pane.getByRole('row').filter({ hasText: folder });
  await expect(made).toBeVisible();

  const search = pane.getByRole('searchbox', { name: 'Traži po imenu' });
  await search.fill(`popis ${stamp}`);
  await expect(pane.getByRole('status')).toHaveText('Pronađeno: 1');
  await pane.getByRole('button', { name: file }).click();
  await expect(page.locator('.cm-content')).toContainText(text);
  await page.getByRole('button', { name: 'Natrag na popis datoteka' }).click();
  await expect(row).toBeVisible();

  await row.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Svojstva' }).click();
  const properties = page.getByRole('dialog', { name: file });
  await expect(properties.getByText('Prava', { exact: true })).toBeVisible();
  await properties.getByRole('button', { name: 'Izračunaj SHA-256' }).click();
  await expect(properties.locator('code')).toHaveText(
    createHash('sha256').update(text).digest('hex'),
  );
  await page.keyboard.press('Escape');
  await expect(properties).toBeHidden();

  await address.getByRole('button', { name }).click();
  await made.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Dodaj u oznake' }).click();
  await tree
    .getByRole('link', { name: 'Oznake' })
    .locator('..')
    .getByRole('button', { name: 'Proširi' })
    .click();
  await expect(tree.getByRole('link', { name: folder })).toHaveCount(2);
  const bookmark = tree.getByRole('link', { name: folder }).first();
  await bookmark.click();
  await expect(row).toBeVisible();

  await page.getByRole('button', { name: 'Dva panela' }).click();
  await expect(page.getByRole('region', { name })).toHaveCount(2);
  await expect(page.getByRole('region', { name }).nth(1).getByRole('row')).toHaveCount(2);
  await page.getByRole('button', { name: 'Dva panela' }).click();
  await expect(page.getByRole('region', { name })).toHaveCount(1);

  await bookmark.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Ukloni iz oznaka' }).click();
  await expect(tree.getByRole('link', { name: folder })).toHaveCount(1);
  await removeLocation(page, name);
});
