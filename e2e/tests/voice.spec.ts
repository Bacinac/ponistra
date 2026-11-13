import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

// Chromium's own microphone: a tone, granted without asking.
test.use({
  permissions: ['microphone'],
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
});

/** The installation writes speech as the given text, and the user's consent is kept as it is
 * given. */
async function speech(page: Page, text: string, given: string | null = null) {
  const sent: string[] = [];
  await page.route('**/api/speech/consent', async (route) => {
    if (route.request().method() === 'PUT') given = new Date().toISOString();
    await route.fulfill({
      json: { enabled: true, understands: false, given_at: given },
    });
  });
  await page.route('**/api/speech', async (route) => {
    sent.push(route.request().headers()['content-type']);
    await route.fulfill({ json: { text } });
  });
  return sent;
}

async function say(page: Page) {
  await page.getByRole('button', { name: 'Izgovorite naredbu ili bilješku' }).click();
  const recording = page.getByRole('dialog', { name: 'Govorite' });
  await expect(recording.getByText('Slušam')).toBeVisible();
  await expect(recording.getByText(/^0:(0[1-9]|[1-5]\d)$/)).toBeVisible();
  await recording.getByRole('button', { name: 'Gotovo' }).click();
}

test('what is said asks consent once and is kept as a note after it is read', async ({ page }) => {
  const said = `Nazvati servis ${Date.now()}`;
  const sent = await speech(page, `${said}\nzbog pisača na drugom katu`);
  await page.goto('/documents');
  await page.getByRole('button', { name: 'Izgovorite naredbu ili bilješku' }).click();
  await page
    .getByRole('dialog', { name: 'Slanje govora tvrtki OpenAI' })
    .getByRole('button', { name: 'Pristajem' })
    .click();
  const recording = page.getByRole('dialog', { name: 'Govorite' });
  await expect(recording.getByText('Slušam')).toBeVisible();
  await expect(recording.getByText(/^0:(0[1-9]|[1-5]\d)$/)).toBeVisible();
  await recording.getByRole('button', { name: 'Gotovo' }).click();

  const heard = page.getByRole('dialog', { name: 'Izgovoreno' });
  const text = heard.getByRole('textbox', { name: 'Prepoznati tekst' });
  await expect(text).toHaveValue(`${said}\nzbog pisača na drugom katu`);
  await text.fill(`${said}\nzbog pisača na trećem katu`);
  await heard.getByRole('button', { name: 'Spremi kao bilješku' }).click();

  await expect(page).toHaveURL(/\/d\//);
  const editor = page.locator('.ProseMirror').first();
  await expect(editor).toContainText(said);
  await expect(editor).toContainText('zbog pisača na trećem katu');
  expect(sent).toEqual([expect.stringMatching(/^audio\/(webm|ogg|mp4)/)]);
  await page.goBack();
  await expect(page).toHaveURL(/\/documents$/);
});

test('a command said by its name runs, from any page and by Alt+M', async ({ page }) => {
  await speech(page, 'Nova bilješka.', new Date().toISOString());
  await page.goto('/calendar');
  await say(page);
  await expect(page).toHaveURL(/\/d\//);
  await expect(page.locator('.ProseMirror').first()).toBeVisible();

  await page.keyboard.press('Alt+KeyM');
  await expect(page.getByRole('dialog', { name: 'Govorite' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page).not.toHaveURL(/voice/);
});
