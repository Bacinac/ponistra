import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

test.use({
  permissions: ['camera', 'microphone'],
  launchOptions: {
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
  },
});

async function meetingNow(page: Page): Promise<Page> {
  await page.goto('/');
  await page
    .getByRole('navigation', { name: 'Moduli' })
    .getByRole('link', { name: 'Razgovori' })
    .click();
  const [meeting] = await Promise.all([
    page.waitForEvent('popup'),
    page.getByRole('button', { name: 'Sastanak sada' }).click(),
  ]);
  return meeting;
}

test('a meeting recorded from the call lands in a folder of its own, listed after it', async ({
  page,
}) => {
  const meeting = await meetingNow(page);
  await meeting.getByRole('button', { name: 'Pridruži se' }).click();
  await expect(meeting.getByRole('main').getByRole('group')).toHaveCount(1);

  await meeting.getByRole('button', { name: 'Snimaj' }).click();
  await expect(meeting.getByRole('status').filter({ hasText: 'Snima se' })).toBeVisible();
  await expect(meeting.getByRole('button', { name: 'Zaustavi snimanje' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );

  await meeting.getByRole('button', { name: 'Zaustavi snimanje' }).click();
  await expect(meeting.getByRole('status').filter({ hasText: 'Snima se' })).toBeHidden();
  await expect(meeting.getByRole('button', { name: 'Snimaj' })).toBeVisible();

  await meeting.getByRole('button', { name: 'Napusti' }).click();
  await expect(meeting.getByText('Napustili ste sastanak.')).toBeVisible();
  const recordings = meeting.getByRole('heading', { name: 'Snimke' }).locator('..');
  await expect(recordings.getByRole('link', { name: 'Mapa' })).toBeVisible({ timeout: 30_000 });
  await expect(recordings.getByRole('button', { name: 'Reproduciraj' })).toBeVisible();

  await recordings.getByRole('button', { name: 'Reproduciraj' }).click();
  const player = meeting.getByRole('dialog', { name: 'Reproduciraj' });
  await expect(player.locator('video')).toHaveCount(1);
  await expect
    .poll(() => player.locator('video').evaluate((video: HTMLVideoElement) => video.readyState))
    .toBeGreaterThan(0);
});
