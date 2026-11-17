import type { Browser, Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { idIn, newDocument, nodeHref } from './helpers/nodes';

async function posted<T>(page: Page, path: string, data: object): Promise<T> {
  return page.evaluate(
    async ({ path, data }) => {
      const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
      const sent = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify(data),
      });
      if (!sent.ok) throw new Error(`POST ${path}: ${sent.status}`);
      return sent.json();
    },
    { path, data },
  );
}

/** Someone outside the installation, in a browser of their own, and what it refused them. */
async function stranger(browser: Browser, baseURL: string) {
  const context = await browser.newContext({ baseURL, locale: 'hr-HR' });
  const page = await context.newPage();
  const refused: string[] = [];
  page.on('response', (response) => {
    if (response.status() >= 400) refused.push(`${response.status()} ${response.url()}`);
  });
  return { page, refused };
}

test('whoever holds a link reads the document and nothing else of the suite', async ({
  page,
  browser,
  baseURL,
}) => {
  const address = await newDocument(page, 'Za vanjske');
  await page.goto(address);
  await page.locator('.ProseMirror').click();
  await page.keyboard.type('Tekst za vanjske.');
  const id = idIn(address.split('/')[2]);
  const link = await posted<{ url: string }>(page, `/api/nodes/${id}/outside-links`, {});

  const outside = await stranger(browser, baseURL!);
  await outside.page.goto(new URL(link.url).pathname);
  await expect(outside.page.getByText('Tekst za vanjske.')).toBeVisible();
  await expect(outside.page.getByRole('navigation', { name: 'Moduli' })).toHaveCount(0);
  await expect(outside.page.getByRole('button', { name: 'Dijeli' })).toHaveCount(0);
  await outside.page.goto('/mail');
  await expect(outside.page).toHaveURL(/\/shared$/);
  await expect(outside.page.getByText('Za vanjske').first()).toBeVisible();
  expect(outside.refused).toEqual([]);
  await outside.page.context().close();
});

test('a document is shared with people outside chosen among the contacts as one types, each mailed a link', async ({
  page,
}) => {
  await page.goto('/documents');
  await posted(page, '/api/mail/accounts', {
    address: 'mox@localhost',
    username: 'mox@localhost',
    password: 'moxmoxmox',
    imap: { host: 'mox', port: 1143, security: 'none' },
    smtp: { host: 'mox', port: 1587, security: 'none' },
  });
  await posted(page, '/api/contacts', {
    fields: { given: 'Vesna', family: 'Vanjska' },
    points: [{ kind: 'email', label: '', value: 'vesna@example.org', parts: [] }],
  });
  const address = await newDocument(page, 'Za kontakte izvana');
  await page.goto(address);
  await page.getByRole('button', { name: 'Dijeli' }).click();
  const panel = page.getByRole('complementary', { name: 'Pristup' });
  await panel.getByRole('button', { name: 'Podijeli s osobom izvana' }).click();
  const people = panel.getByRole('combobox', { name: 'Osobe' });
  const form = panel.locator('form').filter({ has: page.getByRole('combobox', { name: 'Osobe' }) });
  await people.fill('Vesn');
  await panel.getByRole('option', { name: /Vesna Vanjska/ }).click();
  await people.fill('marko@example.net');
  await people.press('Enter');
  await form.getByLabel('Uloga').selectOption('edit');
  await form.getByRole('button', { name: 'Podijeli', exact: true }).click();
  await expect(people).toHaveCount(0, { timeout: 30_000 });
  await expect(panel.getByText('Izvan instalacije · vesna@example.org')).toBeVisible();
  await expect(panel.getByText('Vesna Vanjska', { exact: true })).toBeVisible();
  await expect(panel.getByText('Izvan instalacije · marko@example.net')).toBeVisible();
});

test('a folder asks for files without an account', async ({ page, browser, baseURL }) => {
  await page.goto('/');
  const folder = await posted<{ id: string; title: string; kind: string }>(page, '/api/nodes', {
    kind: 'folder',
    title: 'Ponude',
    parent: null,
  });
  const link = await posted<{ url: string }>(page, `/api/nodes/${folder.id}/outside-links`, {
    kind: 'upload',
  });

  const outside = await stranger(browser, baseURL!);
  await outside.page.goto(new URL(link.url).pathname);
  await expect(outside.page.getByRole('heading', { name: 'Ponude' })).toBeVisible();
  await outside.page.getByLabel('Vaše ime').fill('Marko');
  await outside.page.getByLabel('Datoteke').setInputFiles({
    name: 'ponuda.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('Ponuda'),
  });
  await outside.page.getByRole('button', { name: 'Pošalji' }).click();
  await expect(outside.page.getByRole('status').getByText('ponuda')).toBeVisible();
  expect(outside.refused).toEqual([]);
  await outside.page.context().close();

  await page.goto(nodeHref(folder));
  await expect(page.getByText('ponuda').first()).toBeVisible();
});
