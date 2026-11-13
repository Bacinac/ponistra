import type { Node } from 'prosemirror-model';
import { Selection, type Command } from 'prosemirror-state';
import type { EditorView, NodeView } from 'prosemirror-view';
import type * as Y from 'yjs';
import type { MessageKey } from '../i18n/hr';
import { tabHref, type Heading } from '../tabs';
import type { Tab } from '../tree';
import { headingNumbers, startOf } from './numbering';
import { wordsOf } from './outline';
import { LEVELS, schema } from './schema';
import type { Styling } from './styling';
import { readingOrder, type LinesOf } from './tables';

const { contents, heading, paragraph } = schema.nodes;

/** A heading as its tab keeps it for the contents in other tabs. */
export interface Kept {
  id: string | null;
  level: number;
  text: string;
  style: string | null;
  restart: boolean;
}

/** Every heading of the tab, also one without words, which still takes a number. */
export function headingsOf(doc: Node, lines: LinesOf): Kept[] {
  const found: Kept[] = [];
  for (const { node } of readingOrder(doc, lines)) {
    if (node.type !== heading) continue;
    found.push({
      id: node.attrs.id,
      level: node.attrs.level,
      text: wordsOf(node),
      style: node.attrs.style,
      restart: node.attrs.restart === true,
    });
  }
  return found;
}

/** Each tab's headings, kept by the editors of each tab so the contents in the others list them
 * without loading it. */
export function keptHeadings(own: Y.Doc): Y.Map<Kept[]> {
  return own.getMap<Kept[]>('headings');
}

export function writeHeadings(own: Y.Doc, tab: string, headings: Kept[]): void {
  const known = keptHeadings(own).get(tab);
  if (known ? JSON.stringify(known) === JSON.stringify(headings) : !headings.length) return;
  own.transact(() => keptHeadings(own).set(tab, headings));
}

function isKept(value: unknown): value is Kept {
  if (typeof value !== 'object' || value === null) return false;
  const { id, level, text, style, restart } = value as Record<string, unknown>;
  return (
    (id === null || typeof id === 'string') &&
    LEVELS.some((each) => each === level) &&
    typeof text === 'string' &&
    (style === null || typeof style === 'string') &&
    typeof restart === 'boolean'
  );
}

/** A tab as the contents list it: its headings, each leading to its block. */
export interface Chapter {
  href: string;
  headings: Heading[];
}

/** Every tab in reading order: the open one with the headings its editor shows, the others with
 * those their editors kept, numbered on from the tabs before them. */
export function chaptersOf(
  own: Y.Doc,
  tabs: readonly Pick<Tab, 'id' | 'title'>[],
  open: { tab: string; headings: Heading[] },
  styling: Styling,
  home: string,
): Chapter[] {
  const ids = tabs.map(({ id }) => id);
  return tabs.map((tab) => {
    const href = tabHref(home, tab, tabs);
    if (tab.id === open.tab) return { href, headings: open.headings };
    const stored: unknown = keptHeadings(own).get(tab.id);
    const kept = Array.isArray(stored) ? stored.filter(isKept) : [];
    const numbers = headingNumbers(kept, styling, startOf(own, ids, tab.id));
    const headings = kept.flatMap(({ id, level, text }, at) =>
      id && text.trim() ? [{ id, level, number: numbers[at], text: text.trim() }] : [],
    );
    return { href, headings };
  });
}

/** The chapters every contents block of a view lists, and where following one of them leads. */
export function contentsStore(go: (href: string) => void) {
  let chapters: Chapter[] = [];
  let shown = '[]';
  const listeners = new Set<() => void>();
  return {
    go,
    get: () => chapters,
    set(next: Chapter[]) {
      const json = JSON.stringify(next);
      if (json === shown) return;
      chapters = next;
      shown = json;
      for (const listener of listeners) listener();
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export type ContentsStore = ReturnType<typeof contentsStore>;

/** The contents as the document's headings stand; a link in them is followed as any other: at
 * once where the text is read, with Ctrl where it is written. */
export class ContentsView implements NodeView {
  readonly dom = document.createElement('nav');
  private readonly unsubscribe: () => void;

  constructor(
    private node: Node,
    private readonly view: EditorView,
    private readonly store: ContentsStore,
    private readonly label: () => (key: MessageKey) => string,
  ) {
    this.dom.className = 'ponistra-contents';
    this.dom.contentEditable = 'false';
    this.dom.addEventListener('click', (event) => this.follow(event));
    this.unsubscribe = store.subscribe(() => this.render());
    this.render();
  }

  private follow(event: MouseEvent) {
    const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null;
    if (!anchor) return;
    event.preventDefault();
    if (this.view.editable && !event.ctrlKey && !event.metaKey) return;
    this.store.go(anchor.getAttribute('href')!);
  }

  private render() {
    const t = this.label();
    const depth: number = this.node.attrs.depth;
    const lines = this.store.get().flatMap(({ href, headings }) =>
      headings
        .filter(({ level }) => level <= depth)
        .map(({ id, level, number, text }) => ({
          level,
          number,
          text,
          href: `${href}?${new URLSearchParams({ block: id })}`,
        })),
    );
    this.dom.dataset.contents = String(depth);
    this.dom.setAttribute('aria-label', t('contents.label'));
    if (!lines.length) {
      const empty = document.createElement('p');
      empty.className = 'ponistra-contents-empty';
      empty.textContent = t('contents.empty');
      this.dom.replaceChildren(empty);
      return;
    }
    const top = Math.min(...lines.map(({ level }) => level));
    const list = document.createElement('ol');
    for (const { level, number, text, href } of lines) {
      const item = list.appendChild(document.createElement('li'));
      item.dataset.level = String(level);
      item.style.setProperty('--depth', String(level - top));
      const link = item.appendChild(document.createElement('a'));
      link.href = href;
      link.draggable = false;
      if (number) {
        const shown = link.appendChild(document.createElement('span'));
        shown.className = 'ponistra-contents-number';
        shown.textContent = number;
      }
      link.append(text);
    }
    this.dom.replaceChildren(list);
  }

  update(node: Node): boolean {
    if (node.type !== this.node.type) return false;
    this.node = node;
    this.render();
    return true;
  }

  // A link here is followed by the view's own handler, not the editor's for links in the text.
  stopEvent(event: Event): boolean {
    return event.type === 'click';
  }

  ignoreMutation(): boolean {
    return true;
  }

  destroy() {
    this.unsubscribe();
  }
}

/** Puts the contents in place of the selection and the cursor after them, in a paragraph of its
 * own where they end the tab. */
export const insertContents: Command = (state, dispatch) => {
  const index = state.selection.$from.index(0);
  if (!state.doc.canReplaceWith(index, index, contents)) return false;
  if (dispatch) {
    const node = contents.create();
    const tr = state.tr.replaceSelectionWith(node);
    if (!tr.doc.lastChild!.isTextblock) tr.insert(tr.doc.content.size, paragraph.create());
    let after = 0;
    tr.doc.forEach((child, offset) => {
      if (child === node) after = offset + child.nodeSize;
    });
    dispatch(tr.setSelection(Selection.near(tr.doc.resolve(after), 1)).scrollIntoView());
  }
  return true;
};
