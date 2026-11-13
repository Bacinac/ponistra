// @vitest-environment jsdom
import { splitBlock } from 'prosemirror-commands';
import { DOMParser as Parser, DOMSerializer, type Node } from 'prosemirror-model';
import { EditorState, NodeSelection, TextSelection } from 'prosemirror-state';
import type { DecorationSet } from 'prosemirror-view';
import { describe, expect, it } from 'vitest';
import { blockIds } from './blocks';
import { hasProposals, kindsOf, proposalsAt, proposalsPlugin } from './proposals';
import { schema } from './schema';

const { doc, paragraph, pageBreak } = schema.nodes;
const { insertion, deletion, formatting, strong } = schema.marks;

const change = (id: string, author = 'Ana Horvat') => ({
  id,
  author,
  user: null,
  date: '2026-10-19T10:00:00Z',
});

function state(content: Node, at?: number): EditorState {
  const made = EditorState.create({ doc: content, plugins: [proposalsPlugin(), blockIds()] });
  return at === undefined
    ? made
    : made.apply(made.tr.setSelection(TextSelection.create(made.doc, at)));
}

const replaced = doc.create(null, [
  paragraph.create({ id: 'a' }, [
    schema.text('Najam '),
    schema.text('stana', [insertion.create(change('p'))]),
    schema.text('kuće', [deletion.create(change('p'))]),
  ]),
  paragraph.create({ id: 'b', insertion: change('q', 'Ivo') }, schema.text('Kraj')),
]);

describe('proposals', () => {
  it('keep their kind, author and date through the clipboard', () => {
    const marks = [
      insertion.create(change('p')),
      deletion.create(change('p')),
      formatting.create({ ...change('f'), before: { em: {} } }),
    ];
    const content = doc.create(
      null,
      paragraph.create(null, schema.text('Tekst', [strong.create(), ...marks])),
    );
    const dom = DOMSerializer.fromSchema(schema).serializeFragment(content.content);
    const element = document.createElement('div');
    element.append(dom);
    const parsed = Parser.fromSchema(schema).parse(element).firstChild!.firstChild!;
    expect(parsed.marks.map((mark) => [mark.type.name, mark.attrs])).toEqual(
      [strong.create(), ...marks].map((mark) => [mark.type.name, mark.attrs]),
    );
  });

  it('are found at the cursor with all the kinds of their parts there', () => {
    expect(proposalsAt(state(replaced, 3))).toEqual([]);
    const inserted = state(replaced, 9);
    expect(proposalsAt(inserted)).toEqual([{ ...change('p'), kinds: ['insertion'] }]);
    expect(kindsOf(inserted, proposalsAt(inserted)[0])).toEqual(['insertion', 'deletion']);
    expect(proposalsAt(state(replaced, 12))).toEqual([
      { ...change('p'), kinds: ['insertion', 'deletion'] },
    ]);
  });

  it('of a paragraph’s end are found at the end and in a selection that crosses it', () => {
    const end = replaced.child(0).nodeSize + replaced.child(1).nodeSize - 1;
    expect(proposalsAt(state(replaced, end))).toEqual([
      { ...change('q', 'Ivo'), kinds: ['insertion'] },
    ]);
    expect(proposalsAt(state(replaced, end - 1))).toEqual([]);
    const crossing = state(replaced);
    const selected = crossing.apply(
      crossing.tr.setSelection(TextSelection.create(crossing.doc, 2, end)),
    );
    expect(proposalsAt(selected).map((proposal) => proposal.id)).toEqual(['p']);
    const both = doc.create(null, [
      replaced.child(1),
      paragraph.create({
        id: 'c',
        formatting: { ...change('f'), before: { type: 'heading', attrs: {} } },
      }),
    ]);
    const whole = state(both);
    const all = whole.apply(
      whole.tr.setSelection(TextSelection.create(whole.doc, 1, both.content.size - 1)),
    );
    expect(proposalsAt(all).map(({ id, kinds }) => [id, kinds])).toEqual([
      ['q', ['insertion']],
      ['f', ['formatting']],
    ]);
  });

  it('of a block are found where it is selected', () => {
    const content = doc.create(null, [
      pageBreak.create({ id: 'k', deletion: change('d') }),
      paragraph.create({ id: 'a' }),
    ]);
    const made = state(content);
    const selected = made.apply(made.tr.setSelection(NodeSelection.create(made.doc, 0)));
    expect(proposalsAt(selected)).toEqual([{ ...change('d'), kinds: ['deletion'] }]);
  });

  it('show a paragraph’s end and are known to be in the document', () => {
    const shown = state(replaced);
    expect(hasProposals(shown)).toBe(true);
    expect(
      hasProposals(state(doc.create(null, paragraph.create({ id: 'a' }, schema.text('Tekst'))))),
    ).toBe(false);
    const [plugin] = shown.plugins;
    const decorations = plugin.props.decorations!.call(plugin, shown) as DecorationSet;
    const ends = decorations.find().map((decoration) => decoration.from);
    expect(ends).toEqual([replaced.content.size - 1]);
  });

  it('do not take in what is written at them', () => {
    let current = state(replaced, 9);
    current = current.apply(current.tr.insertText('x'));
    expect(current.doc.child(0).child(1).text).toBe('st');
    expect(current.doc.child(0).child(2).marks).toEqual([]);
  });

  it('of a paragraph’s end stay with the second half where it is split', () => {
    let current = state(replaced, replaced.child(0).nodeSize + 3);
    splitBlock(current, (tr) => (current = current.applyTransaction(tr).state));
    const [, first, second] = current.doc.children;
    expect(first.attrs).toMatchObject({ id: 'b', insertion: null });
    expect(second.attrs.insertion).toEqual(change('q', 'Ivo'));
    expect(second.attrs.id).not.toBe('b');
  });
});
