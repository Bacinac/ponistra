import type { Node } from 'prosemirror-model';
import { Plugin, PluginKey, type EditorState } from 'prosemirror-state';
import { Decoration, DecorationSet, type EditorView } from 'prosemirror-view';
import type * as Y from 'yjs';
import type { GridSource } from './grids';
import { numeral } from './numerals';
import { LEVELS, listOf, schema } from './schema';
import { kindOf, styleOf, type Style, type Styling } from './styling';
import { linesOf, OUTLINED, readingOrder, type LinesOf } from './tables';

const { heading } = schema.nodes;

/** Each counter where a tab starts. A heading level counts as `#<level>`, any other block under
 * its style's id. */
export type Counters = Record<string, number>;

/** What a tab does to each counter: sets it, where a heading above or a block numbered from 1
 * starts it again, or else counts on from where the tab found it. */
export type Tally = Record<string, { reset: boolean; count: number }>;

const levelKey = (level: number) => `#${level}`;

/** The style that numbers the block; a list item shows its list's number instead. */
export function numberedBy(node: Node, styling: Styling): Style | null {
  const kind = kindOf(node);
  if (!kind || listOf(node)) return null;
  const style = styling.styles[styleOf(node, styling) ?? kind];
  return style?.numbering ? style : null;
}

export interface Numbered {
  /** Each numbered block's number as it shows, by its offset in the tab. */
  labels: Map<number, string>;
  /** Every block counts, numbered or not, so the tabs after it number on rightly once its style
   * numbers. */
  tally: Tally;
}

/** Counts a tab's blocks in reading order from where the tab starts. A heading numbers on at its
 * level and starts the levels below it again; it shows the numbers of the headings above it when
 * its style nests them, each in the form of that heading's style. */
function counter(styling: Styling, start: Counters) {
  const tally: Tally = {};
  const above = new Map<number, Style | undefined>();
  const value = (key: string) => {
    const own = tally[key];
    return own?.reset ? own.count : (start[key] ?? 0) + (own?.count ?? 0);
  };
  const step = (key: string, restart: boolean) => {
    const own = tally[key];
    tally[key] = restart
      ? { reset: true, count: 1 }
      : { reset: own?.reset ?? false, count: (own?.count ?? 0) + 1 };
  };
  const block = (id: string, restart: boolean): string | null => {
    const style: Style | undefined = styling.styles[id];
    step(id, restart);
    if (!style?.numbering) return null;
    return `${style.prefix}${numeral(value(id), style.numbering)}${style.suffix}`;
  };
  const heading = (level: number, id: string, restart: boolean): string | null => {
    const style: Style | undefined = styling.styles[id];
    step(levelKey(level), restart);
    above.set(level, style);
    for (const below of LEVELS) {
      if (below <= level) continue;
      tally[levelKey(below)] = { reset: true, count: 0 };
      above.delete(below);
    }
    if (!style?.numbering) return null;
    const numerals = [];
    if (style.nested) {
      for (const higher of LEVELS) {
        const by = higher < level ? (above.get(higher) ?? styling.styles[`h${higher}`]) : null;
        if (by?.numbering) numerals.push(numeral(value(levelKey(higher)), by.numbering));
      }
    }
    numerals.push(numeral(value(levelKey(level)), style.numbering));
    return `${style.prefix}${numerals.join('.')}${style.suffix}`;
  };
  return { tally, block, heading };
}

export function numbered(doc: Node, styling: Styling, start: Counters, lines: LinesOf): Numbered {
  const labels = new Map<number, string>();
  const count = counter(styling, start);
  for (const { node, pos } of readingOrder(doc, lines)) {
    const kind = kindOf(node);
    if (!kind || listOf(node)) continue;
    const id = styleOf(node, styling) ?? kind;
    const restart = node.attrs.restart === true;
    const label =
      node.type === heading
        ? count.heading(node.attrs.level, id, restart)
        : count.block(id, restart);
    if (label) labels.set(pos, label);
  }
  return { labels, tally: count.tally };
}

/** The numbers of a tab's headings, from the tab's list of them, which another tab's contents
 * show without loading it. */
export function headingNumbers(
  headings: readonly { level: number; style: string | null; restart: boolean }[],
  styling: Styling,
  start: Counters,
): (string | null)[] {
  const count = counter(styling, start);
  return headings.map(({ level, style, restart }) => {
    const own = style && styling.styles[style]?.kind === `h${level}` ? style : `h${level}`;
    return count.heading(level, own, restart);
  });
}

/** Each tab's tally, kept by the editors of each tab so the tabs after it number on without
 * loading it. */
export function tallies(own: Y.Doc): Y.Map<Tally> {
  return own.getMap<Tally>('numbers');
}

function sameTally(a: Tally, b: Tally): boolean {
  const keys = Object.keys(a);
  return (
    keys.length === Object.keys(b).length &&
    keys.every((key) => a[key].reset === b[key]?.reset && a[key].count === b[key]?.count)
  );
}

export function writeTally(own: Y.Doc, tab: string, tally: Tally): void {
  const known = tallies(own).get(tab);
  if (known ? sameTally(known, tally) : !Object.keys(tally).length) return;
  own.transact(() => tallies(own).set(tab, tally));
}

const counted = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0;

/** Where the tab's counters start: on from the tabs before it, as their editors tallied them. */
export function startOf(own: Y.Doc, tabs: readonly string[], tab: string): Counters {
  const counters: Counters = {};
  for (const id of tabs) {
    if (id === tab) break;
    for (const [key, step] of Object.entries(tallies(own).get(id) ?? {})) {
      if (!counted(step?.count)) continue;
      counters[key] = step.reset === true ? step.count : (counters[key] ?? 0) + step.count;
    }
  }
  return counters;
}

interface Shown extends Numbered {
  styling: Styling;
  start: Counters;
  /** The same numbers by block, for a copy, which holds the blocks it takes whole. */
  byBlock: Map<Node, string>;
  decorations: DecorationSet;
}

const key = new PluginKey<Shown>('numbering');

function shown(doc: Node, styling: Styling, start: Counters, lines: LinesOf): Shown {
  const found = numbered(doc, styling, start, lines);
  const byBlock = new Map<Node, string>();
  const decorations: Decoration[] = [];
  for (const [pos, label] of found.labels) {
    const block = doc.nodeAt(pos)!;
    byBlock.set(block, label);
    decorations.push(Decoration.node(pos, pos + block.nodeSize, { 'data-number': label }));
  }
  return {
    ...found,
    styling,
    start,
    byBlock,
    decorations: DecorationSet.create(doc, decorations),
  };
}

/** Shows each numbered block's number before its text; the number is never part of the text. */
export function numberingPlugin(
  styling: Styling,
  start: Counters,
  grids: GridSource | null,
): Plugin<Shown> {
  const lines = linesOf(grids);
  return new Plugin<Shown>({
    key,
    state: {
      init: (_, state) => shown(state.doc, styling, start, lines),
      apply: (tr, before) => {
        const next: { styling: Styling; start: Counters } | undefined = tr.getMeta(key);
        if (next) return shown(tr.doc, next.styling, next.start, lines);
        return tr.docChanged || tr.getMeta(OUTLINED)
          ? shown(tr.doc, before.styling, before.start, lines)
          : before;
      },
    },
    props: {
      decorations: (state) => key.getState(state)!.decorations,
    },
  });
}

function sameCounters(a: Counters, b: Counters): boolean {
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((name) => a[name] === b[name]);
}

/** Numbers the tab again by the document's styles and from the tabs before it, when either moved. */
export function renumber(view: EditorView, styling: Styling, start: Counters): void {
  const now = key.getState(view.state);
  if (!now || (now.styling === styling && sameCounters(now.start, start))) return;
  view.dispatch(view.state.tr.setMeta(key, { styling, start }).setMeta('addToHistory', false));
}

export function numbersOf(state: EditorState): Numbered | null {
  return key.getState(state) ?? null;
}

export function numberIn(state: EditorState, block: Node): string | null {
  return key.getState(state)?.byBlock.get(block) ?? null;
}
