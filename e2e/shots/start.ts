import { expect } from '@playwright/test';
import { shot } from './shot';

shot('start-frame', async (page) => {
  await page.goto('/');
  await expect(page.getByRole('combobox').first()).toBeVisible();
});

shot('start-search', async (page) => {
  await page.goto('/');
  await page.getByRole('combobox').first().fill('Marija');
  await expect(page.getByRole('option').first()).toBeVisible();
});
