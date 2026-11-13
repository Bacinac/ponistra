import { keymap } from 'prosemirror-keymap';
import { Fragment, type Node, Slice } from 'prosemirror-model';
import {
  type Command,
  EditorState,
  NodeSelection,
  Plugin,
  Selection,
  TextSelection,
  type Transaction,
} from 'prosemirror-state';
import { Decoration, DecorationSet, EditorView } from 'prosemirror-view';
import { shortId } from './blocks';
import { columnName } from './formulas';
import type { Change, GridSource } from './grids';
import { chartOf, listOf } from './schema';
import { designsIn } from './design';
import {
  type Copied,
  isSized,
  Layout,
  nameProblem,
  OUTLINED,
  partLines,
  type Rect,
  rectOfCell,
} from './tables';
import {
  ARROWS,
  atEdge,
  awaited,
  BACK,
  cellOf,
  CellRange,
  chart,
  CLEARED,
  type Direction,
  key,
  loneTable,
  owners,
  paragraph,
  positionOf,
  type RangeEdit,
  remote,
  specOf,
  table,
  type TablesSpec,
  tableViewAt,
} from './tableBase';
import { contentOf, TableView } from './tableView';

export interface Target {
  table: TableView;
  rect: Rect;
  /** Whole cells are selected, rather than text in one of them. */
  range: boolean;
}

export function targetOf(view: EditorView): Target | null {
  const cell = cellOf(view);
  if (cell) {
    const placed = cell.gone || cell.table.gone ? null : cell.table.placedOf(cell.key);
    return placed ? { table: cell.table, rect: rectOfCell(placed), range: false } : null;
  }
  const { selection } = view.state;
  const pos =
    selection instanceof CellRange
      ? selection.$table.pos
      : selection instanceof NodeSelection && selection.node.type === table
        ? selection.from
        : null;
  const found = pos === null ? null : tableViewAt(view, pos);
  if (!found || !found.lines) return null;
  const { layout } = found;
  if (!(selection instanceof CellRange))
    return { table: found, rect: layout.whole(), range: false };
  const rect = selection.rect();
  return rect && { table: found, rect, range: true };
}

/** The selected cells as a state of their own for a formatting command, and what writes the
 * cells it changed; null where no cells are selected. */
export function rangeEdit(view: EditorView): RangeEdit | null {
  const { selection } = view.state;
  if (!(selection instanceof CellRange)) return null;
  return tableViewAt(view, selection.$table.pos)?.rangeEdit(selection) ?? null;
}

/** The cell at `address` of the table chosen and brought into view, as a search hit or a link
 * leads to it. */
export function showCell(view: EditorView, table: string, address: string, focus = true): void {
  const at = positionOf(view.state.doc, table);
  if (at !== null) tableViewAt(view, at)?.show(address, focus);
}

/** The cell brought into view and chosen wherever its row stands, as a hit of a search in the
 * tab leads to it, the focus left where it is. */
export function revealCell(view: EditorView, table: string, row: string, col: string): void {
  const { grids, fail } = specOf(view.state);
  grids
    .rowPlaces(table, [row])
    .then(([y]) => {
      const grid = grids.grid(table);
      const x = grid?.colIndex(col) ?? -1;
      const number = y >= 0 ? grid?.rowNumber(y) : undefined;
      if (!view.isDestroyed && number !== undefined && x >= 0)
        showCell(view, table, `${columnName(x)}${number + 1}`, false);
    })
    .catch(fail);
}

/** What writes the editor's tables and reads their grids, and the tab it writes. */
export function tablesOf(state: EditorState): Pick<TablesSpec, 'write' | 'grids' | 'tab'> {
  const { write, grids, tab } = specOf(state);
  return { write, grids, tab };
}

/** Back into the cell a command was given in, or the one now in its slot once it is gone. */
export function refocusCell(view: EditorView): boolean {
  const cell = owners.get(view);
  if (!cell) return false;
  if (cell.gone) cell.table.focusNear(cell.placed);
  else if (cell.inner === view) view.focus();
  else cell.focus(Selection.atEnd);
  return true;
}

/** Keys of a cell's own editor that lead out of it: arrows past its edges, Tab, Escape. */
export function cellKeys(): Plugin {
  const at = (view: EditorView | undefined) => (view ? (owners.get(view) ?? null) : null);
  const arrow =
    (dir: Direction): Command =>
    (state, _dispatch, view) => {
      const cell = at(view);
      if (!cell || !state.selection.empty || !atEdge(view!, dir)) return false;
      cell.table.move(cell, dir);
      return true;
    };
  const extend =
    (dir: Direction): Command =>
    (_state, _dispatch, view) => {
      const cell = at(view);
      return Boolean(cell && atEdge(view!, dir) && cell.table.extend(cell, dir));
    };
  const tab =
    (step: 1 | -1): Command =>
    (state, _dispatch, view) => {
      const cell = at(view);
      if (!cell) return false;
      const { $from, empty } = state.selection;
      // As in Word: at the start of a list item Tab changes its level, elsewhere it leads on.
      if (empty && $from.parentOffset === 0 && listOf($from.parent)) return false;
      cell.table.tab(cell.key, step);
      return true;
    };
  return keymap({
    ArrowUp: arrow('up'),
    ArrowDown: arrow('down'),
    ArrowLeft: arrow('left'),
    ArrowRight: arrow('right'),
    'Shift-ArrowUp': extend('up'),
    'Shift-ArrowDown': extend('down'),
    'Shift-ArrowLeft': extend('left'),
    'Shift-ArrowRight': extend('right'),
    Tab: tab(1),
    'Shift-Tab': tab(-1),
    Escape: (_state, _dispatch, view) => {
      const cell = at(view);
      if (!cell) return false;
      if (cell.light) cell.cancel();
      else cell.table.selectWhole();
      return true;
    },
  });
}

function onRange(view: EditorView, range: CellRange, event: KeyboardEvent): boolean {
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  const found = tableViewAt(view, range.$table.pos);
  if (!found) return false;
  const dir = ARROWS[event.key];
  if (dir && event.shiftKey) {
    const head = found.placedOf(range.headKey);
    const next = head && found.layout.neighbour(head, dir);
    const extended =
      next && found.cellRange(view.state.doc, range.$table.pos, range.anchorKey, next.key);
    if (extended) view.dispatch(view.state.tr.setSelection(extended));
    return true;
  }
  if (dir || event.key === 'Enter') {
    found.focusCell(range.headKey, Selection.atEnd);
    return true;
  }
  switch (event.key) {
    case 'Escape':
      view.dispatch(
        view.state.tr.setSelection(NodeSelection.create(view.state.doc, range.$table.pos)),
      );
      return true;
    case 'Backspace':
    case 'Delete':
      if (view.editable) view.dispatch(view.state.tr.deleteSelection());
      return true;
    case 'Tab':
      found.tab(range.headKey, event.shiftKey ? -1 : 1);
      return true;
  }
  return false;
}

function keyed(view: EditorView, event: KeyboardEvent): boolean {
  const { selection } = view.state;
  if (selection instanceof CellRange) return onRange(view, selection, event);
  if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return false;
  if (selection instanceof NodeSelection && selection.node.type === table) {
    if (event.key !== 'Enter') return false;
    tableViewAt(view, selection.from)?.enter('first');
    return true;
  }
  const dir = ARROWS[event.key];
  if (!dir || !(selection instanceof TextSelection) || !selection.empty) return false;
  const { $head } = selection;
  if ($head.depth !== 1 || !view.endOfTextblock(dir)) return false;
  const back = BACK[dir];
  const edge = back ? $head.before(1) : $head.after(1);
  const next = back ? view.state.doc.resolve(edge).nodeBefore : view.state.doc.nodeAt(edge);
  if (next?.type !== table) return false;
  const found = tableViewAt(view, back ? edge - next.nodeSize : edge);
  found?.enter(dir === 'up' ? 'bottom' : back ? 'last' : 'first');
  return Boolean(found);
}

/** Typing over whole cells empties them and writes in the first. */
function typed(view: EditorView, text: string): boolean {
  const { selection } = view.state;
  if (selection instanceof NodeSelection && selection.node.type === table) return true;
  if (!(selection instanceof CellRange)) return false;
  const found = tableViewAt(view, selection.$table.pos);
  if (!found) return true;
  found.clear(selection);
  const cell = found.openCell(selection.anchorKey);
  if (cell && text.startsWith('=')) cell.edit(text);
  else if (cell) {
    cell.focus(Selection.atStart);
    cell.replaceText(text);
  }
  return true;
}

/** A copied table over the selected cells, from their first; other content into the first. */
function pastedOver(view: EditorView, slice: Slice): boolean {
  const { selection } = view.state;
  if (!(selection instanceof CellRange)) return pastedTables(view, slice);
  const target = targetOf(view);
  const source = loneTable(slice);
  if (target && source) target.table.pasteCells(target.rect.top, target.rect.left, source);
  else view.dispatch(view.state.tr.replaceSelection(slice).scrollIntoView());
  return true;
}

/** A free name for a table of the document, beside the tables named before it in one paste: the
 * one given, else after it the first number not taken, as the server names a copy; none where
 * that is no longer a name. */
function freeName(source: GridSource, name: string, given: Set<string>): string {
  if (!name) return '';
  const taken = (each: string) => source.named(each) !== null || given.has(each.toUpperCase());
  let found = name;
  for (let number = 2; taken(found); number++) found = `${name} (${number})`;
  if (found !== name && nameProblem(source, '', found) === 'invalid') return '';
  given.add(found.toUpperCase());
  return found;
}

/** A copied table as the server makes one: its rows of cells, its lines' sizes and its look. */
function tableOperation(
  source: GridSource,
  given: Set<string>,
  copy: Node,
  at: object,
  id: string,
): object {
  const lines = partLines(copy)!;
  const laid = new Layout(lines, copy);
  const copied: Copied | null = copy.attrs.copied;
  const rows: unknown[][] = [];
  for (let y = 0; y < laid.rows; y++) {
    const row: unknown[] = [];
    for (let x = 0; x < laid.cols; x++) {
      if (!laid.starts(y, x)) {
        row.push(null);
        continue;
      }
      const placed = laid.at(y, x)!;
      const content = contentOf(placed.node, placed.key, copied, null);
      const format = copied?.formats[placed.key];
      const span =
        placed.rows > 1 || placed.cols > 1 ? { rows: placed.rows, cols: placed.cols } : null;
      if (!format && !span && 'value' in content) row.push(content.value);
      else row.push({ ...content, ...(format && { format }), ...(span && { span }) });
    }
    rows.push(row);
  }
  const name = freeName(source, lines.name, given);
  const designs = designsIn(copy.attrs.designs);
  return {
    op: 'table',
    at,
    id,
    rowIds: lines.rows,
    colIds: lines.cols,
    rows,
    sized: isSized(copy),
    ...(designs ? { designs } : { design: 'plain' }),
    widths: lines.cols.map((col) => lines.widths.get(col) ?? null),
    heights: lines.rows.map((row) => lines.heights.get(row) ?? null),
    ...(name && { name }),
  };
}

/** The slice in place of the selection, each copied table in it made by the server before a
 * paragraph holding its place, which goes once the table stands there; false where it holds no
 * table. The text and the tables are one change to take back. */
export function pastedTables(view: EditorView, slice: Slice, enter = false): boolean {
  const spec = specOf(view.state);
  const tables: { holder: string; node: Node }[] = [];
  const made: string[] = [];
  const copies = new Map<string, string>();
  slice.content.forEach((node) => {
    if (node.type !== table || !node.attrs.grid) return;
    const id = shortId();
    tables.push({ holder: shortId(), node });
    made.push(id);
    const from: string | undefined = node.attrs.grid.from;
    if (from) copies.set(from, id);
  });
  if (!tables.length) return false;
  const { write } = spec;
  if (!write || !view.editable) return true;
  const nodes: Node[] = [];
  let index = 0;
  slice.content.forEach((node) => {
    if (node.type === table && node.attrs.grid) {
      nodes.push(paragraph.create({ id: tables[index++].holder }));
      return;
    }
    const { range } = node.type === chart ? chartOf(node.attrs) : { range: null };
    const copy = range && copies.get(range.table);
    nodes.push(copy ? chart.create({ ...node.attrs, range: { ...range, table: copy } }) : node);
  });
  const content = new Slice(Fragment.fromArray(nodes), slice.openStart, slice.openEnd);
  const paste = () => {
    view.dispatch(view.state.tr.replaceSelection(content).scrollIntoView());
    const given = new Set<string>();
    write(
      tables.map(({ holder, node }, index) =>
        tableOperation(spec.grids, given, node, { before: holder }, made[index]),
      ),
    );
  };
  const change = spec.history ? spec.history.together(paste) : (paste(), null);
  tables.forEach(({ holder }, index) => {
    awaited.set(made[index], {
      holder: { id: holder, change },
      ...(enter && index === 0 && { then: 'first' as const }),
    });
  });
  return true;
}

/** The selection with whole tables in it as the clipboard carries them: each with its cells and
 * what they compute, where their rows are held. */
function copiedSlice(slice: Slice, view: EditorView): Slice {
  let missing = false;
  const nodes: Node[] = [];
  slice.content.forEach((node) => {
    if (node.type !== table || node.attrs.grid) {
      nodes.push(node);
      return;
    }
    const pos = positionOf(view.state.doc, node.attrs.id);
    const found = pos === null ? null : tableViewAt(view, pos);
    const copy = found?.copiedWhole();
    if (copy) nodes.push(copy);
    else missing = true;
  });
  if (missing) throw new LoadingRows();
  return new Slice(Fragment.fromArray(nodes), slice.openStart, slice.openEnd);
}

class LoadingRows extends Error {}

/** A copy or a cut of cells whose rows are not yet held waits for them: it is refused, told, and
 * the rows asked for. */
function copying(view: EditorView, event: Event): boolean {
  const { selection } = view.state;
  const spec = specOf(view.state);
  let ready = true;
  if (selection instanceof CellRange) {
    ready = tableViewAt(view, selection.$table.pos)?.readable(selection) ?? false;
  } else {
    selection.content().content.forEach((node) => {
      if (node.type !== table) return;
      const pos = positionOf(view.state.doc, node.attrs.id);
      const found = pos === null ? null : tableViewAt(view, pos);
      if (found && !found.copiedWhole()) ready = false;
    });
  }
  if (ready) return false;
  event.preventDefault();
  spec.fail(new Error(spec.label()('table.loading')));
  return true;
}

/** Chrome takes a click just past the table for a click on its hidden range of cells, and keeps
 * that range. */
function leftCells(view: EditorView, event: MouseEvent): boolean {
  if (!(view.state.selection instanceof CellRange) || event.shiftKey) return false;
  const at = view.posAtCoords({ left: event.clientX, top: event.clientY });
  if (at) {
    view.dispatch(view.state.tr.setSelection(Selection.near(view.state.doc.resolve(at.pos))));
  }
  return false;
}

/** A range of cells marked on its table, whose view then draws it. */
function highlighted(state: EditorState): DecorationSet | null {
  const { selection } = state;
  if (!(selection instanceof CellRange)) return null;
  const pos = selection.$table.pos;
  return DecorationSet.create(state.doc, [
    Decoration.node(pos, pos + selection.table.nodeSize, {}, { range: selection }),
  ]);
}

/** Cells emptied go to the grid; a range of cells outlasts a change from elsewhere; the
 * document's own selection is never text inside a table, whose cells have theirs. */
function settle(
  transactions: readonly Transaction[],
  before: EditorState,
  state: EditorState,
): Transaction | null {
  const tr = state.tr;
  for (const transaction of transactions) {
    const cleared: { view: TableView | undefined; range: CellRange; content: Slice } | undefined =
      transaction.getMeta(CLEARED);
    cleared?.view?.clear(cleared.range, cleared.content);
  }
  let selection = tr.selection;
  const was = before.selection;
  if (was instanceof CellRange && !(selection instanceof CellRange) && transactions.some(remote)) {
    const pos = positionOf(tr.doc, was.table.attrs.id);
    if (pos !== null) {
      selection = new CellRange(
        tr.doc.resolve(pos),
        was.anchorKey,
        was.headKey,
        was.rows,
        was.cols,
        was.lines,
      );
    }
  }
  const { $from } = selection;
  if (!(selection instanceof CellRange) && $from.depth > 0 && $from.node(1).type === table) {
    selection = NodeSelection.create(tr.doc, $from.before(1));
  }
  if (!selection.eq(tr.selection)) tr.setSelection(selection);
  return tr.docChanged || tr.selectionSet ? tr : null;
}

/** The commands' state of a range of cells is read from its rows, which change outside the text. */
const RANGE_WRITTEN = 'rangeWritten';

function rangeIn(state: EditorState, change: Change): boolean {
  const { selection } = state;
  if (!(selection instanceof CellRange) || selection.table.attrs.id !== change.table) return false;
  const rect = selection.rect();
  if (!change.rows || !rect) return !change.rows;
  return [...change.rows].some((row) => {
    const at = selection.lines.rowIndex(row);
    return at >= rect.top && at <= rect.bottom;
  });
}

export function tablesPlugin(spec: TablesSpec): Plugin {
  return new Plugin({
    key,
    tables: spec,
    props: {
      nodeViews: {
        table: (node, view, getPos, decorations, inside) =>
          new TableView(node, view, getPos, decorations, inside),
      },
      decorations: highlighted,
      handleKeyDown: keyed,
      handleTextInput: (view, _from, _to, text) => typed(view, text),
      handlePaste: (view, _event, slice) => pastedOver(view, slice),
      transformCopied: copiedSlice,
      handleDOMEvents: { mousedown: leftCells, copy: copying, cut: copying },
    },
    appendTransaction: settle,
    view: (view) => {
      let ranged = false;
      const unsubscribe = spec.grids.subscribe(null, (change) => {
        if (change.outline) view.dispatch(view.state.tr.setMeta(OUTLINED, true));
        else if (!ranged && rangeIn(view.state, change)) {
          ranged = true;
          // A cell written as it is left is written while the view takes its new state.
          queueMicrotask(() => {
            ranged = false;
            if (!view.isDestroyed) view.dispatch(view.state.tr.setMeta(RANGE_WRITTEN, true));
          });
        }
      });
      return { destroy: unsubscribe };
    },
  });
}
