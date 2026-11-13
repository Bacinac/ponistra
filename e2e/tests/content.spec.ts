import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { selectBack } from './helpers/editor';
import { newDocument } from './helpers/nodes';

const MOD = process.platform === 'darwin' ? 'Meta' : 'Control';

async function picture(page: Page): Promise<Buffer> {
  const data = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 400;
    canvas.height = 200;
    const paint = canvas.getContext('2d')!;
    paint.fillStyle = '#1d4ed8';
    paint.fillRect(0, 0, 400, 200);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  return Buffer.from(data, 'base64');
}

test('lists number themselves, nest with Tab and tick with a click', async ({ page }) => {
  await page.goto(await newDocument(page, 'Popisi'));
  const editor = page.locator('.ProseMirror');
  await editor.click();
  await page.keyboard.type('1. Prvi');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');
  await page.keyboard.type('Drugi');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.type('Treći');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  await page.keyboard.type('[] Kupiti cijevi');

  const numbered = editor.locator('p[data-list="number"]');
  await expect(numbered).toHaveText(['Prvi', 'Drugi', 'Treći']);
  expect(
    await numbered.evaluateAll((items) => items.map((item) => item.getAttribute('data-marker'))),
  ).toEqual(['1.', 'a.', '2.']);
  await numbered.nth(1).click();
  await page.getByRole('button', { name: 'Oblik popisa' }).click();
  await page.getByRole('menuitemcheckbox', { name: 'a)', exact: true }).click();
  await expect(numbered.nth(1)).toHaveAttribute('data-marker', 'a)');
  await expect(numbered.nth(2)).toHaveAttribute('data-marker', '2.');

  const check = editor.locator('p[data-list="check"]');
  await expect(check).toHaveText('Kupiti cijevi');
  const box = (await check.boundingBox())!;
  await page.mouse.click(box.x + 4, box.y + box.height / 2);
  await expect(check).toHaveAttribute('data-checked', 'true');
  await expect(check).toHaveCSS('text-decoration-line', 'line-through');

  await page.keyboard.press('End');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Napomena');
  await page.getByRole('button', { name: 'Popis s grafičkim oznakama' }).click();
  await expect(editor.locator('p[data-list="bullet"]')).toHaveAttribute('data-marker', '•');
  await page.getByRole('button', { name: 'Oblik popisa' }).click();
  await page.getByRole('menuitemcheckbox', { name: '–', exact: true }).click();
  await expect(editor.locator('p[data-list="bullet"]')).toHaveAttribute('data-marker', '–');
});

test('a list takes a format of its own at every level', async ({ page }) => {
  await page.goto(await newDocument(page, 'Ugovor s člancima'));
  const editor = page.locator('.ProseMirror');
  await editor.click();
  await page.keyboard.type('1. Opseg');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');
  await page.keyboard.type('Isporuka');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.type('Rokovi');

  await page.getByRole('button', { name: 'Oblik popisa' }).click();
  await page.getByRole('menuitem', { name: 'Prilagodi oblik popisa…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Prilagodi oblik popisa' });
  const levels = dialog.getByRole('navigation', { name: 'Razine' });
  const level = (name: string) => levels.getByRole('button', { name });
  await expect(level('Razina 1')).toHaveAttribute('aria-pressed', 'true');
  await expect(dialog.getByLabel('S brojevima viših razina (1.1.)')).toBeDisabled();
  await dialog.getByLabel('Ispred broja').fill('Članak ');
  await level('Razina 2').click();
  await dialog.getByLabel('Oznaka', { exact: true }).selectOption('Grafička oznaka');
  const symbol = dialog.getByLabel('Znak', { exact: true });
  await symbol.fill('');
  await expect(dialog.getByText('Svaka razina s grafičkom oznakom treba znak.')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Primijeni' })).toBeDisabled();
  const symbols = dialog.getByRole('group', { name: 'Česte oznake' });
  await symbols.getByRole('button', { name: '–' }).click();
  await expect(symbol).toHaveValue('–');
  const preview = dialog.getByRole('list', { name: 'Pregled' }).getByRole('listitem');
  await expect(preview.nth(0)).toContainText('Članak 1.');
  await expect(preview.nth(1)).toContainText('–');
  await dialog.getByRole('button', { name: 'Primijeni' }).click();
  await expect(dialog).toBeHidden();

  const items = editor.locator('p[data-list]');
  await expect(items).toHaveText(['Opseg', 'Isporuka', 'Rokovi']);
  await expect(items.nth(1)).toHaveAttribute('data-list', 'bullet');
  expect(
    await items.evaluateAll((all) => all.map((item) => item.getAttribute('data-marker'))),
  ).toEqual(['Članak 1.', '–', 'Članak 2.']);
});

test('an image uploaded among the documents stays a file, shows as itself and goes into a document from its folder', async ({
  page,
}) => {
  const buffer = await picture(page);
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles({ name: 'Plan kata.png', mimeType: 'image/png', buffer });
  const row = page.getByRole('row', { name: /Plan kata/ });
  await expect(row).toContainText('PNG datoteka');
  await row.getByText('Plan kata', { exact: true }).dblclick();

  const shown = page.getByRole('img', { name: 'Plan kata' });
  await expect.poll(() => shown.evaluate((found: HTMLCanvasElement) => found.width)).toBe(400);
  await expect(page.getByRole('link', { name: 'Preuzmi' })).toHaveAttribute(
    'href',
    /\/edited\?download=1$/,
  );
  await expect(page.getByRole('button', { name: 'Stranice' })).toHaveCount(0);

  await page.goto(await newDocument(page, 'Raspored ureda'));
  await page.locator('.ProseMirror').click();
  await page.getByRole('button', { name: 'Umetni' }).click();
  await page.getByRole('menuitem', { name: 'Slika' }).click();
  await page
    .getByRole('dialog', { name: 'Umetni sliku' })
    .getByText('Plan kata', { exact: true })
    .click();
  const img = page.locator('.ProseMirror figure[data-image] img');
  await expect.poll(() => img.evaluate((found: HTMLImageElement) => found.naturalWidth)).toBe(400);
});

test('an image is uploaded, resized, described and shown to another reader', async ({
  page,
  context,
}) => {
  const url = await newDocument(page, 'Slike');
  await page.goto(url);
  const editor = page.locator('.ProseMirror');
  await editor.click();
  await page.keyboard.type('Shema');
  const buffer = await picture(page);
  await page.getByRole('button', { name: 'Umetni' }).click();
  await page.getByRole('menuitem', { name: 'Slika' }).click();
  const chooser = page.waitForEvent('filechooser');
  await page
    .getByRole('dialog', { name: 'Umetni sliku' })
    .getByRole('button', { name: 'S računala…' })
    .click();
  await (await chooser).setFiles({ name: 'shema.png', mimeType: 'image/png', buffer });

  const img = editor.locator('figure[data-image] img');
  await expect(img).toBeVisible();
  await expect.poll(() => img.evaluate((found: HTMLImageElement) => found.naturalWidth)).toBe(400);

  await img.click();
  const handle = editor.locator('.ponistra-resize');
  const corner = (await handle.boundingBox())!;
  const column = (await editor.boundingBox())!.width;
  await page.mouse.move(corner.x + 6, corner.y + 6);
  await page.mouse.down();
  await page.mouse.move(corner.x + 6 - (400 - column / 2), corner.y + 6, { steps: 5 });
  await page.mouse.up();
  await expect(editor.locator('figure[data-image]')).toHaveAttribute('data-width', '50');

  await img.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Opis slike' }).click();
  const dialog = page.getByRole('dialog', { name: 'Opis slike' });
  await dialog.getByRole('textbox').fill('Plavi pravokutnik');
  await dialog.getByRole('button', { name: 'Spremi' }).click();
  await expect(img).toHaveAttribute('alt', 'Plavi pravokutnik');

  const other = await context.newPage();
  await other.goto(url);
  const theirs = other.locator('.ProseMirror figure[data-image] img');
  await expect(theirs).toHaveAttribute('alt', 'Plavi pravokutnik');
  await expect
    .poll(() => theirs.evaluate((found: HTMLImageElement) => found.naturalWidth))
    .toBe(400);
});

test('Ctrl+K links the text, the link opens from its popover, Alt+/ and Ctrl+K elsewhere search', async ({
  page,
}) => {
  const target = await newDocument(page, 'Cjenik usluga');
  await page.goto(await newDocument(page, 'Poveznice'));
  const editor = page.locator('.ProseMirror');
  await editor.click();
  await page.keyboard.type('Vidi www.example.com i cjenik');
  await expect(editor.locator('a[href="https://www.example.com/"]')).toHaveText('www.example.com');

  await selectBack(page, 'cjenik');
  await page.keyboard.press(`${MOD}+k`);
  const dialog = page.getByRole('dialog', { name: 'Poveznica' });
  await expect(dialog.getByLabel('Tekst')).toHaveValue('cjenik');
  await dialog.getByLabel('Ili potražite dokument').fill('Cjenik usl');
  await dialog.getByRole('button', { name: /Cjenik usluga/ }).click();
  await expect(dialog.getByLabel('Adresa')).toHaveValue(target);
  await dialog.getByRole('button', { name: 'Spremi' }).click();
  const link = editor.locator(`a[href="${target}"]`);
  await expect(link).toHaveText('cjenik');

  await page.keyboard.press('ArrowLeft');
  const popover = page.getByRole('toolbar', { name: 'Poveznica' });
  await popover.getByRole('button', { name: 'Otvori' }).click();
  await expect(page).toHaveURL(new RegExp(`${target}$`));

  await page.goBack();
  await expect(link).toHaveText('cjenik');
  const search = page.getByRole('combobox', { name: 'Pretraži' });
  await link.click();
  await page.keyboard.press('Alt+/');
  await expect(search).toBeFocused();
  await page.locator('main').click({ position: { x: 8, y: 8 } });
  await page.keyboard.press(`${MOD}+k`);
  await expect(search).toBeFocused();
});
