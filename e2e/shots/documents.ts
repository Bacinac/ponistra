import { expect, type Page } from '@playwright/test';
import { shot } from './shot';

async function projects(page: Page): Promise<void> {
  await page.goto('/documents');
  await page
    .getByRole('row', { name: /\b(Projekti|Projects)\b/ })
    .first()
    .dblclick();
  await expect(page.getByRole('row', { name: /(Arhiva|Archive)/ })).toBeVisible();
}

shot('documents-folder', async (page) => {
  await projects(page);
  const preview = page.getByRole('button', { name: /^(Pregled|Preview)$/ });
  if ((await preview.getAttribute('aria-pressed')) !== 'true') await preview.click();
  await page
    .getByRole('row', { name: /(Ponuda za uređenje ureda|Office fit-out proposal)/ })
    .click();
  await expect(page.getByText(/^(Opseg radova|Scope of work)$/).first()).toBeVisible();
});
