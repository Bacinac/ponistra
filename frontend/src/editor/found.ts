import { Plugin, PluginKey, type EditorState } from 'prosemirror-state';
import { Decoration, DecorationSet, type EditorView } from 'prosemirror-view';

const key = new PluginKey<string | null>('found');
const SHOWN_MS = 4000;

export function positionOf(state: EditorState, block: string): number | null {
  let position: number | null = null;
  state.doc.descendants((node, offset) => {
    if (position === null && node.attrs.id === block) position = offset;
    return position === null && !node.isTextblock;
  });
  return position;
}

export function foundPlugin(): Plugin<string | null> {
  return new Plugin<string | null>({
    key,
    state: {
      init: () => null,
      apply: (transaction, block) => {
        const next: string | null | undefined = transaction.getMeta(key);
        return next === undefined ? block : next;
      },
    },
    props: {
      decorations(state) {
        const block = key.getState(state);
        const at = block ? positionOf(state, block) : null;
        if (at === null) return null;
        const end = at + state.doc.nodeAt(at)!.nodeSize;
        return DecorationSet.create(state.doc, [
          Decoration.node(at, end, { class: 'ponistra-found' }),
        ]);
      },
    },
  });
}

/** Scrolls to the block and marks it for a moment; false while the tab has no such block. */
export function showBlock(view: EditorView, block: string): boolean {
  const at = positionOf(view.state, block);
  if (at === null) return false;
  view.dispatch(view.state.tr.setMeta(key, block));
  view.dom.querySelector('.ponistra-found')?.scrollIntoView({ block: 'center' });
  setTimeout(() => {
    if (!view.isDestroyed && key.getState(view.state) === block) {
      view.dispatch(view.state.tr.setMeta(key, null));
    }
  }, SHOWN_MS);
  return true;
}
