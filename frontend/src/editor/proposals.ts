import type { Node } from 'prosemirror-model';
import { NodeSelection, Plugin, PluginKey, type EditorState } from 'prosemirror-state';
import { Decoration, DecorationSet } from 'prosemirror-view';

/** What a proposal does to its part of the text: inserts it, deletes it or changes its
 * formatting. */
export type Kind = 'insertion' | 'deletion' | 'formatting';

/** The proposals a node or its end carries as attributes, as text carries them as marks. */
export const PROPOSED = ['insertion', 'deletion'] as const;
const KINDS: readonly Kind[] = [...PROPOSED, 'formatting'];

/** A proposed change as the schema keeps it: the proposal it is part of, its author, the
 * author's account where the author is one of ours, and when it was made. */
export interface Change {
  id: string;
  author: string;
  user: number | null;
  date: string | null;
}

/** A proposal in the text: its change and what its parts there do. */
export interface Proposal extends Change {
  kinds: Kind[];
}

function isKind(name: string): name is Kind {
  return (KINDS as readonly string[]).includes(name);
}

/** Whether a mark is formatting, which a paragraph's end keeps and a formatting change puts
 * back: neither a link nor a proposal. */
export function formats(name: string): boolean {
  return name !== 'link' && !isKind(name);
}

/** The change an attribute or a mark holds; attributes come from every editor's Yjs updates. */
export function changeOf(value: unknown): Change | null {
  if (!value || typeof value !== 'object') return null;
  const { id, author, user, date } = value as Record<string, unknown>;
  if (typeof id !== 'string' || typeof author !== 'string') return null;
  return {
    id,
    author,
    user: typeof user === 'number' ? user : null,
    date: typeof date === 'string' ? date : null,
  };
}

class Found {
  private readonly all = new Map<string, Proposal>();

  add(value: unknown, kind: Kind): void {
    const change = changeOf(value);
    if (!change) return;
    const known = this.all.get(change.id);
    if (!known) this.all.set(change.id, { ...change, kinds: [kind] });
    else if (!known.kinds.includes(kind)) known.kinds.push(kind);
  }

  marks(node: Node): void {
    for (const mark of node.marks) if (isKind(mark.type.name)) this.add(mark.attrs, mark.type.name);
  }

  attrs(node: Node, kinds: readonly Kind[]): void {
    for (const kind of kinds) this.add(node.attrs[kind], kind);
  }

  get list(): Proposal[] {
    return [...this.all.values()];
  }
}

/** The proposals at the cursor or in the selection: of the text, the nodes, a paragraph's
 * formatting, and a paragraph's end where the cursor stands at it or the selection crosses it. */
export function proposalsAt(state: EditorState): Proposal[] {
  const found = new Found();
  const { selection } = state;
  if (selection instanceof NodeSelection) {
    found.marks(selection.node);
    found.attrs(selection.node, PROPOSED);
  } else if (selection.empty) {
    const { $from } = selection;
    for (const node of [$from.nodeBefore, $from.nodeAfter]) {
      if (!node) continue;
      found.marks(node);
      if (!node.isText) found.attrs(node, PROPOSED);
    }
    if ($from.parent.isTextblock) {
      found.attrs($from.parent, ['formatting']);
      if ($from.parentOffset === $from.parent.content.size) found.attrs($from.parent, PROPOSED);
    }
  } else {
    const { from, to } = selection;
    state.doc.nodesBetween(from, to, (node, pos) => {
      found.marks(node);
      if (!node.isTextblock) {
        found.attrs(node, PROPOSED);
        return true;
      }
      found.attrs(node, ['formatting']);
      const end = pos + node.nodeSize - 1;
      if (end >= from && end < to) found.attrs(node, PROPOSED);
      return true;
    });
  }
  return found.list;
}

interface Shown {
  decorations: DecorationSet;
  kinds: Map<string, Kind[]>;
}

const key = new PluginKey<Shown>('proposals');

function endMark(proposed: string): HTMLElement {
  const mark = document.createElement('span');
  mark.className = 'ponistra-end';
  mark.dataset.proposed = proposed;
  return mark;
}

function shown(doc: Node): Shown {
  const decorations: Decoration[] = [];
  const found = new Found();
  doc.descendants((node, pos) => {
    found.marks(node);
    found.attrs(node, KINDS);
    for (const row of Object.values((node.attrs.proposedRows ?? {}) as Record<string, object>)) {
      for (const kind of PROPOSED) found.add((row as Record<string, unknown>)[kind], kind);
    }
    const proposed = PROPOSED.filter((kind) => changeOf(node.attrs[kind])).join(' ');
    if (proposed) {
      decorations.push(
        node.isTextblock
          ? Decoration.widget(pos + node.nodeSize - 1, () => endMark(proposed), {
              side: 1,
              key: `end ${proposed}`,
              ignoreSelection: true,
              marks: [],
            })
          : Decoration.node(pos, pos + node.nodeSize, { 'data-proposed': proposed }),
      );
    }
    if (changeOf(node.attrs.formatting)) {
      decorations.push(Decoration.node(pos, pos + node.nodeSize, { 'data-restyled': '' }));
    }
    return true;
  });
  const kinds = new Map(found.list.map(({ id, kinds }) => [id, kinds]));
  return { decorations: DecorationSet.create(doc, decorations), kinds };
}

/** Shows what the text's marks cannot: a paragraph's end and a node proposed, and a
 * paragraph's formatting changed. */
export function proposalsPlugin(): Plugin<Shown> {
  return new Plugin<Shown>({
    key,
    state: {
      init: (_, state) => shown(state.doc),
      apply: (tr, value) => (tr.docChanged ? shown(tr.doc) : value),
    },
    props: { decorations: (state) => key.getState(state)?.decorations },
    // Text written at a proposal is the writer's own, not part of the proposal.
    appendTransaction: (_, __, state) => {
      const marks =
        state.storedMarks ?? (state.selection.empty ? state.selection.$from.marks() : []);
      if (!marks.some((mark) => isKind(mark.type.name))) return null;
      return state.tr.setStoredMarks(marks.filter((mark) => !isKind(mark.type.name)));
    },
  });
}

export function hasProposals(state: EditorState): boolean {
  return (key.getState(state)?.kinds.size ?? 0) > 0;
}

/** What a proposal does in all its parts in the editor's text, where the editor shows them. */
export function kindsOf(state: EditorState, proposal: Proposal): Kind[] {
  return key.getState(state)?.kinds.get(proposal.id) ?? proposal.kinds;
}
