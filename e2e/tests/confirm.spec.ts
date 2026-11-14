import type { BrowserContext, Page } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { expect, sessions, test } from './fixtures';

/** The backend refuses the next app password once, as it does when the user last showed who they
 * are too long ago. */
async function askedOnce(page: Page) {
  let asked = false;
  await page.route('**/api/app-passwords', (route) => {
    if (route.request().method() !== 'POST' || asked) return route.continue();
    asked = true;
    return route.fulfill({ status: 403, json: { error: 'confirm_required' } });
  });
}

async function makeAppPassword(page: Page, name: string) {
  await page.goto('/settings/app-passwords');
  await page.getByRole('button', { name: 'Lozinka za drugu aplikaciju…' }).click();
  await page.getByLabel('Naziv uređaja').fill(name);
  await page.getByRole('button', { name: 'Napravi lozinku' }).click();
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

test('an action waiting on a confirmation goes on once the password is given', async ({
  page,
  problems,
}) => {
  await askedOnce(page);
  await makeAppPassword(page, 'Tablet');
  const dialog = page.getByRole('dialog', { name: 'Potvrdite da ste to vi' });
  await expect(dialog.getByRole('button', { name: 'Potvrdi pristupnim ključem' })).toHaveCount(0);
  await dialog.getByLabel('Lozinka').fill('nije-ta');
  await dialog.getByRole('button', { name: 'Potvrdi', exact: true }).click();
  await expect(dialog.getByText('Lozinka nije točna.')).toBeVisible();
  await dialog.getByLabel('Lozinka').fill(sessions().password);
  await dialog.getByRole('button', { name: 'Potvrdi', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('region', { name: 'Tablet' })).toBeVisible();

  await askedOnce(page);
  await makeAppPassword(page, 'Drugi tablet');
  await dialog.getByRole('button', { name: 'Odustani' }).click();
  await expect(page.getByText('Radnja nije potvrđena.')).toBeVisible();

  const refused = problems.filter((problem) => / status of 40[03]/.test(problem));
  expect(refused).toHaveLength(3);
  problems.splice(0, problems.length, ...problems.filter((problem) => !refused.includes(problem)));
});

test('a user with a passkey confirms with it', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ baseURL, locale: 'hr-HR' });
  await context.addCookies([
    { name: 'sessionid', value: sessions().colleague, url: baseURL },
    { name: 'csrftoken', value: randomBytes(16).toString('hex'), url: baseURL },
  ]);
  const page = await context.newPage();
  await authenticator(context, page);
  await page.goto('/settings/sign-in');
  await page.getByLabel('Naziv novog ključa').fill('Laptop');
  await page.getByRole('button', { name: 'Dodaj pristupni ključ' }).click();
  await expect(page.getByRole('cell', { name: 'Laptop' })).toBeVisible();

  await askedOnce(page);
  await makeAppPassword(page, 'Mobitel');
  const dialog = page.getByRole('dialog', { name: 'Potvrdite da ste to vi' });
  await expect(dialog.getByLabel('Lozinka')).toBeVisible();
  await dialog.getByRole('button', { name: 'Potvrdi pristupnim ključem' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('region', { name: 'Mobitel' })).toBeVisible();
  await context.close();
});
