import type { BrowserContext, Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { nodeHref } from './helpers/nodes';

/** A node made through the API, by the address the app gives it. */
async function made(page: Page, fields: object): Promise<{ id: string; href: string }> {
  const node = await page.evaluate(async (fields) => {
    await fetch('/api/auth/session');
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const response = await fetch('/api/nodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify(fields),
    });
    if (!response.ok) throw new Error(`POST /api/nodes: ${response.status}`);
    return response.json();
  }, fields);
  return { id: node.id, href: nodeHref(node) };
}

async function authenticator(context: BrowserContext, page: Page) {
  const cdp = await context.newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
}

test('an owner keeps a folder in the browser and reads who opened what is in it', async ({
  page,
}) => {
  await page.goto('/');
  const folder = await made(page, { kind: 'folder', title: 'Plaće', parent: null });
  const payslip = await made(page, { kind: 'document', title: 'Listopad', parent: folder.id });
  await page.goto(payslip.href);
  await expect(page.locator('.ProseMirror').first()).toBeVisible();

  await page.goto(folder.href);
  await page.getByRole('button', { name: 'Dijeli' }).click();
  const panel = page.getByRole('complementary', { name: 'Pristup' });
  const confined = panel.getByRole('checkbox', { name: /Bez preuzimanja/ });
  await confined.click();
  await expect(confined).toBeChecked();
  await panel.getByRole('button', { name: 'Dnevnik pristupa' }).click();
  const log = page.getByRole('dialog', { name: 'Dnevnik pristupa: Plaće' });
  await expect(log.getByText('Otvaranje')).toBeVisible();
  await expect(log.getByRole('link', { name: 'Listopad' })).toBeVisible();
  await log.getByRole('button', { name: 'Zatvori' }).click();

  await page.goto('/documents');
  await expect(
    page.getByRole('row', { name: /Plaće/ }).getByRole('img', { name: 'Bez preuzimanja' }),
  ).toBeVisible();
});

test('a user the policy holds to passkeys adds one before anything else', async ({
  page,
  context,
}) => {
  await authenticator(context, page);
  let added = false;
  await page.route('**/api/auth/session', async (route) => {
    const response = await route.fetch();
    const session = await response.json();
    await route.fulfill({ response, json: { ...session, passkey_due: !added } });
  });
  await page.route('**/api/passkeys/options', (route) =>
    route.fulfill({
      json: {
        rp: { id: 'localhost', name: 'PONISTRA' },
        user: { id: 'AQID', name: 'e2e@e2e.invalid', displayName: 'E2E' },
        challenge: 'AAECAwQFBgcICQoLDA0ODw',
        pubKeyCredParams: [
          { type: 'public-key', alg: -7 },
          { type: 'public-key', alg: -257 },
        ],
        authenticatorSelection: { residentKey: 'required', userVerification: 'required' },
      },
    }),
  );
  await page.route('**/api/passkeys', (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    added = true;
    return route.fulfill({
      status: 201,
      json: { id: 1, name: 'Laptop', created_at: '2026-10-24T09:00:00Z', used_at: null },
    });
  });

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Dodajte pristupni ključ' })).toBeVisible();
  await expect(page.getByRole('button', { name: /^Račun / })).toBeHidden();
  await page.getByLabel('Naziv novog ključa').fill('Laptop');
  await page.getByRole('button', { name: 'Dodaj pristupni ključ' }).click();
  await expect(page.getByRole('button', { name: /^Račun / })).toBeVisible();
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});
