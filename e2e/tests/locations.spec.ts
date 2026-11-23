import { expect, test } from './fixtures';
import { openLocation, removeLocation } from './helpers/locations';

test('a location on the network is set up, browsed in Files, changed and copied from', async ({
  page,
}) => {
  const stamp = Date.now();
  const name = `Arhiva ${stamp}`;
  const folder = `Ponude ${stamp}`;
  const file = `zapis ${stamp}`;

  const tree = await openLocation(page, name);
  const location = page.url();

  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Nova mapa' }).click();
  await page.getByLabel('Naziv').fill(folder);
  await page.getByRole('button', { name: 'Izradi' }).click();
  await page.getByRole('row').filter({ hasText: folder }).click();
  await expect(page.getByText('Mapa je prazna.')).toBeVisible();

  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (
    await chooser
  ).setFiles([{ name: `${file}.txt`, mimeType: 'text/plain', buffer: Buffer.from('Prvi redak') }]);
  const row = page.getByRole('row').filter({ hasText: `${file}.txt` });
  await expect(row).toContainText('TXT datoteka');

  await row.click();
  const text = page.locator('.cm-content');
  await expect(text).toContainText('Prvi redak');
  await text.click();
  await page.keyboard.press('Control+End');
  await page.keyboard.type(' i drugi');
  await page.keyboard.press('Control+s');
  await expect(page.getByText('Spremljeno')).toBeVisible();
  await page.getByRole('button', { name: 'Natrag na popis datoteka' }).click();
  await expect(row).toContainText('18 B');

  await row.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Kopiraj', exact: true }).click();
  await tree.getByRole('link', { name: 'Moji dokumenti' }).click();
  const mine = page.getByRole('region', { name: 'Moji dokumenti' });
  const box = (await mine.boundingBox())!;
  await mine.click({ button: 'right', position: { x: box.width / 2, y: box.height - 8 } });
  await page.getByRole('menuitem', { name: 'Zalijepi', exact: true }).click();
  await expect(mine.getByRole('row').filter({ hasText: file })).toBeVisible();
  await page.goto('/documents');
  await expect(page.getByRole('row').filter({ hasText: file })).toBeVisible();

  await page.goto(location);
  const made = page.getByRole('row').filter({ hasText: folder });
  await made.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Obriši' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Obriši' }).click();
  await expect(made).toBeHidden();

  await removeLocation(page, name);
});
