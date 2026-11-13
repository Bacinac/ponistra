import { type Node, Slice } from 'prosemirror-model';
import { EditorState, NodeSelection, Selection } from 'prosemirror-state';
import { type Step, StepMap } from 'prosemirror-transform';
import {
  Decoration,
  DecorationSet,
  type DecorationSource,
  EditorView,
  type NodeView,
} from 'prosemirror-view';
import { onScheme } from '../theme';
import { shortId } from './blocks';
import { conditionText } from './conditions';
import {
  type Book,
  columnName,
  rectOfAddress,
  type Syntax,
  syntaxOf,
  type Value,
} from './formulas';
import {
  type Attrs,
  type Change,
  type Condition,
  type Grid,
  keyOf,
  type Look,
  placesOf,
  type Shown,
  type Written,
} from './grids';
import {
  GAP,
  pagingOf,
  repaginate,
  type Row,
  scaleOf,
  tableGaps,
  type TableGaps,
  tableRows,
} from './pages';
import { schema } from './schema';
import { INNER } from './suggesting';
import { Mirror } from './mirror';
import { hold } from './settled';
import {
  CATALOGUE,
  designOf,
  designsIn,
  ours,
  shadowOf,
  type Switch,
  type TableDesign,
} from './design';
import {
  type Box,
  dressed,
  forgetWraps,
  type Frame,
  frozenShift,
  Geometry,
  headingsAt,
  Inks,
  insetsOf,
  paint,
  type Painted,
  paperCell,
  PaperTable,
  REACH,
  wrapped,
} from './sheet';
import {
  type Axis,
  charactersOf,
  type Copied,
  copiedTable,
  drawnWidths,
  filled,
  isSized,
  type KnownLines,
  Layout,
  lightCell,
  type Lines,
  lookOf,
  meets,
  NONE_HIDDEN,
  OUTLINED,
  partLines,
  type Placed,
  type Rect,
  rectOfCell,
  retyped,
  rounded,
  rowAt,
  SIDES,
  standsIn,
  tableWidth,
  widened,
  widthsOf,
} from './tables';
import {
  awaited,
  BACK,
  blockAt,
  boxes,
  cellBlocks,
  CellRange,
  cellType,
  type Direction,
  forCell,
  holdsTableOrNote,
  loneTable,
  POINTS,
  type RangeEdit,
  shownBy,
  specOf,
  tablesIn,
  type TablesSpec,
  views,
  whole,
} from './tableBase';
import { blocksJSON, CellView, writing } from './cellView';

let names = 0;
const BLOCK_ROWS = 50;
/** A table this short holds all its rows, as its rows' heights then never change in view. */
const SHORT = 200;
/** As many columns of 4rem as the page column holds. */
const WIDE_COLS = 11;
/** The canvas reaches as much past the view above and below, as a share of the view's height. */
const OVERSCAN = 0.5;
/** Of an edge between lines, in pixels, that a press takes for dragging it. */
const EDGE = 4;

type Hit =
  | { kind: 'colEdge'; index: number }
  | { kind: 'rowEdge'; index: number }
  | { kind: 'lines'; rect: Rect }
  | { kind: 'cell'; key: string };

const NONE: Lines = {
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

/** A table: its grid of rows and columns drawn on a canvas, from the rows of it the server sent,
 * and the cells with a node in the text, or written in, as elements over it, each with an editor
 * of its own. Whole cells are selected by dragging across them or with Shift. */
export class TableView implements NodeView {
  readonly dom = document.createElement('div');
  readonly spec: TablesSpec;
  lines: Grid | null = null;
  layout: Layout;
  design: TableDesign;
  geometry: Geometry | null = null;
  gone = false;
  /** The address of a cell to show once the grid has come. */
  private wanted: string | null = null;
  private focusing = true;
  /** Counts the addresses shown, so that one whose rows came later gives way to the last. */
  private shows = 0;
  /** The rows of cells with a node in the text whose places were asked for. */
  private placing = new Set<string>();
  /** The table's name, by which formulas refer to it, as to a workbook's sheet. */
  private caption = document.createElement('div');
  private filters = document.createElement('div');
  /** The headings and the rows; it scrolls sideways where the rows are wider. */
  private sheet = document.createElement('div');
  private paper: PaperTable | null = null;
  private grid = document.createElement('div');
  private canvas = document.createElement('canvas');
  private context: CanvasRenderingContext2D;
  private layer = document.createElement('div');
  private mirror = new Mirror(this.grid);
  /** Dragged from the corner of the selected cells, fills the cells it is dragged over. */
  private handle = document.createElement('div');
  private inks: Inks;
  /** The rows each page of the Pages view starts with inside the table, and the gaps before them. */
  private gaps: TableGaps['rows'] = [];
  private gapElements: HTMLElement[] = [];
  private shadows: HTMLElement[] = [];
  /** The cell the cursor is in. */
  private current: string | null = null;
  private cells = new Map<string, CellView>();
  /** The heights the cells with elements need, by key. */
  private needs = new Map<string, number>();
  private window: [number, number] = [0, -1];
  /** The frozen rows held above the window. */
  private above = 0;
  /** How many rows stand atop each page the table runs onto, as the pages were laid out. */
  private header = 0;
  private range_: CellRange | null = null;
  /** Holds the rows of the selected cells, which a copy reads. */
  private ranged = {};
  private frame = 0;
  private painted: { area: Box; view: Box; key: string } | null = null;
  private side = 0;
  private top = 0;
  private clips: HTMLElement[] | null = null;
  private resizing = false;
  /** The columns' widths in characters while one of their edges is dragged. */
  private dragged: readonly number[] | null = null;
  private unsubscribe: () => void;
  private observer: ResizeObserver;
  private measured: ResizeObserver;
  private scrolled = () => this.viewed();
  private themed = () => {
    this.inks.clear();
    forgetWraps();
    if (this.paper) this.measurePaper();
    else this.relayout();
  };
  private unscheme = () => {};
  /** Focus anywhere else in the document takes the cells out of their typed text. */
  private left = (event: FocusEvent) => {
    for (const cell of this.cells.values()) {
      if (!(event.target instanceof globalThis.Node && cell.box.contains(event.target)))
        cell.leave();
    }
  };

  constructor(
    public node: Node,
    readonly outer: EditorView,
    readonly getPos: () => number | undefined,
    decorations: readonly Decoration[],
    private inside: DecorationSource,
  ) {
    this.spec = specOf(outer.state);
    this.layout = new Layout(NONE, node);
    this.design = designOf(node, this.layout);
    this.dom.className = 'ponistra-table';
    this.caption.className = 'ponistra-table-name';
    this.caption.id = `ponistra-table-${++names}`;
    this.filters.className = 'ponistra-table-filter';
    this.filters.hidden = true;
    this.sheet.className = 'ponistra-sheet';
    this.grid.className = 'ponistra-grid';
    this.grid.setAttribute('role', 'grid');
    this.grid.setAttribute('aria-labelledby', this.caption.id);
    this.canvas.className = 'ponistra-canvas';
    this.canvas.ariaHidden = 'true';
    this.layer.className = 'ponistra-cells';
    this.handle.className = 'ponistra-fill-handle';
    this.handle.hidden = true;
    this.grid.append(this.canvas, this.mirror.dom, this.layer, this.handle);
    this.sheet.append(this.grid);
    this.dom.append(this.caption, this.filters, this.sheet);
    this.context = this.canvas.getContext('2d')!;
    this.inks = new Inks(this.dom);
    views.set(this.dom, this);
    shownBy.set(node, this);
    let tables = tablesIn.get(outer);
    if (!tables) tablesIn.set(outer, (tables = new Set()));
    tables.add(this);
    this.unsubscribe = this.spec.grids.subscribe(node.attrs.id, (change) => this.changed(change));
    this.dom.addEventListener('mousedown', (event) => this.pressed(event), true);
    this.dom.addEventListener('dblclick', (event) => this.doubled(event), true);
    this.grid.addEventListener('mousemove', (event) => this.hovered(event));
    outer.dom.addEventListener('focusin', this.left);
    this.observer = new ResizeObserver(() => this.relayout());
    this.observer.observe(this.sheet);
    this.measured = new ResizeObserver((entries) => this.remeasured(entries));
    document.addEventListener('scroll', this.scrolled, { capture: true, passive: true });
    addEventListener('resize', this.scrolled, { passive: true });
    this.unscheme = onScheme(this.themed);
    document.fonts.addEventListener('loadingdone', this.themed);
    tableRows.set(this.dom, () => (this.paper ? this.paper.rows() : this.rowBoxes()));
    this.gaps = tableGaps(decorations);
    this.range_ = this.range();
    this.arrived();
    this.refresh(null);
  }

  /** A pasted table's holder taken out once the table stands before it, unless it is the last
   * block, which the cursor can then go to after the table. */
  private arrived(): void {
    const awaiting = awaited.get(this.id);
    const holder = awaiting?.holder;
    if (!awaiting || !holder) return;
    awaiting.holder = undefined;
    if (!awaiting.then) awaited.delete(this.id);
    queueMicrotask(() => {
      const { state } = this.outer;
      const pos = blockAt(state.doc, holder.id);
      const node = pos === null ? null : state.doc.nodeAt(pos);
      if (pos === null || !node || node.content.size || node === state.doc.lastChild) return;
      const take = () => this.outer.dispatch(this.outer.state.tr.delete(pos, pos + node.nodeSize));
      if (holder.change && this.spec.history) this.spec.history.into(holder.change, take);
      else take();
    });
  }

  private get id(): string {
    return this.node.attrs.id;
  }

  valueOf(key: string): Value | undefined {
    const [row, col] = key.split(':');
    return this.lines?.value(row, col);
  }

  syntax(): Syntax {
    return syntaxOf(this.spec.locale());
  }

  /** The document's tables and the defined names in force in this one, which formulas refer to
   * by name. */
  book(): Book {
    const { grids } = this.spec;
    return {
      named: (name) => grids.named(name),
      name: (name) => grids.defined(name, this.id),
    };
  }

  size(): { rows: number; cols: number } {
    return { rows: this.layout.rows, cols: this.layout.cols };
  }

  /** Writes the cells, each shown at once as `shown` gives it. */
  /** `formulas` are written again after the cells' blocks, which take a cell's formula away: a
   * formula written keeps the look its cell has. */
  writeCells(
    cells: object[],
    shown: Record<string, Shown | undefined | null>,
    formulas: object[] = [],
  ): void {
    const { write } = this.spec;
    if (!write || !this.outer.editable) return;
    const written = new Map(
      Object.entries(shown).map(([key, cell]) => [key, cell ? withoutEmpty(cell) : null]),
    );
    const operations = [{ op: 'cells', table: this.id, cells }];
    if (formulas.length) operations.push({ op: 'cells', table: this.id, cells: formulas });
    write(operations, { table: this.id, cells: written });
  }

  private operate(operations: object[], written?: Written): boolean {
    const { write } = this.spec;
    if (!write || !this.outer.editable || this.gone) return false;
    write(operations, written);
    return true;
  }

  /** The cell's formula, or none, with `text` in its place. A formula outweighs the cell's text,
   * which would only lie hidden under it. */
  setFormula(cell: CellView, formula: string | null, text = ''): void {
    const [row, col] = cell.key.split(':');
    const [r, c] = [row, col];
    const was = this.lines?.cell(r, c);
    if (formula !== null) {
      const taken = cell.takeLook();
      const shown = { ...was, text: undefined, formula, ...(taken && { look: taken.look }) };
      this.operate(
        [
          ...(taken
            ? [{ op: 'cells', table: this.id, cells: [{ row, col, blocks: taken.blocks }] }]
            : []),
          { op: 'cells', table: this.id, cells: [{ row, col, formula }] },
        ],
        { table: this.id, cells: new Map([[cell.key, withoutEmpty(shown)]]) },
      );
    } else if (text.startsWith('=')) {
      const blocks = blocksJSON(
        retyped(cell.inner?.state.doc ?? lightCell(schema, row, col, '', was?.look), text),
      );
      this.writeCells([{ row, col, blocks }], { [cell.key]: { ...was, formula: undefined, text } });
    } else {
      this.writeCells([{ row, col, value: text || null }], {
        [cell.key]: { ...was, formula: undefined, text },
      });
    }
  }

  /** The number format of the cells, or none. */
  setFormat(rect: Rect, code: string | null): void {
    const lines = this.lines;
    if (!lines || !this.loaded(rect)) return;
    const cells: object[] = [];
    const shown: Record<string, Shown | null> = {};
    for (const placed of this.layout.cellsIn(rect)) {
      const [row, col] = placed.key.split(':');
      cells.push({ row, col, format: code });
      if (lines.holds(row))
        shown[placed.key] = { ...lines.cell(row, col), format: code ?? undefined };
    }
    if (cells.length) this.writeCells(cells, shown);
  }

  /** The cells filled, or their fill taken off with null; whole rows or columns as their lines,
   * which the cells in them follow. */
  async setFill(rect: Rect, fill: string | null): Promise<void> {
    const lines = this.lines;
    if (!lines) return;
    if (rect.top === 0 && rect.bottom === lines.rowCount - 1) {
      const ends = this.colEnds(rect.left, rect.right);
      this.operate([{ op: 'looks', table: this.id, axis: 'cols', ...ends, fill }]);
      return;
    }
    if (rect.left === 0 && rect.right === lines.cols.length - 1) {
      const ends = await this.rowEnds(rect.top, rect.bottom);
      this.operate([{ op: 'looks', table: this.id, axis: 'rows', ...ends, fill }]);
      return;
    }
    if (!this.loaded(rect)) return;
    const cells: object[] = [];
    const shown: Record<string, Shown | null> = {};
    for (const placed of this.layout.cellsIn(rect)) {
      const [row, col] = placed.key.split(':');
      cells.push({ row, col, fill });
      if (placed.node) continue;
      const was = lines.cell(row, col);
      const look: Look = { ...was?.look };
      delete look.fill;
      if (fill) look.fill = fill;
      shown[placed.key] = { ...was, look };
    }
    if (cells.length) this.writeCells(cells, shown);
  }

  /** The fill of the range's first cell, which the toolbar shows as chosen. */
  fillAt(rect: Rect): string | null {
    const placed = this.layout.at(rect.top, rect.left);
    if (!placed) return null;
    if (placed.node) return placed.node.attrs.fill ?? null;
    const [row, col] = placed.key.split(':');
    return this.lines?.cell(row, col)?.look?.fill ?? null;
  }

  /** The ids of the rows at both ends, by which a range of rows is sent. */
  private async rowEnds(first: number, last: number): Promise<{ from: string; to: string }> {
    const [from, to] = await this.spec.grids.rowIds(this.id, [first, last]);
    return { from, to };
  }

  private colEnds(first: number, last: number): { from: string; to: string } {
    const cols = this.lines!.cols;
    return { from: cols[first], to: cols[last] };
  }

  /** The rows from the first to the last, or the table's data, sorted by the column. */
  async sort(col: string, descending: boolean, rows: [number, number] | null): Promise<void> {
    const ends = rows ? await this.rowEnds(...rows) : {};
    this.operate([{ op: 'order', table: this.id, col, descending, ...ends }]);
  }

  formatOf(key: string): string | undefined {
    const [row, col] = key.split(':');
    return this.lines?.cell(row, col)?.format;
  }

  placedOf(key: string): Placed | null {
    return this.layout.placed(key);
  }

  cellView(key: string): CellView | null {
    return this.cells.get(key) ?? null;
  }

  private changed(change: Change): void {
    if (change.gone || this.gone) return;
    this.refresh(change.outline ? null : change.rows);
    if (change.outline) this.holdRange();
  }

  /** The table again from its node and grid: its lines and merges where `rows` is null, else only
   * the cells of those rows. */
  private refresh(rows: ReadonlySet<string> | null): void {
    const grid = this.spec.grids.grid(this.id);
    this.lines = grid ?? null;
    if (rows === null || !grid) {
      this.layout = new Layout(grid ?? NONE, this.node);
      if (grid) this.placeNodes(grid);
    }
    this.design = designOf(this.node, this.layout, (row, col) => grid?.cell(row, col)?.look);
    const name = grid?.name ?? '';
    if (this.caption.textContent !== name) this.caption.textContent = name;
    if (this.caption.hidden !== !name) this.caption.hidden = !name;
    if (this.dom.hasAttribute('data-named') !== !!name)
      this.dom.toggleAttribute('data-named', !!name);
    this.showFilter(grid?.filter ?? []);
    const sized = isSized(this.node);
    this.showSize(grid ? tableWidth(sized, grid.cols, grid.widths, grid.hidden.cols) : null);
    if (this.spec.paper) this.drawPaper();
    else this.relayout();
    const header = grid?.frozenRows() ?? 0;
    if (header !== this.header) {
      this.header = header;
      repaginate(this.outer);
    }
    if (grid && this.wanted) this.showWanted();
    const awaiting = awaited.get(this.id);
    const then = awaiting?.then;
    if (grid && awaiting && then) {
      awaiting.then = undefined;
      if (!awaiting.holder) awaited.delete(this.id);
      queueMicrotask(() => {
        if (then === 'first') this.enter('first');
        else this.selectWhole();
      });
    }
  }

  /** The table as wide as `width` characters, or as the page where null. */
  private showSize(width: number | null): void {
    const cols = this.layout.cols;
    const least =
      width !== null
        ? `calc(${Math.round(width * 10) / 10}ch + ${REACH}px)`
        : cols > WIDE_COLS
          ? `${cols * 4}rem`
          : '';
    if (this.dom.hasAttribute('data-wide') !== !!least) {
      this.dom.toggleAttribute('data-wide', !!least);
    }
    if (this.dom.hasAttribute('data-sized') !== (width !== null)) {
      this.dom.toggleAttribute('data-sized', width !== null);
    }
    if (this.dom.style.getPropertyValue('--least') !== least) {
      this.dom.style.setProperty('--least', least);
    }
  }

  /** The columns' share of the table's width in per cent. */
  private shares(): number[] {
    const lines = this.lines ?? NONE;
    const { dragged } = this;
    if (!dragged) return widthsOf(isSized(this.node), lines.cols, lines.widths, lines.hidden.cols);
    const widths = new Map(lines.cols.map((col, at) => [col, dragged[at]]));
    return widthsOf(true, lines.cols, widths, lines.hidden.cols);
  }

  /** The headings' room beside and above the rows, as the stylesheet gives it. */
  private headingRoom(): void {
    if (this.side) return;
    const style = getComputedStyle(this.dom);
    const probe = this.inks.host.appendChild(document.createElement('div'));
    probe.style.width = style.getPropertyValue('--heading-side');
    probe.style.height = style.getPropertyValue('--heading-top');
    const rect = probe.getBoundingClientRect();
    probe.remove();
    const scale = this.scale();
    this.side = rect.width / scale;
    this.top = rect.height / scale;
  }

  /** The geometry, laid out now where the table was not shown when its lines last changed. */
  private laidOut(): Geometry | null {
    if (!this.geometry) this.relayout();
    return this.geometry;
  }

  /** Whether the document shows the table, which is measured only then. */
  private shown(): boolean {
    return this.sheet.getClientRects().length > 0;
  }

  private scale(): number {
    const width = this.dom.offsetWidth;
    return width ? this.dom.getBoundingClientRect().width / width || 1 : 1;
  }

  /** The heights the rows need: as tall as given, else as one line, and never shorter than the
   * text of a held row's cells. */
  private rowHeights(lefts: Float64Array): Float64Array {
    const { layout, lines } = this;
    if (!lines) return new Float64Array(0);
    const padding = this.inks.padding();
    const least = padding.y * 2 + this.inks.of(undefined, null).line + 1;
    const inset = this.inset();
    const heights = new Float64Array(layout.rows);
    for (let row = 0; row < layout.rows; row++) {
      const id = lines.rowId(row);
      const given = id === undefined ? undefined : lines.heights.get(id);
      const apart = insetsOf({ top: row, left: 0, bottom: row, right: 0 }, layout.rows, 1, inset);
      const extra = apart.top + apart.bottom;
      let height = Math.max(least + extra, given ? given * POINTS : 0);
      if (id !== undefined && lines.holds(id)) {
        for (let col = 0; col < layout.cols; col++) {
          if (!layout.starts(row, col)) continue;
          const placed = layout.at(row, col)!;
          if (placed.rows > 1) continue;
          const { left, right } = insetsOf(rectOfCell(placed), layout.rows, layout.cols, inset);
          const width = lefts[col + placed.cols] - lefts[col] - left - right;
          const need = (this.needs.get(placed.key) ?? this.textHeight(placed, width)) + extra;
          if (need > height) height = need;
        }
      }
      heights[row] = height;
    }
    return heights;
  }

  /** Half the gap Word's spacing sets between the cells, in pixels. */
  private inset(): number {
    return (this.design.whole?.spacing ?? 0) * POINTS;
  }

  private textHeight(placed: Placed, width: number): number {
    if (placed.node) return 0;
    const painted = this.paintedCell(placed.row, placed.col, placed.key, true);
    if (!painted?.text) return 0;
    const { ink } = painted;
    const padding = this.inks.padding();
    const room = width - padding.x * 2 - ink.start - ink.end;
    if (room <= 0) return 0;
    return wrapped(painted.text, ink.font, room, ink.first).length * ink.line + padding.y * 2 + 1;
  }

  /** What a light cell shows: the value the server computed in its place, else its text; and
   * the fill of a cell drawn by its own element, which stays under the sheet's lines. */
  private paintedCell(row: number, col: number, key: string, any = false): Painted | null {
    const lines = this.lines;
    if (!lines) return null;
    const r = lines.rowId(row);
    if (r === undefined) return null;
    const c = lines.cols[col];
    const shown = lines.cell(r, c);
    const node = this.layout.at(row, col)?.node;
    const designed = this.design.at(row, col);
    if (node || (!any && this.cells.has(key))) {
      const own: string | null | undefined = node ? node.attrs.fill : shown?.look?.fill;
      const fill = own ?? designed.fill;
      return fill ? { text: '', ink: this.inks.of({ fill }, null) } : null;
    }
    const value = lines.value(r, c);
    const computed = standsIn(value, !!shown?.formula, !!shown?.format);
    const typed = shown?.text ?? '';
    const text = computed ? value!.text : typed.startsWith("'") ? typed.slice(1) : typed;
    const look = dressed(shown?.look, designed);
    if (!text && !look?.fill) return null;
    return { text, ink: this.inks.of(look, value?.kind ?? null, computed) };
  }

  /** The lines laid out at the sheet's width now, the cells in view placed over them. */
  relayout(): void {
    if (this.gone || this.spec.paper || !this.shown()) return;
    this.headingRoom();
    const lines = this.lines ?? NONE;
    const width = Math.max(0, this.grid.clientWidth - this.side - REACH);
    const lefts = new Float64Array(lines.cols.length + 1);
    lefts[0] = this.side;
    this.shares().forEach((share, index) => {
      lefts[index + 1] = lefts[index] + (share * width) / 100;
    });
    const heights = this.rowHeights(lefts);
    const tops = new Float64Array(heights.length);
    const gaps = new Map(this.gaps.map(({ row, gap }) => [row, gap]));
    let y = this.top;
    for (let row = 0; row < heights.length; row++) {
      y += gaps.get(row) ?? 0;
      tops[row] = y;
      y += heights[row];
    }
    this.geometry = new Geometry(this.side, this.top, lefts, tops, heights, this.inset());
    const height = `${this.geometry.height + REACH}px`;
    if (this.grid.style.height !== height) this.grid.style.height = height;
    this.showGaps();
    this.showShadow();
    this.viewed(true);
  }

  /** The rows in view held, the cells with elements among them placed, and the sheet drawn again
   * where the view went past what the canvas covers. */
  private viewed(force = false): void {
    const geometry = this.geometry;
    if (!geometry || this.gone) return;
    const view = this.viewBox();
    if (view) this.hold(view);
    this.place(force, view);
    if (force || !view || !this.painted || !within(view, this.painted.area) || this.sticky(view)) {
      this.schedule();
    }
  }

  /** Whether the headings or the frozen rows moved with the view, as they stay at its top. */
  private sticky(view: Box): boolean {
    if (!this.painted || !this.geometry) return false;
    const headings = this.headingsShown();
    const before = { view: this.painted.view, geometry: this.geometry, frozen: this.frozen() };
    const now = { ...before, view };
    const [was, is] = [headingsAt(before), headingsAt(now)];
    return (
      (headings && (was.x !== is.x || was.y !== is.y)) ||
      frozenShift(before, headings) !== frozenShift(now, headings)
    );
  }

  /** How many rows stay at the top of the view; none in the Pages view, which shows the rows on
   * their pages. */
  private frozen(): number {
    return this.lines && !pagingOf(this.outer.state)?.sheets ? this.lines.frozenRows() : 0;
  }

  /** How many header rows the Pages view draws again atop the pages the table runs onto. */
  private repeated(): number {
    return this.lines && this.gaps.some((each) => each.header) ? this.lines.frozenRows() : 0;
  }

  /** Whether a height on the sheet is in a copy of the header rows atop a page, which only shows
   * them. */
  private repeatedAt(y: number): boolean {
    const geometry = this.geometry;
    return this.gaps.some(
      ({ row, header }) =>
        !!header &&
        !!geometry &&
        row < geometry.rows &&
        y >= geometry.tops[row] - header &&
        y < geometry.tops[row],
    );
  }

  /** The height on the sheet a pointer at `y` in the view points to, where the frozen rows are
   * shown over the rows beneath them. */
  private unfrozen(y: number, view: Box | null): number {
    const { shift, bottom } = this.band(view);
    return shift && y >= this.geometry!.top + shift && y < bottom ? y - shift : y;
  }

  /** How far the frozen rows are moved in the view, and the sheet's height they end at there. */
  private band(view: Box | null): { shift: number; bottom: number } {
    const geometry = this.geometry;
    const frozen = this.frozen();
    if (!geometry || !view || !frozen) return { shift: 0, bottom: 0 };
    const shift = frozenShift({ view, geometry, frozen }, this.headingsShown());
    return { shift, bottom: geometry.bottom(frozen - 1) + shift };
  }

  /** The part of the sheet in view below what covers the panes it scrolls in, in its own pixels;
   * null where none is. */
  private viewBox(): Box | null {
    const rect = this.grid.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const scale = scaleOf(this.grid, rect);
    let left = 0;
    let top = 0;
    let right = innerWidth;
    let bottom = innerHeight;
    this.clips ??= clipsOf(this.grid);
    for (const clip of this.clips) {
      const box = clip.getBoundingClientRect();
      left = Math.max(left, box.left);
      top = Math.max(top, box.top + (parseFloat(getComputedStyle(clip).scrollPaddingTop) || 0));
      right = Math.min(right, box.right);
      bottom = Math.min(bottom, box.bottom);
    }
    left = Math.max(left, rect.left);
    top = Math.max(top, rect.top);
    right = Math.min(right, rect.right);
    bottom = Math.min(bottom, rect.bottom);
    if (right <= left || bottom <= top) return null;
    return {
      x: (left - rect.left) / scale,
      y: (top - rect.top) / scale,
      width: (right - left) / scale,
      height: (bottom - top) / scale,
    };
  }

  /** The rows around those in view held, in blocks, and the frozen rows above them; a short
   * table's all of them. */
  private hold(view: Box): void {
    const geometry = this.geometry!;
    const lines = this.lines;
    if (!lines) return;
    const count = lines.rowCount;
    let first = 0;
    let last = count - 1;
    if (count > SHORT) {
      const from = Math.max(0, geometry.rowAt(view.y));
      const to = Math.max(from, geometry.rowAt(view.y + view.height));
      first = Math.max(0, (Math.floor(from / BLOCK_ROWS) - 1) * BLOCK_ROWS);
      last = Math.min(count - 1, (Math.floor(to / BLOCK_ROWS) + 2) * BLOCK_ROWS - 1);
    }
    const above = Math.min(Math.max(this.frozen(), this.repeated()), first);
    if (first === this.window[0] && last === this.window[1] && above === this.above) return;
    this.window = [first, last];
    this.above = above;
    this.spec.grids.show(
      this,
      this.id,
      above
        ? [
            [0, above - 1],
            [first, last],
          ]
        : [[first, last]],
    );
  }

  /** The elements of the cells with a node in the held rows, and of those written in, where the
   * sheet lays them now. */
  private place(force: boolean, view: Box | null): void {
    const { layout } = this;
    const [first, last] = this.window;
    const kept = new Set<string>();
    const sync = (cell: CellView, placed: Placed, decorations: DecorationSource) =>
      this.syncCell(cell, placed, decorations, force, view);
    for (const placed of layout.nodeCells()) {
      const out = placed.row + placed.rows - 1 < first || placed.row > last;
      if (out && placed.row >= this.above) continue;
      kept.add(placed.key);
      let view = this.cells.get(placed.key);
      if (view?.light) {
        view.destroy();
        view = undefined;
      }
      if (!view) {
        view = new CellView(this, placed, false);
        this.cells.set(placed.key, view);
        this.layer.append(view.box);
        this.measured.observe(view.holder);
      }
      sync(view, placed, this.inside.forChild(placed.offset!, placed.node!));
    }
    for (const [key, view] of this.cells) {
      if (kept.has(key)) continue;
      const placed = view.light ? layout.placed(key) : null;
      if (placed && !placed.node) {
        sync(view, placed, DecorationSet.empty);
        continue;
      }
      if (view.inner?.hasFocus() || view.formula) continue;
      this.measured.unobserve(view.holder);
      view.destroy();
      this.cells.delete(key);
      this.needs.delete(key);
    }
  }

  /** A cell's element where the sheet lays the cell now: a frozen row's moved with the view, and
   * one beneath the frozen rows cut where they cover it. */
  private syncCell(
    cell: CellView,
    placed: Placed,
    decorations: DecorationSource,
    force: boolean,
    view: Box | null,
  ): void {
    const box = this.geometry!.cell(rectOfCell(placed));
    const { shift, bottom } = this.band(view);
    const above = placed.row < this.frozen();
    if (above) box.y += shift;
    cell.sync(placed, box, decorations, this.spec.label()('table.cell'), force);
    const unseen = !box.width || !box.height || this.layout.hiddenAt(placed.row, placed.col);
    if (cell.box.hidden !== unseen) cell.box.hidden = unseen;
    const hidden = above || !shift ? 0 : bottom - box.y;
    const clip = hidden > 0 ? `inset(${hidden}px 0 0 0)` : '';
    if (cell.box.style.clipPath !== clip) cell.box.style.clipPath = clip;
    cell.box.toggleAttribute('data-frozen', above && shift > 0);
  }

  private remeasured(entries: ResizeObserverEntry[]): void {
    if (!this.shown()) return;
    const padding = this.inks.padding();
    let changed = false;
    for (const entry of entries) {
      const box = (entry.target as HTMLElement).parentElement;
      const view = box ? boxes.get(box) : undefined;
      if (!view || view.light) continue;
      const need = (entry.target as HTMLElement).offsetHeight + padding.y * 2 + 1;
      if (this.needs.get(view.key) !== need) {
        this.needs.set(view.key, need);
        changed = true;
      }
    }
    if (changed) this.relayout();
  }

  /** Draws the sheet once the browser draws next. */
  schedule(): void {
    if (this.frame || this.gone || this.spec.paper) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.draw();
    });
  }

  private headingsShown(): boolean {
    return (
      this.dom.classList.contains('ProseMirror-selectednode') ||
      this.range_ !== null ||
      (writing !== null && writing.table !== this && !!this.lines?.name) ||
      (writing?.table === this && writing.formula !== null)
    );
  }

  private draw(): void {
    const geometry = this.geometry;
    if (!geometry || this.gone) return;
    this.mirror.size(geometry);
    const view = this.viewBox();
    if (!view) {
      this.painted = null;
      this.mirror.clear();
      return;
    }
    const over = view.height * OVERSCAN;
    const top = Math.max(0, view.y - over);
    const area = {
      x: view.x,
      y: top,
      width: view.width,
      height: Math.min(geometry.height + REACH, view.y + view.height + over) - top,
    };
    const scale = (devicePixelRatio || 1) * this.scale();
    const { canvas, context } = this;
    const width = Math.ceil(area.width * scale);
    const height = Math.ceil(area.height * scale);
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    const style = canvas.style;
    for (const [name, value] of [
      ['left', area.x],
      ['top', area.y],
      ['width', area.width],
      ['height', area.height],
    ] as const) {
      if (style[name] !== `${value}px`) style[name] = `${value}px`;
    }
    context.setTransform(scale, 0, 0, scale, -area.x * scale, -area.y * scale);
    const lines = this.lines;
    const editable = this.outer.editable;
    const selected = this.rangeRect();
    const headings = this.headingsShown();
    const paged = !!pagingOf(this.outer.state)?.sheets;
    const frame: Frame = {
      area,
      view,
      geometry,
      layout: this.layout,
      cell: (row, col, key) => this.paintedCell(row, col, key),
      design: this.design,
      guides: editable && (headings || !paged),
      paint: (css) => this.inks.paint(css),
      selected,
      headings: headings
        ? {
            picked: this.pickedRect(),
            number: (row) => lines?.rowNumber(row),
            filtered: !!lines?.filter.length,
          }
        : null,
      colours: this.inks.colour(),
      heading: this.inks.headings(),
      padding: this.inks.padding(),
      held: (row) => {
        const id = lines?.rowId(row);
        return id !== undefined && lines!.holds(id);
      },
      frozen: this.frozen(),
      repeats: this.repeats(geometry),
    };
    paint(context, frame);
    this.painted = { area, view, key: '' };
    this.mirror.update({
      area,
      view,
      geometry,
      layout: this.layout,
      headings,
      text: (row, col, key) => this.paintedCell(row, col, key, true)?.text ?? '',
      number: (row) => lines?.rowNumber(row),
      own: (key) => this.cells.get(key)?.box ?? null,
      selected,
      frozen: frame.frozen,
    });
    this.showHandle(view);
  }

  private repeats(geometry: Geometry): Frame['repeats'] {
    const rows = this.repeated();
    if (!rows) return null;
    const tops = this.gaps.flatMap(({ row, header }) =>
      header && row < geometry.rows ? [geometry.tops[row] - header] : [],
    );
    return { rows, tops, cell: (row, col, key) => this.paintedCell(row, col, key, true) };
  }

  /** The rows as the Pages view measures them, in the page's pixels. */
  private rowBoxes(): Row[] {
    const geometry = this.geometry;
    if (!geometry) return [];
    const header = this.lines?.frozenRows() ?? 0;
    const rect = this.grid.getBoundingClientRect();
    const scale = scaleOf(this.grid, rect);
    const joined = new Set<number>();
    for (const merge of this.layout.mergesIn(0, geometry.rows - 1)) {
      for (let row = merge.top + 1; row <= merge.bottom; row++) joined.add(row);
    }
    const boxes: Row[] = [];
    for (let row = 0; row < geometry.rows; row++) {
      boxes.push({
        top: rect.top + geometry.tops[row] * scale,
        bottom: rect.top + geometry.bottom(row) * scale,
        joined: joined.has(row),
        header: row < header,
      });
    }
    return boxes;
  }

  /** A gap of the given height before each row a page starts with; at its end, the header rows'
   * cells with elements of their own drawn again, as the canvas draws the others. */
  private showGaps(): void {
    const geometry = this.geometry;
    while (this.gapElements.length < this.gaps.length) {
      const gap = this.grid.appendChild(document.createElement('div'));
      gap.className = GAP;
      gap.ariaHidden = 'true';
      this.gapElements.push(gap);
    }
    for (const gap of this.gapElements.splice(this.gaps.length)) gap.remove();
    const rows = this.lines?.frozenRows() ?? 0;
    const cells = [...this.layout.nodeCells()].filter((placed) => placed.row < rows);
    this.gaps.forEach(({ row, gap, header }, index) => {
      const element = this.gapElements[index];
      const { style } = element;
      const top = geometry && row < geometry.rows ? geometry.tops[row] - gap : 0;
      style.top = `${top}px`;
      style.height = `${gap}px`;
      const copies =
        geometry && header
          ? cells.map((placed) => this.headerCopy(placed, gap - header, geometry))
          : [];
      element.replaceChildren(...copies);
    });
  }

  /** The shadow the design casts, under the table's rows on each page they stand on. */
  private showShadow(): void {
    const geometry = this.geometry;
    const shadow = geometry && geometry.rows ? shadowOf(this.design.whole?.shadow) : null;
    const pages: [number, number][] = [];
    if (geometry && shadow) {
      let top = geometry.tops[0];
      for (const { row, gap, header } of this.gaps) {
        if (row <= 0 || row >= geometry.rows) continue;
        pages.push([top, geometry.tops[row] - gap]);
        top = geometry.tops[row] - (header ?? 0);
      }
      pages.push([top, geometry.height]);
    }
    while (this.shadows.length < pages.length) {
      const element = this.grid.insertBefore(document.createElement('div'), this.canvas);
      element.className = 'ponistra-shadow';
      this.shadows.push(element);
    }
    for (const element of this.shadows.splice(pages.length)) element.remove();
    if (!geometry) return;
    pages.forEach(([top, bottom], index) => {
      const { style } = this.shadows[index];
      style.left = `${geometry.lefts[0]}px`;
      style.width = `${geometry.width - geometry.lefts[0]}px`;
      style.top = `${top}px`;
      style.height = `${bottom - top}px`;
      style.boxShadow = shadow ?? '';
    });
  }

  /** A header cell with an element of its own as it stands again atop a page, `top` down its gap. */
  private headerCopy(placed: Placed, top: number, geometry: Geometry): HTMLElement {
    const rows = this.lines!.frozenRows();
    const box = geometry.cell(rectOfCell(placed));
    const element = document.createElement('div');
    element.className = 'ponistra-cell-box';
    const { style } = element;
    style.left = `${box.x}px`;
    style.top = `${top + box.y - geometry.tops[0]}px`;
    style.width = `${box.width}px`;
    style.height = `${Math.min(box.height, geometry.bottom(rows - 1) - box.y)}px`;
    element.append(paperCell(this.lines ?? undefined, placed));
    return element;
  }

  /** The table as paper shows it, its rows measured once it stands in the page. */
  private drawPaper(): void {
    this.paper = new PaperTable(this.node, this.lines ?? undefined);
    this.paper.gap(this.gaps);
    this.sheet.replaceChildren(this.paper.element);
    this.measurePaper();
  }

  /** The paper's rows measured and its pages laid out again: again once the images in its rows
   * are in, which the page counts as laid out only after. */
  private measurePaper(): void {
    const paper = this.paper;
    if (this.gone || !paper) return;
    if (!this.shown()) {
      requestAnimationFrame(() => paper === this.paper && this.measurePaper());
      return;
    }
    const loading = paper.measure();
    repaginate(this.outer);
    if (loading) hold(loading.then(() => paper === this.paper && this.measurePaper()));
  }

  update(node: Node, decorations: readonly Decoration[], inside: DecorationSource): boolean {
    if (node.type !== this.node.type || node.attrs.id !== this.node.attrs.id) return false;
    const reshaped = node !== this.node;
    this.node = node;
    shownBy.set(node, this);
    this.inside = inside;
    const gaps = tableGaps(decorations);
    const regapped =
      gaps.length !== this.gaps.length ||
      gaps.some(
        (each, at) =>
          each.row !== this.gaps[at].row ||
          each.gap !== this.gaps[at].gap ||
          each.header !== this.gaps[at].header,
      );
    this.gaps = gaps;
    const range = this.range();
    if (range !== this.range_) {
      this.range_ = range;
      this.dom.classList.toggle('ponistra-ranged', range !== null);
      this.holdRange();
    }
    if (regapped && !reshaped && this.paper) this.paper.gap(gaps);
    else if (reshaped || regapped) this.refresh(null);
    else this.schedule();
    return true;
  }

  /** Asks where the rows of the cells with a node in the text stand that the browser does not
   * know, as the reading order of the text and the numbering need them; then lays them out. */
  private placeNodes(grid: Grid): void {
    const rows = new Set<string>();
    this.node.forEach((cell) => {
      const row: string = cell.attrs.row;
      if (grid.rowIndex(row) < 0 && !this.placing.has(row)) rows.add(row);
    });
    if (!rows.size) return;
    for (const row of rows) this.placing.add(row);
    this.spec.grids
      .rowPlaces(this.id, [...rows])
      .then(() => {
        if (this.gone) return;
        this.refresh(null);
        this.outer.dispatch(this.outer.state.tr.setMeta(OUTLINED, true));
      })
      .catch(this.spec.fail);
  }

  /** Whether the rect's rows are held, which what writes its cells reads; where not, they are
   * asked for and the user told they are still coming. */
  private loaded(rect: Rect): boolean {
    if (this.lines?.holdsSpan(rect.top, rect.bottom)) return true;
    this.spec.grids.show(this.ranged, this.id, [[rect.top, rect.bottom]]);
    this.spec.fail(new Error(this.spec.label()('table.loading')));
    return false;
  }

  /** The selected cells' rows held, which the commands on them read, as they stand now. */
  private holdRange(): void {
    const rect = this.range_?.rect();
    if (rect) this.spec.grids.show(this.ranged, this.id, [[rect.top, rect.bottom]]);
    else this.spec.grids.forget(this.ranged);
  }

  /** The selected cells' rectangle. */
  private rangeRect(): Rect | null {
    return this.lines ? (this.range_?.rect() ?? null) : null;
  }

  /** The selected cells' rows and columns, else the cursor's cell's. */
  private pickedRect(): Rect | null {
    const rect = this.rangeRect();
    if (rect) return rect;
    const placed = this.current === null ? null : this.placedOf(this.current);
    return placed && rectOfCell(placed);
  }

  /** The selected cells as the clipboard carries them, where their rows are held. */
  copied(range: CellRange): Node | null {
    const lines = this.lines;
    const rect = range.rect();
    if (!lines || !rect || !lines.holdsSpan(rect.top, rect.bottom)) return null;
    const grid = this.spec.grids.grid(this.id)!;
    return copiedTable(this.node, this.layout, grid, rect);
  }

  /** The whole table as the clipboard carries it, where its rows are held. */
  copiedWhole(): Node | null {
    const lines = this.lines;
    const grid = this.spec.grids.grid(this.id);
    if (!lines || !grid || !lines.holdsSpan(0, lines.rowCount - 1)) {
      if (lines) this.spec.grids.show(this.ranged, this.id, [[0, lines.rowCount - 1]]);
      return null;
    }
    return copiedTable(this.node, this.layout, grid, this.layout.whole());
  }

  /** Whether the rows a copy of the range reads are held, asking for them where they are not. */
  readable(range: CellRange): boolean {
    const lines = this.lines;
    const rect = range.rect();
    if (!lines || !rect) return false;
    if (lines.holdsSpan(rect.top, rect.bottom)) return true;
    this.spec.grids.show(this.ranged, this.id, [[rect.top, rect.bottom]]);
    return false;
  }

  /** The selection is drawn on the sheet: the cells' own text, or whole cells marked. */
  setSelection(): void {}

  selectNode(): void {
    this.dom.classList.add('ProseMirror-selectednode');
    this.schedule();
  }

  deselectNode(): void {
    this.dom.classList.remove('ProseMirror-selectednode', 'ponistra-writing');
    this.current = null;
    this.schedule();
  }

  stopEvent(): boolean {
    return true;
  }

  ignoreMutation(): boolean {
    return true;
  }

  destroy(): void {
    this.gone = true;
    if (this.frame) cancelAnimationFrame(this.frame);
    this.unsubscribe();
    this.spec.grids.forget(this);
    this.spec.grids.forget(this.ranged);
    this.observer.disconnect();
    this.measured.disconnect();
    document.removeEventListener('scroll', this.scrolled, { capture: true });
    removeEventListener('resize', this.scrolled);
    this.unscheme();
    document.fonts.removeEventListener('loadingdone', this.themed);
    this.outer.dom.removeEventListener('focusin', this.left);
    tablesIn.get(this.outer)?.delete(this);
    this.inks.destroy();
    for (const view of this.cells.values()) view.destroy();
    this.cells.clear();
  }

  /** The steps of a node cell's change, as steps of the document's. */
  write(cell: CellView, steps: readonly Step[]): void {
    const pos = this.getPos();
    if (pos === undefined || cell.placed.offset === null) return;
    const tr = this.outer.state.tr.setMeta(INNER, true);
    const offset = StepMap.offset(pos + 1 + cell.placed.offset + 1);
    for (const step of steps) {
      const mapped = step.map(offset);
      if (mapped) tr.step(mapped);
    }
    if (tr.docChanged) this.outer.dispatch(tr);
  }

  /** A light cell's element gone once it was left, the sheet drawing it again. */
  closed(cell: CellView): void {
    if (this.cells.get(cell.key) !== cell) return;
    this.cells.delete(cell.key);
    cell.destroy();
    this.schedule();
  }

  /** While a cell is being written in, the document has the table selected: the outline and the
   * others' view of where one is follow it, and it is not drawn as selected. */
  entered(key: string): void {
    const pos = this.getPos();
    if (pos === undefined) return;
    this.dom.classList.add('ponistra-writing');
    this.current = key;
    this.schedule();
    const { state } = this.outer;
    const { selection } = state;
    if (!(selection instanceof NodeSelection) || selection.from !== pos) {
      this.outer.dispatch(state.tr.setSelection(NodeSelection.create(state.doc, pos)));
    }
  }

  private range(): CellRange | null {
    const { selection } = this.outer.state;
    return selection instanceof CellRange && selection.$table.pos === this.getPos()
      ? selection
      : null;
  }

  /** The cell's view: its node's, or a light cell's made for writing in it. */
  openCell(key: string): CellView | null {
    const placed = this.layout.placed(key);
    const geometry = this.laidOut();
    if (!placed || !geometry || this.gone) return null;
    let view = this.cells.get(key);
    if (!view) {
      view = new CellView(this, placed, !placed.node);
      this.cells.set(key, view);
      this.layer.append(view.box);
      if (!view.light) this.measured.observe(view.holder);
      const decorations = placed.node
        ? this.inside.forChild(placed.offset!, placed.node)
        : DecorationSet.empty;
      this.syncCell(view, placed, decorations, true, this.viewBox());
      this.schedule();
    }
    return view;
  }

  /** Where on the sheet a pointer is, in its own pixels. */
  private sheetPoint(event: MouseEvent): { x: number; y: number } {
    const rect = this.grid.getBoundingClientRect();
    const scale = scaleOf(this.grid, rect);
    return { x: (event.clientX - rect.left) / scale, y: (event.clientY - rect.top) / scale };
  }

  /** What a pointer is over: an edge between lines, the headings, or a cell. */
  private hitAt(event: MouseEvent): Hit | null {
    const geometry = this.geometry;
    if (!geometry || !this.grid.contains(event.target as globalThis.Node)) return null;
    const { x, y: pointed } = this.sheetPoint(event);
    const { layout } = this;
    if (!layout.rows || !layout.cols || x > geometry.width || pointed > geometry.height)
      return null;
    if (this.repeatedAt(pointed)) return null;
    const editable = this.outer.editable;
    const headings = this.headingsShown();
    const view = this.painted?.view ?? this.viewBox();
    const at = view ? headingsAt({ view, geometry }) : { x: 0, y: 0 };
    const { shift, bottom } = this.band(view);
    const y = this.unfrozen(pointed, view);
    const banded = y !== pointed;
    const hidden = (row: number) => shift > 0 && !banded && geometry.bottom(row) <= bottom;
    const inLetters =
      headings && pointed >= at.y && pointed < at.y + geometry.top && x >= geometry.side;
    const inNumbers = headings && x >= at.x && x < at.x + geometry.side && y >= geometry.top;
    const inCorner =
      headings &&
      x >= at.x &&
      x < at.x + geometry.side &&
      pointed >= at.y &&
      pointed < at.y + geometry.top;
    const all = layout.whole();
    const col = geometry.colAt(x);
    const row = geometry.rowAt(y);
    const within = x >= geometry.side && y >= geometry.top;
    if (editable && (inLetters || within)) {
      for (const index of [col - 1, col]) {
        if (index < 0 || Math.abs(x - geometry.lefts[index + 1]) > EDGE) continue;
        const placed = inLetters ? null : layout.at(row, index);
        if (placed && placed.col + placed.cols - 1 > index) continue;
        return { kind: 'colEdge', index };
      }
    }
    if (editable && (inNumbers || within) && row >= 0) {
      for (const index of [row - 1, row]) {
        if (index < 0 || hidden(index) || Math.abs(y - geometry.bottom(index)) > EDGE) continue;
        const placed = inNumbers ? null : layout.at(index, col);
        if (placed && placed.row + placed.rows - 1 > index) continue;
        return { kind: 'rowEdge', index };
      }
    }
    if (inCorner) return { kind: 'lines', rect: all };
    if (inLetters) {
      return col < 0 ? null : { kind: 'lines', rect: { ...all, left: col, right: col } };
    }
    if (inNumbers) {
      return row < 0 ? null : { kind: 'lines', rect: { ...all, top: row, bottom: row } };
    }
    if (!within || row < 0 || col < 0) return null;
    if (y > geometry.bottom(row)) return null;
    const placed = layout.at(row, col);
    return placed && { kind: 'cell', key: placed.key };
  }

  private hovered(event: MouseEvent): void {
    if (this.resizing || event.buttons) return;
    const hit = this.hitAt(event);
    const cursor =
      hit?.kind === 'colEdge'
        ? 'col-resize'
        : hit?.kind === 'rowEdge'
          ? 'row-resize'
          : hit?.kind === 'lines'
            ? 'pointer'
            : hit
              ? 'text'
              : '';
    if (this.grid.style.cursor !== cursor) this.grid.style.cursor = cursor;
  }

  private pressed(event: MouseEvent): void {
    if (event.target === this.handle) {
      event.preventDefault();
      event.stopPropagation();
      if (event.button === 0) this.fillFrom();
      return;
    }
    const editing = writing?.formula ? writing : null;
    if (editing && event.target === editing.formula) return;
    const hit = this.hitAt(event);
    if (!hit) {
      if (this.geometry && this.repeatedAt(this.sheetPoint(event).y)) {
        event.preventDefault();
        event.stopPropagation();
      }
      return;
    }
    if (hit.kind === 'colEdge' || hit.kind === 'rowEdge') {
      event.preventDefault();
      event.stopPropagation();
      if (event.button !== 0) return;
      if (hit.kind === 'colEdge') this.resize(hit.index, event);
      else this.resizeRow(hit.index, event);
      return;
    }
    if (hit.kind === 'lines') {
      event.preventDefault();
      event.stopPropagation();
      if (event.button === 0) this.pressedLines(hit.rect, event.shiftKey);
      return;
    }
    const key = hit.key;
    const other = editing?.table !== this;
    const pointable = other ? !!this.lines?.name : key !== editing?.key;
    if (editing?.takes() && pointable && event.button === 0) {
      event.preventDefault();
      event.stopPropagation();
      this.pointFrom(editing, key);
      return;
    }
    const range = this.range_;
    if (event.button !== 0) {
      // A right click on the selected cells keeps them selected, for its menu.
      const rect = this.rangeRect();
      const placed = this.placedOf(key);
      if (range && rect && placed && meets(rectOfCell(placed), rect)) event.preventDefault();
      return;
    }
    if (event.shiftKey) {
      const anchor =
        range?.anchorKey ?? [...this.cells.values()].find((cell) => cell.inner?.hasFocus())?.key;
      if (anchor && anchor !== key) {
        event.preventDefault();
        event.stopPropagation();
        this.select(anchor, key);
      }
      return;
    }
    const known = this.cells.get(key);
    const inside = known?.inner?.dom.contains(event.target as globalThis.Node);
    if (!inside) {
      const cell = this.openCell(key);
      if (cell?.computed) {
        event.preventDefault();
        cell.edit();
      } else if (cell?.formatted && cell.dom.hidden) {
        event.preventDefault();
        cell.focus(Selection.atEnd);
      } else if (cell && !cell.inner?.hasFocus()) {
        event.preventDefault();
        cell.openAt(event.clientX, event.clientY);
      }
    }
    this.drag(key);
  }

  private keyAt(event: MouseEvent): string | null {
    const hit = this.hitAt(event);
    return hit?.kind === 'cell' ? hit.key : null;
  }

  /** Selects the lines pressed, and those dragged over after; while a formula takes a reference,
   * puts in their address instead. */
  private pressedLines(start: Rect, extend: boolean): void {
    const editing = writing?.formula ? writing : null;
    const other = editing?.table !== this;
    const name = this.lines?.name ?? '';
    const pointing = editing?.takes() && (!other || name !== '');
    const from = extend && !pointing ? (this.pickedRect() ?? start) : start;
    const apply = (rect: Rect) => {
      const area = {
        top: Math.min(from.top, rect.top),
        left: Math.min(from.left, rect.left),
        bottom: Math.max(from.bottom, rect.bottom),
        right: Math.max(from.right, rect.right),
      };
      if (pointing) {
        const numbered = this.numbered(area);
        if (numbered) editing!.point(numbered, other ? name : null);
      } else {
        const { layout } = this;
        this.select(layout.at(area.top, area.left)!.key, layout.at(area.bottom, area.right)!.key);
      }
    };
    apply(start);
    const move = (event: MouseEvent) => {
      const over = this.hitAt(event);
      if (over?.kind !== 'lines') return;
      event.preventDefault();
      apply(over.rect);
    };
    this.dom.classList.add('ponistra-ranging');
    const up = () => {
      document.removeEventListener('mousemove', move);
      this.dom.classList.remove('ponistra-ranging');
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up, { once: true });
  }

  /** A click while a formula takes a reference puts in the cell's address, a drag from it the
   * address of the cells between. */
  private pointFrom(editing: CellView, start: string): void {
    const first = this.placedOf(start);
    if (!first) return;
    const table = editing.table === this ? null : (this.lines?.name ?? '');
    const point = (rect: Rect) => {
      const numbered = this.numbered(rect);
      if (numbered) editing.point(numbered, table);
    };
    point(rectOfCell(first));
    let head = start;
    const move = (event: MouseEvent) => {
      const over = this.keyAt(event);
      const last = over && over !== head ? this.placedOf(over) : null;
      if (!last) return;
      head = over!;
      event.preventDefault();
      point(this.layout.between(rectOfCell(first), rectOfCell(last)));
    };
    this.dom.classList.add('ponistra-ranging');
    const up = () => {
      document.removeEventListener('mousemove', move);
      this.dom.classList.remove('ponistra-ranging');
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up, { once: true });
  }

  private drag(start: string): void {
    let head = start;
    const move = (event: MouseEvent) => {
      const over = this.keyAt(event);
      if (!over || over === head) return;
      head = over;
      this.dom.classList.add('ponistra-ranging');
      event.preventDefault();
      this.select(start, over);
    };
    const up = () => {
      document.removeEventListener('mousemove', move);
      this.dom.classList.remove('ponistra-ranging');
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up, { once: true });
  }

  /** Pixels in a character of the table's width, and in the widest table the pane holds. */
  private measures(): { character: number; widest: number } {
    const probe = this.dom.appendChild(document.createElement('div'));
    probe.className = 'ponistra-probe';
    probe.style.width = '100ch';
    const character = probe.offsetWidth / 100;
    probe.style.width = 'calc(100cqi - var(--heading-side))';
    const widest = probe.offsetWidth;
    probe.remove();
    return { character, widest };
  }

  /** The columns' widths in characters, `character` pixels each. */
  private characters(character: number): number[] {
    const geometry = this.geometry;
    const lines = this.lines ?? NONE;
    const drawn = geometry ? (geometry.width - geometry.side) / character : 0;
    return charactersOf(isSized(this.node), lines.cols, lines.widths, drawn, lines.hidden.cols);
  }

  /** The column's edge dragged, as in Excel: the column takes the width, the others keep theirs
   * and the table grows or shrinks. */
  private resize(index: number, event: MouseEvent): void {
    const { character } = this.measures();
    const from = this.characters(character);
    const start = event.clientX;
    const scale = this.scale();
    let widths = from;
    this.resizing = true;
    this.dom.classList.add('ponistra-resizing');
    const move = (moved: MouseEvent) => {
      widths = widened(from, index, from[index] + (moved.clientX - start) / scale / character);
      const drawn = drawnWidths(widths);
      this.showSize(drawn.reduce((total, width) => total + width, 0));
      this.dragged = widths;
      this.relayout();
    };
    const up = () => {
      document.removeEventListener('mousemove', move);
      this.dom.classList.remove('ponistra-resizing');
      this.resizing = false;
      this.dragged = null;
      if (widths !== from) this.setWidths(widths);
      else this.refresh(null);
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up, { once: true });
  }

  /** The column as wide as its widest text, up to the widest table the pane holds. */
  private fit(index: number): void {
    const { character, widest } = this.measures();
    const lines = this.lines;
    const geometry = this.geometry;
    if (!lines || !geometry) return;
    const padding = this.inks.padding();
    let content = 0;
    for (let row = 0; row < this.layout.rows; row++) {
      const placed = this.layout.at(row, index)!;
      if (placed.col !== index || placed.cols !== 1 || placed.row !== row) continue;
      const view = this.cells.get(placed.key);
      if (view) {
        const measure = this.dom.appendChild(document.createElement('div'));
        measure.className = 'ponistra-measure';
        measure.inert = true;
        measure.append(view.face.cloneNode(true));
        content = Math.max(content, measure.offsetWidth);
        measure.remove();
        continue;
      }
      const painted = this.paintedCell(row, index, placed.key, true);
      if (!painted?.text) continue;
      const measurer = this.context;
      measurer.save();
      measurer.font = painted.ink.font;
      const width = measurer.measureText(painted.text).width + painted.ink.start + painted.ink.end;
      measurer.restore();
      content = Math.max(content, width);
    }
    if (!content) return;
    const column = { top: 0, left: index, bottom: 0, right: index };
    const { left, right } = insetsOf(column, 1, this.layout.cols, this.inset());
    const width = Math.min(content + padding.x * 2 + 1 + left + right, widest) / character - SIDES;
    this.setWidths(widened(this.characters(character), index, width));
  }

  private setWidths(widths: readonly number[]): void {
    const pos = this.getPos();
    const lines = this.spec.grids.grid(this.id);
    const { history } = this.spec;
    if (pos === undefined || !lines || !this.spec.write || !this.outer.editable) {
      this.refresh(null);
      return;
    }
    const given = Object.fromEntries(lines.cols.map((col, at) => [col, rounded(widths[at])]));
    const set = () => {
      if (!isSized(this.node)) {
        this.outer.dispatch(this.outer.state.tr.setNodeAttribute(pos, 'sized', true));
      }
      this.operate([{ op: 'grid', table: this.id, widths: given }]);
    };
    if (history) history.together(set);
    else set();
  }

  /** The row's bottom edge dragged: the row is at least as tall as it was dragged to, and never
   * shorter than its text. */
  private resizeRow(index: number, event: MouseEvent): void {
    const geometry = this.geometry;
    if (!geometry) return;
    const start = event.clientY;
    const scale = this.scale();
    const from = geometry.heights[index];
    let height: number | null = null;
    this.resizing = true;
    this.dom.classList.add('ponistra-resizing-rows');
    const heights = Float64Array.from(geometry.heights);
    const move = (moved: MouseEvent) => {
      height = Math.max(from + (moved.clientY - start) / scale, 1);
      heights[index] = height;
      const tops = Float64Array.from(geometry.tops);
      for (let row = index + 1; row < tops.length; row++) {
        tops[row] = geometry.tops[row] + height - from;
      }
      const { side, top, lefts, inset } = geometry;
      this.geometry = new Geometry(side, top, lefts, tops, heights, inset);
      this.grid.style.height = `${this.geometry.height + REACH}px`;
      this.viewed(true);
    };
    const up = () => {
      document.removeEventListener('mousemove', move);
      this.dom.classList.remove('ponistra-resizing-rows');
      this.resizing = false;
      if (height === null) return;
      this.geometry = geometry;
      const fits = this.rowHeights(geometry.lefts)[index];
      this.setHeight(index, height > fits ? Math.round(height * 0.75 * 2) / 2 : null);
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up, { once: true });
  }

  /** The row at least `height` points tall, or as tall as its text with null. */
  private setHeight(index: number, height: number | null): void {
    const lines = this.lines;
    if (!lines) return;
    const row = rowAt(lines, index);
    if ((lines.heights.get(row) ?? null) === height) {
      this.relayout();
      return;
    }
    if (!this.operate([{ op: 'grid', table: this.id, heights: { [row]: height } }]))
      this.relayout();
  }

  /** A double click on a column's edge fits it to its text, on a row's lets it fit its text. */
  private doubled(event: MouseEvent): void {
    const hit = this.hitAt(event);
    if (hit?.kind !== 'colEdge' && hit?.kind !== 'rowEdge') return;
    event.preventDefault();
    event.stopPropagation();
    if (hit.kind === 'colEdge') this.fit(hit.index);
    else this.setHeight(hit.index, null);
  }

  select(anchorKey: string, headKey: string, focus = true): void {
    const pos = this.getPos();
    if (pos === undefined) return;
    const range = this.cellRange(this.outer.state.doc, pos, anchorKey, headKey);
    if (!range) return;
    getSelection()?.removeAllRanges();
    this.outer.dispatch(this.outer.state.tr.setSelection(range));
    if (focus && !this.outer.hasFocus()) this.outer.focus();
  }

  cellRange(doc: Node, pos: number, anchorKey: string, headKey: string): CellRange | null {
    const lines = this.lines;
    const anchor = this.layout.placed(anchorKey);
    const head = this.layout.placed(headKey);
    if (!lines || !anchor || !head) return null;
    const rect = this.layout.between(rectOfCell(anchor), rectOfCell(head));
    return new CellRange(
      doc.resolve(pos),
      anchorKey,
      headKey,
      [rowAt(lines, rect.top), rowAt(lines, rect.bottom)],
      lines.cols.slice(rect.left, rect.right + 1),
      lines,
    );
  }

  /** The cells at `address` chosen and the first brought into view, now or once the grid has
   * come. */
  show(address: string, focus = true): void {
    this.wanted = address;
    this.focusing = focus;
    if (this.lines) this.showWanted();
  }

  private shownFilter = '';

  /** The user's conditions above the table, each opening the filter of its column or taking it
   * off. */
  private showFilter(conditions: readonly Condition[]): void {
    const key = JSON.stringify(conditions);
    if (key === this.shownFilter) return;
    this.shownFilter = key;
    const label = this.spec.label();
    const cols = this.lines?.cols ?? [];
    this.filters.replaceChildren();
    this.filters.hidden = !conditions.length;
    this.filters.setAttribute('aria-label', label('filter.shown'));
    this.filters.setAttribute('role', 'group');
    for (const condition of conditions) {
      const name = columnName(cols.indexOf(condition.col));
      const chip = this.filters.appendChild(document.createElement('span'));
      chip.className = 'ponistra-filter-chip';
      const open = chip.appendChild(document.createElement('button'));
      open.type = 'button';
      open.textContent = `${name}: ${conditionText(condition, label)}`;
      open.title = label('filter.edit');
      open.addEventListener('click', () => this.spec.filtering?.(this.id, condition.col));
      const off = chip.appendChild(document.createElement('button'));
      off.type = 'button';
      off.textContent = '×';
      off.setAttribute('aria-label', `${label('filter.clear')} ${name}`);
      off.addEventListener('click', () => {
        const rest = (this.lines?.filter ?? []).filter((each) => each.col !== condition.col);
        this.spec.grids.filter(this.id, rest).catch(this.spec.fail);
      });
    }
  }

  /** Opens the user's filter of the column. */
  openFilter(col: string): void {
    this.spec.filtering?.(this.id, col);
  }

  /** Whether the user can filter the table. */
  filterable(): boolean {
    return this.spec.filtering !== undefined && this.lines !== null;
  }

  /** The user's filter keeps only the rows whose cell in the column shows what the cell there
   * shows. */
  filterByValue(row: number, col: number): Promise<void> {
    const lines = this.lines;
    const placed = this.layout.at(row, col);
    if (!lines || !placed) return Promise.resolve();
    const text = placed.node
      ? placed.node.textContent
      : (this.paintedCell(row, col, placed.key, true)?.text ?? '');
    const id = lines.cols[col];
    const rest = lines.filter.filter((each) => each.col !== id);
    return this.spec.grids.filter(this.id, [...rest, { col: id, values: [text] }]);
  }

  /** The user's filter of the table taken off. */
  unfilter(): Promise<void> {
    return this.spec.grids.filter(this.id, []);
  }

  private showWanted(): void {
    const rect = rectOfAddress(this.wanted!);
    this.wanted = null;
    if (!rect) return;
    const shown = ++this.shows;
    const { grids } = this.spec;
    grids
      .numberedPlaces(this.id, [rect.top, rect.bottom])
      .then(async ([top, bottom]) => {
        const { layout } = this;
        const anchor = top >= 0 ? layout.at(top, rect.left) : null;
        if (shown !== this.shows || this.gone) return;
        if (top < 0 && this.lines?.plain === false) {
          this.spec.fail(new Error(this.spec.label()('filter.notShown')));
          return;
        }
        if (!anchor) return;
        const last = bottom >= 0 ? bottom : this.lines?.plain ? layout.rows - 1 : top;
        const head = layout.at(last, Math.min(rect.right, layout.cols - 1)) ?? anchor;
        await grids.rowIds(this.id, [anchor.row, head.row]);
        const from = this.layout.at(anchor.row, anchor.col);
        const to = this.layout.at(head.row, head.col);
        if (shown !== this.shows || this.gone || !from || !to) return;
        this.scrollTo(from.key);
        this.select(from.key, to.key, this.focusing);
      })
      .catch(this.spec.fail);
  }

  /** The rectangle of the rows laid out here by the rows' own places, which an address names;
   * null where the browser does not know them. */
  numbered(rect: Rect): Rect | null {
    const top = this.lines?.rowNumber(rect.top);
    const bottom = this.lines?.rowNumber(rect.bottom);
    return top === undefined || bottom === undefined ? null : { ...rect, top, bottom };
  }

  /** The address of the cell laid out there, by its row's own place. */
  addressAt(row: number, col: number): string {
    return `${columnName(col)}${(this.lines?.rowNumber(row) ?? row) + 1}`;
  }

  selectWhole(): void {
    const pos = this.getPos();
    if (pos === undefined) return;
    this.dom.classList.remove('ponistra-writing');
    const { state } = this.outer;
    this.outer.dispatch(state.tr.setSelection(NodeSelection.create(state.doc, pos)));
    this.outer.focus();
  }

  /** Into the table from the text before it, or after it. */
  enter(where: 'first' | 'last' | 'bottom'): void {
    const { layout } = this;
    const placed =
      where === 'first'
        ? layout.first()
        : where === 'last'
          ? layout.last()
          : layout.at(layout.rows - 1, 0);
    if (placed) this.focusCell(placed.key, where === 'first' ? Selection.atStart : Selection.atEnd);
  }

  focusCell(key: string, selection: (doc: Node) => Selection): void {
    this.scrollTo(key);
    this.openCell(key)?.focus(selection);
  }

  /** The cell brought into view, where the sheet holds it. */
  private scrollTo(key: string): void {
    const placed = this.placedOf(key);
    const geometry = this.laidOut();
    if (!placed || !geometry) return;
    const box = geometry.box(rectOfCell(placed));
    const view = this.viewBox();
    const frozen = this.frozen();
    const { shift, bottom } = this.band(view);
    if (shift && placed.row < frozen) return;
    const covered = shift ? bottom - view!.y : 0;
    const wide = Math.min(box.width, view?.width ?? box.width);
    const across = view && box.x >= view.x && box.x + wide <= view.x + view.width;
    if (across && box.y >= view.y + covered && box.y + box.height <= view.y + view.height) return;
    const band = frozen
      ? geometry.bottom(frozen - 1) - (this.headingsShown() ? 0 : geometry.top)
      : 0;
    const top = placed.row < frozen ? box.y : box.y - band;
    const probe = this.layer.appendChild(document.createElement('div'));
    probe.style.cssText = `position:absolute;left:${box.x}px;top:${top}px;width:${wide}px;height:${box.y + box.height - top}px`;
    probe.scrollIntoView({ block: 'nearest' });
    probe.remove();
    this.viewed(true);
  }

  /** To the next cell that way, or out of the table past its edge. */
  move(cell: CellView, dir: Direction): void {
    const next = this.layout.neighbour(cell.placed, dir);
    if (next) {
      this.focusCell(next.key, BACK[dir] ? Selection.atEnd : Selection.atStart);
      return;
    }
    const pos = this.getPos();
    if (pos === undefined) return;
    const { doc } = this.outer.state;
    const back = BACK[dir];
    const selection = Selection.near(
      doc.resolve(back ? pos : pos + this.node.nodeSize),
      back ? -1 : 1,
    );
    this.outer.dispatch(this.outer.state.tr.setSelection(selection).scrollIntoView());
    this.outer.focus();
  }

  extend(cell: CellView, dir: Direction): boolean {
    const next = this.layout.neighbour(cell.placed, dir);
    if (next) this.select(cell.key, next.key);
    return next !== null;
  }

  /** The next cell's text selected, a new row after the last cell. */
  tab(from: string, step: 1 | -1): void {
    const placed = this.placedOf(from);
    if (!placed) return;
    const next = this.layout.neighbour(placed, step > 0 ? 'right' : 'left');
    if (next) {
      this.focusCell(next.key, whole);
      return;
    }
    const lines = this.lines;
    if (step < 0 || !lines || !lines.cols.length) return;
    const row = shortId();
    if (this.operate([{ op: 'lines', table: this.id, axis: 'rows', ids: [row] }])) {
      this.entering = keyOf(row, lines.cols[0]);
    }
  }

  /** The cell to go into once the grid has it, as a new row's first. */
  private set entering(key: string) {
    const unsubscribe = this.spec.grids.subscribe(this.id, () => {
      if (!this.layout.placed(key)) return;
      unsubscribe();
      queueMicrotask(() => this.focusCell(key, whole));
    });
  }

  /** Back to where the command left off: the cell now in the slot of one it removed. */
  focusNear(placed: Placed): void {
    const { layout } = this;
    const found = layout.at(
      Math.min(placed.row, layout.rows - 1),
      Math.min(placed.col, layout.cols - 1),
    );
    if (!this.gone && found) this.focusCell(found.key, Selection.atStart);
    else this.outer.focus();
  }

  pasted(cell: CellView, slice: Slice): boolean {
    const source = loneTable(slice);
    if (source) {
      this.pasteCells(cell.placed.row, cell.placed.col, source);
      return true;
    }
    if (!holdsTableOrNote(slice.content)) return false;
    const inner = cell.open();
    inner.dispatch(inner.state.tr.replaceSelection(forCell(slice)).scrollIntoView());
    return true;
  }

  /** A copied table's cells over the cells from this slot on, the table growing as it needs: its
   * merged cells, its formulas moved as far as the cells were, and its number formats with them;
   * what the cells there held before is taken out. */
  pasteCells(row: number, col: number, source: Node): void {
    const lines = this.lines;
    const from = partLines(source);
    if (!lines || !from || !from.rows.length || !from.cols.length) return;
    const over = Math.min(row + from.rows.length, lines.rowCount) - 1;
    this.spec.grids
      .rowIds(this.id, placesOf(row, over))
      .then((rows) => this.pasteOver(row, col, source, from, rows))
      .catch(this.spec.fail);
  }

  /** The copied table over the rows given, from the slot's on, and as many more as it needs. */
  private pasteOver(row: number, col: number, source: Node, from: KnownLines, over: string[]) {
    const lines = this.lines;
    if (!lines) return;
    const copied: Copied | null = source.attrs.copied;
    const height = from.rows.length;
    const width = from.cols.length;
    const operations: object[] = [];
    const rows = [...over];
    const cols = [...lines.cols];
    for (const [axis, ids, need] of [
      ['rows', rows, height],
      ['cols', cols, col + width],
    ] as const) {
      const added = Array.from({ length: Math.max(0, need - ids.length) }, () => shortId());
      if (!added.length) continue;
      ids.push(...added);
      operations.push({ op: 'lines', table: this.id, axis, ids: added });
    }
    const region = { top: row, left: col, bottom: row + height - 1, right: col + width - 1 };
    const splits = this.layout
      .mergesIn(region.top, region.bottom)
      .filter((merge) => meets(merge, region))
      .map((merge) => {
        const [r, c] = merge.key.split(':');
        return { row: r, col: c, span: { rows: 1, cols: 1 } };
      });
    if (splits.length) operations.push({ op: 'cells', table: this.id, cells: splits });
    const laid = new Layout(from, source);
    const by = copied && { rows: row - copied.origin.row, cols: col - copied.origin.col };
    const cells: object[] = [];
    const shown: Record<string, Shown | null> = {};
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (!laid.starts(y, x)) continue;
        const placed = laid.at(y, x)!;
        const target = { row: rows[y], col: cols[col + x] };
        const item: Record<string, unknown> = {
          ...target,
          ...contentOf(placed.node, placed.key, copied, by),
          ...(copied && { format: copied.formats[placed.key] ?? null }),
        };
        if (placed.rows > 1 || placed.cols > 1)
          item.span = { rows: placed.rows, cols: placed.cols };
        cells.push(item);
        const light = placed.node && lookOf(placed.node);
        shown[keyOf(target.row, target.col)] = light
          ? withoutEmpty({ text: light.text, look: light.look })
          : null;
      }
    }
    operations.push({ op: 'cells', table: this.id, cells });
    if (!this.operate(operations, { table: this.id, cells: new Map(Object.entries(shown)) }))
      return;
    const pos = this.getPos();
    if (pos === undefined) return;
    const anchor = keyOf(rows[0], cols[col]);
    const head = keyOf(rows[height - 1], cols[region.right]);
    const range = new CellRange(
      this.outer.state.doc.resolve(pos),
      anchor,
      head,
      [rows[0], rows[height - 1]],
      cols.slice(region.left, region.right + 1),
      lines,
    );
    this.outer.dispatch(this.outer.state.tr.setSelection(range));
    this.outer.focus();
  }

  /** The cells emptied, each keeping its look and number format, and `content` written into the
   * anchor. */
  clear(range: CellRange, content: Slice = Slice.empty): void {
    const lines = this.lines;
    const rect = range.rect();
    if (!lines || !rect || !this.loaded(rect)) return;
    const cells: object[] = [];
    const shown: Record<string, Shown | null> = {};
    for (const placed of this.layout.cellsIn(rect)) {
      const [row, col] = placed.key.split(':');
      const was = lines.cell(row, col);
      if (placed.key === range.anchorKey && content.size) {
        const blocks = cellBlocks(content.content);
        cells.push({ row, col, blocks: blocks.map((block) => block.toJSON()) });
        const light = lookOf(cellType.create({ row, col }, blocks));
        shown[placed.key] = light ? { text: light.text, look: light.look } : null;
        continue;
      }
      cells.push({ row, col, value: null });
      shown[placed.key] = was?.look || was?.format ? { look: was.look, format: was.format } : null;
    }
    if (cells.length) this.writeCells(cells, shown);
  }

  /** The cells of the range as a state of their own, which a formatting command changes as it
   * would one cell's text; what it changed in them goes to the grid at once. Whole rows or
   * columns are formatted as lines instead, as the cell the range started from shows. */
  rangeEdit(range: CellRange): RangeEdit | null {
    const lines = this.lines;
    const rect = range.rect();
    if (!lines || !rect) return null;
    if (rect.top === 0 && rect.bottom === lines.rowCount - 1) return this.lineEdit(range, 'cols');
    if (range.cols.length === lines.cols.length) return this.lineEdit(range, 'rows');
    if (!lines.holdsSpan(rect.top, rect.bottom)) return null;
    const cells: Node[] = [];
    for (const placed of this.layout.cellsIn(rect)) {
      const [row, col] = placed.key.split(':');
      const shown = lines.cell(row, col);
      cells.push(placed.node ?? lightCell(schema, row, col, shown?.text ?? '', shown?.look));
    }
    const scratch = this.node.type.create(this.node.attrs, cells);
    const doc = schema.topNodeType.create(null, scratch);
    const selection = new CellRange(
      doc.resolve(0),
      range.anchorKey,
      range.headKey,
      range.rows,
      range.cols,
      lines,
    );
    const state = EditorState.create({ doc, selection });
    const apply = (after: Node) => {
      const changed: object[] = [];
      const formulas: object[] = [];
      const shown: Record<string, Shown | null> = {};
      after.firstChild!.forEach((cell, _offset, index) => {
        if (cell.eq(cells[index])) return;
        const { row, col } = cell.attrs;
        const key = keyOf(row, col);
        changed.push({ row, col, blocks: blocksJSON(cell) });
        const light = lookOf(cell);
        const was = lines.cell(row, col);
        if (was?.formula && light) {
          formulas.push({ row, col, formula: was.formula });
          shown[key] = withoutEmpty({ ...was, look: light.look });
          return;
        }
        shown[key] = light ? withoutEmpty({ ...was, text: light.text, look: light.look }) : null;
      });
      if (changed.length) this.writeCells(changed, shown, formulas);
    };
    return { state, apply };
  }

  private lineEdit(range: CellRange, axis: Axis): RangeEdit {
    const lines = this.lines!;
    const [row, col] = range.anchorKey.split(':');
    const node = this.layout.at(lines.rowIndex(row), lines.colIndex(col))?.node;
    const look =
      (node
        ? lookOf(node)?.look
        : (lines.cell(row, col)?.look ??
          lines.lineLooks.rows.get(row) ??
          lines.lineLooks.cols.get(col))) ?? {};
    const scratch = this.node.type.create(this.node.attrs, [lightCell(schema, row, col, '', look)]);
    const doc = schema.topNodeType.create(null, scratch);
    const selection = new CellRange(
      doc.resolve(0),
      range.anchorKey,
      range.anchorKey,
      [row, row],
      [col],
      lines,
    );
    const lookAfter = (after: Node) => lookOf(after.firstChild!.firstChild!)?.look ?? null;
    return {
      state: EditorState.create({ doc, selection }),
      fits: (after) => lookAfter(after) !== null,
      apply: async (after) => {
        const now = lookAfter(after);
        if (!now) throw new Error('A row or a column takes only the look of a light cell');
        const change = lookChange(look, now);
        if (!change) return;
        const rect = range.rect()!;
        const ends =
          axis === 'rows'
            ? await this.rowEnds(rect.top, rect.bottom)
            : this.colEnds(rect.left, rect.right);
        this.operate([{ op: 'looks', table: this.id, axis, ...ends, ...change }]);
      },
    };
  }

  async addLine(axis: Axis, index: number): Promise<void> {
    const lines = this.lines;
    if (!lines) return;
    const [before] =
      axis === 'cols'
        ? lines.cols.slice(index, index + 1)
        : index < lines.rowCount
          ? await this.spec.grids.rowIds(this.id, [index])
          : [];
    this.operate([
      { op: 'lines', table: this.id, axis, ids: [shortId()], ...(before && { before }) },
    ]);
  }

  /** A cell reaching past the lines keeps its slots outside them; one within them goes. */
  async deleteLines(axis: Axis, first: number, last: number): Promise<void> {
    const lines = this.lines;
    if (!lines) return;
    const ends = axis === 'cols' ? this.colEnds(first, last) : await this.rowEnds(first, last);
    this.operate([{ op: 'lines', table: this.id, axis, ...ends, remove: true }]);
  }

  /** The cells' content in reading order in the first, which then spans them all. */
  merge(rect: Rect): void {
    const lines = this.lines;
    if (!lines || !this.loaded(rect)) return;
    const inside = [...this.layout.cellsIn(rect)];
    const content: Node[] = [];
    let filledCells = 0;
    for (const placed of inside) {
      const [row, col] = placed.key.split(':');
      const shown = lines.cell(row, col);
      const node = placed.node ?? lightCell(schema, row, col, shown?.text ?? '', shown?.look);
      if (!filled(node)) continue;
      filledCells++;
      node.forEach((block) => content.push(block));
    }
    const anchor = inside[0];
    if (!anchor) return;
    const [row, col] = anchor.key.split(':');
    const splits = inside
      .filter((placed) => placed !== anchor && (placed.rows > 1 || placed.cols > 1))
      .map((placed) => {
        const [r, c] = placed.key.split(':');
        return { row: r, col: c, span: { rows: 1, cols: 1 } };
      });
    const item: Record<string, unknown> = {
      row,
      col,
      span: { rows: rect.bottom - rect.top + 1, cols: rect.right - rect.left + 1 },
    };
    if (filledCells > 1) item.blocks = content.map((block) => block.toJSON());
    const operations: object[] = [];
    if (splits.length) operations.push({ op: 'cells', table: this.id, cells: splits });
    operations.push({ op: 'cells', table: this.id, cells: [item] });
    if (!this.operate(operations)) return;
    const pos = this.getPos();
    if (pos === undefined) return;
    const range = new CellRange(
      this.outer.state.doc.resolve(pos),
      anchor.key,
      anchor.key,
      [rowAt(lines, rect.top), rowAt(lines, rect.bottom)],
      lines.cols.slice(rect.left, rect.right + 1),
      lines,
    );
    this.outer.dispatch(this.outer.state.tr.setSelection(range));
  }

  split(rect: Rect): void {
    const cells = [...this.layout.cellsIn(rect)]
      .filter((placed) => placed.rows > 1 || placed.cols > 1)
      .map((placed) => {
        const [row, col] = placed.key.split(':');
        return { row, col, span: { rows: 1, cols: 1 } };
      });
    if (cells.length) this.operate([{ op: 'cells', table: this.id, cells }]);
  }

  /** Whether formulas or defined names refer to the table by its name, which it must then keep. */
  referred(): Promise<boolean> {
    return this.spec.grids.referred(this.id);
  }

  /** The table's name, by which formulas refer to it; an empty one takes it away. */
  rename(name: string): void {
    this.operate([{ op: 'grid', table: this.id, name }]);
  }

  /** Whether the cells can be filled, or filled from: none merged. */
  private fillable(rect: Rect): boolean {
    for (const placed of this.layout.cellsIn(rect)) {
      if (placed.rows > 1 || placed.cols > 1) return false;
    }
    return true;
  }

  /** The fill handle at the corner of the selected cells, or of the cell being written in, where
   * they can be filled from. */
  private showHandle(view: Box): void {
    const geometry = this.geometry!;
    const picked = this.pickedRect();
    const fills = this.outer.editable && !!this.spec.write && !writing?.formula;
    if (!picked || !fills || !this.fillable(picked)) {
      this.handle.hidden = true;
      return;
    }
    const box = geometry.box(picked);
    const { shift, bottom } = this.band(view);
    const above = picked.bottom < this.frozen();
    const y = box.y + box.height + (above ? shift : 0);
    const { style } = this.handle;
    style.left = `${box.x + box.width}px`;
    style.top = `${y}px`;
    this.handle.hidden = !above && shift > 0 && y < bottom;
  }

  /** The slot a pointer is over, the nearest one where it is past the rows or the columns. */
  private slotAt(event: MouseEvent): { row: number; col: number } {
    const geometry = this.geometry!;
    const { x, y } = this.sheetPoint(event);
    const row = geometry.rowAt(this.unfrozen(y, this.viewBox()));
    const col = geometry.colAt(x);
    return {
      row: Math.min(geometry.rows - 1, Math.max(0, row)),
      col: Math.min(geometry.cols - 1, Math.max(0, col)),
    };
  }

  /** How far the cells fill towards a slot: down or up to its row, or right or left to its
   * column, whichever it lies further out on, short of the first merged cell on the way. */
  private reach(from: Rect, slot: { row: number; col: number }): Rect | null {
    const out = (at: number, low: number, high: number) =>
      at > high ? at - high : at < low ? at - low : 0;
    const down = out(slot.row, from.top, from.bottom);
    const across = out(slot.col, from.left, from.right);
    if (!down && !across) return null;
    const rows = Math.abs(down) >= Math.abs(across);
    const step = Math.sign(rows ? down : across);
    let edge = rows ? (step > 0 ? from.bottom : from.top) : step > 0 ? from.right : from.left;
    const end = rows ? slot.row : slot.col;
    while (edge !== end) {
      const next = edge + step;
      const line = rows
        ? { ...from, top: next, bottom: next }
        : { ...from, left: next, right: next };
      if (!this.fillable(line)) break;
      edge = next;
    }
    const reached = rows
      ? { ...from, top: Math.min(from.top, edge), bottom: Math.max(from.bottom, edge) }
      : { ...from, left: Math.min(from.left, edge), right: Math.max(from.right, edge) };
    return reached.top === from.top &&
      reached.bottom === from.bottom &&
      reached.left === from.left &&
      reached.right === from.right
      ? null
      : reached;
  }

  /** Fills the selected cells' series, or their copies, on over the cells the handle is dragged
   * to, as the server computes them, and selects the cells filled. */
  private fillFrom(): void {
    const from = this.pickedRect();
    const geometry = this.geometry;
    if (!from || !geometry) return;
    const { layout } = this;
    const key = (row: number, col: number) => layout.at(row, col)!.key;
    this.select(key(from.top, from.left), key(from.bottom, from.right));
    let reached: Rect | null = null;
    const frame = this.grid.appendChild(document.createElement('div'));
    frame.className = 'ponistra-fill-frame';
    frame.hidden = true;
    this.dom.classList.add('ponistra-filling');
    const move = (event: MouseEvent) => {
      event.preventDefault();
      reached = this.reach(from, this.slotAt(event));
      frame.hidden = !reached;
      if (!reached) return;
      const box = geometry.box(reached);
      Object.assign(frame.style, {
        left: `${box.x}px`,
        top: `${box.y}px`,
        width: `${box.width}px`,
        height: `${box.height}px`,
      });
    };
    const up = () => {
      document.removeEventListener('mousemove', move);
      frame.remove();
      this.dom.classList.remove('ponistra-filling');
      const lines = this.lines;
      if (!reached || !lines) return;
      const point = (row: number, col: number) => ({
        row: rowAt(lines, row),
        col: lines.cols[col],
      });
      const until =
        reached.bottom > from.bottom
          ? point(reached.bottom, from.left)
          : reached.top < from.top
            ? point(reached.top, from.left)
            : reached.right > from.right
              ? point(from.top, reached.right)
              : point(from.top, reached.left);
      const filled = this.operate([
        {
          op: 'fill',
          table: this.id,
          from: point(from.top, from.left),
          to: point(from.bottom, from.right),
          until,
        },
      ]);
      if (filled) this.select(key(reached.top, reached.left), key(reached.bottom, reached.right));
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up, { once: true });
  }

  /** What a fill down or right copies and how far: the first line of the selected cells over the
   * rest of them, or where they are one line, the line before them over it. */
  private copying(rect: Rect, axis: Axis): { from: Rect; to: Rect } | null {
    const rows = axis === 'rows';
    const [first, last] = rows ? [rect.top, rect.bottom] : [rect.left, rect.right];
    if (first === last && first === 0) return null;
    const at = first === last ? first - 1 : first;
    const from = rows ? { ...rect, top: at, bottom: at } : { ...rect, left: at, right: at };
    const to = rows ? { ...rect, top: at } : { ...rect, left: at };
    return this.fillable(to) ? { from, to } : null;
  }

  fillsOver(rect: Rect, axis: Axis): boolean {
    return this.copying(rect, axis) !== null;
  }

  /** Copies the first line of the selected cells over the rest, or the line before them over
   * them, formulas moving with each copy. */
  fillOver(rect: Rect, axis: Axis): void {
    const copying = this.copying(rect, axis);
    const lines = this.lines;
    if (!copying || !lines) return;
    const { from, to } = copying;
    const point = (row: number, col: number) => ({ row: rowAt(lines, row), col: lines.cols[col] });
    this.operate([
      {
        op: 'fill',
        table: this.id,
        from: point(from.top, from.left),
        to: point(from.bottom, from.right),
        until: point(to.bottom, to.right),
        copies: true,
      },
    ]);
  }

  /** The first `count` rows stay at the top of the view; none with 0. */
  freeze(count: number): void {
    const lines = this.lines;
    if (!lines) return;
    this.operate([{ op: 'grid', table: this.id, frozen: count ? rowAt(lines, count - 1) : null }]);
  }

  /** Whether the rectangle has a row or a column that way still shown, or one hidden. The rows
   * hidden are not among those the browser lays out, so one lies hidden in the rectangle where
   * its rows' numbers skip one or it reaches an edge past which some lie. */
  hidesIn(axis: 'rows' | 'cols', rect: Rect, hidden: boolean): boolean {
    const lines = this.lines;
    if (!lines) return false;
    if (axis === 'cols') {
      const ids = lines.cols.slice(rect.left, rect.right + 1);
      const count = ids.filter((id) => lines.hidden.cols.has(id)).length;
      return hidden ? count > 0 : count < ids.length;
    }
    if (!hidden || lines.plain) return !hidden && lines.rowCount > 0;
    const top = lines.rowNumber(rect.top);
    const bottom = lines.rowNumber(rect.bottom);
    if (top === undefined || bottom === undefined) return true;
    return (
      bottom - top > rect.bottom - rect.top ||
      (rect.top === 0 && top > 0) ||
      rect.bottom === lines.rowCount - 1
    );
  }

  /** Hides the rows or the columns of the rectangle, or shows again those hidden in it; at an
   * edge of the table, the rows hidden past it too. */
  hide(axis: 'rows' | 'cols', rect: Rect, hidden: boolean): void {
    const lines = this.lines;
    if (!lines) return;
    if (axis === 'cols') {
      const ids = lines.cols
        .slice(rect.left, rect.right + 1)
        .filter((id) => lines.hidden.cols.has(id) !== hidden);
      if (!ids.length) return;
      const given = Object.fromEntries(ids.map((id) => [id, hidden]));
      this.operate([{ op: 'grid', table: this.id, hidden: { cols: given } }]);
      return;
    }
    const from = lines.rowId(rect.top);
    const to = lines.rowId(rect.bottom);
    if ((from === undefined || to === undefined) && !this.loaded(rect)) return;
    this.operate([
      {
        op: 'lines',
        table: this.id,
        axis: 'rows',
        hidden,
        ...((hidden || rect.top > 0) && { from }),
        ...((hidden || rect.bottom < lines.rowCount - 1) && { to }),
      },
    ]);
  }

  /** The table in one of our designs, its switches kept; or in none. */
  designIn(id: string | null): void {
    const pos = this.getPos();
    if (pos === undefined) return;
    const on = this.design.whole?.on;
    const designs = id === null ? null : [{ ...ours(id), ...(on && { on }) }];
    this.outer.dispatch(this.outer.state.tr.setNodeAttribute(pos, 'designs', designs));
  }

  /** A part of the table's design turned on or off, in each of its designs. */
  toggle(part: Switch): void {
    const pos = this.getPos();
    const designs = designsIn(this.node.attrs.designs);
    if (pos === undefined || !designs) return;
    const on = !designs[0].on?.[part];
    const switched = designs.map((design) => ({ ...design, on: { ...design.on, [part]: on } }));
    this.outer.dispatch(this.outer.state.tr.setNodeAttribute(pos, 'designs', switched));
  }

  /** Which of our designs the table is in, by its id; null where it is in none of them. */
  get ours(): string | null {
    const designs = designsIn(this.node.attrs.designs);
    const name = designs?.length === 1 ? designs[0].name : undefined;
    return name && Object.hasOwn(CATALOGUE, name) ? name : null;
  }

  remove(): void {
    const pos = this.getPos();
    if (pos === undefined) return;
    const { outer } = this;
    const tr = outer.state.tr.delete(pos, pos + this.node.nodeSize);
    tr.setSelection(Selection.near(tr.doc.resolve(Math.min(pos, tr.doc.content.size))));
    outer.dispatch(tr.scrollIntoView());
    outer.focus();
  }

  /** A copy of the table below it, as Excel pastes values: the server's value in each formula's
   * place, and the next free name after its own. */
  duplicateAsValues(): void {
    const id = shortId();
    if (this.operate([{ op: 'copy', table: this.id, id, values: true }])) {
      awaited.set(id, { then: 'select' });
    }
  }
}

/** A cell's content as an operation writes it: its formula moved `by` as far as it was, the
 * text typed into it where it shows a value, its text alone where that is all it holds, or its
 * blocks. */
export function contentOf(
  node: Node | null,
  key: string,
  copied: Copied | null,
  by: { rows: number; cols: number } | null,
): Record<string, unknown> {
  const formula = copied?.formulas[key];
  if (formula) return { formula, ...(by && (by.rows || by.cols) ? { by } : {}) };
  const typed = copied?.typed?.[key];
  if (typed !== undefined && !typed.startsWith('=')) return { value: typed || null };
  if (!node) return { value: null };
  const light = lookOf(node);
  if (light && !light.look.marks && !light.look.attrs && !light.text.startsWith('=')) {
    return { value: light.text || null };
  }
  return { blocks: cellBlocks(node.content).map((block) => block.toJSON()) };
}

/** What a formatting command changed of a look: each mark given, or taken off as null, and each
 * paragraph attribute set, or taken off as null; none where it changed nothing. */
function lookChange(was: Look, now: Look): Partial<Record<keyof Look, Attrs>> | null {
  const change: Partial<Record<keyof Look, Attrs>> = {};
  for (const part of ['marks', 'attrs'] as const) {
    const [before, after]: Attrs[] = [was[part] ?? {}, now[part] ?? {}];
    const changed: Attrs = {};
    for (const name of new Set([...Object.keys(before), ...Object.keys(after)])) {
      if (JSON.stringify(before[name]) !== JSON.stringify(after[name])) {
        changed[name] = after[name] ?? null;
      }
    }
    if (Object.keys(changed).length) change[part] = changed;
  }
  return Object.keys(change).length ? change : null;
}

function withoutEmpty(cell: Shown): Shown {
  const kept: Shown = {};
  for (const [name, value] of Object.entries(cell) as [keyof Shown, never][]) {
    if (value !== undefined && value !== '') kept[name] = value;
  }
  return kept;
}

function within(inner: Box, outer: Box): boolean {
  return (
    inner.x >= outer.x &&
    inner.y >= outer.y &&
    inner.x + inner.width <= outer.x + outer.width &&
    inner.y + inner.height <= outer.y + outer.height
  );
}

/** The element's ancestors that cut off what lies outside them. */
function clipsOf(element: HTMLElement): HTMLElement[] {
  const found: HTMLElement[] = [];
  for (let at = element.parentElement; at; at = at.parentElement) {
    const style = getComputedStyle(at);
    if (`${style.overflowX} ${style.overflowY}` !== 'visible visible') found.push(at);
  }
  return found;
}

/** The table a command applies to and the rows and columns of it. */
