import { readFile } from 'node:fs/promises';
import { inflateSync } from 'node:zlib';
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';
import { pdfFile, upload } from './helpers/pdf';
import { unzipped } from './helpers/zip';

const priceList = () =>
  pdfFile({
    pages: [
      [{ text: 'Uvjeti cjenika', top: 100 }],
      [{ text: 'Cijena dostave', top: 100 }],
      [{ text: 'Popust za stalne kupce', top: 100 }],
    ],
  });

/** What the file's streams hold, unpacked where they are packed. */
function streams(pdf: Buffer): string {
  const text = pdf.toString('latin1');
  const found: string[] = [];
  for (const { index, 0: opening } of text.matchAll(/stream\r?\n/g)) {
    const start = index + opening.length;
    const body = pdf.subarray(start, text.indexOf('endstream', start));
    try {
      found.push(inflateSync(body).toString('latin1'));
    } catch {
      found.push(body.toString('latin1'));
    }
  }
  return found.join('\n');
}

async function saved(page: Page, format: string): Promise<Buffer> {
  const download = page.waitForEvent('download');
  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Spremi kao' }).click();
  await page.getByRole('menuitem', { name: format, exact: true }).click();
  return readFile((await (await download).path())!);
}

test('a PDF goes into a document as a copy of its pages, printed as they are and pictured for Word', async ({
  page,
}) => {
  await upload(page, 'Cjenik prijevoza', priceList());
  await page.goto(await newDocument(page, 'Ponuda s cjenikom'));
  const editor = page.locator('.ProseMirror');
  await editor.click();
  await page.keyboard.type('Uvod');
  await page.keyboard.press('Enter');

  await page.getByRole('button', { name: 'Umetni' }).click();
  await page.getByRole('menuitem', { name: 'PDF datoteka…' }).click();
  await page
    .getByRole('dialog', { name: 'Umetni PDF' })
    .getByText('Cjenik prijevoza', { exact: true })
    .click();
  const shown = editor.getByRole('figure', { name: 'Cjenik prijevoza' });
  const pages = shown.locator('.ponistra-pdf-page');
  await expect(pages).toHaveCount(3);
  await expect(pages.first().locator('canvas')).toBeVisible();
  await pages.last().scrollIntoViewIfNeeded();
  await expect(pages.locator('canvas')).toHaveCount(3);

  await shown.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Stranice…' }).click();
  const range = page.getByRole('dialog', { name: 'Stranice PDF-a' });
  await expect(range).toContainText('Stranica u datoteci: 3');
  await range.getByLabel('Od stranice').fill('2');
  await range.getByRole('button', { name: 'Spremi' }).click();
  await expect(pages).toHaveCount(2);
  await expect(pages.first()).toHaveAttribute('data-page', '2');
  await expect(editor).toBeFocused();

  await editor.locator('p').last().click();
  await page.keyboard.type('/pdf');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('option', { name: 'PDF datoteka…' }).click();
  await page
    .getByRole('dialog', { name: 'Umetni PDF' })
    .getByRole('button', { name: 'S računala…' })
    .click();
  await (
    await chooser
  ).setFiles({
    name: 'Prilog ponudi.pdf',
    mimeType: 'application/pdf',
    buffer: pdfFile({ pages: [[{ text: 'Rok isporuke', top: 100 }]] }),
  });
  await expect(
    editor.getByRole('figure', { name: 'Prilog ponudi' }).locator('canvas'),
  ).toBeVisible();

  const printed = await saved(page, 'PDF');
  const drawn = streams(printed);
  for (const text of ['Cijena dostave', 'Popust za stalne kupce', 'Rok isporuke']) {
    expect(drawn).toContain(text);
  }
  expect(drawn).not.toContain('Uvjeti cjenika');
  expect(printed.toString('latin1')).not.toContain('ponistra-pdf:');

  const word = unzipped(await saved(page, 'Word (.docx)'));
  expect(
    Object.keys(word)
      .filter((name) => name.startsWith('word/media/'))
      .sort(),
  ).toEqual(['word/media/page1.png', 'word/media/page2.png', 'word/media/page3.png']);
  expect(word['word/document.xml']).toContain('descr="Cjenik prijevoza · 2"');

  await page.goto('/documents');
  await expect(page.getByRole('row', { name: /Cjenik prijevoza/ })).toHaveCount(1);
  await expect(page.getByRole('row', { name: /Prilog ponudi/ })).toHaveCount(0);
});
