import { NodeSelection, Plugin, PluginKey, type EditorState } from 'prosemirror-state';
import { Decoration, DecorationSet, type EditorView } from 'prosemirror-view';
import {
  absolutePositionToRelativePosition,
  relativePositionToAbsolutePosition,
  ySyncPluginKey,
  type ProsemirrorBinding,
} from 'y-prosemirror';
import * as Y from 'yjs';
import { inCell, type Anchor, type CellAnchor, type InText } from '../anchors';
import { schema } from './schema';
import { CellRange, cellOf, specOf, table as tableType, tableViewAt } from './tableBase';

const QUOTE = 500;
/** Where a row the browser does not know stands, after those it knows. */
const UNKNOWN = Number.MAX_SAFE_INTEGER;
const { footnote } = schema.nodes;

export interface Anchored {
  id: string;
  anchor: Anchor | CellAnchor;
}

/** What the text shows of the tab's comments. */
export interface Commented {
  threads: readonly Anchored[];
  active: string | null;
  draft: Anchor | CellAnchor | null;
}

/** A cell a comment is on, as its table's decoration tells the table: none for the thread of a
 * draft. */
export interface CellComment {
  thread: string | null;
  row: string;
  col: string;
  active: boolean;
}

/** What a table's decoration carries of the comments on its cells, and what picks one. */
export interface CellsCommented {
  comments: readonly CellComment[];
  pick: (thread: string | null) => void;
}

interface Shown extends Commented {
  decorations: DecorationSet;
}

const key = new PluginKey<Shown>('comments');
const NONE: Commented = { threads: [], active: null, draft: null };

function bindingOf(state: EditorState): ProsemirrorBinding | null {
  return ySyncPluginKey.getState(state)?.binding ?? null;
}

/** The end follows its last character, so text typed after the stretch stays out of it and the
 * end stays put when that character is deleted. */
function anchorOf(binding: ProsemirrorBinding, from: number, to: number): Anchor {
  const { type, mapping } = binding;
  const last = absolutePositionToRelativePosition(to - 1, type, mapping);
  return {
    from: Y.relativePositionToJSON(absolutePositionToRelativePosition(from, type, mapping)),
    to: Y.relativePositionToJSON(new Y.RelativePosition(last.type, last.tname, last.item, -1)),
  };
}

/** Where an anchor's stretch is in the text, or null once its text is gone. */
function rangeOf(binding: ProsemirrorBinding, anchor: Anchor): { from: number; to: number } | null {
  const at = (end: object) =>
    relativePositionToAbsolutePosition(
      binding.doc,
      binding.type,
      Y.createRelativePositionFromJSON(end),
      binding.mapping,
    );
  const from = at(anchor.from);
  const to = at(anchor.to);
  return from !== null && to !== null && from < to ? { from, to } : null;
}

function shown(
  commented: Commented,
  state: EditorState,
  pick: (thread: string | null) => void,
): Shown {
  const binding = bindingOf(state);
  const decorations: Decoration[] = [];
  const cells = new Map<string, CellComment[]>();
  const mark = (thread: string | null, anchor: Anchor | CellAnchor, active: boolean) => {
    if (inCell(anchor)) {
      const { table, row, col } = anchor;
      cells.set(table, [...(cells.get(table) ?? []), { thread, row, col, active }]);
      return;
    }
    const range = binding && rangeOf(binding, anchor);
    if (!range) return;
    const attrs: Record<string, string> = {
      class: `ponistra-comment${active ? ' ponistra-comment-active' : ''}`,
    };
    if (thread) attrs['data-thread'] = thread;
    decorations.push(Decoration.inline(range.from, range.to, attrs, thread ? { thread } : {}));
  };
  for (const { id, anchor } of commented.threads) mark(id, anchor, id === commented.active);
  if (commented.draft) mark(null, commented.draft, true);
  if (cells.size) {
    state.doc.forEach((node, at) => {
      const comments = node.type === tableType ? cells.get(node.attrs.id) : undefined;
      if (!comments) return;
      // A node decoration is told apart by its attributes alone, so they name what it carries.
      const attrs = { 'data-comments': JSON.stringify(comments) };
      const spec: CellsCommented = { comments, pick };
      decorations.push(Decoration.node(at, at + node.nodeSize, attrs, spec));
    });
  }
  return { ...commented, decorations: DecorationSet.create(state.doc, decorations) };
}

/** The comments on a table's cells its decorations carry, and what picks one. */
export function cellComments(decorations: readonly Decoration[]): CellsCommented | null {
  for (const decoration of decorations) {
    const spec = decoration.spec as Partial<CellsCommented>;
    if (spec.comments) return spec as CellsCommented;
  }
  return null;
}

/** Marks the stretches of the tab's threads. A change from the room rebuilds the whole text, so
 * the marks are found again from their anchors; one of the user's own only shifts them. */
export function commentsPlugin(pick: (thread: string | null) => void): Plugin<Shown> {
  return new Plugin<Shown>({
    key,
    state: {
      init: (_, state) => shown(NONE, state, pick),
      apply: (tr, value, _before, state) => {
        const next: Commented | undefined = tr.getMeta(key);
        if (next || tr.getMeta(ySyncPluginKey)?.isChangeOrigin)
          return shown(next ?? value, state, pick);
        if (!tr.docChanged) return value;
        return { ...value, decorations: value.decorations.map(tr.mapping, tr.doc) };
      },
    },
    props: {
      decorations: (state) => key.getState(state)!.decorations,
      handleClick(view, pos) {
        const { decorations, active } = key.getState(view.state)!;
        const here = decorations.find(pos, pos, (spec) => Boolean(spec.thread));
        const innermost = here.reduce<Decoration | null>(
          (best, decoration) =>
            best && best.to - best.from <= decoration.to - decoration.from ? best : decoration,
          null,
        );
        if (innermost) pick(innermost.spec.thread);
        else if (active) pick(null);
        return false;
      },
    },
  });
}

/** Shows what has changed only: a transaction writes its selection over the page's, and the page
 * may have a newer one that the editor has not read yet. */
export function showComments(view: EditorView, commented: Commented): void {
  const now = key.getState(view.state);
  if (!now || summaryOf(now) !== summaryOf(commented))
    view.dispatch(view.state.tr.setMeta(key, commented));
}

function summaryOf({ threads, active, draft }: Commented): string {
  return JSON.stringify([threads.map(({ id, anchor }) => [id, anchor]), active, draft]);
}

/** The threads the text shows, in its order, a table's by where their cells stand in it, and
 * those whose text or cell is gone. */
export function placedOf(state: EditorState): InText {
  const shown = key.getState(state);
  const starts = new Map<string, [number, number, number]>();
  for (const decoration of shown?.decorations.find() ?? []) {
    const { thread, comments } = decoration.spec as { thread?: string } & Partial<CellsCommented>;
    if (thread) {
      const was = starts.get(thread)?.[0] ?? Infinity;
      starts.set(thread, [Math.min(was, decoration.from), 0, 0]);
    }
    if (!comments) continue;
    const grid = specOf(state).grids.grid(state.doc.nodeAt(decoration.from)!.attrs.id);
    for (const { thread, row, col } of comments) {
      if (!thread || (grid && (grid.colIndex(col) < 0 || grid.lacks(row)))) continue;
      const y = grid?.rowIndex(row) ?? -1;
      starts.set(thread, [decoration.from, y < 0 ? UNKNOWN : y, grid?.colIndex(col) ?? 0]);
    }
  }
  const order = [...starts].sort(([, a], [, b]) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  return {
    order: order.map(([thread]) => thread),
    lost: (shown?.threads ?? []).map(({ id }) => id).filter((id) => !starts.has(id)),
  };
}

export function quoted(text: string): string {
  const quote = text.replace(/\s+/g, ' ').trim();
  return quote.length > QUOTE ? `${quote.slice(0, QUOTE - 1)}…` : quote;
}

/** The selected text as a comment takes it: its stretch and its words, without its notes. */
function selectedText(state: EditorState): { from: number; to: number; quote: string } | null {
  const { selection } = state;
  if (selection.empty || selection instanceof NodeSelection) return null;
  let from = -1;
  let to = -1;
  const words: string[] = [];
  state.doc.nodesBetween(selection.from, selection.to, (node, pos) => {
    if (node.type === footnote) return false;
    if (node.isTextblock && words.length) words.push(' ');
    if (!node.isText) return true;
    const start = Math.max(pos, selection.from);
    const end = Math.min(pos + node.nodeSize, selection.to);
    if (start < end) {
      if (from < 0) from = start;
      to = end;
      words.push(node.text!.slice(start - pos, end - pos));
    }
    return false;
  });
  const quote = quoted(words.join(''));
  return quote ? { from, to, quote } : null;
}

export function commentable(state: EditorState): boolean {
  return Boolean(bindingOf(state) && selectedText(state));
}

/** A thread on the selected text, as far as the text decides it. */
export function draftOf(state: EditorState): { anchor: Anchor; quote: string } | null {
  const binding = bindingOf(state);
  const text = selectedText(state);
  return binding && text
    ? { anchor: anchorOf(binding, text.from, text.to), quote: text.quote }
    : null;
}

/** A thread on the cell the cursor is in, or the cell the selected cells start from, as far as
 * its table decides it. */
export function cellDraftOf(view: EditorView): { anchor: CellAnchor; quote: string } | null {
  const cell = cellOf(view);
  if (cell) return cell.table.commentOn(cell.key);
  const { selection } = view.state;
  if (!(selection instanceof CellRange)) return null;
  return tableViewAt(view, selection.$table.pos)?.commentOn(selection.anchorKey) ?? null;
}
