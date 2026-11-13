// @vitest-environment jsdom
import { splitBlock } from 'prosemirror-commands';
import type { Node } from 'prosemirror-model';
import { EditorState, TextSelection } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { afterEach, describe, expect, it } from 'vitest';
import { ySyncPlugin, ySyncPluginKey } from 'y-prosemirror';
import { Awareness } from 'y-protocols/awareness';
import * as Y from 'yjs';
import { blockIds, retype, shortId } from './blocks';
import { contentsStore } from './contents';
import { listStore } from './forms';
import { columnName } from './formulas';
import { editingPlugins, liveView, type Actions } from './Editor';
import { GridClient } from './grids';
import { bodyOf } from './tab';
import { endMarksOf, marksFrom, writtenAtEnd } from './ends';
import { schema } from './schema';
import { Layout, linesOf, retyped, type Part } from './tables';

/** Grids no server answers: these tests write no table's cells. */
function closedGrids(): GridClient {
  const grids = new GridClient('00000000-0000-0000-0000-000000000001');
  grids.close();
  return grids;
}

const { doc, paragraph, heading } = schema.nodes;

const ACTIONS: Actions = {
  open: () => {},
  filter: () => {},
  ran: () => {},
  consent: () => {},
  fail: (error) => {
    throw error;
  },
  follow: () => {},
  label: { current: (key) => key },
  place: {
    document: '00000000-0000-0000-0000-000000000001',
    tab: '00000000-0000-0000-0000-000000000002',
    address: '/d/probni-dokument-0000000000000000000001',
  },
  styling: {
    current: { theme: { headings: 'Inter', text: 'Inter' }, styles: {} },
  },
  notes: { current: null },
  numbers: { current: {} },
  locale: { current: 'hr' },
  proposer: { current: null },
  suggest: () => {},
  visitTab: () => false,
  desk: { current: null },
  parts: { current: null },
  slides: { current: null },
  present: { current: null },
  contents: contentsStore(() => {}),
  lists: listStore(new Y.Doc()),
  grids: closedGrids(),
};

function blocks(...ids: (string | null)[]): Node {
  return doc.create(
    null,
    ids.map((id, index) => paragraph.create({ id }, schema.text(`Odlomak ${index + 1}`))),
  );
}

function ids(state: EditorState): (string | null)[] {
  const found: (string | null)[] = [];
  state.doc.forEach((node) => found.push(node.attrs.id));
  return found;
}

function connect(left: Y.Doc, right: Y.Doc): void {
  left.on('update', (update: Uint8Array, origin: unknown) => {
    if (origin !== right) Y.applyUpdate(right, update, left);
  });
  right.on('update', (update: Uint8Array, origin: unknown) => {
    if (origin !== left) Y.applyUpdate(left, update, right);
  });
}

describe('shortId', () => {
  it('is twelve URL-safe characters and does not repeat', () => {
    const made = Array.from({ length: 1000 }, shortId);
    expect(made.every((id) => /^[A-Za-z0-9_-]{12}$/.test(id))).toBe(true);
    expect(new Set(made).size).toBe(1000);
  });
});

describe('block ids', () => {
  const state = (content: Node) => EditorState.create({ doc: content, plugins: [blockIds()] });

  it('gives a missing or repeated id a new one and keeps the first', () => {
    const start = state(blocks('a'));
    const tr = start.tr.insert(start.doc.content.size, blocks('a', null).content);
    const [first, second, third] = ids(start.apply(tr));
    expect(first).toBe('a');
    expect(new Set([first, second, third]).size).toBe(3);
  });

  it('leaves the original id where a paragraph is split', () => {
    let current = state(blocks('a'));
    current = current.apply(current.tr.setSelection(TextSelection.create(current.doc, 4)));
    splitBlock(current, (tr) => (current = current.applyTransaction(tr).state));
    expect(ids(current)[0]).toBe('a');
    expect(ids(current)[1]).toMatch(/^[A-Za-z0-9_-]{12}$/);
  });

  it('keeps the id and the layout, not a restart of its numbers, when a paragraph becomes a heading', () => {
    let current = state(blocks('a'));
    current = current.apply(
      current.tr.setNodeAttribute(0, 'align', 'center').setNodeAttribute(0, 'restart', true),
    );
    retype(heading, { level: 2 })(current, (tr) => (current = current.applyTransaction(tr).state));
    const block = current.doc.firstChild!;
    expect([block.type, block.attrs]).toEqual([
      heading,
      {
        id: 'a',
        align: 'center',
        indent: null,
        firstLine: null,
        right: null,
        tabs: null,
        style: null,
        restart: false,
        endMarks: null,
        formatting: null,
        insertion: null,
        deletion: null,
        layout: null,
        background: null,
        hidden: false,
        level: 2,
      },
    ]);
  });

  it('does not touch what another client sent', () => {
    const start = state(blocks('a'));
    const tr = start.tr
      .insert(start.doc.content.size, blocks('a').content)
      .setMeta(ySyncPluginKey, { isChangeOrigin: true });
    expect(ids(start.applyTransaction(tr).state)).toEqual(['a', 'a']);
  });

  it('does not look through the blocks when only text is written or marked', () => {
    const start = state(blocks('a', 'a'));
    const tr = start.tr.insertText('x', 2).addMark(2, 4, schema.marks.strong.create());
    expect(ids(start.applyTransaction(tr).state)).toEqual(['a', 'a']);
  });
});

describe('paragraph ends', () => {
  const { strong, em } = schema.marks;
  const names = (marks: readonly { type: { name: string } }[]) =>
    marks.map((mark) => mark.type.name);

  it('keep only known marks, a link not among them', () => {
    const found = marksFrom(schema, {
      em: 5,
      strong: {},
      link: { href: 'https://ponistra.example.org' },
      color: {},
      constructor: {},
      blink: {},
    });
    expect(names(found)).toEqual(['strong', 'em']);
    expect(marksFrom(schema, [{ strong: {} }])).toEqual([]);
  });

  it('keep the marks of text a formula replaces, which its value then shows in', () => {
    const bold = schema.nodes.cell.create(
      { row: 'r', col: 'c' },
      paragraph.create({ align: 'right' }, schema.text('x', [strong.create()])),
    );
    const emptied = retyped(bold, '');
    expect(emptied.firstChild!.attrs).toMatchObject({ align: 'right', endMarks: { strong: {} } });
    const shown = retyped(emptied, '6');
    expect(shown.firstChild!.attrs.align).toBe('right');
    expect(names(shown.firstChild!.firstChild!.marks)).toEqual(['strong']);
  });

  it('give what is written into an empty paragraph their marks', () => {
    const start = EditorState.create({
      doc: doc.create(null, [
        paragraph.create(null, schema.text('Uvod')),
        paragraph.create({ endMarks: { strong: {}, em: {} } }),
      ]),
      plugins: [writtenAtEnd()],
    });
    const inside = start.apply(start.tr.setSelection(TextSelection.atEnd(start.doc)));
    expect(names(inside.storedMarks ?? [])).toEqual(['strong', 'em']);
    const written = inside.apply(inside.tr.insertText('Zaključak'));
    expect(names(written.doc.lastChild!.firstChild!.marks)).toEqual(['strong', 'em']);
    expect(endMarksOf(written.doc.firstChild!)).toEqual([]);
    expect(em.isInSet(endMarksOf(written.doc.lastChild!))).toBeTruthy();
  });
});

describe('tables', () => {
  it('names columns as a spreadsheet does', () => {
    expect([0, 25, 26, 51, 701, 702].map(columnName)).toEqual(['A', 'Z', 'AA', 'AZ', 'ZZ', 'AAA']);
  });

  const cell = (row: string, col: string, text: string) =>
    schema.nodes.cell.create({ row, col }, paragraph.create(null, schema.text(text)));
  const laid = (grid: Part, cells: Node[]) => {
    const table = schema.nodes.table.create({ id: 't', grid }, cells);
    return new Layout(linesOf(null)(table)!, table);
  };

  it('lays out cells by row and column id, an empty slot without a node', () => {
    const layout = laid({ rows: ['a', 'b'], cols: ['x', 'y', 'z'], merges: { 'a:x': 'a:y' } }, [
      cell('b', 'z', '42'),
      cell('a', 'x', 'Naslov'),
    ]);
    expect(
      [...layout.cellsIn(layout.whole())].map((placed) => [
        placed.key,
        placed.cols,
        placed.node?.textContent ?? null,
      ]),
    ).toEqual([
      ['a:x', 2, 'Naslov'],
      ['a:z', 1, null],
      ['b:x', 1, null],
      ['b:y', 1, null],
      ['b:z', 1, '42'],
    ]);
    expect(layout.at(0, 1)!.key).toBe('a:x');
    expect([layout.starts(0, 0), layout.starts(0, 1)]).toEqual([true, false]);
  });

  it('leaves out a cell whose row is gone, and a merge over one that came first', () => {
    const merges = { 'a:x': 'b:y', 'b:y': 'b:z', 'gone:x': 'b:x' };
    const layout = laid({ rows: ['a', 'b'], cols: ['x', 'y', 'z'], merges }, [
      cell('a', 'x', 'A'),
      cell('gone', 'x', 'C'),
    ]);
    expect(
      [...layout.cellsIn(layout.whole())].map((placed) => [placed.key, placed.rows, placed.cols]),
    ).toEqual([
      ['a:x', 2, 2],
      ['a:z', 1, 1],
      ['b:z', 1, 1],
    ]);
    expect([...layout.nodeCells()].map((placed) => placed.key)).toEqual(['a:x']);
  });

  it('moves from cell to cell in reading order, over a merged cell once', () => {
    const layout = laid({ rows: ['a', 'b'], cols: ['x', 'y', 'z'], merges: { 'a:y': 'b:y' } }, []);
    const right = (key: string) => layout.neighbour(layout.placed(key)!, 'right')?.key ?? null;
    expect(['a:x', 'a:y', 'a:z', 'b:x', 'b:z'].map(right)).toEqual([
      'a:y',
      'a:z',
      'b:x',
      'b:z',
      null,
    ]);
    expect(layout.neighbour(layout.placed('a:y')!, 'down')).toBeNull();
    const corner = { top: 0, left: 0, bottom: 0, right: 0 };
    expect(layout.between(corner, { ...corner, left: 1, right: 1 })).toEqual({
      top: 0,
      left: 0,
      bottom: 1,
      right: 1,
    });
  });
});

describe('two editors on one document', () => {
  const views: EditorView[] = [];
  afterEach(() => views.splice(0).forEach((view) => view.destroy()));

  function editor(ydoc: Y.Doc): EditorView {
    const view = new EditorView(document.body.appendChild(document.createElement('div')), {
      state: EditorState.create({
        schema,
        plugins: [ySyncPlugin(bodyOf(ydoc)), ...editingPlugins(ydoc, ACTIONS)],
      }),
    });
    views.push(view);
    return view;
  }

  it('mount with presence and report every state, the first one during construction', () => {
    const ydoc = new Y.Doc();
    const states: EditorState[] = [];
    const view = liveView(
      document.body.appendChild(document.createElement('div')),
      ydoc,
      new Awareness(ydoc),
      {
        notes: null,
        editable: () => true,
        onState: (state) => states.push(state),
        onFocus: () => {},
        onInner: () => {},
        actions: ACTIONS,
      },
    );
    views.push(view);
    expect(states.length).toBeGreaterThan(0);
    view.dispatch(view.state.tr.insertText('Uvod', 1));
    expect(states.at(-1)!.doc.textContent).toBe('Uvod');
    expect(bodyOf(ydoc).length).toBe(1);
  });

  it('share text, blocks with ids and headings in the layout the backend reads', () => {
    const left = new Y.Doc();
    const right = new Y.Doc();
    connect(left, right);
    const mine = editor(left);
    const theirs = editor(right);

    mine.dispatch(mine.state.tr.insertText('Ponuda', 1));
    retype(heading, { level: 2 })(mine.state, mine.dispatch);
    mine.dispatch(mine.state.tr.setSelection(TextSelection.atEnd(mine.state.doc)));
    splitBlock(mine.state, mine.dispatch);
    mine.dispatch(mine.state.tr.insertText('Cijene u eurima.'));

    expect(theirs.state.doc.toJSON()).toEqual(mine.state.doc.toJSON());
    const [title, text] = bodyOf(right).toArray() as Y.XmlElement[];
    expect(title.nodeName).toBe('heading');
    expect(title.getAttribute('level')).toBe(2);
    expect(text.nodeName).toBe('paragraph');
    expect((text.get(0) as Y.XmlText).toDelta()).toEqual([{ insert: 'Cijene u eurima.' }]);
    expect(new Set([title, text].map((block) => block.getAttribute('id'))).size).toBe(2);
  });

  it('store a mark as a text attribute', () => {
    const ydoc = new Y.Doc();
    const view = editor(ydoc);
    view.dispatch(view.state.tr.insertText('Ukupno: 120 €', 1));
    view.dispatch(view.state.tr.addMark(1, 7, schema.marks.strong.create()));
    const [block] = bodyOf(ydoc).toArray() as Y.XmlElement[];
    expect((block.get(0) as Y.XmlText).toDelta()).toEqual([
      { insert: 'Ukupno', attributes: { strong: {} } },
      { insert: ': 120 €' },
    ]);
  });
});
