import { describe, expect, it } from 'vitest';
import cases from '../../../schema/tables.cases.json';
import {
  apartOf,
  backgroundOf,
  gradientLine,
  Resolver,
  shadowOf,
  TableDesign,
  type Design,
  type Edges,
} from './design';
import type { Lines } from './tables';

describe('a table’s design', () => {
  it('draws each cell as the server’s resolver does', () => {
    for (const each of cases.cases) {
      const own = (each as { own?: Record<string, Edges> }).own ?? {};
      const resolver = new Resolver(
        each.design as Design,
        each.rows,
        each.cols,
        (row, col) => own[`${row}:${col}`],
      );
      const cells = Array.from({ length: each.rows }, (_, row) =>
        Array.from({ length: each.cols }, (_, col) => resolver.cell(row, col)),
      );
      expect(cells, JSON.stringify(each.design.name ?? each.design.rules)).toEqual(each.cells);
    }
  });

  it('lays designs over their areas and settles the edges between them as the server does', () => {
    for (const [at, each] of cases.laid.entries()) {
      const own = (each as unknown as { own?: Record<string, Edges> }).own ?? {};
      const lines = {
        rowCount: each.rows,
        cols: Array.from({ length: each.cols }, (_, col) => `c${col}`),
        rowIndex: (id: string) => Number(id.slice(1)),
        colIndex: (id: string) => Number(id.slice(1)),
      } as unknown as Lines;
      const table = new TableDesign(
        each.designs as Design[],
        lines,
        (row, col) => own[`${row}:${col}`],
      );
      const cells = Array.from({ length: each.rows }, (_, row) =>
        Array.from({ length: each.cols }, (_, col) => table.at(row, col)),
      );
      expect(cells, `laid ${at}`).toEqual(each.cells);
    }
  });

  it('runs a gradient at its angle clockwise from the right, corner to corner as CSS does', () => {
    const box = { x: 0, y: 0, width: 200, height: 100 };
    expect(gradientLine(0, box)).toEqual([0, 50, 200, 50]);
    const down = [100, 0, 100, 100];
    gradientLine(90, box).forEach((each, at) => expect(each).toBeCloseTo(down[at]));
    const [x0, y0, x1, y1] = gradientLine(45, box);
    expect(Math.hypot(x1 - x0, y1 - y0)).toBeCloseTo(150 * Math.SQRT2);
    expect(
      backgroundOf(
        {
          angle: 90,
          stops: [
            { at: 0, color: '#ffffff' },
            { at: 100, color: '#000000' },
          ],
        },
        true,
      ),
    ).toBe('linear-gradient(180deg, #ffffff 0%, #000000 100%)');
    expect(backgroundOf('none')).toBe('transparent');
  });

  it('casts its shadow by its distance at its angle', () => {
    expect(shadowOf({ color: '#00000066', blur: 4, distance: 3, angle: 90 }, true)).toBe(
      '0pt 3pt 4pt #00000066',
    );
    expect(shadowOf(undefined)).toBeNull();
  });

  it('sets Word’s cells apart by twice its spacing, round them too, its outer lines a frame', () => {
    const red = { line: 'single', width: 1.5, color: '#ff0000' } as const;
    const spaced: Design = { rules: 'word', spacing: 3.6, lines: { top: red, bottom: 'none' } };
    expect(apartOf(spaced, true)).toEqual({
      'border-collapse': 'separate',
      'border-spacing': '7.2pt',
      'border-top': '1.5pt solid #ff0000',
      'border-left': 'none',
      'border-bottom': 'none',
      'border-right': 'none',
    });
    expect(apartOf({ rules: 'word', lines: { top: red } })).toEqual({});
  });
});
