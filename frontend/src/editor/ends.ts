import { Mark, type Attrs, type Node, type Schema } from 'prosemirror-model';
import { Plugin, TextSelection, type EditorState, type Transaction } from 'prosemirror-state';
import { formats } from './proposals';

/** The marks a paragraph's `endMarks` names, each one known and as its type takes it. */
export function marksFrom(schema: Schema, value: unknown): readonly Mark[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return Mark.none;
  return Mark.setFrom(
    Object.entries(value).flatMap(([name, attrs]) => {
      if (!formats(name) || !Object.hasOwn(schema.marks, name)) return [];
      try {
        return [schema.marks[name].create(attrs && typeof attrs === 'object' ? attrs : null)];
      } catch {
        return [];
      }
    }),
  );
}

/** The formatting kept at a paragraph's end, as Word keeps its paragraph mark's: what is written
 * into it while empty takes it, and a value computed for its cell shows in it. */
export function endMarksOf(node: Node): readonly Mark[] {
  return marksFrom(node.type.schema, node.attrs.endMarks);
}

export function endMarksAttr(marks: readonly Mark[]): Record<string, Attrs> | null {
  const kept = marks.filter((mark) => formats(mark.type.name));
  return kept.length ? Object.fromEntries(kept.map((mark) => [mark.type.name, mark.attrs])) : null;
}

/** The marks text written at the cursor takes. */
export function marksAt(state: EditorState): readonly Mark[] {
  const { $from } = state.selection;
  if (state.storedMarks) return state.storedMarks;
  return $from.parent.content.size ? $from.marks() : endMarksOf($from.parent);
}

export function restyleEnds(
  tr: Transaction,
  ends: readonly { node: Node; pos: number }[],
  change: (marks: readonly Mark[]) => readonly Mark[],
): void {
  for (const { node, pos } of ends) {
    const before = endMarksOf(node);
    const after = change(before);
    if (!Mark.sameSet(before, after)) tr.setNodeAttribute(pos, 'endMarks', endMarksAttr(after));
  }
}

/** Text written into an empty paragraph takes the formatting kept at its end. */
export function writtenAtEnd(): Plugin {
  return new Plugin({
    appendTransaction(transactions, _old, state) {
      if (state.storedMarks) return null;
      if (!transactions.some((tr) => tr.selectionSet || tr.docChanged)) return null;
      const { selection } = state;
      const $cursor = selection instanceof TextSelection ? selection.$cursor : null;
      if (!$cursor || $cursor.parent.content.size) return null;
      const marks = endMarksOf($cursor.parent);
      return marks.length ? state.tr.setStoredMarks(marks) : null;
    },
  });
}
