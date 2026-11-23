import { expect, type Page } from '@playwright/test';

/** The check stack's SFTP server added as a location, opened in Files through the tree. */
export async function openLocation(page: Page, name: string) {
  await page.goto('/settings/locations');
  await page.getByRole('button', { name: 'Dodaj lokaciju' }).click();
  await page.getByLabel('Vrsta').selectOption('sftp');
  await page.getByRole('textbox', { name: 'Naziv' }).fill(name);
  await page.getByRole('textbox', { name: 'Poslužitelj', exact: true }).fill('sftp');
  await page.getByRole('textbox', { name: 'Mapa' }).fill('files');
  await page.getByRole('textbox', { name: 'Korisničko ime' }).fill('sftp');
  await page.getByLabel('Lozinka', { exact: true }).fill('sftpsftp');
  await page.getByRole('button', { name: 'Spremi' }).click();
  await expect(page.getByRole('link', { name })).toBeVisible();
  await page.goto('/files');
  const tree = page.getByRole('navigation', { name: 'Mape' }).filter({ visible: true });
  await tree
    .getByRole('link', { name: 'Mreža' })
    .locator('..')
    .getByRole('button', { name: 'Proširi' })
    .click();
  await tree.getByRole('link', { name }).click();
  await expect(page).toHaveURL(/\/files\/location%3A[0-9a-f-]{36}$/);
  return tree;
}

export async function removeLocation(page: Page, name: string) {
  await page.goto('/settings/locations');
  const kept = page.getByRole('listitem').filter({ hasText: name });
  await kept.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Ukloni lokaciju' }).click();
  await page.getByRole('alertdialog').getByRole('button', { name: 'Ukloni lokaciju' }).click();
  await expect(kept).toBeHidden();
}
