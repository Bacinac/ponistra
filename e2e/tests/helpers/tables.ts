import { expect, type Locator, type Page } from '@playwright/test';

/** A table's cell by its address: the one the canvas draws, or the one written in. */
export function cellAt(table: Locator, address: string): Locator {
  return table.locator(`[role="gridcell"][data-address="${address}"]`);
}

/** The editor of a table's cell, which has the focus while the cell is written. */
export function writing(table: Locator, address: string): Locator {
  return table.getByRole('textbox', { name: `Ćelija ${address}`, exact: true });
}

/** Inserts a table of the size the menu names and waits until its first cell is written in. */
export async function insertTable(page: Page, size: string): Promise<void> {
  await page.getByRole('button', { name: 'Umetni' }).click();
  await page.getByRole('menuitem', { name: 'Tablica' }).click();
  await page.getByRole('menuitem', { name: size, exact: true }).click();
  await writes(page, 'A1');
}

/** Waits until the cell at the address is the one written in. */
export async function writes(page: Page, address: string): Promise<void> {
  await expect(page.locator(':focus')).toHaveAccessibleName(`Ćelija ${address}`);
}

/** Moves to the next cell with Tab and waits until it is the one written in. */
export async function tab(page: Page, address: string): Promise<void> {
  await page.keyboard.press('Tab');
  await writes(page, address);
}

/** Runs a command from the Tablica menu. */
export async function tableCommand(page: Page, name: string): Promise<void> {
  await page.getByRole('button', { name: 'Tablica' }).click();
  await page.getByRole('menuitem', { name }).click();
}

/** What each cell of a table shows, row by row. The cells written in lie apart from the ones the
 * canvas draws, so they are read in the order the grid numbers them. */
export function cellTexts(table: Locator): Promise<string[]> {
  return table.getByRole('grid').evaluate((grid) => {
    const rowOf = (cell: HTMLElement) =>
      cell.closest('[role="row"]') ?? grid.querySelector(`[role="row"][aria-owns~="${cell.id}"]`);
    return [...grid.querySelectorAll<HTMLElement>('[role="gridcell"]')]
      .map((cell) => ({
        row: Number(rowOf(cell)?.getAttribute('aria-rowindex')),
        col: Number(cell.getAttribute('aria-colindex')),
        text: cell.innerText.replace(/\s+/g, ' ').trim(),
      }))
      .sort((a, b) => a.row - b.row || a.col - b.col)
      .map(({ text }) => text);
  });
}

/** The addresses of a table's selected cells. */
export function selectedCells(table: Locator): Promise<string[]> {
  return table
    .locator('[role="gridcell"][aria-selected="true"]')
    .evaluateAll((cells) => cells.map((cell) => cell.getAttribute('data-address')!).sort());
}

type Box = { x: number; y: number; width: number; height: number };

/** Where an element stands once it does: a cell's own element left is taken out, and the table
 * draws the cell again by another a frame later. */
export async function standing(element: Locator): Promise<Box> {
  const found: { box: Box | null } = { box: null };
  await expect.poll(async () => (found.box = await element.boundingBox())).not.toBeNull();
  return found.box!;
}

/** The cells from one to another, selected as a pointer drags across them. */
export async function dragCells(
  page: Page,
  table: Locator,
  from: string,
  to: string,
): Promise<void> {
  const start = await standing(cellAt(table, from));
  const end = await standing(cellAt(table, to));
  await page.mouse.move(start.x + 8, start.y + 8);
  await page.mouse.down();
  await page.mouse.move(end.x + 8, end.y + 8, { steps: 5 });
  await page.mouse.up();
}
