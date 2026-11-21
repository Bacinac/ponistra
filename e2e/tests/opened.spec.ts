import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { DOCX, wordFile } from './helpers/word';

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    Object.defineProperty(window, 'launchQueue', {
      value: {
        setConsumer(consumer: unknown) {
          Object.assign(window, { launched: consumer });
        },
      },
    });
  });
});

async function launch(page: Page, name: string) {
  await page.waitForFunction(() => 'launched' in window);
  await page.evaluate(
    ({ name, type, data }) => {
      const file = new File([Uint8Array.from(atob(data), (c) => c.charCodeAt(0))], name, { type });
      const launched = (window as unknown as { launched: (params: unknown) => void }).launched;
      launched({ files: [{ getFile: async () => file }] });
    },
    { name, type: DOCX, data: wordFile().toString('base64') },
  );
}

test('a file opened from the computer is read alone in a window of its own, in no folder until saved into one', async ({
  page,
  context,
}) => {
  const title = `Ponuda ${Date.now()}`;
  await page.goto('/documents');
  await expect(page.getByRole('navigation', { name: 'Putanja' })).toContainText('Moji dokumenti');
  const opening = context.waitForEvent('page');
  await launch(page, `${title}.docx`);
  const alone = await opening;
  await expect(alone.getByText('Prvi članak')).toBeVisible();
  await expect(alone).toHaveURL(/\/d\//);
  await expect(alone).toHaveTitle(new RegExp(title));
  await expect(alone.getByRole('link', { name: 'Danas' })).toHaveCount(0);
  await expect(alone.getByRole('navigation', { name: 'Putanja' })).not.toContainText(
    'Moji dokumenti',
  );
  await expect(page).toHaveURL(/\/documents$/);
  await expect(page.getByText(title, { exact: true })).toHaveCount(0);

  await alone.getByRole('button', { name: 'Spremi u…' }).click();
  const dialog = alone.getByRole('dialog', { name: 'Spremi u mapu' });
  await dialog.getByRole('button', { name: 'Spremi ovdje' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(alone.getByRole('button', { name: 'Spremi u…' })).toHaveCount(0);
  await expect(page.getByText(title, { exact: true })).toBeVisible();
});

test('a window the browser refuses to open waits in the main window for a click', async ({
  page,
  context,
}) => {
  const title = `Narudžba ${Date.now()}`;
  await page.goto('/');
  await page.evaluate(() => {
    const open = window.open;
    window.open = () => {
      window.open = open;
      return null;
    };
  });
  await launch(page, `${title}.docx`);
  const held = page.getByRole('group', { name: 'Datoteke otvorene s računala' });
  await expect(held.getByText(`${title}.docx`)).toBeVisible();
  const opening = context.waitForEvent('page');
  await held.getByRole('button', { name: 'Otvori' }).click();
  const alone = await opening;
  await expect(alone.getByText('Prvi članak')).toBeVisible();
  await expect(held).toHaveCount(0);
});
