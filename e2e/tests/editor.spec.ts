import { expect, test } from './fixtures';
import { settled } from './helpers/editor';
import { newDocument } from './helpers/nodes';
import { cellAt, insertTable, writes, writing } from './helpers/tables';

test('the explorer and search open', async ({ page }) => {
  for (const path of ['/', '/search?q=ponuda']) {
    await page.goto(path);
    await expect(page.locator('#root > *')).not.toHaveCount(0);
    await expect(page.getByRole('alert')).toHaveCount(0);
  }
});

test('two windows edit one document', async ({ page, context }) => {
  const url = await newDocument(page, 'Probni uređivač');
  await page.goto(url);
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('# Probna ponuda');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Ukupno je ');
  await page.keyboard.press('Control+b');
  await page.keyboard.type('120 EUR');
  await page.keyboard.press('Control+b');
  await page.keyboard.type(' bez PDV-a.');
  await insertTable(page, '3 × 3');
  const table = page.locator('.ponistra-table');
  await cellAt(table, 'B2').click();
  await writes(page, 'B2');
  await page.keyboard.type('42');
  await page.keyboard.press('Tab');
  await page.getByRole('button', { name: 'Tablica' }).click();
  await page.getByRole('menuitem', { name: 'Umetni redak ispod' }).click();

  const other = await context.newPage();
  await other.goto(url);
  const theirs = other.locator('.ponistra-table');
  const rows = theirs.getByRole('grid');
  await expect(other.locator('.ProseMirror h1')).toHaveText('Probna ponuda');
  await expect(other.locator('.ProseMirror p strong')).toHaveText('120 EUR');
  await expect(cellAt(theirs, 'B2')).toHaveText('42');
  await expect(rows).toHaveAttribute('aria-rowcount', '5');

  await page.bringToFront();
  await editor.locator('h1').click();
  await expect(other.locator('.ProseMirror-yjs-cursor')).toHaveCount(1);

  await cellAt(table, 'C2').click();
  await writes(page, 'C2');
  await page.keyboard.type('7');
  await page.keyboard.press('Tab');
  await expect(cellAt(theirs, 'C2')).toHaveText('7');
  await page.keyboard.press('Control+z');
  await expect(cellAt(table, 'C2')).toHaveText('');
  await expect(cellAt(theirs, 'C2')).toHaveText('');

  await page.getByRole('button', { name: 'Poništi' }).click();
  await expect(rows).toHaveAttribute('aria-rowcount', '4');
  await page.getByRole('button', { name: 'Ponovi' }).click();
  await expect(rows).toHaveAttribute('aria-rowcount', '5');
});

test('every view of the commands reaches the text and the tables', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto(await newDocument(page, 'Probne naredbe'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Ponuda');
  await page.keyboard.press('Enter');
  await page.keyboard.type('/tab');
  await expect(page.getByRole('option', { name: 'Tablica' })).toBeVisible();
  await page.keyboard.press('Enter');
  const tables = page.locator('.ponistra-table');
  await expect(tables).toHaveCount(1);
  await expect(editor).not.toContainText('/tab');

  const first = tables.first();
  const cell = writing(first, 'A1');
  await expect(cell).toBeFocused();
  await page.keyboard.type('Najam');
  await cell.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Umetni redak ispod' }).click();
  await expect(cell).toBeFocused();
  await expect(first.getByRole('grid')).toHaveAttribute('aria-rowcount', '5');
  await expect(page.getByRole('button', { name: 'Tablica' })).toBeEnabled();

  await editor.getByText('Ponuda').click();
  await expect(page.getByRole('button', { name: 'Tablica' })).toHaveCount(0);
  await page.keyboard.press('Alt+/');
  await page.keyboard.type('naslov 2');
  await page
    .getByRole('listbox', { name: 'Pretraži' })
    .getByRole('option', { name: 'Naslov 2' })
    .click();
  await expect(editor.locator('h2')).toHaveText('Ponuda');

  await page.keyboard.press('Control+/');
  const shortcuts = page.getByRole('dialog', { name: 'Prečaci tipkovnice' });
  await expect(shortcuts).toContainText('Ctrl+B');
  await page.keyboard.press('Escape');
  await expect(shortcuts).toHaveCount(0);
  await expect(editor).toBeFocused();

  await page.keyboard.press('Control+a');
  await editor.locator('h2').click({ button: 'right' });
  await page.getByRole('menuitem', { name: /^Kopiraj(?! poveznicu)/ }).click();
  await expect(editor).toBeFocused();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toContain('Najam');
  await settled(page);
  await expect
    .poll(async () => {
      await page.keyboard.press('Control+Home');
      return page.getByRole('combobox', { name: 'Stil odlomka' }).inputValue();
    })
    .toBe('style.heading2');
  await page.keyboard.press('Control+v');
  await expect(tables).toHaveCount(2);
  await expect(cellAt(tables.nth(0), 'A1')).toHaveText('Najam');
  await expect(cellAt(tables.nth(1), 'A1')).toHaveText('Najam');
});

test('the toolbar formats the text and its paragraphs', async ({ page }) => {
  await page.goto(await newDocument(page, 'Probno oblikovanje'));
  const editor = page.locator('.ProseMirror');
  const hint = editor.locator('.ponistra-empty');
  await expect(hint).toHaveCount(1);
  await editor.click({ position: { x: 300, y: 300 } });
  await expect(editor).toBeFocused();
  await page.keyboard.type('Ponuda za najam');
  await expect(hint).toHaveCount(0);
  await page.getByRole('combobox', { name: 'Stil odlomka' }).selectOption({ label: 'Naslov' });
  const title = editor.locator('[data-block=title]');
  await expect(title).toHaveText('Ponuda za najam');
  await expect(editor).toBeFocused();

  await page.keyboard.press('Control+Shift+e');
  await expect(title).toHaveCSS('text-align', 'center');
  await page.keyboard.press('Shift+Home');
  await page.getByRole('button', { name: 'Boja teksta' }).click();
  await page.getByRole('menuitemcheckbox', { name: 'Crvena' }).click();
  await expect(title.locator('span[data-color=red]')).toHaveText('Ponuda za najam');
  await expect(editor).toBeFocused();
  await page.keyboard.press('Control+u');
  await expect(title.locator('u')).toHaveText('Ponuda za najam');
  await page.getByRole('button', { name: 'Ukloni oblikovanje' }).click();
  await expect(title.locator('span, u')).toHaveCount(0);
  await expect(title).toHaveCSS('text-align', 'start');

  await page.setViewportSize({ width: 480, height: 900 });
  await page.getByRole('button', { name: 'Više' }).click();
  await page.getByRole('menuitemcheckbox', { name: 'Poravnaj desno' }).click();
  await expect(title).toHaveCSS('text-align', 'right');
  await expect(editor).toBeFocused();
});

test('in the Suggesting mode what is typed and taken out is proposed, and accepted as any proposal', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Probno predlaganje'));
  const editor = page.locator('.ProseMirror');
  await editor.click({ position: { x: 300, y: 300 } });
  await page.keyboard.type('Rok je 30 dana.');
  const suggest = page.getByRole('button', { name: 'Predlaganje', exact: true });
  await suggest.click();
  await expect(suggest).toHaveAttribute('aria-pressed', 'true');
  await expect(editor).toBeFocused();
  for (let step = 0; step < 6; step++) await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('Backspace');
  await page.keyboard.press('Backspace');
  await page.keyboard.type('15');
  await expect(editor.locator('del[data-proposal]')).toHaveText('30');
  await expect(editor.locator('ins[data-proposal]')).toHaveText('15');
  const popover = page.getByRole('toolbar', { name: 'Prijedlozi' });
  await expect(popover).toContainText(/Zamijenjeno · \w+@e2e\.invalid/);

  await page.keyboard.press('End');
  await expect(popover).toHaveCount(0);
  await page.keyboard.press('Enter');
  await page.keyboard.type('Kraj.');
  await expect(editor.locator('.ponistra-end[data-proposed="insertion"]')).toHaveCount(1);
  await expect(editor.locator('ins[data-proposal]')).toHaveText(['15', 'Kraj.']);

  await suggest.click();
  await expect(suggest).toHaveAttribute('aria-pressed', 'false');
  await page.keyboard.type(' Potpisano.');
  await expect(editor.locator('p').nth(1)).toHaveText('Kraj. Potpisano.');
  await expect(editor.locator('ins[data-proposal]')).toHaveText(['15', 'Kraj.']);

  await editor.locator('ins', { hasText: '15' }).click();
  await popover.getByRole('button', { name: 'Prihvati prijedlog' }).click();
  await expect(editor.locator('p')).toHaveText(['Rok je 15 dana.', 'Kraj. Potpisano.']);
  await expect(editor.locator('del[data-proposal]')).toHaveCount(0);
});

test('a table takes the picked size and leaves room to write below it', async ({ page }) => {
  await page.goto(await newDocument(page, 'Probna tablica'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Ponuda');
  await page.getByRole('button', { name: 'Umetni' }).click();
  await page.getByRole('menuitem', { name: 'Tablica' }).click();
  await page.getByRole('menuitem', { name: '5 × 4', exact: true }).hover();
  await expect(page.getByRole('menu').getByText('5 × 4', { exact: true })).toBeVisible();
  await page.getByRole('menuitem', { name: '5 × 4', exact: true }).click();
  const table = editor.locator('.ponistra-table');
  const grid = table.getByRole('grid');
  await expect(grid).toHaveAttribute('aria-rowcount', '5');
  await expect(grid).toHaveAttribute('aria-colcount', '6');
  await expect(writing(table, 'A1')).toBeFocused();
  const blocks = editor.locator(':scope > *');
  await expect(blocks).toHaveCount(3);

  await blocks.last().click();
  await page.keyboard.press('Backspace');
  await expect(blocks).toHaveCount(2);
  const below = (await grid.boundingBox())!;
  await page.mouse.click(below.x + 40, below.y + below.height + 40);
  await page.keyboard.type('Napomena');
  await expect(blocks).toHaveCount(3);
  await expect(blocks.last()).toHaveText('Napomena');
});

test("switching tabs keeps the document's own room open", async ({ page }) => {
  await page.goto(await newDocument(page, 'Dvije kartice'));
  const editor = page.locator('.ProseMirror');
  await editor.click();
  await page.keyboard.type('Prva kartica');
  await page.getByRole('button', { name: 'Nova kartica' }).click();
  await expect(editor).not.toContainText('Prva kartica');
  await editor.click();
  await page.keyboard.type('Druga kartica');
  await expect(editor).toContainText('Druga kartica');

  const sockets: string[] = [];
  page.on('websocket', (socket) => sockets.push(socket.url()));
  await page.getByRole('link', { name: 'Kartica bez naziva' }).first().click();
  await expect(editor).toContainText('Prva kartica');
  expect(sockets).toHaveLength(1);
});
