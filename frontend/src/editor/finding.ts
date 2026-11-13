import type { Node } from 'prosemirror-model';
import { Plugin, PluginKey, TextSelection } from 'prosemirror-state';
import { Decoration, DecorationSet, type EditorView } from 'prosemirror-view';
import { showNote } from './notes';
import { revealCell } from './tablesPlugin';

/** Where the server found the text sought: in a block or a note from a character to another,
 * counted in code points over its texts, or in a table's cell, wholly or in a block of it. */
export interface Hit {
  block?: string;
  from?: number;
  to?: number;
  table?: string;
  row?: string;
  col?: string;
  formula?: true;
}

export interface Found {
  hits: Hit[];
  more: boolean;
}

interface Shown {
  hits: readonly Hit[];
  current: number;
  decorations: DecorationSet;
}

const key = new PluginKey<Shown>('finding');
const NONE: Shown = { hits: [], current: -1, decorations: DecorationSet.empty };

function textblocks(doc: Node): Map<string, number> {
  const found = new Map<string, number>();
  doc.descendants((node, pos) => {
    if (node.isTextblock && typeof node.attrs.id === 'string') found.set(node.attrs.id, pos);
    return !node.isTextblock;
  });
  return found;
}

/** The positions the characters from `from` to `to` of the texts of the block at `at` span, as
 * the server counts them: in code points, past what is not text; null where they are not
 * there. */
export function spanOf(doc: Node, at: number, from: number, to: number): [number, number] | null {
  const block = doc.nodeAt(at);
  if (!block?.isTextblock || from >= to) return null;
  const starts: number[] = [];
  const ends: number[] = [];
  block.forEach((child, offset) => {
    if (!child.isText) return;
    let pos = at + 1 + offset;
    for (const char of child.text!) {
      starts.push(pos);
      pos += char.length;
      ends.push(pos);
    }
  });
  return to <= starts.length ? [starts[from], ends[to - 1]] : null;
}

function decorated(doc: Node, hits: readonly Hit[], current: number): DecorationSet {
  const blocks = textblocks(doc);
  const found: Decoration[] = [];
  hits.forEach((hit, index) => {
    const at = hit.table === undefined && hit.block ? blocks.get(hit.block) : undefined;
    const span = at === undefined ? null : spanOf(doc, at, hit.from!, hit.to!);
    if (span) {
      const look = index === current ? 'ponistra-hit ponistra-hit-current' : 'ponistra-hit';
      found.push(Decoration.inline(span[0], span[1], { class: look }));
    }
  });
  return DecorationSet.create(doc, found);
}

export function findingPlugin(): Plugin<Shown> {
  return new Plugin<Shown>({
    key,
    state: {
      init: () => NONE,
      apply: (transaction, shown) => {
        const next: Omit<Shown, 'decorations'> | undefined = transaction.getMeta(key);
        if (next)
          return { ...next, decorations: decorated(transaction.doc, next.hits, next.current) };
        if (!transaction.docChanged) return shown;
        return {
          ...shown,
          decorations: shown.decorations.map(transaction.mapping, transaction.doc),
        };
      },
    },
    props: {
      decorations: (state) => key.getState(state)!.decorations,
    },
  });
}

/** Marks the hits in the editor's text, the current one apart; none once `hits` is empty. */
export function markHits(view: EditorView, hits: readonly Hit[], current: number): void {
  view.dispatch(view.state.tr.setMeta(key, { hits, current }));
}

/** Brings the hit into view: its text chosen, the note it is in shown, or its cell chosen. */
export function goToHit(view: EditorView, hit: Hit): void {
  if (hit.table !== undefined && hit.row !== undefined && hit.col !== undefined) {
    revealCell(view, hit.table, hit.row, hit.col);
    return;
  }
  if (!hit.block) return;
  const at = textblocks(view.state.doc).get(hit.block);
  const span = at === undefined ? null : spanOf(view.state.doc, at, hit.from!, hit.to!);
  if (!span) {
    showNote(view, hit.block);
    return;
  }
  const selection = TextSelection.create(view.state.doc, span[0], span[1]);
  view.dispatch(view.state.tr.setSelection(selection).scrollIntoView());
}

/** The first hit at or after the position, else the first of all. */
export function firstFrom(doc: Node, hits: readonly Hit[], pos: number): number {
  const places = textblocks(doc);
  doc.forEach((node, offset) => {
    if (node.type.name === 'table') places.set(node.attrs.id, offset);
  });
  const found = hits.findIndex((hit) => {
    const at = places.get((hit.table ?? hit.block)!);
    if (at === undefined) return false;
    const span = hit.table === undefined ? spanOf(doc, at, hit.from!, hit.to!) : null;
    return (span ? span[0] : at) >= pos;
  });
  return Math.max(found, 0);
}

/** What the operation `substitute` needs to replace the hit alone. */
export function hitPlace(hit: Hit): object {
  if (hit.table !== undefined && hit.block === undefined) {
    return { table: hit.table, row: hit.row, col: hit.col };
  }
  return { block: hit.block, from: hit.from };
}
