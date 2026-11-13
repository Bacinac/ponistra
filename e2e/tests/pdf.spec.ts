import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { pageAt, pdfFile, upload, type Line } from './helpers/pdf';

const COUNT = 20;
const WIDTH = (595 * 96) / 72;

function lease(): Buffer {
  const pages: Line[][] = Array.from({ length: COUNT }, (_, index) => [
    { text: `Dio ${index + 1}`, top: 72 },
  ]);
  pages[0].push({ text: 'Uvod', top: 110 }, { text: 'Ugovor o najmu prostora.', top: 140 });
  pages[2].push({ text: 'Teret se podize dizalicom.', top: 300 });
  pages[5].push({ text: 'Cijene', top: 110 });
  pages[8].push({ text: 'Placanje', top: 420 }, { text: 'Dostava dizalicom.', top: 450 });
  pages[11].push({ text: 'Skladistenje robe u prostoru.', top: 200 });
  return pdfFile({
    pages,
    bookmarks: [
      { title: 'Uvod', page: 1, top: 100 },
      { title: 'Cijene', page: 6, top: 100, under: [{ title: 'Plaćanje', page: 9, top: 400 }] },
    ],
    notes: [{ page: 1, left: 480, top: 100, text: 'Provjeriti iznos najma.', author: 'Ana' }],
    padding: 120_000,
  });
}

const shownPage = (page: Page) => page.getByLabel('Stranica', { exact: true });

test('a PDF opens in its pages, fetching only the parts it shows, with its bookmarks, zoom and find', async ({
  page,
}) => {
  test.slow();
  const file = lease();
  const ranges: number[] = [];
  const data: string[] = [];
  page.on('response', (response) => {
    const { pathname } = new URL(response.url());
    if (pathname.startsWith('/assets/pdfjs-')) data.push(`${response.status()} ${pathname}`);
    if (!/\/api\/nodes\/[^/]+\/file$/.test(pathname)) return;
    const range = response.headers()['content-range'];
    if (response.status() === 206 && range) {
      const [, first, last] = range.match(/bytes (\d+)-(\d+)\//)!;
      ranges.push(Number(last) - Number(first) + 1);
    }
  });
  await upload(page, 'Najam', file);

  await expect(pageAt(page, 1).locator('.textLayer')).toContainText('Ugovor o najmu prostora.');
  await expect(pageAt(page, 1)).toHaveAttribute('aria-label', 'Stranica 1');
  const note = pageAt(page, 1).getByRole('img', { name: 'Bilješka' });
  await expect.poll(() => note.evaluate((icon: HTMLImageElement) => icon.naturalWidth)).toBe(40);
  expect(data.filter((each) => !each.startsWith('200 '))).toEqual([]);
  await note.hover();
  const popup = pageAt(page, 1).locator('.popupAnnotation .popup');
  await expect(popup).toBeVisible();
  await expect(popup).toContainText('Ana');
  await expect(popup).toContainText('Provjeriti iznos najma.');
  await expect(popup.locator('time')).toHaveText(/^19\. lis 2026\. \d\d:00$/);
  await expect(shownPage(page)).toHaveValue('1');
  await expect(page.getByText(`od ${COUNT}`)).toBeVisible();
  expect(ranges.length).toBeGreaterThan(0);
  expect(ranges.reduce((sum, each) => sum + each, 0)).toBeLessThan(file.length / 3);

  const width = async () => (await pageAt(page, 1).boundingBox())!.width;
  const room = await page.locator('.pdfViewer').evaluate((viewer) => {
    const { paddingLeft, paddingRight } = getComputedStyle(viewer);
    return viewer.clientWidth - parseFloat(paddingLeft) - parseFloat(paddingRight);
  });
  expect(await width()).toBeCloseTo(WIDTH, 0);
  await page.getByRole('button', { name: 'Širina stranice' }).click();
  await expect.poll(width).toBeCloseTo(room, 0);
  await page.getByRole('button', { name: 'Stvarna veličina (100 %)' }).click();
  await expect.poll(width).toBeCloseTo(WIDTH, 0);

  const headings = page.getByRole('list', { name: 'Naslovi' });
  await expect(headings.getByRole('link')).toHaveText(['Uvod', 'Cijene', 'Plaćanje']);
  await expect(headings.getByRole('link', { name: 'Uvod' })).toHaveAttribute(
    'aria-current',
    'location',
  );
  await headings.getByRole('link', { name: 'Plaćanje' }).click();
  await expect(page).toHaveURL(/\?heading=2\.1$/);
  await expect(shownPage(page)).toHaveValue('9');
  await expect(headings.getByRole('link', { name: 'Plaćanje' })).toHaveAttribute(
    'aria-current',
    'location',
  );
  await expect(pageAt(page, 9).getByText('Placanje')).toBeInViewport();

  await shownPage(page).fill('6');
  await shownPage(page).press('Enter');
  await expect(pageAt(page, 6).getByText('Cijene')).toBeInViewport();
  await expect(headings.getByRole('link', { name: 'Cijene' })).toHaveAttribute(
    'aria-current',
    'location',
  );

  await page.keyboard.press('Control+f');
  const find = page.getByRole('searchbox', { name: 'Traži u datoteci' });
  await expect(find).toBeFocused();
  await find.fill('dizalicom');
  const status = page.getByRole('search').locator('[aria-live]');
  await expect(status).toHaveText('2 od 2');
  await expect(pageAt(page, 9).locator('.highlight.selected')).toHaveText('dizalicom');
  await expect(shownPage(page)).toHaveValue('9');
  await find.press('Shift+Enter');
  await expect(status).toHaveText('1 od 2');
  await expect(pageAt(page, 3).locator('.highlight.selected')).toBeInViewport();
  await find.fill('kamionom');
  await expect(status).toHaveText('Nema pogodaka');
  await find.press('Escape');
  await expect(find).toHaveCount(0);
  await expect(page.locator('.pdfViewer .highlight')).toHaveCount(0);

  await expect
    .poll(
      async () => {
        const response = await page.request.get('/api/search?q=skladistenje');
        return (await response.json()).documents.length;
      },
      { timeout: 90_000 },
    )
    .toBe(1);
  const search = page.getByRole('combobox', { name: 'Pretraži' });
  await search.fill('skladistenje');
  await page.getByRole('option', { name: /Najam/ }).click();
  await expect(page).toHaveURL(/\?page=12&find=Skladistenje$/);
  await expect(shownPage(page)).toHaveValue('12');
  await expect(page.getByRole('search').locator('[aria-live]')).toHaveText('1 od 1');
  await expect(pageAt(page, 12).locator('.highlight.selected')).toHaveText('Skladistenje');
  await expect(pageAt(page, 12).locator('.highlight.selected')).toBeInViewport();
});

test('a PDF locked by a password opens once it is given', async ({ page }) => {
  const file = pdfFile({ pages: [[{ text: 'Povjerljivo', top: 100 }]], password: 'tajna' });
  await upload(page, 'Zaključano', file);

  const dialog = page.getByRole('dialog', { name: 'Datoteka je zaštićena lozinkom' });
  await dialog.getByRole('button', { name: 'Odustani' }).click();
  await expect(page.getByRole('link', { name: 'Preuzmi', exact: true })).toHaveAttribute(
    'href',
    /\/noted\?download=1$/,
  );
  await expect(page.getByText('Datoteka je zaštićena lozinkom')).toBeVisible();
  await page.getByRole('button', { name: 'Otvori', exact: true }).click();

  await dialog.getByLabel('Lozinka').fill('kriva');
  await dialog.getByRole('button', { name: 'Otvori' }).click();
  await expect(dialog.getByText('Lozinka nije točna.')).toBeVisible();
  await dialog.getByLabel('Lozinka').fill('tajna');
  await dialog.getByRole('button', { name: 'Otvori' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(pageAt(page, 1).locator('.textLayer')).toContainText('Povjerljivo');
});
