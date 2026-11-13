import type { Node, Slice } from 'prosemirror-model';
import {
  Plugin,
  Selection,
  TextSelection,
  type EditorState,
  type Transaction,
} from 'prosemirror-state';
import { canJoin, ReplaceStep } from 'prosemirror-transform';
import { remote, shortId } from './blocks';
import { changeOf, PROPOSED, type Change } from './proposals';
import { schema } from './schema';
import { allRows, type LinesOf } from './tables';

/** The meta of a transaction that carries a note's or a cell's own editor's steps into the
 * document, which that editor has already proposed. */
export const INNER = 'inner';

/** Who proposes in the Suggesting mode: the name the proposals carry and the account. */
export interface Proposer {
  author: string;
  user: number;
}

type Kind = (typeof PROPOSED)[number];

/** The browser's own ways of taking text out at the cursor, as `beforeinput` names them. */
const DELETING = /^delete(Content|Word|SoftLine|HardLine|EntireSoftLine)/;
type Rows = (table: Node) => readonly string[];

/** What one of the user's steps did, where it stands now: the content it took out, which goes
 * back in where it was as proposed deleted, and the content it brought in, proposed inserted. */
interface Edit {
  at: number;
  removed: Slice;
  from: number;
  to: number;
  /** Taken out from before the cursor, as Backspace takes it: the cursor stays before it. */
  backward: boolean;
}

function held(node: Node, kind: Kind): Change | null {
  if (!node.isText) return changeOf(node.attrs[kind]);
  return changeOf(node.marks.find((mark) => mark.type.name === kind)?.attrs);
}

function mine(change: Change | null, who: Proposer): boolean {
  return change?.user === who.user;
}

/** Word's time of a change, to the second. */
function now(): string {
  return new Date().toISOString().replace(/\.\d+Z$/, 'Z');
}

function editsOf(transactions: readonly Transaction[], before: EditorState): Edit[] {
  const edits: Edit[] = [];
  const cursor = before.selection.empty ? before.selection.head : null;
  for (const transaction of transactions) {
    const typed =
      !transaction.getMeta('appendedTransaction') &&
      !transaction.getMeta(INNER) &&
      !remote(transaction);
    transaction.steps.forEach((step, index) => {
      const map = step.getMap();
      for (const edit of edits) {
        edit.at = map.map(edit.at, -1);
        edit.from = map.map(edit.from, 1);
        edit.to = Math.max(edit.from, map.map(edit.to, -1));
      }
      if (!typed || !(step instanceof ReplaceStep)) return;
      const { from, to, slice } = step;
      if (from === to && !slice.size) return;
      edits.push({
        at: from,
        removed: transaction.docs[index].slice(from, to),
        from,
        to: from + slice.size,
        backward: !slice.size && cursor === to && transaction.docs[index] === before.doc,
      });
    });
  }
  return edits;
}

/** The user's own change next to the range, which what is written there joins, as Word keeps
 * a run of typing one change: one of the same kind first, else the other, so that text taken
 * out and written in its place is one replacement. Next to the range are the text on either
 * side, the end of the block before where the range starts a block, and the range's block's
 * own end where it ends it. */
function adjacent(doc: Node, from: number, to: number, kind: Kind, who: Proposer): Change | null {
  const $from = doc.resolve(from);
  const $to = doc.resolve(to);
  const around = [$from.nodeBefore, $to.nodeAfter];
  if ($from.parent.isTextblock && $from.parentOffset === 0 && $from.depth > 0) {
    const index = $from.index($from.depth - 1);
    if (index > 0) around.push($from.node($from.depth - 1).child(index - 1));
  }
  if ($to.parent.isTextblock && $to.parentOffset === $to.parent.content.size) {
    around.push($to.parent);
  }
  for (const each of kind === 'insertion' ? PROPOSED : [...PROPOSED].reverse()) {
    for (const node of around) {
      const change = node && held(node, each);
      if (change && mine(change, who)) return change;
    }
  }
  return null;
}

/** Whether all of the content taken out is the user's own proposed insertion, which goes as
 * if it was never written. */
function ownOnly(removed: Slice, who: Proposer): boolean {
  let own = true;
  removed.content.forEach((node) => {
    own &&= node.isInline && mine(held(node, 'insertion'), who);
  });
  return own;
}

function rowsProposed(
  node: Node,
  rows: readonly string[],
  kind: Kind,
  change: Change,
): Record<string, object> {
  const proposed = { ...((node.attrs.proposedRows ?? {}) as Record<string, object>) };
  for (const row of rows) proposed[row] = { ...proposed[row], [kind]: change };
  return proposed;
}

/** Proposes as inserted what the range brought in: its text, the ends of its blocks and the
 * blocks within it whole. */
function inserted(tr: Transaction, from: number, to: number, change: Change, rowsOf: Rows): void {
  const mark = schema.marks.insertion.create(change);
  tr.doc.nodesBetween(from, to, (node, pos) => {
    const end = pos + node.nodeSize;
    if (node.isText) {
      tr.addMark(Math.max(pos, from), Math.min(end, to), mark);
    } else if (node.isTextblock) {
      if (end - 1 >= from && end - 1 < to) tr.setNodeAttribute(pos, 'insertion', change);
      return true;
    } else if (pos >= from && end <= to) {
      if (node.type === schema.nodes.table) {
        tr.setNodeAttribute(
          pos,
          'proposedRows',
          rowsProposed(node, rowsOf(node), 'insertion', change),
        );
      } else if ('insertion' in node.attrs) {
        tr.setNodeAttribute(pos, 'insertion', change);
      }
    } else {
      return true;
    }
    return false;
  });
}

/** Proposes as deleted what the range took out and is now back in it, except the user's own
 * proposed insertions, which go: text and blocks out, and an end the user wrote joins its
 * block with the next one, which keeps its own end. */
function deleted(
  tr: Transaction,
  from: number,
  to: number,
  change: Change,
  who: Proposer,
  rowsOf: Rows,
): void {
  const mark = schema.marks.deletion.create(change);
  const gone: { from: number; to: number; join: boolean }[] = [];
  tr.doc.nodesBetween(from, to, (node, pos) => {
    const end = pos + node.nodeSize;
    if (node.isInline) {
      const start = Math.max(pos, from);
      const stop = Math.min(end, to);
      if (mine(held(node, 'insertion'), who)) gone.push({ from: start, to: stop, join: false });
      else if (held(node, 'deletion')) return false;
      else if (node.isText) tr.addMark(start, stop, mark);
      else tr.setNodeAttribute(pos, 'deletion', change);
      return false;
    }
    if (node.isTextblock) {
      if (end - 1 < from || end - 1 >= to || held(node, 'deletion')) return true;
      if (mine(held(node, 'insertion'), who) && canJoin(tr.doc, end)) {
        gone.push({ from: end, to: end, join: true });
      } else {
        tr.setNodeAttribute(pos, 'deletion', change);
      }
      return true;
    }
    if (pos < from || end > to) return true;
    if (mine(held(node, 'insertion'), who)) {
      gone.push({ from: pos, to: end, join: false });
    } else if (node.type === schema.nodes.table) {
      const rows = rowsOf(node).filter((row) => !changeOf(proposedRow(node, row)?.deletion));
      tr.setNodeAttribute(pos, 'proposedRows', rowsProposed(node, rows, 'deletion', change));
    } else if ('deletion' in node.attrs && !held(node, 'deletion')) {
      tr.setNodeAttribute(pos, 'deletion', change);
    }
    return false;
  });
  for (const { from, to, join } of gone.sort((a, b) => b.from - a.from)) {
    if (!join) {
      tr.delete(from, to);
      continue;
    }
    const next = tr.doc.resolve(from).nodeAfter!;
    const first = tr.doc.resolve(from).nodeBefore!;
    tr.join(from);
    for (const kind of PROPOSED) {
      tr.setNodeAttribute(from - first.nodeSize, kind, next.attrs[kind]);
    }
  }
}

function proposedRow(node: Node, row: string): Record<string, unknown> | undefined {
  return (node.attrs.proposedRows as Record<string, Record<string, unknown>> | null)?.[row];
}

/** The Suggesting mode: while the proposer is set, what the user writes is proposed inserted
 * and what the user takes out stays, proposed deleted, as Word tracks changes. The user's own
 * proposed insertions go when taken out, as if never written. Formatting and structure apply
 * at once. Changes from other editors and from the backend come as they are; the document's
 * tables' rows are their lines', where the editor has them, as a note's or a cell's has none. */
export function suggesting(
  proposer: () => Proposer | null,
  lines?: LinesOf,
  unknown?: (table: Node) => void,
): Plugin {
  const rowsOf: Rows = (table) => {
    const found = lines?.(table);
    return found ? allRows(found)! : [];
  };
  return new Plugin({
    // A table taken out is proposed deleted row by row, so the browser must know all its rows.
    filterTransaction(tr, state) {
      if (!lines || !tr.docChanged || remote(tr) || !proposer()) return true;
      const kept = new Set<string>();
      tr.doc.forEach((node) => {
        if (node.type === schema.nodes.table) kept.add(node.attrs.id);
      });
      let missing: Node | null = null;
      state.doc.forEach((node) => {
        if (missing || node.type !== schema.nodes.table || kept.has(node.attrs.id)) return;
        const found = lines(node);
        if (found && !allRows(found)) missing = node;
      });
      if (!missing) return true;
      unknown?.(missing);
      return false;
    },
    props: {
      handleDOMEvents: {
        // The browser takes text out itself before the editor reads it, and the text put back
        // then comes after a next key already pressed; the range the browser would take out
        // (a character, a word, a line) goes through a transaction at once instead. The editor
        // learns where arrow keys moved the cursor only after the event, so the cursor is taken
        // from the range: after it for Backspace, before it for Delete.
        beforeinput: (view, event) => {
          if (!proposer() || !DELETING.test(event.inputType)) return false;
          const [range] = event.getTargetRanges();
          if (!range) return false;
          const from = view.posAtDOM(range.startContainer, range.startOffset);
          const to = view.posAtDOM(range.endContainer, range.endOffset);
          if (from >= to) return false;
          event.preventDefault();
          const cursor = event.inputType.endsWith('Backward') ? to : from;
          const { selection, doc } = view.state;
          if (!selection.empty || selection.head !== cursor) {
            view.dispatch(view.state.tr.setSelection(TextSelection.create(doc, cursor)));
          }
          view.dispatch(view.state.tr.delete(from, to).scrollIntoView());
          return true;
        },
      },
    },
    appendTransaction(transactions, before, state) {
      const who = proposer();
      if (!who) return null;
      const edits = editsOf(transactions, before);
      if (!edits.length) return null;
      const tr = state.tr;
      const fresh = (): Change => ({
        id: shortId(),
        author: who.author,
        user: who.user,
        date: now(),
      });
      let cursor: { at: number; steps: number } | null = null;
      for (const edit of edits) {
        const from = tr.mapping.map(edit.from, 1);
        const to = tr.mapping.map(edit.to, -1);
        let change: Change | null = null;
        if (to > from) {
          change = adjacent(tr.doc, from, to, 'insertion', who) ?? fresh();
          inserted(tr, from, to, change, rowsOf);
        }
        if (!edit.removed.size || ownOnly(edit.removed, who)) continue;
        const at = tr.mapping.map(edit.at, -1);
        const steps = tr.steps.length;
        tr.replace(at, at, edit.removed);
        const end = tr.mapping.slice(steps).map(at, 1);
        change ??= adjacent(tr.doc, at, end, 'deletion', who) ?? fresh();
        if (edit.backward) cursor = { at, steps: tr.steps.length };
        deleted(tr, at, end, change, who, rowsOf);
      }
      if (cursor) {
        const at = tr.mapping.slice(cursor.steps).map(cursor.at, -1);
        tr.setSelection(Selection.near(tr.doc.resolve(at), -1));
      }
      return tr.docChanged ? tr : null;
    },
  });
}
