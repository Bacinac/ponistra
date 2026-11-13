import { expect } from '@playwright/test';
import { shot } from './shot';

shot('text-editor', async (page) => {
  await page.goto('/documents');
  await page
    .locator('tr[data-id]', { hasText: /^(Projekti|Projects)/ })
    .first()
    .dblclick();
  await page
    .locator('tr[data-id]', { hasText: /(Ponuda za uređenje ureda|Office fit-out proposal)/ })
    .dblclick();
  await expect(page.getByRole('toolbar')).toBeVisible();
  await expect(page.getByText(/^(Opseg radova|Scope of work)$/).first()).toBeVisible();
});
