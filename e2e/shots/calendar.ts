import { expect } from '@playwright/test';
import { shot } from './shot';

shot('calendar-month', async (page) => {
  await page.goto('/calendar/month');
  await expect(
    page.getByTitle(/^(Tjedni sastanak tima|Weekly team meeting)$/).first(),
  ).toBeVisible();
});
