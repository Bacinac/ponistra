// @vitest-environment jsdom
import { DOMParser as Parser, Slice } from 'prosemirror-model';
import { NodeSelection, TextSelection } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Awareness } from 'y-protocols/awareness';
import * as Y from 'yjs';
import { hr } from '../i18n/hr';
import { clipboardSerializer, clipboardText, pastedHTML } from './clipboard';
import type { Context } from './command';
import { COMMANDS, perform, refocus, whereOf } from './commands';
import { contentsStore } from './contents';
import { listStore } from './forms';
import { GridClient } from './grids';
import { historyIn } from './history';
import { liveView, type Actions } from './Editor';
import { bodyOf } from './tab';
import {
  countsOf,
  noteById,
  noteCounts,
  notesIn,
  numberFrom,
  offsetOf,
  placed,
  setRestart,
  writeCounts,
  type TabNotes,
} from './notes';
import { schema } from './schema';

/** Grids no server answers: these tests write no table's cells. */
function closedGrids(): GridClient {
  const grids = new GridClient('00000000-0000-0000-0000-000000000001');
  grids.close();
  return grids;
}

const { doc, paragraph, heading, footnote } = schema.nodes;

// jsdom lays nothing out: it has nothing to scroll and no place to measure a focused selection.
Element.prototype.scrollIntoView ??= () => {};
Range.prototype.getClientRects ??= () => [] as unknown as DOMRectList;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();

const views: EditorView[] = [];
afterEach(() => views.splice(0).forEach((view) => view.destroy()));

const notesNow: { current: TabNotes | null } = { current: null };

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
  notes: notesNow,
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

function editor(ydoc = new Y.Doc()): { view: EditorView; notes: HTMLElement } {
  const notes = document.body.appendChild(document.createElement('div'));
  const view = liveView(
    document.body.appendChild(document.createElement('div')),
    ydoc,
    new Awareness(ydoc),
    {
      notes,
      editable: () => true,
      onState: () => {},
      onFocus: () => {},
      onInner: () => {},
      actions: ACTIONS,
    },
  );
  views.push(view);
  return { view, notes };
}

function contextOf(view: EditorView, outer: EditorView, ydoc: Y.Doc): Context {
  return {
    view,
    doc: ydoc,
    history: historyIn(outer.state)!,
    styling: ACTIONS.styling.current,
    place: ACTIONS.place,
    notes: notesNow.current,
    desk: null,
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

function run(id: string, context: Context): boolean {
  return perform(
    COMMANDS.find((command) => command.id === id)!,
    context,
  );
}

function write(view: EditorView, text: string): void {
  view.dispatch(view.state.tr.insertText(text));
}

function connect(left: Y.Doc, right: Y.Doc): void {
  left.on('update', (update: Uint8Array, origin: unknown) => {
    if (origin !== right) Y.applyUpdate(right, update, left);
  });
  right.on('update', (update: Uint8Array, origin: unknown) => {
    if (origin !== left) Y.applyUpdate(left, update, right);
  });
}

function listed(notes: HTMLElement, kind: 'foot' | 'end'): string[] {
  return [...notes.querySelectorAll(`[data-notes="${kind}"] li`)].map((item) => item.textContent!);
}

function noted(...parts: (string | [string, 'foot' | 'end'])[]) {
  return doc.create(null, [
    paragraph.create(
      { id: 'p1' },
      parts.map((part) =>
        typeof part === 'string'
          ? schema.text(part)
          : footnote.create({ id: `n${part[0]}`, kind: part[1] }, schema.text(part[0])),
      ),
    ),
  ]);
}

describe('numbers', () => {
  it('count footnotes and endnotes apart, on from the tabs before', () => {
    const content = noted('Cijena', ['a', 'foot'], ' vrijedi', ['b', 'end'], '.', ['c', 'foot']);
    expect(placed(content, { foot: 3, end: 1 }).map(({ kind, label }) => [kind, label])).toEqual([
      ['foot', '4'],
      ['end', 'ii'],
      ['foot', '5'],
    ]);
    expect(countsOf(placed(content, { foot: 3, end: 1 }))).toEqual({ foot: 2, end: 1 });
  });

  it('run on through the tabs in reading order and start again where a tab says so', () => {
    const own = new Y.Doc();
    noteCounts(own).set('a', { foot: 2, end: 1 });
    noteCounts(own).set('b', { foot: 3, end: 0 });
    noteCounts(own).set('gone', { foot: 9, end: 9 });
    const tabs = ['a', 'b', 'c', 'd'];
    expect(offsetOf(own, tabs, 'a')).toEqual({ foot: 0, end: 0 });
    expect(offsetOf(own, tabs, 'c')).toEqual({ foot: 5, end: 1 });
    setRestart(own, 'b', true);
    expect(offsetOf(own, tabs, 'b')).toEqual({ foot: 0, end: 0 });
    expect(offsetOf(own, tabs, 'd')).toEqual({ foot: 3, end: 0 });
    setRestart(own, 'b', false);
    expect(offsetOf(own, tabs, 'd')).toEqual({ foot: 5, end: 1 });
  });

  it('are written only when they change, and not at all for a tab that never had notes', () => {
    const own = new Y.Doc();
    const updates: Uint8Array[] = [];
    own.on('update', (update: Uint8Array) => updates.push(update));
    writeCounts(own, 'a', { foot: 0, end: 0 });
    expect(updates).toHaveLength(0);
    writeCounts(own, 'a', { foot: 1, end: 0 });
    writeCounts(own, 'a', { foot: 1, end: 0 });
    expect(updates).toHaveLength(1);
    writeCounts(own, 'a', { foot: 0, end: 0 });
    expect(noteCounts(own).get('a')).toEqual({ foot: 0, end: 0 });
  });
});

describe('a note in the editor', () => {
  it('is inserted after the selection, listed under the text and written in its own editor', () => {
    const ydoc = new Y.Doc();
    const { view, notes } = editor(ydoc);
    write(view, 'Cijena vrijedi');
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 7)));
    expect(run('insert.footnote', contextOf(view, view, ydoc))).toBe(true);
    const [{ id }] = notesIn(view.state);
    const note = noteById(view, id!)!;
    expect(whereOf(contextOf(note.inner, view, ydoc))).toBe('note');
    expect(note.inner.dom.classList.contains('ponistra-empty')).toBe(true);
    expect(view.state.selection).toBeInstanceOf(NodeSelection);
    const open = vi.spyOn(note, 'open');
    refocus(contextOf(view, view, ydoc));
    expect(open).toHaveBeenCalledOnce();
    write(note.inner, 'Bez PDV-a');
    expect(note.inner.dom.classList.contains('ponistra-empty')).toBe(false);
    expect(view.state.doc.textContent).toBe('CijenaBez PDV-a vrijedi');
    expect(listed(notes, 'foot')).toEqual(['1Bez PDV-a']);
    expect(view.dom.querySelector('sup.ponistra-note')!.getAttribute('data-marker')).toBe('1');

    const [block] = bodyOf(ydoc).toArray() as Y.XmlElement[];
    const mark = block.toArray().find((child) => child instanceof Y.XmlElement) as Y.XmlElement;
    expect([mark.nodeName, mark.getAttribute('kind'), mark.toString()]).toEqual([
      'footnote',
      'foot',
      '<footnote id="' + id + '" kind="foot">Bez PDV-a</footnote>',
    ]);

    historyIn(view.state)!.manager.stopCapturing();
    write(note.inner, '!');
    expect(note.inner.state.doc.textContent).toBe('Bez PDV-a!');
    expect(run('history.undo', contextOf(note.inner, view, ydoc))).toBe(true);
    expect(note.inner.state.doc.textContent).toBe('Bez PDV-a');
  });

  it('sits on the word the spaces typed before it follow, the cursor coming back after them', () => {
    const ydoc = new Y.Doc();
    const { view } = editor(ydoc);
    write(view, 'Rok je 30 dana  ');
    expect(run('insert.footnote', contextOf(view, view, ydoc))).toBe(true);
    const [{ id }] = notesIn(view.state);
    const note = noteById(view, id!)!;
    write(note.inner, 'od isporuke');
    note.back();
    write(view, 'ili ranije');
    const line = view.state.doc.firstChild!;
    expect([line.child(0).text, line.child(1).type, line.child(2).text]).toEqual([
      'Rok je 30 dana',
      footnote,
      '  ili ranije',
    ]);

    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 4)));
    write(view, ' ');
    expect(run('insert.endnote', contextOf(view, view, ydoc))).toBe(true);
    expect(view.state.doc.firstChild!.child(1).type).toBe(footnote);
    expect(view.state.doc.firstChild!.child(0).text).toBe('Rok');
  });

  it('keeps the formatting the toolbar gives its text, turns into an endnote and goes', () => {
    const ydoc = new Y.Doc();
    const { view, notes } = editor(ydoc);
    write(view, 'Rok');
    run('insert.footnote', contextOf(view, view, ydoc));
    const note = noteById(view, notesIn(view.state)[0].id!)!;
    write(note.inner, 'trideset dana');
    note.inner.dispatch(
      note.inner.state.tr.setSelection(TextSelection.create(note.inner.state.doc, 0, 8)),
    );
    const context = contextOf(note.inner, view, ydoc);
    expect(run('format.bold', context)).toBe(true);
    expect(run('style.heading1', context)).toBe(false);
    expect(run('insert.table', context)).toBe(false);
    const inner = view.state.doc.firstChild!.child(1);
    expect(inner.child(0).marks.map((mark) => mark.type.name)).toEqual(['strong']);

    expect(run('note.toEnd', context)).toBe(true);
    expect(listed(notes, 'foot')).toEqual([]);
    expect(listed(notes, 'end')).toEqual(['itrideset dana']);
    expect(run('note.delete', contextOf(note.inner, view, ydoc))).toBe(true);
    expect(view.state.doc.textContent).toBe('Rok');
    expect(notes.querySelectorAll('li')).toHaveLength(0);
  });

  it('numbers on from the tabs before and restarts when the tab says so', () => {
    const ydoc = new Y.Doc();
    const own = new Y.Doc();
    noteCounts(own).set('first', { foot: 4, end: 0 });
    notesNow.current = {
      offset: offsetOf(own, ['first', 'second'], 'second'),
      restart: false,
      first: false,
      setRestart: (restart) => setRestart(own, 'second', restart),
    };
    const { view, notes } = editor(ydoc);
    run('insert.footnote', contextOf(view, view, ydoc));
    expect(listed(notes, 'foot')).toEqual(['5']);
    const note = noteById(view, notesIn(view.state)[0].id!)!;
    expect(run('note.continue', contextOf(note.inner, view, ydoc))).toBe(false);
    expect(run('note.restart', contextOf(note.inner, view, ydoc))).toBe(true);
    numberFrom(view, offsetOf(own, ['first', 'second'], 'second'));
    expect(listed(notes, 'foot')).toEqual(['1']);
    notesNow.current = null;
  });

  it('follows what another editor writes into it', () => {
    const left = new Y.Doc();
    const right = new Y.Doc();
    connect(left, right);
    const mine = editor(left);
    const theirs = editor(right);
    write(mine.view, 'Uvod');
    run('insert.endnote', contextOf(mine.view, mine.view, left));
    const id = notesIn(mine.view.state)[0].id!;
    write(noteById(mine.view, id)!.inner, 'Izvor');
    const their = noteById(theirs.view, id)!;
    expect(their.inner.state.doc.textContent).toBe('Izvor');
    their.inner.dispatch(their.inner.state.tr.insertText(': HZN', 5));
    expect(noteById(mine.view, id)!.inner.state.doc.textContent).toBe('Izvor: HZN');
    expect(listed(theirs.notes, 'end')).toEqual(['iIzvor: HZN']);
  });
});

describe('notes on the clipboard', () => {
  const content = doc.create(null, [
    heading.create({ level: 1 }, [
      schema.text('Rok'),
      footnote.create({ kind: 'end' }, schema.text('Izvor')),
    ]),
    paragraph.create(null, [
      schema.text('Cijena'),
      footnote.create({ kind: 'foot' }, schema.text('Bez PDV-a', [schema.marks.strong.create()])),
      schema.text(' vrijedi.'),
    ]),
  ]);
  const slice = new Slice(content.content, 0, 0);

  it('copy as Word lays notes out and paste back as notes', () => {
    const html = document.createElement('div');
    html.append(
      clipboardSerializer(ACTIONS.lists).serializeFragment(slice.content, {
        document,
      }),
    );
    const reference = html.querySelector('a[style="mso-footnote-id:ftn1"]')!;
    expect(reference.getAttribute('href')).toBe('#_ftn1');
    expect(html.querySelector('#ftn1 p.MsoFootnoteText')!.textContent).toBe('1 Bez PDV-a');
    expect(html.querySelector('#edn1')!.textContent).toBe('i Izvor');

    const pasted = document.createElement('div');
    pasted.innerHTML = pastedHTML(html.innerHTML);
    const parsed = Parser.fromSchema(schema).parse(pasted);
    expect(parsed.toString()).toBe(
      'doc(heading("Rok", footnote("Izvor")), paragraph("Cijena", footnote(strong("Bez PDV-a")), " vrijedi."))',
    );
    expect(placed(parsed, { foot: 0, end: 0 }).map(({ kind }) => kind)).toEqual(['end', 'foot']);
  });

  it('copy as plain text with each note numbered after the text', () => {
    expect(clipboardText(ACTIONS.lists)(slice)).toBe(
      'Rok[i]\n\nCijena[1] vrijedi.\n\n[1] Bez PDV-a\n[i] Izvor',
    );
  });

  it('paste from Word and LibreOffice as notes where their marks are', () => {
    const word = `<p class=MsoNormal>Cijena<a style='mso-footnote-id:ftn1' href="#_ftn1" name="_ftnref1" title=""><span class=MsoFootnoteReference><span style='mso-special-character:footnote'><![if !supportFootnotes]><span class=MsoFootnoteReference>[1]</span><![endif]></span></span></a> vrijedi.</p>
<div style='mso-element:footnote-list'><![if !supportFootnotes]><br clear=all><hr align=left size=1 width="33%"><![endif]>
<div style='mso-element:footnote' id=ftn1>
<p class=MsoFootnoteText><a style='mso-footnote-id:ftn1' href="#_ftnref1" name="_ftn1" title=""><span class=MsoFootnoteReference><span style='mso-special-character:footnote'><![if !supportFootnotes]><span class=MsoFootnoteReference>[1]</span><![endif]></span></span></a> Bez <b>PDV-a</b>.</p>
</div></div>`;
    const office = `<p>Rok<a class="sdendnoteanc" name="sdendnote1anc" href="#sdendnote1sym"><sup>i</sup></a></p>
<div id="sdendnote1"><p class="sdendnote"><a class="sdendnotesym" name="sdendnote1sym" href="#sdendnote1anc">i</a>Izvor</p></div>`;
    const parse = (html: string) => {
      const pasted = document.createElement('div');
      pasted.innerHTML = pastedHTML(html);
      return Parser.fromSchema(schema).parse(pasted).toString();
    };
    expect(parse(word)).toBe(
      'doc(paragraph("Cijena", footnote("Bez ", strong("PDV-a"), "."), " vrijedi."))',
    );
    expect(parse(office)).toBe('doc(paragraph("Rok", footnote("Izvor")))');
  });
});
