import type { Attrs, Node } from 'prosemirror-model';
import tables from '../../../schema/tables.json';
import { fontStack, substitute } from '../fonts';
import { HIGHLIGHTS, onScreen, type Palette, swatchOf, TEXT_COLORS, type Swatch } from './colors';
import type { Look } from './grids';
import type { Layout, Lines } from './tables';

export type Side = 'top' | 'bottom' | 'left' | 'right';
type Region = Side | 'insideH' | 'insideV';

export interface Edge {
  line: string;
  width: number;
  color?: string;
}

/** A line on an edge, or none, which takes away a line beneath it. */
export type Line = Edge | 'none';
export type Edges = Partial<Record<Side, Line>>;

export interface Part {
  fill?: string;
  marks?: Record<string, Attrs | false>;
  caps?: 'all' | 'small' | 'none';
  align?: string;
  valign?: 'top' | 'center' | 'bottom';
  edges?: Partial<Record<Region, Line>>;
}

export const SWITCHES = [
  'header',
  'totals',
  'firstColumn',
  'lastColumn',
  'rowBands',
  'columnBands',
] as const;
export type Switch = (typeof SWITCHES)[number];
export type Rules = 'word' | 'excel' | 'powerpoint';

export interface Gradient {
  angle: number;
  stops: { at: number; color: string }[];
}

export interface Design {
  rules: Rules;
  name?: string;
  parts?: Partial<Record<string, Part>>;
  on?: Partial<Record<Switch, boolean>>;
  bands?: { rows?: readonly number[]; columns?: readonly number[] };
  lines?: Partial<Record<Region, Line>>;
  background?: string | Gradient;
  shadow?: { color: string; blur: number; distance: number; angle: number };
  spacing?: number;
  area?: { from: string; to: string };
}

export interface Designed {
  parts: string[];
  fill: string | null;
  marks: Record<string, Attrs>;
  caps: Part['caps'] | null;
  align: string | null;
  valign: Part['valign'] | null;
  edges: Record<Side, Edge | null>;
}

interface Reach {
  after: string | null;
  skip: string[];
}

interface RuleSet {
  order: string[];
  claimWhereDefined: string[];
  lastYields: boolean;
  rowBands: Reach;
  columnBands: Reach;
  regions: 'nominal' | 'contiguous';
  insideVWithRows: number;
  shared: 'weight' | 'rank' | 'later';
  own: 'cell' | 'upperLeft';
  classes?: Record<string, number>;
  codes?: Record<string, number>;
  kinds?: { name: string; line: string; width: number }[];
  darkness?: number[][];
}

const RULES = tables.rules as unknown as Record<Rules, RuleSet>;
const CORNERS: Record<string, readonly string[]> = tables.corners;
/** Our own designs by their ids, as the menu offers them. */
export const CATALOGUE = tables.designs as unknown as Record<string, Omit<Design, 'name'>>;
/** The design a new table takes. */
export const NEW = 'grid';

const SIDES: Record<Side, [Region, number, number]> = {
  top: ['insideH', -1, 0],
  bottom: ['insideH', 1, 0],
  left: ['insideV', 0, -1],
  right: ['insideV', 0, 1],
};
const OPPOSITE: Record<Side, Side> = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' };

export function ours(id: string): Design {
  return { name: id, ...CATALOGUE[id] };
}

export function partsAt(
  design: Design,
  row: number,
  col: number,
  rows: number,
  cols: number,
): string[] {
  const { parts } = placedAt(design, row, col, rows, cols);
  return RULES[design.rules].order.filter((part) => parts.has(part));
}

/** The parts in a cell, and for each band among them where the cell stands in it and how many
 * rows or columns it spans, cut short by the table's end or not. */
function placedAt(
  design: Design,
  row: number,
  col: number,
  rows: number,
  cols: number,
): { parts: Set<string>; spans: Map<string, [number, number]> } {
  const rules = RULES[design.rules];
  const on = design.on ?? {};
  const defined = design.parts ?? {};
  const here = new Set(['table']);
  if (on.header && row === 0) here.add('header');
  if (on.totals && row === rows - 1) here.add('totals');
  if (on.firstColumn && col === 0) here.add('firstColumn');
  if (on.lastColumn && col === cols - 1) here.add('lastColumn');
  const claims = (part: string) =>
    !rules.claimWhereDefined.includes(part) ||
    part in defined ||
    Object.entries(CORNERS).some(
      ([corner, pair]) =>
        pair.includes(part) && corner in defined && pair.every((each) => on[each as Switch]),
    );
  if (rules.lastYields) {
    for (const [first, last] of [
      ['header', 'totals'],
      ['firstColumn', 'lastColumn'],
    ]) {
      if (here.has(first) && claims(first)) here.delete(last);
    }
  }
  const bands = design.bands ?? {};
  const spans = new Map<string, [number, number]>();
  for (const [kind, at, names] of [
    ['rowBands', row, ['rowBand1', 'rowBand2']],
    ['columnBands', col, ['columnBand1', 'columnBand2']],
  ] as const) {
    const reach = rules[kind];
    if (!on[kind] || reach.skip.some((part) => here.has(part) && claims(part))) continue;
    const after = reach.after as Switch | null;
    const from = at - (after && on[after] && claims(after) ? 1 : 0);
    const [first, second] = bands[kind === 'rowBands' ? 'rows' : 'columns'] ?? [1, 1];
    const size = first + second;
    if (!size) continue;
    const offset = ((from % size) + size) % size;
    const [name, place, length] =
      offset < first ? [names[0], offset, first] : [names[1], offset - first, second];
    here.add(name);
    spans.set(name, [place, length]);
  }
  for (const [corner, [across, down]] of Object.entries(CORNERS)) {
    if (here.has(across) && here.has(down)) here.add(corner);
  }
  return { parts: here, spans };
}

function rgb(color: string | undefined): number[] {
  const hex = color ? swatchOf(TEXT_COLORS, color)?.light : undefined;
  const value = hex ? parseInt(hex.slice(1), 16) : 0;
  return [value >> 16, (value >> 8) & 255, value & 255];
}

function darkness(rules: RuleSet, edge: Edge): number[] {
  const channels = rgb(edge.color);
  return rules.darkness!.map(
    (weights) => -weights.reduce((sum, w, at) => sum + w * channels[at], 0),
  );
}

function weight(rules: RuleSet, edge: Edge): number[] {
  const kind = rules.classes![edge.line] ?? 2;
  const code = rules.codes![edge.line];
  const eighths = edge.width * 8;
  return [kind, kind === 2 ? eighths * code : eighths, code, ...darkness(rules, edge)];
}

/** Where among the kinds of line a program's rules rank the one nearest an edge stands: of its
 * line, else a single one, the nearest width, the heavier where two are as near. */
export function kindOf(rules: Rules, edge: Edge): number {
  const kinds = RULES[rules].kinds!;
  let same = kinds.flatMap((kind, at) => (kind.line === edge.line ? [at] : []));
  if (!same.length) same = kinds.flatMap((kind, at) => (kind.line === 'single' ? [at] : []));
  let best = same[0];
  for (const at of same) {
    const near = Math.abs(kinds[at].width - edge.width);
    const bestNear = Math.abs(kinds[best].width - edge.width);
    if (near < bestNear || (near === bestNear && at > best)) best = at;
  }
  return best;
}

function rank(rules: Rules, edge: Edge): number[] {
  return [kindOf(rules, edge), ...darkness(RULES[rules], edge)];
}

function atLeast(one: number[], other: number[]): boolean {
  for (let at = 0; at < one.length; at++) if (one[at] !== other[at]) return one[at] > other[at];
  return true;
}

/** An edge as it draws: null where it draws no line. */
export function drawn(edge: Line | undefined | null): Edge | null {
  return edge === undefined || edge === null || edge === 'none' ? null : edge;
}

function same(one: Edge, other: Edge): boolean {
  return one.line === other.line && one.width === other.width && one.color === other.color;
}

/** The edge two cells share by a program's rules, the upper or left one's side first, each with
 * where among the parts it came from. */
function settle(
  rules: Rules,
  a: Edge | null,
  from: number,
  b: Edge | null,
  to: number,
): Edge | null {
  const set = RULES[rules];
  if (set.shared === 'later') return from >= to ? a : b;
  if (a === null || b === null || same(a, b)) return a ?? b;
  const key =
    set.shared === 'weight' ? (edge: Edge) => weight(set, edge) : (edge: Edge) => rank(rules, edge);
  return atLeast(key(a), key(b)) ? a : b;
}

interface Raw {
  cell: Designed;
  lines: Partial<Record<Side, Line>>;
  sources: Partial<Record<Side, number>>;
}

const KEPT = 4096;

/** A table's design (D30) over rows by cols, with the cells' own edges over it, by the rules of
 * the program it came from (schema/tables.json), as the server's resolver (designs.py) gives it:
 * each cell's parts, fill, marks, capitals and alignment, and its four edges once the edges two
 * cells share are settled. A cell is resolved as it is drawn, since a sheet's rows run long. */
export class Resolver {
  private readonly rules: RuleSet;
  private readonly kept = new Map<number, Raw>();

  constructor(
    readonly design: Design,
    readonly rows: number,
    readonly cols: number,
    private readonly own: (row: number, col: number) => Edges | undefined = () => undefined,
  ) {
    this.rules = RULES[design.rules];
  }

  private parts(row: number, col: number): string[] {
    return partsAt(this.design, row, col, this.rows, this.cols);
  }

  private spans(row: number, col: number): Map<string, [number, number]> {
    return placedAt(this.design, row, col, this.rows, this.cols).spans;
  }

  private inside(row: number, col: number): boolean {
    return row >= 0 && col >= 0 && row < this.rows && col < this.cols;
  }

  private raw(row: number, col: number): Raw {
    const key = row * this.cols + col;
    const found = this.kept.get(key);
    if (found) return found;
    const { design, rules } = this;
    const order = rules.order;
    const defined = design.parts ?? {};
    const lines = design.lines ?? {};
    const names = this.parts(row, col);
    const cell: Designed = {
      parts: names,
      fill: null,
      marks: {},
      caps: null,
      align: null,
      valign: null,
      edges: { top: null, bottom: null, left: null, right: null },
    };
    for (const name of names) {
      const part = defined[name];
      if (!part) continue;
      if (part.fill !== undefined) cell.fill = part.fill;
      for (const [mark, attrs] of Object.entries(part.marks ?? {})) {
        if (attrs === false) delete cell.marks[mark];
        else cell.marks[mark] = attrs;
      }
      if (part.caps !== undefined) cell.caps = part.caps;
      if (part.align !== undefined) cell.align = part.align;
      if (part.valign !== undefined) cell.valign = part.valign;
    }
    const raw: Raw = { cell, lines: {}, sources: {} };
    const mine = this.own(row, col) ?? {};
    const spans = this.spans(row, col);
    const nominal = rules.regions === 'nominal';
    const noInsideV = (design.bands?.rows ?? [1, 1])[0] < rules.insideVWithRows;
    for (const [side, [inner, dr, dc]] of Object.entries(SIDES) as [
      Side,
      [Region, number, number],
    ][]) {
      const outer = !this.inside(row + dr, col + dc);
      const across = outer ? [] : this.parts(row + dr, col + dc);
      const region = outer && !design.spacing ? side : inner;
      if (region in lines) {
        raw.lines[side] = lines[region];
        raw.sources[side] = -1;
      }
      for (const name of names) {
        const edges = defined[name]?.edges;
        if (!edges) continue;
        const span = spans.get(name);
        const acrossBand = (side === 'top' || side === 'bottom') === name.startsWith('rowBand');
        const within =
          nominal && span && acrossBand
            ? side === 'top' || side === 'left'
              ? span[0] > 0
              : span[0] < span[1] - 1
            : !outer && across.includes(name);
        const key = within ? inner : side;
        if (key === 'insideV' && noInsideV && name.startsWith('columnBand')) continue;
        if (key in edges) {
          raw.lines[side] = edges[key];
          raw.sources[side] = order.indexOf(name);
        }
      }
      if (
        side in mine &&
        !(rules.own === 'upperLeft' && !outer && (side === 'top' || side === 'left'))
      ) {
        raw.lines[side] = mine[side];
        raw.sources[side] = order.length;
      }
    }
    if (this.kept.size >= KEPT) this.kept.clear();
    this.kept.set(key, raw);
    return raw;
  }

  /** The edge two cells share, the upper or left one's side first. */
  private settled(first: Raw, side: Side, second: Raw): Edge | null {
    const other = OPPOSITE[side];
    return settle(
      this.design.rules,
      drawn(first.lines[side]),
      first.sources[side] ?? -2,
      drawn(second.lines[other]),
      second.sources[other] ?? -2,
    );
  }

  /** A cell's side before the cell beside it has its say, and where among the parts it came from. */
  side(row: number, col: number, side: Side): [Edge | null, number] {
    const raw = this.raw(row, col);
    return [drawn(raw.lines[side]), raw.sources[side] ?? -2];
  }

  cell(row: number, col: number): Designed {
    const raw = this.raw(row, col);
    const edges = {} as Designed['edges'];
    for (const [side, [, dr, dc]] of Object.entries(SIDES) as [Side, [Region, number, number]][]) {
      const [r, c] = [row + dr, col + dc];
      if (this.design.spacing || !this.inside(r, c)) edges[side] = drawn(raw.lines[side]);
      else if (side === 'bottom' || side === 'right')
        edges[side] = this.settled(raw, side, this.raw(r, c));
      else edges[side] = this.settled(this.raw(r, c), OPPOSITE[side], raw);
    }
    return { ...raw.cell, edges };
  }
}

/** Where a design lies over a table, by row and col from 0; null where its ends are gone. */
export function areaOf(design: Design, lines: Lines): [number, number, number, number] | null {
  const given = design.area;
  if (!given) return [0, 0, lines.rowCount - 1, lines.cols.length - 1];
  const [top, left] = given.from.split(':');
  const [bottom, right] = given.to.split(':');
  const found = [
    lines.rowIndex(top),
    lines.colIndex(left),
    lines.rowIndex(bottom),
    lines.colIndex(right),
  ];
  return found.includes(-1) ? null : (found as [number, number, number, number]);
}

const EMPTY: Designed = {
  parts: [],
  fill: null,
  marks: {},
  caps: null,
  align: null,
  valign: null,
  edges: { top: null, bottom: null, left: null, right: null },
};

/** A table as its designs draw it, each over its area, a later one over an earlier, with the edges
 * its cells keep over them. An edge two cells under one design share is settled by its rules; one
 * between two designs, or beside a cell under none, by the rules of the table's first design,
 * Word's in a table without one (designs.py, laid). */
export class TableDesign {
  private readonly laid: { resolver: Resolver; top: number; left: number }[] = [];
  private readonly rules: Rules;
  private readonly rows: number;
  private readonly cols: number;

  constructor(
    readonly designs: readonly Design[],
    lines: Lines,
    private readonly own: (row: number, col: number) => Edges | undefined,
  ) {
    this.rules = designs[0]?.rules ?? 'word';
    this.rows = lines.rowCount;
    this.cols = lines.cols.length;
    for (const design of designs) {
      const area = areaOf(design, lines);
      if (!area) continue;
      const [top, left, bottom, right] = area;
      const resolver = new Resolver(design, bottom - top + 1, right - left + 1, (row, col) =>
        own(top + row, left + col),
      );
      this.laid.push({ resolver, top, left });
    }
  }

  /** The design over the whole table, which its ground and shadow come from. */
  get whole(): Design | null {
    return this.designs.find((design) => !design.area) ?? null;
  }

  get lined(): boolean {
    return this.laid.some(({ resolver: { design } }) => design.parts || design.lines);
  }

  private under(row: number, col: number): number {
    for (let at = this.laid.length - 1; at >= 0; at--) {
      const { resolver, top, left } = this.laid[at];
      const [r, c] = [row - top, col - left];
      if (r >= 0 && c >= 0 && r < resolver.rows && c < resolver.cols) return at;
    }
    return -1;
  }

  private side(under: number, row: number, col: number, side: Side): [Edge | null, number] {
    if (under < 0) {
      const mine = this.own(row, col);
      return mine && side in mine
        ? [drawn(mine[side]), RULES[this.rules].order.length]
        : [null, -2];
    }
    const { resolver, top, left } = this.laid[under];
    return resolver.side(row - top, col - left, side);
  }

  private apart(under: number): boolean {
    return under >= 0 && !!this.laid[under].resolver.design.spacing;
  }

  at(row: number, col: number): Designed {
    const under = this.under(row, col);
    let found = EMPTY;
    if (under >= 0) {
      const { resolver, top, left } = this.laid[under];
      found = resolver.cell(row - top, col - left);
    } else {
      const mine = this.own(row, col);
      if (mine) {
        const edges = { ...EMPTY.edges };
        for (const side of Object.keys(mine) as Side[]) edges[side] = drawn(mine[side]);
        found = { ...EMPTY, edges };
      }
    }
    let edges: Designed['edges'] | null = null;
    for (const [side, [, dr, dc]] of Object.entries(SIDES) as [Side, [Region, number, number]][]) {
      const [r, c] = [row + dr, col + dc];
      if (r < 0 || c < 0 || r >= this.rows || c >= this.cols) continue;
      const there = this.under(r, c);
      if ((there === under && under >= 0) || this.apart(under) || this.apart(there)) continue;
      const [a, from] = this.side(under, row, col, side);
      const [b, to] = this.side(there, r, c, OPPOSITE[side]);
      const upper = side === 'bottom' || side === 'right';
      edges ??= { ...found.edges };
      edges[side] = upper ? settle(this.rules, a, from, b, to) : settle(this.rules, b, to, a, from);
    }
    return edges ? { ...found, edges } : found;
  }
}

/** The designs a table carries, where it carries any its rules are known for. */
export function designsIn(value: unknown): Design[] | null {
  if (!Array.isArray(value) || !value.length) return null;
  const known = value.every(
    (each) => typeof each === 'object' && each !== null && Object.hasOwn(RULES, each.rules),
  );
  return known ? (value as Design[]) : null;
}

/** A table's designs, with the edges each slot keeps over them: its cell's own, only the outer
 * sides of a merged one, else the look its row or its column gives a light cell. */
export function designOf(
  table: Node,
  layout: Layout,
  look?: (row: string, col: string) => Look | undefined,
): TableDesign {
  const own = (row: number, col: number): Edges | undefined => {
    const placed = layout.at(row, col);
    const id = placed ? layout.grid.rowId(placed.row) : undefined;
    if (!placed || id === undefined) return undefined;
    const edges: Edges | null | undefined = placed.node
      ? placed.node.attrs.edges
      : look?.(id, layout.grid.cols[placed.col])?.edges;
    if (!edges || (placed.rows === 1 && placed.cols === 1)) return edges ?? undefined;
    const outer: Record<Side, boolean> = {
      top: row === placed.row,
      bottom: row === placed.row + placed.rows - 1,
      left: col === placed.col,
      right: col === placed.col + placed.cols - 1,
    };
    const kept = Object.entries(edges).filter(([side]) => outer[side as Side]);
    return kept.length ? Object.fromEntries(kept) : undefined;
  };
  return new TableDesign(designsIn(table.attrs.designs) ?? [], layout.grid, own);
}

function shown(swatch: Swatch, paper: boolean): string {
  return paper ? swatch.light : onScreen(swatch);
}

/** A tint as the page shows it, or paper where another program reads it: a palette's highlight by
 * its name, or a file's own, with its alpha where it has one; transparent for none, which shows
 * what is beneath. */
export function tintOf(tint: string | null | undefined, paper = false): string | null {
  return tinted(HIGHLIGHTS, tint, paper);
}

function tinted(palette: Palette, tint: string | null | undefined, paper: boolean): string | null {
  if (!tint) return null;
  if (tint === 'none') return 'transparent';
  const alpha = /^#[0-9a-f]{8}$/.test(tint) ? tint.slice(7) : '';
  const swatch = swatchOf(palette, alpha ? tint.slice(0, 7) : tint);
  if (!swatch) return null;
  return shown(alpha ? { light: swatch.light + alpha, dark: swatch.dark + alpha } : swatch, paper);
}

/** A table's ground as CSS: its tint, or its gradient. */
export function backgroundOf(ground: Design['background'], paper = false): string | null {
  if (!ground || typeof ground === 'string') return tintOf(ground, paper);
  const stops = ground.stops.map(
    ({ at, color }) => `${tintOf(color, paper) ?? 'transparent'} ${at}%`,
  );
  return `linear-gradient(${(ground.angle + 90) % 360}deg, ${stops.join(', ')})`;
}

/** Where a gradient at an angle clockwise from the right runs across a box, from and to the
 * corners its ends pass through, as CSS runs it. */
export function gradientLine(
  angle: number,
  box: { x: number; y: number; width: number; height: number },
): [number, number, number, number] {
  const turned = (angle * Math.PI) / 180;
  const [dx, dy] = [Math.cos(turned), Math.sin(turned)];
  const half = (Math.abs(box.width * dx) + Math.abs(box.height * dy)) / 2;
  const [x, y] = [box.x + box.width / 2, box.y + box.height / 2];
  return [x - dx * half, y - dy * half, x + dx * half, y + dy * half];
}

/** A table's shadow as a CSS box shadow. */
export function shadowOf(shadow: Design['shadow'], paper = false): string | null {
  const color = shadow && tinted(TEXT_COLORS, shadow.color, paper);
  if (!shadow || !color) return null;
  const turned = (shadow.angle * Math.PI) / 180;
  const [x, y] = [Math.cos(turned), Math.sin(turned)].map(
    (each) => Math.round(each * shadow.distance * 100) / 100,
  );
  return `${x}pt ${y}pt ${shadow.blur}pt ${color}`;
}

/** A line's colour as the page shows it: the text's where it names none. */
export function inkOf(edge: Edge, paper = false): string {
  const swatch = edge.color ? swatchOf(TEXT_COLORS, edge.color) : null;
  return swatch ? shown(swatch, paper) : paper ? '#000000' : 'currentColor';
}

const DOUBLED = /^(double|triple|thinThick|thickThin)/;
const DASHES: Record<string, number[]> = {
  dotted: [1, 1],
  dashed: [4, 2],
  dashSmallGap: [3, 1],
  dotDash: [4, 2, 1, 2],
  dashDotStroked: [4, 2, 1, 2],
  slantDashDot: [4, 2, 1, 2],
  dotDotDash: [4, 2, 1, 2, 1, 2],
};
const RAISED: Record<string, string> = {
  threeDEmboss: 'ridge',
  threeDEngrave: 'groove',
  outset: 'outset',
  inset: 'inset',
};
/** The narrowest a doubled line draws in points, its two strokes and the gap a pixel each. */
const DOUBLED_LEAST = 2.25;

/** How a line draws: its style in CSS, whether it is two strokes, its dashes in widths of a
 * stroke, and its whole width in points. */
export function strokeOf(edge: Edge): {
  style: string;
  doubled: boolean;
  dashes: number[];
  width: number;
} {
  const doubled = DOUBLED.test(edge.line) || edge.line === 'doubleWave';
  const dashes = DASHES[edge.line] ?? [];
  const style = doubled
    ? 'double'
    : (RAISED[edge.line] ??
      (edge.line === 'dotted' ? 'dotted' : dashes.length ? 'dashed' : 'solid'));
  return {
    style,
    doubled,
    dashes,
    width: doubled ? Math.max(edge.width, DOUBLED_LEAST) : edge.width,
  };
}

/** A line as a CSS border; none where there is none. */
export function borderOf(edge: Edge | null, paper = false): string {
  if (!edge) return 'none';
  const { style, width } = strokeOf(edge);
  return `${width}pt ${style} ${inkOf(edge, paper)}`;
}

/** The styles of a table whose cells Word sets apart: the gap between them and round them, and
 * the frame round the table, the only place its design's outer lines are drawn; none where they
 * touch. */
export function apartOf(design: Design | null, paper = false): Record<string, string> {
  if (!design?.spacing) return {};
  const lines = design.lines ?? {};
  return {
    'border-collapse': 'separate',
    'border-spacing': `${design.spacing * 2}pt`,
    'border-top': borderOf(drawn(lines.top), paper),
    'border-left': borderOf(drawn(lines.left), paper),
    'border-bottom': borderOf(drawn(lines.bottom), paper),
    'border-right': borderOf(drawn(lines.right), paper),
  };
}

/** A cell's design as styles of the element it is drawn in: its marks, capitals and alignment. */
export function dressOf(cell: Designed, paper = false): Record<string, string> {
  const style: Record<string, string> = {};
  const { marks } = cell;
  if (marks.strong) style['font-weight'] = 'bold';
  if (marks.em) style['font-style'] = 'italic';
  const lines = [marks.underline && 'underline', marks.strike && 'line-through'].filter(Boolean);
  if (lines.length) style['text-decoration-line'] = lines.join(' ');
  const color = marks.color && swatchOf(TEXT_COLORS, marks.color.color);
  if (color) style.color = shown(color, paper);
  const family = marks.font && substitute(String(marks.font.family));
  const stack = family && fontStack(family);
  if (stack) style['font-family'] = stack;
  const pt = Number(marks.size?.pt);
  if (pt > 0) style['font-size'] = `${pt}pt`;
  if (cell.caps === 'all') style['text-transform'] = 'uppercase';
  if (cell.caps === 'small') style['font-variant-caps'] = 'small-caps';
  if (cell.align) style['text-align'] = cell.align;
  return style;
}
