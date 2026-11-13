import type { EditorView } from 'prosemirror-view';

/** A view given the focus, as a closed menu or dialog gives it back, puts its own selection
 * there at once: the browser places the caret at the start of the text, or nowhere, and
 * ProseMirror puts its selection back only 20 ms later, after taking the browser's when that
 * comes first; keys typed in between write nothing or land at the start. */
export function selectOnFocus(view: EditorView): void {
  view.focus();
}
