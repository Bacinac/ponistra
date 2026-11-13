import { splitBlockAs } from 'prosemirror-commands';
import { InputRule } from 'prosemirror-inputrules';
import { Fragment, Slice, type Node } from 'prosemirror-model';
import { Plugin, PluginKey, type Command, type EditorState } from 'prosemirror-state';
import { Decoration, DecorationSet } from 'prosemirror-view';
import { indent, textblocks } from './blocks';
import {
  formatFrom,
  formatOf,
  isStandard,
  kindOfLevel,
  LIST_LEVELS,
  levelIn,
  reformed,
  standard,
  type ListFormat,
  type ListFormats,
  type ListLevel,
  type ListStore,
  type Marked,
} from './forms';
import { numeral } from './numerals';
import { INDENT_MAX, INDENT_STEP, levelOf, listOf, schema, type ListKind } from './schema';
import { AFFIX_MAX, type Numbering } from './styling';

const { paragraph } = schema.nodes;
export const CHECKED = '☑';
export const UNCHECKED = '☐';

type Counts = ({ kind: ListKind; count: number } | undefined)[];

function numberShown(
  form: ListLevel,
  format: ListFormat | undefined,
  counts: Counts,
  level: number,
): string {
  const numerals: string[] = [];
  for (let above = 0; form.nested && above < level; above++) {
    const at = counts[above];
    if (at?.kind === 'number') {
      numerals.push(numeral(at.count, levelIn(format, 'number', above).numbering));
    }
  }
  numerals.push(numeral(counts[level]!.count, form.numbering));
  return `${form.prefix}${numerals.join('.')}${form.suffix}`;
}

/** The marker each item shows, by its offset in the content, in its list's format. A number
 * counts on within a run of items, at its level and of its kind; any other block ends the run,
 * except for an item that continues its list. */
export function markers(content: Fragment, formats: ListFormats = new Map()): Map<number, string> {
  const found = new Map<number, string>();
  let counts: Counts = [];
  const last: Partial<Record<ListKind, Counts>> = {};
  content.forEach((node, offset) => {
    const kind = node.type === paragraph ? listOf(node) : null;
    if (!kind) {
      counts = [];
      return;
    }
    const level = levelOf(node);
    const continued = node.attrs.continued === true && !node.attrs.restart;
    counts = (continued ? (last[kind] ?? []) : counts).slice(0, level + 1);
    const before = counts[level];
    const count = before?.kind === kind && !node.attrs.restart ? before.count + 1 : 1;
    counts[level] = { kind, count };
    last[kind] = counts;
    if (kind === 'check') return;
    const format = formatOf(formats, node.attrs.format);
    const form = levelIn(format, kind, level);
    found.set(offset, kind === 'number' ? numberShown(form, format, counts, level) : form.prefix);
  });
  return found;
}

/** Whether the number item at the offset, continuing its list, would count on from an item
 * before it rather than start from 1. */
export function continuable(content: Fragment, offset: number): boolean {
  let index = -1;
  content.forEach((_, at, i) => {
    if (at === offset) index = i;
  });
  const node = content.child(index);
  if (listOf(node) !== 'number' || node.attrs.continued === true) return false;
  const marked = (continued: boolean) => {
    const attrs = { ...node.attrs, restart: false, continued };
    const item = node.type.create(attrs, node.content, node.marks);
    return markers(content.replaceChild(index, item)).get(offset);
  };
  return marked(true) !== marked(false);
}

function decorated(doc: Node, formats: ListFormats): DecorationSet {
  const decorations = [...markers(doc.content, formats)].map(([pos, marker]) =>
    Decoration.node(pos, pos + doc.nodeAt(pos)!.nodeSize, { 'data-marker': marker }),
  );
  return DecorationSet.create(doc, decorations);
}

/** The format a pasted item names, as this document keeps it: one of its own, or one a copy
 * brought along, kept here. */
function pastedFormat(value: unknown, lists: ListStore): string | null {
  if (typeof value !== 'string') return null;
  if (lists.get().has(value)) return value;
  let brought: unknown;
  try {
    brought = JSON.parse(value);
  } catch {
    return null;
  }
  const format = formatFrom(brought);
  return format && lists.keep(format);
}

function withFormats(fragment: Fragment, lists: ListStore): Fragment {
  const nodes: Node[] = [];
  fragment.forEach((node) => {
    if (node.type === paragraph && node.attrs.format !== null) {
      const format = listOf(node) === 'check' ? null : pastedFormat(node.attrs.format, lists);
      nodes.push(node.type.create({ ...node.attrs, format }, node.content, node.marks));
    } else {
      nodes.push(node.isLeaf ? node : node.copy(withFormats(node.content, lists)));
    }
  });
  return Fragment.from(nodes);
}

const markersKey = new PluginKey<DecorationSet>('listMarkers');

/** Shows each item's marker, again whenever the document's list formats change; a pasted item
 * keeps its list's format. */
export function listMarkers(lists: ListStore): Plugin {
  return new Plugin<DecorationSet>({
    key: markersKey,
    state: {
      init: (_, state) => decorated(state.doc, lists.get()),
      apply: (tr, before) =>
        tr.docChanged || tr.getMeta(markersKey) ? decorated(tr.doc, lists.get()) : before,
    },
    view: (view) => ({
      destroy: lists.subscribe(() => {
        if (!view.isDestroyed) {
          view.dispatch(view.state.tr.setMeta(markersKey, true).setMeta('addToHistory', false));
        }
      }),
    }),
    props: {
      decorations(state) {
        return this.getState(state);
      },
      transformPasted: (slice) =>
        new Slice(withFormats(slice.content, lists), slice.openStart, slice.openEnd),
    },
  });
}

/** A click on a check item's box ticks it. */
export function checkBoxes(): Plugin {
  return new Plugin({
    props: {
      handleDOMEvents: {
        mousedown(view, event) {
          const item = event.target;
          if (!view.editable || !(item instanceof HTMLElement) || item.dataset.list !== 'check') {
            return false;
          }
          const box = item.getBoundingClientRect();
          if (event.clientX > box.left + parseFloat(getComputedStyle(item).paddingLeft)) {
            return false;
          }
          const pos = view.posAtDOM(item, 0) - 1;
          const node = view.state.doc.nodeAt(pos);
          if (node?.type !== paragraph) return false;
          view.dispatch(view.state.tr.setNodeAttribute(pos, 'checked', !node.attrs.checked));
          event.preventDefault();
          return true;
        },
      },
    },
  });
}

function paragraphs(state: EditorState): { node: Node; pos: number }[] {
  return textblocks(state).filter(({ node }) => node.type === paragraph);
}

export function inList(state: EditorState, kind?: ListKind): boolean {
  const { parent } = state.selection.$from;
  const found = parent.type === paragraph ? listOf(parent) : null;
  return kind ? found === kind : found !== null;
}

/** The format of the item of the kind right before the blocks from `from` to `to`, or else right
 * after them, whose list they join. */
function joinedFormat(doc: Node, from: number, to: number, kind: ListKind): string | null {
  if (kind === 'check') return null;
  for (const next of [doc.resolve(from).nodeBefore, doc.resolve(to).nodeAfter]) {
    if (next?.type === paragraph && listOf(next) === kind) return next.attrs.format;
  }
  return null;
}

/** Makes the selected paragraphs items of the list, or plain paragraphs once all of them are. */
export function toggleList(kind: ListKind): Command {
  return (state, dispatch) => {
    const items = paragraphs(state);
    if (!items.length) return false;
    const off = items.every(({ node }) => listOf(node) === kind);
    if (dispatch) {
      const tr = state.tr;
      const last = items.at(-1)!;
      const format = joinedFormat(state.doc, items[0].pos, last.pos + last.node.nodeSize, kind);
      for (const { pos, node } of items) {
        tr.setNodeAttribute(pos, 'list', off ? null : kind);
        if (off || listOf(node) !== kind) {
          tr.setNodeAttribute(pos, 'checked', false)
            .setNodeAttribute(pos, 'restart', false)
            .setNodeAttribute(pos, 'continued', false)
            .setNodeAttribute(pos, 'format', off ? null : format)
            .setNodeAttribute(pos, 'firstLine', null);
        }
      }
      dispatch(tr.scrollIntoView());
    }
    return true;
  };
}

function unlisted(state: EditorState, pos: number) {
  return state.tr
    .setNodeAttribute(pos, 'list', null)
    .setNodeAttribute(pos, 'checked', false)
    .setNodeAttribute(pos, 'restart', false)
    .setNodeAttribute(pos, 'continued', false)
    .setNodeAttribute(pos, 'format', null);
}

/** The format of the last number item before `pos`, the list an item there continues. */
export function continuedFormat(doc: Node, pos: number): string | null {
  let format: string | null = null;
  doc.forEach((node, offset) => {
    if (offset < pos && node.type === paragraph && listOf(node) === 'number') {
      format = node.attrs.format;
    }
  });
  return format;
}

/** The item at the cursor, where it is one of the kind. */
function itemAt(state: EditorState, kind: Marked): { node: Node; pos: number } | null {
  const { $from } = state.selection;
  if ($from.depth < 1) return null;
  const node = $from.node(1);
  return node.type === paragraph && listOf(node) === kind ? { node, pos: $from.before(1) } : null;
}

/** The item at the cursor, where it is a bullet or a number. */
export function listAt(state: EditorState): { node: Node; pos: number } | null {
  return itemAt(state, 'number') ?? itemAt(state, 'bullet');
}

/** The form the item at the cursor shows its level in. */
export function formAt(state: EditorState, formats: ListFormats, kind: Marked): ListLevel | null {
  const at = itemAt(state, kind);
  return at && levelIn(formatOf(formats, at.node.attrs.format), kind, levelOf(at.node));
}

/** The items of the list the item at `pos` is in: those of its format in its run of items, and in
 * the runs its numbers continue from and into. */
function listItems(doc: Node, pos: number): number[] {
  const runs: { node: Node; pos: number }[][] = [];
  let run: { node: Node; pos: number }[] = [];
  doc.forEach((node, offset) => {
    if (node.type === paragraph && listOf(node)) {
      run.push({ node, pos: offset });
    } else if (run.length) {
      runs.push(run);
      run = [];
    }
  });
  if (run.length) runs.push(run);
  const continues = (items: { node: Node }[]) =>
    items.some(({ node }) => node.attrs.continued === true && !node.attrs.restart);
  let first = runs.findIndex((items) => items.some((item) => item.pos === pos));
  let last = first;
  while (first > 0 && continues(runs[first])) first -= 1;
  while (last + 1 < runs.length && continues(runs[last + 1])) last += 1;
  const format = doc.nodeAt(pos)!.attrs.format;
  return runs
    .slice(first, last + 1)
    .flat()
    .filter(({ node }) => listOf(node) !== 'check' && node.attrs.format === format)
    .map((item) => item.pos);
}

/** The list's items in the format; where the format is given whole, each item takes the kind its
 * level has in it. */
function formatted(state: EditorState, pos: number, id: string | null, format?: ListFormat) {
  const tr = state.tr;
  for (const at of listItems(state.doc, pos)) {
    const node = state.doc.nodeAt(at)!;
    tr.setNodeAttribute(at, 'format', id);
    const kind = format && kindOfLevel(format[levelOf(node)]);
    if (kind && listOf(node) !== kind) tr.setNodeAttribute(at, 'list', kind);
  }
  return tr;
}

/** Shows the level of the item at the cursor in the form, throughout its list. */
export function reform(lists: ListStore, form: ListLevel): Command {
  return (state, dispatch) => {
    const at = itemAt(state, kindOfLevel(form));
    const level = at ? levelOf(at.node) : 0;
    if (!at || (form.nested && level === 0)) return false;
    if (dispatch) {
      const id = lists.keep(reformed(formatOf(lists.get(), at.node.attrs.format), level, form));
      dispatch(formatted(state, at.pos, id));
    }
    return true;
  };
}

/** Each level of the list at the cursor as it shows: in the kind of its first item, or as the
 * list's format has it where no item is at that level. */
export function levelsAt(state: EditorState, formats: ListFormats): ListLevel[] | null {
  const at = listAt(state);
  if (!at) return null;
  const format = formatOf(formats, at.node.attrs.format);
  const kinds: (Marked | undefined)[] = [];
  for (const pos of listItems(state.doc, at.pos)) {
    const node = state.doc.nodeAt(pos)!;
    kinds[levelOf(node)] ??= listOf(node) as Marked;
  }
  const own = listOf(at.node) as Marked;
  return Array.from({ length: LIST_LEVELS }, (_, level) => {
    const kind = kinds[level];
    return kind ? levelIn(format, kind, level) : (format?.[level] ?? standard(own, level));
  });
}

/** Gives the list at the cursor the format at every level. */
export function formatList(lists: ListStore, format: ListFormat): Command {
  return (state, dispatch) => {
    const at = listAt(state);
    if (!at || format[0].nested) return false;
    if (dispatch) dispatch(formatted(state, at.pos, lists.keep(format), format));
    return true;
  };
}

function emptyItem(state: EditorState): boolean {
  const { $from, empty } = state.selection;
  return empty && inList(state) && $from.parent.content.size === 0;
}

const continueItem = splitBlockAs((node) => ({
  type: paragraph,
  attrs: { ...node.attrs, id: null, checked: false, restart: false, continued: false },
}));

/** Enter: on an empty item one level out, or out of the list from the first level; elsewhere in
 * an item, the next item. */
const enter: Command = (state, dispatch, view) => {
  if (!inList(state)) return false;
  if (!emptyItem(state)) return continueItem(state, dispatch, view);
  if (levelOf(state.selection.$from.parent) > 0) return indent(-1)(state, dispatch);
  dispatch?.(unlisted(state, state.selection.$from.before()));
  return true;
};

/** Backspace at the start of an item leaves the text where it is, without its marker. */
const unmark: Command = (state, dispatch) => {
  const { $from, empty } = state.selection;
  if (!empty || $from.parentOffset > 0 || !inList(state)) return false;
  dispatch?.(unlisted(state, $from.before()));
  return true;
};

function level(step: 1 | -1): Command {
  return (state, dispatch) => {
    if (!inList(state)) return false;
    indent(step)(state, dispatch);
    return true;
  };
}

export const listKeys: Record<string, Command> = {
  Enter: enter,
  Backspace: unmark,
  Tab: level(1),
  'Shift-Tab': level(-1),
};

function listRule(pattern: RegExp, kind: ListKind, checked = (_: RegExpMatchArray) => false) {
  return new InputRule(pattern, (state, match, start, end) => {
    const $start = state.doc.resolve(start);
    if ($start.depth !== 1 || $start.parent.type !== paragraph || inList(state)) return null;
    const pos = $start.before();
    const format = joinedFormat(state.doc, pos, $start.after(), kind);
    return state.tr
      .delete(start, end)
      .setNodeAttribute(pos, 'list', kind)
      .setNodeAttribute(pos, 'checked', checked(match))
      .setNodeAttribute(pos, 'format', format);
  });
}

export const listRules = [
  listRule(/^[-*•]\s$/, 'bullet'),
  listRule(/^\d+[.)]\s$/, 'number'),
  listRule(/^\[([ xX]?)\]\s$/, 'check', (match) => match[1].toLowerCase() === 'x'),
];

const BLOCKS = new Set(['P', 'DIV', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE']);
const NUMBERED = /^(?:\d+|[a-z]{1,3}|[ivxlc]+)[.)]$/i;

function item(
  from: HTMLElement,
  kind: ListKind,
  level: number,
  checked: boolean,
): HTMLParagraphElement {
  const item = from.ownerDocument.createElement('p');
  item.dataset.list = kind;
  if (level > 0) item.dataset.indent = String(level * INDENT_STEP);
  if (checked) item.dataset.checked = 'true';
  if (from.dataset.style) item.dataset.style = from.dataset.style;
  if (from.dataset.format) item.dataset.format = from.dataset.format;
  if (from.style.textAlign) item.style.textAlign = from.style.textAlign;
  return item;
}

const bullet = (symbol: string): ListLevel => ({
  numbering: '',
  prefix: symbol,
  suffix: '',
  nested: false,
});
const plainNumber = (numbering: Numbering): ListLevel => ({
  numbering,
  prefix: '',
  suffix: '.',
  nested: false,
});

/** The bullets Word draws from a symbol font's letters (backend imports/word.py). */
const SYMBOLS: Record<string, Record<string, string>> = {
  symbol: { '·': '•', '-': '–' },
  wingdings: { '§': '▪', Ø: '➢', ü: '✓', v: '❖', q: '❑', n: '■', l: '●' },
  'courier new': { o: '◦' },
};
const SYMBOL_FONTS = new Set(['symbol', 'wingdings', 'wingdings 2', 'wingdings 3', 'webdings']);
const MARKER = /^([^\p{L}\p{N}]*)((?:[\p{L}\p{N}]+\.)*)([\p{L}\p{N}]+)([^\p{L}\p{N}]*)$/u;

function numberingOf(numeral: string): Numbering | null {
  if (/^\d+$/.test(numeral)) return '1';
  if (/^(?:i|[ivxlcdm]{2,})$/.test(numeral)) return 'i';
  if (/^(?:I|[IVXLCDM]{2,})$/.test(numeral)) return 'I';
  if (/^[a-z]+$/.test(numeral)) return 'a';
  return /^[A-Z]+$/.test(numeral) ? 'A' : null;
}

/** The form of a marker another program wrote out, in its font. */
function markerForm(marker: string, font: string): ListLevel | null {
  const symbol = SYMBOLS[font]?.[marker];
  if (symbol) return bullet(symbol);
  if (SYMBOL_FONTS.has(font) || /[\uE000-\uF8FF]/u.test(marker)) return null;
  if ([...marker].length === 1 && !/[\p{L}\p{N}]/u.test(marker)) return bullet(marker);
  const found = MARKER.exec(marker);
  const numbering = found && numberingOf(found[3]);
  if (!found || !numbering || found[1].length > AFFIX_MAX || found[4].length > AFFIX_MAX) {
    return null;
  }
  return { numbering, prefix: found[1], suffix: found[4], nested: found[2] !== '' };
}

const STYLE_TYPES: Record<string, ListLevel> = {
  decimal: plainNumber('1'),
  'lower-alpha': plainNumber('a'),
  'lower-latin': plainNumber('a'),
  'upper-alpha': plainNumber('A'),
  'upper-latin': plainNumber('A'),
  'lower-roman': plainNumber('i'),
  'upper-roman': plainNumber('I'),
  disc: bullet('•'),
  circle: bullet('◦'),
  square: bullet('▪'),
};
const OL_TYPES: Record<string, Numbering> = { '1': '1', a: 'a', A: 'A', i: 'i', I: 'I' };

/** The form an HTML list gives its entries, by its type or style. */
function listForm(list: HTMLElement): ListLevel | null {
  const style = /list-style-type:\s*(?:"([^"]*)"|([\w-]+))/i.exec(list.getAttribute('style') ?? '');
  if (style?.[1]?.trim()) return bullet(style[1].trim());
  if (style?.[2] && STYLE_TYPES[style[2].toLowerCase()]) return STYLE_TYPES[style[2].toLowerCase()];
  const type = list.tagName === 'OL' ? OL_TYPES[list.getAttribute('type') ?? ''] : undefined;
  return type ? plainNumber(type) : null;
}

function withForm(item: HTMLElement, form: ListLevel | null): void {
  if (form && kindOfLevel(form) === item.dataset.list) item.dataset.form = JSON.stringify(form);
}

function checkOf(entry: HTMLElement): { kind: ListKind; checked: boolean } | null {
  const box = entry.querySelector<HTMLInputElement>(':scope > input[type=checkbox]');
  if (box) {
    box.remove();
    return { kind: 'check', checked: box.hasAttribute('checked') };
  }
  if (entry.getAttribute('role') === 'checkbox') {
    return { kind: 'check', checked: entry.getAttribute('aria-checked') === 'true' };
  }
  const first = entry.firstChild;
  const mark = first?.textContent?.trimStart()[0];
  if (first?.nodeType === 3 && (mark === CHECKED || mark === UNCHECKED)) {
    first.textContent = first.textContent!.trimStart().slice(1).trimStart();
    return { kind: 'check', checked: mark === CHECKED };
  }
  return null;
}

/** The list's entries as items, each nested list one level further in. */
function itemsOf(list: HTMLElement, level: number): Element[] {
  const kind: ListKind =
    list.dataset.list === 'check' ? 'check' : list.tagName === 'OL' ? 'number' : 'bullet';
  const found: Element[] = [];
  for (const entry of [...list.children] as HTMLElement[]) {
    if (entry.tagName === 'UL' || entry.tagName === 'OL') {
      found.push(...itemsOf(entry, level + 1));
      continue;
    }
    if (entry.tagName !== 'LI') {
      found.push(entry);
      continue;
    }
    const aria = Number(entry.getAttribute('aria-level'));
    const depth = aria >= 1 ? aria - 1 : level;
    const nested: Element[] = [];
    for (const inner of [...entry.querySelectorAll<HTMLElement>(':scope > ul, :scope > ol')]) {
      nested.push(...itemsOf(inner, depth + 1));
      inner.remove();
    }
    const check = checkOf(entry);
    const made = item(entry, check?.kind ?? kind, depth, check?.checked ?? false);
    withForm(made, listForm(list));
    for (const child of [...entry.childNodes]) {
      if (child instanceof HTMLElement && BLOCKS.has(child.tagName)) {
        if (made.childNodes.length) made.append(' ');
        made.append(...child.childNodes);
      } else {
        made.append(child);
      }
    }
    found.push(made, ...nested);
  }
  return found;
}

/** Word marks a list paragraph only in its style, its marker being text it hides elsewhere. */
function wordItems(body: HTMLElement): void {
  for (const paragraph of body.querySelectorAll<HTMLElement>('p[style*="mso-list"]')) {
    const style = paragraph.getAttribute('style') ?? '';
    const level = /level(\d+)/.exec(style);
    if (!level) continue;
    const hidden = [...paragraph.querySelectorAll<HTMLElement>('[style*="mso-list"]')].filter(
      (span) => /mso-list:\s*ignore/i.test(span.getAttribute('style') ?? ''),
    );
    const marker = hidden
      .map((span) => span.textContent ?? '')
      .join('')
      .trim();
    const font = /font-family:\s*"?([^;"]+)/i.exec(
      hidden[0]?.closest('[style*="font-family"]')?.getAttribute('style') ?? '',
    );
    const form = markerForm(marker, font?.[1].trim().toLowerCase() ?? '');
    hidden.forEach((span) => span.remove());
    paragraph.dataset.list = form ? kindOfLevel(form) : NUMBERED.test(marker) ? 'number' : 'bullet';
    withForm(paragraph, form);
    paragraph.dataset.run = /mso-list:\s*(l\d+)/i.exec(style)?.[1] ?? '';
    const depth = Number(level[1]) - 1;
    if (depth > 0) paragraph.dataset.indent = String(depth * INDENT_STEP);
    else delete paragraph.dataset.indent;
  }
}

/** Items that came in forms of their own give their run of items a format, each level in the
 * form of the run's first item at that level; each list they came from is a run of its own. */
function formatRuns(body: HTMLElement): void {
  let run: HTMLElement[] = [];
  const close = () => {
    const levels = new Map<number, ListLevel>();
    for (const item of run) {
      const form = item.dataset.form;
      delete item.dataset.form;
      const level = Math.min(
        Math.round(Number(item.dataset.indent ?? 0) / INDENT_STEP),
        INDENT_MAX / INDENT_STEP,
      );
      if (form && !item.dataset.format && !levels.has(level)) levels.set(level, JSON.parse(form));
    }
    const format = Array.from(
      { length: LIST_LEVELS },
      (_, at) => levels.get(at) ?? standard('number', at),
    );
    if (levels.size && !isStandard(format)) {
      for (const item of run) {
        if (item.dataset.list !== 'check') item.dataset.format ??= JSON.stringify(format);
      }
    }
    run = [];
  };
  for (const item of body.querySelectorAll<HTMLElement>('p[data-list]')) {
    const before = run.at(-1);
    if (before && (before.nextElementSibling !== item || before.dataset.run !== item.dataset.run)) {
      close();
    }
    run.push(item);
  }
  close();
  for (const item of body.querySelectorAll<HTMLElement>('p[data-run]')) delete item.dataset.run;
}

/** Lists from elsewhere as this editor keeps them: every entry a paragraph marked as an item, in
 * its list's format. */
export function flattenLists(body: HTMLElement): void {
  wordItems(body);
  const outer = [...body.querySelectorAll<HTMLElement>('ul, ol')].filter(
    (list) => !list.parentElement?.closest('ul, ol'),
  );
  for (const [index, list] of outer.entries()) {
    const items = itemsOf(list, 0);
    for (const item of items) {
      if (item instanceof HTMLElement && item.dataset.list) item.dataset.run = String(index);
    }
    // How open the copied slice was, which ProseMirror reads from the first element having it.
    const slice = list.getAttribute('data-pm-slice');
    if (slice && items[0]) items[0].setAttribute('data-pm-slice', slice);
    list.replaceWith(...items);
  }
  formatRuns(body);
}

const BULLET_TYPES: Record<string, string> = { '◦': 'circle', '▪': 'square' };

/** The look an HTML list gives its entries at the level, near as it can to the form. */
function lookAs(list: HTMLElement, form: ListLevel): void {
  if (form.numbering) {
    if (form.numbering !== '1') list.setAttribute('type', form.numbering);
  } else if (form.prefix !== '•') {
    const type = BULLET_TYPES[form.prefix] ?? JSON.stringify(`${form.prefix} `);
    list.setAttribute('style', `list-style-type: ${type}`);
  }
}

/** Items as other programs know them: runs of items as nested lists, each entry carrying its
 * list's format for a paste back into PONISTRA. */
export function listElements(
  content: Fragment,
  render: (node: Node) => globalThis.Node,
  inline: (node: Node, into: HTMLElement) => void,
  document: Document,
  formats: ListFormats,
): DocumentFragment {
  const into = document.createDocumentFragment();
  let open: { level: number; kind: ListKind; list: HTMLElement }[] = [];
  content.forEach((node) => {
    const kind = node.type === paragraph ? listOf(node) : null;
    if (!kind) {
      open = [];
      into.append(render(node));
      return;
    }
    const level = levelOf(node);
    while (
      open.length &&
      (open.at(-1)!.level > level || (open.at(-1)!.level === level && open.at(-1)!.kind !== kind))
    ) {
      open.pop();
    }
    if (!open.length || open.at(-1)!.level < level) {
      const list = document.createElement(kind === 'number' ? 'ol' : 'ul');
      if (kind === 'check') list.dataset.list = 'check';
      else lookAs(list, levelIn(formatOf(formats, node.attrs.format), kind, level));
      const parent = open.at(-1)?.list.lastElementChild ?? open.at(-1)?.list ?? into;
      parent.append(list);
      open.push({ level, kind, list });
    }
    const entry = document.createElement('li');
    if (node.attrs.style) entry.dataset.style = node.attrs.style;
    const format = kind === 'check' ? undefined : formatOf(formats, node.attrs.format);
    if (format) entry.dataset.format = JSON.stringify(format);
    if (node.attrs.align) entry.style.textAlign = node.attrs.align;
    if (kind === 'check') entry.append(`${node.attrs.checked ? CHECKED : UNCHECKED} `);
    inline(node, entry);
    open.at(-1)!.list.append(entry);
  });
  return into;
}

/** An item's marker in plain text, indented two spaces a level. */
export function textMarker(node: Node, marker: string | undefined): string {
  const kind = node.type === paragraph ? listOf(node) : null;
  if (!kind) return '';
  const shown = kind === 'check' ? (node.attrs.checked ? CHECKED : UNCHECKED) : marker;
  return `${'  '.repeat(levelOf(node))}${shown} `;
}
