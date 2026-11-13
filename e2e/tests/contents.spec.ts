import { expect, test } from './fixtures';
import { addTabs, newDocument } from './helpers/nodes';

test('the contents list the headings of every tab and lead to them', async ({ page }) => {
  const address = await newDocument(page, 'Ugovor sa sadržajem');
  await addTabs(page, address, ['Prilozi']);
  await page.goto(address);
  const tabs = page.getByRole('navigation', { name: 'Kartice' });
  await tabs.getByRole('link', { name: 'Prilozi' }).click();
  const editor = page.locator('.ProseMirror').first();
  await expect(page).toHaveURL(/\/prilozi-/);
  await editor.click();
  await page.keyboard.type('# Troškovnik');
  await expect(tabs.getByRole('list', { name: 'Naslovi' })).toHaveText('Troškovnik');

  await page.goto(address);
  await expect(editor).not.toContainText('Troškovnik');
  await editor.click();
  await page.getByRole('button', { name: 'Umetni' }).click();
  await page.getByRole('menuitem', { name: 'Sadržaj', exact: true }).click();
  const contents = editor.getByRole('navigation', { name: 'Sadržaj' });
  await expect(contents.getByRole('link')).toHaveText(['Troškovnik']);
  await expect(editor).toBeFocused();
  await page.keyboard.type('# Uvod');
  await page.keyboard.press('Enter');
  await page.keyboard.type('## Cilj');
  await page.keyboard.press('Enter');
  for (let line = 0; line < 40; line++) await page.keyboard.press('Enter');
  await page.keyboard.type('# Cijene');
  await expect(contents.getByRole('link')).toHaveText(['Uvod', 'Cilj', 'Cijene', 'Troškovnik']);

  const prices = editor.locator('h1', { hasText: 'Cijene' });
  await contents.scrollIntoViewIfNeeded();
  await contents.getByRole('link', { name: 'Cijene' }).click();
  await expect(page).not.toHaveURL(/block=/);
  await contents.getByRole('link', { name: 'Cijene' }).click({ modifiers: ['ControlOrMeta'] });
  await expect(page).toHaveURL(/block=/);
  await expect(prices).toBeInViewport();

  await contents.getByRole('link', { name: 'Troškovnik' }).click({ modifiers: ['ControlOrMeta'] });
  await expect(page).toHaveURL(/\/prilozi-.*block=/);
  await expect(editor).not.toContainText('Uvod');
  await expect(editor.locator('h1')).toHaveText('Troškovnik');
});
