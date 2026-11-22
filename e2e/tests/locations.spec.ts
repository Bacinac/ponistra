import { expect, test } from './fixtures';

test('a location on the network is set up, browsed, changed and copied from', async ({ page }) => {
  const stamp = Date.now();
  const name = `Arhiva ${stamp}`;
  const folder = `Ponude ${stamp}`;
  const file = `zapis ${stamp}`;

  await page.goto('/settings/locations');
  await page.getByRole('button', { name: 'Dodaj lokaciju' }).click();
  await page.getByLabel('Vrsta').selectOption('sftp');
  await page.getByRole('textbox', { name: 'Naziv' }).fill(name);
  await page.getByRole('textbox', { name: 'Poslužitelj', exact: true }).fill('sftp');
  await page.getByRole('textbox', { name: 'Mapa' }).fill('files');
  await page.getByRole('textbox', { name: 'Korisničko ime' }).fill('sftp');
  await page.getByLabel('Lozinka', { exact: true }).fill('sftpsftp');
  await page.getByRole('button', { name: 'Spremi' }).click();
  await page.getByRole('link', { name }).click();
  await expect(page).toHaveURL(/\/locations\/[0-9a-f-]{36}$/);

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
  await page.getByRole('menuitem', { name: 'Kopiraj u Ponistru…' }).click();
  await page.getByRole('button', { name: 'Kopiraj ovamo' }).click();
  await page.goto('/documents');
  await expect(page.getByRole('row').filter({ hasText: file })).toBeVisible();

  await page.goBack();
  await page.getByRole('button', { name, exact: true }).click();
  const made = page.getByRole('row').filter({ hasText: folder });
  await made.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Obriši' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Obriši' }).click();
  await expect(made).toBeHidden();

  await page.goto('/settings/locations');
  const kept = page.getByRole('listitem').filter({ hasText: name });
  await kept.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Ukloni lokaciju' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Ukloni lokaciju' }).click();
  await expect(kept).toBeHidden();
});
