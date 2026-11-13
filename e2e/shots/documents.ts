import { expect, type Page } from '@playwright/test';
import { shot } from './shot';

async function projects(page: Page): Promise<void> {
  await page.goto('/documents');
  await page
    .locator('tr[data-id]', { hasText: /^(Projekti|Projects)/ })
    .first()
    .dblclick();
  await expect(page.locator('tr[data-id]', { hasText: /(Arhiva|Archive)/ })).toBeVisible();
}

shot('documents-folder', async (page) => {
  await projects(page);
  const preview = page.getByRole('button', { name: /^(Pregled|Preview)$/ });
  if ((await preview.getAttribute('aria-pressed')) !== 'true') await preview.click();
  await page
    .locator('tr[data-id]', { hasText: /(Ponuda za uređenje ureda|Office fit-out proposal)/ })
    .click();
  await expect(page.getByText(/^(Opseg radova|Scope of work)$/).first()).toBeVisible();
});
