import type { Locator, Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';
import {
  cellAt,
  cellTexts,
  dragCells,
  insertTable,
  selectedCells,
  standing,
  tab,
  tableCommand,
  writes,
  writing,
} from './helpers/tables';

async function cellFormat(page: Page, name: string): Promise<void> {
  await page.getByRole('button', { name: 'Tablica' }).click();
  await page.getByRole('menuitem', { name: 'Oblikovanje broja' }).click();
  await page.getByRole('menuitem', { name, exact: true }).click();
}

async function paste(page: Page, html: string): Promise<void> {
  await page.evaluate((html) => {
    const data = new DataTransfer();
    data.setData('text/html', html);
    const event = new ClipboardEvent('paste', { clipboardData: data, bubbles: true });
    document.activeElement!.dispatchEvent(event);
  }, html);
}

/** Whether a button of the editor's toolbar is pressed, as it is for the look of the cells chosen. */
function pressed(page: Page, name: string): Locator {
  return page.getByRole('toolbar').first().getByRole('button', { name, exact: true });
}

async function aligned(page: Page, name: string, checked: boolean): Promise<void> {
  await pressed(page, 'Poravnanje').click();
  await expect(page.getByRole('menuitemcheckbox', { name })).toBeChecked({ checked });
  await page.keyboard.press('Escape');
  await expect(page.locator('.ProseMirror-focused')).toHaveCount(1);
}

test('cells hold formatted paragraphs and lists, and the keys lead through the table', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Tablica s tekstom'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Uvod');
  await insertTable(page, '2 × 2');
  const table = page.locator('.ponistra-table');
  const first = writing(table, 'A1');
  await expect(first).toBeFocused();

  await page.keyboard.press('Control+b');
  await page.keyboard.type('Stavka');
  await page.keyboard.press('Control+b');
  await page.keyboard.press('Enter');
  await page.keyboard.type('- prva');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Tab');
  await page.keyboard.type('druga');
  await expect(first.locator('strong')).toHaveText('Stavka');
  await expect(first.locator('p[data-list=bullet]')).toHaveText(['prva', 'druga']);
  await expect(first).toBeFocused();

  await page.keyboard.press('Tab');
  await expect(writing(table, 'B1')).toBeFocused();
  await page.keyboard.type('42');
  await page.keyboard.press('Shift+Tab');
  await expect(writing(table, 'A1')).toBeFocused();
  await expect(cellAt(table, 'B1')).toHaveText('42');

  await cellAt(table, 'B2').click();
  await page.keyboard.press('Tab');
  await expect(table.getByRole('grid')).toHaveAttribute('aria-rowcount', '4');
  await expect(writing(table, 'A3')).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(editor).toBeFocused();
  await page.keyboard.type('Zaključak');
  await expect(editor.locator(':scope > p').last()).toHaveText('Zaključak');
  await page.keyboard.press('Home');
  await page.keyboard.press('ArrowUp');
  await expect(writing(table, 'A3')).toBeFocused();
  await page.keyboard.type('Ukupno');
  await page.keyboard.press('Shift+Tab');
  await expect(cellAt(table, 'A3')).toHaveText('Ukupno');
});

test('a table is undone with its data and the paragraph after it, its lines added on every side, the last row kept', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Retci i stupci'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Uvod');
  await insertTable(page, '2 × 2');
  const table = page.locator('.ponistra-table');
  const grid = table.getByRole('grid');
  const undo = page.getByRole('button', { name: 'Poništi' });
  const redo = page.getByRole('button', { name: 'Ponovi' });
  await expect(writing(table, 'A1')).toBeFocused();
  await page.keyboard.type('staro');
  await page.keyboard.press('Tab');
  await undo.click();
  await expect(cellAt(table, 'A1')).toHaveText('');
  await undo.click();
  await expect(table).toHaveCount(0);
  await expect(editor.locator(':scope > *')).toHaveText(['Uvod']);
  await redo.click();
  await redo.click();
  await expect(cellAt(table, 'A1')).toHaveText('staro');

  await cellAt(table, 'B1').click();
  await page.keyboard.type('isto');
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.press('End');
  await page.keyboard.press('Shift+ArrowRight');
  await expect.poll(() => selectedCells(table)).toEqual(['A1', 'B1']);
  await page.keyboard.type('novo');
  await page.keyboard.press('ArrowDown');
  await expect(writing(table, 'A2')).toBeFocused();
  await expect.poll(() => cellTexts(table)).toEqual(['novo', '', '', '']);

  await tableCommand(page, 'Umetni stupac lijevo');
  await expect(grid).toHaveAttribute('aria-colcount', '4');
  await expect(writing(table, 'B2')).toBeFocused();
  await tableCommand(page, 'Umetni stupac desno');
  await expect(grid).toHaveAttribute('aria-colcount', '5');
  await tableCommand(page, 'Umetni redak iznad');
  await expect(grid).toHaveAttribute('aria-rowcount', '4');
  await expect(writing(table, 'B3')).toBeFocused();
  await expect
    .poll(() => cellTexts(table))
    .toEqual(['', 'novo', '', '', '', '', '', '', '', '', '', '']);

  for (const row of ['A3', 'A2']) {
    await cellAt(table, row).click();
    await tableCommand(page, 'Obriši redak');
  }
  await expect(grid).toHaveAttribute('aria-rowcount', '2');
  await cellAt(table, 'A1').click();
  await page.getByRole('button', { name: 'Tablica' }).click();
  await expect(page.getByRole('menuitem', { name: 'Obriši redak' })).toBeDisabled();
  await expect(page.getByRole('menuitem', { name: 'Obriši stupac' })).toBeEnabled();
  const design = async (checked: string): Promise<void> => {
    await page.getByRole('menuitem', { name: 'Izgled tablice' }).click();
    await expect(page.getByRole('menuitemcheckbox', { name: checked })).toBeChecked();
  };
  await design('Mreža');
  await expect(page.getByRole('menuitemcheckbox', { name: 'Redak zaglavlja' })).toBeEnabled();
  await page.getByRole('menuitemcheckbox', { name: 'Bez crta' }).click();
  await page.getByRole('button', { name: 'Tablica' }).click();
  await design('Bez crta');
  await expect(page.getByRole('menuitemcheckbox', { name: 'Redak zaglavlja' })).toBeDisabled();
  await page.keyboard.press('Escape');
  await undo.click();
  await page.getByRole('button', { name: 'Tablica' }).click();
  await design('Mreža');
  await page.keyboard.press('Escape');
  await expect.poll(() => cellTexts(table)).toEqual(['', 'novo', '', '']);
});

test('empty cells formatted together write in that look, and a table deleted elsewhere leaves the editor as it was', async ({
  page,
  context,
}) => {
  const url = await newDocument(page, 'Prazne ćelije');
  await page.goto(url);
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Uvod');
  await insertTable(page, '2 × 2');
  const table = page.locator('.ponistra-table');
  await editor.getByText('Uvod').click();
  await dragCells(page, table, 'A1', 'B2');
  await expect.poll(() => selectedCells(table)).toEqual(['A1', 'A2', 'B1', 'B2']);
  const bold = pressed(page, 'Podebljano');
  await expect(bold).toHaveAttribute('aria-pressed', 'false');
  await page.keyboard.press('Control+b');
  await expect(bold).toHaveAttribute('aria-pressed', 'true');
  await cellAt(table, 'B2').click();
  await page.keyboard.type('Ukupno');
  await expect(writing(table, 'B2').locator('strong')).toHaveText('Ukupno');
  await page.keyboard.press('Shift+Tab');
  await page.keyboard.type('Iznos');
  await expect(writing(table, 'A2').locator('strong')).toHaveText('Iznos');
  await page.keyboard.press('Escape');
  await expect(cellAt(table, 'A2')).toHaveAttribute('aria-selected', 'true');

  const other = await context.newPage();
  await other.goto(url);
  const theirs = other.locator('.ponistra-table');
  await cellAt(theirs, 'B2').click();
  await other.getByRole('button', { name: 'Tablica' }).click();
  await other.getByRole('menuitem', { name: 'Obriši tablicu' }).click();
  await expect(theirs).toHaveCount(0);

  await page.bringToFront();
  await expect(table).toHaveCount(0);
  await expect(page.getByRole('alert')).toHaveCount(0);
  await editor.click();
  await page.keyboard.press('Control+End');
  await page.keyboard.type(' i kraj');
  await expect(other.locator('.ProseMirror').first()).toContainText('i kraj');
});

test('whole cells are merged, copied as Word reads them and split again', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto(await newDocument(page, 'Spajanje ćelija'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await insertTable(page, '3 × 3');
  const table = page.locator('.ponistra-table').first();
  const cells = table.getByRole('gridcell');
  await page.keyboard.type('A');
  await tab(page, 'B1');
  await page.keyboard.type('B');

  await dragCells(page, table, 'A1', 'B2');
  await expect.poll(() => selectedCells(table)).toEqual(['A1', 'A2', 'B1', 'B2']);
  await tableCommand(page, 'Spoji ćelije');
  await expect(cells).toHaveCount(6);
  const merged = cellAt(table, 'A1');
  await expect(merged).toHaveAttribute('aria-rowspan', '2');
  await expect(merged).toHaveAttribute('aria-colspan', '2');
  await expect(merged.locator('p')).toHaveText(['A', 'B']);

  await page.keyboard.press('Control+c');
  const html = await page.evaluate(async () => {
    const [item] = await navigator.clipboard.read();
    return (await item.getType('text/html')).text();
  });
  expect(html).toMatch(/<td[^>]*rowspan="2"/);
  expect(html).toMatch(/<td[^>]*colspan="2"/);

  await editor.locator(':scope > p').last().click();
  await page.keyboard.press('Control+v');
  const tables = page.locator('.ponistra-table');
  await expect(tables).toHaveCount(2);
  const pasted = cellAt(tables.nth(1), 'A1');
  await expect(pasted).toHaveAttribute('aria-colspan', '2');
  await expect(pasted.locator('p')).toHaveText(['A', 'B']);

  await merged.click();
  await tableCommand(page, 'Razdvoji ćeliju');
  await expect(cells).toHaveCount(9);
  await expect(cellAt(table, 'A1').locator('p')).toHaveText(['A', 'B']);
});

test('a table from Word keeps its merged cells and formatting, and pastes into cells', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Tablica iz Worda'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await paste(
    page,
    '<table border="1"><tr><td colspan="2"><p><b>Ponuda</b></p></td></tr>' +
      '<tr><td><p>Najam</p><p>dizalice</p></td><td><p>120</p></td></tr></table>',
  );
  const table = page.locator('.ponistra-table');
  await expect(table.getByRole('gridcell')).toHaveCount(3);
  await expect(cellAt(table, 'A1')).toHaveAttribute('aria-colspan', '2');
  await expect(cellAt(table, 'A2').locator('p')).toHaveText(['Najam', 'dizalice']);
  await cellAt(table, 'A1').click();
  await expect(writing(table, 'A1').locator('strong')).toHaveText('Ponuda');

  await cellAt(table, 'B2').click();
  await paste(page, '<table><tr><td>130</td><td>EUR</td></tr><tr><td>140</td></tr></table>');
  await expect(table.getByRole('grid')).toHaveAttribute('aria-rowcount', '4');
  await expect
    .poll(() => cellTexts(table))
    .toEqual(['Ponuda', '', 'Najam dizalice', '130', 'EUR', '', '140', '']);
});

test('columns and rows take the size their edges are dragged to, as in Excel, and fit their text on a double click', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Širina stupca'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '3 × 2');
  const table = page.locator('.ponistra-table');
  const text = 'Dugačak opis stavke bez prijeloma';
  await tab(page, 'B1');
  await page.keyboard.type(text);
  await page.keyboard.press('Tab');
  await expect(cellAt(table, 'B1')).toHaveText(text);
  const grid = table.getByRole('grid');
  const sizes = () =>
    grid.evaluate((grid) => ({
      widths: [...grid.querySelectorAll('[role="columnheader"]')].map(
        (heading) => heading.getBoundingClientRect().width,
      ),
      heights: [...grid.querySelectorAll('[role="rowheader"]')].map(
        (heading) => heading.getBoundingClientRect().height,
      ),
    }));
  const near = (got: number[], wanted: number[]) =>
    got.length === wanted.length && got.every((size, index) => Math.abs(size - wanted[index]) <= 2);
  const drag = async (from: { x: number; y: number }, dx: number, dy: number) => {
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    await page.mouse.move(from.x + dx, from.y + dy, { steps: 5 });
    await page.mouse.up();
  };
  const edges = async (address: string) => {
    const box = (await cellAt(table, address).boundingBox())!;
    return {
      right: { x: box.x + box.width, y: box.y + box.height / 2 },
      bottom: { x: box.x + box.width / 2, y: box.y + box.height },
    };
  };

  await expect
    .poll(async () => {
      const [one, two] = (await sizes()).heights;
      return one - two;
    })
    .toBeGreaterThan(10);
  const before = await sizes();
  const [a, b, c] = before.widths;
  const [one, two] = before.heights;
  await drag((await edges('A1')).right, 120, 0);
  await expect.poll(async () => near((await sizes()).widths, [a + 120, b, c])).toBe(true);
  await drag((await edges('A1')).bottom, 0, 40);
  await expect.poll(async () => near((await sizes()).heights, [one + 40, two])).toBe(true);

  await page.waitForTimeout(600);
  await page.reload();
  await expect(cellAt(table, 'B1')).toHaveText(text);
  await expect.poll(async () => near((await sizes()).widths, [a + 120, b, c])).toBe(true);
  expect(near((await sizes()).heights, [one + 40, two])).toBe(true);

  const edge = (await edges('B1')).right;
  await page.mouse.dblclick(edge.x, edge.y);
  await expect.poll(async () => (await sizes()).widths[1]).toBeGreaterThan(b + 20);
  const row = (await edges('A1')).bottom;
  await page.mouse.dblclick(row.x, row.y);
  await expect.poll(async () => near((await sizes()).heights, [two, two])).toBe(true);
});

test('a document reads its tables in the language chosen from its menu', async ({ page }) => {
  const url = await newDocument(page, 'Jezik dokumenta');
  await page.goto(url);
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 2');
  await page.keyboard.type('46006');
  await cellFormat(page, 'Datum');
  await page.keyboard.press('Tab');
  const date = cellAt(page.locator('.ponistra-table'), 'A1');
  await expect(date).toHaveText('15.12.2025');
  const choose = async () => {
    await page.locator('header button[aria-current="page"]').click();
    await page.getByRole('menuitem', { name: 'Jezik dokumenta' }).click();
  };
  await choose();
  await expect(page.getByRole('menuitemradio', { name: 'Hrvatski' })).toBeChecked();
  await page.getByRole('menuitemradio', { name: 'Britanski engleski' }).click();
  await expect(date).toHaveText('15/12/2025');
  await page.reload();
  await expect(date).toHaveText('15/12/2025');
  await choose();
  await expect(page.getByRole('menuitemradio', { name: 'Britanski engleski' })).toBeChecked();
});

test('a formula is written in its cell, pointed with clicks and computed by the server', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Tablica s formulama'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 3');
  const table = page.locator('.ponistra-table');
  const cell = (address: string) => cellAt(table, address);
  const formula = page.locator('.ponistra-formula');

  await page.keyboard.type('2');
  await tab(page, 'B1');
  await page.keyboard.type('3,5');
  await tab(page, 'A2');
  await page.keyboard.type('=SUM(');
  await expect(formula).toBeFocused();
  await cell('A1').click();
  await page.keyboard.type(';');
  await cell('B1').click();
  await page.keyboard.type(')');
  await expect(formula).toHaveValue('=SUM(A1;B1)');
  await page.keyboard.press('Enter');
  await expect(cell('A2')).toHaveText('5,5');
  await expect(writing(table, 'A3')).toBeFocused();

  await cell('A2').click();
  await expect(formula).toHaveValue('=SUM(A1;B1)');
  await page.keyboard.press('Escape');
  await expect(formula).toHaveCount(0);
  await expect(cell('A2')).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('Delete');
  await expect(cell('A2')).toHaveText('');
  await page.keyboard.press('Control+z');
  await expect(cell('A2')).toHaveText('5,5');
  await cell('A1').click();
  await page.keyboard.press('Control+a');
  await page.keyboard.type('4');
  await page.keyboard.press('Tab');
  await expect(cell('A2')).toHaveText('7,5');

  await cell('B2').click();
  await page.keyboard.type('=A9');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert')).toHaveText('Adresa je izvan tablice.');
  await expect(formula).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(formula).toHaveCount(0);
  await expect(cell('B2')).toHaveText('');

  await page.reload();
  await expect(cell('A2')).toHaveText('7,5');
});

test('a table in use shows its headings, which select whole lines and point them from a formula', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Tablica sa zaglavljima'));
  await page.locator('.ProseMirror').first().click();
  await page.keyboard.type('Ponuda');
  await page.keyboard.press('Enter');
  await insertTable(page, '3 × 3');
  const table = page.locator('.ponistra-table');
  const grid = table.getByRole('grid');
  const letter = (name: string) => grid.getByRole('columnheader', { name, exact: true });
  const number = (name: string) => grid.getByRole('rowheader', { name, exact: true });
  const shown = grid.locator('.ponistra-mirror[data-headings]');

  for (const value of ['1', '2', '', '3', '4']) {
    await page.keyboard.type(value);
    await page.keyboard.press('Tab');
  }
  await expect(shown).toHaveCount(1);
  await letter('B').click();
  await expect.poll(() => selectedCells(table)).toEqual(['B1', 'B2', 'B3']);
  await number('2').click();
  await expect.poll(() => selectedCells(table)).toEqual(['A2', 'B2', 'C2']);
  const corner = (await letter('A').boundingBox())!;
  await page.mouse.click(corner.x - 10, corner.y + corner.height / 2);
  await expect.poll(() => selectedCells(table)).toHaveLength(9);

  await cellAt(table, 'C3').click();
  await page.keyboard.type('=SUM(');
  await letter('B').click();
  await expect(page.locator('.ponistra-formula')).toHaveValue('=SUM(B1:B3');
  await page.keyboard.type(')');
  await page.keyboard.press('Enter');
  await expect(cellAt(table, 'C3')).toHaveText('6');

  await cellAt(table, 'B2').click();
  await expect(shown).toHaveCount(1);
  const box = await cellAt(table, 'B2').boundingBox();
  await page.locator('.ProseMirror p').first().click();
  await expect(shown).toHaveCount(0);
  expect(await cellAt(table, 'B2').boundingBox()).toEqual(box);
});

test('a whole column or row formatted by its heading gives its look to every cell, a row added later too', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Oblikovani stupci'));
  await page.locator('.ProseMirror').first().click();
  await page.keyboard.type('Ponuda');
  await page.keyboard.press('Enter');
  await insertTable(page, '3 × 3');
  const table = page.locator('.ponistra-table');
  const grid = table.getByRole('grid');
  const letter = (name: string) => grid.getByRole('columnheader', { name, exact: true });
  const number = (name: string) => grid.getByRole('rowheader', { name, exact: true });
  const bold = pressed(page, 'Podebljano');
  const choose = async (address: string) => {
    await cellAt(table, address).click();
    await page.keyboard.press('Escape');
    await expect(cellAt(table, address)).toHaveAttribute('aria-selected', 'true');
  };

  for (const value of ['1', '2', '3', '4']) {
    await page.keyboard.type(value);
    await page.keyboard.press('Tab');
  }
  await choose('B2');
  await page.keyboard.press('Control+i');
  await letter('B').click();
  await expect.poll(() => selectedCells(table)).toEqual(['B1', 'B2', 'B3']);
  await expect(bold).toHaveAttribute('aria-pressed', 'false');
  await page.keyboard.press('Control+b');
  await expect(bold).toHaveAttribute('aria-pressed', 'true');
  await number('2').click();
  await page.keyboard.press('Control+Shift+E');

  await choose('B3');
  await tableCommand(page, 'Umetni redak ispod');
  await page.reload();
  await expect(cellAt(table, 'B4')).toHaveText('');
  for (const [address, strong, centred] of [
    ['B1', true, false],
    ['B4', true, false],
    ['A2', false, true],
    ['B2', true, true],
    ['A1', false, false],
  ] as const) {
    await choose(address);
    await expect(bold).toHaveAttribute('aria-pressed', String(strong));
    await aligned(page, 'Centriraj', centred);
  }
  await choose('B2');
  await expect(pressed(page, 'Kurziv')).toHaveAttribute('aria-pressed', 'true');
  await cellAt(table, 'B4').click();
  await page.keyboard.type('5');
  await expect(writing(table, 'B4').locator('strong')).toHaveText('5');
});

test('a named table is pointed at by its name from a formula in another table', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Dvije tablice'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await insertTable(page, '2 × 2');
  const named = page.locator('.ponistra-table').first();
  const caption = named.locator('.ponistra-table-name');
  await expect(caption).toBeHidden();
  await page.keyboard.type('2');
  await tab(page, 'B1');
  await page.keyboard.type('3');
  await tableCommand(page, 'Naziv tablice…');
  const dialog = page.getByRole('dialog', { name: 'Naziv tablice' });
  await dialog.getByLabel('Naziv').fill('Cijene 2026');
  await dialog.getByRole('button', { name: 'Spremi' }).click();
  await expect(caption).toHaveText('Cijene 2026');

  await editor.locator(':scope > p').last().click();
  await insertTable(page, '2 × 2');
  const formula = page.locator('.ponistra-formula');
  const total = cellAt(page.locator('.ponistra-table').nth(1), 'A1');
  await page.keyboard.type('=SUM(');
  await cellAt(named, 'A1').click();
  await page.keyboard.type(';');
  await cellAt(named, 'B1').click();
  await page.keyboard.type(')');
  await expect(formula).toHaveValue("=SUM('Cijene 2026'!A1;'Cijene 2026'!B1)");
  await page.keyboard.press('Enter');
  await expect(total).toHaveText('5');

  await cellAt(named, 'A1').click();
  await page.keyboard.press('Control+a');
  await page.keyboard.type('4');
  await page.keyboard.press('Tab');
  await expect(total).toHaveText('7');

  await tableCommand(page, 'Naziv tablice…');
  await dialog.getByLabel('Naziv').fill('');
  await expect(dialog.getByText('Formule upućuju na ovu tablicu po nazivu')).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Spremi' })).toBeDisabled();
  await page.keyboard.press('Escape');

  await page.reload();
  await expect(caption).toHaveText('Cijene 2026');
  await expect(total).toHaveText('7');
});

test("a cell keeps its look as Word keeps a paragraph mark's: under a formula, cleared and written again", async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Oblikovane ćelije'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 3');
  const table = page.locator('.ponistra-table');
  const cell = cellAt(table, 'A2');
  const formula = page.locator('.ponistra-formula');
  const bold = pressed(page, 'Podebljano');
  const choose = async (address: string) => {
    await cellAt(table, address).click();
    await page.keyboard.press('Escape');
    await expect(cellAt(table, address)).toHaveAttribute('aria-selected', 'true');
  };

  await expect(writing(table, 'A1')).toBeFocused();
  await page.keyboard.type('2');
  await page.keyboard.press('Tab');
  await expect(writing(table, 'B1')).toBeFocused();
  await page.keyboard.type('3');
  await page.keyboard.press('Tab');
  await expect(writing(table, 'A2')).toBeFocused();
  await page.keyboard.press('Control+b');
  await page.keyboard.type('=A1+B1');
  await expect(formula).toHaveValue('=A1+B1');
  await page.keyboard.press('Enter');
  await expect(cell).toHaveText('5');

  await choose('A2');
  await expect(bold).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Control+b');
  await expect(bold).toHaveAttribute('aria-pressed', 'false');
  await expect(cell).toHaveText('5');
  await page.keyboard.press('Control+b');
  await expect(bold).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press('Control+Shift+E');
  await aligned(page, 'Centriraj', true);

  await page.keyboard.press('Delete');
  await expect(cell).toHaveText('');
  await page.keyboard.type('x');
  await expect(writing(table, 'A2').locator('strong')).toHaveText('x');
  await expect(writing(table, 'A2').locator('p')).toHaveCSS('text-align', 'center');
  await page.keyboard.press('Backspace');
  await page.keyboard.type('=A1*B1');
  await page.keyboard.press('Enter');
  await expect(cell).toHaveText('6');

  await page.reload();
  await expect(cell).toHaveText('6');
  await choose('A2');
  await expect(bold).toHaveAttribute('aria-pressed', 'true');
  await aligned(page, 'Centriraj', true);
  await choose('A1');
  await expect(bold).toHaveAttribute('aria-pressed', 'false');
});

test('copied formulas move as in Excel and leave their values for other programs', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto(await newDocument(page, 'Kopirane formule'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await insertTable(page, '2 × 3');
  const table = page.locator('.ponistra-table').first();
  const cell = (address: string) => cellAt(table, address);
  await page.keyboard.type('2');
  await tab(page, 'B1');
  await page.keyboard.type('=A1*2+$A$1');
  await page.keyboard.press('Enter');
  await expect(cell('B1')).toHaveText('6');

  await dragCells(page, table, 'A1', 'B1');
  await expect.poll(() => selectedCells(table)).toEqual(['A1', 'B1']);
  await page.keyboard.press('Control+c');
  const html = await page.evaluate(async () => {
    const [item] = await navigator.clipboard.read();
    return (await item.getType('text/html')).text();
  });
  expect(html).toMatch(/<td[^>]*data-formula="=A1\*2\+\$A\$1"[^>]*><p>6<\/p><\/td>/);

  await cell('A2').click();
  await page.keyboard.press('Control+v');
  await expect(cell('B2')).toHaveText('6');
  await cell('A2').click();
  await page.keyboard.press('Control+a');
  await page.keyboard.type('5');
  await page.keyboard.press('Tab');
  await expect(page.locator('.ponistra-formula')).toHaveValue('=A2*2+$A$1');
  await page.keyboard.press('Escape');
  await expect(cell('B2')).toHaveText('12');

  await editor.locator(':scope > p').last().click();
  await page.keyboard.press('Control+v');
  await expect.poll(() => cellTexts(page.locator('.ponistra-table').nth(1))).toEqual(['2', '6']);
});

test('a number format writes the value as the language does, the typed number stays for editing', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto(await newDocument(page, 'Oblik broja'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 2');
  const table = page.locator('.ponistra-table');
  const cell = (address: string) => cellAt(table, address);

  await page.keyboard.type('1234,5');
  await cellFormat(page, 'Valuta');
  await expect(writing(table, 'A1')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(cell('A1')).toHaveText('1.234,50 €');

  await page.keyboard.type('9:05');
  await cellFormat(page, 'Vrijeme');
  await page.keyboard.press('Tab');
  await expect(cell('B1')).toHaveText('09:05');

  await cell('A1').click();
  await expect(writing(table, 'A1')).toBeFocused();
  await expect(writing(table, 'A1')).toHaveText('1234,5');
  await page.keyboard.press('End');
  await page.keyboard.type('6');
  await cell('A2').click();
  await expect(cell('A1')).toHaveText('1.234,56 €');

  await cell('A1').click();
  await cellFormat(page, 'Prilagođeno…');
  const code = page.getByRole('textbox', { name: 'Kod oblika' });
  await expect(code).toHaveValue('#.##0,00 "€"');
  await code.fill('#.##0,0" kn"');
  await page.keyboard.press('Enter');
  await cell('A2').click();
  await expect(cell('A1')).toHaveText('1.234,6 kn');

  await page.reload();
  await expect(cell('A1')).toHaveText('1.234,6 kn');
  await expect(cell('B1')).toHaveText('09:05');

  await dragCells(page, table, 'A1', 'B1');
  await page.keyboard.press('Control+c');
  await cell('A2').click();
  await page.keyboard.press('Control+v');
  await page.keyboard.press('Escape');
  await expect.poll(() => cellTexts(table)).toEqual(['1.234,6 kn', '09:05', '1.234,6 kn', '09:05']);
});

test('rows are sorted under their header as the language orders them, and the sort undone', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Sortiranje'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 5');
  const table = page.locator('.ponistra-table');
  for (const header of ['Ime', 'Iznos']) {
    await page.keyboard.press('Control+b');
    await page.keyboard.type(header);
    await page.keyboard.press('Tab');
  }
  const rows = ['Željko', '1', 'ana', '2', 'Čedo', '3', 'Zoran', '4'];
  for (const [index, text] of rows.entries()) {
    await page.keyboard.type(text);
    if (index < rows.length - 1) await page.keyboard.press('Tab');
  }
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows]);

  await cellAt(table, 'A2').click();
  await tableCommand(page, 'Sortiraj uzlazno');
  const sorted = ['ana', '2', 'Čedo', '3', 'Zoran', '4', 'Željko', '1'];
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...sorted]);
  await tableCommand(page, 'Sortiraj silazno');
  await expect
    .poll(() => cellTexts(table))
    .toEqual(['Ime', 'Iznos', 'Željko', '1', 'Zoran', '4', 'Čedo', '3', 'ana', '2']);

  await page.keyboard.press('Control+z');
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...sorted]);
  await page.keyboard.press('Control+z');
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows]);
});

test('an action totals the columns of numbers below the data and is undone, leaving later edits', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Zbrojevi'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 3');
  const table = page.locator('.ponistra-table');
  for (const header of ['Ime', 'Iznos']) {
    await page.keyboard.press('Control+b');
    await page.keyboard.type(header);
    await page.keyboard.press('Tab');
  }
  const rows = ['ana', '2', 'Čedo', '3,5'];
  for (const [index, text] of rows.entries()) {
    await page.keyboard.type(text);
    if (index < rows.length - 1) await page.keyboard.press('Tab');
  }
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows]);

  await tableCommand(page, 'Zbroji stupce');
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows, 'Ukupno', '5,5']);
  const bar = page.getByRole('status').filter({ hasText: 'Izvedeno: Zbroji stupce' });
  await expect(bar).toBeVisible();
  await cellAt(table, 'A4').click();
  await expect(writing(table, 'A4').locator('strong')).toHaveText('Ukupno');

  await cellAt(table, 'B2').click();
  await tableCommand(page, 'Sortiraj silazno');
  const sorted = ['Čedo', '3,5', 'ana', '2'];
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...sorted, 'Ukupno', '5,5']);

  await bar.getByRole('button', { name: 'Poništi akciju' }).click();
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...sorted]);
  await expect(bar).toBeHidden();
});

test('a cell of the totals row takes the function chosen for its column, a column of text the count of its values', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Ukupno po izboru'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 3');
  const table = page.locator('.ponistra-table');
  for (const header of ['Ime', 'Iznos']) {
    await page.keyboard.press('Control+b');
    await page.keyboard.type(header);
    await page.keyboard.press('Tab');
  }
  const rows = ['ana', '2', 'Čedo', '3,5'];
  for (const [index, text] of rows.entries()) {
    await page.keyboard.type(text);
    if (index < rows.length - 1) await page.keyboard.press('Tab');
  }
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows]);
  const total = async (address: string, way: string) => {
    await cellAt(table, address).click();
    await page.getByRole('button', { name: 'Tablica' }).click();
    await page.getByRole('menuitem', { name: 'Ukupno u stupcu' }).click();
    await page.getByRole('menuitem', { name: way }).click();
  };

  await total('B2', 'Prosjek');
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows, 'Ukupno', '2,75']);

  await cellAt(table, 'A4').click();
  await expect(writing(table, 'A4').locator('strong')).toHaveText('Ukupno');
  await page.getByRole('button', { name: 'Tablica' }).click();
  await page.getByRole('menuitem', { name: 'Ukupno u stupcu' }).click();
  await expect(page.getByRole('menuitem', { name: 'Zbroj', exact: true })).toBeDisabled();
  await page.getByRole('menuitem', { name: 'Broj vrijednosti' }).click();
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows, '2', '2,75']);

  await total('B4', 'Ništa');
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows, '2', '']);
  await total('A4', 'Ništa');
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows]);
});

test('a calculated column holds the operation over the columns picked in every row, and in a row added', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Izračunati stupac'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '3 × 3');
  const table = page.locator('.ponistra-table');
  for (const header of ['Količina', 'Cijena', 'Iznos']) {
    await page.keyboard.press('Control+b');
    await page.keyboard.type(header);
    await page.keyboard.press('Tab');
  }
  for (const text of ['3', '1,5', '', '2']) {
    await page.keyboard.type(text);
    await page.keyboard.press('Tab');
  }
  await page.keyboard.type('0,25');
  const headers = ['Količina', 'Cijena', 'Iznos'];
  await expect.poll(() => cellTexts(table)).toEqual([...headers, '3', '1,5', '', '2', '0,25', '']);

  await cellAt(table, 'C2').click();
  await page.getByRole('button', { name: 'Tablica' }).click();
  await page.getByRole('menuitem', { name: 'Izračunati stupac…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Izračunati stupac' });
  await expect(dialog.getByRole('button', { name: 'Umnožak' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  const columns = dialog.getByRole('group', { name: 'Stupci' });
  await expect(columns.getByRole('button')).toHaveCount(2);
  await expect(dialog.getByRole('button', { name: 'Izračunaj' })).toBeDisabled();
  await columns.getByRole('button', { name: 'Količina' }).click();
  await columns.getByRole('button', { name: 'Cijena' }).click();
  await expect(dialog.locator('p').first()).toHaveText('Iznos = Količina × Cijena');
  await dialog.getByRole('button', { name: 'Izračunaj' }).click();
  await expect(dialog).toBeHidden();
  await expect
    .poll(() => cellTexts(table))
    .toEqual([...headers, '3', '1,5', '4,5', '2', '0,25', '0,5']);

  await cellAt(table, 'C3').click();
  await page.keyboard.press('Tab');
  await writes(page, 'A4');
  await page.keyboard.type('4');
  await page.keyboard.press('Tab');
  await page.keyboard.type('2');
  await cellAt(table, 'A1').click();
  await expect
    .poll(() => cellTexts(table))
    .toEqual([...headers, '3', '1,5', '4,5', '2', '0,25', '0,5', '4', '2', '8']);
});

test('an action groups the data by the column the cursor is in, subtotalling each group', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Skupine'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 4');
  const table = page.locator('.ponistra-table');
  for (const header of ['Ime', 'Iznos']) {
    await page.keyboard.press('Control+b');
    await page.keyboard.type(header);
    await page.keyboard.press('Tab');
  }
  const rows = ['ana', '2', 'Čedo', '3,5', 'ana', '1'];
  for (const [index, text] of rows.entries()) {
    await page.keyboard.type(text);
    if (index < rows.length - 1) await page.keyboard.press('Tab');
  }
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows]);

  await cellAt(table, 'A2').click();
  await tableCommand(page, 'Grupiraj po stupcu');
  const grouped = ['ana', '2', 'ana', '1', 'ana ukupno', '3', 'Čedo', '3,5', 'Čedo ukupno', '3,5'];
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...grouped, 'Ukupno', '6,5']);
  await cellAt(table, 'A4').click();
  await expect(writing(table, 'A4').locator('strong')).toHaveText('ana ukupno');

  const bar = page.getByRole('status').filter({ hasText: 'Izvedeno: Grupiraj po stupcu' });
  await bar.getByRole('button', { name: 'Poništi akciju' }).click();
  await expect.poll(() => cellTexts(table)).toEqual(['Ime', 'Iznos', ...rows]);
});

test('an action cleans the table data, trimming text, making numbers and taking out empty rows', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Čišćenje'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 4');
  const table = page.locator('.ponistra-table');
  const cells = table.getByRole('gridcell');
  const name = cellAt(table, 'A2');
  const typed = ['Ime', 'Iznos', ' ana  kovač ', '1 234,5', '', '', 'Čedo', '3,5'];
  for (const [index, text] of typed.entries()) {
    if (text) await page.keyboard.type(text);
    if (index < typed.length - 1) await page.keyboard.press('Tab');
  }
  await expect(cells).toHaveCount(8);
  await expect.poll(() => name.textContent()).toBe(' ana  kovač ');

  await tableCommand(page, 'Očisti podatke tablice');
  await expect
    .poll(() => cellTexts(table))
    .toEqual(['Ime', 'Iznos', 'ana kovač', '1234,5', 'Čedo', '3,5']);
  await expect.poll(() => name.textContent()).toBe('ana kovač');
  const bar = page.getByRole('status').filter({ hasText: 'Izvedeno: Očisti podatke tablice' });

  await bar.getByRole('button', { name: 'Poništi akciju' }).click();
  await expect(cells).toHaveCount(8);
  await expect.poll(() => name.textContent()).toBe(' ana  kovač ');
  await expect(cellAt(table, 'B2')).toHaveText('1 234,5');
});

test('a table is duplicated below as values, which stay as they were when its cells change', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Snimka'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '3 × 1');
  const tables = page.locator('.ponistra-table');
  const texts = (index: number) => cellTexts(tables.nth(index));
  await page.keyboard.type('2');
  await tab(page, 'B1');
  await page.keyboard.type('3,5');
  await tab(page, 'C1');
  await page.keyboard.type('=A1*B1');
  await page.keyboard.press('Enter');
  await expect.poll(() => texts(0)).toEqual(['2', '3,5', '7']);

  const choose = async () => {
    await cellAt(tables.first(), 'C1').click();
    await page.keyboard.press('Escape');
  };
  await choose();
  await tableCommand(page, 'Udvostruči kao vrijednosti');
  await expect(tables).toHaveCount(2);
  await expect.poll(() => texts(1)).toEqual(['2', '3,5', '7']);
  await page.keyboard.press('Control+z');
  await expect(tables).toHaveCount(1);

  await choose();
  await tableCommand(page, 'Udvostruči kao vrijednosti');
  await expect.poll(() => texts(1)).toEqual(['2', '3,5', '7']);
  await cellAt(tables.first(), 'A1').click();
  await page.keyboard.press('Control+a');
  await page.keyboard.type('4');
  await page.keyboard.press('Tab');
  await expect(cellAt(tables.first(), 'C1')).toHaveText('14');
  await expect.poll(() => texts(1)).toEqual(['2', '3,5', '7']);
  await cellAt(tables.nth(1), 'C1').click();
  await expect(page.locator('.ponistra-formula')).toHaveCount(0);

  await page.reload();
  await expect.poll(() => texts(0)).toEqual(['4', '3,5', '14']);
  await expect.poll(() => texts(1)).toEqual(['2', '3,5', '7']);
});

test('rows frozen above a cell stay at the top while the table runs on past them, and are freed', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Zamrznuti redci'));
  await page.locator('.ProseMirror').first().click();
  const rows = Array.from(
    { length: 60 },
    (_, index) => `<tr><td>Stavka ${index + 1}</td><td>${(index + 1) * 12}</td></tr>`,
  ).join('');
  await paste(page, `<table><tbody><tr><td>Artikl</td><td>Iznos</td></tr>${rows}</tbody></table>`);
  const table = page.locator('.ponistra-table');
  await expect(table.getByRole('grid')).toHaveAttribute('aria-rowcount', '62');
  const frozen = table.locator('[role="gridcell"][data-frozen]');

  await cellAt(table, 'A1').click();
  await page.getByRole('button', { name: 'Tablica' }).click();
  await expect(page.getByRole('menuitem', { name: 'Zamrzni retke iznad' })).toBeDisabled();
  await expect(page.getByRole('menuitem', { name: 'Odmrzni retke' })).toBeDisabled();
  await page.keyboard.press('Escape');
  const down = async () => {
    const box = (await table.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, Math.max(box.y, 0) + 100);
    await page.mouse.wheel(0, 1200);
    await expect.poll(async () => (await table.boundingBox())!.y).toBeLessThan(-600);
  };
  await cellAt(table, 'A2').click();
  await tableCommand(page, 'Zamrzni retke iznad');
  await down();
  await expect(frozen).toHaveText(['Artikl', 'Iznos']);
  const header = cellAt(table, 'A1');
  const bar = (await page.getByRole('toolbar').first().boundingBox())!;
  expect((await header.boundingBox())!.y).toBeGreaterThanOrEqual(bar.y + bar.height);

  await tableCommand(page, 'Odmrzni retke');
  await down();
  await expect(frozen).toHaveCount(0);
  await page.keyboard.press('Control+z');
  await expect(frozen).toHaveText(['Artikl', 'Iznos']);
  await header.click();
  await expect(writing(table, 'A1')).toBeFocused();
  await expect(writing(table, 'A1')).toBeInViewport();
});

test('the fill handle goes on with numbers, dates and counted text, moves formulas, and is undone at once; Ctrl+D and Ctrl+R copy', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Popunjavanje'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '4 × 6');
  const table = page.locator('.ponistra-table');
  const cell = (address: string) => cellAt(table, address);
  for (const text of ['1', '20.10.2026', 'Stavka 1']) {
    await page.keyboard.type(text);
    await page.keyboard.press('Tab');
  }
  await page.keyboard.type('=A1*2');
  await page.keyboard.press('Enter');
  await cell('A2').click();
  await page.keyboard.type('2');
  await page.keyboard.press('Tab');
  await expect(cell('D1')).toHaveText('2');
  await expect(cell('A2')).toHaveText('2');

  const handle = table.locator('.ponistra-fill-handle');
  // The handle moves to the cells chosen at the next frame the table draws.
  const fillTo = async (corner: string, address: string) => {
    const at = await standing(cell(corner));
    const from = { x: at.x + at.width, y: at.y + at.height };
    await expect
      .poll(async () => {
        const box = await handle.boundingBox();
        return (
          !!box &&
          Math.abs(box.x + box.width / 2 - from.x) < 2 &&
          Math.abs(box.y + box.height / 2 - from.y) < 2
        );
      })
      .toBe(true);
    const to = await standing(cell(address));
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 5 });
    await expect(table.locator('.ponistra-fill-frame')).toBeVisible();
    await page.mouse.up();
  };
  const column = (letter: string, rows: number) =>
    Promise.all(
      Array.from({ length: rows }, (_, index) => cell(`${letter}${index + 1}`).innerText()),
    );

  await dragCells(page, table, 'A1', 'A2');
  await fillTo('A2', 'A6');
  await expect.poll(() => column('A', 6)).toEqual(['1', '2', '3', '4', '5', '6']);
  expect(await selectedCells(table)).toEqual(['A1', 'A2', 'A3', 'A4', 'A5', 'A6']);

  await cell('B1').click();
  await fillTo('B1', 'B4');
  await expect
    .poll(() => column('B', 4))
    .toEqual(['20.10.2026', '21.10.2026', '22.10.2026', '23.10.2026']);

  await dragCells(page, table, 'C1', 'D1');
  await fillTo('D1', 'C3');
  await expect.poll(() => column('C', 3)).toEqual(['Stavka 1', 'Stavka 2', 'Stavka 3']);
  await expect.poll(() => column('D', 3)).toEqual(['2', '4', '6']);
  expect(await selectedCells(table)).toEqual(['C1', 'C2', 'C3', 'D1', 'D2', 'D3']);

  await page.keyboard.press('Control+z');
  await expect.poll(() => column('C', 3)).toEqual(['Stavka 1', '', '']);
  await expect.poll(() => column('D', 3)).toEqual(['2', '', '']);
  await expect.poll(() => column('A', 6)).toEqual(['1', '2', '3', '4', '5', '6']);

  await dragCells(page, table, 'C1', 'C3');
  await page.keyboard.press('Control+d');
  await expect.poll(() => column('C', 3)).toEqual(['Stavka 1', 'Stavka 1', 'Stavka 1']);
  await cell('D2').click();
  await page.keyboard.press('Control+d');
  await expect(cell('D2')).toHaveText('4');
  await cell('B5').click();
  await page.keyboard.press('Control+r');
  await expect(cell('B5')).toHaveText('5');
});

/** The colour the table's canvas shows just inside a cell's top left corner. */
async function ground(table: Locator, address: string): Promise<string> {
  const cell = (await cellAt(table, address).boundingBox())!;
  return table.locator('canvas.ponistra-canvas').evaluate((canvas: HTMLCanvasElement, cell) => {
    const box = canvas.getBoundingClientRect();
    const x = Math.floor(((cell.x + 3 - box.left) * canvas.width) / box.width);
    const y = Math.floor(((cell.y + 3 - box.top) * canvas.height) / box.height);
    const pixel = document.createElement('canvas').getContext('2d', { willReadFrequently: true })!;
    pixel.drawImage(canvas, x, y, 1, 1, 0, 0, 1, 1);
    return `rgba(${[...pixel.getImageData(0, 0, 1, 1).data].join(', ')})`;
  }, cell);
}

test('cells are filled from the toolbar, a whole column as its line, in either theme, and the fill taken off', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Ispunjene ćelije'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '3 × 3');
  const table = page.locator('.ponistra-table');
  const letter = (name: string) =>
    table.getByRole('grid').getByRole('columnheader', { name, exact: true });
  const fill = async (name: string) => {
    await page.getByRole('button', { name: 'Tablica' }).click();
    await page.getByRole('menuitem', { name: 'Ispuna ćelija' }).click();
    await page.getByRole('menuitemcheckbox', { name }).click();
  };
  const yellow = 'rgba(253, 230, 138, 255)';
  const blue = 'rgba(191, 219, 254, 255)';

  await page.keyboard.type('Stavka');
  await dragCells(page, table, 'A1', 'B2');
  await expect.poll(() => selectedCells(table)).toEqual(['A1', 'A2', 'B1', 'B2']);
  await fill('Žuta');
  await letter('C').click();
  await fill('Plava');
  await cellAt(table, 'B3').click();
  await expect.poll(() => ground(table, 'A2')).toBe(yellow);
  await expect.poll(() => ground(table, 'C3')).toBe(blue);
  await expect.poll(() => ground(table, 'A3')).toBe('rgba(0, 0, 0, 0)');

  await page.reload();
  await expect(cellAt(table, 'A1')).toHaveText('Stavka');
  await expect.poll(() => ground(table, 'B1')).toBe(yellow);
  await expect.poll(() => ground(table, 'C1')).toBe(blue);
  await cellAt(table, 'B2').click();
  await expect(table.locator('.ponistra-cell-box:focus-within')).toHaveCSS(
    'background-color',
    'rgb(253, 230, 138)',
  );
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect.poll(() => ground(table, 'A1')).toBe('rgba(92, 74, 10, 255)');
  await page.emulateMedia({ colorScheme: 'light' });

  await dragCells(page, table, 'A1', 'B2');
  await fill('Bez boje');
  await cellAt(table, 'B3').click();
  await expect.poll(() => ground(table, 'A1')).toBe('rgba(0, 0, 0, 0)');
  await expect.poll(() => ground(table, 'C2')).toBe(blue);
});

test('rows and columns are hidden and shown again, the keys passing over them and a subtotal leaving the hidden rows out', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Skriveni retci'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 4');
  const table = page.locator('.ponistra-table');
  const cell = (address: string) => cellAt(table, address);
  const grid = table.getByRole('grid');
  const number = (name: string) => grid.getByRole('rowheader', { name, exact: true });
  const letter = (name: string) => grid.getByRole('columnheader', { name, exact: true });
  const command = async (name: string) => {
    await page.getByRole('button', { name: 'Tablica' }).click();
    await page.getByRole('menuitem', { name }).click();
  };

  await page.keyboard.type('1');
  await tab(page, 'B1');
  await tab(page, 'A2');
  await page.keyboard.type('2');
  await tab(page, 'B2');
  await tab(page, 'A3');
  await page.keyboard.type('4');
  await tab(page, 'B3');
  await tab(page, 'A4');
  await page.keyboard.type('=SUBTOTAL(109;A1:A3)');
  await page.keyboard.press('Enter');
  await expect(cell('A4')).toHaveText('7');

  await cell('A2').click();
  await command('Sakrij retke');
  await expect(number('2')).toHaveCount(0);
  await expect(cell('A2')).toHaveCount(0);
  await expect(cell('A4')).toHaveText('5');
  await cell('A1').click();
  await page.keyboard.press('ArrowDown');
  await writes(page, 'A3');
  await cell('B1').click();
  await command('Sakrij stupce');
  await expect(letter('B')).toHaveCount(0);

  await page.reload();
  await expect(cell('A4')).toHaveText('5');
  await expect(number('2')).toHaveCount(0);
  await expect(letter('B')).toHaveCount(0);

  await dragCells(page, table, 'A1', 'A3');
  await page.keyboard.press('Escape');
  await command('Prikaži skrivene retke');
  await expect(number('2')).toBeVisible();
  await expect(cell('A4')).toHaveText('7');
  await command('Prikaži skrivene stupce');
  await expect(letter('B')).toBeVisible();
});

test('a filter shows the rows of the values chosen or of a condition met, numbered by their places, until it is taken off', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Filtar'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '2 × 4');
  const table = page.locator('.ponistra-table');
  const cell = (address: string) => cellAt(table, address);
  const number = (name: string) =>
    table.getByRole('grid').getByRole('rowheader', { name, exact: true });
  const filters = table.getByRole('group', { name: 'Filtar' });
  const dialog = page.getByRole('dialog', { name: 'Filtar stupca A' });

  for (const [text, next] of [
    ['kava', 'A2'],
    ['sok', 'A3'],
    ['kava', 'A4'],
    ['čaj', null],
  ] as const) {
    await page.keyboard.type(text);
    const row = next ? Number(next.slice(1)) - 1 : 4;
    await tab(page, `B${row}`);
    if (next) await tab(page, next);
  }
  await expect(cell('A4')).toHaveText('čaj');

  await cell('A1').click();
  await tableCommand(page, 'Filtriraj po ovoj vrijednosti');
  await expect(number('2')).toHaveCount(0);
  await expect(number('4')).toHaveCount(0);
  await expect(number('3')).toBeVisible();
  await expect(cell('A3')).toHaveText('kava');
  await expect(filters).toHaveText(/A: kava/);

  await page.reload();
  await expect(number('3')).toBeVisible();
  await expect(number('2')).toHaveCount(0);

  await filters.getByRole('button', { name: 'A: kava' }).click();
  await dialog.getByRole('button', { name: 'Uvjet', exact: true }).click();
  await dialog.getByLabel('Vrsta uvjeta').selectOption({ label: 'sadrži' });
  await dialog.getByLabel('Vrijednost').fill('a');
  await dialog.getByRole('button', { name: 'Primijeni' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(number('4')).toBeVisible();
  await expect(number('2')).toHaveCount(0);
  await expect(filters).toHaveText(/A: sadrži a/);

  await filters.getByRole('button', { name: 'A: sadrži a' }).click();
  await dialog.getByRole('button', { name: 'Vrijednosti', exact: true }).click();
  await expect(dialog.getByRole('listitem')).toHaveText([/čaj\s*1/, /kava\s*2/, /sok\s*1/]);
  await dialog.getByRole('checkbox', { name: /sok/ }).uncheck();
  await dialog.getByRole('checkbox', { name: /kava/ }).uncheck();
  await dialog.getByRole('button', { name: 'Primijeni' }).click();
  await expect(number('4')).toBeVisible();
  await expect(number('1')).toHaveCount(0);
  await expect(number('3')).toHaveCount(0);

  await cell('A4').click();
  await tableCommand(page, 'Ukloni filtar');
  await expect(number('2')).toBeVisible();
  await expect(filters).toBeHidden();
});
