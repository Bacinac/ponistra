import { randomBytes } from 'node:crypto';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { Locator, Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { cellAt, selectedCells } from './helpers/tables';
import { pdfFile } from './helpers/pdf';
import { zipped } from './helpers/zip';

const W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
const PACKAGE = 'http://schemas.openxmlformats.org/package/2006';
const RELATIONSHIPS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
const WORD = 'application/vnd.openxmlformats-officedocument.wordprocessingml';
const DOCX = `${WORD}.document`;

const run = (text: string) => `<w:r><w:t xml:space="preserve">${text}</w:t></w:r>`;
const item = (text: string) =>
  `<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>${run(text)}</w:p>`;

const heading = (text: string) =>
  `<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>${run(text)}</w:p>`;
const field = (kind: string) => `<w:r><w:fldChar w:fldCharType="${kind}"/></w:r>`;

const BODY = [
  `<w:p>${field('begin')}<w:r><w:instrText>TOC \\o "1-3"</w:instrText></w:r>${field('separate')}` +
    `${run('Ugovor o djelu 1')}${field('end')}</w:p>`,
  heading('Ugovor o djelu'),
  `<w:p>${run('Cijena je ')}<w:commentRangeStart w:id="0"/>${run('100 €')}<w:commentRangeEnd w:id="0"/>` +
    '<w:r><w:rPr><w:vanish/></w:rPr><w:t>skriveno</w:t></w:r></w:p>',
  item('Izrada nacrta'),
  `<w:p>${run('Napomena između stavki.')}</w:p>`,
  `<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>` +
    `<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:pPr>${run('Predaja djela')}</w:p>`,
  heading('Prilog'),
  `<w:p>${run('Tablica cijena')}</w:p>`,
  '<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/></w:sectPr>',
].join('');

const looked = (text: string, look: string) =>
  `<w:p><w:r><w:rPr>${look}</w:rPr><w:t xml:space="preserve">${text}</w:t></w:r></w:p>`;
const ARIAL = '<w:rFonts w:ascii="Arial" w:hAnsi="Arial"/>';
const BY_HAND = [
  looked('Uvod', `${ARIAL}<w:b/><w:sz w:val="32"/>`),
  looked('Ovaj je tekst autor oblikovao rukom, redak za retkom.', `${ARIAL}<w:sz w:val="22"/>`),
  looked('Pojmovi', `${ARIAL}<w:b/><w:sz w:val="28"/>`),
  looked('Ni ovdje nema nijednog stila, samo izravno oblikovanje.', `${ARIAL}<w:sz w:val="22"/>`),
  looked('Napomena', `${ARIAL}<w:b/><w:sz w:val="22"/>`),
].join('');

const PARTS: Record<string, [string, string]> = {
  styles: [
    `<w:styles xmlns:w="${W}">` +
      '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>' +
      '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>' +
      '<w:basedOn w:val="Normal"/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style></w:styles>',
    `${WORD}.styles+xml`,
  ],
  numbering: [
    `<w:numbering xmlns:w="${W}"><w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0">` +
      '<w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%1)"/></w:lvl>' +
      '</w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num></w:numbering>',
    `${WORD}.numbering+xml`,
  ],
  comments: [
    `<w:comments xmlns:w="${W}"><w:comment w:id="0" w:author="Marko Marić" ` +
      'w:date="2026-03-02T10:15:00Z"><w:p><w:r><w:t>Provjeriti iznos.</w:t></w:r></w:p>' +
      '</w:comment></w:comments>',
    `${WORD}.comments+xml`,
  ],
};

const MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const SPREADSHEET = 'application/vnd.openxmlformats-officedocument.spreadsheetml';
const XLSX = `${SPREADSHEET}.sheet`;

/** A workbook of two sheets, as Excel packs one, its formulas left for the import to compute. */
function spreadsheet(): Buffer {
  const text = (ref: string, value: string) =>
    `<c r="${ref}" t="inlineStr"><is><t>${value}</t></is></c>`;
  const number = (ref: string, value: number) => `<c r="${ref}"><v>${value}</v></c>`;
  const formula = (ref: string, code: string) => `<c r="${ref}"><f>${code}</f></c>`;
  const sheet = (rows: string[][], cols = '') =>
    `<worksheet xmlns="${MAIN}">${cols}<sheetData>` +
    rows.map((cells, at) => `<row r="${at + 1}">${cells.join('')}</row>`).join('') +
    '</sheetData></worksheet>';
  const worksheets = [
    sheet(
      [
        [text('A1', 'Artikl'), text('B1', 'Cijena'), text('C1', 'S porezom')],
        [
          text('A2', 'Olovka'),
          number('B2', 2.5),
          formula('C2', 'B2*(1+Stopa)'),
          formula('D2', 'FOOBAR(1)'),
        ],
        [text('A3', 'Bilježnica'), number('B3', 4), formula('C3', 'B3*(1+Stopa)')],
        [formula('C4', 'SUM(C2:C3)')],
      ],
      '<cols><col min="1" max="1" width="120" customWidth="1"/></cols>',
    ),
    sheet([[number('A1', 0.25)]]),
  ];
  return zipped({
    '[Content_Types].xml':
      `<Types xmlns="${PACKAGE}/content-types">` +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
      '<Default Extension="xml" ContentType="application/xml"/>' +
      `<Override PartName="/xl/workbook.xml" ContentType="${SPREADSHEET}.sheet.main+xml"/>` +
      worksheets
        .map(
          (_, at) =>
            `<Override PartName="/xl/worksheets/sheet${at + 1}.xml" ContentType="${SPREADSHEET}.worksheet+xml"/>`,
        )
        .join('') +
      '</Types>',
    '_rels/.rels':
      `<Relationships xmlns="${PACKAGE}/relationships"><Relationship Id="rId1" ` +
      `Type="${RELATIONSHIPS}/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
    'xl/workbook.xml':
      `<workbook xmlns="${MAIN}" xmlns:r="${RELATIONSHIPS}"><sheets>` +
      '<sheet name="Cijene" sheetId="1" r:id="rId1"/><sheet name="Porez" sheetId="2" r:id="rId2"/>' +
      '</sheets><definedNames><definedName name="Stopa">Porez!$A$1</definedName></definedNames>' +
      '</workbook>',
    'xl/_rels/workbook.xml.rels':
      `<Relationships xmlns="${PACKAGE}/relationships">` +
      worksheets
        .map(
          (_, at) =>
            `<Relationship Id="rId${at + 1}" Type="${RELATIONSHIPS}/worksheet" Target="worksheets/sheet${at + 1}.xml"/>`,
        )
        .join('') +
      '</Relationships>',
    ...Object.fromEntries(worksheets.map((data, at) => [`xl/worksheets/sheet${at + 1}.xml`, data])),
  });
}

const RTF = Buffer.from('{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Arial;}}\\f0 Ponuda za radove\\par}');

function wordFile(body = BODY): Buffer {
  const parts: Record<string, [string, string]> = {
    document: [
      `<w:document xmlns:w="${W}"><w:body>${body}</w:body></w:document>`,
      `${DOCX}.main+xml`,
    ],
    ...PARTS,
  };
  const names = Object.keys(parts);
  const overrides = names
    .map((name) => `<Override PartName="/word/${name}.xml" ContentType="${parts[name][1]}"/>`)
    .join('');
  const related = names
    .filter((name) => name !== 'document')
    .map(
      (name) =>
        `<Relationship Id="rId${name}" Type="${RELATIONSHIPS}/${name}" Target="${name}.xml"/>`,
    )
    .join('');
  return zipped({
    '[Content_Types].xml':
      `<Types xmlns="${PACKAGE}/content-types">` +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
      `<Default Extension="xml" ContentType="application/xml"/>${overrides}</Types>`,
    '_rels/.rels':
      `<Relationships xmlns="${PACKAGE}/relationships"><Relationship Id="rId1" ` +
      `Type="${RELATIONSHIPS}/officeDocument" Target="word/document.xml"/></Relationships>`,
    'word/_rels/document.xml.rels': `<Relationships xmlns="${PACKAGE}/relationships">${related}</Relationships>`,
    ...Object.fromEntries(names.map((name) => [`word/${name}.xml`, parts[name][0]])),
  });
}

test('a folder uploaded comes in whole with the folders below it, without its dotted files, telling what it could not import', async ({
  page,
}) => {
  const root = join(await mkdtemp(join(tmpdir(), 'mapa-')), 'Ponude 2026');
  await mkdir(join(root, 'Diversus'), { recursive: true });
  await mkdir(join(root, '.git'));
  await writeFile(join(root, 'Cjenik.pdf'), pdfFile({ pages: [[{ text: 'Cijene', top: 100 }]] }));
  await writeFile(join(root, 'Diversus', 'Ugovor.docx'), wordFile());
  await writeFile(join(root, 'Diversus', 'Pokvaren.docx'), zipped({ 'word/document.xml': '<w:' }));
  await writeFile(join(root, 'Diversus', 'Crtež.dwg'), Buffer.from('AC1032\0\0\0\0\0\0'));
  await writeFile(join(root, '.DS_Store'), '');
  await writeFile(join(root, '.git', 'HEAD'), 'ref: refs/heads/main');

  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj mapu…' }).click();
  await (await chooser).setFiles(root);
  const unimported = page.getByText('Spremljeno kao datoteka jer se nije moglo uvesti');
  await expect(unimported).toContainText('Ponude 2026/Diversus/Pokvaren.docx');
  await expect(page.getByRole('status')).toBeHidden({ timeout: 30_000 });
  await expect(unimported).not.toContainText('Ugovor');
  await expect(page.getByText('Nije učitano zbog pogreške')).toBeHidden();

  // A folder that is still loading leaves the one shown, and the tree, as they were.
  // Only the folder's first load is held: the files read in the background change it again, and
  // a refetch still held when the route goes is one Playwright refuses to continue.
  await page.route(
    /\/api\/nodes\?parent=/,
    async (route) => {
      await new Promise((done) => setTimeout(done, 800));
      await route.continue();
    },
    { times: 1 },
  );
  const tree = page.getByRole('navigation', { name: 'Mape' }).filter({ visible: true });
  await page.evaluate(() => {
    const watched = window as unknown as { left?: string[] };
    watched.left = [];
    new MutationObserver(() => {
      const trees = [...document.querySelectorAll('nav[aria-label="Mape"]')];
      if (!trees.some((nav) => nav.textContent!.includes('Ponude 2026')))
        watched.left!.push('tree');
      if (document.body.textContent!.includes('Učitavanje…')) watched.left!.push('loading');
    }).observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await page
    .getByRole('row', { name: /Ponude 2026/ })
    .getByText('Ponude 2026', { exact: true })
    .dblclick();
  await expect(page.getByRole('row', { name: /Diversus/ })).toBeVisible();
  await expect(page.getByRole('row', { name: /Cjenik/ })).toContainText('PDF datoteka');
  await expect(page.getByRole('row')).toHaveCount(3);
  expect(await page.evaluate(() => (window as unknown as { left: string[] }).left)).toEqual([]);

  await page
    .getByRole('row', { name: /Diversus/ })
    .getByText('Diversus', { exact: true })
    .dblclick();
  await expect(page.getByRole('row', { name: /Ugovor/ })).toContainText('Dokument');
  await expect(page.getByRole('row', { name: /Pokvaren/ })).toContainText('DOCX datoteka');
  await expect(page.getByRole('row', { name: /Crtež/ })).toContainText('DWG datoteka');
  await expect(page.getByRole('row')).toHaveCount(4);
  // Beside the tree, which shows the way, the header names the folder alone.
  await expect(page.getByRole('navigation', { name: 'Putanja' })).toHaveText('Diversus');
  // A folder holding none has nothing to open in the tree, and says nothing about it.
  const diversus = tree.locator('div', { has: page.getByRole('link', { name: 'Diversus' }) });
  await expect(diversus.getByRole('button', { name: /Sažmi|Proširi/ })).toHaveCount(0);
  await expect(tree).not.toContainText('Nema podmapa');

  await page.locator('main table').evaluate((list) => {
    const data = new DataTransfer();
    data.items.add(new File(['%PDF-1.7\n%%EOF\n'], 'Bilješka.pdf', { type: 'application/pdf' }));
    for (const type of ['dragover', 'drop']) {
      list.dispatchEvent(
        new DragEvent(type, { dataTransfer: data, bubbles: true, cancelable: true }),
      );
    }
  });
  await expect(page.getByRole('row', { name: /Bilješka/ })).toContainText('PDF datoteka');

  // A row dragged onto a folder of the tree goes into it.
  await page
    .locator('main table')
    .getByRole('row', { name: /Crtež/ })
    .dragTo(tree.getByRole('link', { name: 'Ponude 2026' }));
  await expect(page.getByRole('row', { name: /Crtež/ })).toHaveCount(0);

  // Files from the computer dropped onto a folder of the tree go into it, which opens.
  await tree.getByRole('link', { name: 'Ponude 2026' }).click();
  await expect(page.getByRole('row', { name: /Crtež/ })).toBeVisible();
  await tree.getByRole('link', { name: 'Diversus' }).evaluate((link) => {
    const data = new DataTransfer();
    data.items.add(new File(['a;b\n'], 'Popis.csv', { type: 'text/csv' }));
    for (const type of ['dragover', 'drop']) {
      link.dispatchEvent(
        new DragEvent(type, { dataTransfer: data, bubbles: true, cancelable: true }),
      );
    }
  });
  await expect(page.getByRole('row', { name: /Popis/ })).toContainText('Tablica');
  await expect(page.getByRole('row', { name: /Ugovor/ })).toBeVisible();

  await tree.getByRole('link', { name: 'Ponude 2026' }).click();
  await page.getByRole('row', { name: /Crtež/ }).getByText('Crtež', { exact: true }).dblclick();
  await expect(
    page.getByText('Ponistra ovu vrstu datoteke čuva, ali je ne prikazuje.'),
  ).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Preuzmi' }).click();
  expect((await download).suggestedFilename()).toBe('Crtež.dwg');
});

test('a Word file becomes a document, each section on paper of its own, with its contents, comments and numbers and a report on the import, and is imported again from it', async ({
  page,
}) => {
  const buffer = wordFile();
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles({ name: 'Ugovor o djelu.docx', mimeType: DOCX, buffer });
  const row = page.getByRole('row', { name: /Ugovor o djelu/ });
  await row.getByText('Ugovor o djelu', { exact: true }).dblclick();

  const editor = page.locator('.ProseMirror');
  await expect(editor.locator('h1')).toHaveText(['Ugovor o djelu', 'Prilog']);
  await expect(editor.locator('[data-section-break]')).toHaveCount(1);
  const papers = page.locator('.ponistra-paper');
  const landscape = async () => {
    await expect(papers).toHaveCount(2);
    const first = (await papers.first().boundingBox())!;
    const second = (await papers.nth(1).boundingBox())!;
    expect(first.width / first.height).toBeCloseTo(21 / 29.7, 2);
    expect(second.width / second.height).toBeCloseTo(29.7 / 21, 2);
  };
  await landscape();
  const contents = editor.getByRole('navigation', { name: 'Sadržaj' });
  await expect(contents.getByRole('link')).toHaveText(['Ugovor o djelu', 'Prilog']);
  await expect(editor.locator('p[data-list=number]')).toHaveText([
    'Izrada nacrta',
    'Predaja djela',
  ]);
  const markers = editor.locator('p[data-list=number]');
  await expect(markers.nth(0)).toHaveAttribute('data-marker', 'a)');
  await expect(markers.nth(1)).toHaveAttribute('data-marker', 'b)');
  await expect(editor.locator('.ponistra-comment')).toHaveText('100 €');

  const report = page.getByRole('region', { name: 'Izvještaj o uvozu' });
  await expect(report).toContainText('dio sadržaja nije prenesen');
  await report.getByRole('button', { name: 'Pojedinosti' }).click();
  await expect(report.getByRole('listitem')).toHaveText([/Skriven/]);
  const original = report.getByRole('link', { name: 'Preuzmi izvornu datoteku' });
  const download = await page.request.get((await original.getAttribute('href'))!);
  expect(download.headers()['content-type']).toBe(DOCX);
  expect(Buffer.compare(await download.body(), buffer)).toBe(0);

  await page.getByRole('button', { name: /^Komentari/ }).click();
  const panel = page.getByRole('complementary', { name: 'Komentari' });
  await expect(panel).toContainText('Marko Marić');
  await expect(panel).toContainText('iz uvezene datoteke');
  await expect(panel).toContainText('Provjeriti iznos.');

  await report.getByRole('button', { name: 'Zatvori izvještaj' }).click();
  await expect(report).toHaveCount(0);
  await page.reload();
  await expect(editor.locator('h1')).toHaveText(['Ugovor o djelu', 'Prilog']);
  await expect(report).toHaveCount(0);

  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Ponovno uvezi iz izvorne datoteke' }).click();
  await page
    .getByRole('alertdialog')
    .getByRole('button', { name: 'Ponovno uvezi iz izvorne datoteke' })
    .click();
  await expect(report).toContainText('dio sadržaja nije prenesen');
  await expect(editor.locator('h1')).toHaveText(['Ugovor o djelu', 'Prilog']);
  await expect(editor.locator('.ponistra-comment')).toHaveText('100 €');
  await landscape();

  const saved = page.waitForEvent('download');
  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Spremi kao' }).click();
  await expect(page.getByRole('menuitem', { name: /makronaredbama/ })).toHaveCount(0);
  await page.getByRole('menuitem', { name: 'Word (.docx)' }).click();
  const word = await saved;
  expect(word.suggestedFilename()).toBe('Ugovor o djelu.docx');
  await page.goto('/documents');
  const again = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  const back = await readFile((await word.path())!);
  await (await again).setFiles({ name: 'Natrag.docx', mimeType: DOCX, buffer: back });
  const returned = page.getByRole('row', { name: /Natrag/ });
  await returned.getByText('Natrag', { exact: true }).dblclick();
  await expect(editor.locator('h1')).toHaveText(['Ugovor o djelu', 'Prilog']);
  await expect(markers.nth(1)).toHaveAttribute('data-marker', 'b)');
  await expect(editor.locator('.ponistra-comment')).toHaveText('100 €');
  await landscape();
});

test('a Word file formatted by hand comes in with its formatting made into styles, looking as it did', async ({
  page,
}) => {
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles({ name: 'Rukom.docx', mimeType: DOCX, buffer: wordFile(BY_HAND) });
  await page.getByRole('row', { name: /Rukom/ }).getByText('Rukom', { exact: true }).dblclick();
  const editor = page.locator('.ProseMirror');
  await expect(editor.locator('h1')).toHaveText('Uvod');
  await expect(editor.locator('h2')).toHaveText('Pojmovi');
  await expect(editor.locator('[data-font], [data-font-size], strong')).toHaveCount(1);
  await expect(editor.locator('p strong')).toHaveText('Napomena');
  await expect(editor.locator('h1')).toHaveCSS('font-family', /^"?Liberation Sans"?,/);
  await expect(editor.locator('h1')).toHaveCSS('font-size', /^21\.33/);
  const text = editor.locator('p', { hasText: 'Ovaj je tekst' });
  await expect(text).toHaveCSS('font-family', /^"?Liberation Sans"?,/);
  await expect(text).toHaveCSS('font-size', /^14\.66/);
});

const ANA = 'w:author="Ana Horvat" w:date="2026-10-19T10:00:00Z"';
const PROPOSED = [
  `<w:p>${run('Rok je ')}<w:del w:id="1" ${ANA}><w:r><w:delText>30</w:delText></w:r></w:del>` +
    `<w:ins w:id="2" ${ANA}>${run('15')}</w:ins>${run(' dana.')}</w:p>`,
  '<w:p><w:pPr><w:rPr><w:ins w:id="3" w:author="Ivo"/></w:rPr></w:pPr>' +
    `<w:ins w:id="4" w:author="Ivo">${run('Novi stavak.')}</w:ins></w:p>`,
  `<w:p>${run('Kraj.')}</w:p>`,
].join('');

test('tracked changes of a Word file come in as proposals, accepted one by one or rejected all, and the rejection is taken back', async ({
  page,
}) => {
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (
    await chooser
  ).setFiles({ name: 'Prijedlozi.docx', mimeType: DOCX, buffer: wordFile(PROPOSED) });
  await page
    .getByRole('row', { name: /Prijedlozi/ })
    .getByText('Prijedlozi', { exact: true })
    .dblclick();
  const editor = page.locator('.ProseMirror');
  await expect(editor.locator('del[data-proposal]')).toHaveText('30');
  await expect(editor.locator('ins[data-proposal]')).toHaveText(['15', 'Novi stavak.']);
  await expect(editor.locator('.ponistra-end[data-proposed="insertion"]')).toHaveCount(1);

  await editor.locator('ins', { hasText: '15' }).click();
  const popover = page.getByRole('toolbar', { name: 'Prijedlozi' });
  await expect(popover).toContainText('Zamijenjeno · Ana Horvat');
  await popover.getByRole('button', { name: 'Prihvati prijedlog' }).click();
  await expect(editor.locator('p').first()).toHaveText('Rok je 15 dana.');
  await expect(editor.locator('del[data-proposal]')).toHaveCount(0);
  await expect(
    page.getByRole('status').filter({ hasText: 'Izvedeno: Prihvati prijedlog' }),
  ).toBeVisible();

  await editor.locator('ins', { hasText: 'Novi stavak.' }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Odbij sve prijedloge' }).click();
  await expect(editor.locator('p')).toHaveText(['Rok je 15 dana.', 'Kraj.']);
  await expect(editor.locator('[data-proposal], .ponistra-end')).toHaveCount(0);

  const bar = page.getByRole('status').filter({ hasText: 'Izvedeno: Odbij sve prijedloge' });
  await bar.getByRole('button', { name: 'Poništi akciju' }).click();
  await expect(editor.locator('p')).toHaveText(['Rok je 15 dana.', 'Novi stavak.', 'Kraj.']);
  await expect(editor.locator('ins[data-proposal]')).toHaveText('Novi stavak.');
});

test('a file of another word processor comes in through LibreOffice, and a file imported into an open document follows its tabs', async ({
  page,
}) => {
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles({ name: 'Ponuda.rtf', mimeType: 'application/rtf', buffer: RTF });
  await page
    .getByRole('row', { name: /Ponuda/ })
    .getByText('Ponuda', { exact: true })
    .dblclick();
  const editor = page.locator('.ProseMirror');
  await expect(editor).toContainText('Ponuda za radove');
  const address = new URL(page.url()).pathname;

  const into = page.waitForEvent('filechooser');
  await page
    .getByRole('navigation', { name: 'Putanja' })
    .getByRole('button', { name: 'Ponuda' })
    .click();
  await page.getByRole('menuitem', { name: 'Uvezi u ovaj dokument…' }).click();
  await (await into).setFiles({ name: 'Ugovor o djelu.docx', mimeType: DOCX, buffer: wordFile() });

  const report = page.getByRole('dialog', { name: 'Izvještaj o uvozu' });
  await expect(report).toContainText('nove kartice na kraju dokumenta');
  await expect(report.getByRole('listitem')).toHaveText([/Skriven/]);
  await report.getByRole('button', { name: 'Zatvori' }).click();
  await expect(page).toHaveURL(new RegExp(`${address}/ugovor-o-djelu-[0-9A-Za-z]{22}$`));
  const tabs = page.getByRole('navigation', { name: 'Kartice' });
  await expect(
    tabs.getByRole('link', { name: /^(Kartica bez naziva|Ugovor o djelu|Prilog)$/ }),
  ).toHaveText(['Kartica bez naziva', 'Ugovor o djelu', 'Ugovor o djelu', 'Prilog']);
  await expect(editor.locator('h1')).toHaveText(['Ugovor o djelu', 'Prilog']);
  await expect(editor.locator('[data-section-break]')).toHaveCount(1);
  const markers = editor.locator('p[data-list=number]');
  await expect(markers.nth(0)).toHaveAttribute('data-marker', 'a)');
  await expect(markers.nth(1)).toHaveAttribute('data-marker', 'b)');
  await expect(editor.locator('.ponistra-comment')).toHaveText('100 €');
});

/** The workbook of two sheets brought in as a document of its own, and opened. */
async function uploadSpreadsheet(page: Page): Promise<string> {
  const name = `Cjenik ${randomBytes(3).toString('hex')}`;
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles({ name: `${name}.xlsx`, mimeType: XLSX, buffer: spreadsheet() });
  return name;
}

async function openSpreadsheet(page: Page): Promise<string> {
  const name = await uploadSpreadsheet(page);
  await page.getByRole('row', { name }).getByText(name, { exact: true }).dblclick();
  return name;
}

test('an imported workbook is listed as a spreadsheet by what it holds, the file it came from beside it in the preview', async ({
  page,
}) => {
  const name = await uploadSpreadsheet(page);
  const row = page.getByRole('row', { name });
  await expect(row).toBeVisible();
  await expect
    .poll(
      async () => {
        const listing = await (await page.request.get('/api/nodes')).json();
        return listing.children.find((node: { title: string }) => node.title === name)?.holds;
      },
      { timeout: 20_000 },
    )
    .toBe('table');

  await page.reload();
  await expect(row).toContainText('Tablica');
  await page.getByRole('button', { name: 'Pregled' }).click();
  await row.getByText(name, { exact: true }).click();
  const pane = page.getByRole('complementary', { name: 'Pregled' });
  await expect(pane).toContainText('Olovka');
  await expect(pane).toContainText(/Veličina[\d,]+ (B|kB)/);
  await expect(pane).toContainText(/IzvornikXLSX datoteka · [\d,]+ (B|kB)/);
  await expect(pane.getByRole('link', { name: 'Preuzmi izvornu datoteku' })).toHaveAttribute(
    'href',
    /\/source\?download=1$/,
  );
});

test('a spreadsheet becomes a document of a tab for each sheet, its table named after it and computed on the server', async ({
  page,
}) => {
  const name = await openSpreadsheet(page);
  const tabs = page.getByRole('navigation', { name: 'Kartice' });
  await expect(tabs.getByRole('link', { name: 'Cijene', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  const tables = page.locator('.ponistra-table');
  await expect(tables.locator('.ponistra-table-name')).toHaveText(['Cijene']);
  const at = (address: string) => cellAt(tables.first(), address);
  const rightmost = () =>
    tables
      .first()
      .locator('.ponistra-sheet')
      .evaluate((sheet) => {
        sheet.scrollLeft = sheet.scrollWidth;
      });
  await expect(at('A2')).toHaveText('Olovka');
  await rightmost();
  const shown = { B2: '2,5', C2: '3,125', D2: '#NAME?', C4: '8,125' };
  for (const [address, text] of Object.entries(shown)) await expect(at(address)).toHaveText(text);
  const scrolls = (table: Locator) =>
    table.locator('.ponistra-sheet').evaluate((sheet) => sheet.scrollWidth > sheet.clientWidth);
  expect(await scrolls(tables.first())).toBe(true);
  const spread = (table: Locator) =>
    table.evaluate((box) => {
      const column = box.closest('[data-styling]')!;
      const sheet = box.querySelector('.ponistra-sheet')!;
      let pane = column.parentElement!;
      while (getComputedStyle(pane).display === 'contents') pane = pane.parentElement!;
      return [box.clientWidth > column.clientWidth, sheet.clientWidth === pane.clientWidth];
    });
  expect(await spread(tables.first())).toEqual([true, true]);

  const report = page.getByRole('region', { name: 'Izvještaj o uvozu' });
  await expect(report).toContainText('dio sadržaja nije prenesen');
  await report.getByRole('button', { name: 'Pojedinosti' }).click();
  await expect(report).toContainText('FOOBAR');
  const original = report.getByRole('link', { name: 'Preuzmi izvornu datoteku' });
  const download = await page.request.get((await original.getAttribute('href'))!);
  expect(download.headers()['content-type']).toBe(XLSX);

  await at('B2').click();
  await page.keyboard.press('Control+a');
  await page.keyboard.type('3');
  await page.keyboard.press('ArrowDown');
  await expect(at('C2')).toHaveText('3,75');
  await expect(at('C4')).toHaveText('8,75');
  await at('C2').click();
  await expect(page.locator('.ponistra-formula')).toHaveValue('=B2*(1+Stopa)');
  await page.keyboard.press('Escape');

  await page.reload();
  await expect(at('A2')).toHaveText('Olovka');
  await rightmost();
  await expect(at('B2')).toHaveText('3');
  await expect(at('C4')).toHaveText('8,75');

  await tabs.getByRole('link', { name: 'Porez', exact: true }).click();
  await expect(tables.locator('.ponistra-table-name')).toHaveText(['Porez']);
  await expect(tables.first().getByRole('gridcell')).toHaveText(['0,25']);
  expect([await scrolls(tables.first()), await spread(tables.first())]).toEqual([
    false,
    [false, false],
  ]);

  const saved = page.waitForEvent('download');
  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Spremi kao' }).click();
  await expect(page.getByRole('menuitem', { name: /makronaredbama/ })).toHaveCount(0);
  await page.getByRole('menuitem', { name: 'Excel (.xlsx)' }).click();
  const workbook = await saved;
  expect(workbook.suggestedFilename()).toBe(`${name}.xlsx`);
  const bytes = await readFile((await workbook.path())!);
  expect(bytes.subarray(0, 2).toString()).toBe('PK');
});

test('the name box shows the cells chosen and leads to an address, another sheet’s cells and a defined name', async ({
  page,
}) => {
  await openSpreadsheet(page);
  const tables = page.locator('.ponistra-table');
  const names = tables.locator('.ponistra-table-name');
  const box = page.getByRole('textbox', { name: 'Polje imena' });
  const go = async (written: string) => {
    await box.click();
    await page.keyboard.type(written);
    await page.keyboard.press('Enter');
  };
  await cellAt(tables.first(), 'A2').click();
  await expect(box).toHaveValue('Cijene!A2');
  const home = page.url();

  await go('B3');
  await expect(page).toHaveURL(`${home}?cell=B3`);
  await expect(box).toHaveValue('Cijene!B3');
  await go('a1:a3');
  await expect(page).toHaveURL(`${home}?cell=A1%3AA3`);
  await expect(box).toHaveValue('Cijene!A1:A3');
  expect(await selectedCells(tables.first())).toEqual(['A1', 'A2', 'A3']);

  await go('Z99');
  await expect(page.getByRole('alert')).toHaveText('Adresa je izvan tablice.');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(box).toHaveValue('Cijene!A1:A3');
  await go('Nema!A1');
  await expect(page.getByRole('alert')).toHaveText(
    'Nema tablice ni definiranog naziva s tim imenom.',
  );
  await page.keyboard.press('Escape');

  await go("'Porez'!A1");
  await expect(names).toHaveText(['Porez']);
  await expect(page).toHaveURL(/\/[^/?]+\?cell=A1$/);
  await expect(box).toHaveValue('Porez!A1');
  await go('Cijene!C4');
  await expect(names).toHaveText(['Cijene']);
  await expect(page).toHaveURL(`${home}?cell=C4`);
  await expect(box).toHaveValue('Cijene!C4');

  await page.keyboard.press('Control+g');
  await expect(box).toBeFocused();
  await page.keyboard.type('stopa');
  await page.keyboard.press('Enter');
  await expect(names).toHaveText(['Porez']);
  await expect(box).toHaveValue('Porez!A1');
  await page.goBack();
  await expect(names).toHaveText(['Cijene']);
  await expect(box).toHaveValue('Cijene!C4');

  const wide = page.viewportSize()!;
  await page.setViewportSize({ width: 480, height: 800 });
  await cellAt(tables.first(), 'A3').click();
  await expect(box).not.toBeVisible();
  await page.keyboard.press('Control+g');
  const dialog = page.getByRole('dialog', { name: 'Idi na ćeliju' });
  await expect(dialog.getByRole('textbox', { name: 'Polje imena' })).toHaveValue('Cijene!A3');
  await page.keyboard.type('B2');
  await page.keyboard.press('Enter');
  await expect(dialog).toHaveCount(0);
  await expect(page).toHaveURL(`${home}?cell=B2`);
  await expect.poll(() => selectedCells(tables.first())).toEqual(['B2']);

  await page.setViewportSize(wide);
  await page.goto(`${home}?cell=A3`);
  await expect.poll(() => selectedCells(tables.first())).toEqual(['A3']);
  await expect(box).toHaveValue('Cijene!A3');
});

test('a document goes into PONISTRA’s own file and comes back whole, and a copy is made the same way', async ({
  page,
}) => {
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles({ name: 'Zakup.docx', mimeType: DOCX, buffer: wordFile() });
  await page.getByRole('row', { name: /Zakup/ }).getByText('Zakup', { exact: true }).dblclick();
  const editor = page.locator('.ProseMirror');
  await expect(editor.locator('.ponistra-comment')).toHaveText('100 €');

  const title = page.locator('header button[aria-current="page"]');
  const download = page.waitForEvent('download');
  await title.click();
  await page.getByRole('menuitem', { name: 'Spremi kao' }).click();
  await page.getByRole('menuitem', { name: 'Ponistra (.ponx)' }).click();
  const saved = await download;
  expect(saved.suggestedFilename()).toBe('Zakup.ponx');

  await page.goto('/documents');
  const again = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (
    await again
  ).setFiles({
    name: 'Zakup natrag.ponx',
    mimeType: '',
    buffer: await readFile((await saved.path())!),
  });
  await page
    .getByRole('row', { name: /Zakup natrag/ })
    .getByText('Zakup natrag', { exact: true })
    .dblclick();
  const whole = async () => {
    await expect(editor.locator('h1')).toHaveText(['Ugovor o djelu', 'Prilog']);
    await expect(editor.locator('[data-section-break]')).toHaveCount(1);
    const markers = editor.locator('p[data-list=number]');
    await expect(markers.nth(0)).toHaveAttribute('data-marker', 'a)');
    await expect(markers.nth(1)).toHaveAttribute('data-marker', 'b)');
    await expect(editor.locator('.ponistra-comment')).toHaveText('100 €');
  };
  await whole();
  await expect(page.getByRole('region', { name: 'Izvještaj o uvozu' })).toHaveCount(0);

  await title.click();
  await page.getByRole('menuitem', { name: 'Napravi kopiju' }).click();
  const naming = page.getByRole('dialog', { name: 'Napravi kopiju' });
  await expect(naming.getByRole('textbox', { name: 'Naziv' })).toHaveValue('Kopija – Zakup natrag');
  await naming.getByRole('button', { name: 'Izradi' }).click();
  await expect(title).toContainText('Kopija – Zakup natrag');
  await whole();
});
