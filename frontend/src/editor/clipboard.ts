import {
  DOMSerializer,
  type DOMOutputSpec,
  type Fragment,
  type Mark,
  type Node,
  type Slice,
} from 'prosemirror-model';
import type { EditorView } from 'prosemirror-view';
import { HIGHLIGHTS, swatchOf, TEXT_COLORS, type Palette } from './colors';
import { formatOf, type ListStore } from './forms';
import { flattenLists, listElements, markers, textMarker } from './lists';
import { noteNumber } from './notes';
import {
  imageSpec,
  imageUrl,
  listOf,
  noteKind,
  NOTES,
  schema,
  sizedSpan,
  type NoteKind,
} from './schema';
import { tableElement, tableText } from './tables';

export function clipboardReady(): boolean {
  return typeof navigator.clipboard?.write === 'function';
}

function onPaper(palette: Palette, tag: string, property: string, dataset: string) {
  return (mark: Mark): DOMOutputSpec => {
    const name: string = mark.attrs.color;
    return [
      tag,
      {
        [`data-${dataset}`]: name,
        style: `${property}: ${swatchOf(palette, name)!.light}`,
      },
      0,
    ];
  };
}

/** How Word writes a footnote or an endnote as HTML, on the clipboard and in its web pages. */
const WORD: Record<NoteKind, { id: string; style: string; element: string; text: string }> = {
  foot: {
    id: 'ftn',
    style: 'mso-footnote-id',
    element: 'footnote',
    text: 'MsoFootnoteText',
  },
  end: {
    id: 'edn',
    style: 'mso-endnote-id',
    element: 'endnote',
    text: 'MsoEndnoteText',
  },
};

function wordReference(document: Document, kind: NoteKind, count: number, back: boolean) {
  const { id, style } = WORD[kind];
  const reference = document.createElement('a');
  reference.setAttribute('style', `${style}:${id}${count}`);
  reference.setAttribute('href', back ? `#_${id}ref${count}` : `#_${id}${count}`);
  reference.setAttribute('name', back ? `_${id}${count}` : `_${id}ref${count}`);
  reference.appendChild(document.createElement('sup')).textContent = noteNumber(kind, count);
  return reference;
}

/** The notes of a copy as Word lays them out: a numbered mark in the text, the note itself in a
 * list after it, numbered from one in the copy as Word numbers them again anyway. */
function wordNotes(root: HTMLElement | DocumentFragment, document: Document): void {
  const counts: Record<NoteKind, number> = { foot: 0, end: 0 };
  const bodies: Record<NoteKind, HTMLElement[]> = { foot: [], end: [] };
  for (const note of root.querySelectorAll<HTMLElement>('span[data-note-copy]')) {
    const kind: NoteKind = note.dataset.noteCopy === 'end' ? 'end' : 'foot';
    const count = ++counts[kind];
    const { id, element, text } = WORD[kind];
    const body = document.createElement('div');
    body.setAttribute('style', `mso-element:${element}`);
    body.id = `${id}${count}`;
    const paragraph = body.appendChild(document.createElement('p'));
    paragraph.className = text;
    paragraph.append(wordReference(document, kind, count, true), ' ', ...note.childNodes);
    note.replaceWith(wordReference(document, kind, count, false));
    bodies[kind].push(body);
  }
  for (const kind of NOTES) {
    if (!bodies[kind].length) continue;
    const list = document.createElement('div');
    list.setAttribute('style', `mso-element:${WORD[kind].element}-list`);
    list.append(document.createElement('hr'), ...bodies[kind]);
    root.append(list);
  }
}

/** Other programs know neither the tables' Yjs grids, light-dark(), items marked by an attribute
 * nor notes inside the text, so the copy carries tables as rows of cells, the colours as they
 * print, lists as lists and notes as Word's. */
class PaperSerializer extends DOMSerializer {
  private depth = 0;

  constructor(
    nodes: ConstructorParameters<typeof DOMSerializer>[0],
    marks: ConstructorParameters<typeof DOMSerializer>[1],
    private lists: ListStore,
  ) {
    super(nodes, marks);
  }

  serializeFragment(
    fragment: Fragment,
    options: { document?: Document } = {},
    target?: HTMLElement | DocumentFragment,
  ): HTMLElement | DocumentFragment {
    this.depth += 1;
    let result: HTMLElement | DocumentFragment;
    try {
      result = this.laidOut(fragment, options, target);
    } finally {
      this.depth -= 1;
    }
    if (this.depth === 0) wordNotes(result, options.document ?? window.document);
    return result;
  }

  private laidOut(
    fragment: Fragment,
    options: { document?: Document },
    target?: HTMLElement | DocumentFragment,
  ): HTMLElement | DocumentFragment {
    let items = 0;
    fragment.forEach((node) => {
      if (node.type === schema.nodes.paragraph && listOf(node)) items += 1;
    });
    // A lone item is most often a part of one copied into some other text.
    if (!items || fragment.childCount === 1) {
      return super.serializeFragment(fragment, options, target);
    }
    const lists = listElements(
      fragment,
      (node) => this.serializeNode(node, options),
      (node, into) => super.serializeFragment(node.content, options, into),
      options.document ?? window.document,
      this.lists.get(),
    );
    if (!target) return lists;
    target.append(lists);
    return target;
  }
}

/** The number a block shows leads its text in a copy, marked so a paste back here drops it again. */
function withNumber(spec: DOMOutputSpec, number: string | null): DOMOutputSpec {
  if (!number) return spec;
  const { dom, contentDOM } = DOMSerializer.renderSpec(document, spec);
  const label = document.createElement('span');
  label.dataset.number = '';
  label.textContent = `${number} `;
  (contentDOM as HTMLElement).prepend(label);
  return { dom, contentDOM };
}

/** An item carries its list's format itself, for a paste into another document. */
function withFormat(spec: DOMOutputSpec, node: Node, lists: ListStore): DOMOutputSpec {
  const format = formatOf(lists.get(), node.attrs.format);
  if (!format || !Array.isArray(spec)) return spec;
  const [tag, attrs, ...rest] = spec;
  return [tag, { ...attrs, 'data-format': JSON.stringify(format) }, ...rest];
}

type NumberOf = (block: Node) => string | null;

const unnumbered: NumberOf = () => null;

export function clipboardSerializer(
  lists: ListStore,
  numberOf: NumberOf = unnumbered,
): DOMSerializer {
  const base = DOMSerializer.fromSchema(schema);
  const serializer: DOMSerializer = new PaperSerializer(
    {
      ...base.nodes,
      paragraph: (node) =>
        withNumber(withFormat(base.nodes.paragraph(node), node, lists), numberOf(node)),
      heading: (node) => withNumber(base.nodes.heading(node), numberOf(node)),
      title: (node) => withNumber(base.nodes.title(node), numberOf(node)),
      subtitle: (node) => withNumber(base.nodes.subtitle(node), numberOf(node)),
      table: (node) => tableElement(node, (cell) => serializer.serializeFragment(cell.content)),
      image: (node) => imageSpec(node, (blob) => new URL(imageUrl(blob), location.origin).href),
      footnote: (node) => ['span', { 'data-note-copy': noteKind(node) }, 0],
    },
    {
      ...base.marks,
      size: (mark) => sizedSpan(mark, false),
      color: onPaper(TEXT_COLORS, 'span', 'color', 'color'),
      highlight: onPaper(HIGHLIGHTS, 'mark', 'background-color', 'highlight'),
    },
    lists,
  );
  return serializer;
}

export function clipboardText(
  lists: ListStore,
  numberOf: NumberOf = unnumbered,
): (slice: Slice) => string {
  const leaf = (node: Node) =>
    node.type === schema.nodes.table ? tableText(node) : (node.type.spec.leafText?.(node) ?? '');
  return (slice) => {
    const found = markers(slice.content, lists.get());
    const whole = slice.content.childCount > 1 || slice.openStart === 0;
    const counts: Record<NoteKind, number> = { foot: 0, end: 0 };
    const notes: Record<NoteKind, string[]> = { foot: [], end: [] };
    const inline = (node: Node) => {
      let text = '';
      node.forEach((child) => {
        if (child.type !== schema.nodes.footnote) {
          text += child.isText ? child.text : leaf(child);
          return;
        }
        const kind = noteKind(child);
        const label = `[${noteNumber(kind, ++counts[kind])}]`;
        notes[kind].push(`${label} ${child.textContent}`);
        text += label;
      });
      return text;
    };
    let text = '';
    let item = false;
    slice.content.forEach((node, offset, index) => {
      const marker = whole ? textMarker(node, found.get(offset)) : '';
      if (index > 0) text += item && marker ? '\n' : '\n\n';
      const number = numberOf(node);
      const own = node.isLeaf || node.type === schema.nodes.table;
      text += marker + (number ? `${number} ` : '') + (own ? leaf(node) : inline(node));
      item = Boolean(marker);
    });
    const listed = [...notes.foot, ...notes.end];
    return listed.length ? `${text}\n\n${listed.join('\n')}` : text;
  };
}

/** A note from Word or LibreOffice where its mark was, as one run of text. */
function asNote(reference: Element, body: Element | null, kind: NoteKind): void {
  const note = reference.ownerDocument.createElement('span');
  note.dataset.note = kind;
  if (body) {
    for (const back of body.querySelectorAll('a[href^="#"]')) back.remove();
    const paragraphs = [...body.querySelectorAll('p')];
    (paragraphs.length ? paragraphs : [body]).forEach((paragraph, index) => {
      if (index > 0) note.append(' ');
      note.append(...paragraph.childNodes);
    });
    body.remove();
  }
  const first = note.firstChild;
  if (first instanceof Text) first.data = first.data.trimStart();
  reference.replaceWith(note);
}

function pastedNotes(body: HTMLElement): void {
  const document = body.ownerDocument;
  for (const kind of NOTES) {
    const { style, element } = WORD[kind];
    const references = [...body.querySelectorAll(`a[style*="${style}"]`)].filter(
      (reference) => !reference.closest(`[style*="mso-element:${element}"]`),
    );
    for (const reference of references) {
      const id = new RegExp(`${style}:\\s*([\\w-]+)`).exec(reference.getAttribute('style')!)?.[1];
      asNote(reference, id ? document.getElementById(id) : null, kind);
    }
    for (const list of body.querySelectorAll(`[style*="mso-element:${element}-list"]`)) {
      list.remove();
    }
    const office = kind === 'foot' ? 'sdfootnote' : 'sdendnote';
    for (const reference of body.querySelectorAll(`a.${office}anc`)) {
      const target = reference.getAttribute('href')?.replace(/^#/, '').replace(/sym$/, '');
      asNote(reference, target ? document.getElementById(target) : null, kind);
    }
  }
}

/** HTML from elsewhere as this editor keeps it: lists flat, notes in their place, numbers shown
 * rather than written. */
export function pastedHTML(html: string): string {
  const parsed = new DOMParser().parseFromString(html, 'text/html');
  for (const number of parsed.body.querySelectorAll('span[data-number]')) number.remove();
  pastedNotes(parsed.body);
  flattenLists(parsed.body);
  return parsed.body.innerHTML;
}

export async function copySelection(view: EditorView): Promise<void> {
  const { dom, text } = view.serializeForClipboard(view.state.selection.content());
  await navigator.clipboard.write([
    new ClipboardItem({
      'text/html': new Blob([dom.innerHTML], { type: 'text/html' }),
      'text/plain': new Blob([text], { type: 'text/plain' }),
    }),
  ]);
}

export async function cutSelection(view: EditorView): Promise<void> {
  await copySelection(view);
  view.dispatch(view.state.tr.deleteSelection().scrollIntoView().setMeta('uiEvent', 'cut'));
}

export async function pasteInto(view: EditorView, plain: boolean): Promise<void> {
  if (!plain) {
    for (const item of await navigator.clipboard.read()) {
      if (item.types.includes('text/html')) {
        view.pasteHTML(await (await item.getType('text/html')).text());
        return;
      }
    }
  }
  view.pasteText(await navigator.clipboard.readText());
}
