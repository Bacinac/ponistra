import { expect } from '@playwright/test';
import { shot } from './shot';

shot('tables-table', async (page) => {
  await page.goto('/documents');
  await page
    .getByRole('row', { name: /\b(Projekti|Projects)\b/ })
    .first()
    .dblclick();
  await page.getByRole('row', { name: /(Proračun ureda|Office budget)/ }).dblclick();
  const cell = page.getByText(/^(Namještaj|Furniture)$/).first();
  await expect(cell).toBeVisible();
  await cell.click();
  await expect(page.getByRole('textbox', { name: /^(Polje imena|Name box)$/ })).toBeVisible();
});
