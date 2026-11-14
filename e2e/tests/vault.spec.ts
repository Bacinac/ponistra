import type { Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { expect, test } from './fixtures';

const PASSWORD = 'Kamen-Most-Rijeka-71';

/** The account's vault as it was before this test: none. */
async function cleared(page: Page) {
  await page.goto('/');
  await page.evaluate(async () => {
    await fetch('/api/auth/session');
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const response = await fetch('/api/vault', {
      method: 'DELETE',
      headers: { 'X-CSRFToken': token },
    });
    if (!response.ok) throw new Error(`DELETE: ${response.status}`);
  });
}

async function made(page: Page): Promise<string> {
  await page.goto('/vault');
  await expect(page.getByRole('heading', { name: 'Izradite svoj sef' })).toBeVisible();
  await page.getByLabel('Nova lozinka sefa').fill('kratka');
  await expect(page.getByRole('button', { name: 'Izradi sef' })).toBeDisabled();
  await page.getByLabel('Nova lozinka sefa').fill(PASSWORD);
  await page.getByLabel('Ponovite lozinku').fill(PASSWORD);
  await page.getByRole('button', { name: 'Izradi sef' }).click();
  const dialog = page.getByRole('dialog', { name: 'Kod za oporavak' });
  const code = (await dialog.getByLabel('Kod za oporavak').textContent())!;
  expect(code).toMatch(/^([0-9A-Z]{4}-){7}[0-9A-Z]{4}$/);
  await dialog.getByRole('button', { name: 'Kod je spremljen' }).click();
  return code;
}

/** Logins brought in as Chrome exports them, each row `name,url,username,password,note`. */
async function imported(page: Page, rows: string[]) {
  await page.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Uvezi…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Uvezi…' });
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    dialog.getByRole('button', { name: 'Odaberi datoteku…' }).click(),
  ]);
  await chooser.setFiles({
    name: 'Chrome Passwords.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(['name,url,username,password,note', ...rows, ''].join('\n')),
  });
  await expect(dialog.getByText(`Chrome ili Edge · Stavki za uvoz: ${rows.length}`)).toBeVisible();
  await dialog.getByRole('button', { name: 'Uvezi', exact: true }).click();
  await expect(dialog).toBeHidden();
}

async function locked(page: Page) {
  await page.getByRole('button', { name: 'Zaključaj sef' }).click();
  await expect(page.getByRole('heading', { name: 'Sef je zaključan' })).toBeVisible();
}

test('a vault is made, holds a login with its one-time code, and opens with its password and code', async ({
  page,
}) => {
  test.setTimeout(60_000);
  await cleared(page);
  const code = await made(page);
  await expect(page.getByRole('heading', { name: 'Moj sef' })).toBeVisible();

  await page.getByRole('button', { name: 'Nova stavka' }).click();
  const editor = page.getByRole('dialog', { name: /Nova stavka/ });
  await editor.getByLabel('Naziv').fill('Banka');
  await editor.getByLabel('Korisničko ime').fill('ana');
  await editor.getByRole('button', { name: 'Generiraj lozinku' }).click();
  await editor.getByRole('button', { name: 'Upotrijebi' }).click();
  const generated = await editor.getByLabel('Lozinka', { exact: true }).inputValue();
  expect(generated).toHaveLength(20);
  await editor.getByLabel('Jednokratni kod').fill('nije tajna');
  await expect(editor.getByText('Ovo nije tajni ključ jednokratnih kodova.')).toBeVisible();
  await expect(editor.getByRole('button', { name: 'Izradi' })).toBeDisabled();
  await editor.getByLabel('Jednokratni kod').fill('JBSW Y3DP EHPK 3PXP');
  await editor.getByLabel('Adrese (jedna po retku)').fill('banka.hr');
  await editor.getByRole('button', { name: 'Izradi' }).click();

  const item = page.getByRole('article', { name: 'Banka' });
  await expect(item.getByText('ana', { exact: true })).toBeVisible();
  await expect(item.getByText(generated)).toHaveCount(0);
  await item.getByRole('button', { name: 'Prikaži' }).click();
  await expect(item.getByText(generated)).toBeVisible();
  await expect(item.getByText(/^\d{3} \d{3}$/)).toBeVisible();
  await expect(page.getByRole('link', { name: /Moj sef/ })).toContainText('1');

  const search = page.getByRole('combobox', { name: 'Pretraži' });
  await search.fill('bank');
  const hit = page.getByRole('option', { name: /Banka/ });
  await expect(hit).toContainText('ana · banka.hr · Moj sef');
  await hit.click();
  await expect(page).toHaveURL(/\/vault\/[^/]+\/[^/?]+$/);
  await expect(page.getByRole('article', { name: 'Banka' })).toBeVisible();

  await locked(page);
  await search.fill('bank');
  await expect(page.getByText('Sef je zaključan i nije pretražen.')).toBeVisible();
  await expect(page.getByRole('option', { name: /Banka/ })).toHaveCount(0);
  await search.fill('');
  await page.getByLabel('Lozinka sefa').fill('pogrešna lozinka');
  await page.getByRole('button', { name: 'Otključaj', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Lozinka nije ispravna.');
  await page.getByLabel('Lozinka sefa').fill(PASSWORD);
  await page.getByRole('button', { name: 'Otključaj', exact: true }).click();
  await expect(page.getByRole('article', { name: 'Banka' })).toBeVisible();

  await locked(page);
  await page.getByRole('button', { name: /Zaboravili ste lozinku/ }).click();
  await page.getByLabel('Kod za oporavak').fill(code.toLowerCase().replace(/-/g, ' '));
  await page.getByRole('button', { name: 'Otključaj', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Postavi novu lozinku' })).toBeVisible();
  await page.getByLabel('Nova lozinka sefa').fill(`${PASSWORD}-novo`);
  await page.getByLabel('Ponovite lozinku').fill(`${PASSWORD}-novo`);
  await page.getByRole('button', { name: 'Postavi novu lozinku' }).click();
  await expect(page.getByRole('article', { name: 'Banka' })).toBeVisible();

  await locked(page);
  await page.getByLabel('Lozinka sefa').fill(`${PASSWORD}-novo`);
  await page.getByRole('button', { name: 'Otključaj', exact: true }).click();
  await expect(page.getByRole('article', { name: 'Banka' })).toBeVisible();
});

test('logins come in from Chrome and go out as Bitwarden reads them', async ({ page }) => {
  await cleared(page);
  await made(page);
  await imported(page, [
    'Git,https://git.example.com,ana,t1,',
    'Poslužitelj,https://mail.example.com,ana,t2,bilješka',
  ]);
  await expect(page.getByRole('link', { name: /Git/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /Poslužitelj/ })).toBeVisible();

  await page.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Izvezi…' }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('dialog').getByRole('button', { name: 'Izvezi', exact: true }).click();
  const file = await download;
  const exported = JSON.parse(await readFile(await file.path(), 'utf8'));
  expect(exported.encrypted).toBe(false);
  expect(
    exported.items.map((item: { name: string; login: { password: string } }) => [
      item.name,
      item.login.password,
    ]),
  ).toEqual(
    expect.arrayContaining([
      ['Git', 't1'],
      ['Poslužitelj', 't2'],
    ]),
  );
});

test('logins are filed into folders by hand, and by Claude reading only their names and hosts', async ({
  page,
}) => {
  test.setTimeout(60_000);
  await page.route('**/api/actions', async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), ai: true } });
  });
  let asked: unknown;
  await page.route('**/api/vault/collections/*/sorting', async (route) => {
    asked = route.request().postDataJSON();
    await route.fulfill({
      json: {
        folders: [
          { name: 'Financije', entries: [0] },
          { name: 'Kupovina', entries: [1] },
        ],
      },
    });
  });
  await cleared(page);
  await made(page);
  await imported(page, [
    'Git,https://git.example.com,ana,t1,',
    'Poslužitelj,https://mail.example.com,ana,t2,',
    'Banka,https://banka.hr/prijava,ana,t3,',
    'Trgovina,https://shop.example.com,ana,t4,',
  ]);
  const side = page.getByRole('navigation', { name: 'Sef' });
  const actions = async (name: string) => {
    await page.getByRole('button', { name: 'Radnje' }).click();
    await page.getByRole('menuitem', { name }).click();
  };

  await actions('Nova mapa');
  const naming = page.getByRole('dialog', { name: 'Nova mapa' });
  await naming.getByLabel('Naziv').fill('Posao');
  await naming.getByRole('button', { name: 'Izradi' }).click();
  await expect(page.getByText('Mapa je prazna.')).toBeVisible();
  await side.getByRole('link', { name: /Moj sef/ }).click();

  const row = (name: string) =>
    page.getByRole('main').getByRole('listitem').filter({ hasText: name });
  await row('Git').getByRole('link').hover();
  await page.mouse.down();
  await expect(page.getByText('Odabrano: 1')).toBeVisible();
  await page.mouse.up();
  await row('Poslužitelj').getByRole('link').click();
  await expect(page.getByText('Odabrano: 2')).toBeVisible();
  await page.getByRole('button', { name: 'Premjesti', exact: true }).click();
  const moving = page.getByRole('dialog', { name: 'Premjesti: 2' });
  await moving.getByLabel('Premjesti u').selectOption({ label: 'Moj sef / Posao' });
  await moving.getByRole('button', { name: 'Premjesti ovamo' }).click();
  await expect(moving).toBeHidden();
  await expect(side.getByRole('link', { name: /Posao/ })).toContainText('2');
  await expect(row('Git')).toHaveCount(0);
  await expect(row('Banka')).toBeVisible();

  await actions('Razvrstaj u mape…');
  const sorting = page.getByRole('dialog', { name: 'Razvrstavanje u mape' });
  await expect(sorting.getByText('Stavki za razvrstavanje: 2')).toBeVisible();
  await sorting.getByRole('button', { name: 'Pošalji i razvrstaj' }).click();
  await expect(sorting.getByLabel('Naziv mape')).toHaveCount(2);
  expect(asked).toEqual({
    entries: [
      { name: 'Banka', host: 'banka.hr' },
      { name: 'Trgovina', host: 'shop.example.com' },
    ],
    existing: ['Posao'],
    language: 'hr',
    consent: 'once',
  });
  await sorting.getByLabel('Naziv mape').nth(1).fill('posao');
  await sorting.getByRole('button', { name: 'Primijeni' }).click();
  await expect(sorting).toBeHidden();
  await expect(side.getByRole('link', { name: /Financije/ })).toContainText('1');
  await expect(side.getByRole('link', { name: /Posao/ })).toContainText('3');
  await expect(side.getByRole('link', { name: /Kupovina|posao/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'Radnje' }).click();
  await expect(page.getByRole('menuitem', { name: /Razvrstaj u mape/ })).toBeDisabled();
  await expect(page.getByText('Sve su stavke već u mapama.')).toBeVisible();
  await page.keyboard.press('Escape');

  await side.getByRole('link', { name: /Financije/ }).click();
  await expect(row('Banka')).toBeVisible();
  await actions('Obriši mapu');
  await page
    .getByRole('alertdialog', { name: 'Obrisati mapu?' })
    .getByRole('button', { name: 'Obriši mapu' })
    .click();
  await expect(side.getByRole('link', { name: /Financije/ })).toHaveCount(0);
  await expect(row('Banka')).toBeVisible();
  await expect(row('Git')).toHaveCount(0);
});

test('a long press at the foot of a vault keeps the bar in view and the row in place, and a right click offers its actions', async ({
  page,
}) => {
  await cleared(page);
  await made(page);
  const names = Array.from({ length: 40 }, (_, at) => `Prijava ${at}`);
  await imported(
    page,
    names.map((name) => `${name},https://example.com,ana,tajna,`),
  );
  await page.getByRole('link', { name: /Moj sef/ }).click();
  const list = page.getByRole('main').getByRole('listitem');
  await expect(list).toHaveCount(names.length);
  const row = list.last();
  await row.scrollIntoViewIfNeeded();
  await row.getByRole('link').hover();
  await page.waitForTimeout(200);
  const before = (await row.boundingBox())!.y;
  await page.mouse.down();
  await expect(page.getByText('Odabrano: 1')).toBeInViewport();
  await page.mouse.up();
  expect(Math.abs((await row.boundingBox())!.y - before)).toBeLessThanOrEqual(1);
  await page.keyboard.press('Escape');
  await row.click({ button: 'right' });
  await expect(page.getByRole('menuitem', { name: 'Premjesti u smeće' })).toBeVisible();
  await page.keyboard.press('Escape');
});

test('a passkey with PRF unlocks the vault without its password', async ({ page }) => {
  await cleared(page);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('WebAuthn.enable');
  await cdp.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      ctap2Version: 'ctap2_1',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      hasPrf: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  await page.goto('/settings/sign-in');
  const keys = page.getByRole('main');
  await keys.getByLabel('Naziv novog ključa').fill('Ključ sefa');
  await keys.getByRole('button', { name: 'Dodaj pristupni ključ' }).click();
  await expect(keys.getByRole('cell', { name: 'Ključ sefa' })).toBeVisible();

  await made(page);
  await page.getByRole('button', { name: 'Postavke sefa' }).click();
  const settings = page.getByRole('dialog', { name: 'Postavke sefa' });
  await settings.getByRole('button', { name: 'Dodaj pristupni ključ' }).click();
  await expect(settings.getByText('Ključ sefa')).toBeVisible();
  await page.keyboard.press('Escape');

  await locked(page);
  await page.getByRole('button', { name: 'Otključaj pristupnim ključem' }).click();
  await expect(page.getByRole('heading', { name: 'Moj sef' })).toBeVisible();
});
