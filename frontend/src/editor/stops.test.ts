import { EditorState, TextSelection } from 'prosemirror-state';
import { describe, expect, it } from 'vitest';
import { schema, stopsOf } from './schema';
import { addStop, decimalOf, moveStop, removeStop, restyleStop, retab } from './stops';

describe('tab stops', () => {
  it('keep only sound stops, in order, one to a place', () => {
    expect(
      stopsOf([
        { at: 10.004, kind: 'right', leader: 'dot' },
        { at: 2, kind: 'left', leader: 'wavy' },
        { at: 2.02, kind: 'center' },
        { at: -1, kind: 'left' },
        { at: 4, kind: 'bar' },
        'tab',
      ]),
    ).toEqual([
      { at: 2, kind: 'left' },
      { at: 10, kind: 'right', leader: 'dot' },
    ]);
    expect(stopsOf(null)).toEqual([]);
  });

  it('are added, moved, restyled and removed on every selected paragraph', () => {
    const doc = schema.node('doc', null, [
      schema.node('paragraph', { tabs: [{ at: 4, kind: 'left' }] }, schema.text('Prvi')),
      schema.node('paragraph', null, schema.text('Drugi')),
    ]);
    let state = EditorState.create({ doc });
    state = state.apply(state.tr.setSelection(TextSelection.create(doc, 2, doc.content.size - 2)));
    const run = (command: ReturnType<typeof addStop>) =>
      command(state, (tr) => (state = state.apply(tr)));
    const tabs = () => [0, 1].map((index) => state.doc.child(index).attrs.tabs);

    expect(run(addStop({ at: 8, kind: 'right' }))).toBe(true);
    expect(tabs()).toEqual([
      [
        { at: 4, kind: 'left' },
        { at: 8, kind: 'right' },
      ],
      [{ at: 8, kind: 'right' }],
    ]);
    run(moveStop(8, 3));
    run(restyleStop(3, { leader: 'dot' }));
    expect(tabs()[1]).toEqual([{ at: 3, kind: 'right', leader: 'dot' }]);
    run(restyleStop(3, { leader: undefined }));
    expect(tabs()[1]).toEqual([{ at: 3, kind: 'right' }]);
    run(removeStop(3));
    expect(tabs()).toEqual([[{ at: 4, kind: 'left' }], null]);
    expect(removeStop(3)(state)).toBe(false);
  });

  it('change on every selected paragraph as the first one was changed, keeping their others', () => {
    const doc = schema.node('doc', null, [
      schema.node(
        'paragraph',
        {
          tabs: [
            { at: 2, kind: 'left' },
            { at: 6, kind: 'center' },
          ],
        },
        schema.text('Prvi'),
      ),
      schema.node(
        'paragraph',
        {
          tabs: [
            { at: 2, kind: 'left' },
            { at: 4, kind: 'decimal' },
            { at: 6.02, kind: 'left' },
          ],
        },
        schema.text('Drugi'),
      ),
    ]);
    let state = EditorState.create({ doc });
    state = state.apply(state.tr.setSelection(TextSelection.create(doc, 2, doc.content.size - 2)));
    const before = stopsOf(doc.child(0).attrs.tabs);
    const after = [
      { at: 6, kind: 'right', leader: 'dot' },
      { at: 9.5, kind: 'left' },
    ] as const;
    expect(retab(before, after)(state, (tr) => (state = state.apply(tr)))).toBe(true);
    expect([0, 1].map((index) => state.doc.child(index).attrs.tabs)).toEqual([
      [...after],
      [{ at: 4, kind: 'decimal' }, ...after],
    ]);
    expect(retab(after, after)(state)).toBe(false);
  });

  it('line numbers up on the separator of the document language', () => {
    expect(decimalOf('hr')).toBe(',');
    expect(decimalOf('en')).toBe('.');
  });
});
