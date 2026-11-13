import { EditorState, TextSelection } from 'prosemirror-state';
import { describe, expect, it } from 'vitest';
import { STANDARD } from './pages';
import { indentsOf, movedEdge, movedIndent, setIndent, snapped } from './rulers';
import { schema } from './schema';

describe('rulers', () => {
  it('settle on a quarter centimetre, or anywhere with Alt', () => {
    expect(snapped(2.37, false)).toBe(2.25);
    expect(snapped(2.38, false)).toBe(2.5);
    expect(snapped(2.371, true)).toBe(2.37);
  });

  it('move a margin as far as the text keeps its room, and a header from its edge', () => {
    expect(movedEdge(STANDARD, 'left', 3.25)).toEqual({ ...STANDARD, left: 3.25 });
    expect(movedEdge(STANDARD, 'left', 20).left).toBe(21 - 2.5 - 2);
    expect(movedEdge(STANDARD, 'top', -1).top).toBe(0);
    expect(movedEdge(STANDARD, 'header', 40).header).toBe(15);
  });

  it('move the first line, the other lines, both, or the right edge of a paragraph', () => {
    const indents = { left: 1, first: 0.5, right: 0 };
    expect(movedIndent(indents, 'first', 0, 16, false)).toEqual({ left: 1, first: -1, right: 0 });
    expect(movedIndent(indents, 'hanging', 2, 16, false)).toEqual({
      left: 2,
      first: -0.5,
      right: 0,
    });
    expect(movedIndent(indents, 'left', 3, 16, false)).toEqual({ left: 3, first: 0.5, right: 0 });
    expect(movedIndent(indents, 'right', 20, 16, false).right).toBe(16 - 1.5 - 1);
  });

  it('keep a hanging first line on the page and move an item a level at a time', () => {
    const hanging = { left: 1, first: -1, right: 0 };
    expect(movedIndent(hanging, 'left', 0, 16, false)).toEqual(hanging);
    expect(movedIndent({ left: 0, first: 0, right: 0 }, 'left', 3.3, 16, true).left).toBe(3.75);
  });

  it('indent every selected paragraph and clear what comes back to the edge', () => {
    const doc = schema.node('doc', null, [
      schema.node('paragraph', { indent: 1, firstLine: 0.5 }, schema.text('Prvi')),
      schema.node('paragraph', { indent: 2 }, schema.text('Drugi')),
    ]);
    let state = EditorState.create({ doc });
    state = state.apply(state.tr.setSelection(TextSelection.create(doc, 2, doc.content.size - 2)));
    setIndent('first', 0, 16)(state, (tr) => (state = state.apply(tr)));
    expect([0, 1].map((index) => indentsOf(state.doc.child(index).attrs))).toEqual([
      { left: 1, first: -1, right: 0 },
      { left: 2, first: -2, right: 0 },
    ]);
    setIndent('hanging', 0, 16)(state, (tr) => (state = state.apply(tr)));
    expect(state.doc.child(0).attrs).toMatchObject({ indent: null, firstLine: null });
  });
});
