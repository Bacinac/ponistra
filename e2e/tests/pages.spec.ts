import type { Locator, Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';
import { DOCX, wordFile, wordLines } from './helpers/word';

const sentence =
  'Ugovorne strane suglasno utvrđuju da se ovim ugovorom uređuju međusobna prava i obveze u vezi s isporukom robe, rokovima plaćanja i jamstvom za nedostatke. ';

function pasted(page: Page, html: string): Promise<void> {
  return page.evaluate((html) => {
    const data = new DataTransfer();
    data.setData('text/html', html);
    data.setData('text/plain', html);
    document
      .querySelector('.ProseMirror')!
      .dispatchEvent(
        new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }),
      );
  }, html);
}

function showPages(page: Page): Promise<void> {
  return page
    .getByRole('group', { name: 'Prikaz' })
    .getByRole('button', { name: 'Stranice' })
    .click();
}

test('a Word file opens on its pages, each headed with its number, and a page break starts one', async ({
  page,
}) => {
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (
    await chooser
  ).setFiles({ name: 'Ugovor na stranicama.docx', mimeType: DOCX, buffer: wordFile() });
  await page
    .getByRole('row', { name: /Ugovor na stranicama/ })
    .getByText('Ugovor na stranicama')
    .dblclick();
  const editor = page.locator('.ProseMirror').first();
  await expect(editor.locator('[data-page-break]')).toHaveCount(1);
  const view = page.getByRole('group', { name: 'Prikaz' });
  await expect(view.getByRole('button', { name: 'Stranice' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  const headers = page.locator('.ponistra-header');
  await expect(headers).toHaveText(['Stranica 1 od 2', 'Stranica 2 od 2']);

  const second = editor.getByText('Drugi članak');
  const top = async () =>
    (await second.boundingBox())!.y -
    (await page.locator('.ponistra-paper').nth(1).boundingBox())!.y;
  expect(Math.abs((await top()) - (2.5 * 96) / 2.54)).toBeLessThan(1);

  await page.reload();
  await expect(view.getByRole('button', { name: 'Stranice' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(headers).toHaveText(['Stranica 1 od 2', 'Stranica 2 od 2']);

  await editor.getByText('Prvi članak').click();
  await page.keyboard.press('End');
  await page.keyboard.press('Control+Enter');
  await page.keyboard.type('Novi članak');
  await expect(headers).toHaveText(['Stranica 1 od 3', 'Stranica 2 od 3', 'Stranica 3 od 3']);
  const third = editor.getByText('Novi članak');
  const paper = page.locator('.ponistra-paper').nth(1);
  expect(
    Math.abs((await third.boundingBox())!.y - (await paper.boundingBox())!.y - (2.5 * 96) / 2.54),
  ).toBeLessThan(1);

  await view.getByRole('button', { name: 'Tekst' }).click();
  await expect(page.locator('.ponistra-paper')).toHaveCount(0);
  await expect(editor.locator('[data-page-break]')).toHaveCount(2);
});

test('a tab nobody has laid out on its pages is counted by the server, so the pages number on through it', async ({
  page,
}) => {
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (
    await chooser
  ).setFiles({ name: 'Ugovor s prilogom.docx', mimeType: DOCX, buffer: wordFile() });
  await page
    .getByRole('row', { name: /Ugovor s prilogom/ })
    .getByText('Ugovor s prilogom')
    .dblclick();
  const into = page.waitForEvent('filechooser');
  await page
    .getByRole('navigation', { name: 'Putanja' })
    .getByRole('button', { name: 'Ugovor s prilogom' })
    .click();
  await page.getByRole('menuitem', { name: 'Uvezi u ovaj dokument…' }).click();
  await (await into).setFiles({ name: 'Prilog.docx', mimeType: DOCX, buffer: wordFile() });
  await page
    .getByRole('dialog', { name: 'Izvještaj o uvozu' })
    .getByRole('button', { name: 'Zatvori' })
    .click();
  const tabs = page.getByRole('navigation', { name: 'Kartice' }).getByRole('link');
  await expect(tabs).toHaveCount(2);
  await tabs.first().click();

  await showPages(page);
  await expect(page.locator('.ponistra-header')).toHaveText(
    ['Stranica 1 od 4', 'Stranica 2 od 4'],
    {
      timeout: 30_000,
    },
  );
});

test('a long text breaks between lines and table rows, none of them in a margin, on white paper in either theme', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Dugi ugovor'));
  await page.locator('.ProseMirror').first().click();
  const rows = Array.from(
    { length: 40 },
    (_, index) => `<tr><td>Stavka ${index + 1}</td><td>${(index + 1) * 12}</td></tr>`,
  ).join('');
  const paragraphs = Array.from(
    { length: 6 },
    (_, index) => `<p>${index + 1}. ${sentence.repeat(6)}</p>`,
  );
  await pasted(
    page,
    `<h1>Ugovor</h1>${paragraphs.join('')}<table><tbody>${rows}</tbody></table>${paragraphs.join('')}`,
  );
  await expect(page.getByRole('grid')).toHaveAttribute('aria-rowcount', '41');
  await showPages(page);

  await expect.poll(() => page.locator('.ponistra-paper').count()).toBeGreaterThan(2);
  await expect(page.locator('span.ponistra-page-gap').first()).toBeAttached();
  await expect(page.locator('.ponistra-table .ponistra-page-gap').first()).toBeAttached();

  const outside = () =>
    page.evaluate(() => {
      const pages = [...document.querySelectorAll('.ponistra-paper')].map((paper) => {
        const box = paper.getBoundingClientRect();
        const margin = (box.width / 21) * 2.5;
        return { top: box.top + margin - 1, bottom: box.bottom - margin + 1 };
      });
      const range = document.createRange();
      const walker = document.createTreeWalker(
        document.querySelector('.ProseMirror')!,
        NodeFilter.SHOW_TEXT,
      );
      const strays: string[] = [];
      for (let text = walker.nextNode(); text; text = walker.nextNode()) {
        // A table's letters and numbers follow the view down the table, margins included.
        if (text.parentElement!.closest('[role="columnheader"], [role="rowheader"]')) continue;
        range.selectNodeContents(text);
        for (const box of range.getClientRects()) {
          if (!box.height) continue;
          if (!pages.some((each) => box.top >= each.top && box.bottom <= each.bottom)) {
            strays.push(text.textContent!.slice(0, 20));
          }
        }
      }
      return strays;
    });
  await expect.poll(outside).toEqual([]);

  await page.emulateMedia({ colorScheme: 'dark' });
  const paper = page.locator('.ponistra-paper').first();
  await expect(paper).toHaveCSS('background-color', 'rgb(255, 255, 255)');
  await expect(page.locator('.ProseMirror p').first()).toHaveCSS('color', 'rgb(23, 62, 70)');

  await page.getByRole('button', { name: 'Širina stranice' }).click();
  await expect.poll(async () => (await paper.boundingBox())!.width).toBeGreaterThan(900);
  await expect.poll(outside).toEqual([]);
});

test('a page that starts on an empty line keeps the line, and the pages stay as they are laid out', async ({
  page,
}) => {
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (
    await chooser
  ).setFiles({
    name: 'Prazni retci.docx',
    mimeType: DOCX,
    buffer: wordLines(sentence.repeat(8), 90, 'Kraj.'),
  });
  await page
    .getByRole('row', { name: /Prazni retci/ })
    .getByText('Prazni retci')
    .dblclick();
  await showPages(page);
  const paragraph = page.locator('.ProseMirror p').first();
  await expect(paragraph.locator('span.ponistra-page-gap').first()).toBeAttached();

  const laid = () =>
    paragraph.evaluate(async (p) => {
      const frames = [];
      for (let frame = 0; frame < 3; frame++) {
        await new Promise(requestAnimationFrame);
        const gaps = [...p.querySelectorAll<HTMLElement>('.ponistra-page-gap')];
        const height = (element: Element) => element.getBoundingClientRect().height;
        const shown = height(p) - gaps.reduce((sum, gap) => sum + height(gap), 0);
        const widgets = gaps.map((gap) => gap.closest<HTMLElement>('.ProseMirror-widget')!);
        for (const widget of widgets) widget.style.display = 'none';
        const written = height(p);
        for (const widget of widgets) widget.style.display = '';
        frames.push({
          lost: Math.round(written - shown),
          gaps: gaps.map((gap) => Math.round(gap.getBoundingClientRect().top)),
        });
      }
      return frames;
    });
  const [first, ...next] = await laid();
  expect(first.lost).toBe(0);
  expect(next).toEqual([first, first]);
});

test('the frozen rows head a table again atop each page it runs onto, in the Pages view and in print', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto(await newDocument(page, 'Cjenik'));
  await page.locator('.ProseMirror').first().click();
  const rows = Array.from(
    { length: 60 },
    (_, index) => `<tr><td>Stavka ${index + 1}</td><td>${(index + 1) * 12}</td></tr>`,
  ).join('');
  await pasted(
    page,
    `<p>Cjenik</p><table><tbody><tr><td><p>Artikl</p><p>(naziv)</p></td><td>Iznos</td></tr>${rows}</tbody></table>`,
  );
  const table = page.locator('.ponistra-table');
  await expect(table.getByRole('grid')).toHaveAttribute('aria-rowcount', '62');
  await table.locator('[role="gridcell"][data-address="A2"]').click();
  const command = async (name: string) => {
    await page.getByRole('button', { name: 'Tablica' }).click();
    await page.getByRole('menuitem', { name }).click();
  };
  await command('Zamrzni retke iznad');
  await showPages(page);

  const gaps = table.locator('.ponistra-page-gap');
  const copies = table.locator('.ponistra-page-gap .ponistra-cell-box');
  await expect(copies.first()).toHaveText('Artikl(naziv)');
  await expect.poll(() => gaps.count()).toBeGreaterThan(1);
  expect(await copies.count()).toBe(await gaps.count());
  const second = (await page.locator('.ponistra-paper').nth(1).boundingBox())!;
  const copy = (await copies.first().boundingBox())!;
  expect(Math.abs(copy.y - (second.y + (second.width / 21) * 2.5))).toBeLessThan(2);

  await table.locator('[role="gridcell"][data-address="B2"]').click();
  await command('Odmrzni retke');
  await expect(copies).toHaveCount(0);
  await command('Zamrzni retke iznad');
  await expect(copies.first()).toHaveText('Artikl(naziv)');

  await page.goto(`/print/${new URL(page.url()).pathname.split('/')[2]}`);
  const body = page.locator('body');
  await expect(body).toHaveAttribute('data-printed', 'ready');
  const sheet = (await page.locator('.ponistra-printed').boundingBox())!;
  const repeated = page.locator('tr.ponistra-repeated');
  const drawn = page.locator('.ponistra-printed tr');
  await expect(drawn).toHaveCount(0);
  await page.evaluate(() => dispatchEvent(new Event('beforeprint')));
  await expect(repeated.first()).toHaveText('Artikl(naziv)Iznos');
  const height = (sheet.width / 21) * 29.7;
  const headed = async () => {
    for (const row of await repeated.all()) {
      const box = (await row.boundingBox())!;
      expect(Math.abs(((box.y - sheet.y) % height) - (sheet.width / 21) * 2.5)).toBeLessThan(2);
    }
  };
  await headed();
  const headers = await repeated.count();
  expect(headers).toBeGreaterThan(0);
  expect(await drawn.count()).toBe(61 + headers);

  await body.evaluate((body) => (body.dataset.range = '2-2'));
  await expect(body).toHaveAttribute('data-ranged', '2-2');
  await expect(repeated).toHaveCount(1);
  await headed();
  const ranged = (await repeated.boundingBox())!;
  expect(ranged.y - sheet.y).toBeGreaterThan(height);
  expect(ranged.y - sheet.y).toBeLessThan(2 * height);
});

test('the page setup turns the page and narrows its margins, never past room for text', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Položeni ugovor'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Prvi članak');
  await showPages(page);
  const paper = page.locator('.ponistra-paper').first();
  await expect(paper).toBeVisible();

  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Postavke stranice…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Postavke stranice' });
  await expect(dialog.getByLabel('Ova kartica')).toHaveCount(0);
  await expect(dialog.getByLabel('Papir')).toHaveValue('a4');
  await dialog.getByLabel('Položaj').selectOption('landscape');
  await expect(dialog.getByLabel('Širina (cm)')).toHaveValue('29.7');
  await dialog.getByLabel('Margine').selectOption('narrow');
  const left = dialog.getByLabel('Lijevo (cm)');
  await expect(left).toHaveValue('1.27');
  await left.fill('28');
  await expect(
    dialog.getByText('Uz ove margine na stranici ne ostaje mjesta za tekst.'),
  ).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Primijeni' })).toBeDisabled();
  await left.fill('1.27');
  await expect(dialog.getByLabel('Margine')).toHaveValue('narrow');
  await dialog.getByRole('button', { name: 'Primijeni' }).click();

  await expect
    .poll(async () => {
      const box = (await paper.boundingBox())!;
      return box.width / box.height;
    })
    .toBeCloseTo(29.7 / 21, 2);
  const box = (await paper.boundingBox())!;
  const text = (await editor.getByText('Prvi članak').boundingBox())!;
  const cm = box.width / 29.7;
  expect(Math.abs(text.x - box.x - 1.27 * cm)).toBeLessThan(1);
  expect(Math.abs(text.y - box.y - 1.27 * cm)).toBeLessThan(1);
});

test('a header is written on its page with fields, pushes the text down when tall, and the first page can have its own', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1600, height: 2400 });
  await page.goto(await newDocument(page, 'Zaglavlja'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await pasted(
    page,
    Array.from({ length: 12 }, (_, index) => `<p>${index + 1}. ${sentence.repeat(5)}</p>`).join(''),
  );
  await showPages(page);
  await expect.poll(() => page.locator('.ponistra-paper').count()).toBeGreaterThan(1);
  const papers = page.locator('.ponistra-paper');
  const count = await papers.count();

  const second = (await papers.nth(1).boundingBox())!;
  const cm = second.width / 21;
  await page.mouse.dblclick(second.x + second.width / 2, second.y + 0.8 * cm);
  const open = page.locator('.ponistra-part-open');
  await expect(open.locator('.ponistra-part-label')).toHaveText('Zaglavlje');
  const part = open.locator('.ProseMirror');
  await expect(part).toBeFocused();
  await page.keyboard.type('Ugovor, stranica ');
  const insert = (name: string) =>
    page
      .getByRole('button', { name: 'Umetni' })
      .click()
      .then(() => page.getByRole('menuitem', { name }).click());
  await insert('Broj stranice');
  await page.keyboard.type(' od ');
  await insert('Broj stranica');
  await expect(part).toHaveText(`Ugovor, stranica 2 od ${count}`);
  // Typing is grouped into one step only while it comes quickly, so it takes as many as it made.
  let steps = 0;
  await expect(async () => {
    await page.keyboard.press('Control+z');
    steps += 1;
    await expect(part).toHaveText('', { timeout: 1000 });
  }).toPass();
  await expect(editor.locator('p')).toHaveCount(12);
  for (let step = 0; step < steps; step += 1) await page.keyboard.press('Control+Shift+z');
  await expect(part).toHaveText(`Ugovor, stranica 2 od ${count}`);
  await page.keyboard.press('Escape');
  await expect(open).toHaveCount(0);
  await expect(editor).toBeFocused();

  const headers = page.locator('.ponistra-papers > div > .ponistra-header');
  await expect(headers).toHaveText(
    Array.from({ length: count }, (_, index) => `Ugovor, stranica ${index + 1} od ${count}`),
  );

  const first = editor.locator('p').first();
  const offset = async () =>
    (await first.boundingBox())!.y - (await papers.first().boundingBox())!.y;
  expect(Math.abs((await offset()) - 2.5 * cm)).toBeLessThan(1);
  await first.click();
  await insert('Zaglavlje');
  await expect(open.locator('.ponistra-part-label')).toHaveText('Zaglavlje');
  await page.keyboard.press('Control+End');
  for (const line of ['Drugi redak', 'Treći redak', 'Četvrti redak']) {
    await page.keyboard.press('Enter');
    await page.keyboard.type(line);
  }
  await expect
    .poll(async () => {
      const header = (await open.boundingBox())!;
      return Math.abs(
        (await offset()) - (header.y + header.height - (await papers.first().boundingBox())!.y),
      );
    })
    .toBeLessThan(1);
  expect(await offset()).toBeGreaterThan(2.5 * cm);

  await page.getByRole('button', { name: 'Zaglavlje i podnožje' }).click();
  await page.getByRole('menuitemcheckbox', { name: 'Drukčija prva stranica' }).click();
  await expect(open.locator('.ponistra-part-label')).toHaveText('Zaglavlje prve stranice');
  await expect(part).toHaveText('');
  await page.keyboard.press('Escape');
  await expect(headers.first()).toHaveText('');
  await expect(headers.nth(1)).toContainText('Četvrti redak');
  await expect.poll(async () => Math.abs((await offset()) - 2.5 * cm)).toBeLessThan(1);
});

async function dragged(page: Page, handle: Locator, by: { x?: number; y?: number }) {
  const box = (await handle.boundingBox())!;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + (by.x ?? 0), y + (by.y ?? 0), { steps: 6 });
  await page.mouse.up();
}

test('the rulers move the margins and the paragraph’s indents to a quarter centimetre', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Ravnalo'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type(sentence.repeat(2).trim());
  await page.keyboard.press('Enter');
  await page.keyboard.type('Drugi odlomak');
  await showPages(page);
  const paper = page.locator('.ponistra-paper').first();
  const across = page.getByRole('group', { name: 'Vodoravno ravnalo' });
  const down = page.getByRole('group', { name: 'Okomito ravnalo' });
  await expect(across).toBeVisible();
  await expect(down).toBeVisible();
  const sheet = (await paper.boundingBox())!;
  const ruler = (await across.boundingBox())!;
  expect(Math.abs(ruler.x - sheet.x)).toBeLessThan(1);
  expect(Math.abs(ruler.width - sheet.width)).toBeLessThan(1);
  const cm = sheet.width / 21;

  const left = across.getByRole('slider', { name: 'Lijeva margina' });
  await expect(left).toHaveAttribute('aria-valuenow', '2.5');
  await dragged(page, left, { x: 1.1 * cm });
  await expect(left).toHaveAttribute('aria-valuenow', '3.5');
  const second = editor.locator('p').nth(1);
  await expect
    .poll(async () => ((await second.boundingBox())!.x - sheet.x) / cm)
    .toBeCloseTo(3.5, 1);

  await editor.locator('p').first().click();
  await dragged(page, across.getByRole('slider', { name: 'Uvlaka prvog retka' }), {
    x: 1.3 * cm,
  });
  const first = editor.locator('p').first();
  await expect(first).toHaveAttribute('data-first-line', '1.25');
  await dragged(page, across.getByRole('slider', { name: 'Viseća uvlaka' }), { x: 2 * cm });
  await expect(first).toHaveAttribute('data-indent', '2');
  await expect(first).toHaveAttribute('data-first-line', '-0.75');
  await expect(second).not.toHaveAttribute('data-indent');
  await page.screenshot({ path: '/tmp/results/rulers.png' });

  const right = across.getByRole('slider', { name: 'Desna uvlaka' });
  await right.focus();
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('ArrowLeft');
  await expect(first).toHaveAttribute('data-right', '0.5');

  const top = down.getByRole('slider', { name: 'Gornja margina' });
  await dragged(page, top, { y: cm });
  await expect(top).toHaveAttribute('aria-valuenow', '3.5');
  await expect
    .poll(async () => ((await first.boundingBox())!.y - (await paper.boundingBox())!.y) / cm)
    .toBeCloseTo(3.5, 1);
});

test('tab stops set on the ruler line up what follows a tab, and leave when dragged off', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Tabulatori'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Ukupno');
  await page.keyboard.press('Tab');
  await page.keyboard.type('1234,5');
  await showPages(page);
  const first = editor.locator('p').first();
  await expect(first.locator('.ponistra-tab')).toHaveCount(1);
  const paper = page.locator('.ponistra-paper').first();
  const across = page.getByRole('group', { name: 'Vodoravno ravnalo' });
  const sheet = (await paper.boundingBox())!;
  const cm = sheet.width / 21;
  const fromPaper = (x: number) => (x - sheet.x) / cm;
  const end = () =>
    first.evaluate((paragraph) => {
      const range = document.createRange();
      range.selectNodeContents(paragraph);
      return Math.max(...[...range.getClientRects()].map((rect) => rect.right));
    });
  const comma = () =>
    first.evaluate((paragraph) => {
      const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
      for (let text = walker.nextNode(); text; text = walker.nextNode()) {
        const found = text.textContent!.indexOf(',');
        if (found < 0) continue;
        const range = document.createRange();
        range.setStart(text, found);
        range.setEnd(text, found + 1);
        return range.getBoundingClientRect().left;
      }
      return NaN;
    });
  const tabEnd = async () => {
    const box = (await first.locator('.ponistra-tab').boundingBox())!;
    return fromPaper(box.x + box.width);
  };
  await expect.poll(tabEnd).toBeCloseTo(2.5 + 2 * 1.25, 1);

  const kind = page.getByRole('button', { name: /^Vrsta tabulatora/ });
  await expect(kind).toHaveAccessibleName('Vrsta tabulatora: Lijevi tabulator');
  await kind.click();
  await kind.click();
  await expect(kind).toHaveAccessibleName('Vrsta tabulatora: Desni tabulator');
  const ruler = (await across.boundingBox())!;
  await page.mouse.click(sheet.x + 10.6 * cm, ruler.y + ruler.height / 2);
  const stop = across.getByRole('slider', { name: /tabulator$/ });
  await expect(stop).toHaveAccessibleName('Desni tabulator');
  await expect(stop).toHaveAttribute('aria-valuenow', '8');
  await expect.poll(async () => fromPaper(await end())).toBeCloseTo(10.5, 1);

  await stop.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Decimalni tabulator' }).click();
  await expect(stop).toHaveAccessibleName('Decimalni tabulator');
  await expect.poll(async () => fromPaper(await comma())).toBeCloseTo(10.5, 1);
  await stop.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Vodilica' }).click();
  await page.getByRole('menuitem', { name: 'Točkice' }).click();
  await expect(first.locator('.ponistra-tab')).toHaveAttribute('data-leader', 'dot');

  await dragged(page, stop, { x: 2 * cm });
  await expect(stop).toHaveAttribute('aria-valuenow', '10');
  await expect.poll(async () => fromPaper(await comma())).toBeCloseTo(12.5, 1);
  await expect(first).toHaveAttribute('data-tabs', '[{"at":10,"kind":"decimal","leader":"dot"}]');
  await page.screenshot({ path: '/tmp/results/tabs.png' });

  await dragged(page, stop, { y: 3 * ruler.height });
  await expect(stop).toHaveCount(0);
  await expect(first).not.toHaveAttribute('data-tabs');
  await expect(first.locator('.ponistra-tab')).not.toHaveAttribute('data-leader');
  await expect.poll(tabEnd).toBeCloseTo(2.5 + 2 * 1.25, 1);
});

test('the Tabs dialog sets and clears stops from the keyboard, on every selected paragraph', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Cjenik s tabulatorima'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  for (const [name, amount] of [
    ['Ukupno', '1234,5'],
    ['Popust', '10,0'],
  ]) {
    await page.keyboard.type(name);
    await page.keyboard.press('Tab');
    await page.keyboard.type(amount);
    if (name === 'Ukupno') await page.keyboard.press('Enter');
  }
  await showPages(page);
  const [first, second] = [editor.locator('p').first(), editor.locator('p').nth(1)];
  const dialog = page.getByRole('dialog', { name: 'Tabulatori' });

  await second.click();
  await page.keyboard.press('Control+a');
  await page.keyboard.press('Alt+/');
  await page.keyboard.type('Tabulatori');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(dialog.getByText('Odlomak nema postavljenih tabulatora.')).toBeVisible();
  const position = dialog.getByLabel('Položaj tabulatora (cm)');
  await expect(position).toBeFocused();
  await page.keyboard.type('20');
  await expect(dialog.getByRole('button', { name: 'Primijeni' })).toBeDisabled();
  await position.fill('12');
  await dialog.getByLabel('Vrsta tabulatora').selectOption('right');
  await dialog.getByLabel('Vodilica').selectOption('dot');
  await position.press('Enter');
  await expect(dialog).toHaveCount(0);
  const right = '[{"at":12,"kind":"right","leader":"dot"}]';
  await expect(first).toHaveAttribute('data-tabs', right);
  await expect(second).toHaveAttribute('data-tabs', right);
  const paper = (await page.locator('.ponistra-paper').first().boundingBox())!;
  const ends = await second.evaluate((paragraph) => {
    const range = document.createRange();
    range.selectNodeContents(paragraph);
    return Math.max(...[...range.getClientRects()].map((rect) => rect.right));
  });
  expect((ends - paper.x) / (paper.width / 21)).toBeCloseTo(2.5 + 12, 1);

  await first.getByText('Ukupno').click();
  await first.getByText('Ukupno').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Tabulatori…' }).click();
  await expect(position).toHaveValue('12');
  await position.fill('4');
  await dialog.getByLabel('Vrsta tabulatora').selectOption('left');
  await dialog.getByLabel('Vodilica').selectOption('none');
  await dialog.getByRole('button', { name: 'Postavi' }).click();
  const set = dialog.getByLabel('Postavljeni tabulatori');
  await expect(set.getByRole('button')).toHaveText([
    '4 cm · Lijevi tabulator',
    '12 cm · Desni tabulator · Točkice',
  ]);
  await set.getByRole('button', { name: /^12 cm/ }).click();
  await expect(set.getByRole('button', { name: /^12 cm/ })).toHaveAttribute('aria-pressed', 'true');
  await expect(position).toHaveValue('12');
  await dialog.getByRole('button', { name: 'Ukloni', exact: true }).click();
  await expect(set.getByRole('button')).toHaveText(['4 cm · Lijevi tabulator']);
  await expect(position).toHaveValue('');
  await dialog.getByRole('button', { name: 'Primijeni' }).click();
  await expect(first).toHaveAttribute('data-tabs', '[{"at":4,"kind":"left"}]');
  await expect(second).toHaveAttribute('data-tabs', right);

  const stop = page.getByRole('group', { name: 'Vodoravno ravnalo' }).getByRole('slider', {
    name: 'Lijevi tabulator',
  });
  await stop.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Tabulatori…' }).click();
  await dialog.getByRole('button', { name: 'Ukloni sve' }).click();
  await expect(dialog.getByText('Odlomak nema postavljenih tabulatora.')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(first).toHaveAttribute('data-tabs', '[{"at":4,"kind":"left"}]');
});

test('a footnote stands at the foot of its mark’s page, clear of the text, and endnotes follow the text', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Bilješke na stranicama'));
  const editor = page.locator('.ProseMirror').first();
  const insert = async (name: string) => {
    await page.getByRole('button', { name: 'Umetni' }).click();
    await page.getByRole('menuitem', { name, exact: true }).click();
  };
  await editor.click();
  await page.keyboard.type('Uvod');
  await insert('Fusnota');
  await page.keyboard.type('Prva fusnota');
  await page.keyboard.press('Escape');
  await page.keyboard.press('Enter');
  await page.keyboard.insertText(sentence.repeat(30).trim());
  await insert('Fusnota');
  await page.keyboard.type('Druga fusnota');
  await page.keyboard.press('Escape');
  await insert('Završna bilješka');
  await page.keyboard.type('Krajnja bilješka');
  await page.keyboard.press('Escape');
  await showPages(page);

  const papers = page.locator('.ponistra-paper');
  await expect(papers.nth(1)).toBeVisible();
  const sheets = await Promise.all(
    (await papers.all()).map(async (paper) => (await paper.boundingBox())!),
  );
  const cm = sheets[0].width / 21;
  const paperAt = (y: number) =>
    sheets.findIndex((sheet) => y >= sheet.y && y < sheet.y + sheet.height);
  const item = (name: string) => page.getByRole('textbox', { name }).locator('xpath=ancestor::li');
  const marks = page.locator('sup.ponistra-note[data-note="foot"]');

  for (const [index, name] of ['Fusnota 1', 'Fusnota 2'].entries()) {
    const mark = (await marks.nth(index).boundingBox())!;
    const sheet = sheets[paperAt(mark.y)];
    await expect
      .poll(async () => {
        const box = (await item(name).boundingBox())!;
        return box.y + box.height - (sheet.y + sheet.height - 2.5 * cm);
      })
      .toBeLessThan(1);
    const box = (await item(name).boundingBox())!;
    expect(box.y + box.height).toBeGreaterThan(sheet.y + sheet.height - 2.5 * cm - 1);
    const overlaps = await editor
      .locator('p')
      .nth(1)
      .evaluate(
        (paragraph, { top, bottom }) => {
          const range = document.createRange();
          const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
          const rects: number[][] = [];
          for (let text = walker.nextNode(); text; text = walker.nextNode()) {
            range.selectNodeContents(text);
            for (const rect of range.getClientRects()) {
              if (rect.bottom > top && rect.top < bottom) rects.push([rect.top, rect.bottom]);
            }
          }
          return rects;
        },
        { top: box.y - 8, bottom: box.y + box.height },
      );
    expect(overlaps).toEqual([]);
  }

  const text = (await editor.locator('p').nth(1).boundingBox())!;
  const endnote = (await item('Završna bilješka i').boundingBox())!;
  expect(endnote.y).toBeGreaterThan(text.y + text.height);
  expect(paperAt(endnote.y)).toBe(sheets.length - 1);
  await item('Završna bilješka i').scrollIntoViewIfNeeded();
  await page.screenshot({ path: '/tmp/results/notes.png' });
});
