import * as Y from 'yjs';
import { shortId } from './blocks';
import { numeral } from './numerals';
import { INDENT_MAX, INDENT_STEP } from './schema';
import { AFFIX_MAX, NUMBERINGS, type Numbering } from './styling';

/** How a list shows the items at one of its levels: a number in a form, between words, or a
 * bullet, which is the words alone. */
export interface ListLevel {
  numbering: Numbering;
  prefix: string;
  suffix: string;
  /** The number leads with the numbers of the items above it, as 1.2. */
  nested: boolean;
}

export type Marked = 'bullet' | 'number';

export const LIST_LEVELS = INDENT_MAX / INDENT_STEP + 1;

/** A list's look at each of its levels, kept once in the document and named by its items. */
export type ListFormat = readonly ListLevel[];
export type ListFormats = ReadonlyMap<string, ListFormat>;

const NUMBERS: Numbering[] = ['1', 'a', 'i'];
const BULLETS = ['•', '◦', '▪'];

/** A list without a format of its own: 1. a. i. or • ◦ ▪, and so again further in. */
export function standard(kind: Marked, level: number): ListLevel {
  return kind === 'number'
    ? { numbering: NUMBERS[level % 3], prefix: '', suffix: '.', nested: false }
    : { numbering: '', prefix: BULLETS[level % 3], suffix: '', nested: false };
}

export function kindOfLevel(level: ListLevel): Marked {
  return level.numbering ? 'number' : 'bullet';
}

/** The level as an item of the kind shows it: in the format's form where that is of its kind. */
export function levelIn(format: ListFormat | undefined, kind: Marked, level: number): ListLevel {
  const own = format?.[level];
  return own && kindOfLevel(own) === kind ? own : standard(kind, level);
}

export function sameLevel(a: ListLevel, b: ListLevel): boolean {
  return (
    a.numbering === b.numbering &&
    a.prefix === b.prefix &&
    a.suffix === b.suffix &&
    a.nested === b.nested
  );
}

function levelFrom(value: unknown): ListLevel | null {
  if (!value || typeof value !== 'object') return null;
  const { numbering, prefix, suffix, nested } = value as Record<string, unknown>;
  const form = NUMBERINGS.find((found) => found === numbering);
  if (form === undefined || typeof prefix !== 'string' || typeof suffix !== 'string') return null;
  if (prefix.length > AFFIX_MAX || suffix.length > AFFIX_MAX || !(form || prefix)) return null;
  return { numbering: form, prefix, suffix: form ? suffix : '', nested: !!form && nested === true };
}

/** A format as another editor or a copy brought it, where every level is one we can show. */
export function formatFrom(value: unknown): ListFormat | null {
  if (!Array.isArray(value) || value.length !== LIST_LEVELS) return null;
  const levels = value.map(levelFrom);
  return levels.every((level): level is ListLevel => level !== null) ? levels : null;
}

/** Whether the format shows every level as a list without one does. */
export function isStandard(format: ListFormat): boolean {
  return format.every((level, at) => sameLevel(level, standard(kindOfLevel(level), at)));
}

function listsOf(own: Y.Doc): Y.Map<unknown> {
  return own.getMap('lists');
}

export function formatsOf(own: Y.Doc): ListFormats {
  const found = new Map<string, ListFormat>();
  listsOf(own).forEach((value, id) => {
    const format = formatFrom(value);
    if (format) found.set(id, format);
  });
  return found;
}

export interface ListStore {
  get(): ListFormats;
  subscribe(changed: () => void): () => void;
  /** The format's id, kept in the document unless it has one alike; none where it is standard. */
  keep(format: ListFormat): string | null;
}

export function listStore(own: Y.Doc): ListStore {
  const lists = listsOf(own);
  return {
    get: () => formatsOf(own),
    subscribe(changed) {
      const observer = () => changed();
      lists.observe(observer);
      return () => lists.unobserve(observer);
    },
    keep(format) {
      if (isStandard(format)) return null;
      for (const [id, known] of formatsOf(own)) {
        if (known.every((level, at) => sameLevel(level, format[at]))) return id;
      }
      const id = shortId();
      own.transact(() =>
        lists.set(
          id,
          format.map((level) => ({ ...level })),
        ),
      );
      return id;
    },
  };
}

/** The formats of a saved version, which nothing writes to. */
export function savedLists(formats: ListFormats): ListStore {
  return {
    get: () => formats,
    subscribe: () => () => {},
    keep: () => {
      throw new Error('A saved version keeps no list formats.');
    },
  };
}

export function formatOf(formats: ListFormats, id: unknown): ListFormat | undefined {
  return typeof id === 'string' ? formats.get(id) : undefined;
}

/** The format with the level in its new form, from the one the list has. */
export function reformed(format: ListFormat | undefined, level: number, form: ListLevel) {
  const levels = Array.from(
    { length: LIST_LEVELS },
    (_, at) => format?.[at] ?? standard(kindOfLevel(form), at),
  );
  levels[level] = form;
  return levels;
}

const number = (numbering: Numbering, prefix: string, suffix: string, nested = false) => ({
  numbering,
  prefix,
  suffix,
  nested,
});
const bullet = (symbol: string) => number('', symbol, '');

/** The forms a level is given from the toolbar, as Word's numbering and bullet libraries. */
export const FORMS: Record<Marked, Record<string, ListLevel>> = {
  number: {
    decimal: number('1', '', '.'),
    decimalParen: number('1', '', ')'),
    decimalEnclosed: number('1', '(', ')'),
    letter: number('a', '', '.'),
    letterParen: number('a', '', ')'),
    letterEnclosed: number('a', '(', ')'),
    upperLetter: number('A', '', '.'),
    roman: number('i', '', '.'),
    upperRoman: number('I', '', '.'),
    nested: number('1', '', '.', true),
  },
  bullet: {
    bullet: bullet('•'),
    circle: bullet('◦'),
    square: bullet('▪'),
    dash: bullet('–'),
    arrow: bullet('➢'),
    diamond: bullet('◆'),
  },
};

/** The form as its first item shows it, a nested one under a first item. */
export function sample(form: ListLevel): string {
  if (!form.numbering) return form.prefix;
  return `${form.prefix}${form.nested ? '1.' : ''}${numeral(1, form.numbering)}${form.suffix}`;
}
