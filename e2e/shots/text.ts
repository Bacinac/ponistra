import { expect } from '@playwright/test';
import { shot } from './shot';

shot('text-editor', async (page) => {
  await page.goto('/documents');
  await page
    .getByRole('row', { name: /\b(Projekti|Projects)\b/ })
    .first()
    .dblclick();
  await page
    .getByRole('row', { name: /(Ponuda za uređenje ureda|Office fit-out proposal)/ })
    .dblclick();
  await expect(page.getByRole('toolbar')).toBeVisible();
  await expect(page.getByText(/^(Opseg radova|Scope of work)$/).first()).toBeVisible();
});
