import type { Node } from 'prosemirror-model';
import { Plugin, PluginKey, type EditorState } from 'prosemirror-state';
import { Decoration, DecorationSet, type EditorView } from 'prosemirror-view';
import * as Y from 'yjs';
import { shownNotes, tabSettings, type ShownNote } from './notes';

/** A page as the document or a tab sets it up, in centimetres, its width and height as the page
 * lies; `start` is the first page's number where the tab does not number on from the one before. */
export interface PageSetup {
  width: number;
  height: number;
  top: number;
  right: number;
  bottom: number;
  left: number;
  header: number;
  footer: number;
  firstPage: boolean;
  start: number | null;
}

export const STANDARD: PageSetup = {
  width: 21,
  height: 29.7,
  top: 2.5,
  right: 2.5,
  bottom: 2.5,
  left: 2.5,
  header: 1.25,
  footer: 1.25,
  firstPage: false,
  start: null,
};

export const PARTS = ['header', 'footer', 'headerFirst', 'footerFirst'] as const;
export type Part = (typeof PARTS)[number];

const PAGE = 'page';
const COUNTS = 'pages';
const SECTIONS = 'sections';
const LENGTHS = ['width', 'height', 'top', 'right', 'bottom', 'left', 'header', 'footer'] as const;

/** The tab's own settings where it has pages of its own. */
function ownPages(own: Y.Doc, tab: string | null): Y.Map<unknown> | null {
  const mine = tab === null ? undefined : tabSettings(own).get(tab);
  return mine?.get(PAGE) instanceof Y.Map ? mine : null;
}

/** The tab's pages: its own where it has them, else the document's. */
export function setupOf(own: Y.Doc, tab: string | null): PageSetup {
  const mine = ownPages(own, tab);
  return setupFrom((mine?.get(PAGE) as Y.Map<unknown> | undefined) ?? own.getMap(PAGE));
}

function setupFrom(kept: Y.Map<unknown>): PageSetup {
  const setup = { ...STANDARD };
  for (const name of LENGTHS) {
    const value = kept.get(name);
    if (typeof value === 'number' && value > 0) setup[name] = value;
  }
  setup.firstPage = kept.get('firstPage') === true;
  const start = kept.get('start');
  setup.start = Number.isInteger(start) ? (start as number) : null;
  return setup;
}

/** The tab's headers and footers, from where its pages are kept. */
export function partsOf(own: Y.Doc, tab: string | null): Partial<Record<Part, Y.XmlFragment>> {
  const mine = ownPages(own, tab);
  const parts: Partial<Record<Part, Y.XmlFragment>> = {};
  for (const name of PARTS) {
    const fragment = mine ? mine.get(name) : own.getXmlFragment(name);
    if (fragment instanceof Y.XmlFragment && fragment.length) parts[name] = fragment;
  }
  return parts;
}

/** The tab's header or footer to write in, made where its own pages have none yet. */
export function partFragment(own: Y.Doc, tab: string | null, part: Part): Y.XmlFragment {
  const mine = ownPages(own, tab);
  if (!mine) return own.getXmlFragment(part);
  const found = mine.get(part);
  if (found instanceof Y.XmlFragment) return found;
  const made = new Y.XmlFragment();
  own.transact(() => mine.set(part, made));
  return made;
}

/** Sets the first page's header and footer apart, or not, where the tab takes its pages from. */
export function setFirstPage(own: Y.Doc, tab: string | null, apart: boolean): void {
  const mine = ownPages(own, tab);
  const kept = (mine?.get(PAGE) as Y.Map<unknown> | undefined) ?? own.getMap(PAGE);
  own.transact(() => kept.set('firstPage', apart));
}

/** A section of the tab: the id of the break it follows, null for the tab's first, its page setup
 * and its headers and footers. What a section after a break does not set itself it takes from the
 * section before, the page setup without its `start`; a header or footer it sets empty is blank. */
export interface Section {
  id: string | null;
  setup: PageSetup;
  parts: Partial<Record<Part, Y.XmlFragment>>;
}

/** What the section after the break sets itself, kept under the tab's settings by the break's id. */
function sectionKept(own: Y.Doc, tab: string, id: string, make = false): Y.Map<unknown> | null {
  const settings = tabSettings(own);
  let holder = settings.get(tab);
  let kept = holder?.get(SECTIONS);
  if (!(kept instanceof Y.Map) && make) {
    if (!holder) {
      holder = new Y.Map();
      settings.set(tab, holder);
    }
    kept = new Y.Map();
    holder.set(SECTIONS, kept);
  }
  if (!(kept instanceof Y.Map)) return null;
  const found = (kept as Y.Map<unknown>).get(id);
  if (found instanceof Y.Map) return found;
  if (!make) return null;
  const made = new Y.Map<unknown>();
  (kept as Y.Map<unknown>).set(id, made);
  return made;
}

/** The place among the tab's sections of the one `pos` is in; a break ends the section before it. */
export function sectionAt(doc: Node, pos: number): number {
  let section = 0;
  doc.forEach((node, offset) => {
    if (node.type.name === 'sectionBreak' && offset < pos) section++;
  });
  return section;
}

/** Whether the page is the first of its section, by each page's section. */
export function opensSection(sections: readonly number[], page: number): boolean {
  return page === 0 || sections[page] !== sections[page - 1];
}

/** Each page's number, by each page's section, from the tab's first: a section that sets its own
 * `start` numbers from it, any other on from the page before. */
export function pageNumbersOf(
  first: number,
  setups: readonly PageSetup[],
  sections: readonly number[],
): number[] {
  const numbers: number[] = [];
  sections.forEach((section, page) => {
    const start = page > 0 && opensSection(sections, page) ? setups[section]?.start : null;
    numbers.push(page === 0 ? first : (start ?? numbers[page - 1] + 1));
  });
  return numbers;
}

/** The ids of the tab's section breaks, in order. */
export function breaksOf(doc: Node): string[] {
  const found: string[] = [];
  doc.forEach((node) => {
    if (node.type.name === 'sectionBreak') found.push(node.attrs.id as string);
  });
  return found;
}

/** The tab's sections, one before its first section break and one after each. */
export function sectionsOf(own: Y.Doc, tab: string | null, breaks: readonly string[]): Section[] {
  const sections: Section[] = [{ id: null, setup: setupOf(own, tab), parts: partsOf(own, tab) }];
  for (const id of breaks) {
    const before = sections.at(-1)!;
    const kept = tab === null ? null : sectionKept(own, tab, id);
    const page = kept?.get(PAGE);
    const parts = { ...before.parts };
    for (const name of PARTS) {
      const fragment = kept?.get(name);
      if (!(fragment instanceof Y.XmlFragment)) continue;
      if (fragment.length) parts[name] = fragment;
      else delete parts[name];
    }
    sections.push({
      id,
      setup: page instanceof Y.Map ? setupFrom(page) : { ...before.setup, start: null },
      parts,
    });
  }
  return sections;
}

/** Whether the section after the break shows the header or footer of the section before. */
export function partLinked(own: Y.Doc, tab: string, id: string, part: Part): boolean {
  return !(sectionKept(own, tab, id)?.get(part) instanceof Y.XmlFragment);
}

/** The place of the section whose header or footer the section at `index` of those `breaks` start
 * shows: the nearest up to it that sets it itself, the tab's first where none does. */
export function partOwner(
  own: Y.Doc,
  tab: string,
  breaks: readonly string[],
  index: number,
  part: Part,
): number {
  for (let at = index; at > 0; at--) if (!partLinked(own, tab, breaks[at - 1], part)) return at;
  return 0;
}

/** The header or footer to write in for the section at `index`, that of the section it shows. */
export function sectionPart(
  own: Y.Doc,
  tab: string,
  breaks: readonly string[],
  index: number,
  part: Part,
): Y.XmlFragment {
  const owner = partOwner(own, tab, breaks, index, part);
  if (!owner) return partFragment(own, tab, part);
  return sectionKept(own, tab, breaks[owner - 1])!.get(part) as Y.XmlFragment;
}

/** Has the section after the break show the header or footer of the section before, or one of its
 * own that starts as a copy of it. */
export function linkPart(
  own: Y.Doc,
  tab: string,
  breaks: readonly string[],
  index: number,
  part: Part,
  linked: boolean,
): void {
  own.transact(() => {
    const kept = sectionKept(own, tab, breaks[index - 1], true)!;
    if (linked) {
      kept.delete(part);
      return;
    }
    const shown = sectionPart(own, tab, breaks, index - 1, part);
    const copy = new Y.XmlFragment();
    kept.set(part, copy);
    copy.insert(
      0,
      shown.toArray().map((child) => child.clone() as Y.XmlElement | Y.XmlText),
    );
  });
}

/** Whether the section after the break has a page setup of its own. */
export function sectionOwnsPages(own: Y.Doc, tab: string, id: string): boolean {
  return sectionKept(own, tab, id)?.get(PAGE) instanceof Y.Map;
}

/** Saves the setup as the section's own, for the section after the break, or has it take the one
 * of the section before where null. */
export function saveSection(own: Y.Doc, tab: string, id: string, setup: PageSetup | null): void {
  own.transact(() => {
    const kept = sectionKept(own, tab, id, setup !== null);
    if (!kept) return;
    if (!setup) {
      kept.delete(PAGE);
      return;
    }
    let page = kept.get(PAGE);
    if (!(page instanceof Y.Map)) {
      page = new Y.Map();
      kept.set(PAGE, page);
    }
    written(page as Y.Map<unknown>, setup);
  });
}

/** How many pages each tab has, kept by whoever lays it out, the server's printer included, so the
 * tabs after it number on. */
function pageCounts(own: Y.Doc): Y.Map<number> {
  return own.getMap<number>(COUNTS);
}

export function writePages(own: Y.Doc, tab: string, pages: number): void {
  if (pageCounts(own).get(tab) !== pages) own.transact(() => pageCounts(own).set(tab, pages));
}

/** The tab's first page number and the document's page count, from the tabs' kept counts and the
 * tab's own count as laid out now. A tab the server has not counted yet is new and empty, on one
 * page. */
export function numberingOf(
  own: Y.Doc,
  tabs: readonly string[],
  tab: string,
  pages: number,
): { first: number; total: number } {
  const counts = pageCounts(own);
  const { firsts, total } = pageNumbers(own, tabs, (id) =>
    id === tab ? pages : (counts.get(id) ?? 1),
  );
  return { first: firsts[tab] ?? 1, total };
}

/** Each tab's first page number and the document's page count, from how many pages each tab has. */
export function pageNumbers(
  own: Y.Doc,
  tabs: readonly string[],
  countOf: (tab: string) => number,
): { firsts: Record<string, number>; total: number } {
  const firsts: Record<string, number> = {};
  let next = 1;
  for (const [index, id] of tabs.entries()) {
    const start = restartOf(own, id, index === 0);
    if (start !== null) next = start;
    firsts[id] = next;
    next += countOf(id);
  }
  return { firsts, total: tabs.reduce((total, id) => total + countOf(id), 0) };
}

/** The number the tab's pages start again from: its own pages' start, the document's on its first
 * tab, which no other tab sharing the document's pages takes. */
function restartOf(own: Y.Doc, tab: string, first: boolean): number | null {
  return first || ownPages(own, tab) ? setupOf(own, tab).start : null;
}

export function ownsPages(own: Y.Doc, tab: string | null): boolean {
  return ownPages(own, tab) !== null;
}

/** Whether the tab has headers or footers of its own, which it gives up with its own pages. */
export function ownsParts(own: Y.Doc, tab: string): boolean {
  const mine = ownPages(own, tab);
  return PARTS.some((name) => {
    const fragment = mine?.get(name);
    return fragment instanceof Y.XmlFragment && fragment.length > 0;
  });
}

function written(kept: Y.Map<unknown>, setup: PageSetup): void {
  for (const name of LENGTHS) kept.set(name, setup[name]);
  kept.set('firstPage', setup.firstPage);
  if (setup.start === null) kept.delete('start');
  else kept.set('start', setup.start);
}

/** Saves the setup as the tab's own, taking over the document's headers and footers when it gets
 * pages of its own, or as the document's, which the tab then follows, giving up its own. */
export function savePages(own: Y.Doc, tab: string | null, setup: PageSetup, mine: boolean): void {
  own.transact(() => {
    const settings = tabSettings(own);
    let holder = tab === null ? undefined : settings.get(tab);
    if (!mine || tab === null) {
      if (holder?.get(PAGE) instanceof Y.Map) {
        holder.delete(PAGE);
        for (const name of PARTS) holder.delete(name);
      }
      written(own.getMap(PAGE), setup);
      return;
    }
    if (!holder) {
      holder = new Y.Map();
      settings.set(tab, holder);
    }
    if (!(holder.get(PAGE) instanceof Y.Map)) {
      holder.set(PAGE, new Y.Map());
      for (const name of PARTS) {
        const shared = own.getXmlFragment(name);
        if (!shared.length) continue;
        const copy = new Y.XmlFragment();
        holder.set(name, copy);
        copy.insert(
          0,
          shared.toArray().map((child) => child.clone() as Y.XmlElement | Y.XmlText),
        );
      }
    }
    written(holder.get(PAGE) as Y.Map<unknown>, setup);
  });
}

/** Paper sizes as the sheet stands, in centimetres. */
export const PAPERS = {
  a4: [21, 29.7],
  a3: [29.7, 42],
  a5: [14.8, 21],
  b5: [17.6, 25],
  letter: [21.59, 27.94],
  legal: [21.59, 35.56],
} as const;
export type Paper = keyof typeof PAPERS;

const same = (a: number, b: number) => Math.abs(a - b) < 0.05;

export function paperOf({ width, height }: Pick<PageSetup, 'width' | 'height'>): Paper | null {
  const [short, long] = width < height ? [width, height] : [height, width];
  const found = Object.entries(PAPERS).find(
    ([, size]) => same(size[0], short) && same(size[1], long),
  );
  return found ? (found[0] as Paper) : null;
}

type Sides = Pick<PageSetup, 'top' | 'right' | 'bottom' | 'left'>;

export const MARGINS = {
  normal: { top: 2.5, right: 2.5, bottom: 2.5, left: 2.5 },
  narrow: { top: 1.27, right: 1.27, bottom: 1.27, left: 1.27 },
  wide: { top: 2.54, right: 5.08, bottom: 2.54, left: 5.08 },
} as const satisfies Record<string, Sides>;
export type Margins = keyof typeof MARGINS;

export function marginsOf(setup: Sides): Margins | null {
  const found = Object.entries(MARGINS).find(([, sides]) =>
    (['top', 'right', 'bottom', 'left'] as const).every((side) => same(sides[side], setup[side])),
  );
  return found ? (found[0] as Margins) : null;
}

/** Text needs at least this much of the page each way, in centimetres. */
export const LEAST_TEXT = 2;

export function roomForText(setup: PageSetup): boolean {
  return (
    setup.width - setup.left - setup.right >= LEAST_TEXT &&
    setup.height - setup.top - setup.bottom >= LEAST_TEXT
  );
}

export const PX_PER_CM = 96 / 2.54;
/** Grey between two pages. */
const BETWEEN = 24;

/** A page in CSS pixels. */
export interface Geometry {
  width: number;
  height: number;
  top: number;
  right: number;
  bottom: number;
  left: number;
  header: number;
  footer: number;
  gap: number;
  /** The first page's margins, which its own header and footer may push in. */
  firstTop: number;
  firstBottom: number;
}

export function geometryOf(setup: PageSetup): Geometry {
  const px = (cm: number) => cm * PX_PER_CM;
  return {
    width: px(setup.width),
    height: px(setup.height),
    top: px(setup.top),
    right: px(setup.right),
    bottom: px(setup.bottom),
    left: px(setup.left),
    header: px(setup.header),
    footer: px(setup.footer),
    gap: BETWEEN,
    firstTop: px(setup.top),
    firstBottom: px(setup.bottom),
  };
}

/** How tall the tab's headers and footers show, in CSS pixels. */
export type PartHeights = Partial<Record<Part, number>>;

/** The page with its text clear of a header or footer taller than its margin, as Word pushes it;
 * the first page by its own where the tab sets it apart. */
export function clearOfParts(
  geometry: Geometry,
  heights: PartHeights,
  firstPage: boolean,
): Geometry {
  const top = (part: Part) => Math.max(geometry.top, geometry.header + (heights[part] ?? 0));
  const bottom = (part: Part) => Math.max(geometry.bottom, geometry.footer + (heights[part] ?? 0));
  return {
    ...geometry,
    top: top('header'),
    bottom: bottom('footer'),
    firstTop: top(firstPage ? 'headerFirst' : 'header'),
    firstBottom: bottom(firstPage ? 'footerFirst' : 'footer'),
  };
}

/** A page as it stands among the others: its top from the top of the first, its left from the left
 * edge of the widest, its section's place among the tab's sections and its section's geometry. */
export interface PagePlace {
  top: number;
  left: number;
  section: number;
  geometry: Geometry;
}

/** The pages one under another, each centred on the widest of the tab's sections, as laid out;
 * before that, one page of the first section. */
export interface Stack {
  pages: PagePlace[];
  width: number;
  height: number;
}

export function stackOf(sheets: readonly Geometry[], laid: Laid | null): Stack {
  const width = Math.max(...sheets.map((sheet) => sheet.width));
  let top = 0;
  const pages = (laid?.sections ?? [0]).map((each) => {
    const section = Math.min(each, sheets.length - 1);
    const geometry = sheets[section];
    const page = { top, left: (width - geometry.width) / 2, section, geometry };
    top += geometry.height + geometry.gap;
    return page;
  });
  return { pages, width, height: top - pages.at(-1)!.geometry.gap };
}

/** How far a section's text stands in from the first section's at either side, where its pages
 * are narrower or wider or its margins otherwise. */
export function insetOf(sheets: readonly Geometry[], section: number): [number, number] {
  const width = Math.max(...sheets.map((sheet) => sheet.width));
  const column = ({ width: across, left, right }: Geometry) => {
    const x = (width - across) / 2;
    return [x + left, width - x - across + right];
  };
  const [left, right] = column(sheets[0]);
  const [mine, theirs] = column(sheets[Math.min(section, sheets.length - 1)]);
  return [mine - left, theirs - right];
}

/** A line of a block, from the top of its box: the position of its first character. */
export interface Line {
  top: number;
  bottom: number;
  pos: number;
}

/** A table row from the top of the table; `joined` where a merged cell from above runs into it,
 * `header` where it is one of the table's first rows that stand again atop each page it runs onto. */
export interface Row {
  top: number;
  bottom: number;
  joined: boolean;
  header: boolean;
}

/** A footnote whose mark stands in a block: the note's place among the tab's footnotes, how far
 * down the block its mark ends and how tall the note shows at the foot of the page. */
export interface Footnote {
  index: number;
  y: number;
  height: number;
}

/** A block of the tab as it lies without the page gaps, in CSS pixels. */
export interface Measured {
  pos: number;
  height: number;
  before: number;
  after: number;
  /** Stays on the page of the block after it, as a heading does. */
  keep: boolean;
  /** What follows starts a new page. */
  forces: boolean;
  lines?: () => Line[];
  rows?: () => Row[];
  notes?: readonly Footnote[];
  /** The block is the tab's endnote of this place, listed after its text. */
  endnote?: number;
  /** The tab's section the block is in, by its place among them; its first where not given. */
  section?: number;
}

/** A page ends before the block at `pos`, before the line starting at `pos`, or before the row
 * `row` of the table at `pos`; `gap` is how far the next page's first line stands below. A table's
 * header rows stand again in the last `header` pixels of the gap before a row of its body. A break
 * after a block, line or row taller than its page turns the `pages` it runs on over. */
export type Break = (
  | { kind: 'block'; pos: number; gap: number }
  | { kind: 'line'; pos: number; gap: number }
  | { kind: 'row'; pos: number; row: number; gap: number; header?: number }
  | { kind: 'note'; index: number; gap: number }
) & { pages?: number };

/** A footnote set at the foot of page `page`, `top` from the top of the first page. */
export interface Foot {
  index: number;
  page: number;
  top: number;
}

/** The pages laid out and the tab's section each is in, by its place among them. */
export interface Laid {
  breaks: Break[];
  pages: number;
  feet: Foot[];
  sections: number[];
}

/** The page a position of the text is on. */
export function pageAt(laid: Laid | null | undefined, pos: number): number {
  let page = 0;
  for (const each of laid?.breaks ?? []) {
    if (each.kind !== 'note' && each.pos <= pos) page += each.pages ?? 1;
  }
  return page;
}

/** Lines a paragraph keeps together at the foot and the head of a page, as Word does. */
const ORPHANS = 2;
const WIDOWS = 2;

/** Room between the text and the footnotes under it, where the separator rule stands. */
export const SEPARATOR = 16;

interface Kept {
  index: number;
  /** Bottom of the block on its page, with its margin after it. */
  end: number;
  whole: boolean;
  /** The footnotes whose marks it has on the page. */
  notes: readonly Footnote[];
}

/** The pages the blocks fill, each section's on pages of its own, `sheets` by its place among the
 * tab's sections: a paragraph breaks between its lines, keeping two at either side; a table
 * between its rows; a block that keeps with the next goes over with it; any other block goes over
 * whole, unless it starts a page and is taller than one. A section's first page keeps the room
 * above its first block, as the tab's first does. A footnote stands at the foot of the page its
 * mark is on, and the text on that page leaves it room. */
export function laidOut(blocks: readonly Measured[], sheets: readonly Geometry[]): Laid {
  const sections = [blocks[0]?.section ?? 0];
  const tops = [0];
  const now = () => sections[pages - 1];
  const opens = (page: number) => page === 1 || sections[page - 1] !== sections[page - 2];
  // A section written since the sheets were given is laid on the last until its own come.
  const sheetOf = (section: number) => sheets[Math.min(section, sheets.length - 1)];
  const sheet = (page: number) => sheetOf(sections[page - 1]);
  const top = (page: number) => (opens(page) ? sheet(page).firstTop : sheet(page).top);
  const bottom = (page: number) => (opens(page) ? sheet(page).firstBottom : sheet(page).bottom);
  const roomOf = (page: number) => sheet(page).height - top(page) - bottom(page);
  /** From the foot of this page's text to the top of the next's, in the section given. */
  const skipTo = (section: number) =>
    bottom(pages) +
    sheet(pages).gap +
    (section === now() ? sheetOf(section).top : sheetOf(section).firstTop);
  const breaks: Break[] = [];
  const feet: Foot[] = [];
  let pages = 1;
  let room = roomOf(pages);
  let y = 0;
  let placed: Kept[] = [];
  let noted: Footnote[] = [];
  let forced = false;

  const footing = (more: readonly Footnote[] = []) => {
    const height = [...noted, ...more].reduce((sum, note) => sum + note.height, 0);
    return height ? height + SEPARATOR : 0;
  };
  const settle = () => {
    let at = tops[pages - 1] + sheet(pages).height - bottom(pages) - footing() + SEPARATOR;
    for (const note of noted) {
      feet.push({ index: note.index, page: pages - 1, top: at });
      at += note.height;
    }
  };
  const turn = (section = now()) => {
    settle();
    tops.push(tops[pages - 1] + sheet(pages).height + sheet(pages).gap);
    sections.push(section);
    pages += 1;
    room = roomOf(pages);
    y = 0;
    placed = [];
    noted = [];
  };
  /** How far below `end`, where the page's text ends, the next page's first line stands, that
   * page in the section given, past the pages that text runs on over where it is taller than its
   * page; a gap is never below nought, which no element can be. */
  const ending = (end: number, section = now()): { gap: number; pages?: number } => {
    let gap = room - end;
    let over = 0;
    for (; gap + skipTo(section) < 0; over++) {
      gap += skipTo(now());
      turn();
      gap += room;
    }
    gap += skipTo(section);
    return over ? { gap, pages: over + 1 } : { gap };
  };
  const breakBefore = (index: number, end: number) => {
    const block = blocks[index];
    const section = block.section ?? 0;
    const opening = section !== now();
    const { gap, ...turned } = ending(end, section);
    const below = opening ? gap : Math.max(0, gap - block.before);
    breaks.push(
      block.endnote === undefined
        ? { kind: 'block', pos: block.pos, gap: below, ...turned }
        : { kind: 'note', index: block.endnote, gap: below, ...turned },
    );
    turn(section);
  };
  const end = () => placed.at(-1)?.end ?? 0;
  const place = (index: number, bottom: number, whole: boolean, notes: readonly Footnote[]) => {
    y = bottom;
    placed.push({ index, end: bottom + blocks[index].after, whole, notes });
    noted.push(...notes);
    forced = blocks[index].forces;
  };

  for (let index = 0; index < blocks.length; index++) {
    const block = blocks[index];
    const notes = block.notes ?? [];
    if (forced || (block.section ?? 0) !== now()) breakBefore(index, end());
    const fresh = placed.length === 0;
    const at = fresh
      ? opens(pages)
        ? block.before
        : 0
      : y + Math.max(blocks[index - 1].after, block.before);
    if (at + block.height <= room - footing(notes)) {
      place(index, at + block.height, true, notes);
      continue;
    }
    const pieces: readonly (Line | Row)[] = block.lines?.() ?? block.rows?.() ?? [];
    if (fresh && !pieces.length) {
      place(index, at + block.height, true, notes);
      continue;
    }
    if (!fresh) {
      const chain = keptWith(blocks, placed, index);
      if (chain < index && !fitsAny(block, pieces, room - footing() - at)) {
        const leading = placed.findIndex((each) => each.index === chain);
        const moved = new Set(placed.slice(leading).flatMap((each) => each.notes));
        noted = noted.filter((note) => !moved.has(note));
        breakBefore(chain, placed[leading - 1].end);
        index = chain - 1;
        continue;
      }
      if (!pieces.length) {
        breakBefore(index, end());
        place(index, block.height, true, notes);
        continue;
      }
    }

    let first = 0;
    let offset = at;
    let startsPage = fresh;
    const marked = (to: number) =>
      notes.filter((note) => (first === 0 || note.y > pieces[first].top) && note.y <= to);
    while (offset + block.height > room - footing(marked(Infinity))) {
      let fit = first;
      while (
        fit < pieces.length &&
        offset + pieces[fit].bottom <= room - footing(marked(pieces[fit].bottom))
      ) {
        fit++;
      }
      const count = taken(block, pieces, first, fit, startsPage);
      if (count === 0) {
        breakBefore(index, end());
        offset = 0;
        startsPage = true;
        continue;
      }
      const next = first + count;
      if (next >= pieces.length) break;
      noted.push(...marked(pieces[next].top));
      const { gap: below, ...turned } = ending(offset + pieces[next].top);
      const header = block.lines
        ? 0
        : headerOver(
            pieces as readonly Row[],
            next,
            sheet(pages).height - sheet(pages).top - sheet(pages).bottom,
          );
      const gap = below + header;
      breaks.push(
        block.lines
          ? { kind: 'line', pos: (pieces[next] as Line).pos, gap, ...turned }
          : header
            ? { kind: 'row', pos: block.pos, row: next, gap, header, ...turned }
            : { kind: 'row', pos: block.pos, row: next, gap, ...turned },
      );
      turn();
      first = next;
      offset = header - pieces[next].top;
      startsPage = true;
    }
    place(index, offset + block.height, first === 0, marked(Infinity));
  }
  settle();
  return { breaks, pages, feet, sections };
}

/** How many of a block's lines or rows from `first` stay on the page, of the `fit - first` that
 * would: a paragraph keeps two lines at either side, a row a merged cell runs into stays with the
 * one above, and a page that starts with the block takes at least one. */
function taken(
  block: Measured,
  pieces: readonly (Line | Row)[],
  first: number,
  fit: number,
  startsPage: boolean,
): number {
  if (block.lines) {
    const count = Math.min(fit - first, pieces.length - first - WIDOWS);
    if (count >= ORPHANS) return count;
    return startsPage ? Math.max(fit - first, 1) : 0;
  }
  const rows = pieces as readonly Row[];
  let count = fit - first;
  while (count > 0 && rows[first + count]?.joined) count--;
  if (count > 0 || !startsPage) return count;
  count = Math.max(fit - first, 1);
  while (first + count < rows.length && rows[first + count].joined) count++;
  return count;
}

/** How tall a table's header rows stand again atop a page that starts with its row `next`: not
 * where the page starts inside them, nor where they leave no room for that row. */
function headerOver(rows: readonly Row[], next: number, room: number): number {
  const count = rows.findIndex((row) => !row.header);
  if (count <= 0 || next < count) return 0;
  const height = rows[count - 1].bottom - rows[0].top;
  return height + rows[next].bottom - rows[next].top <= room ? height : 0;
}

/** The first block of the run before `index` that keeps with what follows it, back to the page's
 * first block, which stays. */
function keptWith(blocks: readonly Measured[], placed: readonly Kept[], index: number): number {
  let chain = index;
  for (let at = placed.length - 1; at > 0; at--) {
    const each = placed[at];
    if (each.index !== chain - 1 || !each.whole || !blocks[each.index].keep) break;
    chain = each.index;
  }
  return chain;
}

/** Whether a block that breaks leaves enough of itself on the page to keep what leads into it. */
function fitsAny(block: Measured, pieces: readonly (Line | Row)[], space: number): boolean {
  const fit = pieces.filter((piece) => piece.bottom <= space).length;
  return block.lines ? Math.min(fit, pieces.length - WIDOWS) >= ORPHANS : fit > 0;
}

export function sameLaid(a: Laid | null, b: Laid): boolean {
  if (!a || a.pages !== b.pages || a.breaks.length !== b.breaks.length) return false;
  if (a.sections.some((section, page) => section !== b.sections[page])) return false;
  if (a.feet.length !== b.feet.length) return false;
  const feet = a.feet.every((each, at) => {
    const other = b.feet[at];
    return each.index === other.index && Math.abs(each.top - other.top) < 0.5;
  });
  const near = (one = 0, two = 0) => Math.abs(one - two) < 0.5;
  const header = (each: Break) => (each.kind === 'row' ? each.header : 0);
  return (
    feet &&
    a.breaks.every((each, at) => {
      const other = b.breaks[at];
      return (
        near(each.gap, other.gap) &&
        near(header(each), header(other)) &&
        JSON.stringify({ ...each, gap: 0, header: 0 }) ===
          JSON.stringify({ ...other, gap: 0, header: 0 })
      );
    })
  );
}

export const GAP = 'ponistra-page-gap';
export const PDF_PAGE = 'ponistra-pdf-page';

/** The page gaps a block holds, as they stand now: client top and height. */
function gapsIn(dom: HTMLElement, scale: number): { top: number; height: number }[] {
  return [...dom.querySelectorAll<HTMLElement>(`.${GAP}`)].map((gap) => {
    const rect = gap.getBoundingClientRect();
    return { top: rect.top, height: rect.height / scale };
  });
}

/** How much a transform, as the Pages view's zoom, enlarges an element on screen: its box against
 * its width as laid out, which `offsetWidth` rounds to a whole pixel. */
export function scaleOf(element: HTMLElement, rect = element.getBoundingClientRect()): number {
  return rect.width / parseFloat(getComputedStyle(element).width) || 1;
}

function heightAbove(gaps: readonly { top: number; height: number }[], client: number): number {
  let sum = 0;
  for (const gap of gaps) if (gap.top < client - 0.5) sum += gap.height;
  return sum;
}

const KEEPS = new Set(['heading', 'title', 'subtitle']);
const FORCES = new Set(['pageBreak', 'sectionBreak']);

/** The tab's blocks as they would lie without the page gaps, its endnotes after them. */
export function measure(view: EditorView): Measured[] {
  const scale = scaleOf(view.dom);
  const blocks: Measured[] = [];
  const footnotes = shownNotes(view, 'foot').notes;
  let section = 0;
  view.state.doc.forEach((node, pos) => {
    const here = section;
    if (node.type.name === 'sectionBreak') section++;
    const dom = view.nodeDOM(pos);
    if (!(dom instanceof HTMLElement)) return;
    const style = getComputedStyle(dom);
    if (style.display === 'none') return;
    const rect = dom.getBoundingClientRect();
    const gaps = gapsIn(dom, scale);
    const local = (client: number) => (client - rect.top) / scale - heightAbove(gaps, client);
    const block: Measured = {
      pos,
      height: rect.height / scale - gaps.reduce((sum, gap) => sum + gap.height, 0),
      before: parseFloat(style.marginTop) || 0,
      after: parseFloat(style.marginBottom) || 0,
      keep: KEEPS.has(node.type.name),
      forces: FORCES.has(node.type.name),
      section: here,
    };
    const notes = footnotes.flatMap((note, index) =>
      note.pos > pos && note.pos < pos + node.nodeSize
        ? [{ index, y: local(note.mark.getBoundingClientRect().bottom), height: heightOf(note) }]
        : [],
    );
    if (notes.length) block.notes = notes;
    if (node.isTextblock) {
      block.lines = () => linesOf(view, dom, style, rect, local);
    } else if (node.type.name === 'table') {
      block.rows = () => rowsOf(dom, local);
    } else if (node.type.name === 'pdf') {
      block.rows = () => pdfPagesOf(dom, local);
    }
    blocks.push(block);
  });
  return [...blocks, ...endnotes(view, scale).map((block) => ({ ...block, section }))];
}

/** How tall a note shows in its list, without a page gap laid before it. */
function heightOf(note: ShownNote): number {
  return note.item.offsetHeight - (parseFloat(note.item.style.paddingTop) || 0);
}

/** The tab's endnotes as blocks after its text, the first from the top of its section, whose
 * separator goes over with it; a page gap before one is laid in its item, or before the first in
 * its section. */
function endnotes(view: EditorView, scale: number): Measured[] {
  const { section, notes } = shownNotes(view, 'end');
  if (!section || !notes.length || getComputedStyle(section).display === 'none') return [];
  let above = view.dom.lastElementChild?.getBoundingClientRect().bottom ?? 0;
  return notes.map((note, index) => {
    const box = note.item.getBoundingClientRect();
    const padding = parseFloat((index ? note.item : section).style.paddingTop) || 0;
    const top = (index ? box.top : section.getBoundingClientRect().top) + padding * scale;
    const block: Measured = {
      pos: note.pos,
      height: (box.bottom - top) / scale,
      before: (top - padding * scale - above) / scale,
      after: 0,
      keep: false,
      forces: false,
      endnote: index,
    };
    above = box.bottom;
    return block;
  });
}

/** Sets the footnotes at the foot of their pages, as wide as the text of each page's section, and
 * lays the endnotes' page gaps, as laid out; without pages, the lists stand as the text view shows
 * them. */
function placeNotes(view: EditorView, laid: Laid | null, sheets: readonly Geometry[] = []): void {
  const feet = new Map(laid?.feet.map((foot) => [foot.index, foot]));
  shownNotes(view, 'foot').notes.forEach(({ item }, index) => {
    const foot = feet.get(index);
    const [left, right] =
      foot && sheets.length > 1 ? insetOf(sheets, laid!.sections[foot.page]) : [0, 0];
    item.style.top = foot ? `${foot.top}px` : '';
    item.style.left = left ? `${left}px` : '';
    item.style.right = right ? `${right}px` : '';
    item.toggleAttribute('data-placed', Boolean(foot));
    item.toggleAttribute('data-first', Boolean(foot) && feet.get(index - 1)?.page !== foot!.page);
  });
  const gaps = new Map<number, number>();
  for (const each of laid?.breaks ?? []) if (each.kind === 'note') gaps.set(each.index, each.gap);
  const { section, notes } = shownNotes(view, 'end');
  if (section) section.style.paddingTop = gaps.has(0) ? `${gaps.get(0)}px` : '';
  notes.forEach(({ item }, index) => {
    item.style.paddingTop = index > 0 && gaps.has(index) ? `${gaps.get(index)}px` : '';
  });
}

function linesOf(
  view: EditorView,
  dom: HTMLElement,
  style: CSSStyleDeclaration,
  rect: DOMRect,
  local: (client: number) => number,
): Line[] {
  const glyphs: { top: number; bottom: number; pos: number }[] = [];
  const range = document.createRange();
  const walker = document.createTreeWalker(dom, NodeFilter.SHOW_TEXT, {
    acceptNode: (text) =>
      text.parentElement?.closest(`.${GAP}`) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  for (let text = walker.nextNode() as Text | null; text; text = walker.nextNode() as Text | null) {
    range.selectNodeContents(text);
    let fragment = 0;
    for (const box of range.getClientRects()) {
      if (box.height === 0) continue;
      const last = glyphs.at(-1);
      if (last && box.top < last.bottom - 1 && box.bottom > last.top + 1) {
        last.top = Math.min(last.top, box.top);
        last.bottom = Math.max(last.bottom, box.bottom);
      } else {
        const offset = fragment === 0 ? 0 : firstOnLine(text, box.top, range);
        glyphs.push({ top: box.top, bottom: box.bottom, pos: view.posAtDOM(text, offset) });
      }
      fragment++;
    }
  }
  if (glyphs.length < 2) return [];
  const contentTop = local(
    rect.top + parseFloat(style.borderTopWidth) + parseFloat(style.paddingTop),
  );
  const contentBottom = local(
    rect.bottom - parseFloat(style.borderBottomWidth) - parseFloat(style.paddingBottom),
  );
  const lines = glyphs.map((glyph) => ({
    top: local(glyph.top),
    bottom: local(glyph.bottom),
    pos: glyph.pos,
  }));
  return lines.map((line, at) => ({
    top: at === 0 ? contentTop : (lines[at - 1].bottom + line.top) / 2,
    bottom: at === lines.length - 1 ? contentBottom : (line.bottom + lines[at + 1].top) / 2,
    pos: line.pos,
  }));
}

/** The offset of the first character of `text` on the line at `top`. */
function firstOnLine(text: Text, top: number, range: Range): number {
  let low = 0;
  let high = text.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    range.setStart(text, middle);
    range.setEnd(text, middle + 1);
    const box = range.getClientRects()[0];
    if (box && box.top >= top - 0.5) high = middle;
    else low = middle + 1;
  }
  return low;
}

/** A table's rows, by its element: each row's client top and bottom, whether a merged cell above
 * reaches into it and whether it heads the table. */
export const tableRows = new WeakMap<HTMLElement, () => Row[]>();

function rowsOf(dom: HTMLElement, local: (client: number) => number): Row[] {
  const rows = tableRows.get(dom)?.() ?? [];
  return rows.map((row) => ({ ...row, top: local(row.top), bottom: local(row.bottom) }));
}

/** A PDF's pages as rows, each from where the one above ends, so that a page the paper's page
 * starts with loses the space it keeps above. */
function pdfPagesOf(dom: HTMLElement, local: (client: number) => number): Row[] {
  return [...dom.querySelectorAll<HTMLElement>(`.${PDF_PAGE}`)].map((page) => {
    const box = page.getBoundingClientRect();
    const above = parseFloat(getComputedStyle(page).marginTop) || 0;
    return { top: local(box.top) - above, bottom: local(box.bottom), joined: false, header: false };
  });
}

/** The page gaps each table or PDF at a position shows, before which of its rows or pages, and
 * how tall a table's header rows stand again at the end of each. */
export interface TableGaps {
  rows: { row: number; gap: number; header?: number }[];
}

/** A page gap; in a paragraph it ends its line after it, or a page starting on an empty line
 * would have the gap's line take that line's place. */
export function gapElement(kind: 'block' | 'line', gap: number): HTMLElement {
  const element = document.createElement(kind === 'block' ? 'div' : 'span');
  element.className = GAP;
  element.contentEditable = 'false';
  element.style.height = `${gap}px`;
  if (kind === 'block') return element;
  const line = document.createElement('span');
  line.contentEditable = 'false';
  line.append(element, document.createElement('br'));
  return line;
}

function decorationsOf(doc: Node, laid: Laid): DecorationSet {
  const decorations: Decoration[] = [];
  const tables = new Map<number, TableGaps['rows']>();
  for (const each of laid.breaks) {
    if (each.kind === 'note') continue;
    if (each.kind === 'row') {
      const rows = tables.get(each.pos) ?? [];
      rows.push({ row: each.row, gap: each.gap, ...(each.header ? { header: each.header } : {}) });
      tables.set(each.pos, rows);
      continue;
    }
    decorations.push(
      Decoration.widget(each.pos, () => gapElement(each.kind, each.gap), {
        side: -1,
        marks: [],
        ignoreSelection: true,
        key: `${each.kind} ${Math.round(each.gap * 64)}`,
      }),
    );
  }
  for (const [pos, rows] of tables) {
    const table = doc.nodeAt(pos);
    if (table) decorations.push(Decoration.node(pos, pos + table.nodeSize, {}, { rows }));
  }
  return DecorationSet.create(doc, decorations);
}

/** The page gaps a table's or a PDF's decorations ask for. */
export function tableGaps(decorations: readonly Decoration[]): TableGaps['rows'] {
  for (const decoration of decorations) {
    const rows = (decoration.spec as Partial<TableGaps>).rows;
    if (rows) return rows;
  }
  return [];
}

/** The tab on pages, each section's of its own geometry by its place among the sections, as laid
 * out; the page gaps, and each block of a section whose text stands in otherwise than the first's
 * set in by that. */
interface Paging {
  sheets: readonly Geometry[] | null;
  laid: Laid | null;
  gaps: DecorationSet;
  decorations: DecorationSet;
}

export const pagesKey = new PluginKey<Paging>('pages');

type Meta = { sheets: readonly Geometry[] | null } | { laid: Laid };

export function pagingOf(state: EditorState): Paging | undefined {
  return pagesKey.getState(state);
}

/** Lays the tab out on pages, those of each section of the geometry at its place in `sheets`, or
 * shows it as one column where null. */
export function showPages(view: EditorView, sheets: readonly Geometry[] | null): void {
  const now = pagingOf(view.state)?.sheets ?? null;
  if (now === sheets || (now && sheets && sameSheets(now, sheets))) return;
  view.dispatch(view.state.tr.setMeta(pagesKey, { sheets } satisfies Meta));
}

function sameSheets(a: readonly Geometry[], b: readonly Geometry[]): boolean {
  return (
    a.length === b.length &&
    a.every((sheet, at) =>
      (Object.keys(sheet) as (keyof Geometry)[]).every((key) => sheet[key] === b[at][key]),
    )
  );
}

/** Each block of a section whose text stands in otherwise than the first's, set in by that: a text
 * block's own indents added to it, as its margins hold them. */
function insetsOf(doc: Node, sheets: readonly Geometry[] | null): Decoration[] {
  if (!sheets || sheets.length < 2) return [];
  const found: Decoration[] = [];
  let section = 0;
  doc.forEach((node, pos) => {
    const [left, right] = insetOf(sheets, section);
    if (node.type.name === 'sectionBreak') section++;
    if (!left && !right) return;
    const style = [`--inset-left: ${left}px`, `--inset-right: ${right}px`];
    if (node.isTextblock) {
      const indent = Number(node.attrs.indent) || 0;
      const end = Number(node.attrs.right) || 0;
      style.push(
        `margin-left: calc(${left}px + ${indent}cm)`,
        `margin-right: calc(${right}px + ${end}cm)`,
      );
    }
    found.push(
      Decoration.node(pos, pos + node.nodeSize, { 'data-inset': '', style: style.join('; ') }),
    );
  });
  return found;
}

function shown(doc: Node, gaps: DecorationSet, sheets: readonly Geometry[] | null): DecorationSet {
  const insets = insetsOf(doc, sheets);
  return insets.length ? gaps.add(doc, insets) : gaps;
}

const paginators = new WeakMap<EditorView, Paginator>();

/** Lays the pages out again where what they measure changed while the text and its size did not,
 * as a table's header rows do. */
export function repaginate(view: EditorView): void {
  paginators.get(view)?.schedule();
}

class Paginator {
  private frame = 0;
  private observer: ResizeObserver | null = null;
  private fonts = () => this.schedule();

  constructor(private view: EditorView) {
    paginators.set(view, this);
  }

  update(view: EditorView, previous: EditorState): void {
    const now = pagingOf(view.state)!;
    const was = pagingOf(previous)!;
    if (now.sheets !== was.sheets) this.watch(Boolean(now.sheets));
    if (!now.sheets && was.sheets) placeNotes(view, null);
    if (view.state.doc !== previous.doc || now.sheets !== was.sheets) this.schedule();
  }

  /** Lays the pages out again when the text's width or fonts change, while there are pages. */
  private watch(on: boolean): void {
    if (on && !this.observer) {
      this.observer = new ResizeObserver(() => this.schedule());
      this.observer.observe(this.view.dom);
      document.fonts?.addEventListener('loadingdone', this.fonts);
    } else if (!on && this.observer) {
      this.observer.disconnect();
      this.observer = null;
      document.fonts?.removeEventListener('loadingdone', this.fonts);
    }
  }

  schedule(): void {
    if (!pagingOf(this.view.state)?.sheets) return;
    cancelAnimationFrame(this.frame);
    this.frame = requestAnimationFrame(() => this.lay());
  }

  private lay(): void {
    const view = this.view;
    if (view.isDestroyed) return;
    const { sheets, laid } = pagingOf(view.state)!;
    if (!sheets) return;
    const next = laidOut(measure(view), sheets);
    placeNotes(view, next, sheets);
    if (sameLaid(laid, next)) return;
    view.dispatch(
      view.state.tr.setMeta(pagesKey, { laid: next } satisfies Meta).setMeta('addToHistory', false),
    );
  }

  destroy(): void {
    cancelAnimationFrame(this.frame);
    this.watch(false);
  }
}

/** Shows only the blocks of the section at that place among the tab's, as its printed pages do. */
export function sectionShown(section: number): Plugin {
  return new Plugin({
    props: {
      decorations(state) {
        const hidden: Decoration[] = [];
        let at = 0;
        state.doc.forEach((node, pos) => {
          if (at !== section) {
            hidden.push(Decoration.node(pos, pos + node.nodeSize, { style: 'display: none' }));
          }
          if (node.type.name === 'sectionBreak') at++;
        });
        return DecorationSet.create(state.doc, hidden);
      },
    },
  });
}

export function pagesPlugin(): Plugin<Paging> {
  return new Plugin<Paging>({
    key: pagesKey,
    state: {
      init: () => ({
        sheets: null,
        laid: null,
        gaps: DecorationSet.empty,
        decorations: DecorationSet.empty,
      }),
      apply(tr, value) {
        const meta = tr.getMeta(pagesKey) as Meta | undefined;
        if (meta && 'sheets' in meta) {
          const gaps = DecorationSet.empty;
          return {
            sheets: meta.sheets,
            laid: null,
            gaps,
            decorations: shown(tr.doc, gaps, meta.sheets),
          };
        }
        if (meta && 'laid' in meta) {
          const gaps = decorationsOf(tr.doc, meta.laid);
          return {
            ...value,
            laid: meta.laid,
            gaps,
            decorations: shown(tr.doc, gaps, value.sheets),
          };
        }
        if (!tr.docChanged) return value;
        const gaps = value.gaps.map(tr.mapping, tr.doc);
        return { ...value, gaps, decorations: shown(tr.doc, gaps, value.sheets) };
      },
    },
    props: {
      decorations: (state) => pagingOf(state)?.decorations,
    },
    view: (view) => new Paginator(view),
  });
}
