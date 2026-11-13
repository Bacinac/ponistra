// @vitest-environment jsdom
import { joinBackward, splitBlock } from 'prosemirror-commands';
import type { Node } from 'prosemirror-model';
import { EditorState, TextSelection, type Command, type Transaction } from 'prosemirror-state';
import { describe, expect, it } from 'vitest';
import { ySyncPluginKey } from 'y-prosemirror';
import { blockIds } from './blocks';
import { changeOf, proposalsPlugin } from './proposals';
import { schema } from './schema';
import { INNER, suggesting, type Proposer } from './suggesting';

const { doc, paragraph, pageBreak } = schema.nodes;
const { insertion, deletion } = schema.marks;

const ANA: Proposer = { author: 'Ana Horvat', user: 7 };
const IVO = { id: 'i', author: 'Ivo', user: 3, date: '2026-10-19T10:00:00Z' };

function editor(content: Node, at: number, who: Proposer | null = ANA) {
  let state = EditorState.create({
    doc: content,
    plugins: [blockIds(), proposalsPlugin(), suggesting(() => who)],
  });
  state = state.apply(state.tr.setSelection(TextSelection.create(state.doc, at)));
  return {
    get state() {
      return state;
    },
    apply(make: (state: EditorState) => Transaction) {
      state = state.apply(make(state));
    },
    run(command: Command) {
      command(state, (tr) => (state = state.apply(tr)));
    },
    select(from: number, to = from) {
      state = state.apply(state.tr.setSelection(TextSelection.create(state.doc, from, to)));
    },
  };
}

/** The text of a block as runs: their text and the proposals on them, by kind and account. */
function runs(block: Node): [string, string[]][] {
  const found: [string, string[]][] = [];
  block.forEach((child) => {
    const proposed = child.marks
      .filter((mark) => mark.type === insertion || mark.type === deletion)
      .map((mark) => `${mark.type.name}:${mark.attrs.user}`);
    const last = found.at(-1);
    if (last && last[1].join() === proposed.join()) last[0] += child.text;
    else found.push([child.text!, proposed]);
  });
  return found;
}

function ids(block: Node): Set<string> {
  const found = new Set<string>();
  block.forEach((child) => {
    for (const mark of child.marks) if (changeOf(mark.attrs)) found.add(mark.attrs.id);
  });
  return found;
}

const plain = () => doc.create(null, paragraph.create({ id: 'a' }, schema.text('Najam stana')));

describe('the Suggesting mode', () => {
  it('proposes what is typed inserted, a run of typing as one proposal', () => {
    const at = editor(plain(), 12);
    at.apply((state) => state.tr.insertText('x'));
    at.apply((state) => state.tr.insertText('y'));
    const block = at.state.doc.child(0);
    expect(runs(block)).toEqual([
      ['Najam stana', []],
      ['xy', ['insertion:7']],
    ]);
    const [mark] = block.child(1).marks;
    expect(mark.attrs).toMatchObject({ author: 'Ana Horvat', user: 7 });
    expect(Date.parse(mark.attrs.date)).not.toBeNaN();
    expect(ids(block).size).toBe(1);
  });

  it('keeps what is taken out, proposed deleted, the cursor before it as Backspace leaves it', () => {
    const at = editor(plain(), 12);
    at.apply((state) => state.tr.delete(11, 12));
    at.apply((state) => state.tr.delete(10, 11));
    expect(at.state.doc.child(0).textContent).toBe('Najam stana');
    expect(runs(at.state.doc.child(0))).toEqual([
      ['Najam sta', []],
      ['na', ['deletion:7']],
    ]);
    expect(ids(at.state.doc.child(0)).size).toBe(1);
    expect(at.state.selection.head).toBe(10);
    at.select(1);
    at.apply((state) => state.tr.delete(1, 2));
    expect(runs(at.state.doc.child(0))[0]).toEqual(['N', ['deletion:7']]);
    expect(at.state.selection.head).toBe(2);
  });

  it('replaces a selection as one proposal, and text written where text was taken out', () => {
    const at = editor(plain(), 7);
    at.select(7, 12);
    at.apply((state) => state.tr.insertText('kuće'));
    const block = at.state.doc.child(0);
    expect(runs(block)).toEqual([
      ['Najam ', []],
      ['stana', ['deletion:7']],
      ['kuće', ['insertion:7']],
    ]);
    expect(ids(block).size).toBe(1);
    expect(at.state.selection.head).toBe(at.state.doc.child(0).nodeSize - 1);

    const typed = editor(plain(), 12);
    typed.apply((state) => state.tr.delete(11, 12));
    typed.apply((state) => state.tr.insertText('e'));
    expect(runs(typed.state.doc.child(0))).toEqual([
      ['Najam stan', []],
      ['e', ['insertion:7']],
      ['a', ['deletion:7']],
    ]);
    expect(ids(typed.state.doc.child(0)).size).toBe(1);
  });

  it('takes out the user’s own insertion as if never written, another’s stays proposed deleted', () => {
    const content = doc.create(
      null,
      paragraph.create({ id: 'a' }, [
        schema.text('Rok '),
        schema.text('30', [insertion.create(IVO)]),
      ]),
    );
    const at = editor(content, 7);
    at.apply((state) => state.tr.insertText('x'));
    at.apply((state) => state.tr.delete(7, 8));
    expect(runs(at.state.doc.child(0))).toEqual([
      ['Rok ', []],
      ['30', ['insertion:3']],
    ]);
    at.apply((state) => state.tr.delete(6, 7));
    expect(runs(at.state.doc.child(0))).toEqual([
      ['Rok ', []],
      ['3', ['insertion:3']],
      ['0', ['insertion:3', 'deletion:7']],
    ]);
  });

  it('proposes a paragraph’s end where the user splits a paragraph or joins two', () => {
    const at = editor(plain(), 7);
    at.run(splitBlock);
    const [first, second] = at.state.doc.children;
    expect(changeOf(first.attrs.insertion)?.user).toBe(7);
    expect(second.attrs.insertion).toBeNull();
    at.run(joinBackward);
    expect(at.state.doc.childCount).toBe(1);
    expect(at.state.doc.child(0).attrs).toMatchObject({ id: 'a', insertion: null });
    expect(runs(at.state.doc.child(0))).toEqual([['Najam stana', []]]);

    const two = doc.create(null, [
      paragraph.create({ id: 'a' }, schema.text('Prvi')),
      paragraph.create({ id: 'b' }, schema.text('Drugi')),
    ]);
    const joined = editor(two, 7);
    joined.run(joinBackward);
    expect(joined.state.doc.children.map((block) => block.textContent)).toEqual(['Prvi', 'Drugi']);
    expect(changeOf(joined.state.doc.child(0).attrs.deletion)?.user).toBe(7);
    expect(joined.state.doc.child(1).attrs.id).toBe('b');
    expect(joined.state.selection.head).toBe(5);
  });

  it('proposes a block taken out deleted', () => {
    const content = doc.create(null, [
      paragraph.create({ id: 'a' }, schema.text('Prije')),
      pageBreak.create({ id: 'k' }),
      paragraph.create({ id: 'b' }, schema.text('Poslije')),
    ]);
    const at = editor(content, 1);
    at.apply((state) => state.tr.delete(7, 8));
    expect(at.state.doc.child(1).type).toBe(pageBreak);
    expect(changeOf(at.state.doc.child(1).attrs.deletion)?.user).toBe(7);
  });

  it('leaves the text as it is outside the mode, from other editors and from a note’s own', () => {
    const outside = editor(plain(), 12, null);
    outside.apply((state) => state.tr.delete(11, 12));
    expect(outside.state.doc.child(0).textContent).toBe('Najam stan');
    const remote = editor(plain(), 12);
    remote.apply((state) =>
      state.tr.delete(11, 12).setMeta(ySyncPluginKey, { isChangeOrigin: true }),
    );
    expect(remote.state.doc.child(0).textContent).toBe('Najam stan');
    const inner = editor(plain(), 12);
    inner.apply((state) => state.tr.insertText('x').setMeta(INNER, true));
    expect(runs(inner.state.doc.child(0))).toEqual([['Najam stanax', []]]);
  });
});
