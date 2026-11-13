import { DOMSerializer, Fragment, type Node, type ResolvedPos, Slice } from 'prosemirror-model';
import {
  EditorState,
  Plugin,
  PluginKey,
  Selection,
  SelectionRange,
  TextSelection,
  type Transaction,
} from 'prosemirror-state';
import type { Mappable } from 'prosemirror-transform';
import {
  DecorationSet,
  type DecorationSource,
  EditorView,
  type NodeViewConstructor,
} from 'prosemirror-view';
import { ySyncPluginKey } from 'y-prosemirror';
import type * as Y from 'yjs';
import type { MessageKey } from '../i18n/hr';
import type { DocumentLocale } from '../tree';
import { folded, type GridSource, type Written } from './grids';
import { schema } from './schema';
import type { Entry, History } from './history';
import type { Lines, Rect } from './tables';
import type { CellView } from './cellView';
import type { TableView } from './tableView';

export const { table, cell: cellType, paragraph, footnote, chart } = schema.nodes;
export const serializer = DOMSerializer.fromSchema(schema);
export const FROM_OUTSIDE = 'fromOutside';
/** Whole cells emptied, by the range of them. */
export const CLEARED = 'clearedCells';
export const POINTS = 96 / 72;

export type Direction = 'up' | 'down' | 'left' | 'right';
export const BACK: Record<Direction, boolean> = { up: true, left: true, down: false, right: false };
export const ARROWS: Record<string, Direction> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
};

/** Carries out the operations on the grids of the editor's tab, after its own edits to the text;
 * the cells written show at once. */
export type Write = (operations: object[], written?: Written) => void;

/** Cells as a state of their own for a formatting command, and what writes what it changed in
 * them; `fits` says whether a change is one their lines can take. */
export interface RangeEdit {
  state: EditorState;
  apply: (doc: Node) => void | Promise<void>;
  fits?: (doc: Node) => boolean;
}

export interface TablesSpec {
  doc: Y.Doc;
  grids: GridSource;
  /** Null where the tables are only read. */
  write: Write | null;
  /** What makes an edit of the text and of grids one change to take back. */
  history: History | null;
  /** The tab the editor writes, null for a header's or a footer's. */
  tab: () => string | null;
  /** Every row an element of its own, for the browser to break pages between. */
  paper?: boolean;
  /** The plugins of each cell's own editor. */
  inner: Plugin[];
  nodeViews: Record<string, NodeViewConstructor>;
  /** A cell's editor took the focus or changed its state while it has it. */
  onCell: (view: EditorView) => void;
  /** Opens the user's filter of the table's column, where the user can filter. */
  filtering?: (table: string, col: string) => void;
  label: () => (key: MessageKey) => string;
  /** The document's language, in which its formulas are written. */
  locale: () => DocumentLocale;
  fail: (error: unknown) => void;
}

export const key = new PluginKey('tables');

export function specOf(state: EditorState): TablesSpec {
  return (key.get(state)!.spec as unknown as { tables: TablesSpec }).tables;
}

export function remote(transaction: Transaction): boolean {
  return Boolean(transaction.getMeta(ySyncPluginKey)?.isChangeOrigin);
}

export function positionOf(doc: Node, id: string): number | null {
  let found: number | null = null;
  doc.forEach((node, offset) => {
    if (node.type === table && node.attrs.id === id) found = offset;
  });
  return found;
}

/** The table of the text an address leads into: the one of the block it comes with, else the one
 * its table's name names, else the first. */
export function tableIn(
  doc: Node,
  grids: GridSource,
  block: string | null,
  name: string | null,
): string | null {
  let found: string | null = null;
  doc.forEach((node) => {
    if (found !== null || node.type !== table) return;
    const id = node.attrs.id as string;
    const named = name !== null && folded(grids.grid(id)?.name ?? '') === folded(name);
    if (block === null ? name === null || named : id === block) found = id;
  });
  return found;
}

export function blockAt(doc: Node, id: string): number | null {
  let found: number | null = null;
  doc.forEach((node, offset) => {
    if (node.attrs.id === id) found = offset;
  });
  return found;
}

function rangesOf(
  $table: ResolvedPos,
  lines: Lines,
  rows: readonly [string, string],
  cols: readonly string[],
): SelectionRange[] {
  const top = lines.rowIndex(rows[0]);
  const bottom = lines.rowIndex(rows[1]);
  const inCols = new Set(cols);
  const ranges: SelectionRange[] = [];
  $table.nodeAfter!.forEach((cell, offset) => {
    const at = lines.rowIndex(cell.attrs.row);
    if (top < 0 || at < top || at > bottom || !inCols.has(cell.attrs.col)) return;
    const start = $table.pos + 1 + offset;
    ranges.push(
      new SelectionRange(
        $table.doc.resolve(start + 1),
        $table.doc.resolve(start + cell.nodeSize - 1),
      ),
    );
  });
  // Selection's own default would span the whole table, and formatting would reach every cell.
  return ranges.length ? ranges : [new SelectionRange($table, $table)];
}

function same(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

/** The table views by the node each was last given, which a range of cells copies from. */
export const shownBy = new WeakMap<Node, TableView>();

/** Whole cells of one table: the rows and columns between the cell the selection started in and
 * the one it reached, the rows by the first and the last, so that a row put in between joins
 * them. What is done to the selection is done to each of its cells. */
export class CellRange extends Selection {
  constructor(
    readonly $table: ResolvedPos,
    readonly anchorKey: string,
    readonly headKey: string,
    readonly rows: readonly [string, string],
    readonly cols: readonly string[],
    readonly lines: Lines,
  ) {
    // Spanning the table in the page's own selection, which stays hidden, lets the browser copy
    // and cut it.
    super(
      $table,
      $table.doc.resolve($table.pos + $table.nodeAfter!.nodeSize),
      rangesOf($table, lines, rows, cols),
    );
  }

  get table(): Node {
    return this.$table.nodeAfter!;
  }

  /** Where the cells stand now, null where the first or the last row or every column is gone. */
  rect(): Rect | null {
    const { lines } = this;
    const top = lines.rowIndex(this.rows[0]);
    const bottom = lines.rowIndex(this.rows[1]);
    const cols = this.cols.map((id) => lines.colIndex(id)).filter((index) => index >= 0);
    if (top < 0 || bottom < 0 || !cols.length) return null;
    return { top, left: Math.min(...cols), bottom, right: Math.max(...cols) };
  }

  /** Whole cells, held even where none of them has a node. */
  get empty(): boolean {
    return false;
  }

  map(doc: Node, mapping: Mappable): Selection {
    const id = this.table.attrs.id;
    const mapped = mapping.map(this.$table.pos, 1);
    const pos = doc.nodeAt(mapped)?.attrs.id === id ? mapped : positionOf(doc, id);
    if (pos === null) return Selection.near(doc.resolve(Math.min(mapped, doc.content.size)));
    const { anchorKey, headKey, rows, cols, lines } = this;
    return new CellRange(doc.resolve(pos), anchorKey, headKey, rows, cols, lines);
  }

  eq(other: Selection): boolean {
    return (
      other instanceof CellRange &&
      other.$table.pos === this.$table.pos &&
      other.anchorKey === this.anchorKey &&
      other.headKey === this.headKey &&
      other.lines === this.lines &&
      same(other.rows, this.rows) &&
      same(other.cols, this.cols)
    );
  }

  /** The cells as a table of their own, each showing what it shows here, with what computes it. */
  content(): Slice {
    const view = shownBy.get(this.table);
    const copied = view?.copied(this);
    return copied ? new Slice(Fragment.from(copied), 0, 0) : Slice.empty;
  }

  /** Emptied, each keeping its look and number format, as Word and Excel keep them; the content
   * written into the first. */
  replace(tr: Transaction, content: Slice = Slice.empty): void {
    tr.setMeta(CLEARED, { view: shownBy.get(this.table), range: this, content });
  }

  replaceWith(tr: Transaction, node: Node): void {
    this.replace(tr, new Slice(Fragment.from(node), 0, 0));
  }

  toJSON() {
    const { anchorKey: anchor, headKey: head, rows, cols } = this;
    return { type: 'cells', table: this.$table.pos, anchor, head, rows, cols };
  }

  static fromJSON(
    doc: Node,
    json: { table: number; anchor: string; head: string; rows: [string, string]; cols: string[] },
  ): CellRange {
    const $table = doc.resolve(json.table);
    const lines = $table.nodeAfter && shownBy.get($table.nodeAfter)?.lines;
    if (!lines) throw new RangeError('A range of cells is read only over a table shown');
    return new CellRange($table, json.anchor, json.head, json.rows, json.cols, lines);
  }
}

CellRange.prototype.visible = false;
Selection.jsonID('cells', CellRange);

/** What a cell can hold of the content: the cells of a table in turn, a note's text in brackets. */
function cellContent(fragment: Fragment): Fragment {
  const nodes: Node[] = [];
  fragment.forEach((node) => {
    if (node.type === table) {
      node.forEach((cell) => cellContent(cell.content).forEach((block) => nodes.push(block)));
    } else if (node.type === footnote) {
      nodes.push(schema.text(`[${node.textContent}]`, node.marks));
    } else {
      nodes.push(node.isLeaf ? node : node.copy(cellContent(node.content)));
    }
  });
  return Fragment.fromArray(nodes);
}

export function forCell(slice: Slice): Slice {
  return new Slice(cellContent(slice.content), slice.openStart, slice.openEnd);
}

/** The content as blocks a cell holds. */
export function cellBlocks(fragment: Fragment): Node[] {
  const content = cellContent(fragment);
  if (content.firstChild?.isInline) return [paragraph.create(null, content)];
  const blocks: Node[] = [];
  content.forEach((block) => blocks.push(block));
  return blocks;
}

export function holdsTableOrNote(fragment: Fragment): boolean {
  let found = false;
  fragment.descendants((node) => {
    found ||= node.type === table || node.type === footnote;
    return !found;
  });
  return found;
}

export function loneTable(slice: Slice): Node | null {
  const { firstChild } = slice.content;
  return slice.content.childCount === 1 && firstChild?.type === table ? firstChild : null;
}

/** A cell the schema draws as its editor would: text blocks of text alone, with no list marker,
 * box or image, which the editor's plugins and views draw. */
export function drawable(node: Node): boolean {
  let plain = true;
  node.forEach((block) => {
    if (!block.isTextblock || block.attrs.list) plain = false;
    else
      block.forEach((inline) => {
        if (!inline.isText) plain = false;
      });
  });
  return plain;
}

export function decorated(source: DecorationSource): boolean {
  let found = false;
  source.forEachSet((set) => {
    if (set.find().length) found = true;
  });
  return found;
}

export function sameSource(a: DecorationSource, b: DecorationSource): boolean {
  const left: DecorationSet[] = [];
  const right: DecorationSet[] = [];
  a.forEachSet((set) => left.push(set));
  b.forEachSet((set) => right.push(set));
  return left.length === right.length && left.every((set, index) => set === right[index]);
}

/** What makes the cell's editor show the node: attributes alone where only they differ, so the
 * cursor stays where it was. */
export function towards(state: EditorState, target: Node): Transaction | null {
  const tr = state.tr;
  for (let last = -1; ;) {
    const start = target.content.findDiffStart(tr.doc.content);
    if (start === null) break;
    const from = tr.doc.nodeAt(start);
    const to = target.nodeAt(start);
    if (start !== last && from && to && !from.isText && !to.isText && from.content.eq(to.content)) {
      tr.setNodeMarkup(start, to.type, to.attrs, to.marks);
      last = start;
      continue;
    }
    let { a: endA, b: endB } = target.content.findDiffEnd(tr.doc.content)!;
    const overlap = start - Math.min(endA, endB);
    if (overlap > 0) {
      endA += overlap;
      endB += overlap;
    }
    tr.replace(start, endB, target.slice(start, endA));
    break;
  }
  return tr.docChanged ? tr.setMeta(FROM_OUTSIDE, true) : null;
}

export function atEdge(view: EditorView, dir: Direction): boolean {
  const { selection, doc } = view.state;
  const index = selection.$head.index(0);
  if (BACK[dir] ? index > 0 : index < doc.childCount - 1) return false;
  return view.endOfTextblock(dir);
}

export function whole(doc: Node): Selection {
  return TextSelection.between(Selection.atStart(doc).$from, Selection.atEnd(doc).$to);
}

export const owners = new WeakMap<EditorView, CellView>();
export const boxes = new WeakMap<Element, CellView>();
export const views = new WeakMap<Element, TableView>();
/** Each editor's tables, which draw their headings again while a formula takes references. */
export const tablesIn = new WeakMap<EditorView, Set<TableView>>();
/** A table asked of the server and not yet shown: the paragraph holding a pasted one's place
 * until it stands there, taken out as part of the change that pasted it, and where to go once its
 * grid comes. */
interface Awaited {
  holder?: { id: string; change: Entry | null };
  then?: 'first' | 'select';
}
export const awaited = new Map<string, Awaited>();

export function pointingChanged(outer: EditorView): void {
  for (const each of tablesIn.get(outer) ?? []) each.schedule();
}

/** The cell whose own editor this is. */
export function cellOf(view: EditorView): CellView | null {
  return owners.get(view) ?? null;
}

/** The editor of the cell an event happened in. */
export function cellViewAt(target: EventTarget | null): EditorView | null {
  const box = target instanceof Element ? target.closest('[data-cell]') : null;
  const cell = box ? boxes.get(box) : undefined;
  return cell && !cell.gone ? cell.open() : null;
}

/** The document's editor, which outlives the editors of its cells. */
export function outerOf(view: EditorView): EditorView {
  return owners.get(view)?.table.outer ?? view;
}

/** The editor of the view's cell that has the focus, as one has once a table is put in. */
export function focusedCell(view: EditorView): EditorView | null {
  const inner = cellViewAt(view.dom.ownerDocument.activeElement);
  return inner && outerOf(inner) === view ? inner : null;
}

export function tableViewAt(view: EditorView, pos: number): TableView | null {
  const dom = view.nodeDOM(pos);
  return dom instanceof Element ? (views.get(dom) ?? null) : null;
}
