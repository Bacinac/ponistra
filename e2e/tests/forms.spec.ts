import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { pageAt, pdfFile, upload } from './helpers/pdf';

const application = () =>
  pdfFile({
    pages: [
      [
        { text: 'Zahtjev za najam opreme', top: 100 },
        { text: 'Ime', top: 175 },
        { text: 'Iznos', top: 215 },
        { text: 'Porez', top: 255 },
        { text: 'Ukupno', top: 295 },
        { text: 'Opremljen', top: 335 },
        { text: 'Placanje', top: 375 },
        { text: 'Grad', top: 415 },
        { text: 'Potpis', top: 480 },
      ],
    ],
    fields: [
      { kind: 'text', name: 'Ime', page: 1, left: 200, top: 160, width: 200 },
      { kind: 'text', name: 'Iznos', page: 1, left: 200, top: 200, width: 200, number: true },
      { kind: 'text', name: 'Porez', page: 1, left: 200, top: 240, width: 200, number: true },
      {
        kind: 'text',
        name: 'Ukupno',
        page: 1,
        left: 200,
        top: 280,
        width: 200,
        number: true,
        sum: ['Iznos', 'Porez'],
      },
      {
        kind: 'check',
        name: 'Opremljen',
        on: 'Da',
        page: 1,
        left: 200,
        top: 320,
        width: 16,
        height: 16,
      },
      {
        kind: 'radio',
        name: 'Plaćanje',
        options: ['Gotovina', 'Kartica'],
        page: 1,
        left: 200,
        top: 360,
        width: 16,
        height: 16,
      },
      {
        kind: 'combo',
        name: 'Grad',
        options: ['Zagreb', 'Split'],
        page: 1,
        left: 200,
        top: 400,
        width: 200,
      },
      { kind: 'signature', name: 'Potpis', page: 1, left: 200, top: 460, width: 200, height: 40 },
    ],
  });

const fieldOf = (page: Page, name: string) => pageAt(page, 1).locator(`[name="${name}"]`);

async function type(page: Page, name: string, text: string): Promise<void> {
  await fieldOf(page, name).click();
  await page.keyboard.press('ControlOrMeta+a');
  await page.keyboard.type(text);
  await page.keyboard.press('Tab');
}

test('a form is filled beside its file, live, its scripts reckoning, and its copy carries the values', async ({
  page,
  context,
}) => {
  await upload(page, 'Zahtjev s obrascem', application());
  await expect(fieldOf(page, 'Ime')).toBeEditable();

  await type(page, 'Ime', 'Ana Horvat');
  await type(page, 'Iznos', '1234,5');
  await type(page, 'Porez', '100');
  await expect(fieldOf(page, 'Iznos')).toHaveValue('1.234,50');
  await expect(fieldOf(page, 'Ukupno')).toHaveValue('1.334,50');
  await expect(fieldOf(page, 'Ukupno')).toBeDisabled();
  await fieldOf(page, 'Opremljen').check();
  await fieldOf(page, 'Plaćanje').nth(1).check();
  await fieldOf(page, 'Grad').selectOption('Split');

  const signature = pageAt(page, 1).locator('.ponistra-blocked');
  await expect(signature).toHaveAttribute('title', /Ponistra ne potpisuje dokumente/);

  const other = await context.newPage();
  await other.goto(page.url());
  await expect(fieldOf(other, 'Ime')).toHaveValue('Ana Horvat');
  await expect(fieldOf(other, 'Ukupno')).toHaveValue('1.334,50');
  await expect(fieldOf(other, 'Opremljen')).toBeChecked();
  await expect(fieldOf(other, 'Plaćanje').nth(1)).toBeChecked();
  await expect(fieldOf(other, 'Grad')).toHaveValue('Split');

  await type(other, 'Porez', '200');
  await expect(fieldOf(other, 'Ukupno')).toHaveValue('1.434,50');
  await expect(fieldOf(page, 'Porez')).toHaveValue('200,00');
  await expect(fieldOf(page, 'Ukupno')).toHaveValue('1.434,50');

  await other.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await other.keyboard.press('Control+z');
  await expect(fieldOf(page, 'Porez')).toHaveValue('100,00');
  await expect(fieldOf(page, 'Ukupno')).toHaveValue('1.334,50');
  await expect(fieldOf(page, 'Ime')).toHaveValue('Ana Horvat');

  await page.bringToFront();
  const downloading = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Preuzmi', exact: true }).click();
  const filled = await (await downloading).createReadStream();
  const bytes = Buffer.concat(await filled.toArray()).toString('latin1');
  for (const value of [
    '(Ana Horvat)',
    '(1234.5)',
    '(1334.5)',
    '/V /Da',
    '/V /Kartica',
    '(Split)',
  ]) {
    expect(bytes).toContain(value);
  }
  expect(bytes).toContain('/NeedAppearances true');
});
