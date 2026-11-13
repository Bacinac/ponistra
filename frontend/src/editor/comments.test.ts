// @vitest-environment jsdom
import { TextSelection } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Awareness } from 'y-protocols/awareness';
import * as Y from 'yjs';
import type { Desk } from '../comments';
import { hr } from '../i18n/hr';
import type { Context } from './command';
import { COMMANDS, perform } from './commands';
import { draftOf, placedOf, showComments, type Anchored } from './comments';
import { contentsStore } from './contents';
import { listStore } from './forms';
import { GridClient } from './grids';
import { historyIn } from './history';
import { liveView, type Actions } from './Editor';
import { schema } from './schema';

/** Grids no server answers: these tests write no table's cells. */
function closedGrids(): GridClient {
  const grids = new GridClient('00000000-0000-0000-0000-000000000001');
  grids.close();
  return grids;
}

const { paragraph, footnote } = schema.nodes;

// jsdom lays nothing out: it has nothing to scroll and no place to measure a focused selection.
Element.prototype.scrollIntoView ??= () => {};
Range.prototype.getClientRects ??= () => [] as unknown as DOMRectList;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();

const desk: { current: Desk | null } = { current: null };
const views: EditorView[] = [];
const awarenesses: Awareness[] = [];
afterEach(() => {
  views.splice(0).forEach((view) => view.destroy());
  awarenesses.splice(0).forEach((awareness) => awareness.destroy());
  desk.current = null;
});

const ACTIONS: Actions = {
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
  styling: { current: { theme: { headings: 'Inter', text: 'Inter' }, styles: {} } },
  notes: { current: null },
  numbers: { current: {} },
  locale: { current: 'hr' },
  proposer: { current: null },
  suggest: () => {},
  visitTab: () => false,
  desk,
  parts: { current: null },
  slides: { current: null },
  present: { current: null },
  contents: contentsStore(() => {}),
  lists: listStore(new Y.Doc()),
  grids: closedGrids(),
};

function editor(ydoc = new Y.Doc()): EditorView {
  const awareness = new Awareness(ydoc);
  awarenesses.push(awareness);
  const view = liveView(document.body.appendChild(document.createElement('div')), ydoc, awareness, {
    notes: document.body.appendChild(document.createElement('div')),
    editable: () => true,
    onState: () => {},
    onFocus: () => {},
    onInner: () => {},
    actions: ACTIONS,
  });
  views.push(view);
  return view;
}

function pair(): [EditorView, EditorView] {
  const [left, right] = [new Y.Doc(), new Y.Doc()];
  left.on('update', (update: Uint8Array, origin: unknown) => {
    if (origin !== right) Y.applyUpdate(right, update, left);
  });
  right.on('update', (update: Uint8Array, origin: unknown) => {
    if (origin !== left) Y.applyUpdate(left, update, right);
  });
  return [editor(left), editor(right)];
}

function contextOf(view: EditorView, with_: Desk | null): Context {
  return {
    view,
    doc: new Y.Doc(),
    history: historyIn(view.state)!,
    styling: ACTIONS.styling.current,
    place: ACTIONS.place,
    notes: null,
    desk: with_,
    parts: null,
    slides: null,
    present: null,
    lists: ACTIONS.lists,
    open: ACTIONS.open,
    ran: ACTIONS.ran,
    consent: ACTIONS.consent,
    fail: ACTIONS.fail,
    label: ACTIONS.label.current,
    suggesting: false,
    suggest: ACTIONS.suggest,
    visitTab: ACTIONS.visitTab,
  };
}

function at(view: EditorView, text: string): number {
  let found = -1;
  view.state.doc.descendants((node, pos) => {
    const index = node.isText ? node.text!.indexOf(text) : -1;
    if (found < 0 && index >= 0) found = pos + index;
    return found < 0;
  });
  if (found < 0) throw new Error(`no "${text}" in the text`);
  return found;
}

function select(view: EditorView, text: string): void {
  const from = at(view, text);
  view.dispatch(
    view.state.tr.setSelection(TextSelection.create(view.state.doc, from, from + text.length)),
  );
}

function thread(view: EditorView, id: string, text: string): Anchored {
  select(view, text);
  return { id, anchor: draftOf(view.state)!.anchor };
}

function marked(view: EditorView): Record<string, string> {
  const texts: Record<string, string> = {};
  for (const span of view.dom.querySelectorAll<HTMLElement>('[data-thread]')) {
    const id = span.dataset.thread!;
    texts[id] = (texts[id] ?? '') + span.textContent;
  }
  return texts;
}

function show(views: EditorView[], threads: Anchored[], active: string | null = null): void {
  for (const view of views) showComments(view, { threads, active, draft: null });
}

describe('a comment', () => {
  it('keeps to its words as either side edits around and inside them', () => {
    const [mine, theirs] = pair();
    mine.dispatch(mine.state.tr.insertText('Rok plaćanja je 30 dana od primitka.', 1));
    const commented = thread(mine, 't1', '30 dana');
    show([mine, theirs], [commented]);
    expect(marked(mine)).toEqual({ t1: '30 dana' });
    expect(marked(theirs)).toEqual({ t1: '30 dana' });

    for (const [view, edit] of [
      [theirs, (v: EditorView) => v.state.tr.insertText('0', at(v, '0 dana'))],
      [mine, (v: EditorView) => v.state.tr.insertText(' radnih', at(v, ' od'))],
      [theirs, (v: EditorView) => v.state.tr.insertText('do ', at(v, '300'))],
      [mine, (v: EditorView) => v.state.tr.delete(at(v, 'dana') + 3, at(v, ' radnih'))],
    ] as const) {
      view.dispatch(edit(view));
    }
    expect(mine.state.doc.textContent).toBe('Rok plaćanja je do 300 dan radnih od primitka.');
    expect(marked(mine)).toEqual({ t1: '300 dan' });
    expect(marked(theirs)).toEqual({ t1: '300 dan' });
  });

  it('loses its place once its words are gone, the rest kept in the order of the text', () => {
    const [mine, theirs] = pair();
    mine.dispatch(mine.state.tr.insertText('Rok plaćanja je 30 dana od primitka računa.', 1));
    const threads = [thread(mine, 'late', 'računa'), thread(mine, 'early', 'Rok')];
    show([mine, theirs], threads);
    expect(placedOf(mine.state)).toEqual({ order: ['early', 'late'], lost: [] });

    theirs.dispatch(theirs.state.tr.delete(at(theirs, ' računa'), at(theirs, '.')));
    expect(placedOf(mine.state)).toEqual({ order: ['early'], lost: ['late'] });
    expect(placedOf(theirs.state)).toEqual({ order: ['early'], lost: ['late'] });
    mine.dispatch(mine.state.tr.delete(at(mine, 'Rok'), at(mine, ' plaćanja')));
    expect(placedOf(mine.state)).toEqual({ order: [], lost: ['late', 'early'] });
  });

  it('marks the active thread apart and lets a click on its words pick it', () => {
    const view = editor();
    view.dispatch(view.state.tr.insertText('Rok plaćanja je 30 dana.', 1));
    const show_ = vi.fn();
    desk.current = { show: show_ } as unknown as Desk;
    const threads = [thread(view, 'rok', 'Rok plaćanja'), thread(view, 'dani', '30 dana')];
    show([view], threads, 'dani');
    const active = view.dom.querySelector('.ponistra-comment-active') as HTMLElement;
    expect(active.dataset.thread).toBe('dani');
    const click = (pos: number) =>
      view.someProp('handleClick', (handle) => handle(view, pos, new MouseEvent('click')));
    click(at(view, 'plaćanja') + 2);
    click(at(view, ' je') + 2);
    expect(show_.mock.calls).toEqual([['rok'], [null]]);
  });

  it('is started on the selected words by anyone who reads, without the text of its notes', () => {
    const view = editor();
    view.dispatch(
      view.state.tr.replaceWith(0, view.state.doc.content.size, [
        paragraph.create({ id: 'p1' }, [
          schema.text('Rok'),
          footnote.create({ id: 'n1', kind: 'foot' }, schema.text('napomena')),
          schema.text(' plaćanja'),
        ]),
        paragraph.create({ id: 'p2' }, schema.text('je 30 dana.')),
      ]),
    );
    view.setProps({ editable: () => false });
    const start = vi.fn();
    const comment = COMMANDS.find((command) => command.id === 'comment.add')!;
    const context = contextOf(view, { start } as unknown as Desk);
    expect(perform(comment, context)).toBe(false);
    view.dispatch(
      view.state.tr.setSelection(
        TextSelection.create(view.state.doc, at(view, 'ok'), at(view, ' dana')),
      ),
    );
    expect(perform(comment, contextOf(view, null))).toBe(false);
    expect(perform(comment, context)).toBe(true);
    expect(start).toHaveBeenCalledWith({
      tab: ACTIONS.place.tab,
      anchor: { from: expect.any(Object), to: expect.any(Object) },
      quote: 'ok plaćanja je 30',
    });
  });

  it('is started by Ctrl+Alt+M also where the layout makes that chord AltGr', () => {
    const view = editor();
    view.dispatch(view.state.tr.insertText('Rok plaćanja', 1));
    const start = vi.fn();
    desk.current = { start } as unknown as Desk;
    select(view, 'plaćanja');
    const chord = { code: 'KeyM', ctrlKey: true, altKey: true, bubbles: true, cancelable: true };
    const pressed = new KeyboardEvent('keydown', { ...chord, key: '§' });
    view.dom.dispatchEvent(pressed);
    expect(pressed.defaultPrevented).toBe(true);
    expect(start).toHaveBeenCalledWith(expect.objectContaining({ quote: 'plaćanja' }));
  });
});
