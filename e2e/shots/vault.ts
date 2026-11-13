import { expect, type Page } from '@playwright/test';
import { shot } from './shot';

const PASSWORD = 'help-shot-vault-password';

const ITEMS = [
  { hr: 'Banka', en: 'Bank', username: 'marija.horvat', url: 'bank.example.com' },
  { hr: 'Porezna uprava', en: 'Tax office', username: 'mhorvat', url: 'tax.example.com' },
  { hr: 'Uredski Wi-Fi', en: 'Office Wi-Fi', username: 'ured', url: 'router.example.com' },
];

async function opened(page: Page): Promise<void> {
  await page.goto('/vault');
  const make = page.getByRole('button', { name: /^(Izradi sef|Make the vault)$/ });
  const unlock = page.getByRole('button', { name: /^(Otključaj|Unlock)$/ });
  await expect(make.or(unlock)).toBeVisible();
  if (await make.isVisible()) {
    await page.getByLabel(/^(Nova lozinka sefa|New vault password)$/).fill(PASSWORD);
    await page.getByLabel(/^(Ponovite lozinku|Repeat the password)$/).fill(PASSWORD);
    await make.click();
    await page.getByRole('button', { name: /^(Kod je spremljen|The code is kept)$/ }).click();
  } else {
    await page.getByLabel(/^(Lozinka sefa|Vault password)$/).fill(PASSWORD);
    await unlock.click();
  }
  const empty = page.getByText(/^(Zbirka je prazna\.|The collection is empty\.)$/);
  const listed = page.locator('main li a').first();
  await expect(empty.or(listed)).toBeVisible();
  if (!(await empty.isVisible())) return;
  const hr = (await page.locator('html').getAttribute('lang')) === 'hr';
  for (const item of ITEMS) {
    await page.getByRole('button', { name: /^(Nova stavka|New item)$/ }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel(/^(Naziv|Name)$/).fill(hr ? item.hr : item.en);
    await dialog.getByLabel(/^(Korisničko ime|Username)$/).fill(item.username);
    await dialog.getByLabel(/^(Lozinka|Password)$/).fill('Xq7!vR2#mL9pT4wZ');
    await dialog
      .getByLabel(/^(Adrese \(jedna po retku\)|Addresses \(one per line\))$/)
      .fill(item.url);
    await dialog.getByRole('button', { name: /^(Izradi|Create)$/ }).click();
    await expect(dialog).toBeHidden();
  }
}

shot('vault-open', async (page) => {
  await opened(page);
  await page.locator('main li a').first().click();
  await expect(
    page.getByRole('button', { name: /^(Kopiraj lozinku|Copy the password)$/ }),
  ).toBeVisible();
});
