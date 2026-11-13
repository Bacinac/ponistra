import { expect } from '@playwright/test';
import { shot } from './shot';

shot('tables-table', async (page) => {
  await page.goto('/documents');
  await page
    .locator('tr[data-id]', { hasText: /^(Projekti|Projects)/ })
    .first()
    .dblclick();
  await page.locator('tr[data-id]', { hasText: /(Proračun ureda|Office budget)/ }).dblclick();
  const cell = page.getByText(/^(Namještaj|Furniture)$/).first();
  await expect(cell).toBeVisible();
  await cell.click();
  await expect(page.getByRole('textbox', { name: /^(Polje imena|Name box)$/ })).toBeVisible();
});
