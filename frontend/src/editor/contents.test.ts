// @vitest-environment jsdom
import { TextSelection } from 'prosemirror-state';
import type { EditorView } from 'prosemirror-view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Awareness } from 'y-protocols/awareness';
import * as Y from 'yjs';
import { hr } from '../i18n/hr';
import type { Context } from './command';
import { available, COMMANDS, perform } from './commands';
import {
  chaptersOf,
  contentsStore,
  headingsOf,
  keptHeadings,
  writeHeadings,
  type Chapter,
} from './contents';
import { listStore } from './forms';
import { GridClient } from './grids';
import { historyIn } from './history';
import { liveView, type Actions } from './Editor';
import { headingNumbers, numbered, writeTally } from './numbering';
import { schema } from './schema';
import type { Style, Styling } from './styling';

/** Grids no server answers: these tests write no table's cells. */
function closedGrids(): GridClient {
  const grids = new GridClient('00000000-0000-0000-0000-000000000001');
  grids.close();
  return grids;
}

const { doc, paragraph, heading } = schema.nodes;
const NO_TABLES = () => null;
const HOME = '/d/ugovor-0000000000000000000001';

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

const NUMBERED: Styling = {
  theme: { headings: 'Inter', text: 'Inter' },
  styles: {
    text: style('text'),
    h1: style('h1', { numbering: '1', suffix: '.' }),
    h2: style('h2', { numbering: '1', suffix: '.', nested: true }),
    h3: style('h3'),
    article: style('h1', { name: 'Članak', numbering: '1', prefix: 'Članak ', suffix: '.' }),
  },
};

const h = (level: number, words: string, attrs: Record<string, unknown> = {}) =>
  heading.create({ id: `${level}-${words}`, level, ...attrs }, words ? schema.text(words) : null);
const p = (words: string) => paragraph.create(null, schema.text(words));

const TABS = [
  { id: 'a', title: 'Ugovor' },
  { id: 'b', title: '' },
  { id: 'c', title: 'Prilog' },
];

/** The document's own state as the editors of its tabs keep it. */
function kept(tabs: Record<string, ReturnType<typeof doc.create>>): Y.Doc {
  const own = new Y.Doc();
  for (const [tab, content] of Object.entries(tabs)) {
    writeHeadings(own, tab, headingsOf(content, NO_TABLES));
    writeTally(own, tab, numbered(content, NUMBERED, {}, NO_TABLES).tally);
  }
  return own;
}

describe('the headings a tab keeps', () => {
  it('are all its headings, numbered as its editor numbers them', () => {
    const content = doc.create(null, [
      h(1, 'Uvod'),
      h(2, 'Cilj'),
      h(1, ''),
      h(1, 'Članak', { style: 'article' }),
      h(2, 'Opseg', { restart: true }),
    ]);
    const headings = headingsOf(content, NO_TABLES);
    expect(headings.map(({ text, style, restart }) => [text, style, restart])).toEqual([
      ['Uvod', null, false],
      ['Cilj', null, false],
      ['', null, false],
      ['Članak', 'article', false],
      ['Opseg', null, true],
    ]);
    const labels = [...numbered(content, NUMBERED, { '#1': 4 }, NO_TABLES).labels.values()];
    expect(headingNumbers(headings, NUMBERED, { '#1': 4 })).toEqual(labels);
  });

  it('are written only when they change', () => {
    const own = new Y.Doc();
    const updates = vi.fn();
    own.on('update', updates);
    writeHeadings(own, 'a', []);
    const headings = headingsOf(doc.create(null, [h(1, 'Uvod')]), NO_TABLES);
    writeHeadings(own, 'a', headings);
    writeHeadings(own, 'a', [...headings]);
    expect(updates).toHaveBeenCalledTimes(1);
    expect(keptHeadings(own).get('a')).toEqual(headings);
  });
});

describe('chaptersOf', () => {
  it('lists the open tab as its editor shows it and the others as they were kept, numbered on', () => {
    const own = kept({
      a: doc.create(null, [h(1, 'Uvod'), h(2, 'Cilj'), h(1, ''), p('Tekst')]),
      b: doc.create(null, [h(1, 'Opseg')]),
      c: doc.create(null, [h(1, 'Cijene'), h(2, 'Popust'), h(3, 'Iznimke')]),
    });
    const open = [{ id: '1-Opseg', level: 1, number: '3.', text: 'Opseg' }];
    const chapters = chaptersOf(own, TABS, { tab: 'b', headings: open }, NUMBERED, HOME);
    expect(chapters.map(({ headings }) => headings)).toEqual([
      [
        { id: '1-Uvod', level: 1, number: '1.', text: 'Uvod' },
        { id: '2-Cilj', level: 2, number: '1.1.', text: 'Cilj' },
      ],
      open,
      [
        { id: '1-Cijene', level: 1, number: '4.', text: 'Cijene' },
        { id: '2-Popust', level: 2, number: '4.1.', text: 'Popust' },
        { id: '3-Iznimke', level: 3, number: null, text: 'Iznimke' },
      ],
    ]);
    expect(chapters[0].href).toBe(HOME);
    expect(chapters[2].href).toMatch(new RegExp(`^${HOME}/prilog-`));
  });

  it('passes over what another client kept that is not a heading', () => {
    const own = new Y.Doc();
    keptHeadings(own).set('a', [
      { id: 'x', level: 9, text: 'Duboko', style: null, restart: false },
      { id: 'y', level: 1, text: 'Uvod', style: null, restart: false },
      'Naslov' as never,
    ]);
    const chapters = chaptersOf(own, TABS, { tab: 'b', headings: [] }, NUMBERED, HOME);
    expect(chapters[0].headings).toEqual([{ id: 'y', level: 1, number: '1.', text: 'Uvod' }]);
  });
});

describe('the contents block', () => {
  const views: EditorView[] = [];
  afterEach(() => views.splice(0).forEach((view) => view.destroy()));

  function editor(editable = true) {
    const ydoc = new Y.Doc();
    const go = vi.fn();
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
      place: { document: 'd', tab: 'a', address: HOME },
      styling: { current: NUMBERED },
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
      contents: contentsStore(go),
      lists: listStore(new Y.Doc()),
      grids: closedGrids(),
    };
    const view = liveView(
      document.body.appendChild(document.createElement('div')),
      ydoc,
      new Awareness(ydoc),
      {
        notes: null,
        editable: () => editable,
        onState: () => {},
        onFocus: () => {},
        onInner: () => {},
        actions,
      },
    );
    views.push(view);
    view.dispatch(view.state.tr.replaceWith(0, view.state.doc.content.size, [p('Prije')]));
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 6)));
    const context: Context = {
      view,
      doc: ydoc,
      history: historyIn(view.state)!,
      styling: NUMBERED,
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
    };
    return { view, context, store: actions.contents, go };
  }

  const insert = COMMANDS.find(({ id }) => id === 'insert.contents')!;
  const lines = (view: EditorView) =>
    [...view.dom.querySelectorAll('nav[data-contents] li')].map((item) => item.textContent);

  const CHAPTERS: Chapter[] = [
    {
      href: HOME,
      headings: [
        { id: 'u', level: 1, number: '1.', text: 'Uvod' },
        { id: 'c', level: 2, number: '1.1.', text: 'Cilj' },
        { id: 'i', level: 4, number: null, text: 'Iznimke' },
      ],
    },
    { href: `${HOME}/b`, headings: [{ id: 'o', level: 1, number: '2.', text: 'Opseg' }] },
  ];

  it("is put in after the text and lists every tab's headings to its depth", () => {
    const { view, context, store } = editor();
    expect(available(insert, context)).toBe(true);
    perform(insert, context);
    expect(view.state.doc.toJSON().content.map(({ type }: { type: string }) => type)).toEqual([
      'paragraph',
      'contents',
      'paragraph',
    ]);
    expect(view.state.selection.$from.parent.type).toBe(paragraph);
    expect(view.state.selection.from).toBe(view.state.doc.content.size - 1);
    expect(view.dom.querySelector('nav')!.textContent).toBe(hr['contents.empty']);
    store.set(CHAPTERS);
    expect(lines(view)).toEqual(['1.Uvod', '1.1.Cilj', '2.Opseg']);
    const links = [...view.dom.querySelectorAll('nav a')].map((link) => link.getAttribute('href'));
    expect(links).toEqual([`${HOME}?block=u`, `${HOME}?block=c`, `${HOME}/b?block=o`]);
  });

  it('is followed with Ctrl where it is written and at once where it is read', () => {
    const written = editor();
    perform(insert, written.context);
    written.store.set(CHAPTERS);
    const link = () => written.view.dom.querySelectorAll('nav a')[0];
    link().dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    expect(written.go).not.toHaveBeenCalled();
    link().dispatchEvent(
      new MouseEvent('click', { bubbles: true, cancelable: true, ctrlKey: true }),
    );
    expect(written.go).toHaveBeenCalledWith(`${HOME}?block=u`);

    const read = editor(false);
    read.view.dispatch(read.view.state.tr.insert(0, schema.nodes.contents.create({ depth: 1 })));
    read.store.set(CHAPTERS);
    expect(lines(read.view)).toEqual(['1.Uvod', '2.Opseg']);
    read.view.dom
      .querySelectorAll('nav a')[0]
      .dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    expect(read.go).toHaveBeenCalledWith(`${HOME}?block=u`);
  });
});
