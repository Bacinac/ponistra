import { expect } from '@playwright/test';
import { shot } from './shot';

shot('mail-list', async (page) => {
  await page.goto('/mail');
  await expect(page.locator('li[data-id]').first()).toBeVisible();
});

shot('mail-reader', async (page) => {
  await page.goto('/mail');
  await page.locator('li[data-id] a').first().click();
  await expect(page.locator('article')).toBeVisible();
});

shot('mail-compose', async (page) => {
  await page.goto('/mail');
  await page.getByRole('button', { name: /^(Nova poruka|New message)$/ }).click();
  return page.getByRole('dialog');
});
