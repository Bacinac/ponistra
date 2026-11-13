import type { BrowserContext, Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function device(context: BrowserContext, page: Page) {
  const cdp = await context.newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  const { authenticatorId } = await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  return { cdp, authenticatorId };
}

test('a passkey added in the settings signs in where nobody is, without an email', async ({
  page,
  browser,
  baseURL,
}) => {
  const here = await device(page.context(), page);
  await page.goto('/settings/passkeys');
  const dialog = page.getByRole('main');
  await expect(dialog.getByText('Još nemate pristupnih ključeva.')).toBeVisible();
  await dialog.getByLabel('Naziv novog ključa').fill('Laptop');
  await dialog.getByRole('button', { name: 'Dodaj pristupni ključ' }).click();
  await expect(dialog.getByRole('cell', { name: 'Laptop' })).toBeVisible();
  await expect(dialog.getByRole('cell', { name: 'Nikad' })).toBeVisible();
  await expect(dialog.getByLabel('Naziv novog ključa')).toHaveValue('');

  await dialog.getByLabel('Naziv novog ključa').fill('Isti laptop');
  await dialog.getByRole('button', { name: 'Dodaj pristupni ključ' }).click();
  await expect(dialog.getByText('Ovaj uređaj već čuva vaš pristupni ključ.')).toBeVisible();

  const { credentials } = await here.cdp.send('WebAuthn.getCredentials', {
    authenticatorId: here.authenticatorId,
  });
  const elsewhere = await browser.newContext({ baseURL, locale: 'hr-HR' });
  const signing = await elsewhere.newPage();
  const there = await device(elsewhere, signing);
  await there.cdp.send('WebAuthn.addCredential', {
    authenticatorId: there.authenticatorId,
    credential: credentials[0],
  });
  await signing.goto('/');
  await signing.getByRole('button', { name: 'Prijavi se pristupnim ključem' }).click();
  await expect(signing.getByRole('button', { name: /^Račun / })).toBeVisible();

  await signing.getByRole('button', { name: /^Račun / }).click();
  await signing.getByRole('menuitem', { name: 'Odjavi se' }).click();
  await expect(
    signing.getByRole('button', { name: 'Prijavi se pristupnim ključem' }),
  ).toBeVisible();
  await elsewhere.close();
});

test('the sign-in method chosen in the settings leads the sign-in page, the other a click away', async ({
  page,
  browser,
  baseURL,
}) => {
  const here = await device(page.context(), page);
  await page.goto('/settings/passkeys');
  await page.getByRole('main').getByLabel('Naziv novog ključa').fill('Radni laptop');
  await page.getByRole('main').getByRole('button', { name: 'Dodaj pristupni ključ' }).click();
  await expect(page.getByRole('main').getByRole('cell', { name: 'Radni laptop' })).toBeVisible();

  await page.goto('/settings/sign-in');
  const way = page.getByRole('main').getByLabel('Način prijave');
  await expect(way.getByRole('option', { name: 'Pristupni ključ' })).toBeEnabled();
  await way.selectOption('passkey');
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('ponistra.signIn')))
    .toBe('passkey');

  const { credentials } = await here.cdp.send('WebAuthn.getCredentials', {
    authenticatorId: here.authenticatorId,
  });
  const elsewhere = await browser.newContext({ baseURL });
  const signing = await elsewhere.newPage();
  const there = await device(elsewhere, signing);
  await there.cdp.send('WebAuthn.addCredential', {
    authenticatorId: there.authenticatorId,
    credential: credentials[0],
  });
  await signing.addInitScript(() => localStorage.setItem('ponistra.signIn', 'passkey'));
  await signing.goto('/');
  await expect(signing.getByLabel('E-pošta')).toHaveCount(0);
  await signing.getByRole('button', { name: 'Prijavi se lozinkom' }).click();
  await expect(signing.getByLabel('Lozinka')).toBeVisible();
  await signing.getByRole('button', { name: 'Prijavi se pristupnim ključem' }).click();
  await expect(signing.getByRole('button', { name: /^Račun / })).toBeVisible();
  await elsewhere.close();
});
