import * as Y from 'yjs';
import { shortId } from './blocks';
import type { Value } from './formulas';
import type { Edges } from './design';

export type Attrs = Record<string, unknown>;

/** The look of a light cell: the marks over all of its text, its paragraph's attributes and the
 * colour it is filled with. */
export interface Look {
  marks?: Record<string, Attrs | null>;
  attrs?: Attrs;
  fill?: string;
  edges?: Edges;
}

/** A cell as the server sends it (D16): what was typed into a light cell, its formula as text in
 * the canonical form, its number format, its look and, merged, the slot it reaches ("row:col"). */
export interface Shown {
  text?: string;
  formula?: string;
  format?: string;
  look?: Look;
  to?: string;
}

/** A row's cells and the values the server computed for them, by column id. */
export interface Held {
  cells: Record<string, Shown>;
  values: Record<string, Value>;
}

/** A cell as it comes over the wire: its look by its key among the document's looks, which the
 * server sends once, before the first message that names it. */
type Sent = Omit<Shown, 'look'> & { look?: string };

interface SentHeld {
  cells: Record<string, Sent>;
  values: Record<string, Value>;
}

type Axis = 'rows' | 'cols';

/** The places of rows from the first to the last, both included. */
export type Span = readonly [number, number];

/** The places from the first to the last. */
export function placesOf(first: number, last: number): number[] {
  return Array.from({ length: Math.max(0, last - first + 1) }, (_, at) => first + at);
}

/** One condition of a user's filter of a table, of one column: the texts it lets through, the
 * case not counting, an empty one for an empty cell; or a comparison with a value. */
export type Condition =
  { col: string; values: string[] } | { col: string; op: ConditionOp; value: string };

export type ConditionOp =
  | 'equals'
  | 'notEquals'
  | 'begins'
  | 'ends'
  | 'contains'
  | 'notContains'
  | 'greater'
  | 'greaterEqual'
  | 'less'
  | 'lessEqual';

/** The texts a column shows in the rows the other conditions let through, each with how many
 * rows show it, and whether there are more. */
export interface Offered {
  values: [string, number][];
  more: boolean;
}

/** A grid without its rows, as the server sends it before the browser asks for those it shows:
 * how many it has, and where each row the outline names stands. Where it shows only some of the
 * table's rows, those not hidden that the user's filter lets through, it counts only those and
 * gives each row it places its own place among all of them as its number. */
export interface Outline {
  table: string;
  name: string;
  cols: [string, number | null][];
  rows: number;
  at: Record<string, number>;
  numbers?: Record<string, number>;
  filter?: Condition[];
  heights: Record<string, number>;
  /** The keys of the looks of the rows and the columns that have one, which their cells
   * without a look of their own show: a row's before its column's. */
  looks: Partial<Record<Axis, Record<string, string>>>;
  /** The columns hidden from view. */
  hidden: { cols?: string[] };
  merges: Record<string, string>;
  /** The last of the rows that stay at the top of the view, none where none do. */
  frozen: string | null;
}

/** An outline with every row in order and its cells: a version's, or a document's for print. */
export interface Whole extends Outline {
  ids: string[];
  cells: Record<string, SentHeld>;
}

/** Whole grids as the server answers for them, with the looks their cells and lines name. */
export interface Wholes {
  grids: Whole[];
  looks: Record<string, Look>;
}

/** Lines taken out by where they stood, reordered from where the first of them stands once those
 * are out, and put in by where they stand after, each with its size and its look. */
interface Lines {
  out?: number[];
  order?: [number, string[]];
  put?: [string, number, number | null, string | null][];
}

interface Patch {
  table: string;
  gone?: true;
  made?: Outline;
  laid?: Outline;
  tab?: string | null;
  name?: string;
  frozen?: string | null;
  rows?: Lines;
  cols?: Lines;
  widths?: Record<string, number | null>;
  heights?: Record<string, number | null>;
  looks?: Partial<Record<Axis, Record<string, string | null>>>;
  hidden?: { cols?: Record<string, boolean> };
  merges?: Record<string, string | null>;
  at?: Record<string, number>;
  numbers?: Record<string, number>;
  cells?: Record<string, Record<string, Sent | null>>;
  values?: Record<string, Record<string, Value>>;
}

/** A table of the document, which a formula can name where it has a name, with its size and the
 * tab it stands in, null for a header's or a footer's; `only` where no other table stands there. */
export interface Named {
  table: string;
  name: string;
  rows: number;
  cols: number;
  tab: string | null;
  only: boolean;
}

/** Where a defined name leads: the table and the address of the cells it stands for. */
export interface Where {
  table: string;
  address: string;
}

/** What changed in a table: its lines, sizes, name, merges or frozen rows, or only the cells of
 * `rows`, all of them where null; `gone` once the table is. */
export interface Change {
  table: string;
  outline: boolean;
  rows: ReadonlySet<string> | null;
  gone?: boolean;
}

type Listener = (change: Change) => void;

/** Cells of a table written by an edit, by "row:col": what each now holds, none where emptied. */
export interface Written {
  table: string;
  cells: Map<string, Shown | null>;
}

export function keyOf(row: string, col: string): string {
  return `${row}:${col}`;
}

/** The looks of a document by their keys, as the server sent them. */
export type Looks = ReadonlyMap<string, Look>;

/** A table's grid as the browser holds it: its columns in order, how many rows it has and where
 * those it knows stand, each line's size and look, those hidden, the merged cells, and the cells
 * of the rows it asked for. A cell written here shows at once, until the server says it was done
 * or refused. */
export class Grid {
  readonly table: string;
  tab: string | null;
  name: string;
  cols: string[] = [];
  widths = new Map<string, number>();
  rowCount = 0;
  heights = new Map<string, number>();
  readonly lineLooks: Record<Axis, Map<string, Look>> = { rows: new Map(), cols: new Map() };
  readonly hidden = { cols: new Set<string>() };
  merges = new Map<string, string>();
  frozen: string | null = null;
  /** Whether the browser is shown every row, which then stands at its own place. */
  plain = true;
  filter: readonly Condition[] = [];
  held = new Map<string, Held>();
  /** Cells written and not yet answered, by "row:col": what they now hold, none where emptied. */
  readonly written = new Map<string, { token: string; cell: Shown | null }>();
  /** The rows the browser knows where they stand, both ways: those it holds and those its
   * outline names. */
  private ids = new Map<number, string>();
  private places = new Map<string, number>();
  private numbers = new Map<string, number>();
  private colAt: Map<string, number> | null = null;
  /** Each cell without a look of its own as it shows the look of its line, made once per look. */
  private inheriting = new WeakMap<Shown, [Look, Shown]>();
  private bare = new WeakMap<Look, Shown>();

  constructor(
    outline: Outline,
    tab: string | null,
    private looks: Looks,
  ) {
    this.table = outline.table;
    this.tab = tab;
    this.name = outline.name;
    this.outline(outline);
  }

  outline(outline: Outline): void {
    this.name = outline.name;
    this.cols = outline.cols.map(([id]) => id);
    this.widths = new Map(outline.cols.filter(([, width]) => width !== null) as [string, number][]);
    this.rowCount = outline.rows;
    this.plain = outline.numbers === undefined;
    this.filter = outline.filter ?? [];
    this.ids.clear();
    this.places.clear();
    this.numbers.clear();
    this.place(outline.at, outline.numbers);
    this.heights = new Map(Object.entries(outline.heights));
    for (const axis of ['rows', 'cols'] as const) {
      this.lineLooks[axis] = new Map(
        Object.entries(outline.looks[axis] ?? {}).map(([id, key]) => [id, this.look(key)]),
      );
    }
    this.hidden.cols = new Set(outline.hidden.cols);
    this.merges = new Map(Object.entries(outline.merges));
    this.frozen = outline.frozen;
    this.colAt = null;
  }

  /** Learns where the rows stand, and their numbers where given. */
  place(at: Record<string, number>, numbers?: Record<string, number>): void {
    for (const [id, number] of Object.entries(numbers ?? {})) this.numbers.set(id, number);
    for (const [id, index] of Object.entries(at)) {
      const was = this.places.get(id);
      if (was !== undefined && this.ids.get(was) === id) this.ids.delete(was);
      const other = this.ids.get(index);
      if (other !== undefined) this.places.delete(other);
      this.ids.set(index, id);
      this.places.set(id, index);
    }
  }

  /** Learns every row in order, as a grid held whole has them. */
  placeAll(ids: readonly string[]): void {
    this.place(Object.fromEntries(ids.map((id, index) => [id, index])));
  }

  private look(key: string): Look {
    const look = this.looks.get(key);
    if (!look) throw new Error(`grid ${this.table}: no look ${key}`);
    return look;
  }

  private decoded(cell: Sent): Shown {
    return cell.look === undefined ? (cell as Shown) : { ...cell, look: this.look(cell.look) };
  }

  /** Holds the row's cells as the server sent them. */
  hold(row: string, held: SentHeld): void {
    const cells: Record<string, Shown> = {};
    for (const [col, cell] of Object.entries(held.cells)) cells[col] = this.decoded(cell);
    this.held.set(row, { cells, values: held.values });
  }

  /** How many rows stay at the top of the view. */
  frozenRows(): number {
    return this.frozen === null ? 0 : this.rowIndex(this.frozen) + 1;
  }

  /** The id of the row standing there, where the browser knows it. */
  rowId(index: number): string | undefined {
    return this.ids.get(index);
  }

  /** The row's own place among all the table's rows, which its header and its address show,
   * where the browser knows it. */
  rowNumber(index: number): number | undefined {
    if (this.plain) return index;
    const id = this.ids.get(index);
    return id === undefined ? undefined : this.numbers.get(id);
  }

  rowIndex(id: string): number {
    return this.places.get(id) ?? -1;
  }

  colIndex(id: string): number {
    this.colAt ??= new Map(this.cols.map((col, index) => [col, index]));
    return this.colAt.get(id) ?? -1;
  }

  holds(row: string): boolean {
    return this.held.has(row);
  }

  /** Whether the browser holds every row from the first place to the last. */
  holdsSpan(first: number, last: number): boolean {
    for (let index = first; index <= last; index++) {
      const id = this.ids.get(index);
      if (id === undefined || !this.held.has(id)) return false;
    }
    return true;
  }

  /** The cell as it shows: with its own look, else its row's, else its column's. */
  cell(row: string, col: string): Shown | undefined {
    const written = this.written.get(keyOf(row, col));
    const held = this.held.get(row);
    const cell = written ? (written.cell ?? undefined) : held?.cells[col];
    if (cell?.look || (!written && !held)) return cell;
    const look = this.lineLooks.rows.get(row) ?? this.lineLooks.cols.get(col);
    if (!look) return cell;
    if (!cell) {
      let found = this.bare.get(look);
      if (!found) this.bare.set(look, (found = { look }));
      return found;
    }
    const kept = this.inheriting.get(cell);
    if (kept?.[0] === look) return kept[1];
    const found = { ...cell, look };
    this.inheriting.set(cell, [look, found]);
    return found;
  }

  /** What the server computed the cell shows; none while a write to it waits for its answer. */
  value(row: string, col: string): Value | undefined {
    if (this.written.has(keyOf(row, col))) return undefined;
    return this.held.get(row)?.values[col];
  }

  /** Applies a patch as the server applied it to its grid: lines taken out where they stood,
   * reordered from where the first of them stands between and put in where they stand after;
   * then where the rows it names stand, sizes, merges and cells. */
  apply(patch: Patch): Change {
    let outline = false;
    const rows = new Set<string>();
    if (patch.name !== undefined) {
      this.name = patch.name;
      outline = true;
    }
    if (patch.frozen !== undefined) {
      this.frozen = patch.frozen;
      outline = true;
    }
    for (const axis of ['rows', 'cols'] as const) {
      const lines = patch[axis];
      if (!lines) continue;
      outline = true;
      const gone = axis === 'rows' ? this.unrow(lines) : this.uncol(lines);
      const sizes = axis === 'rows' ? this.heights : this.widths;
      for (const id of gone) {
        sizes.delete(id);
        this.lineLooks[axis].delete(id);
        if (axis === 'cols') this.hidden.cols.delete(id);
      }
      for (const key of [...this.merges.keys()]) {
        const [row, col] = key.split(':');
        if (gone.has(axis === 'rows' ? row : col)) this.merges.delete(key);
      }
      if (axis === 'rows') {
        for (const id of gone) this.held.delete(id);
      } else {
        for (const held of this.held.values()) {
          for (const id of gone) {
            delete held.cells[id];
            delete held.values[id];
          }
        }
      }
      for (const [id, , size, look] of lines.put ?? []) {
        if (size !== null) sizes.set(id, size);
        if (look !== null) this.lineLooks[axis].set(id, this.look(look));
      }
    }
    if (patch.at) this.place(patch.at, patch.numbers);
    for (const [sizes, given] of [
      [this.widths, patch.widths],
      [this.heights, patch.heights],
    ] as const) {
      if (!given) continue;
      outline = true;
      for (const [id, size] of Object.entries(given)) {
        if (size === null) sizes.delete(id);
        else sizes.set(id, size);
      }
    }
    for (const axis of ['rows', 'cols'] as const) {
      const given = patch.looks?.[axis];
      if (!given) continue;
      outline = true;
      for (const [id, key] of Object.entries(given)) {
        if (key === null) this.lineLooks[axis].delete(id);
        else this.lineLooks[axis].set(id, this.look(key));
      }
    }
    if (patch.hidden?.cols) {
      outline = true;
      for (const [id, hidden] of Object.entries(patch.hidden.cols)) {
        if (hidden) this.hidden.cols.add(id);
        else this.hidden.cols.delete(id);
      }
    }
    if (patch.merges) {
      outline = true;
      for (const [key, to] of Object.entries(patch.merges)) {
        if (to === null) this.merges.delete(key);
        else this.merges.set(key, to);
      }
    }
    for (const [row, cols] of Object.entries(patch.cells ?? {})) {
      const held = this.held.get(row);
      if (!held) continue;
      rows.add(row);
      for (const [col, cell] of Object.entries(cols)) {
        if (cell) held.cells[col] = this.decoded(cell);
        else delete held.cells[col];
      }
    }
    for (const [row, values] of Object.entries(patch.values ?? {})) {
      const held = this.held.get(row);
      if (!held) continue;
      rows.add(row);
      held.values = values;
    }
    return { table: this.table, outline, rows: outline ? null : rows };
  }

  /** Moves the rows the browser knows as the lines change, and returns those taken out. */
  private unrow(lines: Lines): Set<string> {
    const out = lines.out ?? [];
    const put = lines.put ?? [];
    const gone = new Set<string>();
    let kept: [number, string][] = [];
    for (const [index, id] of this.ids) {
      const at = lowerBound(out, index);
      if (out[at] === index) gone.add(id);
      else kept.push([index - at, id]);
    }
    if (lines.order) {
      const [first, order] = lines.order;
      const moved = new Set(order);
      const last = first + order.length;
      kept = kept.filter(([index, id]) => !moved.has(id) && (index < first || index >= last));
      kept.push(...order.map((id, at): [number, string] => [first + at, id]));
    }
    kept.sort((a, b) => a[0] - b[0]);
    this.ids.clear();
    this.places.clear();
    let next = 0;
    for (const [index, id] of kept) {
      while (next < put.length && put[next][1] <= index + next) next++;
      this.ids.set(index + next, id);
      this.places.set(id, index + next);
    }
    for (const [id, index] of put) {
      this.ids.set(index, id);
      this.places.set(id, index);
    }
    this.rowCount += put.length - out.length;
    return gone;
  }

  /** Moves the columns as the lines change, and returns those taken out. */
  private uncol(lines: Lines): Set<string> {
    const out = new Set(lines.out ?? []);
    const gone = new Set(this.cols.filter((_, index) => out.has(index)));
    const cols = this.cols.filter((_, index) => !out.has(index));
    if (lines.order) {
      const [first, order] = lines.order;
      cols.splice(first, order.length, ...order);
    }
    for (const [id, index] of lines.put ?? []) cols.splice(index, 0, id);
    this.cols = cols;
    this.colAt = null;
    return gone;
  }
}

/** Where the first of the sorted numbers stands that is not below the one given. */
function lowerBound(sorted: readonly number[], value: number): number {
  let low = 0;
  let high = sorted.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (sorted[middle] < value) low = middle + 1;
    else high = middle;
  }
  return low;
}

/** Where the grids a table view shows come from: the server, live, or a version's whole grids. */
export interface GridSource {
  readonly live: boolean;
  grid(table: string): Grid | undefined;
  tables(): Iterable<Grid>;
  subscribe(table: string | null, listener: Listener): () => void;
  /** The rows `owner` shows of the table, by the spans of their places, which the source holds
   * for it. */
  show(owner: object, table: string, spans: readonly Span[]): void;
  /** Lets go of everything `owner` showed. */
  forget(owner: object): void;
  /** Whether a formula or a defined name refers to the table by its name, which it must then
   * keep. */
  referred(table: string): Promise<boolean>;
  /** The table of the document a formula names so, whatever the case it is written in. */
  named(name: string): Named | null;
  /** The defined name in force in the table, as it was given, whatever the case it is written
   * in. */
  defined(name: string, table: string): string | null;
  /** The table of the document by its id. */
  table(table: string): Named | null;
  /** Where the defined name in force in the table leads, null where it stands for no cells. */
  where(name: string, table: string | null): Promise<Where | null>;
  /** The ids of the rows standing at the places, which the table must have. */
  rowIds(table: string, places: readonly number[]): Promise<string[]>;
  /** Where the rows of the ids stand, -1 for one gone. */
  rowPlaces(table: string, rows: readonly string[]): Promise<number[]>;
  /** Where the rows stand whose own places among all the table's rows are the numbers, -1 for
   * one not shown or past the table's last. */
  numberedPlaces(table: string, numbers: readonly number[]): Promise<number[]>;
  /** The ids of the rows whose own places are the numbers, null for one past the last. */
  numberedRows(table: string, numbers: readonly number[]): Promise<(string | null)[]>;
  /** Keeps the user's filter of the table, none where no condition is given. */
  filter(table: string, conditions: readonly Condition[]): Promise<void>;
  /** The texts the column shows in the rows the other conditions of the filter let through. */
  offered(table: string, col: string): Promise<Offered>;
}

export function folded(name: string): string {
  return name.toUpperCase();
}

class Listeners {
  private all = new Map<string | null, Set<Listener>>();

  add(table: string | null, listener: Listener): () => void {
    let set = this.all.get(table);
    if (!set) this.all.set(table, (set = new Set()));
    set.add(listener);
    return () => set.delete(listener);
  }

  tell(change: Change): void {
    for (const listener of [...(this.all.get(change.table) ?? []), ...(this.all.get(null) ?? [])])
      listener(change);
  }
}

/** Grids held whole, which nobody edits: a version's, or what print reads. */
export class WholeGrids implements GridSource {
  readonly live = false;
  protected grids = new Map<string, Grid>();
  protected listeners = new Listeners();
  protected looks = new Map<string, Look>();

  constructor(...wholes: readonly Wholes[]) {
    this.reset(...wholes);
  }

  reset(...wholes: readonly Wholes[]): void {
    const gone = new Set(this.grids.keys());
    this.looks = new Map(wholes.flatMap((each) => Object.entries(each.looks)));
    this.grids = new Map(
      wholes
        .flatMap((each) => each.grids)
        .map((whole) => {
          const grid = new Grid(whole, null, this.looks);
          grid.placeAll(whole.ids);
          for (const [row, held] of Object.entries(whole.cells)) grid.hold(row, held);
          return [whole.table, grid];
        }),
    );
    for (const table of new Set([...gone, ...this.grids.keys()])) {
      this.listeners.tell({ table, outline: true, rows: null, gone: !this.grids.has(table) });
    }
  }

  grid(table: string): Grid | undefined {
    return this.grids.get(table);
  }

  tables(): Iterable<Grid> {
    return this.grids.values();
  }

  subscribe(table: string | null, listener: Listener): () => void {
    return this.listeners.add(table, listener);
  }

  show(_owner: object, _table: string, _spans: readonly Span[]): void {}

  forget(_owner: object): void {}

  referred(table: string): Promise<boolean> {
    return Promise.reject(new Refusal('read_only', table));
  }

  named(name: string): Named | null {
    for (const grid of this.grids.values()) {
      if (grid.name && folded(grid.name) === folded(name)) return this.table(grid.table);
    }
    return null;
  }

  table(table: string): Named | null {
    const grid = this.grids.get(table);
    if (!grid) return null;
    const { name, rowCount, cols, tab } = grid;
    const only = ![...this.grids.values()].some((each) => each !== grid && each.tab === tab);
    return { table, name, rows: rowCount, cols: cols.length, tab, only };
  }

  defined(): string | null {
    return null;
  }

  where(): Promise<Where | null> {
    return Promise.resolve(null);
  }

  rowIds(table: string, places: readonly number[]): Promise<string[]> {
    const grid = this.grids.get(table);
    return grid
      ? Promise.resolve(idsAt(grid, places))
      : Promise.reject(new Refusal('no_table', table));
  }

  rowPlaces(table: string, rows: readonly string[]): Promise<number[]> {
    const grid = this.grids.get(table);
    return grid
      ? Promise.resolve(rows.map((row) => grid.rowIndex(row)))
      : Promise.reject(new Refusal('no_table', table));
  }

  numberedPlaces(table: string, numbers: readonly number[]): Promise<number[]> {
    const grid = this.grids.get(table);
    if (!grid) return Promise.reject(new Refusal('no_table', table));
    const places = new Map<number, number>();
    for (let index = 0; index < grid.rowCount; index++) places.set(grid.rowNumber(index)!, index);
    return Promise.resolve(numbers.map((number) => places.get(number) ?? -1));
  }

  async numberedRows(table: string, numbers: readonly number[]): Promise<(string | null)[]> {
    const places = await this.numberedPlaces(table, numbers);
    const grid = this.grids.get(table)!;
    return places.map((place) => grid.rowId(place) ?? null);
  }

  filter(table: string): Promise<void> {
    return Promise.reject(new Refusal('read_only', table));
  }

  offered(table: string): Promise<Offered> {
    return Promise.reject(new Refusal('read_only', table));
  }
}

/** The spans every owner shows of the table, joined where they meet. */
function wantedSpans(
  shown: Iterable<Map<string, readonly Span[]>>,
  table: string,
): [number, number][] {
  const spans = [...shown]
    .flatMap((tables) => tables.get(table) ?? [])
    .filter(([first, last]) => first <= last)
    .sort((a, b) => a[0] - b[0]);
  const joined: [number, number][] = [];
  for (const [first, last] of spans) {
    const end = joined.at(-1);
    if (end && first <= end[1] + 1) end[1] = Math.max(end[1], last);
    else joined.push([first, last]);
  }
  return joined;
}

/** The outlines of a version's grids, without their rows. */
export interface KeptOutlines {
  grids: Outline[];
  looks: Record<string, Look>;
}

interface KeptRows {
  at: Record<string, number>;
  numbers?: Record<string, number>;
  rows: Record<string, SentHeld>;
  looks: Record<string, Look>;
}

interface KeptStanding {
  places: Record<string, string>;
  rows: Record<string, number>;
  numbered: Record<string, number>;
}

/** How many places or ids one question about where rows stand names. */
const STANDING_AT_ONCE = 500;

/** A version's grids, which nobody edits, the rows its views show read as they come into view;
 * `read` asks the version's address. */
export class KeptGrids extends WholeGrids {
  private shown = new Map<object, Map<string, readonly Span[]>>();
  private asked = new Map<string, string>();
  private asking = new Set<string>();

  constructor(
    outlines: KeptOutlines,
    private read: (path: string) => Promise<unknown>,
  ) {
    super({
      grids: outlines.grids.map((outline) => ({ ...outline, ids: [], cells: {} })),
      looks: outlines.looks,
    });
  }

  override show(owner: object, table: string, spans: readonly Span[]): void {
    let tables = this.shown.get(owner);
    if (!tables) this.shown.set(owner, (tables = new Map()));
    tables.set(table, spans);
    this.ask(table);
  }

  override forget(owner: object): void {
    const tables = this.shown.get(owner);
    if (!tables) return;
    this.shown.delete(owner);
    for (const table of tables.keys()) this.ask(table);
  }

  private ask(table: string): void {
    if (this.asking.size === 0) {
      queueMicrotask(() => {
        const tables = [...this.asking];
        this.asking.clear();
        for (const each of tables) this.fetchRows(each);
      });
    }
    this.asking.add(table);
  }

  private fetchRows(table: string): void {
    const grid = this.grids.get(table);
    if (!grid) return;
    const spans = wantedSpans(this.shown.values(), table);
    const given = spans.map(([first, last]) => `${first}-${last}`).join(',');
    if ((this.asked.get(table) ?? '') === given) return;
    this.asked.set(table, given);
    if (!given) {
      this.received(grid, given, { at: {}, rows: {}, looks: {} });
      return;
    }
    const query = new URLSearchParams({ table, spans: given });
    void this.read(`rows?${query}`).then((found) => {
      this.received(grid, given, found as KeptRows);
    });
  }

  private received(grid: Grid, given: string, found: KeptRows): void {
    if (this.asked.get(grid.table) !== given) return;
    for (const [key, look] of Object.entries(found.looks)) this.looks.set(key, look);
    const rows = new Set<string>();
    for (const row of [...grid.held.keys()]) {
      if (row in found.at) continue;
      grid.held.delete(row);
      rows.add(row);
    }
    grid.place(found.at, found.numbers);
    for (const [row, held] of Object.entries(found.rows)) {
      grid.hold(row, held);
      rows.add(row);
    }
    if (rows.size) this.listeners.tell({ table: grid.table, outline: false, rows });
  }

  private async standing(
    table: string,
    part: 'places' | 'rows' | 'numbered',
    asked: readonly (number | string)[],
  ): Promise<KeptStanding> {
    const found: KeptStanding = { places: {}, rows: {}, numbered: {} };
    for (let at = 0; at < asked.length; at += STANDING_AT_ONCE) {
      const query = new URLSearchParams({
        table,
        [part]: asked.slice(at, at + STANDING_AT_ONCE).join(','),
      });
      const answer = (await this.read(`standing?${query}`)) as KeptStanding;
      Object.assign(found[part], answer[part]);
    }
    return found;
  }

  override async rowIds(table: string, places: readonly number[]): Promise<string[]> {
    const grid = this.grids.get(table);
    if (!grid) throw new Refusal('no_table', table);
    const missing = places.filter((place) => grid.rowId(place) === undefined);
    if (missing.length) {
      const { places: found } = await this.standing(table, 'places', missing);
      grid.place(Object.fromEntries(Object.entries(found).map(([at, id]) => [id, Number(at)])));
    }
    return idsAt(grid, places);
  }

  override async rowPlaces(table: string, rows: readonly string[]): Promise<number[]> {
    const grid = this.grids.get(table);
    if (!grid) throw new Refusal('no_table', table);
    const missing = rows.filter((row) => grid.rowIndex(row) === -1);
    if (missing.length) {
      const { rows: found } = await this.standing(table, 'rows', missing);
      grid.place(Object.fromEntries(Object.entries(found).filter(([, at]) => at >= 0)));
    }
    return rows.map((row) => grid.rowIndex(row));
  }

  override async numberedPlaces(table: string, numbers: readonly number[]): Promise<number[]> {
    const { numbered } = await this.standing(table, 'numbered', numbers);
    return numbers.map((number) => numbered[number] ?? -1);
  }

  override async numberedRows(
    table: string,
    numbers: readonly number[],
  ): Promise<(string | null)[]> {
    const places = await this.numberedPlaces(table, numbers);
    const known = places.filter((place) => place >= 0);
    const ids = await this.rowIds(table, known);
    const by = new Map(known.map((place, at) => [place, ids[at]!]));
    return places.map((place) => by.get(place) ?? null);
  }
}

function idsAt(grid: Grid, places: readonly number[]): string[] {
  return places.map((place) => {
    const id = grid.rowId(place);
    if (id === undefined) throw new Refusal('no_line', String(place));
    return id;
  });
}

/** Why the server refused an edit, for the one who made it. */
export class Refusal extends Error {
  constructor(
    readonly code: string,
    readonly detail: string | null,
  ) {
    super(detail ? `${code}: ${detail}` : code);
  }
}

interface Pending {
  message: Record<string, unknown>;
  done: () => void;
  refused: (refusal: Refusal) => void;
  /** Times the server answered that the room had not yet received what the edit comes after. */
  behind: number;
}

interface Question {
  message: Record<string, unknown>;
  waiting: { answer: (answer: never) => void; refused: (refusal: Refusal) => void }[];
}

/** Where the edit stands after the browser's own edits to a Yjs state: its client and clock. */
export function afterOf(doc: Y.Doc): [number, number] {
  return [doc.clientID, Y.getState(doc.store, doc.clientID)];
}

function gridsUrl(document: string): string {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${location.host}/api/grids/${document}`;
}

/** How long a refused "behind" edit waits before it is sent again, and how often it is. */
const BEHIND_RETRY = 1000;
const BEHIND_TRIES = 5;
const RECONNECT_FIRST = 500;
const RECONNECT_MOST = 10_000;

/** A document's grids over its grid socket (D16): the outlines of the tables of the tabs it
 * watches, the rows its views show, and edits as operations with a token each, which the server
 * orders. Lost, the socket opens again, watches again, asks for the rows again and sends again
 * what was not answered, which the server does once. */
export class GridClient implements GridSource {
  readonly live = true;
  private grids = new Map<string, Grid>();
  /** The tables a formula can name by their names in upper case, and the defined names, each
   * with the table it is in force in alone. */
  private index = new Map<string, Named>();
  private byId = new Map<string, Named>();
  private names: [string, string | null][] = [];
  private listeners = new Listeners();
  /** The looks the server sent, which it sends again over a socket opened again. */
  private looks = new Map<string, Look>();
  private watched = new Set<string | null>();
  /** The spans of rows each owner shows, by table, and the spans last asked for of each. */
  private shown = new Map<object, Map<string, readonly Span[]>>();
  private asked = new Map<string, string>();
  private pending = new Map<string, Pending>();
  private questions = new Map<string, Question>();
  private socket: WebSocket | null = null;
  private open = false;
  private closed = false;
  private wait = RECONNECT_FIRST;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private asking = new Set<string>();

  constructor(
    readonly document: string,
    private url: string = gridsUrl(document),
  ) {
    this.timer = setTimeout(() => this.connect());
  }

  private connect(): void {
    this.timer = null;
    if (this.closed) return;
    const socket = new WebSocket(this.url);
    this.socket = socket;
    socket.addEventListener('open', () => {
      if (this.socket !== socket) return;
      this.open = true;
      this.wait = RECONNECT_FIRST;
      for (const tab of this.watched) this.send({ type: 'watch', tab });
      for (const pending of this.pending.values()) this.send(pending.message);
      for (const question of this.questions.values()) this.send(question.message);
    });
    socket.addEventListener('message', (event) => {
      if (this.socket === socket) this.take(JSON.parse(event.data as string));
    });
    socket.addEventListener('close', ({ code }) => {
      if (this.socket !== socket) return;
      this.socket = null;
      this.open = false;
      // The server's refusal, as y-websocket reads it in the document's rooms: trying again
      // cannot help.
      if (code >= 4400 && code < 4500) this.close();
      if (this.closed) return;
      this.timer = setTimeout(() => this.connect(), this.wait);
      this.wait = Math.min(this.wait * 2, RECONNECT_MOST);
    });
  }

  close(): void {
    this.closed = true;
    this.open = false;
    if (this.timer) clearTimeout(this.timer);
    const socket = this.socket;
    this.socket = null;
    if (socket?.readyState === WebSocket.CONNECTING) {
      socket.addEventListener('open', () => socket.close(), { once: true });
    } else socket?.close();
    for (const pending of this.pending.values()) pending.refused(new Refusal('closed', null));
    this.pending.clear();
    for (const { waiting } of this.questions.values()) {
      for (const { refused } of waiting) refused(new Refusal('closed', null));
    }
    this.questions.clear();
  }

  private send(message: Record<string, unknown>): void {
    if (this.open) this.socket!.send(JSON.stringify(message));
  }

  /** Watches the tables of a tab, or of the document's headers and footers with null. */
  watch(tab: string | null): void {
    if (this.watched.has(tab)) return;
    this.watched.add(tab);
    this.send({ type: 'watch', tab });
  }

  grid(table: string): Grid | undefined {
    return this.grids.get(table);
  }

  tables(): Iterable<Grid> {
    return this.grids.values();
  }

  subscribe(table: string | null, listener: Listener): () => void {
    return this.listeners.add(table, listener);
  }

  show(owner: object, table: string, spans: readonly Span[]): void {
    let tables = this.shown.get(owner);
    if (!tables) this.shown.set(owner, (tables = new Map()));
    tables.set(table, spans);
    this.ask(table);
  }

  forget(owner: object): void {
    const tables = this.shown.get(owner);
    if (!tables) return;
    this.shown.delete(owner);
    for (const table of tables.keys()) this.ask(table);
  }

  /** The rows shown of the tables asked about within a task go to the server as one message
   * each, where they changed; `again` asks again for what stands there now. */
  private ask(table: string, again = false): void {
    if (again) this.asked.delete(table);
    if (this.asking.size === 0) {
      queueMicrotask(() => {
        const tables = [...this.asking];
        this.asking.clear();
        for (const each of tables) {
          if (!this.grids.has(each)) continue;
          const spans = wantedSpans(this.shown.values(), each);
          const given = JSON.stringify(spans);
          if ((this.asked.get(each) ?? '[]') === given) continue;
          this.asked.set(each, given);
          this.send({ type: 'rows', table: each, spans });
        }
      });
    }
    this.asking.add(table);
  }

  /** Carries out the operations on the tab's table, or a header's or a footer's with null, after
   * the browser's own edits to `doc`. Cells written show at once, by "row:col" of their table. */
  do(
    tab: string | null,
    operations: readonly object[],
    options: { doc?: Y.Doc; written?: Written } = {},
  ): { token: string; answer: Promise<void> } {
    const token = shortId();
    const message: Record<string, unknown> = { type: 'do', token, tab, operations };
    if (options.doc) message.after = afterOf(options.doc);
    const written = options.written;
    const grid = written && this.grids.get(written.table);
    if (grid && written) {
      for (const [key, cell] of written.cells) grid.written.set(key, { token, cell });
      this.tellRows(grid, written.cells.keys());
    }
    return { token, answer: this.sent(token, message) };
  }

  /** Takes back the edit of `token`, as one edit of its own, which in turn takes it back. */
  undo(token: string, doc?: Y.Doc): { token: string; answer: Promise<void> } {
    const then = shortId();
    const message: Record<string, unknown> = { type: 'undo', token, as: then };
    if (doc) message.after = afterOf(doc);
    return { token: then, answer: this.sent(then, message) };
  }

  referred(table: string): Promise<boolean> {
    if (!this.closed && !this.grids.has(table)) {
      return Promise.reject(new Refusal('no_table', table));
    }
    return this.question(`referred ${table}`, { type: 'referred', table });
  }

  where(name: string, table: string | null): Promise<Where | null> {
    return this.question(`where ${folded(name)} ${table}`, { type: 'where', name, table });
  }

  async rowIds(table: string, places: readonly number[]): Promise<string[]> {
    const grid = this.grids.get(table);
    if (!grid) throw new Refusal('no_table', table);
    if (places.some((place) => grid.rowId(place) === undefined)) {
      await this.standing(table, places, []);
    }
    return idsAt(grid, places);
  }

  async rowPlaces(table: string, rows: readonly string[]): Promise<number[]> {
    const grid = this.grids.get(table);
    if (!grid) throw new Refusal('no_table', table);
    if (rows.some((row) => grid.rowIndex(row) < 0)) await this.standing(table, [], rows);
    return rows.map((row) => grid.rowIndex(row));
  }

  async numberedPlaces(table: string, numbers: readonly number[]): Promise<number[]> {
    const grid = this.grids.get(table);
    if (!grid) throw new Refusal('no_table', table);
    if (grid.plain) return numbers.map((number) => (number < grid.rowCount ? number : -1));
    const named = await this.standing(table, [], [], numbers);
    return numbers.map((number) => {
      const id = named[number];
      return id === undefined ? -1 : grid.rowIndex(id);
    });
  }

  async numberedRows(table: string, numbers: readonly number[]): Promise<(string | null)[]> {
    const grid = this.grids.get(table);
    if (!grid) throw new Refusal('no_table', table);
    if (grid.plain) {
      const shown = numbers.filter((number) => number < grid.rowCount);
      const ids = await this.rowIds(table, shown);
      const found = new Map(shown.map((number, at) => [number, ids[at]]));
      return numbers.map((number) => found.get(number) ?? null);
    }
    const named = await this.standing(table, [], [], numbers);
    return numbers.map((number) => named[number] ?? null);
  }

  /** Keeps the user's filter of the table, none where no condition is given; the server lays
   * the table out again for each of the user's browsers. */
  filter(table: string, conditions: readonly Condition[]): Promise<void> {
    const key = `filter ${table}`;
    return new Promise<void>((answer, refused) => {
      if (this.closed) return refused(new Refusal('closed', null));
      const message = { type: 'filter', table, conditions };
      const waiting = [...(this.questions.get(key)?.waiting ?? []), { answer, refused }];
      this.questions.set(key, { message, waiting });
      this.send(message);
    });
  }

  /** The texts the column shows in the rows the other conditions of the filter let through. */
  offered(table: string, col: string): Promise<Offered> {
    return this.question(`values ${table} ${col}`, { type: 'values', table, col });
  }

  /** Asks where the rows stand: those at the places, those of the ids and those whose own
   * places are the numbers, which the answer names by them. */
  private standing(
    table: string,
    places: readonly number[],
    rows: readonly string[],
    numbered: readonly number[] = [],
  ): Promise<Record<number, string>> {
    const key = `standing ${table} ${places.join(' ')} ${rows.join(' ')} ${numbered.join(' ')}`;
    return this.question(key, { type: 'standing', table, places, rows, numbered });
  }

  table(table: string): Named | null {
    return this.byId.get(table) ?? null;
  }

  /** The server's answer to a question, asked once however many wait for it. */
  private question<T>(key: string, message: Record<string, unknown>): Promise<T> {
    return new Promise<T>((answer, refused) => {
      if (this.closed) return refused(new Refusal('closed', null));
      const asked = this.questions.get(key);
      if (asked) return void asked.waiting.push({ answer, refused });
      this.questions.set(key, { message, waiting: [{ answer, refused }] });
      this.send(message);
    });
  }

  private answered(key: string, answer: unknown): void {
    const question = this.questions.get(key);
    this.questions.delete(key);
    for (const each of question?.waiting ?? []) (each.answer as (answer: unknown) => void)(answer);
  }

  named(name: string): Named | null {
    return this.index.get(folded(name)) ?? null;
  }

  defined(name: string, table: string): string | null {
    let found: string | null = null;
    for (const [given, scope] of this.names) {
      if (folded(given) !== folded(name)) continue;
      if (scope === table) return given;
      if (scope === null) found = given;
    }
    return found;
  }

  private sent(token: string, message: Record<string, unknown>): Promise<void> {
    return new Promise<void>((done, refused) => {
      if (this.closed) return refused(new Refusal('closed', null));
      this.pending.set(token, { message, done, refused, behind: 0 });
      this.send(message);
    });
  }

  private settled(token: string): void {
    for (const grid of this.grids.values()) {
      const keys = [...grid.written].filter(([, each]) => each.token === token).map(([key]) => key);
      for (const key of keys) grid.written.delete(key);
      if (keys.length) this.tellRows(grid, keys);
    }
  }

  private tellRows(grid: Grid, keys: Iterable<string>): void {
    const rows = new Set([...keys].map((key) => key.split(':')[0]));
    this.listeners.tell({ table: grid.table, outline: false, rows });
  }

  private take(message: Record<string, unknown>): void {
    switch (message.type) {
      case 'tables': {
        const tables = message.tables as [string, string, number, number, string | null][];
        const counts = new Map<string | null, number>();
        for (const [, , , , tab] of tables) counts.set(tab, (counts.get(tab) ?? 0) + 1);
        const named = tables.map(([table, name, rows, cols, tab]) => {
          return { table, name, rows, cols, tab, only: counts.get(tab) === 1 };
        });
        this.index = new Map(named.map((each) => [folded(each.name), each]));
        this.byId = new Map(named.map((each) => [each.table, each]));
        break;
      }
      case 'names':
        this.names = message.names as [string, string | null][];
        break;
      case 'looks':
        for (const [key, look] of Object.entries(message.looks as Record<string, Look>)) {
          this.looks.set(key, look);
        }
        break;
      case 'grids':
        this.outlines(message.tab as string | null, message.grids as Outline[]);
        break;
      case 'rows': {
        const grid = this.grids.get(message.table as string);
        if (!grid) return;
        const at = message.at as Record<string, number>;
        const rows = new Set<string>();
        for (const row of [...grid.held.keys()]) {
          if (row in at) continue;
          grid.held.delete(row);
          rows.add(row);
        }
        grid.place(at, message.numbers as Record<string, number> | undefined);
        for (const [row, held] of Object.entries(message.rows as Record<string, SentHeld>)) {
          grid.hold(row, held);
          rows.add(row);
        }
        if (rows.size) this.listeners.tell({ table: grid.table, outline: false, rows });
        break;
      }
      case 'patch':
        for (const patch of message.patches as Patch[]) this.patched(patch, message.by as string);
        break;
      case 'done': {
        const token = message.token as string;
        const pending = this.pending.get(token);
        this.pending.delete(token);
        this.settled(token);
        pending?.done();
        break;
      }
      case 'refused': {
        const token = message.token as string;
        const pending = this.pending.get(token);
        if (pending && message.code === 'behind' && pending.behind < BEHIND_TRIES) {
          pending.behind++;
          setTimeout(
            () => this.pending.get(token) === pending && this.send(pending.message),
            BEHIND_RETRY,
          );
          return;
        }
        this.pending.delete(token);
        this.settled(token);
        pending?.refused(new Refusal(message.code as string, (message.detail as string) ?? null));
        break;
      }
      case 'referred':
        this.answered(`referred ${message.table as string}`, message.referred as boolean);
        break;
      case 'standing': {
        const table = message.table as string;
        const numbers = message.numbers as Record<string, number> | undefined;
        this.grids.get(table)?.place(message.at as Record<string, number>, numbers);
        const asked = [message.places, message.rows, message.numbered] as (number | string)[][];
        const key = `standing ${table} ${asked.map((each) => each.join(' ')).join(' ')}`;
        this.answered(key, message.named);
        break;
      }
      case 'values':
        this.answered(`values ${message.table as string} ${message.col as string}`, {
          values: message.values,
          more: message.more,
        });
        break;
      case 'filtered':
        this.answered(`filter ${message.table as string}`, null);
        break;
      case 'unfiltered': {
        const key = `filter ${message.table as string}`;
        const question = this.questions.get(key);
        this.questions.delete(key);
        const refusal = new Refusal(message.code as string, message.table as string);
        for (const each of question?.waiting ?? []) each.refused(refusal);
        break;
      }
      case 'where': {
        const at = message.at as [string, string] | null;
        const key = `where ${folded(message.name as string)} ${message.table as string | null}`;
        this.answered(key, at && { table: at[0], address: at[1] });
        break;
      }
    }
  }

  private outlines(tab: string | null, outlines: readonly Outline[]): void {
    const given = new Set(outlines.map((outline) => outline.table));
    for (const [table, grid] of [...this.grids]) {
      if (grid.tab !== tab || given.has(table)) continue;
      this.grids.delete(table);
      this.listeners.tell({ table, outline: true, rows: null, gone: true });
    }
    for (const outline of outlines) {
      const was = this.grids.get(outline.table);
      const grid = new Grid(outline, tab, this.looks);
      if (was) for (const [key, each] of was.written) grid.written.set(key, each);
      this.grids.set(outline.table, grid);
      this.ask(outline.table, true);
      this.listeners.tell({ table: outline.table, outline: true, rows: null });
    }
  }

  /** The rows of a table this browser made, in their order, which the server's outline names
   * only at its ends: a cell between them is written in before its rows come. */
  private madeRows(by: string, table: string): string[] | undefined {
    const operations = this.pending.get(by)?.message.operations as
      { op: string; id?: string; rowIds?: string[] }[] | undefined;
    return operations?.find((each) => each.op === 'table' && each.id === table)?.rowIds;
  }

  private patched(patch: Patch, by: string): void {
    const { table } = patch;
    if (patch.gone) {
      this.grids.delete(table);
      this.asked.delete(table);
      this.listeners.tell({ table, outline: true, rows: null, gone: true });
      return;
    }
    if (patch.made) {
      const grid = new Grid(patch.made, patch.tab ?? null, this.looks);
      const rows = this.madeRows(by, table);
      if (rows) grid.placeAll(rows);
      this.grids.set(table, grid);
      this.ask(table, true);
      this.listeners.tell({ table, outline: true, rows: null });
      return;
    }
    const grid = this.grids.get(table);
    if (!grid) return;
    if (patch.laid) {
      grid.outline(patch.laid);
      this.ask(table, true);
      this.listeners.tell({ table, outline: true, rows: null });
      return;
    }
    if (patch.rows) this.ask(table, true);
    this.listeners.tell(grid.apply(patch));
  }
}
