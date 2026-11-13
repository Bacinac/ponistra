import { Fragment, Slice, type Node, type ResolvedPos } from 'prosemirror-model';
import {
  EditorState,
  NodeSelection,
  Plugin,
  PluginKey,
  TextSelection,
  type Command,
  type Transaction,
} from 'prosemirror-state';
import { StepMap } from 'prosemirror-transform';
import { Decoration, DecorationSet, EditorView, type NodeView } from 'prosemirror-view';
import * as Y from 'yjs';
import type { MessageKey } from '../i18n/hr';
import { shortId } from './blocks';
import { roman } from './numerals';
import { NOTES, noteKind, schema, type NoteKind } from './schema';
import { INNER } from './suggesting';

const { footnote } = schema.nodes;

export type Counts = Record<NoteKind, number>;
export const NO_NOTES: Counts = { foot: 0, end: 0 };

const FROM_OUTSIDE = 'fromOutside';
const SHOWN_MS = 4000;

/** 1, 2, 3 for footnotes; i, ii, iii for endnotes. */
export function noteNumber(kind: NoteKind, count: number): string {
  return kind === 'foot' ? String(count) : roman(count);
}

export interface Placed {
  id: string | null;
  kind: NoteKind;
  pos: number;
  label: string;
}

/** Every note in the order it is read, numbered on from the tabs before. */
export function placed(doc: Node, offset: Counts): Placed[] {
  const counts = { ...offset };
  const found: Placed[] = [];
  doc.descendants((node, pos) => {
    if (node.type !== footnote) return !node.isAtom;
    const kind = noteKind(node);
    counts[kind] += 1;
    found.push({ id: node.attrs.id, kind, pos, label: noteNumber(kind, counts[kind]) });
    return false;
  });
  return found;
}

export function countsOf(notes: readonly Placed[]): Counts {
  const counts = { ...NO_NOTES };
  for (const note of notes) counts[note.kind] += 1;
  return counts;
}

interface Numbering {
  offset: Counts;
  notes: Placed[];
  decorations: DecorationSet;
}

interface NotesSpec {
  list: NoteList | null;
  /** The plugins of each note's own editor. */
  inner: Plugin[];
}

const key = new PluginKey<Numbering>('notes');

function numbered(doc: Node, offset: Counts): Numbering {
  const notes = placed(doc, offset);
  const decorations = DecorationSet.create(
    doc,
    notes.map(({ pos, label }) =>
      Decoration.node(pos, pos + doc.nodeAt(pos)!.nodeSize, { 'data-marker': label }),
    ),
  );
  return { offset, notes, decorations };
}

export function notesPlugin(spec: NotesSpec & { offset: Counts }): Plugin<Numbering> {
  const { list, inner, offset } = spec;
  return new Plugin<Numbering>({
    key,
    list,
    inner,
    state: {
      init: (_, state) => numbered(state.doc, offset),
      apply: (tr, before) => {
        const next: Counts | undefined = tr.getMeta(key);
        if (next) return numbered(tr.doc, next);
        return tr.docChanged ? numbered(tr.doc, before.offset) : before;
      },
    },
    props: {
      decorations: (state) => key.getState(state)!.decorations,
    },
    view: (view) => {
      list?.arrange(view);
      return { update: (view) => list?.arrange(view), destroy: () => list?.destroy() };
    },
  });
}

export function notesIn(state: EditorState): Placed[] {
  return key.getState(state)?.notes ?? [];
}

function specOf(state: EditorState): NotesSpec | null {
  const plugin = key.get(state);
  return plugin ? (plugin.spec as unknown as NotesSpec) : null;
}

function same(left: Counts, right: Counts): boolean {
  return NOTES.every((kind) => left[kind] === right[kind]);
}

/** Numbers the tab's notes on from the given counts of the tabs before it. */
export function numberFrom(view: EditorView, offset: Counts): void {
  const numbering = key.getState(view.state);
  if (numbering && !same(numbering.offset, offset)) {
    view.dispatch(view.state.tr.setMeta(key, offset).setMeta('addToHistory', false));
  }
}

const owners = new WeakMap<EditorView, NoteView>();
const markers = new WeakMap<Element, NoteView>();

/** The note whose own editor this is. */
export function noteOf(view: EditorView): NoteView | null {
  return owners.get(view) ?? null;
}

/** A pasted or dropped slice as the plain run of text a note holds. */
function inline(slice: Slice): Slice {
  const parts: Node[] = [];
  let blocks = 0;
  slice.content.descendants((node) => {
    if (node.type === footnote) return false;
    if (node.isTextblock && blocks++ > 0) parts.push(schema.text(' '));
    if (node.isText) parts.push(node);
    return true;
  });
  return parts.length ? new Slice(Fragment.from(parts), 0, 0) : Slice.empty;
}

/** The mark in the text and, in the list under it, the note itself in an editor of its own whose
 * changes are steps of the document's, so collaboration and undo know no difference. */
export class NoteView implements NodeView {
  readonly dom = document.createElement('sup');
  readonly item = document.createElement('li');
  readonly inner: EditorView;
  private number = document.createElement('button');

  constructor(
    private node: Node,
    readonly outer: EditorView,
    private getPos: () => number | undefined,
  ) {
    const { list, inner } = specOf(outer.state)!;
    this.dom.className = 'ponistra-note';
    this.dom.dataset.note = noteKind(node);
    this.dom.contentEditable = 'false';
    this.dom.addEventListener('mousedown', (event) => {
      event.preventDefault();
      const pos = this.getPos();
      if (pos !== undefined)
        outer.dispatch(outer.state.tr.setSelection(NodeSelection.create(outer.state.doc, pos)));
      this.open();
    });
    this.number.type = 'button';
    this.number.className = 'ponistra-note-number';
    this.number.addEventListener('click', () => this.back());
    const body = document.createElement('div');
    this.item.append(this.number, body);
    this.inner = new EditorView(body, {
      state: EditorState.create({ doc: node, plugins: inner }),
      editable: () => outer.editable,
      attributes: (state) => ({
        class: state.doc.content.size ? 'ponistra-note-text' : 'ponistra-note-text ponistra-empty',
        role: 'textbox',
      }),
      transformPasted: inline,
      dispatchTransaction: (tr) => this.dispatchInner(tr),
      handleDOMEvents: {
        focus: (view) => {
          list?.focused(view);
          return false;
        },
      },
    });
    owners.set(this.inner, this);
    markers.set(this.dom, this);
    list?.add(this);
  }

  get id(): string | null {
    return this.node.attrs.id;
  }

  get kind(): NoteKind {
    return noteKind(this.node);
  }

  numbered(label: string, name: string): void {
    this.number.textContent = label;
    this.number.setAttribute('aria-label', name);
    this.inner.dom.setAttribute('aria-label', name);
  }

  private dispatchInner(tr: Transaction): void {
    const { state, transactions } = this.inner.state.applyTransaction(tr);
    this.inner.updateState(state);
    const pos = this.getPos();
    if (!tr.getMeta(FROM_OUTSIDE) && pos !== undefined) {
      const outer = this.outer.state.tr.setMeta(INNER, true);
      const offset = StepMap.offset(pos + 1);
      for (const step of transactions.flatMap((transaction) => transaction.steps)) {
        const mapped = step.map(offset);
        if (mapped) outer.step(mapped);
      }
      if (outer.docChanged) this.outer.dispatch(outer);
    }
    specOf(this.outer.state)?.list?.changed(this.inner);
  }

  update(node: Node): boolean {
    if (node.type !== this.node.type) return false;
    this.node = node;
    this.dom.dataset.note = noteKind(node);
    this.inner.setProps({});
    const { state } = this.inner;
    const start = node.content.findDiffStart(state.doc.content);
    if (start !== null) {
      let { a: endA, b: endB } = node.content.findDiffEnd(state.doc.content)!;
      const overlap = start - Math.min(endA, endB);
      if (overlap > 0) {
        endA += overlap;
        endB += overlap;
      }
      this.inner.dispatch(
        state.tr.replace(start, endB, node.slice(start, endA)).setMeta(FROM_OUTSIDE, true),
      );
    }
    return true;
  }

  selectNode(): void {
    this.dom.classList.add('ProseMirror-selectednode');
  }

  deselectNode(): void {
    this.dom.classList.remove('ProseMirror-selectednode');
  }

  stopEvent(): boolean {
    return true;
  }

  ignoreMutation(): boolean {
    return true;
  }

  destroy(): void {
    specOf(this.outer.state)?.list?.remove(this);
    this.inner.destroy();
    this.item.remove();
  }

  /** Into the note, at its end. */
  open(): void {
    this.item.scrollIntoView({ block: 'nearest' });
    this.inner.focus();
    const { state } = this.inner;
    this.inner.dispatch(state.tr.setSelection(TextSelection.atEnd(state.doc)));
  }

  /** Back to the text, right after the note's mark, past the spaces if only they follow it. */
  back(): void {
    const pos = this.getPos();
    if (pos === undefined) return;
    const { outer } = this;
    const { doc } = outer.state;
    const after = TextSelection.create(
      doc,
      pastEndingSpaces(doc.resolve(pos + this.node.nodeSize)),
    );
    outer.dispatch(outer.state.tr.setSelection(after).scrollIntoView());
    outer.focus();
  }

  setKind(kind: NoteKind): void {
    const pos = this.getPos();
    if (pos === undefined) return;
    this.outer.dispatch(this.outer.state.tr.setNodeAttribute(pos, 'kind', kind));
    this.inner.focus();
  }

  remove(): void {
    const pos = this.getPos();
    if (pos === undefined) return;
    const { outer } = this;
    const tr = outer.state.tr.delete(pos, pos + this.node.nodeSize);
    outer.dispatch(tr.setSelection(TextSelection.create(tr.doc, pos)).scrollIntoView());
    outer.focus();
  }

  flash(): void {
    this.item.classList.add('ponistra-found');
    this.item.scrollIntoView({ block: 'center' });
    setTimeout(() => this.item.classList.remove('ponistra-found'), SHOWN_MS);
  }
}

export interface NoteHost {
  label: () => (key: MessageKey) => string;
  /** A note's editor took the focus or changed its state. */
  onNote: (view: EditorView) => void;
}

/** The tab's notes under its text, footnotes first, each list in the order the text reads. */
export class NoteList {
  private views = new Set<NoteView>();
  private sections = Object.fromEntries(
    NOTES.map((kind) => {
      const section = document.createElement('section');
      section.className = 'ponistra-notes';
      section.dataset.notes = kind;
      section.hidden = true;
      const list = section.appendChild(document.createElement('ol'));
      return [kind, { section, list }];
    }),
  ) as Record<NoteKind, { section: HTMLElement; list: HTMLOListElement }>;

  constructor(
    root: HTMLElement,
    private host: NoteHost,
  ) {
    root.append(...NOTES.map((kind) => this.sections[kind].section));
  }

  add(view: NoteView): void {
    this.views.add(view);
  }

  remove(view: NoteView): void {
    this.views.delete(view);
  }

  focused(view: EditorView): void {
    this.host.onNote(view);
  }

  changed(view: EditorView): void {
    this.host.onNote(view);
  }

  find(id: string): NoteView | null {
    return [...this.views].find((view) => view.id === id) ?? null;
  }

  section(kind: NoteKind): HTMLElement {
    return this.sections[kind].section;
  }

  // An item is moved only when it is out of place: moving the one being edited would blur it.
  arrange(view: EditorView): void {
    const t = this.host.label();
    const notes = notesIn(view.state);
    for (const kind of NOTES) {
      const { section, list } = this.sections[kind];
      section.setAttribute('aria-label', t(`notes.${kind}`));
      const wanted: NoteView[] = [];
      for (const note of notes) {
        const shown = note.kind === kind ? markers.get(view.nodeDOM(note.pos) as Element) : null;
        if (!shown) continue;
        shown.numbered(note.label, `${t(`note.${kind}`)} ${note.label}`);
        wanted.push(shown);
      }
      wanted.forEach((note, index) => {
        const there = list.children[index] ?? null;
        if (there !== note.item) list.insertBefore(note.item, there);
      });
      for (const stale of [...list.children].slice(wanted.length)) stale.remove();
      section.hidden = wanted.length === 0;
    }
  }

  destroy(): void {
    for (const { section } of Object.values(this.sections)) section.remove();
  }
}

/** A note as the tab shows it: its mark in the text and its item in the list. */
export interface ShownNote {
  pos: number;
  mark: HTMLElement;
  item: HTMLElement;
}

/** The tab's notes of a kind in the order they are read, and the section listing them. */
export function shownNotes(
  view: EditorView,
  kind: NoteKind,
): { section: HTMLElement | null; notes: ShownNote[] } {
  const notes: ShownNote[] = [];
  for (const note of notesIn(view.state)) {
    const shown = note.kind === kind ? markers.get(view.nodeDOM(note.pos) as Element) : null;
    if (shown) notes.push({ pos: note.pos, mark: shown.dom, item: shown.item });
  }
  return { section: specOf(view.state)?.list?.section(kind) ?? null, notes };
}

export function noteById(view: EditorView, id: string): NoteView | null {
  return specOf(view.state)?.list?.find(id) ?? null;
}

/** Shows the note with this id, the hit of a search; false while the tab has no such note. */
export function showNote(view: EditorView, id: string): boolean {
  const note = noteById(view, id);
  note?.flash();
  return Boolean(note);
}

function canInsertNote(state: EditorState): boolean {
  const { $to } = state.selection;
  return $to.parent.inlineContent && $to.parent.canReplaceWith($to.index(), $to.index(), footnote);
}

function pastEndingSpaces($pos: ResolvedPos): number {
  const { parent } = $pos;
  for (let index = $pos.index(); index < parent.childCount; index++) {
    const child = parent.child(index);
    if (!child.isText || child.text!.trim()) return $pos.pos;
  }
  return $pos.end();
}

/** Where a mark inserted at `to` goes: on what stands before the spaces typed ahead of it. */
function markAt(doc: Node, to: number): number {
  let at = to;
  for (
    let before = doc.resolve(at).nodeBefore;
    before?.isText;
    before = doc.resolve(at).nodeBefore
  ) {
    const text = before.text!.trimEnd();
    at -= before.text!.length - text.length;
    if (text) return at;
  }
  return doc.resolve(at).nodeBefore?.type === footnote ? at : to;
}

/** A new note right after the selection, the cursor in it. */
export function insertNote(kind: NoteKind): Command {
  return (state, dispatch, view) => {
    if (!canInsertNote(state)) return false;
    if (dispatch) {
      const id = shortId();
      const at = markAt(state.doc, state.selection.to);
      const tr = state.tr.insert(at, footnote.create({ id, kind }));
      dispatch(tr.setSelection(NodeSelection.create(tr.doc, at)).scrollIntoView());
      if (view) noteById(view, id)?.open();
    }
    return true;
  };
}

/** Into the note whose mark the text has selected. A mark stays selected while its note is
 * written, so the focus a menu gives back after its command lands in the note, not the text. */
export function openSelected(view: EditorView): boolean {
  const { selection } = view.state;
  if (!(selection instanceof NodeSelection) || selection.node.type !== footnote) return false;
  const note = noteById(view, selection.node.attrs.id);
  note?.open();
  return Boolean(note);
}

/** How many notes of each kind every tab has, kept by the editors of each tab so the tabs after
 * it number on without loading it. */
export function noteCounts(own: Y.Doc): Y.Map<Counts> {
  return own.getMap<Counts>('notes');
}

/** Each tab's own settings. */
export function tabSettings(own: Y.Doc): Y.Map<Y.Map<unknown>> {
  return own.getMap<Y.Map<unknown>>('tabs');
}

const RESTART = 'notesRestart';

export function restarts(own: Y.Doc, tab: string): boolean {
  return tabSettings(own).get(tab)?.get(RESTART) === true;
}

export function setRestart(own: Y.Doc, tab: string, restart: boolean): void {
  own.transact(() => {
    const settings = tabSettings(own);
    let mine = settings.get(tab);
    if (!mine) {
      mine = new Y.Map();
      settings.set(tab, mine);
    }
    if (restart) mine.set(RESTART, true);
    else mine.delete(RESTART);
  });
}

export function writeCounts(own: Y.Doc, tab: string, counts: Counts): void {
  const known = noteCounts(own).get(tab);
  if (known && same(known, counts)) return;
  if (!known && same(counts, NO_NOTES)) return;
  own.transact(() => noteCounts(own).set(tab, counts));
}

/** Where the tab's numbers start: after the notes of the tabs before it, back to the nearest
 * one that starts again. */
export function offsetOf(own: Y.Doc, tabs: readonly string[], tab: string): Counts {
  let running = { ...NO_NOTES };
  for (const id of tabs) {
    if (restarts(own, id)) running = { ...NO_NOTES };
    if (id === tab) break;
    const counts = noteCounts(own).get(id);
    for (const kind of NOTES) running[kind] += counts?.[kind] ?? 0;
  }
  return running;
}

/** The tab's numbering as the commands see it. */
export interface TabNotes {
  offset: Counts;
  restart: boolean;
  first: boolean;
  setRestart: (restart: boolean) => void;
}

export function tabNotesOf(own: Y.Doc, tabs: readonly string[], tab: string): TabNotes {
  return {
    offset: offsetOf(own, tabs, tab),
    restart: restarts(own, tab),
    first: tabs[0] === tab,
    setRestart: (restart) => setRestart(own, tab, restart),
  };
}
