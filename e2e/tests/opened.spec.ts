import type { Browser, Page } from '@playwright/test';
import { expect, sessions, test } from './fixtures';
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

  await alone.getByRole('button', { name: 'Moduli' }).click();
  await alone.getByRole('menuitem', { name: 'Pošta' }).click();
  await expect(page).toHaveURL(/\/mail$/);
  await expect(alone).toHaveURL(/\/d\//);
  await expect(alone.getByText('Prvi članak')).toBeVisible();
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
  await expect(alone).toHaveURL(/\/d\//);
  await expect(alone.getByText('Prvi članak')).toBeVisible();
  await expect(held).toHaveCount(0);
});

async function signedOut(browser: Browser, baseURL: string | undefined): Promise<Page> {
  const context = await browser.newContext({ baseURL, locale: 'hr-HR' });
  await context.addInitScript(() => {
    Object.defineProperty(window, 'launchQueue', {
      value: {
        setConsumer(consumer: unknown) {
          Object.assign(window, { launched: consumer });
        },
      },
    });
  });
  const page = await context.newPage();
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Prijavi se pristupnim ključem' })).toBeVisible();
  return page;
}

test('a file the installed app opens while nobody is signed in is read alone, by a visitor of its own, until its window closes', async ({
  browser,
  baseURL,
}) => {
  const page = await signedOut(browser, baseURL);
  await launch(page, 'Ponuda.docx');
  await expect(page.getByText('Prvi članak')).toBeVisible();
  await expect(page).toHaveURL(/\/d\//);
  await expect(page.getByRole('button', { name: 'Spremi u…' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Moduli' })).toHaveCount(0);
  const opened = page.url();

  await page.getByRole('button', { name: 'Zatvori', exact: true }).click();
  const signIn = page.getByRole('button', { name: 'Prijavi se pristupnim ključem' });
  await expect(signIn).toBeVisible();
  await page.goto(opened);
  await expect(signIn).toBeVisible();
  await page.context().close();
});

test('whoever signs in from the window of a file opened signed out takes it and saves it into a folder', async ({
  browser,
  baseURL,
  page: member,
}) => {
  const { email } = (await (await member.request.get('/api/auth/session')).json()).user;
  const title = `Ponuda ${Date.now()}`;
  const page = await signedOut(browser, baseURL);
  await launch(page, `${title}.docx`);
  await expect(page.getByText('Prvi članak')).toBeVisible();

  await page.getByRole('button', { name: 'Spremi u…' }).click();
  await page.getByLabel('E-pošta').fill(email);
  await page.getByLabel('Lozinka').fill(sessions().password);
  await page.getByRole('button', { name: 'Prijavi se', exact: true }).click();
  await expect(page.getByText('Prvi članak')).toBeVisible();
  await expect(page).toHaveTitle(new RegExp(title));

  await page.getByRole('button', { name: 'Spremi u…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Spremi u mapu' });
  await dialog.getByRole('button', { name: 'Spremi ovdje' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Spremi u…' })).toHaveCount(0);
  await member.goto('/documents');
  await expect(member.getByText(title, { exact: true })).toBeVisible();
  await page.context().close();
});
