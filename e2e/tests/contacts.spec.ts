import { expect, test } from './fixtures';

const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

test('a contact is made, found by any word, changed, given a photo and deleted', async ({
  page,
}) => {
  await page.goto('/');
  const rail = page.getByRole('navigation', { name: 'Moduli' });
  await rail.getByRole('link', { name: 'Razgovori' }).click();
  await page.getByRole('link', { name: 'Kontakti', exact: true }).click();
  await expect(page).toHaveURL(/\/contacts$/);
  await expect(rail.getByRole('link', { name: 'Razgovori' })).toHaveAttribute(
    'aria-current',
    'page',
  );

  await page.getByRole('button', { name: 'Novi kontakt' }).click();
  const made = page.getByRole('dialog', { name: 'Novi kontakt' });
  await made.getByLabel('Ime', { exact: true }).fill('Ana');
  await made.getByLabel('Prezime', { exact: true }).fill('Horvat');
  await made.getByLabel('Tvrtka', { exact: true }).fill('Brodogradilište d.o.o.');
  await made.getByRole('textbox', { name: 'E-pošta', exact: true }).fill('ana@brodo.test');
  await made.getByRole('textbox', { name: 'Telefon', exact: true }).fill('091 234 5678');
  await made.getByRole('spinbutton', { name: 'Dan' }).fill('14');
  await made.getByRole('combobox', { name: 'Mjesec' }).selectOption({ label: 'svibanj' });
  await made.getByRole('button', { name: 'Spremi' }).click();
  await expect(made).toBeHidden();

  const card = page.getByRole('article', { name: 'Ana Horvat' });
  await expect(card.getByRole('heading', { name: 'Ana Horvat' })).toBeVisible();
  await expect(card.getByText('Brodogradilište d.o.o.')).toBeVisible();
  await expect(card.getByText('14. svibnja', { exact: true })).toBeVisible();
  await expect(card.getByRole('link', { name: '+385 91 234 5678' })).toHaveAttribute(
    'href',
    'tel:+385912345678',
  );

  const search = page.getByRole('searchbox', { name: 'Traži kontakte' });
  for (const typed of ['horv', 'brodogradiliste', 'ana@', '091']) {
    await search.fill(typed);
    await expect(page.getByRole('link', { name: /Ana Horvat/ })).toBeVisible();
  }
  await search.fill('nitko');
  await expect(page.getByText('Nijedan kontakt ne odgovara traženju.')).toBeVisible();
  await search.fill('');

  await card.getByRole('button', { name: 'Uredi' }).click();
  const edited = page.getByRole('dialog', { name: 'Uredi kontakt' });
  await edited.getByLabel('Prezime', { exact: true }).fill('Kovač');
  await edited.getByRole('button', { name: 'Spremi' }).click();
  const renamed = page.getByRole('article', { name: 'Ana Kovač' });
  await expect(renamed.getByRole('heading', { name: 'Ana Kovač' })).toBeVisible();
  await expect(renamed.getByRole('link', { name: 'ana@brodo.test' })).toHaveAttribute(
    'href',
    `/mail?${new URLSearchParams({ to: 'ana@brodo.test', name: 'Ana Kovač' })}`,
  );

  await renamed.getByRole('button', { name: 'Radnje' }).click();
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.getByRole('menuitem', { name: 'Dodaj fotografiju' }).click(),
  ]);
  await chooser.setFiles({ name: 'ana.png', mimeType: 'image/png', buffer: PNG });
  await expect(renamed.locator('img')).toHaveAttribute('src', /\/photo\?v=[0-9a-f]{12}$/);
  await expect(page.getByRole('link', { name: /Ana Kovač/ }).locator('img')).toHaveAttribute(
    'src',
    /^data:image\/webp;base64,/,
  );
  await expect
    .poll(() => renamed.locator('img').evaluate((image: HTMLImageElement) => image.naturalWidth))
    .toBe(1);
  await renamed.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Ukloni fotografiju' }).click();
  await expect(renamed.locator('img')).toHaveCount(0);

  await renamed.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Izbriši kontakt' }).click();
  await page
    .getByRole('alertdialog', { name: 'Izbrisati kontakt?' })
    .getByRole('button', { name: 'Izbriši kontakt' })
    .click();
  await expect(page).toHaveURL(/\/contacts$/);
  await expect(page.getByRole('link', { name: /Ana Kovač/ })).toHaveCount(0);
});

test('a favourite is starred on its card and comes first in the list', async ({ page }) => {
  await page.goto('/contacts');
  for (const [given, family] of [
    ['Ksenija', 'Favorit'],
    ['Bruno', 'Abelić'],
  ]) {
    await page.getByRole('button', { name: 'Novi kontakt' }).click();
    const made = page.getByRole('dialog', { name: 'Novi kontakt' });
    await made.getByLabel('Ime', { exact: true }).fill(given);
    await made.getByLabel('Prezime', { exact: true }).fill(family);
    await made.getByRole('button', { name: 'Spremi' }).click();
    await expect(made).toBeHidden();
  }
  const rows = page.getByRole('link', { name: /Ksenija Favorit|Bruno Abelić/ });
  await expect(rows).toHaveText([/Bruno Abelić/, /Ksenija Favorit/]);

  await rows.filter({ hasText: 'Ksenija Favorit' }).click();
  const card = page.getByRole('article', { name: 'Ksenija Favorit' });
  await card.getByRole('button', { name: 'Dodaj u omiljene' }).click();
  await expect(card.getByRole('button', { name: 'Ukloni iz omiljenih' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(rows).toHaveText([/Ksenija Favorit/, /Bruno Abelić/]);
  await expect(rows.first().getByRole('img', { name: 'Omiljeni kontakt' })).toBeVisible();

  await page.reload();
  await expect(rows).toHaveText([/Ksenija Favorit/, /Bruno Abelić/]);
  await card.getByRole('button', { name: 'Ukloni iz omiljenih' }).click();
  await expect(rows).toHaveText([/Bruno Abelić/, /Ksenija Favorit/]);
  await expect(rows.getByRole('img', { name: 'Omiljeni kontakt' })).toHaveCount(0);

  await page.goto('/contacts');
  await rows.first().click({ modifiers: ['Control'] });
  await rows.nth(1).click();
  await expect(page.getByText('Odabrano: 2')).toBeVisible();
  const star = page.getByRole('button', { name: 'Dodaj u omiljene' });
  const unstar = page.getByRole('button', { name: 'Ukloni iz omiljenih' });
  await expect(unstar).toBeDisabled();
  await star.click();
  await expect(rows.getByRole('img', { name: 'Omiljeni kontakt' })).toHaveCount(2);
  await expect(star).toBeDisabled();
  await unstar.click();
  await expect(rows.getByRole('img', { name: 'Omiljeni kontakt' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Izbriši odabrane' }).click();
  await page
    .getByRole('alertdialog', { name: 'Izbrisati odabrane kontakte?' })
    .getByRole('button', { name: 'Izbriši odabrane' })
    .click();
  await expect(rows).toHaveCount(0);
});

test('an app password is shown once and lets a phone read the address book over CardDAV', async ({
  page,
}) => {
  await page.goto('/contacts');
  await page.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Kontakti na mobitelu…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Lozinke aplikacija' });
  await dialog.getByRole('button', { name: 'Lozinka za drugu aplikaciju…' }).click();
  const other = page.getByRole('dialog', { name: 'Lozinka za drugu aplikaciju' });
  await other.getByLabel('Naziv uređaja').fill('iPhone');
  await other.getByRole('button', { name: 'Napravi lozinku' }).click();
  const shown = other.getByLabel('Lozinka aplikacije');
  await expect(shown).toHaveText(/^[a-z2-9]{4}(-[a-z2-9]{4}){3}$/);
  await expect(other.getByText(new URL(page.url()).host, { exact: true })).toBeVisible();
  const password = (await shown.textContent())!;
  await other.getByRole('button', { name: 'Zatvori' }).click();
  await expect(other).toBeHidden();
  await expect(dialog.getByRole('cell', { name: 'iPhone' })).toBeVisible();

  const { user } = await (await page.request.get('/api/auth/session')).json();
  const phone = async () =>
    page.request.fetch('/dav/', {
      method: 'PROPFIND',
      headers: {
        Authorization: `Basic ${Buffer.from(`${user.email}:${password}`).toString('base64')}`,
        Depth: '0',
      },
    });
  expect((await phone()).status()).toBe(207);

  await dialog
    .getByRole('row', { name: /iPhone/ })
    .getByRole('button', { name: 'Radnje' })
    .click();
  await page.getByRole('menuitem', { name: 'Ukloni lozinku' }).click();
  await page
    .getByRole('alertdialog', { name: 'Ukloniti lozinku aplikacije?' })
    .getByRole('button', { name: 'Ukloni lozinku' })
    .click();
  await expect(dialog.getByRole('row', { name: /iPhone/ })).toHaveCount(0);
  expect((await phone()).status()).toBe(401);
});
