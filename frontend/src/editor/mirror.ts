import { columnName } from './formulas';
import {
  frozenShift,
  headingsAt,
  visibleCols,
  visibleRows,
  type Box,
  type Geometry,
} from './sheet';
import { meets, rectOfCell, type Layout, type Rect } from './tables';

/** The part of a sheet the canvas draws, as the mirror shows it. */
export interface Mirrored {
  area: Box;
  view: Box;
  geometry: Geometry;
  layout: Layout;
  headings: boolean;
  /** What a cell drawn on the canvas reads. */
  text: (row: number, col: number, key: string) => string;
  /** The row's own place among all the table's rows, where the browser knows it. */
  number: (row: number) => number | undefined;
  /** The element of a cell that has one: a cell with a node, or one being written in. */
  own: (key: string) => HTMLElement | null;
  selected: Rect | null;
  /** How many rows stay at the top of the view. */
  frozen: number;
}

let ids = 0;

function set(element: HTMLElement, name: string, value: string | null): void {
  if (value === null) element.removeAttribute(name);
  else if (element.getAttribute(name) !== value) element.setAttribute(name, value);
}

function place(element: HTMLElement, box: Box): void {
  const { style } = element;
  for (const [name, value] of [
    ['left', box.x],
    ['top', box.y],
    ['width', box.width],
    ['height', box.height],
  ] as const) {
    if (style[name] !== `${value}px`) style[name] = `${value}px`;
  }
}

function written(element: HTMLElement, text: string): void {
  if (element.textContent !== text) element.textContent = text;
}

const CELL = [
  'role',
  'data-address',
  'aria-colindex',
  'aria-rowspan',
  'aria-colspan',
  'aria-selected',
  'data-frozen',
];

/** The cells the canvas draws as the rows and cells of a grid over it, numbered within the whole
 * table: what a screen reader reads and a pointer finds. A cell with an element of its own is
 * that element, which its row owns; such a row owns its other cells too, as owned elements
 * follow a row's own children, and would be read out of order. */
export class Mirror {
  readonly dom = document.createElement('div');
  private heads = document.createElement('div');
  private rows = new Map<number, HTMLElement>();
  private cells = new Map<string, HTMLElement>();
  private owned = new Set<HTMLElement>();
  private headings = new Map<string, HTMLElement>();

  constructor(private grid: HTMLElement) {
    grid.setAttribute('aria-multiselectable', 'true');
    this.dom.className = 'ponistra-mirror';
    this.heads.setAttribute('role', 'row');
    this.heads.setAttribute('aria-rowindex', '1');
    this.dom.append(this.heads);
  }

  clear(): void {
    for (const element of this.owned) for (const name of CELL) element.removeAttribute(name);
    for (const element of [...this.rows.values(), ...this.headings.values()]) element.remove();
    this.rows.clear();
    this.cells.clear();
    this.owned.clear();
    this.headings.clear();
  }

  /** The table's size, its headings counted, whatever of it is in view. */
  size(geometry: Geometry): void {
    set(this.grid, 'aria-rowcount', String(geometry.rows + 1));
    set(this.grid, 'aria-colcount', String(geometry.cols + 1));
  }

  update(mirrored: Mirrored): void {
    const { area, geometry, layout, selected } = mirrored;
    this.dom.toggleAttribute('data-headings', mirrored.headings);
    const [top, bottom] = visibleRows(geometry, area);
    const [left, right] = visibleCols(geometry, area);
    const at = headingsAt(mirrored);
    const { frozen } = mirrored;
    const shift = frozenShift(mirrored, mirrored.headings);
    const shown: number[] = [];
    const tall = (row: number) => geometry.heights[row] > 0;
    if (shift) for (let row = 0; row < frozen; row++) if (tall(row)) shown.push(row);
    for (let row = shift ? Math.max(top, frozen) : top; row <= bottom; row++) {
      if (tall(row)) shown.push(row);
    }
    const rows = new Map<number, HTMLElement>();
    const cells = new Map<string, HTMLElement>();
    const owned = new Set<HTMLElement>();
    const headings = new Map<string, HTMLElement>();
    const seen = new Set<string>();
    const members = new Map<HTMLElement, HTMLElement[]>();
    const owning = new Set<HTMLElement>();
    const last = new Map<HTMLElement, Element>();
    const member = (holder: HTMLElement, element: HTMLElement) => {
      const list = members.get(holder);
      if (list) list.push(element);
      else members.set(holder, [element]);
    };
    const put = (holder: HTMLElement, element: HTMLElement) => {
      const prior = last.get(holder);
      const there = prior ? prior.nextElementSibling : holder.firstElementChild;
      if (there !== element) {
        if (prior) prior.after(element);
        else holder.prepend(element);
      }
      last.set(holder, element);
    };
    const heading = (
      id: string,
      role: string,
      holder: HTMLElement,
      index: number,
      text: string,
    ) => {
      let element = this.headings.get(id);
      if (!element) {
        element = document.createElement('div');
        element.setAttribute('role', role);
      }
      put(holder, element);
      member(holder, element);
      set(element, 'aria-colindex', String(index));
      written(element, text);
      headings.set(id, element);
      return element;
    };
    const line = (row: number) => {
      let element = rows.get(row) ?? this.rows.get(row);
      if (!element) {
        element = document.createElement('div');
        element.setAttribute('role', 'row');
        element.setAttribute('aria-rowindex', String(row + 2));
      }
      rows.set(row, element);
      return element;
    };

    const across: number[] = [];
    for (let col = left; col <= right; col++) {
      const x = geometry.lefts[col];
      const box = { x, y: at.y, width: geometry.lefts[col + 1] - x, height: geometry.top };
      if (!box.width) continue;
      across.push(col);
      place(heading(`c${col}`, 'columnheader', this.heads, col + 2, columnName(col)), box);
    }
    for (const row of shown) {
      const moved = row < frozen ? shift : 0;
      const box = {
        x: at.x,
        y: geometry.tops[row] + moved,
        width: geometry.side,
        height: geometry.heights[row],
      };
      const number = mirrored.number(row);
      const label = number === undefined ? '' : String(number + 1);
      place(heading(`r${row}`, 'rowheader', line(row), 1, label), box);
      for (const col of across) {
        const cell = layout.at(row, col)!;
        if (seen.has(cell.key) || layout.hiddenAt(cell.row, cell.col)) continue;
        seen.add(cell.key);
        const holder = line(cell.row);
        let element = mirrored.own(cell.key);
        if (element) {
          owning.add(holder);
          owned.add(element);
        } else {
          element = this.cells.get(cell.key) ?? document.createElement('div');
          put(holder, element);
          const box = geometry.box(rectOfCell(cell));
          place(element, { ...box, y: box.y + (cell.row < frozen ? shift : 0) });
          written(element, mirrored.text(cell.row, cell.col, cell.key));
          cells.set(cell.key, element);
        }
        member(holder, element);
        set(element, 'role', 'gridcell');
        const number = mirrored.number(cell.row);
        const address = number === undefined ? null : `${columnName(cell.col)}${number + 1}`;
        set(element, 'data-address', address);
        set(element, 'aria-colindex', String(cell.col + 2));
        set(element, 'aria-rowspan', cell.rows > 1 ? String(cell.rows) : null);
        set(element, 'aria-colspan', cell.cols > 1 ? String(cell.cols) : null);
        const chosen = selected !== null && meets(rectOfCell(cell), selected);
        set(element, 'aria-selected', selected ? String(chosen) : null);
        set(element, 'data-frozen', shift && cell.row < frozen ? '' : null);
      }
    }

    for (const [id, element] of this.headings) if (headings.get(id) !== element) element.remove();
    for (const [key, element] of this.cells) if (cells.get(key) !== element) element.remove();
    for (const element of this.owned) {
      if (!owned.has(element)) for (const name of CELL) element.removeAttribute(name);
    }
    for (const [row, element] of this.rows) if (rows.get(row) !== element) element.remove();
    let before: Element = this.heads;
    for (const row of [...rows.keys()].sort((a, b) => a - b)) {
      const element = rows.get(row)!;
      const order = owning.has(element) ? members.get(element)! : null;
      set(
        element,
        'aria-owns',
        order?.map((each) => (each.id ||= `ponistra-cell-${++ids}`)).join(' ') ?? null,
      );
      if (before.nextElementSibling !== element) before.after(element);
      before = element;
    }
    this.headings = headings;
    this.rows = rows;
    this.cells = cells;
    this.owned = owned;
  }
}
