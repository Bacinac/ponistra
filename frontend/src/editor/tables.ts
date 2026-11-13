import {
  DOMParser as ModelParser,
  Fragment,
  type Attrs,
  type Node,
  type Schema,
} from 'prosemirror-model';
import spec from '../../../schema/schema.json';
import { HIGHLIGHTS, named } from './colors';
import {
  areaOf,
  borderOf,
  designOf,
  designsIn,
  apartOf,
  backgroundOf,
  dressOf,
  NEW,
  ours,
  shadowOf,
  tintOf,
  type Design,
} from './design';
import { endMarksAttr, endMarksOf, marksFrom } from './ends';
import type { Value } from './formulas';
import { keyOf, type Grid, type GridSource, type Look } from './grids';
import { PROPOSED } from './proposals';

export { keyOf };

export type Axis = 'rows' | 'cols';

/** The ids of a table's rows and columns, in order. */
interface Shape {
  rows: string[];
  cols: string[];
}

/** Of a column's width, in characters. */
const NARROWEST = 2;
/** A character of a sheet's width in points, as its program counts nine pixels for one. */
const CHARACTER_POINTS = 6.75;

/** Rows and columns from the top left, both ends included. */
export interface Rect {
  top: number;
  left: number;
  bottom: number;
  right: number;
}

/** The ids of a table's columns hidden from view; its hidden rows are never shown it. */
export interface Hidden {
  readonly cols: ReadonlySet<string>;
}

export const NONE_HIDDEN: Hidden = { cols: new Set() };

/** A table's rows and columns, their sizes, the columns hidden, its merged cells and its name:
 * its grid's, or a copied table's own. Of a grid's rows only those the browser knows have an id;
 * the rows hidden or that the user's filter leaves out are not among them, so each row has a
 * number, its own place among all the table's rows, which its header and address show. */
export interface Lines {
  readonly name: string;
  readonly rowCount: number;
  readonly cols: readonly string[];
  readonly widths: ReadonlyMap<string, number>;
  readonly heights: ReadonlyMap<string, number>;
  readonly hidden: Hidden;
  readonly merges: ReadonlyMap<string, string>;
  /** Whether each row's number is its place: no row hidden, none left out by a filter. */
  readonly plain: boolean;
  rowId(index: number): string | undefined;
  rowNumber(index: number): number | undefined;
  rowIndex(id: string): number;
  colIndex(id: string): number;
}

/** Lines whose every row the browser has: a copied table's own. */
export interface KnownLines extends Lines {
  readonly rows: readonly string[];
}

/** The id of the row standing there, which the browser knows. */
export function rowAt(lines: Lines, index: number): string {
  const id = lines.rowId(index);
  if (id === undefined) throw new Error(`table: row ${index} is not known`);
  return id;
}

/** The ids of the rows from the first to the last, which the browser knows. */
export function rowsOf(lines: Lines, first: number, last: number): string[] {
  const found: string[] = [];
  for (let index = first; index <= last; index++) found.push(rowAt(lines, index));
  return found;
}

/** The ids of all the table's rows, null where the browser does not know them all. */
export function allRows(lines: Lines): string[] | null {
  const found: string[] = [];
  for (let index = 0; index < lines.rowCount; index++) {
    const id = lines.rowId(index);
    if (id === undefined) return null;
    found.push(id);
  }
  return found;
}

/** The key a slot stands by while the browser does not know its row, which no cell has. */
function unknownRow(index: number): string {
  return `?${index}`;
}

export type LinesOf = (table: Node) => Lines | null;

/** The meta of a transaction after which a grid's rows or columns stand otherwise. */
export const OUTLINED = 'outlinedGrid';

/** A table that is no grid of the document's, one copied or read from a page, carries its lines
 * in its `grid` attribute; all its cells are nodes. */
export interface Part {
  rows: string[];
  cols: string[];
  widths?: Record<string, number> | null;
  heights?: Record<string, number> | null;
  merges?: Record<string, string> | null;
  name?: string;
  /** The table of the document these lines were copied from, whose ids they keep. */
  from?: string;
}

class PartLines implements KnownLines {
  readonly name: string;
  readonly rowCount: number;
  readonly cols: readonly string[];
  readonly widths: ReadonlyMap<string, number>;
  readonly heights: ReadonlyMap<string, number>;
  readonly hidden = NONE_HIDDEN;
  readonly plain = true;
  readonly merges: ReadonlyMap<string, string>;
  readonly rows: readonly string[];
  private rowAt: Map<string, number>;
  private colAt: Map<string, number>;

  constructor(part: Part) {
    this.name = part.name ?? '';
    this.rows = part.rows;
    this.rowCount = part.rows.length;
    this.cols = part.cols;
    this.widths = new Map(Object.entries(part.widths ?? {}));
    this.heights = new Map(Object.entries(part.heights ?? {}));
    this.merges = new Map(Object.entries(part.merges ?? {}));
    this.rowAt = new Map(part.rows.map((id, index) => [id, index]));
    this.colAt = new Map(part.cols.map((id, index) => [id, index]));
  }

  rowId(index: number): string | undefined {
    return this.rows[index];
  }

  rowNumber(index: number): number {
    return index;
  }

  rowIndex(id: string): number {
    return this.rowAt.get(id) ?? -1;
  }

  colIndex(id: string): number {
    return this.colAt.get(id) ?? -1;
  }
}

const parts = new WeakMap<Node, KnownLines>();

/** The lines a copied table carries. */
export function partLines(table: Node): KnownLines | null {
  const part: Part | null = table.attrs.grid;
  if (!part) return null;
  let lines = parts.get(table);
  if (!lines) parts.set(table, (lines = new PartLines(part)));
  return lines;
}

/** What a copied table's cells compute: each formula in the canonical form with its addresses as
 * they were where it was copied, the number formats, what was typed where a cell shows a value
 * in its place, and where the copied cells' top left was. */
export interface Copied {
  origin: { row: number; col: number };
  formulas: Record<string, string>;
  formats: Record<string, string>;
  typed?: Record<string, string>;
}

export const NAME_LENGTH = spec.$defs.tableName.maxLength;
const ID = new RegExp(spec.$defs.id.pattern);
const NAME = new RegExp(spec.$defs.tableName.pattern);

/** Why a table cannot have the name, as a workbook's sheet could not: it is not one, or another
 * table of the document has it. */
export function nameProblem(
  source: GridSource,
  table: string,
  name: string,
): 'invalid' | 'taken' | null {
  if (!name) return null;
  if (name.length > NAME_LENGTH || !NAME.test(name)) return 'invalid';
  const found = source.named(name);
  return found && found.table !== table ? 'taken' : null;
}

/** The lines of a table: its own where it carries them, else its grid's. */
export function linesOf(source: GridSource | null): LinesOf {
  return (table) => partLines(table) ?? source?.grid(table.attrs.id) ?? null;
}

/** Whether the value the server computed stands in a cell's place: a formula's, or a number its
 * format writes; typed text stays as it was written. */
export function standsIn(value: Value | undefined, formula: boolean, format: boolean): boolean {
  return value !== undefined && (formula || (format && value.kind !== 'text'));
}

const LOOK_ATTRS = ['align', 'indent', 'firstLine', 'right', 'style'];
const UNLOOKED: readonly string[] = [...PROPOSED, 'formatting'];

/** A light cell as a node: its text in its look, the marks kept at its end where it is empty, and
 * its fill. */
export function lightCell(
  schema: Schema,
  row: string,
  col: string,
  text: string,
  look?: Look,
): Node {
  const { cell, paragraph } = schema.nodes;
  const marks = marksFrom(schema, look?.marks ?? null);
  const attrs = look?.attrs ?? null;
  return cell.create(
    { row, col, fill: look?.fill ?? null },
    text
      ? paragraph.create(attrs, schema.text(text, marks))
      : paragraph.create({ ...attrs, endMarks: endMarksAttr(marks) }),
  );
}

/** The text and the look of a cell's content where it is one paragraph of plain text in one look,
 * which the server keeps as a light cell; null where it keeps a node. */
export function lookOf(cell: Node): { text: string; look: Look } | null {
  const block = cell.firstChild;
  if (cell.childCount !== 1 || block?.type.name !== 'paragraph') return null;
  const attrs: Record<string, unknown> = {};
  for (const [name, value] of Object.entries(block.attrs)) {
    if (name === 'id' || value === block.type.spec.attrs?.[name]?.default) continue;
    if (name !== 'endMarks' && !LOOK_ATTRS.includes(name)) return null;
    if (name !== 'endMarks' && value !== null) attrs[name] = value;
  }
  const runs: Node[] = [];
  let plain = true;
  block.forEach((child) => {
    plain &&= child.isText;
    runs.push(child);
  });
  if (!plain) return null;
  const marks = runs.length ? runs[0].marks : endMarksOf(block);
  if (runs.some((run) => !run.sameMarkup(runs[0]))) return null;
  if (marks.some((mark) => UNLOOKED.includes(mark.type.name))) return null;
  const look: Look = {};
  if (marks.length)
    look.marks = Object.fromEntries(marks.map((mark) => [mark.type.name, mark.attrs]));
  if (Object.keys(attrs).length) look.attrs = attrs;
  if (cell.attrs.fill) look.fill = cell.attrs.fill as string;
  return { text: block.textContent, look };
}

/** The cell holding `text` alone, in the look of its first paragraph and the marks its text starts
 * with, or its end's where it has no text, as a value computed for it shows. Without text the marks
 * stay at the paragraph's end. */
export function retyped(cell: Node, text: string): Node {
  const { schema } = cell.type;
  const { paragraph } = schema.nodes;
  let first = null as Node | null;
  cell.descendants((node) => {
    if (!first && node.isText) first = node;
    return !first;
  });
  const block = cell.firstChild;
  const attrs = block?.type === paragraph ? block.attrs : null;
  const marks = first?.marks ?? (block ? endMarksOf(block) : []);
  return cell.type.create(
    cell.attrs,
    text
      ? paragraph.create(attrs, schema.text(text, marks))
      : paragraph.create({ ...attrs, endMarks: endMarksAttr(marks) }),
  );
}

/** The cell as it reads: an apostrophe before its text only keeps it text rather than a number or
 * a date, as in Excel. */
export function unquoted(cell: Node): Node {
  const text = cell.textContent;
  return cell.childCount === 1 && cell.firstChild!.isTextblock && text.startsWith("'")
    ? retyped(cell, text.slice(1))
    : cell;
}

export function filled(cell: Node): boolean {
  return cell.childCount > 1 || cell.firstChild!.content.size > 0 || !cell.firstChild!.isTextblock;
}

/** A cell in the table: the slot it starts at, the slots it covers, and its node where it has one
 * in the text, else what its grid holds for it. */
export interface Placed {
  key: string;
  row: number;
  col: number;
  rows: number;
  cols: number;
  node: Node | null;
  /** Of the node, within the table's content. */
  offset: number | null;
}

interface Merge extends Rect {
  key: string;
}

/** A table laid out from its grid's lines and merges and its cell nodes, without a slot for each
 * cell, as a sheet has millions: a slot's cell is found when asked for. */
export class Layout {
  readonly rows: number;
  readonly cols: number;
  /** The merged cells, and the slot each covers, by `row * cols + col`. */
  private merges: Merge[] = [];
  private covered = new Map<number, Merge>();
  /** The cell nodes by key. */
  private nodes = new Map<string, { node: Node; offset: number }>();

  constructor(
    readonly grid: Lines,
    readonly table: Node,
  ) {
    this.rows = grid.rowCount;
    this.cols = grid.cols.length;
    // A node's row the browser does not know yet is placed by its key once it does.
    table.forEach((node, offset) => {
      if (grid.colIndex(node.attrs.col) >= 0) {
        this.nodes.set(keyOf(node.attrs.row, node.attrs.col), { node, offset });
      }
    });
    const found: Merge[] = [];
    for (const [key, to] of grid.merges) {
      const [row, col] = key.split(':');
      const [toRow, toCol] = to.split(':');
      const rect = {
        key,
        top: grid.rowIndex(row),
        left: grid.colIndex(col),
        bottom: grid.rowIndex(toRow),
        right: grid.colIndex(toCol),
      };
      if (Object.values(rect).some((index) => index === -1)) continue;
      if (rect.bottom < rect.top || rect.right < rect.left) continue;
      found.push(rect);
    }
    found.sort((a, b) => a.top - b.top || a.left - b.left);
    for (const merge of found) {
      if (!this.free(merge)) continue;
      this.merges.push(merge);
      for (let row = merge.top; row <= merge.bottom; row++) {
        for (let col = merge.left; col <= merge.right; col++) {
          this.covered.set(row * this.cols + col, merge);
        }
      }
    }
  }

  private free(rect: Rect): boolean {
    for (let row = rect.top; row <= rect.bottom; row++) {
      for (let col = rect.left; col <= rect.right; col++) {
        if (this.covered.has(row * this.cols + col)) return false;
      }
    }
    return true;
  }

  /** The cell covering the slot. */
  at(row: number, col: number): Placed | null {
    if (row < 0 || col < 0 || row >= this.rows || col >= this.cols) return null;
    const merge = this.covered.get(row * this.cols + col);
    const top = merge?.top ?? row;
    const left = merge?.left ?? col;
    const key = merge?.key ?? keyOf(this.grid.rowId(top) ?? unknownRow(top), this.grid.cols[left]);
    const found = this.nodes.get(key);
    return {
      key,
      row: top,
      col: left,
      rows: merge ? merge.bottom - merge.top + 1 : 1,
      cols: merge ? merge.right - merge.left + 1 : 1,
      node: found?.node ?? null,
      offset: found?.offset ?? null,
    };
  }

  /** The cell of a key, where its row and column still are. */
  placed(key: string): Placed | null {
    const [row, col] = key.split(':');
    const cell = this.at(this.grid.rowIndex(row), this.grid.colIndex(col));
    return cell && cell.key === key ? cell : null;
  }

  /** Whether the slot is the first of its cell. */
  starts(row: number, col: number): boolean {
    const merge = this.covered.get(row * this.cols + col);
    return !merge || (merge.top === row && merge.left === col);
  }

  /** The merged cells that reach into the rows. */
  mergesIn(top: number, bottom: number): readonly Merge[] {
    return this.merges.filter((merge) => merge.top <= bottom && merge.bottom >= top);
  }

  /** The cell nodes, each with its slot. */
  *nodeCells(): Generator<Placed> {
    for (const key of this.nodes.keys()) {
      const placed = this.placed(key);
      if (placed) yield placed;
    }
  }

  /** The next cell that way: in reading order sideways, the cell below or above in the column. */
  /** Whether the slot's column is hidden. */
  hiddenAt(_row: number, col: number): boolean {
    return this.grid.hidden.cols.has(this.grid.cols[col]);
  }

  /** The next cell that way, past the hidden rows and columns. */
  neighbour(cell: Placed, dir: 'up' | 'down' | 'left' | 'right'): Placed | null {
    if (dir === 'up' || dir === 'down') {
      const step = dir === 'up' ? -1 : 1;
      let row = dir === 'up' ? cell.row - 1 : cell.row + cell.rows;
      while (row >= 0 && row < this.rows && this.hiddenAt(row, cell.col)) row += step;
      return this.at(row, cell.col);
    }
    let row = cell.row;
    let col = dir === 'left' ? cell.col - 1 : cell.col + cell.cols;
    for (;;) {
      if (col < 0) {
        if (--row < 0) return null;
        col = this.cols - 1;
      } else if (col >= this.cols) {
        if (++row >= this.rows) return null;
        col = 0;
      }
      if (this.starts(row, col) && !this.hiddenAt(row, col)) return this.at(row, col);
      col += dir === 'left' ? -1 : 1;
    }
  }

  /** The first and the last cell in reading order that is shown. */
  first(): Placed | null {
    const corner = this.at(0, 0);
    return corner && this.hiddenAt(0, 0) ? this.neighbour(corner, 'right') : corner;
  }

  last(): Placed | null {
    const corner = this.at(this.rows - 1, this.cols - 1);
    if (!corner) return null;
    const found = this.at(corner.row, corner.col)!;
    return this.hiddenAt(found.row, found.col) ? this.neighbour(found, 'left') : found;
  }

  /** The smallest rectangle holding both and every cell that reaches into it. */
  between(a: Rect, b: Rect): Rect {
    const rect = {
      top: Math.min(a.top, b.top),
      left: Math.min(a.left, b.left),
      bottom: Math.max(a.bottom, b.bottom),
      right: Math.max(a.right, b.right),
    };
    for (let grown = true; grown;) {
      grown = false;
      for (const merge of this.merges) {
        if (!meets(merge, rect) || within(merge, rect)) continue;
        rect.top = Math.min(rect.top, merge.top);
        rect.left = Math.min(rect.left, merge.left);
        rect.bottom = Math.max(rect.bottom, merge.bottom);
        rect.right = Math.max(rect.right, merge.right);
        grown = true;
      }
    }
    return rect;
  }

  /** The cells starting in the rectangle, row by row. */
  *cellsIn(rect: Rect): Generator<Placed> {
    for (let row = Math.max(rect.top, 0); row <= Math.min(rect.bottom, this.rows - 1); row++) {
      for (let col = Math.max(rect.left, 0); col <= Math.min(rect.right, this.cols - 1); col++) {
        if (this.starts(row, col)) yield this.at(row, col)!;
      }
    }
  }

  /** The cells reaching into the rectangle, each once, the merged ones started before it among
   * them. */
  *cellsOver(rect: Rect): Generator<Placed> {
    const seen = new Set<string>();
    for (let row = Math.max(rect.top, 0); row <= Math.min(rect.bottom, this.rows - 1); row++) {
      for (let col = Math.max(rect.left, 0); col <= Math.min(rect.right, this.cols - 1); col++) {
        const placed = this.at(row, col)!;
        if (seen.has(placed.key)) continue;
        seen.add(placed.key);
        yield placed;
      }
    }
  }

  whole(): Rect {
    return { top: 0, left: 0, bottom: this.rows - 1, right: this.cols - 1 };
  }
}

export function meets(a: Rect, b: Rect): boolean {
  return a.top <= b.bottom && b.top <= a.bottom && a.left <= b.right && b.left <= a.right;
}

function within(inner: Rect, outer: Rect): boolean {
  return (
    inner.top >= outer.top &&
    inner.left >= outer.left &&
    inner.bottom <= outer.bottom &&
    inner.right <= outer.right
  );
}

export function rectOfCell(cell: Placed): Rect {
  return {
    top: cell.row,
    left: cell.col,
    bottom: cell.row + cell.rows - 1,
    right: cell.col + cell.cols - 1,
  };
}

/** A tab's text blocks as they are read: each table's cell nodes row by row, each cell's blocks in
 * turn, whatever order the cells were written in. */
export function readingOrder(doc: Node, lines: LinesOf): { node: Node; pos: number }[] {
  const found: { node: Node; pos: number }[] = [];
  doc.forEach((node, offset) => {
    if (node.isTextblock) found.push({ node, pos: offset });
    if (node.type.name !== 'table') return;
    const placed = lines(node);
    if (!placed) return;
    const cells: { cell: Node; at: number; row: number; col: number }[] = [];
    node.forEach((cell, at) => {
      const row = placed.rowIndex(cell.attrs.row);
      const col = placed.colIndex(cell.attrs.col);
      if (row >= 0 && col >= 0) cells.push({ cell, at, row, col });
    });
    cells.sort((a, b) => a.row - b.row || a.col - b.col);
    for (const { cell, at } of cells) {
      const start = offset + 1 + at + 1;
      cell.forEach((child, inner) => {
        if (child.isTextblock) found.push({ node: child, pos: start + inner });
      });
    }
  });
  return found;
}

/** The columns' widths as the grid gives them; a column it has no width for takes the
 * average of the others. */
function givenWidths(
  cols: readonly string[],
  widths: ReadonlyMap<string, number>,
  hidden: ReadonlySet<string> = NONE_HIDDEN.cols,
): number[] {
  const given = cols.map((col) => {
    const width = widths.get(col);
    return width !== undefined && width > 0 ? width : null;
  });
  const some = given.filter((width): width is number => width !== null);
  const fallback = some.length ? sum(some) / some.length : 1;
  return given.map((width, at) => (hidden.has(cols[at]) ? 0 : (width ?? fallback)));
}

function sum(numbers: readonly number[]): number {
  return numbers.reduce((total, number) => total + number, 0);
}

/** Each width's share of them all in per cent. */
export function shares(widths: readonly number[]): number[] {
  const total = sum(widths);
  return widths.map((width) => (total ? (width / total) * 100 : 0));
}

/** What a sheet's column is drawn wider than its width in characters, so that it holds the text
 * Excel's does: its cells' sides, a character each, less the five pixels at seven to a character
 * that Excel counts in the width. */
export const SIDES = 2 - 5 / 7;

/** A sheet's columns as wide as they are drawn, in characters. */
export function drawnWidths(widths: readonly number[]): number[] {
  return widths.map((width) => (width ? width + SIDES : 0));
}

/** Whether the columns have widths of their own in characters and the table is as wide as they
 * are together, as a sheet in Excel; otherwise they share the page's width. */
export function isSized(table: Node): boolean {
  return table.attrs.sized === true;
}

/** Each column's share of the table's width in per cent, none for a hidden one. */
export function widthsOf(
  sized: boolean,
  cols: readonly string[],
  widths: ReadonlyMap<string, number>,
  hidden?: ReadonlySet<string>,
): number[] {
  const given = givenWidths(cols, widths, hidden);
  return shares(sized ? drawnWidths(given) : given);
}

/** The table's width as drawn in characters, null where it takes the page's. */
export function tableWidth(
  sized: boolean,
  cols: readonly string[],
  widths: ReadonlyMap<string, number>,
  hidden?: ReadonlySet<string>,
): number | null {
  return sized ? sum(drawnWidths(givenWidths(cols, widths, hidden))) : null;
}

/** Each column's width in characters: its own, or what it would need to be drawn as wide as its
 * share of the `drawn` characters a table that takes the page's width is; a hidden one keeps its
 * own for when it is shown again. */
export function charactersOf(
  sized: boolean,
  cols: readonly string[],
  widths: ReadonlyMap<string, number>,
  drawn: number,
  hidden: ReadonlySet<string> = NONE_HIDDEN.cols,
): number[] {
  const own = givenWidths(cols, widths);
  if (sized) return own;
  return widthsOf(false, cols, widths, hidden).map((share, at) =>
    hidden.has(cols[at]) ? own[at] : Math.max((share * drawn) / 100 - SIDES, NARROWEST),
  );
}

/** The columns after one took `width` characters and the others kept theirs: the table grows or
 * shrinks by the difference, as in Excel. */
export function widened(widths: readonly number[], index: number, width: number): number[] {
  return widths.map((each, at) => (at === index ? Math.max(width, NARROWEST) : each));
}

export function rounded(width: number): number {
  return Math.round(width * 10) / 10;
}

interface Slot {
  cell: HTMLTableCellElement;
  row: number;
  col: number;
  rows: number;
  cols: number;
}

function slotsOf(table: HTMLTableElement): { slots: Slot[]; rows: number; cols: number } {
  const lines = [...table.rows];
  const taken: boolean[][] = lines.map(() => []);
  const slots: Slot[] = [];
  lines.forEach((tr, row) => {
    let col = 0;
    for (const cell of tr.cells) {
      while (taken[row][col]) col++;
      const rows = Math.max(1, Math.min(cell.rowSpan || 1, lines.length - row));
      const cols = Math.max(1, cell.colSpan || 1);
      for (let r = row; r < row + rows; r++)
        for (let c = col; c < col + cols; c++) taken[r][c] = true;
      slots.push({ cell, row, col, rows, cols });
      col += cols;
    }
  });
  return { slots, rows: lines.length, cols: Math.max(1, ...taken.map((slots) => slots.length)) };
}

/** Rows and columns of a table read from a page: those copied from here keep their ids, which
 * a chart pasted with them refers to; others get stand-in ids. */
function linesIn(table: HTMLTableElement, { rows, cols }: { rows: number; cols: number }): Shape {
  const kept = (name: 'rows' | 'cols', count: number) => {
    const ids = table.dataset[name]?.split(' ');
    return ids?.length === count && new Set(ids).size === count && ids.every((id) => ID.test(id))
      ? ids
      : null;
  };
  const height = Math.max(1, rows);
  return {
    rows: kept('rows', height) ?? Array.from({ length: height }, (_, index) => `r${index}`),
    cols: kept('cols', cols) ?? Array.from({ length: cols }, (_, index) => `c${index}`),
  };
}

const UNITS: Record<string, number> = { px: 0.75, pt: 1, cm: 72 / 2.54, mm: 72 / 25.4, in: 72 };

function lengthOf(value: string | null | undefined): { size: number; percent: boolean } | null {
  const match = /^\s*(\d+(?:\.\d+)?)\s*(px|pt|cm|mm|in|%)?\s*$/.exec(value ?? '');
  if (!match || Number(match[1]) <= 0) return null;
  const unit = match[2] ?? 'px';
  return unit === '%'
    ? { size: Number(match[1]), percent: true }
    : { size: Number(match[1]) * UNITS[unit], percent: false };
}

function widthAttr(
  element: HTMLElement,
  name: 'width' | 'height' = 'width',
): ReturnType<typeof lengthOf> {
  return lengthOf(element.style[name]) ?? lengthOf(element.getAttribute(name));
}

/** The columns' widths as the page gives them, in its <col>s or in the cells of a single column,
 * when it gives every one in the same kind of unit. */
function columnWidths(table: HTMLTableElement, slots: Slot[], cols: number): number[] | null {
  const widths: (ReturnType<typeof lengthOf> | undefined)[] = Array(cols).fill(undefined);
  let index = 0;
  for (const col of table.querySelectorAll(':scope > colgroup > col, :scope > col')) {
    const width = widthAttr(col as HTMLElement);
    for (let span = Math.max(1, Number(col.getAttribute('span')) || 1); span > 0; span--) {
      if (index < cols) widths[index++] = width;
    }
  }
  for (const slot of slots) {
    if (slot.cols === 1 && !widths[slot.col]) widths[slot.col] = widthAttr(slot.cell);
  }
  if (widths.some((width) => !width)) return null;
  const known = widths as { size: number; percent: boolean }[];
  if (known.some((width) => width.percent !== known[0].percent)) return null;
  return known.map((width) => width.size);
}

const DRAWN = /border[\w-]*\s*:[^;]*\b(?:solid|double|dotted|dashed)\b/i;

/** A pasted table's designs: ours as we copied them, else our grid where another program draws
 * its lines. */
function designsPasted(table: HTMLTableElement): Design[] | null {
  const own = table.dataset.designs;
  if (own !== undefined) {
    try {
      return designsIn(JSON.parse(own));
    } catch {
      return null;
    }
  }
  const cells = table.querySelectorAll('td, th');
  const lined =
    table.getAttribute('border') !== '0' ||
    [...cells].some((cell) => DRAWN.test(cell.getAttribute('style') ?? ''));
  return lined ? [ours(NEW)] : null;
}

/** The rows' heights the page gives, in points, by row. */
function rowHeights(
  table: HTMLTableElement,
  rows: readonly string[],
): Record<string, number> | null {
  const entries = [...table.rows].flatMap((tr, index) => {
    const height = widthAttr(tr, 'height');
    return height && !height.percent && index < rows.length ? [[rows[index], height.size]] : [];
  });
  return entries.length ? Object.fromEntries(entries) : null;
}

/** A table from a page: its lines in stand-in ids with their sizes, its name, its designs and
 * what its cells compute. A sized table copied from here keeps its columns' own widths. */
export function tableAttrsIn(element: HTMLElement): Attrs {
  const table = element as HTMLTableElement;
  const { slots, rows, cols } = slotsOf(table);
  const shape = linesIn(table, { rows, cols });
  const given = columnWidths(table, slots, cols);
  const sized = table.dataset.sized !== undefined && !!given;
  const widths = sized ? given.map((width) => width / CHARACTER_POINTS) : given;
  const entries = (name: 'formula' | 'format' | 'text') =>
    Object.fromEntries(
      slots.flatMap((slot) => {
        const entry = slot.cell.dataset[name];
        return entry !== undefined && (entry || name === 'text')
          ? [[keyOf(shape.rows[slot.row], shape.cols[slot.col]), entry]]
          : [];
      }),
    );
  const formulas = entries('formula');
  const formats = entries('format');
  const typed = entries('text');
  const [row, col] = (table.dataset.origin ?? '').split(':').map(Number);
  const part: Part = {
    ...shape,
    widths: widths && Object.fromEntries(shape.cols.map((id, at) => [id, rounded(widths[at])])),
    heights: rowHeights(table, shape.rows),
    merges: Object.fromEntries(
      slots
        .filter((slot) => slot.rows > 1 || slot.cols > 1)
        .map((slot) => [
          keyOf(shape.rows[slot.row], shape.cols[slot.col]),
          keyOf(shape.rows[slot.row + slot.rows - 1], shape.cols[slot.col + slot.cols - 1]),
        ]),
    ),
    ...(table.dataset.name && { name: table.dataset.name }),
    ...(table.dataset.table && ID.test(table.dataset.table) && { from: table.dataset.table }),
  };
  const computes =
    Object.keys(formulas).length || Object.keys(formats).length || Object.keys(typed).length;
  return {
    grid: part,
    sized,
    designs: designsPasted(table),
    copied: computes
      ? ({ origin: { row: row || 0, col: col || 0 }, formulas, formats, typed } satisfies Copied)
      : null,
  };
}

/** A table nested in a cell gives its cells' text in turn; a note in a cell keeps its text in
 * brackets, as a cell holds no notes. */
function flattened(cell: HTMLElement): HTMLElement {
  const copy = cell.cloneNode(true) as HTMLElement;
  for (const nested of [...copy.querySelectorAll('table')].reverse()) {
    if (!nested.isConnected) continue;
    const parts = [...nested.querySelectorAll('td, th')].flatMap((inner) => [...inner.childNodes]);
    nested.replaceWith(...parts);
  }
  for (const note of copy.querySelectorAll('span[data-note]')) {
    note.replaceWith(`[${(note.textContent ?? '').trim()}]`);
  }
  return copy;
}

/** A pasted cell's fill: ours by its name or colour, another program's background as its colour,
 * a palette's where it is one; none where it is white or clear. */
function pastedFill(cell: HTMLElement): string | null {
  const own = cell.dataset.fill;
  if (own && tintOf(own)) return own;
  if (cell.closest('table[data-designs]')) return null;
  const given = cell.style.backgroundColor || cell.getAttribute('bgcolor');
  if (!given) return null;
  const probe = document.createElement('span');
  probe.style.color = given;
  const channels = probe.style.color.match(/^rgb\((\d+), (\d+), (\d+)\)$/);
  if (!channels) return null;
  const hex = `#${channels
    .slice(1)
    .map((channel) => Number(channel).toString(16).padStart(2, '0'))
    .join('')}`;
  return hex === '#ffffff' ? null : (named(HIGHLIGHTS, hex) ?? hex);
}

/** The cells of a table from a page, each a node with what it holds and the merge it is, by the
 * stand-in ids of its rows and columns; a computed cell keeps its look, its formula or its typed
 * text computing it again. */
export function tableCellsIn(element: HTMLElement, schema: Schema): Fragment {
  const table = element as HTMLTableElement;
  const { slots, rows, cols } = slotsOf(table);
  const shape = linesIn(table, { rows, cols });
  const parser = ModelParser.fromSchema(schema);
  const cells: Node[] = [];
  for (const slot of slots) {
    const attrs = {
      row: shape.rows[slot.row],
      col: shape.cols[slot.col],
      fill: pastedFill(slot.cell),
    };
    const parsed = parser.parse(flattened(slot.cell), { topNode: schema.nodes.cell.create(attrs) });
    const { formula, text } = slot.cell.dataset;
    const cell = formula
      ? retyped(parsed, '')
      : text !== undefined
        ? retyped(parsed, text)
        : parsed;
    cells.push(cell);
  }
  return Fragment.from(cells);
}

/** The table as another program reads it: rows of cells with their spans and content, each
 * computed cell showing its value and keeping its formula, format and typed text for a paste
 * here. */
export function tableElement(
  table: Node,
  content: (cell: Node) => globalThis.Node,
): HTMLTableElement {
  const lines = partLines(table)!;
  const layout = new Layout(lines, table);
  const copied: Copied | null = table.attrs.copied;
  const element = document.createElement('table');
  const design = designOf(table, layout);
  element.dataset.designs = JSON.stringify(design.designs);
  element.style.background = backgroundOf(design.whole?.background, true) ?? '';
  element.style.boxShadow = shadowOf(design.whole?.shadow, true) ?? '';
  if (copied) element.dataset.origin = `${copied.origin.row}:${copied.origin.col}`;
  if (lines.name) element.dataset.name = lines.name;
  const from: string | undefined = table.attrs.grid?.from;
  if (from) {
    element.dataset.table = from;
    element.dataset.rows = (table.attrs.grid as Part).rows.join(' ');
    element.dataset.cols = lines.cols.join(' ');
  }
  element.style.borderCollapse = 'collapse';
  for (const [name, value] of Object.entries(apartOf(design.whole, true))) {
    element.style.setProperty(name, value);
  }
  const group = element.appendChild(document.createElement('colgroup'));
  const sized = isSized(table);
  if (sized) element.dataset.sized = '';
  else element.style.width = '100%';
  const widths = sized
    ? charactersOf(true, lines.cols, lines.widths, 0)
    : widthsOf(false, lines.cols, lines.widths);
  for (const width of widths) {
    group.appendChild(document.createElement('col')).style.width = sized
      ? `${Math.round(width * CHARACTER_POINTS * 100) / 100}pt`
      : `${rounded(width)}%`;
  }
  const body = element.appendChild(document.createElement('tbody'));
  for (let row = 0; row < layout.rows; row++) {
    const line = body.insertRow();
    const height = lines.heights.get(lines.rowId(row)!);
    if (height) line.style.height = `${height}pt`;
    for (const cell of layout.cellsIn({ top: row, left: 0, bottom: row, right: layout.cols - 1 })) {
      const td = line.insertCell();
      if (cell.rows > 1) td.rowSpan = cell.rows;
      if (cell.cols > 1) td.colSpan = cell.cols;
      const first = design.at(cell.row, cell.col);
      const last = design.at(cell.row + cell.rows - 1, cell.col + cell.cols - 1);
      td.style.borderTop = borderOf(first.edges.top, true);
      td.style.borderLeft = borderOf(first.edges.left, true);
      td.style.borderBottom = borderOf(last.edges.bottom, true);
      td.style.borderRight = borderOf(last.edges.right, true);
      for (const [name, value] of Object.entries(dressOf(first, true))) {
        td.style.setProperty(name, value);
      }
      if (first.valign)
        td.style.verticalAlign = first.valign === 'center' ? 'middle' : first.valign;
      const formula = copied?.formulas[cell.key];
      const format = copied?.formats[cell.key];
      const typed = copied?.typed?.[cell.key];
      if (formula) td.dataset.formula = formula;
      if (format) td.dataset.format = format;
      if (typed !== undefined) td.dataset.text = typed;
      const own: string | null = cell.node?.attrs.fill ?? null;
      if (own) td.dataset.fill = own;
      const fill = tintOf(own ?? first.fill, true);
      if (fill) td.style.backgroundColor = fill;
      if (cell.node) td.append(content(unquoted(cell.node)));
    }
  }
  return element;
}

/** Tab-separated rows, as spreadsheets copy a range as plain text; a merged cell's text is in its
 * first slot. */
export function tableText(table: Node): string {
  const layout = new Layout(partLines(table)!, table);
  const rows: string[] = [];
  for (let row = 0; row < layout.rows; row++) {
    const texts: string[] = [];
    for (let col = 0; col < layout.cols; col++) {
      const cell = layout.at(row, col)!;
      const node = cell.row === row && cell.col === col && cell.node && unquoted(cell.node);
      texts.push(
        node ? node.textBetween(0, node.content.size, ' ').replace(/[\t\r\n]+/g, ' ') : '',
      );
    }
    rows.push(texts.join('\t'));
  }
  return rows.join('\n');
}

/** A table's copy as the clipboard carries it: the cells of the rectangle as nodes, a light cell's
 * from its text and look, each showing the value computed for it, with what computes it. */
export function copiedTable(table: Node, layout: Layout, grid: Grid, rect: Rect): Node {
  const { schema } = table.type;
  const rows = rowsOf(grid, rect.top, rect.bottom);
  const cols = grid.cols.slice(rect.left, rect.right + 1);
  const formulas: Record<string, string> = {};
  const formats: Record<string, string> = {};
  const typed: Record<string, string> = {};
  const merges: Record<string, string> = {};
  const cells: Node[] = [];
  for (const placed of layout.cellsIn(rect)) {
    const [row, col] = placed.key.split(':');
    const shown = grid.cell(row, col);
    const value = grid.value(row, col);
    if (shown?.formula) formulas[placed.key] = shown.formula;
    if (shown?.format) formats[placed.key] = shown.format;
    if (placed.rows > 1 || placed.cols > 1) {
      const bottom = Math.min(placed.row + placed.rows - 1, rect.bottom);
      const right = Math.min(placed.col + placed.cols - 1, rect.right);
      merges[placed.key] = keyOf(grid.rowId(bottom)!, grid.cols[right]);
    }
    let node = placed.node ?? lightCell(schema, row, col, shown?.text ?? '', shown?.look);
    if (standsIn(value, !!shown?.formula, !!shown?.format)) {
      if (!shown?.formula) typed[placed.key] = node.textContent;
      node = retyped(node, value!.text);
    }
    cells.push(node);
  }
  const sizes = (ids: readonly string[], sizes: ReadonlyMap<string, number>) =>
    Object.fromEntries(ids.flatMap((id) => (sizes.has(id) ? [[id, sizes.get(id)!]] : [])));
  const part: Part = {
    rows,
    cols,
    widths: sizes(cols, grid.widths),
    heights: sizes(rows, grid.heights),
    merges,
    ...(grid.name && { name: grid.name }),
    from: table.attrs.id,
  };
  const copied: Copied = { origin: { row: rect.top, col: rect.left }, formulas, formats, typed };
  const designs = (designsIn(table.attrs.designs) ?? []).flatMap((design) => {
    if (!design.area) return [design];
    const area = areaOf(design, grid);
    if (!area) return [];
    const [top, left] = [Math.max(area[0], rect.top), Math.max(area[1], rect.left)];
    const [bottom, right] = [Math.min(area[2], rect.bottom), Math.min(area[3], rect.right)];
    if (bottom < top || right < left) return [];
    const from = keyOf(grid.rowId(top)!, grid.cols[left]);
    return [{ ...design, area: { from, to: keyOf(grid.rowId(bottom)!, grid.cols[right]) } }];
  });
  return table.type.create(
    {
      ...table.attrs,
      id: null,
      proposedRows: null,
      grid: part,
      copied,
      designs: designs.length ? designs : null,
    },
    cells,
  );
}
