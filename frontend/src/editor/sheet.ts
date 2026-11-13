import { DOMSerializer, type Node } from 'prosemirror-model';
import {
  apartOf,
  borderOf,
  designOf,
  drawn,
  dressOf,
  gradientLine,
  backgroundOf,
  inkOf,
  shadowOf,
  strokeOf,
  tintOf,
  type Designed,
  type Edge,
  type Side,
  type TableDesign,
} from './design';
import { columnName, type Value } from './formulas';
import type { Grid, Look } from './grids';
import { GAP, scaleOf, type Row, type TableGaps } from './pages';
import { schema } from './schema';
import {
  isSized,
  Layout,
  NONE_HIDDEN,
  lightCell,
  rectOfCell,
  retyped,
  standsIn,
  unquoted,
  widthsOf,
  type Lines,
  type Placed,
  type Rect,
} from './tables';

const serializer = DOMSerializer.fromSchema(schema);

/** A rectangle in a sheet's own pixels, from the top left of its headings. */
export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Where a sheet's lines lie: each column's left and each row's top and height, its headings
 * before them, and the page gaps of the Pages view above the rows a page starts with. */
export class Geometry {
  constructor(
    readonly side: number,
    readonly top: number,
    /** Of every column and of the last one's right. */
    readonly lefts: Float64Array,
    readonly tops: Float64Array,
    readonly heights: Float64Array,
    /** Half the gap Word's spacing sets between cells, in pixels; none where they touch. */
    readonly inset = 0,
  ) {}

  get rows(): number {
    return this.heights.length;
  }

  get cols(): number {
    return this.lefts.length - 1;
  }

  get width(): number {
    return this.lefts[this.lefts.length - 1];
  }

  get height(): number {
    const last = this.rows - 1;
    return last < 0 ? this.top : this.tops[last] + this.heights[last];
  }

  bottom(row: number): number {
    return this.tops[row] + this.heights[row];
  }

  /** The row at the height, the last one above where it falls in a gap; -1 above the rows. */
  rowAt(y: number): number {
    let low = 0;
    let high = this.rows - 1;
    if (high < 0 || y < this.tops[0]) return -1;
    while (low < high) {
      const middle = (low + high + 1) >> 1;
      if (this.tops[middle] <= y) low = middle;
      else high = middle - 1;
    }
    return low;
  }

  colAt(x: number): number {
    let low = 0;
    let high = this.cols - 1;
    if (high < 0 || x < this.lefts[0]) return -1;
    while (low < high) {
      const middle = (low + high + 1) >> 1;
      if (this.lefts[middle] <= x) low = middle;
      else high = middle - 1;
    }
    return low;
  }

  box(rect: Rect): Box {
    const x = this.lefts[rect.left];
    const y = this.tops[rect.top];
    return { x, y, width: this.lefts[rect.right + 1] - x, height: this.bottom(rect.bottom) - y };
  }

  /** Where a cell's own box stands in its slots, which its fill, text and lines keep to. */
  cell(rect: Rect): Box {
    const box = this.box(rect);
    if (!this.inset) return box;
    const { top, left, bottom, right } = insetsOf(rect, this.rows, this.cols, this.inset);
    return {
      x: box.x + left,
      y: box.y + top,
      width: Math.max(0, box.width - left - right),
      height: Math.max(0, box.height - top - bottom),
    };
  }
}

/** How far a cell's box stands within its slots where the cells are set apart: half the gap from
 * a neighbour's, and the whole gap from the table's frame. */
export function insetsOf(
  rect: Rect,
  rows: number,
  cols: number,
  inset: number,
): Record<'top' | 'left' | 'bottom' | 'right', number> {
  return {
    top: rect.top === 0 ? inset * 2 : inset,
    left: rect.left === 0 ? inset * 2 : inset,
    bottom: rect.bottom === rows - 1 ? inset * 2 : inset,
    right: rect.right === cols - 1 ? inset * 2 : inset,
  };
}

/** How a cell's text is drawn, as the page's styles draw it in an element. */
export interface Ink {
  font: string;
  color: string;
  background: string | null;
  /** The cell's own ground, under its text and the lines around it. */
  fill: string | null;
  underline: boolean;
  strike: boolean;
  caps: 'all' | 'small' | null;
  align: 'left' | 'center' | 'right';
  valign: 'top' | 'center' | 'bottom' | null;
  /** Before every line, after the first line's own, and after every line, in pixels. */
  start: number;
  first: number;
  end: number;
  line: number;
}

/** The interface colours a sheet is drawn in, as the theme gives them now. */
export interface Colours {
  ink: string;
  line: string;
  muted: string;
  selected: string;
  focus: string;
  ground: string;
  accent: string;
}

const TOKENS: Record<keyof Colours, string> = {
  ink: '--ink',
  line: '--line',
  muted: '--muted',
  selected: '--selected',
  focus: '--focus',
  ground: '--raised',
  accent: '--accent',
};

/** The background the text stands on outside the Pages view, whose paper lies under the text
 * rather than around it. */
function groundOf(element: HTMLElement): string {
  for (let at = element.parentElement; at; at = at.parentElement) {
    const colour = getComputedStyle(at).backgroundColor;
    if (!transparent(colour)) return colour;
  }
  return getComputedStyle(document.documentElement).backgroundColor;
}

function px(value: string): number {
  return parseFloat(value) || 0;
}

function aligned(value: string): Ink['align'] {
  if (value === 'center') return 'center';
  return value === 'right' || value === 'end' ? 'right' : 'left';
}

function transparent(colour: string): boolean {
  return colour === 'transparent' || /^rgba\(.*,\s*0\)$/.test(colour);
}

/** A cell's look with its design's under it: the design's marks beneath its own, and its fill,
 * alignment and capitals where it gives none. */
export interface Dressed extends Look {
  caps?: 'all' | 'small';
  valign?: 'top' | 'center' | 'bottom';
}

export function dressed(look: Look | undefined, cell: Designed): Dressed | undefined {
  if (!cell.parts.length) return look;
  const marks = { ...cell.marks, ...look?.marks };
  const align = look?.attrs?.align ?? cell.align;
  const fill = look?.fill ?? cell.fill;
  return {
    ...look,
    ...(Object.keys(marks).length && { marks }),
    ...(align && { attrs: { ...look?.attrs, align } }),
    ...(fill && { fill }),
    ...(cell.caps && cell.caps !== 'none' && { caps: cell.caps }),
    ...(cell.valign && { valign: cell.valign }),
  };
}

/** The looks of cells read from elements the page's styles reach, as a cell of the sheet would
 * be: the canvas draws in what the stylesheet says, which stays the one source of it. */
export class Inks {
  private kept = new Map<string, Ink>();
  private paints = new Map<string, string>();
  private colours: (Colours & { paper: boolean }) | null = null;
  private pads: { x: number; y: number } | null = null;
  private heading: Ink | null = null;
  readonly host: HTMLElement;
  private box: HTMLElement;

  constructor(parent: HTMLElement) {
    this.host = parent.appendChild(document.createElement('div'));
    this.host.className = 'ponistra-probe';
    this.host.ariaHidden = 'true';
    this.box = this.host.appendChild(document.createElement('div'));
    this.box.className = 'ponistra-cell-box';
  }

  /** Forgotten once the theme or the document's styles change. */
  clear(): void {
    this.kept.clear();
    this.paints.clear();
    this.colours = null;
    this.pads = null;
    this.heading = null;
  }

  /** A host the document does not show measures nothing, which would be kept as the look's. */
  private showing(): void {
    if (!this.host.getClientRects().length) throw new Error('A table is measured while not shown');
  }

  /** `kind` is the value's in the cell, `computed` whether that value stands in its place. */
  of(look: Dressed | undefined, kind: Value['kind'] | null, computed = false): Ink {
    const key = `${computed ? '=' : ''}${kind ?? ''}${JSON.stringify(look ?? null)}`;
    let ink = this.kept.get(key);
    if (!ink) {
      ink = this.probe(look, kind, computed);
      this.kept.set(key, ink);
    }
    return ink;
  }

  private probe(look: Dressed | undefined, kind: Value['kind'] | null, computed: boolean): Ink {
    this.showing();
    const holder = document.createElement('div');
    holder.className = computed ? 'ponistra-cell-value' : 'ponistra-cell';
    if (kind) holder.dataset.kind = kind;
    if (look?.caps === 'all') holder.style.textTransform = 'uppercase';
    if (look?.caps === 'small') holder.style.fontVariantCaps = 'small-caps';
    holder.append(serializer.serializeFragment(lightCell(schema, 'r', 'c', 'x', look).content));
    this.box.replaceChildren(holder);
    const block = holder.firstElementChild as HTMLElement;
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    const text = (walker.nextNode()?.parentElement ?? block) as HTMLElement;
    const style = getComputedStyle(text);
    let underline = false;
    let strike = false;
    let background: string | null = null;
    for (let at: HTMLElement | null = text; at && holder.contains(at); at = at.parentElement) {
      const own = at === text ? style : getComputedStyle(at);
      underline ||= own.textDecorationLine.includes('underline');
      strike ||= own.textDecorationLine.includes('line-through');
      if (!background && at !== block && !transparent(own.backgroundColor)) {
        background = own.backgroundColor;
      }
    }
    const paragraph = getComputedStyle(block);
    const tint = tintOf(look?.fill);
    let fill: string | null = null;
    if (tint) {
      holder.style.backgroundColor = tint;
      const ground = getComputedStyle(holder).backgroundColor;
      if (!transparent(ground)) fill = ground;
    }
    const ink: Ink = {
      font: `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`,
      color: style.color,
      background,
      fill,
      underline,
      strike,
      caps:
        style.textTransform === 'uppercase'
          ? 'all'
          : style.fontVariantCaps === 'small-caps'
            ? 'small'
            : null,
      align: aligned(paragraph.textAlign),
      valign: look?.valign ?? null,
      start: px(paragraph.marginLeft) + px(paragraph.paddingLeft),
      first: px(paragraph.textIndent),
      end: px(paragraph.marginRight) + px(paragraph.paddingRight),
      line:
        block.getBoundingClientRect().height -
        px(paragraph.paddingTop) -
        px(paragraph.paddingBottom),
    };
    this.box.replaceChildren();
    return ink;
  }

  /** A cell's padding beside and above its text. */
  padding(): { x: number; y: number } {
    if (!this.pads) {
      this.showing();
      const style = getComputedStyle(this.box);
      this.pads = { x: px(style.paddingLeft), y: px(style.paddingTop) };
    }
    return this.pads;
  }

  /** The look of the letters and numbers of the headings. */
  headings(): Ink {
    if (!this.heading) {
      this.showing();
      const probe = this.host.appendChild(document.createElement('div'));
      probe.className = 'ponistra-heading';
      probe.textContent = 'A';
      const style = getComputedStyle(probe);
      this.heading = {
        font: `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`,
        color: style.color,
        background: null,
        fill: null,
        underline: false,
        strike: false,
        caps: null,
        align: 'center',
        valign: null,
        start: 0,
        first: 0,
        end: px(style.paddingRight),
        line: probe.getBoundingClientRect().height,
      };
      probe.remove();
    }
    return this.heading;
  }

  /** A colour as CSS gives it, as the canvas takes it now: a page's `light-dark()` resolved. */
  paint(css: string): string {
    let found = this.paints.get(css);
    if (found === undefined) {
      const probe = this.host.appendChild(document.createElement('span'));
      probe.style.color = css;
      found = getComputedStyle(probe).color;
      probe.remove();
      this.paints.set(css, found);
    }
    return found;
  }

  colour(): Colours {
    const paper = this.host.closest('.ponistra-pages') !== null;
    if (!this.colours || this.colours.paper !== paper) {
      const probe = this.host.appendChild(document.createElement('span'));
      const found = {} as Colours;
      for (const [name, token] of Object.entries(TOKENS) as [keyof Colours, string][]) {
        probe.style.color = `var(${token})`;
        found[name] = getComputedStyle(probe).color;
      }
      probe.remove();
      if (!paper) found.ground = groundOf(this.host);
      this.colours = { paper, ...found };
    }
    return this.colours;
  }

  destroy(): void {
    this.host.remove();
  }
}

let measurer: CanvasRenderingContext2D | null = null;
const LINES_KEPT = 4000;
const wraps = new Map<string, string[]>();

/** Wrapped lines measured before a font loaded break where its own would not. */
export function forgetWraps(): void {
  wraps.clear();
}

function widthOf(text: string): number {
  return measurer!.measureText(text).width;
}

/** The longest start of the word within the width, a character at least. */
function fitting(word: string, width: number): number {
  let low = 1;
  let high = word.length;
  while (low < high) {
    const middle = (low + high + 1) >> 1;
    if (widthOf(word.slice(0, middle)) <= width) low = middle;
    else high = middle - 1;
  }
  return low;
}

/** The lines the text falls into at the width, as the page wraps a cell's: after the spaces, and
 * inside a word only where it is wider than a whole line. */
export function wrapped(text: string, font: string, width: number, first = 0): string[] {
  const key = `${font}\u0000${Math.round(width)}\u0000${first}\u0000${text}`;
  const known = wraps.get(key);
  if (known) return known;
  measurer ??= document.createElement('canvas').getContext('2d')!;
  measurer.font = font;
  const lines: string[] = [];
  let line = '';
  let room = width - first;
  for (let word of text.split(/(?<= )/)) {
    while (word) {
      if (widthOf((line + word).trimEnd()) <= room) {
        line += word;
        word = '';
      } else if (line) {
        lines.push(line);
        line = '';
        room = width;
      } else {
        const cut = fitting(word, room);
        lines.push(word.slice(0, cut));
        word = word.slice(cut);
        room = width;
      }
    }
  }
  lines.push(line);
  if (wraps.size >= LINES_KEPT) wraps.delete(wraps.keys().next().value!);
  wraps.set(key, lines);
  return lines;
}

/** What a light cell shows: its text, and the look it is drawn in. */
export interface Painted {
  text: string;
  ink: Ink;
}

export interface Frame {
  /** The part of the sheet the canvas covers, and the part of it in view. */
  area: Box;
  view: Box;
  geometry: Geometry;
  layout: Layout;
  /** A light cell's text, null where the cell is drawn by an element of its own or empty. */
  cell: (row: number, col: number, key: string) => Painted | null;
  design: TableDesign;
  /** Whether a line the design does not draw is drawn as a guide, as while the table is written. */
  guides: boolean;
  /** A colour of CSS as the canvas takes it. */
  paint: (css: string) => string;
  selected: Rect | null;
  /** The lines the headings mark, each row's number, where the browser knows it, and whether
   * a filter leaves rows out; null where the headings are not shown. */
  headings: {
    picked: Rect | null;
    number: (row: number) => number | undefined;
    filtered: boolean;
  } | null;
  colours: Colours;
  heading: Ink;
  padding: { x: number; y: number };
  /** Whether a row is held, its cells known; the others are drawn without text. */
  held: (row: number) => boolean;
  /** How many rows stay at the top of the view. */
  frozen: number;
  /** The header rows drawn again atop the pages of the Pages view: how many, the top of each
   * copy and what their cells read there. */
  repeats: { rows: number; tops: readonly number[]; cell: Frame['cell'] } | null;
}

/** The headings' letters stay at the top of the view and the numbers at its left while the
 * sheet runs on past them. */
export function headingsAt(frame: Pick<Frame, 'view' | 'geometry'>): { x: number; y: number } {
  const { view, geometry } = frame;
  return {
    x: Math.max(0, Math.min(view.x, geometry.width - geometry.side)),
    y: Math.max(0, Math.min(view.y, geometry.height - geometry.top)),
  };
}

/** How far the frozen rows are moved from their place, as they stay at the top of the view, under
 * the headings' letters where those are shown, while the rows after them run on past. */
export function frozenShift(
  frame: Pick<Frame, 'view' | 'geometry' | 'frozen'>,
  headings: boolean,
): number {
  const { view, geometry, frozen } = frame;
  if (!frozen) return 0;
  const most = geometry.height - geometry.bottom(frozen - 1);
  return Math.max(0, Math.min(view.y - (headings ? 0 : geometry.top), most));
}

export function visibleRows(geometry: Geometry, area: Box): [number, number] {
  const first = Math.max(0, geometry.rowAt(area.y));
  const last = geometry.rowAt(area.y + area.height);
  return [first, last < 0 ? -1 : last];
}

export function visibleCols(geometry: Geometry, area: Box): [number, number] {
  const first = Math.max(0, geometry.colAt(area.x));
  const last = geometry.colAt(area.x + area.width);
  return [first, last < 0 ? -1 : last];
}

const PX_PER_PT = 4 / 3;
/** Half the widest line an edge draws (6 pt), which the table leaves room for right of and below
 * its cells, where its outer lines reach past them. */
export const REACH = 4;

type Draw = (edge: Edge | null, x1: number, y1: number, x2: number, y2: number) => void;

/** The lines between the cells as the table's design draws them, none inside a merged cell, and
 * where it draws none a guide while the table is written in. */
function paintEdges(
  ctx: CanvasRenderingContext2D,
  frame: Frame,
  rows: [number, number],
  cols: [number, number],
): void {
  const { geometry, colours } = frame;
  if (rows[1] < rows[0] || cols[1] < cols[0]) return;
  const guides = new Path2D();
  const lines: [Edge, number, number, number, number][] = [];
  const line: Draw = (edge, x1, y1, x2, y2) => {
    if (edge) lines.push([edge, x1, y1, x2, y2]);
    else if (frame.guides) {
      const across = y1 === y2;
      guides.moveTo(across ? x1 : Math.round(x1) - 0.5, across ? Math.round(y1) - 0.5 : y1);
      guides.lineTo(across ? x2 : Math.round(x2) - 0.5, across ? Math.round(y2) - 0.5 : y2);
    }
  };
  (geometry.inset ? linesApart : linesBetween)(frame, rows, cols, line);
  ctx.save();
  ctx.lineWidth = 1;
  ctx.strokeStyle = colours.line;
  ctx.setLineDash([3, 2]);
  ctx.stroke(guides);
  for (const [edge, x1, y1, x2, y2] of lines) {
    const { doubled, dashes, width } = strokeOf(edge);
    const whole = Math.max(1, width * PX_PER_PT);
    const each = doubled ? Math.max(1, whole / 3) : whole;
    const offsets = doubled ? [-each, each] : [0];
    const odd = Math.round(each) % 2 === 1 ? 0.5 : 0;
    const across = y1 === y2;
    ctx.lineWidth = each;
    ctx.strokeStyle = edge.color ? frame.paint(inkOf(edge)) : colours.ink;
    ctx.setLineDash(dashes.map((dash) => dash * each));
    ctx.beginPath();
    for (const offset of offsets) {
      if (across) {
        const y = Math.round(y1 + offset) - odd;
        ctx.moveTo(x1, y);
        ctx.lineTo(x2, y);
      } else {
        const x = Math.round(x1 + offset) - odd;
        ctx.moveTo(x, y1);
        ctx.lineTo(x, y2);
      }
    }
    ctx.stroke();
  }
  ctx.restore();
}

/** The lines two touching cells share, each drawn once. */
function linesBetween(
  frame: Frame,
  rows: [number, number],
  cols: [number, number],
  line: Draw,
): void {
  const { geometry, layout, design } = frame;
  for (let row = rows[0]; row <= rows[1]; row++) {
    const top = geometry.tops[row];
    const bottom = geometry.bottom(row);
    for (let col = cols[0]; col <= cols[1]; col++) {
      const left = geometry.lefts[col];
      const right = geometry.lefts[col + 1];
      const here = layout.at(row, col)!;
      const { edges } = design.at(row, col);
      const above = row > 0 && geometry.bottom(row - 1) === top ? layout.at(row - 1, col) : null;
      if (above?.key !== here.key) line(edges.top, left, top, right, top);
      if (col === 0 || layout.at(row, col - 1)!.key !== here.key) {
        line(edges.left, left, top, left, bottom);
      }
      if (
        col === cols[1] &&
        (col + 1 >= geometry.cols || layout.at(row, col + 1)!.key !== here.key)
      ) {
        line(edges.right, right, top, right, bottom);
      }
      const below = row + 1 < geometry.rows ? layout.at(row + 1, col) : null;
      const joined = below && geometry.tops[row + 1] === bottom;
      if ((!joined || row === rows[1]) && below?.key !== here.key) {
        line(edges.bottom, left, bottom, right, bottom);
      }
    }
  }
}

/** The lines of cells set apart, each cell's own four round its box: a side it lacks lets the two
 * beside it run on across the gap to its slots' edge, as Word draws them; and the table's frame
 * round them all. */
function linesApart(
  frame: Frame,
  rows: [number, number],
  cols: [number, number],
  line: Draw,
): void {
  const { geometry, layout, design } = frame;
  const { lefts, tops } = geometry;
  const edge = (row: number, col: number, side: Side) => design.at(row, col).edges[side];
  for (const placed of layout.cellsOver({
    top: rows[0],
    left: cols[0],
    bottom: rows[1],
    right: cols[1],
  })) {
    if (layout.hiddenAt(placed.row, placed.col)) continue;
    const rect = rectOfCell(placed);
    const box = geometry.cell(rect);
    if (!box.width || !box.height) continue;
    const slots = geometry.box(rect);
    const [right, bottom] = [box.x + box.width, box.y + box.height];
    for (const [side, y, at] of [
      ['top', box.y, rect.top],
      ['bottom', bottom, rect.bottom],
    ] as const) {
      const start = !edge(at, rect.left, 'left');
      const end = !edge(at, rect.right, 'right');
      for (let c = rect.left; c <= rect.right; c++) {
        const x1 = c === rect.left ? (start ? slots.x : box.x) : lefts[c];
        const x2 = c === rect.right ? (end ? slots.x + slots.width : right) : lefts[c + 1];
        line(edge(at, c, side), x1, y, x2, y);
      }
    }
    for (const [side, x, at] of [
      ['left', box.x, rect.left],
      ['right', right, rect.right],
    ] as const) {
      const start = !edge(rect.top, at, 'top');
      const end = !edge(rect.bottom, at, 'bottom');
      for (let r = rect.top; r <= rect.bottom; r++) {
        const y1 = r === rect.top ? (start ? slots.y : box.y) : tops[r];
        const y2 = r === rect.bottom ? (end ? slots.y + slots.height : bottom) : geometry.bottom(r);
        line(edge(r, at, side), x, y1, x, y2);
      }
    }
  }
  const outer = design.whole?.lines ?? {};
  const framed = (side: Side, x1: number, y1: number, x2: number, y2: number) => {
    const edge = drawn(outer[side]);
    if (edge) line(edge, x1, y1, x2, y2);
  };
  const [left, right] = [lefts[0], lefts[geometry.cols]];
  if (rows[0] === 0) framed('top', left, tops[0], right, tops[0]);
  if (rows[1] === geometry.rows - 1)
    framed('bottom', left, geometry.height, right, geometry.height);
  for (let row = rows[0]; row <= rows[1]; row++) {
    const [top, bottom] = [tops[row], geometry.bottom(row)];
    if (cols[0] === 0) framed('left', left, top, left, bottom);
    if (cols[1] === geometry.cols - 1) framed('right', right, top, right, bottom);
  }
}

function paintText(ctx: CanvasRenderingContext2D, frame: Frame, box: Box, painted: Painted): void {
  const { ink } = painted;
  const { padding } = frame;
  const width = box.width - padding.x * 2 - ink.start - ink.end;
  const text = ink.caps === 'all' ? painted.text.toLocaleUpperCase() : painted.text;
  if (width <= 0 || !text) return;
  const lines = wrapped(text, ink.font, width, ink.first);
  const room = box.height - padding.y * 2 - lines.length * ink.line;
  const lowered = ink.valign === 'center' ? room / 2 : ink.valign === 'bottom' ? room : 0;
  ctx.save();
  ctx.beginPath();
  ctx.rect(box.x, box.y, box.width, box.height);
  ctx.clip();
  ctx.font = ink.font;
  ctx.fontVariantCaps = ink.caps === 'small' ? 'small-caps' : 'normal';
  ctx.textBaseline = 'middle';
  const left = box.x + padding.x + ink.start;
  lines.forEach((line, index) => {
    const shown = line.trimEnd();
    const measured = ctx.measureText(shown).width;
    const room = width - (index === 0 ? ink.first : 0);
    const offset =
      ink.align === 'right' ? room - measured : ink.align === 'center' ? (room - measured) / 2 : 0;
    const x = left + (index === 0 ? ink.first : 0) + offset;
    const top = box.y + padding.y + Math.max(0, lowered) + index * ink.line;
    const y = top + ink.line / 2;
    if (ink.background) {
      ctx.fillStyle = ink.background;
      ctx.fillRect(x, top, measured, ink.line);
    }
    ctx.fillStyle = ink.color;
    ctx.fillText(shown, x, y);
    if (ink.underline || ink.strike) {
      ctx.strokeStyle = ink.color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      const size = parseFloat(ink.font.split(' ')[2]) || 16;
      for (const at of [ink.underline && y + size * 0.4, ink.strike && y + size * 0.05]) {
        if (at === false) continue;
        const line = Math.round(at) + 0.5;
        ctx.moveTo(x, line);
        ctx.lineTo(x + measured, line);
      }
      ctx.stroke();
    }
  });
  ctx.restore();
}

function paintHeadings(
  ctx: CanvasRenderingContext2D,
  frame: Frame,
  rows: [number, number],
  cols: [number, number],
  shift: number,
): void {
  const { geometry, colours, heading, headings } = frame;
  if (!headings) return;
  const { picked } = headings;
  const at = headingsAt(frame);
  const right = geometry.width;
  ctx.save();
  ctx.font = heading.font;
  ctx.textBaseline = 'middle';
  ctx.fillStyle = colours.ground;
  ctx.fillRect(geometry.side, at.y, right - geometry.side, geometry.top);
  const runs: [number, number][] = [];
  for (let row = rows[0]; row <= rows[1]; row++) {
    const last = runs.at(-1);
    if (last && last[1] === geometry.tops[row]) last[1] = geometry.bottom(row);
    else runs.push([geometry.tops[row], geometry.bottom(row)]);
  }
  for (const [top, bottom] of runs) ctx.fillRect(at.x, top, geometry.side, bottom - top);
  ctx.textAlign = 'center';
  for (let col = cols[0]; col <= cols[1]; col++) {
    const left = geometry.lefts[col];
    const width = geometry.lefts[col + 1] - left;
    if (!width) {
      hiddenMark(ctx, colours, left - 1, at.y, 2, geometry.top);
      continue;
    }
    const marked = picked && col >= picked.left && col <= picked.right;
    if (marked) {
      ctx.fillStyle = colours.selected;
      ctx.fillRect(left, at.y, width, geometry.top);
    }
    ctx.fillStyle = marked ? colours.ink : colours.muted;
    ctx.font = marked ? heading.font.replace(/^(\S+) \S+/, '$1 600') : heading.font;
    ctx.fillText(columnName(col), left + width / 2, at.y + geometry.top / 2, width);
  }
  ctx.textAlign = 'right';
  const number = (row: number, moved: number) => {
    const top = geometry.tops[row] + moved;
    const height = geometry.heights[row];
    if (!height) {
      hiddenMark(ctx, colours, at.x, top - 1, geometry.side, 2);
      return;
    }
    const marked = picked && row >= picked.top && row <= picked.bottom;
    if (marked) {
      ctx.fillStyle = colours.selected;
      ctx.fillRect(at.x, top, geometry.side, height);
    }
    const own = headings.number(row);
    const before = row ? headings.number(row - 1) : -1;
    if (!headings.filtered && own !== undefined && before !== undefined && own - before > 1) {
      hiddenMark(ctx, colours, at.x, top - 1, geometry.side, 2);
    }
    if (own === undefined) return;
    ctx.fillStyle = headings.filtered ? colours.accent : marked ? colours.ink : colours.muted;
    ctx.font = marked ? heading.font.replace(/^(\S+) \S+/, '$1 600') : heading.font;
    ctx.fillText(
      String(own + 1),
      at.x + geometry.side - heading.end,
      top + heading.line / 2 + frame.padding.y / 2,
    );
  };
  for (let row = rows[0]; row <= rows[1]; row++) number(row, 0);
  if (shift) {
    ctx.fillStyle = colours.ground;
    const bottom = geometry.bottom(frame.frozen - 1);
    ctx.fillRect(at.x, geometry.top + shift, geometry.side, bottom - geometry.top);
    for (let row = 0; row < frame.frozen; row++) number(row, shift);
  }
  ctx.fillStyle = colours.ground;
  ctx.fillRect(at.x, at.y, geometry.side, geometry.top);
  // The bands cover the half pixel the table's first lines are drawn on.
  const x = Math.round(at.x + geometry.side) - 0.5;
  const y = Math.round(at.y + geometry.top) - 0.5;
  ctx.strokeStyle = frame.design.lined ? colours.ink : colours.line;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (const [top, bottom] of runs) {
    if (bottom <= y) continue;
    ctx.moveTo(x, Math.max(y, top));
    ctx.lineTo(x, bottom);
  }
  ctx.moveTo(x, y);
  ctx.lineTo(right, y);
  ctx.stroke();
  ctx.restore();
}

/** Where rows or columns are hidden, a bar across the headings, as Excel draws it. */
function hiddenMark(
  ctx: CanvasRenderingContext2D,
  colours: Colours,
  x: number,
  y: number,
  width: number,
  height: number,
): void {
  ctx.fillStyle = colours.ink;
  ctx.fillRect(x, y, width, height);
}

/** Draws the part of the sheet the canvas covers: the selected cells' ground, the lines between
 * the cells, the light cells' text, the frozen rows over the rows they stay above, and the
 * headings over them all. */
export function paint(ctx: CanvasRenderingContext2D, frame: Frame): void {
  const { area, geometry, colours } = frame;
  ctx.clearRect(area.x, area.y, area.width, area.height);
  const rows = visibleRows(geometry, area);
  const cols = visibleCols(geometry, area);
  paintCells(ctx, frame, rows, cols);
  const shift = frozenShift(frame, !!frame.headings);
  if (frame.frozen) {
    const bottom = geometry.bottom(frame.frozen - 1) + shift;
    if (shift) {
      const top = geometry.top + shift - 1;
      ctx.save();
      ctx.fillStyle = colours.ground;
      ctx.fillRect(0, top, geometry.width + 1, bottom - top);
      ctx.beginPath();
      ctx.rect(0, top, geometry.width + 1, bottom - top);
      ctx.clip();
      ctx.translate(0, shift);
      paintCells(ctx, frame, [0, frame.frozen - 1], cols);
      ctx.restore();
    }
    ctx.save();
    ctx.strokeStyle = colours.ink;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(geometry.side, Math.round(bottom));
    ctx.lineTo(geometry.width, Math.round(bottom));
    ctx.stroke();
    ctx.restore();
  }
  if (frame.repeats) paintRepeats(ctx, frame, frame.repeats, cols);
  paintHeadings(ctx, frame, rows, cols, shift);
}

function paintRepeats(
  ctx: CanvasRenderingContext2D,
  frame: Frame,
  repeats: NonNullable<Frame['repeats']>,
  cols: [number, number],
): void {
  const { area, geometry } = frame;
  const height = geometry.bottom(repeats.rows - 1) - geometry.tops[0];
  const copy = { ...frame, selected: null, cell: repeats.cell };
  for (const top of repeats.tops) {
    if (top + height < area.y || top > area.y + area.height) continue;
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, top - 1, geometry.width + 1, height + 1);
    ctx.clip();
    ctx.translate(0, Math.round(top - geometry.tops[0]));
    paintCells(ctx, copy, [0, repeats.rows - 1], cols);
    ctx.restore();
  }
}

function paintCells(
  ctx: CanvasRenderingContext2D,
  frame: Frame,
  rows: [number, number],
  cols: [number, number],
): void {
  const { geometry, layout } = frame;
  const cells: [Box, Painted][] = [];
  if (rows[1] >= rows[0] && cols[1] >= cols[0]) {
    const seen = new Set<string>();
    for (const merge of layout.mergesIn(rows[0], rows[1])) {
      if (merge.right < cols[0] || merge.left > cols[1] || !frame.held(merge.top)) continue;
      const cell = layout.at(merge.top, merge.left)!;
      seen.add(cell.key);
      if (layout.hiddenAt(merge.top, merge.left)) continue;
      const painted = frame.cell(cell.row, cell.col, cell.key);
      const box = geometry.cell(merge);
      if (painted && box.width && box.height) cells.push([box, painted]);
    }
    for (let row = rows[0]; row <= rows[1]; row++) {
      if (!frame.held(row)) continue;
      for (let col = cols[0]; col <= cols[1]; col++) {
        if (!layout.starts(row, col)) continue;
        const cell = layout.at(row, col)!;
        if (seen.has(cell.key)) continue;
        const painted = frame.cell(row, col, cell.key);
        const box = geometry.cell({ top: row, left: col, bottom: row, right: col });
        if (painted && box.width && box.height) cells.push([box, painted]);
      }
    }
  }
  paintGround(ctx, frame, rows, cols);
  const selected = frame.selected && geometry.box(frame.selected);
  if (selected) {
    ctx.fillStyle = frame.colours.selected;
    ctx.fillRect(selected.x, selected.y, selected.width, selected.height);
  }
  for (const [box, { ink }] of cells) {
    if (!ink.fill) continue;
    ctx.fillStyle = ink.fill;
    ctx.fillRect(box.x, box.y, box.width, box.height);
    const over = selected && overlap(box, selected);
    if (!over) continue;
    // The selection stays seen over a filled cell, as a tint of its fill.
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.fillStyle = frame.colours.selected;
    ctx.fillRect(over.x, over.y, over.width, over.height);
    ctx.restore();
  }
  paintEdges(ctx, frame, rows, cols);
  for (const [box, painted] of cells) paintText(ctx, frame, box, painted);
}

/** The ground the table's design lays under its cells, a gradient running across the whole
 * table; only between them where they are set apart, as Word lays it. */
function paintGround(
  ctx: CanvasRenderingContext2D,
  frame: Frame,
  rows: [number, number],
  cols: [number, number],
): void {
  const ground = frame.design.whole?.background;
  const { geometry } = frame;
  if (!ground || rows[1] < rows[0] || cols[1] < cols[0]) return;
  if (typeof ground === 'string') {
    const tint = tintOf(ground);
    if (!tint) return;
    ctx.fillStyle = frame.paint(tint);
  } else {
    const whole = geometry.box({
      top: 0,
      left: 0,
      bottom: geometry.rows - 1,
      right: geometry.cols - 1,
    });
    const gradient = ctx.createLinearGradient(...gradientLine(ground.angle, whole));
    for (const { at, color } of ground.stops)
      gradient.addColorStop(at / 100, frame.paint(tintOf(color) ?? 'transparent'));
    ctx.fillStyle = gradient;
  }
  const area = { top: rows[0], left: cols[0], bottom: rows[1], right: cols[1] };
  const box = geometry.box(area);
  const path = new Path2D();
  path.rect(box.x, box.y, box.width, box.height);
  if (geometry.inset) {
    for (const placed of frame.layout.cellsOver(area)) {
      const cell = geometry.cell(rectOfCell(placed));
      path.rect(cell.x, cell.y, cell.width, cell.height);
    }
  }
  ctx.fill(path, 'evenodd');
}

function overlap(one: Box, other: Box): Box | null {
  const x = Math.max(one.x, other.x);
  const y = Math.max(one.y, other.y);
  const right = Math.min(one.x + one.width, other.x + other.width);
  const bottom = Math.min(one.y + one.height, other.y + other.height);
  return right > x && bottom > y ? { x, y, width: right - x, height: bottom - y } : null;
}

const NO_LINES: Lines = {
  name: '',
  rowCount: 0,
  cols: [],
  widths: new Map(),
  heights: new Map(),
  hidden: NONE_HIDDEN,
  merges: new Map(),
  plain: true,
  rowId: () => undefined,
  rowNumber: () => undefined,
  rowIndex: () => -1,
  colIndex: () => -1,
};

const PAGED = 'ponistra-paged-rows';
/** A table's header rows drawn again atop a page it runs onto, in the page gap before it. */
const REPEATED = 'ponistra-repeated';
/** Rows laid out at a time to be measured: few layouts for a long table, which never stands whole
 * in the page. */
const MEASURED = 256;

type Gap = TableGaps['rows'][number];

const papers = new WeakMap<HTMLElement, PaperTable>();

/** A table as paper shows it, the light cells' text in their look and the computed values in
 * place of their formulas. Its rows are measured a run at a time and drawn only on the pages
 * shown, each page's rows a table of its own where the page gaps of the Pages view leave them: a
 * long table's rows, all laid out at once, take more of the printer's memory than it has. */
export class PaperTable {
  readonly element = document.createElement('div');
  private readonly columns = document.createElement('colgroup');
  private readonly design: TableDesign;
  private readonly lines: Lines;
  private readonly layout: Layout;
  private readonly frozen: number;
  private heights = new Float64Array(0);
  /** How far a table's first row starts below its top, and its end below its last row's. */
  private lead = 0;
  private tail = 0;
  private gaps: readonly Gap[] = [];
  private tops = new Float64Array(0);
  private readonly gapElements: HTMLElement[] = [];
  private shown: HTMLTableElement[] = [];
  private showing: ((top: number, bottom: number) => boolean) | null = null;
  private readonly awaited = new Set<string>();

  constructor(
    table: Node,
    private readonly grid: Grid | undefined,
  ) {
    this.lines = grid ?? NO_LINES;
    this.layout = new Layout(this.lines, table);
    this.frozen = grid?.frozenRows() ?? 0;
    this.design = designOf(table, this.layout, (row, col) => grid?.cell(row, col)?.look);
    this.element.className = PAGED;
    const { cols, widths, hidden } = this.lines;
    widthsOf(isSized(table), cols, widths, hidden.cols).forEach((share, at) => {
      const { style } = this.columns.appendChild(document.createElement('col'));
      style.width = `${share}%`;
      if (hidden.cols.has(cols[at])) style.visibility = 'collapse';
    });
    papers.set(this.element, this);
  }

  /** Every row in one table, as a header or a footer holds it. */
  whole(): HTMLTableElement {
    const table = this.table();
    for (let row = 0; row < this.layout.rows; row++) {
      table.tBodies[0].append(this.drawn(row, this.layout.rows));
    }
    return table;
  }

  /** Measures each row as it lies at the paper's width, then lays the rows out again. The
   * images still loading in them come back as their loading, once each: the rows are to be
   * measured again once they are in. */
  measure(): Promise<unknown> | null {
    const { rows } = this.layout;
    const scale = scaleOf(this.element);
    const heights = new Float64Array(rows);
    const apart = (this.design.whole?.spacing ?? 0) * 2 * PX_PER_PT;
    const loading: Promise<unknown>[] = [];
    for (let first = 0; first < rows;) {
      let last = Math.min(first + MEASURED, rows) - 1;
      for (let below = last; ; last = below) {
        for (const merge of this.layout.mergesIn(last, last)) below = Math.max(below, merge.bottom);
        if (below === last) break;
      }
      const table = this.table();
      const body = table.tBodies[0];
      for (let row = first; row <= last; row++) body.append(this.drawn(row, last + 1));
      this.element.append(table);
      const box = table.getBoundingClientRect();
      for (let at = 0; at < body.rows.length; at++) {
        const line = body.rows[at].getBoundingClientRect();
        heights[first + at] = line.height / scale + (first + at < rows - 1 ? apart : 0);
        if (first + at === 0) this.lead = (line.top - box.top) / scale;
        if (first + at === rows - 1) this.tail = (box.bottom - line.bottom) / scale;
      }
      for (const image of table.querySelectorAll('img')) {
        if (image.complete || this.awaited.has(image.src)) continue;
        this.awaited.add(image.src);
        loading.push(image.decode().catch(() => {}));
      }
      table.remove();
      first = last + 1;
    }
    this.heights = heights;
    this.place();
    return loading.length ? Promise.all(loading) : null;
  }

  gap(gaps: readonly Gap[]): void {
    this.gaps = gaps;
    this.place();
  }

  /** The rows as the Pages view measures them: each one's client top and bottom, whether a
   * merged cell above reaches into it and whether it heads the table. */
  rows(): Row[] {
    const rect = this.element.getBoundingClientRect();
    const scale = scaleOf(this.element, rect);
    const joined = new Set<number>();
    for (const merge of this.layout.mergesIn(0, this.tops.length - 1)) {
      for (let row = merge.top + 1; row <= merge.bottom; row++) joined.add(row);
    }
    return Array.from(this.tops, (top, row) => ({
      top: rect.top + top * scale,
      bottom: rect.top + (top + this.heights[row]) * scale,
      joined: joined.has(row),
      header: row < this.frozen,
    }));
  }

  /** Draws the pages of rows `shown` takes by their top and bottom within the table, and takes
   * the others out. */
  show(shown: (top: number, bottom: number) => boolean): void {
    this.showing = shown;
    for (const table of this.shown) table.remove();
    this.shown = [];
    const rows = this.tops.length;
    const starts = this.gaps.filter(({ row }) => row > 0 && row < rows);
    const header = new Map(this.gaps.map((gap) => [gap.row, gap.header ?? 0]));
    [0, ...starts.map(({ row }) => row)].forEach((first, index, firsts) => {
      const last = (firsts[index + 1] ?? rows) - 1;
      if (last < first) return;
      const above = header.get(first) ?? 0;
      const top = this.tops[first] - above - this.lead;
      if (!shown(top, this.tops[last] + this.heights[last] + this.tail)) return;
      const table = this.table();
      table.style.top = `${top}px`;
      const body = table.tBodies[0];
      for (let copied = 0; above && copied < this.frozen; copied++) {
        const copy = body.appendChild(this.drawn(copied, this.frozen));
        copy.className = REPEATED;
        copy.ariaHidden = 'true';
      }
      for (let row = first; row <= last; row++) {
        const line = body.appendChild(this.drawn(row, last + 1));
        if (row === first) this.continued(line, row);
      }
      this.shown.push(table);
    });
    this.element.append(...this.shown);
  }

  /** Each row's top below the gaps before it, the table as tall as its rows and gaps, and a gap
   * element where each gap stands, which the Pages view takes out of the table's height. */
  private place(): void {
    const rows = this.heights.length;
    const gaps = new Map(this.gaps.map(({ row, gap }) => [row, gap]));
    const tops = new Float64Array(rows);
    let y = this.lead;
    for (let row = 0; row < rows; row++) {
      y += gaps.get(row) ?? 0;
      tops[row] = y;
      y += this.heights[row];
    }
    this.tops = tops;
    this.element.style.height = `${y + this.tail}px`;
    while (this.gapElements.length < this.gaps.length) {
      const gap = this.element.appendChild(document.createElement('div'));
      gap.className = GAP;
      gap.ariaHidden = 'true';
      this.gapElements.push(gap);
    }
    for (const gap of this.gapElements.splice(this.gaps.length)) gap.remove();
    this.gaps.forEach(({ row, gap }, index) => {
      const { style } = this.gapElements[index];
      style.top = `${(row < rows ? tops[row] : y) - gap}px`;
      style.height = `${gap}px`;
    });
    if (this.showing) this.show(this.showing);
  }

  private table(): HTMLTableElement {
    const table = document.createElement('table');
    table.className = 'ponistra-rows';
    table.style.background = backgroundOf(this.design.whole?.background) ?? '';
    table.style.boxShadow = shadowOf(this.design.whole?.shadow) ?? '';
    const apart = apartOf(this.design.whole);
    for (const [name, value] of Object.entries(apart)) table.style.setProperty(name, value);
    table.toggleAttribute('data-apart', !!apart['border-spacing']);
    table.append(this.columns.cloneNode(true), document.createElement('tbody'));
    return table;
  }

  /** The merged cells a page breaks, each an empty cell of its own atop the page's rows, without
   * which the browser would move the cells right of it into its columns. */
  private continued(line: HTMLTableRowElement, row: number): void {
    const merges = this.layout
      .mergesIn(row, row)
      .filter((merge) => merge.top < row)
      .sort((a, b) => a.left - b.left);
    merges.forEach((merge, held) => {
      let before = held;
      for (let col = 0; col < merge.left; col++) if (this.layout.starts(row, col)) before++;
      const cell = document.createElement('td');
      if (merge.bottom > row) cell.rowSpan = merge.bottom - row + 1;
      if (merge.right > merge.left) cell.colSpan = merge.right - merge.left + 1;
      line.insertBefore(cell, line.cells[before] ?? null);
    });
  }

  private drawn(row: number, until: number): HTMLTableRowElement {
    const line = document.createElement('tr');
    const id = this.lines.rowId(row);
    const height = id === undefined ? undefined : this.lines.heights.get(id);
    if (height) line.style.height = `${height}pt`;
    for (const placed of this.layout.cellsIn({
      top: row,
      left: 0,
      bottom: row,
      right: this.layout.cols - 1,
    })) {
      const cell = line.insertCell();
      const rows = Math.min(placed.rows, until - row);
      if (rows > 1) cell.rowSpan = rows;
      if (placed.cols > 1) cell.colSpan = placed.cols;
      if (this.layout.hiddenAt(placed.row, placed.col)) continue;
      const first = this.design.at(placed.row, placed.col);
      const last = this.design.at(placed.row + rows - 1, placed.col + placed.cols - 1);
      const { style } = cell;
      style.borderTop = borderOf(first.edges.top);
      style.borderLeft = borderOf(first.edges.left);
      style.borderBottom = borderOf(last.edges.bottom);
      style.borderRight = borderOf(last.edges.right);
      for (const [name, value] of Object.entries(dressOf(first))) style.setProperty(name, value);
      if (first.valign) style.verticalAlign = first.valign === 'center' ? 'middle' : first.valign;
      const fill = fillOf(this.grid, placed, first);
      if (fill) style.backgroundColor = fill;
      const paper = onPaper(this.grid, placed);
      if (!paper) continue;
      // A value keeps a holder of its own: the text style it reads in would otherwise size the
      // cell's padding, which is in `ch` of the cell's font, unlike the canvas's cell box.
      if (paper.computed) cell.append(valueHolder(paper.content, paper.kind!));
      else {
        cell.className = 'ponistra-cell';
        if (paper.kind) cell.dataset.kind = paper.kind;
        cell.append(paper.content);
      }
    }
    return line;
  }
}

/** Draws the pages of the paper tables within `within` that `shown` takes by their top and
 * bottom within it, and takes the others out, so that a long document prints a run of pages at a
 * time: a browser lays out all that a print shows in one go. */
export function showPaperPages(
  within: HTMLElement,
  shown: (top: number, bottom: number) => boolean,
): void {
  const origin = within.getBoundingClientRect().top;
  const placed = [...within.querySelectorAll<HTMLElement>(`.${PAGED}`)].map((element) => ({
    paper: papers.get(element)!,
    top: element.getBoundingClientRect().top - origin,
  }));
  for (const { paper, top } of placed) {
    paper.show((above, below) => shown(top + above, top + below));
  }
}

/** A cell's fill as the page shows it, its node's or its look's over its design's; empty where it
 * has none. */
export function fillOf(grid: Grid | undefined, placed: Placed, designed: Designed): string {
  const [r, c] = placed.key.split(':');
  const own: string | null | undefined = placed.node
    ? placed.node.attrs.fill
    : grid?.cell(r, c)?.look?.fill;
  return tintOf(own ?? designed.fill) ?? '';
}

/** A cell's content as paper shows it: a light cell's text in its look, the computed value in
 * place of its formula. */
export function paperCell(grid: Grid | undefined, placed: Placed): HTMLElement {
  const paper = onPaper(grid, placed);
  if (paper?.computed) return valueHolder(paper.content, paper.kind!);
  const holder = document.createElement('div');
  holder.className = 'ponistra-cell';
  if (paper?.kind) holder.dataset.kind = paper.kind;
  if (paper) holder.append(paper.content);
  return holder;
}

/** What a cell shows on paper, its value's kind and whether that value stands in its place; null
 * where it is a light cell without text. */
function onPaper(
  grid: Grid | undefined,
  placed: Placed,
): {
  content: DocumentFragment | HTMLElement;
  kind: Value['kind'] | null;
  computed: boolean;
} | null {
  const [r, c] = placed.key.split(':');
  const shown = grid?.cell(r, c);
  const value = grid?.value(r, c);
  const computed = standsIn(value, !!shown?.formula, !!shown?.format);
  if (!placed.node && !computed && !shown?.text) return null;
  const node = placed.node ?? lightCell(schema, r, c, shown?.text ?? '', shown?.look);
  const content = computed ? retyped(node, value!.text) : unquoted(node);
  return {
    content: serializer.serializeFragment(content.content),
    kind: value?.kind ?? null,
    computed,
  };
}

function valueHolder(content: DocumentFragment | HTMLElement, kind: Value['kind']): HTMLElement {
  const holder = document.createElement('div');
  holder.className = 'ponistra-cell-value';
  holder.dataset.kind = kind;
  holder.append(content);
  return holder;
}
