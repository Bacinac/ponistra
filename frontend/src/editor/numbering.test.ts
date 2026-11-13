// @vitest-environment jsdom
import type { Node } from 'prosemirror-model';
import { TextSelection } from 'prosemirror-state';
import type { EditorView } from 'prosemirror-view';
import { afterEach, describe, expect, it } from 'vitest';
import { Awareness } from 'y-protocols/awareness';
import * as Y from 'yjs';
import { hr } from '../i18n/hr';
import { pastedHTML } from './clipboard';
import type { Context } from './command';
import { available, COMMANDS } from './commands';
import { contentsStore } from './contents';
import { listStore } from './forms';
import { GridClient } from './grids';
import { historyIn } from './history';
import { liveView, type Actions } from './Editor';
import { numbered, renumber, startOf, tallies, writeTally, type Counters } from './numbering';
import { numeral } from './numerals';
import { schema } from './schema';
import type { Style, Styling } from './styling';
import { linesOf } from './tables';

/** Grids no server answers: these tests write no table's cells. */
function closedGrids(): GridClient {
  const grids = new GridClient('00000000-0000-0000-0000-000000000001');
  grids.close();
  return grids;
}

const { doc, paragraph, heading } = schema.nodes;
const NO_TABLES = () => null;

function style(kind: Style['kind'], look: Partial<Style> = {}): Style {
  return {
    kind,
    name: '',
    font: 'text',
    size: 12,
    bold: false,
    italic: false,
    color: null,
    align: null,
    before: 0,
    after: 9,
    line: 1.6,
    numbering: '',
    prefix: '',
    suffix: '',
    nested: false,
    kerning: true,
    ...look,
  };
}

const PLAIN: Styling = {
  theme: { headings: 'Inter', text: 'Inter' },
  styles: {
    text: style('text'),
    h1: style('h1'),
    h2: style('h2'),
    h3: style('h3'),
    article: style('text', { name: 'Članak' }),
  },
};

const NUMBERED: Styling = {
  ...PLAIN,
  styles: {
    ...PLAIN.styles,
    h1: style('h1', { numbering: '1', suffix: '.' }),
    h2: style('h2', { numbering: '1', suffix: '.', nested: true }),
    h3: style('h3', { numbering: 'a', suffix: ')' }),
    article: style('text', {
      name: 'Članak',
      numbering: '1',
      prefix: 'Članak ',
      suffix: '.',
    }),
  },
};

const h = (level: number, words: string, restart = false) =>
  heading.create({ level, restart }, schema.text(words));
const p = (words: string, attrs: Record<string, unknown> = {}) =>
  paragraph.create(attrs, schema.text(words));

function labelsOf(content: Node[], styling = NUMBERED, start: Counters = {}): string[] {
  const written = doc.create(null, content);
  return [...numbered(written, styling, start, NO_TABLES).labels.values()];
}

describe('numeral', () => {
  it('writes a count in each form', () => {
    expect([1, 2, 3].map((count) => numeral(count, '1'))).toEqual(['1', '2', '3']);
    expect(numeral(28, 'a')).toBe('ab');
    expect(numeral(3, 'A')).toBe('C');
    expect(numeral(4, 'i')).toBe('iv');
    expect(numeral(9, 'I')).toBe('IX');
    expect(numeral(0, 'a')).toBe('0');
  });
});

describe('numbered', () => {
  it('numbers each heading level on, starting the levels below again', () => {
    expect(
      labelsOf([
        h(1, 'Uvod'),
        h(2, 'Cilj'),
        h(2, 'Opseg'),
        h(3, 'Iznimke'),
        h(1, 'Cijene'),
        h(2, 'Popusti'),
      ]),
    ).toEqual(['1.', '1.1.', '1.2.', 'a)', '2.', '2.1.']);
  });

  it('nests only the numbered levels above, a skipped one as 0', () => {
    const h3 = style('h3', { numbering: '1', suffix: '.', nested: true });
    const styling = { ...NUMBERED, styles: { ...NUMBERED.styles, h3 } };
    expect(labelsOf([h(1, 'Uvod'), h(3, 'Iznimke')], styling)).toEqual(['1.', '1.0.1.']);
    const unnumbered = {
      ...styling,
      styles: { ...styling.styles, h1: style('h1') },
    };
    expect(labelsOf([h(1, 'Uvod'), h(2, 'Cilj'), h(3, 'Iznimke')], unnumbered)).toEqual([
      '1.',
      '1.1.',
    ]);
  });

  it('numbers a style of its own on through the tab, but never a list item', () => {
    expect(
      labelsOf([
        p('Predmet', { style: 'article' }),
        p('Obični tekst'),
        p('Stavka', { style: 'article', list: 'number' }),
        h(1, 'Cijene'),
        p('Plaćanje', { style: 'article' }),
      ]),
    ).toEqual(['Članak 1.', '1.', 'Članak 2.']);
  });

  it('starts from 1 again where a block says so', () => {
    expect(labelsOf([h(1, 'Uvod'), h(1, 'Prilozi', true), h(1, 'Kraj')])).toEqual([
      '1.',
      '1.',
      '2.',
    ]);
  });

  it('counts on from the tabs before, and tallies every block for the tabs after', () => {
    const written = doc.create(null, [h(2, 'Cilj'), p('Tekst'), h(1, 'Cijene'), p('Tekst')]);
    const { labels, tally } = numbered(
      written,
      NUMBERED,
      {
        '#1': 2,
        '#2': 1,
        text: 7,
      },
      NO_TABLES,
    );
    expect([...labels.values()]).toEqual(['2.2.', '3.']);
    expect(tally).toEqual({
      '#1': { reset: false, count: 1 },
      '#2': { reset: true, count: 0 },
      '#3': { reset: true, count: 0 },
      '#4': { reset: true, count: 0 },
      text: { reset: false, count: 2 },
    });
    expect(numbered(written, PLAIN, {}, NO_TABLES).labels.size).toBe(0);
    expect(numbered(written, PLAIN, {}, NO_TABLES).tally).toEqual(tally);
  });

  it("numbers a table's headings row by row, whatever order its cells were written in", () => {
    const cell = (row: string, col: string, words: string) =>
      schema.nodes.cell.create({ row, col }, h(1, words));
    const grid = { rows: ['a', 'b'], cols: ['x', 'y'] };
    const table = schema.nodes.table.create({ id: 't', grid }, [
      cell('b', 'x', 'Treći'),
      cell('a', 'y', 'Drugi'),
      cell('a', 'x', 'Prvi'),
    ]);
    const written = doc.create(null, [table, h(1, 'Četvrti')]);
    const { labels } = numbered(written, NUMBERED, {}, linesOf(null));
    const found = [...labels].map(([pos, label]) => `${label} ${written.nodeAt(pos)!.textContent}`);
    expect(found).toEqual(['1. Prvi', '2. Drugi', '3. Treći', '4. Četvrti']);
  });
});

describe('tallies', () => {
  it('lead each tab on from the tabs before it in reading order', () => {
    const own = new Y.Doc();
    writeTally(own, 'a', {
      '#1': { reset: false, count: 2 },
      '#2': { reset: false, count: 3 },
    });
    writeTally(own, 'b', {
      '#1': { reset: true, count: 1 },
      '#2': { reset: true, count: 0 },
    });
    writeTally(own, 'c', { '#2': { reset: false, count: 1 } });
    expect(startOf(own, ['a', 'b', 'c', 'd'], 'a')).toEqual({});
    expect(startOf(own, ['a', 'b', 'c', 'd'], 'b')).toEqual({
      '#1': 2,
      '#2': 3,
    });
    expect(startOf(own, ['a', 'b', 'c', 'd'], 'd')).toEqual({
      '#1': 1,
      '#2': 1,
    });
    expect(startOf(own, ['c', 'a', 'd'], 'd')).toEqual({ '#1': 2, '#2': 4 });
  });

  it('are written only when they change, and never as nothing new', () => {
    const own = new Y.Doc();
    let writes = 0;
    own.on('update', () => (writes += 1));
    writeTally(own, 'a', {});
    expect(tallies(own).has('a')).toBe(false);
    writeTally(own, 'a', { text: { reset: false, count: 1 } });
    writeTally(own, 'a', { text: { reset: false, count: 1 } });
    expect(writes).toBe(1);
    writeTally(own, 'a', {});
    expect(tallies(own).get('a')).toEqual({});
  });

  it('skip what a broken client wrote', () => {
    const own = new Y.Doc();
    tallies(own).set('a', {
      '#1': { reset: false, count: -1 },
      text: { reset: false, count: 2 },
    });
    expect(startOf(own, ['a', 'b'], 'b')).toEqual({ text: 2 });
  });
});

describe('in the editor', () => {
  const views: EditorView[] = [];
  afterEach(() => views.splice(0).forEach((view) => view.destroy()));

  function editor(styling: Styling, start: Counters = {}) {
    const ydoc = new Y.Doc();
    const actions: Actions = {
      open: () => {},
      filter: () => {},
      ran: () => {},
      consent: () => {},
      fail: (error) => {
        throw error;
      },
      follow: () => {},
      label: { current: (key) => hr[key] },
      place: {
        document: '00000000-0000-0000-0000-000000000001',
        tab: '00000000-0000-0000-0000-000000000002',
        address: '/d/probni-dokument-0000000000000000000001',
      },
      styling: { current: styling },
      notes: { current: null },
      numbers: { current: start },
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
    const view = liveView(
      document.body.appendChild(document.createElement('div')),
      ydoc,
      new Awareness(ydoc),
      {
        notes: null,
        editable: () => true,
        onState: () => {},
        onFocus: () => {},
        onInner: () => {},
        actions,
      },
    );
    views.push(view);
    view.dispatch(
      view.state.tr.replaceWith(0, view.state.doc.content.size, [
        h(1, 'Uvod'),
        p('Tekst'),
        h(2, 'Cilj'),
        p('Stavka', { list: 'number' }),
      ]),
    );
    const context = (): Context => ({
      view,
      doc: ydoc,
      history: historyIn(view.state)!,
      styling: actions.styling.current,
      place: actions.place,
      notes: null,
      desk: null,
      parts: null,
      slides: null,
      present: null,
      lists: actions.lists,
      open: actions.open,
      ran: actions.ran,
      consent: actions.consent,
      fail: actions.fail,
      label: actions.label.current,
      suggesting: false,
      suggest: actions.suggest,
      visitTab: actions.visitTab,
    });
    return { view, context };
  }

  const shown = (view: EditorView) =>
    [...view.dom.querySelectorAll('[data-number]')].map((block) =>
      block.getAttribute('data-number'),
    );

  const at = (view: EditorView, text: string) => {
    let found = -1;
    view.state.doc.forEach((node, offset) => {
      if (node.textContent === text) found = offset + 1;
    });
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, found)));
  };

  it('shows the numbers beside the text, from the tabs before, and again when styles change', () => {
    const { view } = editor(PLAIN, { '#1': 4 });
    expect(shown(view)).toEqual([]);
    expect(view.state.doc.textContent).toBe('UvodTekstCiljStavka');
    renumber(view, NUMBERED, { '#1': 4 });
    expect(shown(view)).toEqual(['5.', '5.1.']);
    renumber(view, NUMBERED, {});
    expect(shown(view)).toEqual(['1.', '1.1.']);
  });

  it('copies the numbers as text, which a paste back here drops again', () => {
    const { view } = editor(NUMBERED);
    const { dom, text } = view.serializeForClipboard(
      view.state.doc.slice(0, view.state.doc.content.size),
    );
    expect(text).toBe('1. Uvod\n\nTekst\n\n1.1. Cilj\n\n1. Stavka');
    expect(dom.querySelector('h2')!.textContent).toBe('1.1. Cilj');
    expect(pastedHTML(dom.innerHTML)).not.toContain('1.1.');
  });

  it('starts a numbered block or item from 1 again, and continues it', () => {
    const { view, context } = editor(NUMBERED);
    const restart = COMMANDS.find((command) => command.id === 'numbering.restart')!;
    const proceed = COMMANDS.find((command) => command.id === 'numbering.continue')!;
    at(view, 'Tekst');
    expect(available(restart, context())).toBe(false);
    at(view, 'Cilj');
    expect(available(proceed, context())).toBe(false);
    restart.run(context());
    expect(view.state.selection.$from.parent.attrs.restart).toBe(true);
    expect(available(restart, context())).toBe(false);
    expect(available(proceed, context())).toBe(true);
    proceed.run(context());
    expect(view.state.selection.$from.parent.attrs.restart).toBe(false);
    at(view, 'Stavka');
    expect(available(restart, context())).toBe(true);
  });

  it('continues a list across the blocks since its last item', () => {
    const { view, context } = editor(NUMBERED);
    const restart = COMMANDS.find((command) => command.id === 'numbering.restart')!;
    const proceed = COMMANDS.find((command) => command.id === 'numbering.continue')!;
    const end = view.state.doc.content.size;
    view.dispatch(view.state.tr.insert(end, [p('Napomena'), p('Druga', { list: 'number' })]));
    const markers = () =>
      [...view.dom.querySelectorAll('[data-marker]')].map((item) =>
        item.getAttribute('data-marker'),
      );
    expect(markers()).toEqual(['1.', '1.']);
    at(view, 'Stavka');
    expect(available(proceed, context())).toBe(false);
    at(view, 'Druga');
    expect(available(proceed, context())).toBe(true);
    proceed.run(context());
    expect(view.state.selection.$from.parent.attrs.continued).toBe(true);
    expect(markers()).toEqual(['1.', '2.']);
    expect(available(proceed, context())).toBe(false);
    restart.run(context());
    expect(view.state.selection.$from.parent.attrs).toMatchObject({
      restart: true,
      continued: false,
    });
    expect(markers()).toEqual(['1.', '1.']);
  });

  it('keeps a restart on the first half of a split block only', () => {
    const { view, context } = editor(NUMBERED);
    at(view, 'Uvod');
    COMMANDS.find((command) => command.id === 'numbering.restart')!.run(context());
    const { from } = view.state.selection;
    view.dispatch(view.state.tr.split(from + 2));
    const restarts: boolean[] = [];
    view.state.doc.forEach((node) => restarts.push(node.attrs.restart === true));
    expect(restarts).toEqual([true, false, false, false, false]);
    expect(shown(view)).toEqual(['1.', '2.', '2.1.']);
  });
});
