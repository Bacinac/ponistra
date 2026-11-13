import { InputRule } from 'prosemirror-inputrules';
import { Plugin, TextSelection, type Command, type EditorState } from 'prosemirror-state';
import { safeHref, schema } from './schema';

const { link } = schema.marks;
const TYPED_URL = /(?:^|[\s(])((?:https?:\/\/|www\.)\S+)\s$/;
const TRAILING = /[.,;:!?)\]'"”’]+$/;

export interface Linked {
  from: number;
  to: number;
  href: string;
}

/** The link the selection is in, from its first character to its last. */
export function linkAt(state: EditorState): Linked | null {
  const { $from, $to } = state.selection;
  if (!$from.sameParent($to) || !$from.parent.inlineContent) return null;
  const mark =
    link.isInSet($from.nodeAfter?.marks ?? []) ?? link.isInSet($from.nodeBefore?.marks ?? []);
  if (!mark) return null;
  const start = $from.start();
  let from: number | null = null;
  let found: Linked | null = null;
  $from.parent.forEach((child, offset) => {
    if (!mark.isInSet(child.marks)) {
      from = null;
      return;
    }
    from ??= start + offset;
    const to = start + offset + child.nodeSize;
    if (from <= $from.pos && $to.pos <= to) found = { from, to, href: mark.attrs.href };
  });
  return found;
}

export function canLink(state: EditorState): boolean {
  const { $from, $to } = state.selection;
  return $from.sameParent($to) && $from.parent.inlineContent;
}

/** Makes the link's text, or the selection, this text leading to this address. */
export function setLink(text: string, href: string): Command {
  return (state, dispatch) => {
    const safe = safeHref(href);
    if (!safe || !text || !canLink(state)) return false;
    if (dispatch) {
      const { from, to } = linkAt(state) ?? state.selection;
      const mark = link.create({ href: safe });
      const tr = state.tr;
      if (state.doc.textBetween(from, to) === text) {
        tr.removeMark(from, to, link).addMark(from, to, mark);
      } else {
        const around = link.removeFromSet(state.doc.resolve(from).marks());
        tr.replaceWith(from, to, schema.text(text, mark.addToSet(around)));
      }
      const end = TextSelection.create(tr.doc, from + text.length);
      dispatch(tr.setSelection(end).removeStoredMark(link).scrollIntoView());
    }
    return true;
  };
}

export const removeLink: Command = (state, dispatch) => {
  const found = linkAt(state);
  if (!found) return false;
  dispatch?.(state.tr.removeMark(found.from, found.to, link));
  return true;
};

/** An address typed into the text becomes a link once a space follows it. */
export const autolink = new InputRule(TYPED_URL, (state, match, start, end) => {
  const url = match[1].replace(TRAILING, '');
  const href = safeHref(url.startsWith('www.') ? `https://${url}` : url);
  const from = start + match[0].lastIndexOf(match[1]);
  const to = from + url.length;
  if (!href || state.doc.rangeHasMark(from, to, link)) return null;
  return state.tr.addMark(from, to, link.create({ href })).insertText(match[0].slice(-1), end);
});

/** A link leads on with a click where the text cannot be edited, and with Ctrl or ⌘ held where
 * it can. */
export function followLinks(follow: (href: string) => void): Plugin {
  return new Plugin({
    props: {
      handleDOMEvents: {
        click(view, event) {
          const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null;
          if (!anchor || !view.dom.contains(anchor)) return false;
          event.preventDefault();
          if (view.editable && !event.ctrlKey && !event.metaKey) return false;
          follow(anchor.getAttribute('href')!);
          return true;
        },
      },
    },
  });
}
