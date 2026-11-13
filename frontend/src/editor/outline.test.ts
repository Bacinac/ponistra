import { describe, expect, it } from 'vitest';
import { outlineOf } from './outline';
import { schema } from './schema';

const { doc, paragraph, heading, footnote } = schema.nodes;

const text = (words: string) => schema.text(words);

const written = doc.create(null, [
  paragraph.create({ id: 'p0' }, text('Uvodni odlomak')),
  heading.create({ id: 'h1', level: 1 }, [
    text('Ponuda '),
    footnote.create({ id: 'n1', kind: 'foot' }, text('Bilješka uz naslov')),
  ]),
  paragraph.create({ id: 'p1' }, text('Tekst')),
  heading.create({ id: 'h2', level: 2 }, text('Cijene')),
  heading.create({ id: 'h3', level: 2 }),
  paragraph.create({ id: 'p2' }, text('Tekst')),
]);

const start = (id: string) => {
  let at = -1;
  written.forEach((node, offset) => {
    if (node.attrs.id === id) at = offset;
  });
  return at;
};

const NONE = new Map<number, string>();
const NO_TABLES = () => null;

describe('outlineOf', () => {
  it('lists the headings that say something, by their own words and with their numbers', () => {
    expect(outlineOf(written, null, new Map([[start('h2'), '1.1.']]), NO_TABLES)).toEqual({
      headings: [
        { id: 'h1', level: 1, number: null, text: 'Ponuda' },
        { id: 'h2', level: 2, number: '1.1.', text: 'Cijene' },
      ],
      current: null,
    });
  });

  it('finds the section that holds the cursor', () => {
    expect(outlineOf(written, start('p0') + 1, NONE, NO_TABLES).current).toBeNull();
    expect(outlineOf(written, start('h1') + 1, NONE, NO_TABLES).current).toBe('h1');
    expect(outlineOf(written, start('p1') + 1, NONE, NO_TABLES).current).toBe('h1');
    expect(outlineOf(written, start('p2') + 1, NONE, NO_TABLES).current).toBe('h2');
  });
});
