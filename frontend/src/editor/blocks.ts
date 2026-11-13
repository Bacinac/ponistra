import type { Attrs, Node, NodeType } from 'prosemirror-model';
import {
  Plugin,
  TextSelection,
  type Command,
  type EditorState,
  type Transaction,
} from 'prosemirror-state';
import { AddMarkStep, RemoveMarkStep, ReplaceStep, type Step } from 'prosemirror-transform';
import { ySyncPluginKey } from 'y-prosemirror';
import { INDENT_MAX, INDENT_STEP, schema } from './schema';
import { PROPOSED } from './proposals';

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';

export function shortId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(12)), (byte) => ALPHABET[byte & 63]).join(
    '',
  );
}

export function remote(transaction: Transaction): boolean {
  return Boolean(transaction.getMeta(ySyncPluginKey)?.isChangeOrigin);
}

/** Whether a step can bring in a block without an id, or with one another block has: text
 * written or removed, and marks, cannot. */
function bringsBlocks(step: Step): boolean {
  if (step instanceof AddMarkStep || step instanceof RemoveMarkStep) return false;
  if (!(step instanceof ReplaceStep)) return true;
  let found = false;
  step.slice.content.descendants((node) => {
    found ||= 'id' in node.attrs;
    return !found;
  });
  return found;
}

export function blockIds(): Plugin {
  return new Plugin({
    appendTransaction(transactions, _, state) {
      if (
        !transactions.some(
          (transaction) => !remote(transaction) && transaction.steps.some(bringsBlocks),
        )
      ) {
        return null;
      }
      const seen = new Map<string, number>();
      const tr = state.tr;
      state.doc.descendants((node, pos) => {
        if (!('id' in node.attrs)) return true;
        const id = node.attrs.id as string | null;
        if (id && !seen.has(id)) {
          seen.set(id, pos + node.nodeSize);
          return true;
        }
        tr.setNodeAttribute(pos, 'id', shortId());
        // The second half of a split block: only the first starts or continues its number.
        if (id && node.attrs.restart === true) tr.setNodeAttribute(pos, 'restart', false);
        if (id && node.attrs.continued === true) tr.setNodeAttribute(pos, 'continued', false);
        // The block's end, and what is proposed for it, is the second half's; the first ends
        // where the block was split.
        if (id && node.isTextblock && seen.get(id) === pos) {
          const first = state.doc.resolve(pos).nodeBefore!;
          for (const kind of PROPOSED) {
            if (first.attrs[kind]) tr.setNodeAttribute(pos - first.nodeSize, kind, null);
          }
        }
        return true;
      });
      return tr.docChanged ? tr : null;
    },
  });
}

function kept(node: Node, type: NodeType): Attrs {
  return Object.fromEntries(
    Object.entries(node.attrs).filter(
      ([name]) => name !== 'style' && name !== 'restart' && name in (type.spec.attrs ?? {}),
    ),
  );
}

/** Makes the selected blocks this type, in the style given or else the type's own. */
export function retype(type: NodeType, attrs: Attrs = {}): Command {
  const wanted = { style: null, ...attrs };
  return (state, dispatch) => {
    const { ranges } = state.selection;
    let applicable = false;
    for (const { $from, $to } of ranges) {
      state.doc.nodesBetween($from.pos, $to.pos, (node, pos) => {
        if (applicable || !node.isTextblock) return !applicable;
        const $pos = state.doc.resolve(pos);
        const index = $pos.index();
        applicable =
          !node.hasMarkup(type, { ...node.attrs, ...wanted }) &&
          $pos.parent.canReplaceWith(index, index + 1, type);
        return false;
      });
    }
    if (!applicable) return false;
    if (dispatch) {
      const tr = state.tr;
      for (const { $from, $to } of ranges) {
        tr.setBlockType(tr.mapping.map($from.pos), tr.mapping.map($to.pos), type, (node) => ({
          ...kept(node, type),
          ...wanted,
        }));
      }
      dispatch(tr.scrollIntoView());
    }
    return true;
  };
}

export function textblocks(state: EditorState): { node: Node; pos: number }[] {
  const found: { node: Node; pos: number }[] = [];
  for (const { $from, $to } of state.selection.ranges) {
    state.doc.nodesBetween($from.pos, $to.pos, (node, pos) => {
      if (node.isTextblock) found.push({ node, pos });
      return !node.isTextblock;
    });
  }
  return found;
}

/** The selection's empty paragraphs, whose formatting is kept at their end. */
export function endsIn(state: EditorState): { node: Node; pos: number }[] {
  return textblocks(state).filter(({ node }) => node.content.size === 0);
}

export function reshape(change: (attrs: Attrs) => Attrs | null): Command {
  return (state, dispatch) => {
    const changes = textblocks(state).flatMap(({ node, pos }) => {
      const attrs = change(node.attrs);
      return attrs ? [{ pos, attrs }] : [];
    });
    if (!changes.length) return false;
    if (dispatch) {
      const tr = state.tr;
      for (const { pos, attrs } of changes) {
        for (const [name, value] of Object.entries(attrs)) tr.setNodeAttribute(pos, name, value);
      }
      dispatch(tr);
    }
    return true;
  };
}

/** One step in or out. Snapping to the step grid lines up an imported 0.63 cm with the
 * paragraphs indented here. */
export function indent(step: 1 | -1): Command {
  return reshape(({ indent }) => {
    const steps = (indent ?? 0) / INDENT_STEP;
    const next =
      (step > 0 ? Math.floor(steps + 1e-9) + 1 : Math.ceil(steps - 1e-9) - 1) * INDENT_STEP;
    const bounded = Math.min(INDENT_MAX, Math.max(0, next));
    return bounded === (indent ?? 0) ? null : { indent: bounded || null };
  });
}

/** A break of `type` where the cursor is, as Word's Ctrl+Enter: the text after it starts what
 * follows the break, which at the end of a block is the next block. */
export function insertBreak(type: NodeType): Command {
  return (state, dispatch) => {
    const { $from } = state.selection;
    if ($from.depth !== 1 || !$from.parent.isTextblock) return false;
    if (dispatch) {
      const tr = state.tr.deleteSelection();
      const $at = tr.selection.$from;
      let at = $at.before();
      if ($at.parentOffset === $at.parent.content.size) {
        at = $at.after();
      } else if ($at.parentOffset > 0) {
        tr.split($at.pos);
        at = $at.pos + 1;
      }
      tr.insert(at, type.create());
      if (!tr.doc.resolve(at + 1).nodeAfter?.isTextblock) {
        tr.insert(at + 1, schema.nodes.paragraph.create());
      }
      dispatch(tr.setSelection(TextSelection.create(tr.doc, at + 2)).scrollIntoView());
    }
    return true;
  };
}
