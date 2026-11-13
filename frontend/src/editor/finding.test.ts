import { describe, expect, it } from 'vitest';
import { firstFrom, hitPlace, spanOf } from './finding';
import { schema } from './schema';

const doc = schema.node('doc', null, [
  schema.node('paragraph', { id: 'p1' }, [
    schema.text('😀 čaj'),
    schema.node('field', { kind: 'page' }),
    schema.text('čaj'),
  ]),
  schema.node('paragraph', { id: 'p2' }, schema.text('Kraj čaja')),
]);

describe('find', () => {
  it('spans the characters the server counts, in code points past what is not text', () => {
    expect(spanOf(doc, 0, 2, 5)).toEqual([4, 7]);
    expect(doc.textBetween(4, 7)).toBe('čaj');
    expect(spanOf(doc, 0, 5, 8)).toEqual([8, 11]);
    expect(doc.textBetween(8, 11)).toBe('čaj');
    expect(spanOf(doc, 0, 0, 1)).toEqual([1, 3]);
    expect(spanOf(doc, 0, 7, 9)).toBeNull();
    expect(spanOf(doc, 0, 3, 3)).toBeNull();
  });

  it('starts at the first hit from the cursor, else the first of all', () => {
    const hits = [
      { block: 'p1', from: 2, to: 5 },
      { block: 'p1', from: 5, to: 8 },
      { block: 'p2', from: 5, to: 8 },
    ];
    expect(firstFrom(doc, hits, 0)).toBe(0);
    expect(firstFrom(doc, hits, 6)).toBe(1);
    expect(firstFrom(doc, hits, 13)).toBe(2);
    expect(firstFrom(doc, hits, doc.content.size)).toBe(0);
  });

  it('replaces a hit where it starts, or a cell holding a text wholly', () => {
    expect(hitPlace({ block: 'p1', from: 2, to: 5 })).toEqual({ block: 'p1', from: 2 });
    expect(hitPlace({ table: 't', row: 'r1', col: 'a' })).toEqual({
      table: 't',
      row: 'r1',
      col: 'a',
    });
    expect(hitPlace({ table: 't', row: 'r2', col: 'a', block: 'c1', from: 7, to: 10 })).toEqual({
      block: 'c1',
      from: 7,
    });
  });
});
