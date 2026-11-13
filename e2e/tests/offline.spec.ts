import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';

const OFFLINE = /ERR_INTERNET_DISCONNECTED|WebSocket connection|Failed to fetch|did not sync/;

async function kept(page: Page) {
  await expect(page.getByText('Zadnje spremanje na uređaj:')).toBeVisible({ timeout: 60_000 });
}

async function keptStores(page: Page): Promise<string[]> {
  return page.evaluate(async () =>
    (await indexedDB.databases())
      .map(({ name }) => name ?? '')
      .filter((name) => name.startsWith('ponistra-room-') || name === 'ponistra-offline'),
  );
}

test('a device marked to work offline opens its documents without the network, and what was written there joins the rest', async ({
  page,
  context,
  problems,
}) => {
  test.setTimeout(240_000);
  const title = `Ugovor bez mreže ${Date.now()}`;
  const address = await newDocument(page, title);
  await page.goto(address);
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Prvi redak');
  await expect(editor).toContainText('Prvi redak');

  await page.goto('/settings/devices');
  await page.getByRole('button', { name: 'Uključi rad bez mreže' }).click();
  await expect(page.getByRole('button', { name: 'Isključi rad bez mreže' })).toBeVisible();
  await kept(page);

  await page.goto('/documents');
  await page.getByRole('row').filter({ hasText: title }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Čuvaj na ovom uređaju' }).click();
  await page.goto('/settings/devices');
  await kept(page);

  await context.setOffline(true);
  await page.goto(address);
  await expect(editor).toContainText('Prvi redak');
  await expect(page.getByRole('combobox', { name: 'Pretraži' })).toBeDisabled();
  await editor.click();
  await page.keyboard.press('End');
  await page.keyboard.type(' i drugi bez mreže');
  await expect(editor).toContainText('Prvi redak i drugi bez mreže');

  await context.setOffline(false);
  const other = await context.newPage();
  await other.goto(address);
  await expect(other.locator('.ProseMirror').first()).toContainText(
    'Prvi redak i drugi bez mreže',
    { timeout: 20_000 },
  );
  await other.close();

  // Signing out, ending the device or a session run out all reach the page as nobody signed in.
  await page.route('**/api/auth/session', (route) =>
    route.fulfill({
      json: { user: null, passkey_due: false, setup: false, site: '', providers: [] },
    }),
  );
  await page.goto('/');
  await expect.poll(() => keptStores(page)).toEqual([]);
  problems.splice(0, problems.length, ...problems.filter((each) => !OFFLINE.test(each)));
});

test('a device marked to work offline reads its recent mail with the files it carries, and what was sent there leaves once the network is back', async ({
  page,
  context,
  problems,
}) => {
  test.setTimeout(240_000);
  await page.goto('/mail');
  await page.getByRole('button', { name: 'Poveži račun' }).click();
  const dialog = page.getByRole('dialog', { name: 'Povezivanje računa e-pošte' });
  await dialog.getByLabel('Adresa e-pošte').fill('mox@localhost');
  await dialog.getByLabel('Lozinka').fill('moxmoxmox');
  await dialog.getByRole('button', { name: 'Poveži račun' }).click();
  await expect(
    dialog.getByText('Dolazni poslužitelj nije dostupan; provjerite poslužitelj i priključak.'),
  ).toBeVisible({ timeout: 40_000 });
  const refused = problems.filter((problem) => problem.includes('status of 400'));
  problems.splice(0, problems.length, ...problems.filter((problem) => !refused.includes(problem)));
  for (const [name, port] of [
    ['Dolazna pošta (IMAP)', '1143'],
    ['Odlazna pošta (SMTP)', '1587'],
  ]) {
    const server = dialog.getByRole('group', { name });
    await server.getByLabel('Poslužitelj').fill('mox');
    await server.getByLabel('Šifriranje').selectOption('none');
    await server.getByLabel('Priključak').fill(port);
  }
  await dialog.getByRole('button', { name: 'Poveži račun' }).click();
  await expect(dialog).toBeHidden({ timeout: 40_000 });

  const subject = `Izvještaj bez mreže ${Date.now()}`;
  await page.getByRole('button', { name: 'Nova poruka' }).click();
  const compose = page.getByRole('dialog', { name: 'Nova poruka' });
  await compose.getByLabel('Za').fill('Ana Kovač <ana@example.com>');
  await compose.getByLabel('Predmet').fill(subject);
  await compose.getByLabel('Poruka').fill('U privitku.');
  await compose.getByRole('button', { name: 'Priloži datoteke' }).click();
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('menuitem', { name: 'S računala…' }).click();
  await (
    await chooser
  ).setFiles({ name: 'izvjestaj.txt', mimeType: 'text/plain', buffer: Buffer.from('brojke') });
  await expect(compose.getByText('izvjestaj.txt')).toBeVisible();
  await compose.getByRole('button', { name: 'Pošalji', exact: true }).click();
  await expect(compose).toBeHidden({ timeout: 20_000 });

  await page.goto('/settings/devices');
  await page.getByRole('button', { name: 'Uključi rad bez mreže' }).click();
  await kept(page);

  await context.setOffline(true);
  await page.goto('/mail');
  const accounts = page.getByRole('navigation', { name: 'Računi e-pošte' });
  await accounts.getByRole('link', { name: 'Poslano' }).click();
  await page.getByRole('link', { name: new RegExp(subject) }).click();
  const article = page.getByRole('article', { name: subject });
  await expect(article.getByRole('link', { name: 'izvjestaj.txt' })).toHaveAttribute(
    'href',
    /^blob:/,
  );
  await expect(article.getByRole('button', { name: 'Arhiviraj' })).toBeDisabled();

  await article.getByRole('button', { name: 'Odgovori', exact: true }).click();
  const reply = page.getByRole('dialog', { name: 'Nova poruka' });
  await expect(reply.getByLabel('Predmet')).toHaveValue(`Re: ${subject}`);
  await reply.getByLabel('Poruka').fill('Primljeno bez mreže.');
  await expect(reply.getByText('Spremljeno na uređaju')).toBeVisible();
  await reply.getByRole('button', { name: 'Pošalji', exact: true }).click();
  await expect(reply).toBeHidden();
  await accounts.getByRole('link', { name: /^Za slanje/ }).click();
  const waiting = page
    .getByRole('list', { name: 'Za slanje' })
    .getByRole('listitem')
    .filter({ hasText: `Re: ${subject}` });
  await expect(waiting).toContainText('Čeka mrežu');

  await context.setOffline(false);
  await expect(waiting).toBeHidden({ timeout: 60_000 });
  await accounts.getByRole('link', { name: 'Poslano' }).click();
  await expect(page.getByRole('link', { name: new RegExp(`Re: ${subject}`) })).toHaveCount(1, {
    timeout: 30_000,
  });
  problems.splice(0, problems.length, ...problems.filter((each) => !OFFLINE.test(each)));
});
