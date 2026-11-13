import type { Node } from 'prosemirror-model';
import type { Heading, Outline } from '../tabs';
import { schema } from './schema';
import { readingOrder, type LinesOf } from './tables';

// A heading's own words: a note in it has text of its own, which is not the heading's.
export function wordsOf(heading: Node): string {
  let words = '';
  heading.forEach((child) => {
    if (child.isText) words += child.text;
  });
  return words.trim();
}

/** The tab's headings that say something, each with its number, and the last of them at or
 * before `at`. */
export function outlineOf(
  doc: Node,
  at: number | null,
  numbers: ReadonlyMap<number, string>,
  lines: LinesOf,
): Outline {
  const headings: Heading[] = [];
  let current: string | null = null;
  for (const { node, pos } of readingOrder(doc, lines)) {
    const text = node.type === schema.nodes.heading && node.attrs.id ? wordsOf(node) : '';
    if (!text) continue;
    headings.push({
      id: node.attrs.id,
      level: node.attrs.level,
      number: numbers.get(pos) ?? null,
      text,
    });
    if (at !== null && pos <= at) current = node.attrs.id;
  }
  return { headings, current };
}
