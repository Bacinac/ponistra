import { readFile } from 'node:fs/promises';
import { inflateSync } from 'node:zlib';
import { expect, test } from './fixtures';
import { addTabs, newDocument } from './helpers/nodes';
import { DOCX, wordFile } from './helpers/word';

/** Each page's size in whole millimetres, as the PDF gives it. */
function pageSizes(pdf: Buffer): number[][] {
  return [...pdf.toString('latin1').matchAll(/\/MediaBox\s*\[\s*([^\]]+)\]/g)].map(([, box]) => {
    const [left, bottom, right, top] = box.trim().split(/\s+/).map(Number);
    return [right - left, top - bottom].map((points) => Math.round((points * 25.4) / 72));
  });
}

/** What each page draws, as Chromium writes it: the page's own placing of the CSS pixel grid, then
 * what stands on it. */
function drawings(pdf: Buffer): string[] {
  const text = pdf.toString('latin1');
  const drawn: string[] = [];
  for (const { index, 0: opening } of text.matchAll(/stream\r?\n/g)) {
    const start = index + opening.length;
    try {
      const body = inflateSync(pdf.subarray(start, text.indexOf('endstream', start)));
      if (body.includes(' cm')) drawn.push(body.toString('latin1'));
    } catch {}
  }
  return drawn;
}

const MOVE = /([-\d.]+) 0 0 ([-\d.]+) [-\d.]+ ([-\d.]+) cm/g;

/** How many points each page draws a CSS pixel in: 0.75 unless the browser shrank it to fit. */
function pixelSizes(pdf: Buffer): number[] {
  return drawings(pdf).map((drawn) => {
    const [page, pixels] = [...drawn.matchAll(MOVE)];
    return Math.round(Number(page[1]) * Number(pixels[1]) * 1000) / 1000;
  });
}

/** How far each page's first text stands from the top of its page, in CSS pixels: the same on every
 * page only where the browser breaks the pages where the tab's own layout does. */
function firstTextTops(pdf: Buffer): number[] {
  return drawings(pdf).map((drawn) => {
    const text = drawn.match(/ [-\d.]+ ([-\d.]+) Tm/)!;
    const [, , scale, shift] = [...drawn.slice(0, text.index).matchAll(MOVE)].at(-1)!;
    return Math.round((Number(text[1]) + Number(shift) / Number(scale)) * 100) / 100;
  });
}

test('the print lays every tab on its own paper, numbering the pages through them all', async ({
  page,
}) => {
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (
    await chooser
  ).setFiles({ name: 'Ugovor za ispis.docx', mimeType: DOCX, buffer: wordFile() });
  await page
    .getByRole('row', { name: /Ugovor za ispis/ })
    .getByText('Ugovor za ispis')
    .dblclick();
  const editor = page.locator('.ProseMirror').first();
  await editor.getByText('Drugi članak').click();
  await page.keyboard.press('End');
  for (const article of ['Treći', 'Četvrti', 'Peti']) {
    await page.keyboard.press('Control+Enter');
    await page.keyboard.type(`${article} članak`);
  }
  const address = new URL(page.url()).pathname;
  await addTabs(page, address, ['Prilog']);
  await page.goto(address);
  await page
    .getByRole('navigation', { name: 'Kartice' })
    .getByRole('link', { name: 'Prilog' })
    .click();
  await editor.click();
  await page.keyboard.type('Popis opreme');
  await page.getByRole('button', { name: 'Umetni' }).click();
  await page.getByRole('menuitem', { name: 'Fusnota', exact: true }).click();
  await page.keyboard.type('Prema ponudi');
  await page.keyboard.press('Escape');
  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Postavke stranice…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Postavke stranice' });
  await dialog.getByLabel('Ova kartica').selectOption({ label: 'Ima vlastite postavke' });
  await dialog.getByLabel('Položaj').selectOption('landscape');
  await dialog.getByRole('button', { name: 'Primijeni' }).click();
  await expect(dialog).toHaveCount(0);

  await page.addInitScript(() => {
    window.print = () => {
      window.top!.document.body.dataset.printDialog = 'shown';
    };
  });
  await page.reload();
  await expect(editor.getByText('Popis opreme')).toBeVisible();
  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Ispis…' }).click();
  await expect(page.locator('body')).toHaveAttribute('data-print-dialog', 'shown');
  await expect(page.getByText('Priprema ispisa…')).toHaveCount(0);

  const download = page.waitForEvent('download');
  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Spremi kao' }).click();
  await page.getByRole('menuitem', { name: 'PDF', exact: true }).click();
  const saved = await download;
  expect(saved.suggestedFilename()).toBe('Ugovor za ispis.pdf');
  const pdf = await readFile((await saved.path())!);
  await expect(page.getByText('Izrada datoteke…')).toHaveCount(0);

  await page.goto(`/print/${address.split('/')[2]}`);
  await expect(page.locator('body')).toHaveAttribute('data-printed', 'ready');
  await expect(page).toHaveTitle('Ugovor za ispis');
  const sheets = page.locator('.ponistra-printed');
  await expect(sheets).toHaveCount(2);
  await expect(sheets.first().locator('.ponistra-header')).toHaveText([
    'Stranica 1 od 6',
    'Stranica 2 od 6',
    'Stranica 3 od 6',
    'Stranica 4 od 6',
    'Stranica 5 od 6',
  ]);
  await expect(sheets.nth(1).locator('.ponistra-header')).toHaveText(['Stranica 6 od 6']);
  const last = (await sheets.nth(1).boundingBox())!;
  expect(last.width / last.height).toBeCloseTo(29.7 / 21, 2);
  const note = (await sheets.nth(1).locator('.ponistra-notes li').boundingBox())!;
  const cm = last.width / 29.7;
  expect(Math.abs(note.y + note.height - (last.y + last.height - 2.5 * cm))).toBeLessThan(2);
  for (const pageBreak of await page.locator('[data-page-break]').all())
    await expect(pageBreak).toBeHidden();

  expect(pageSizes(pdf)).toEqual([...Array(5).fill([210, 297]), [297, 210]]);
  expect(pixelSizes(pdf)).toEqual(Array(6).fill(0.75));
  const [top, ...rest] = firstTextTops(pdf);
  expect(rest).toEqual(Array(5).fill(top));
});

test('a section on other paper stands on pages of its own, its header the one before’s until it writes its own, and prints so', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 1400 });
  const address = await newDocument(page, 'Ugovor s prilogom');
  await page.goto(address);
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Ugovor');
  await page.getByRole('button', { name: 'Umetni' }).click();
  await page.getByRole('menuitem', { name: 'Prijelom odjeljka' }).click();
  await page.keyboard.type('Prilog');
  await expect(editor.locator('[data-section-break]')).toHaveCount(1);
  await page
    .getByRole('group', { name: 'Prikaz' })
    .getByRole('button', { name: 'Stranice' })
    .click();
  const papers = page.locator('.ponistra-paper');
  await expect(papers).toHaveCount(2);

  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Postavke stranice…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Postavke stranice' });
  const source = dialog.getByLabel('Ovaj odjeljak');
  await expect(source).toHaveValue('before');
  await source.selectOption('own');
  await dialog.getByLabel('Položaj').selectOption('landscape');
  await dialog.getByRole('button', { name: 'Primijeni' }).click();

  await expect
    .poll(async () => {
      const box = (await papers.nth(1).boundingBox())!;
      return box.width / box.height;
    })
    .toBeCloseTo(29.7 / 21, 2);
  const first = (await papers.first().boundingBox())!;
  const second = (await papers.nth(1).boundingBox())!;
  expect(Math.abs(first.x + first.width / 2 - (second.x + second.width / 2))).toBeLessThan(1);
  const cm = first.width / 21;
  for (const [text, paper] of [
    ['Ugovor', first],
    ['Prilog', second],
  ] as const) {
    const line = (await editor.getByText(text, { exact: true }).boundingBox())!;
    expect(Math.abs(line.x - paper.x - 2.5 * cm)).toBeLessThan(1);
    expect(Math.abs(line.y - paper.y - 2.5 * cm)).toBeLessThan(1);
  }

  await page.mouse.dblclick(first.x + first.width / 2, first.y + 0.8 * cm);
  const part = page.locator('.ponistra-part-open .ProseMirror');
  await expect(part).toBeFocused();
  await page.keyboard.type('Ugovor o isporuci');
  await page.keyboard.press('Escape');
  const headers = page.locator('.ponistra-papers > div > .ponistra-header');
  await expect(headers).toHaveText(['Ugovor o isporuci', 'Ugovor o isporuci']);

  await page.mouse.dblclick(second.x + second.width / 2, second.y + 0.8 * cm);
  await expect(part).toBeFocused();
  await page.getByRole('button', { name: 'Zaglavlje i podnožje' }).click();
  const linked = page.getByRole('menuitemcheckbox', { name: 'Poveži s prethodnim odjeljkom' });
  await expect(linked).toBeChecked();
  await linked.click();
  await expect(part).toHaveText('Ugovor o isporuci');
  await part.click();
  await page.keyboard.press('Control+a');
  await page.keyboard.type('Prilog ugovoru');
  await page.keyboard.press('Escape');
  await expect(headers).toHaveText(['Ugovor o isporuci', 'Prilog ugovoru']);
  await expect(editor.getByText('Ugovor', { exact: true })).toBeVisible();

  const download = page.waitForEvent('download');
  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Spremi kao' }).click();
  await page.getByRole('menuitem', { name: 'PDF', exact: true }).click();
  const pdf = await readFile((await (await download).path())!);
  expect(pageSizes(pdf)).toEqual([
    [210, 297],
    [297, 210],
  ]);

  await page.goto(`/print/${address.split('/')[2]}`);
  await expect(page.locator('body')).toHaveAttribute('data-printed', 'ready');
  const sheets = page.locator('.ponistra-printed');
  await expect(sheets).toHaveCount(2);
  await expect(sheets.first().locator('.ponistra-header')).toHaveText(['Ugovor o isporuci']);
  await expect(sheets.nth(1).locator('.ponistra-header')).toHaveText(['Prilog ugovoru']);
  await expect(sheets.first().getByText('Prilog', { exact: true })).toBeHidden();
  await expect(sheets.nth(1).getByText('Prilog', { exact: true })).toBeVisible();
  await expect(sheets.nth(1).getByText('Ugovor', { exact: true })).toBeHidden();
});
