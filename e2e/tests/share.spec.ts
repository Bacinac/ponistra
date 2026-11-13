import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

const PIXEL = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkqP9fDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);
const FILES = [
  { name: 'Izlet.png', mimeType: 'image/png', buffer: PIXEL },
  { name: 'Popis.txt', mimeType: 'text/plain', buffer: Buffer.from('kruh\nmlijeko\n') },
];

/** Posts to the share target as Chrome does when another app shares with Ponistra. */
async function shared(
  page: Page,
  fields: Record<string, string>,
  files: typeof FILES = [],
): Promise<void> {
  await page.goto('/');
  await page.evaluate(async (fields) => {
    await navigator.serviceWorker.ready;
    const form = document.createElement('form');
    Object.assign(form, { method: 'post', action: '/share', enctype: 'multipart/form-data' });
    for (const [name, value] of Object.entries(fields))
      form.append(Object.assign(document.createElement('input'), { name, value }));
    form.append(
      Object.assign(document.createElement('input'), {
        type: 'file',
        name: 'files',
        multiple: true,
      }),
    );
    form.id = 'shared';
    document.body.append(form);
  }, fields);
  await page.locator('#shared input[type="file"]').setInputFiles(files);
  await page.evaluate(() => (document.getElementById('shared') as HTMLFormElement).submit());
  await expect(page).toHaveURL(/\/share$/);
}

test('the manifest names the share target the phone app posts to', async ({ request }) => {
  const manifest = await (await request.get('/manifest.webmanifest')).json();
  expect(manifest.share_target).toEqual({
    action: '/share',
    method: 'POST',
    enctype: 'multipart/form-data',
    params: {
      title: 'title',
      text: 'text',
      url: 'url',
      files: [{ name: 'files', accept: ['*/*'] }],
    },
  });
});

test('files another app shares are saved in the folder the user picks, once', async ({ page }) => {
  test.slow();
  await shared(page, { title: 'Izlet', text: 'Fotografije s izleta' }, FILES);
  await expect(page.getByRole('heading', { name: 'Podijeljeno s Ponistrom' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Izlet', exact: true })).toBeVisible();
  await expect(page.getByText('Fotografije s izleta')).toBeVisible();
  const files = page.getByRole('list', { name: 'Podijeljene datoteke' }).getByRole('listitem');
  await expect(files).toHaveCount(2);
  await expect(files.first().locator('img')).toHaveJSProperty('naturalWidth', 1);
  await expect(files.nth(1)).toContainText('Popis.txt');

  await page.getByRole('button', { name: 'Spremi u mapu' }).click();
  const dialog = page.getByRole('dialog', { name: 'Spremi u mapu' });
  await dialog.getByRole('button', { name: 'Spremi ovdje' }).click();
  await expect(page).toHaveURL(/\/documents$/);
  await expect(page.getByRole('row', { name: /Izlet.*PNG datoteka/ })).toBeVisible();
  await expect(page.getByRole('row', { name: /Popis.*TXT datoteka/ })).toBeVisible();

  await page.goto('/share');
  await expect(page.getByText('Ništa nije podijeljeno ili je već spremljeno.')).toBeVisible();
});

test('a shared link goes out in a new message, with the files shared beside it', async ({
  page,
}) => {
  let sent: Record<string, unknown> | null = null;
  await page.route('**/api/mail/accounts', async (route) => {
    const response = await route.fetch();
    const given = await response.json();
    const account = {
      id: 9001,
      address: 'ana@example.com',
      name: 'Ana',
      label: '',
      signature: '',
      own_signature: false,
      username: 'ana@example.com',
      login: 'password',
      protocol: 'imap',
      activesync: { host: '' },
      imap: { host: 'imap.example.com', port: 993, security: 'ssl' },
      smtp: { host: 'smtp.example.com', port: 465, security: 'ssl' },
      color: 0,
      default: true,
      together: true,
      unseen: 0,
      state: 'ready',
      error: '',
      synced_at: null,
      older: false,
    };
    await route.fulfill({ response, json: { ...given, accounts: [account] } });
  });
  await page.route('**/api/mail/send', async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill({ json: { refused: [], kept: true } });
  });

  await shared(page, { title: 'Članak', text: 'https://example.com/clanak' }, FILES.slice(1));
  await page.getByRole('button', { name: 'Pošalji e-poštom' }).click();
  const compose = page.getByRole('dialog', { name: 'Nova poruka' });
  await expect(compose.getByLabel('Predmet')).toHaveValue('Članak');
  await expect(compose.getByLabel('Poruka')).toHaveText('https://example.com/clanak');
  await expect(compose.getByRole('list', { name: 'Privitci' })).toContainText('Popis.txt');
  await compose.getByLabel('Za').fill('Ivo <ivo@example.com>');
  await compose.getByRole('button', { name: 'Pošalji', exact: true }).click();
  await expect(page).toHaveURL(/\/mail$/);
  expect(sent).toMatchObject({
    subject: 'Članak',
    html: '<p>https://example.com/clanak</p>',
    files: [{ name: 'Popis.txt', sha256: expect.stringMatching(/^[0-9a-f]{64}$/) }],
  });
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});

test('a link alone is saved in the folder the user picks as a link named by its site', async ({
  page,
}) => {
  const site = `clanak-${Date.now()}.example.com`;
  await shared(page, { text: `https://${site}/` });
  await expect(page.getByText(`https://${site}/`)).toBeVisible();
  await page.getByRole('button', { name: 'Spremi u mapu' }).click();
  await page
    .getByRole('dialog', { name: 'Spremi u mapu' })
    .getByRole('button', { name: 'Spremi ovdje' })
    .click();
  await expect(page).toHaveURL(/\/documents$/);
  await expect(page.getByRole('row', { name: new RegExp(`${site}.*Poveznica`) })).toBeVisible();
});

test('a shared text and link are saved as a note', async ({ page }) => {
  const title = `Recept ${Date.now()}`;
  await shared(page, { title, text: 'tijesto i nadjev', url: 'https://example.com/recept' });
  await page.getByRole('button', { name: 'Spremi kao bilješku' }).click();
  await expect(page).toHaveURL(/\/d\//);
  const editor = page.locator('.ProseMirror').first();
  await expect(editor.locator('p')).toHaveText([title, 'tijesto i nadjev', 'https://example.com/recept']);
  await expect(editor.getByRole('link', { name: 'https://example.com/recept' })).toBeVisible();
  await page.goBack();
  await expect(page).not.toHaveURL(/\/share$/);
});
