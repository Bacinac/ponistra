import { NodeSelection, Plugin, PluginKey, type EditorState } from 'prosemirror-state';
import { Decoration, DecorationSet, type EditorView } from 'prosemirror-view';
import {
  absolutePositionToRelativePosition,
  relativePositionToAbsolutePosition,
  ySyncPluginKey,
  type ProsemirrorBinding,
} from 'y-prosemirror';
import * as Y from 'yjs';
import type { Anchor, InText } from '../comments';
import { schema } from './schema';

const QUOTE = 500;
const { footnote } = schema.nodes;

export interface Anchored {
  id: string;
  anchor: Anchor;
}

/** What the text shows of the tab's comments. */
export interface Commented {
  threads: readonly Anchored[];
  active: string | null;
  draft: Anchor | null;
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

function shown(commented: Commented, state: EditorState): Shown {
  const binding = bindingOf(state);
  const decorations: Decoration[] = [];
  const mark = (anchor: Anchor, attrs: Record<string, string>, spec: object) => {
    const range = binding && rangeOf(binding, anchor);
    if (range) decorations.push(Decoration.inline(range.from, range.to, attrs, spec));
  };
  for (const { id, anchor } of commented.threads) {
    const active = id === commented.active ? ' ponistra-comment-active' : '';
    mark(anchor, { class: `ponistra-comment${active}`, 'data-thread': id }, { thread: id });
  }
  if (commented.draft) {
    mark(commented.draft, { class: 'ponistra-comment ponistra-comment-active' }, {});
  }
  return { ...commented, decorations: DecorationSet.create(state.doc, decorations) };
}

/** Marks the stretches of the tab's threads. A change from the room rebuilds the whole text, so
 * the marks are found again from their anchors; one of the user's own only shifts them. */
export function commentsPlugin(pick: (thread: string | null) => void): Plugin<Shown> {
  return new Plugin<Shown>({
    key,
    state: {
      init: (_, state) => shown(NONE, state),
      apply: (tr, value, _before, state) => {
        const next: Commented | undefined = tr.getMeta(key);
        if (next || tr.getMeta(ySyncPluginKey)?.isChangeOrigin) return shown(next ?? value, state);
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

/** The threads the text shows, in its order, and those whose text is gone. */
export function placedOf(state: EditorState): InText {
  const shown = key.getState(state);
  const starts = new Map<string, number>();
  for (const decoration of shown?.decorations.find() ?? []) {
    const { thread } = decoration.spec;
    if (thread) starts.set(thread, Math.min(starts.get(thread) ?? Infinity, decoration.from));
  }
  return {
    order: [...starts].sort((a, b) => a[1] - b[1]).map(([thread]) => thread),
    lost: (shown?.threads ?? []).map(({ id }) => id).filter((id) => !starts.has(id)),
  };
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
  const quote = words.join('').replace(/\s+/g, ' ').trim();
  if (!quote) return null;
  return { from, to, quote: quote.length > QUOTE ? `${quote.slice(0, QUOTE - 1)}…` : quote };
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
