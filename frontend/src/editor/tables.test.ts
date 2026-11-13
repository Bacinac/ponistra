// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { WholeGrids, type Whole } from './grids';
import { schema } from './schema';
import {
  charactersOf,
  copiedTable,
  Layout,
  linesOf,
  NAME_LENGTH,
  nameProblem,
  SIDES,
  tableAttrsIn,
  tableCellsIn,
  tableElement,
  tableText,
  tableWidth,
  widened,
  widthsOf,
} from './tables';

const cols = ['a', 'b', 'c'];

function whole(table: string, name: string, extra: Partial<Whole> = {}): Whole {
  return {
    table,
    name,
    cols: cols.map((col) => [col, null]),
    rows: 2,
    at: {},
    ids: ['r1', 'r2'],
    heights: {},
    looks: {},
    hidden: {},
    merges: {},
    frozen: null,
    cells: {},
    ...extra,
  };
}

describe('a table’s name', () => {
  it('is one a workbook’s sheet could have, which no other table of the document has', () => {
    const grids = new WholeGrids({ grids: [whole('t1', 'Cijene'), whole('t2', 'BOM')], looks: {} });
    const problem = (name: string) => nameProblem(grids, 't1', name);
    expect(problem('Prices 2026')).toBeNull();
    expect(problem('Cijene')).toBeNull();
    expect(problem('x'.repeat(NAME_LENGTH))).toBeNull();
    expect(problem('bom')).toBe('taken');
    for (const invalid of [
      "'Prices",
      "Prices'",
      'a:b',
      'a/b',
      'ab\n',
      'x'.repeat(NAME_LENGTH + 1),
    ]) {
      expect(problem(invalid)).toBe('invalid');
    }
  });
});

describe('column widths', () => {
  it("of a sized table are its own characters, drawn with their cells' sides", () => {
    const widths = new Map([
      ['a', 10],
      ['b', 20],
    ]);
    expect(charactersOf(true, cols, widths, 999)).toEqual([10, 20, 15]);
    expect(tableWidth(true, cols, widths)).toBeCloseTo(45 + 3 * SIDES);
  });

  it("of a table on the page's width are their shares of it, without the sides", () => {
    const widths = new Map([
      ['a', 25],
      ['b', 25],
      ['c', 50],
    ]);
    expect(charactersOf(false, cols, widths, 80)).toEqual([20 - SIDES, 20 - SIDES, 40 - SIDES]);
    expect(tableWidth(false, cols, widths)).toBeNull();
  });

  it('leave a hidden column none of the width, and keep it its own for when it is shown', () => {
    const widths = new Map([
      ['a', 10],
      ['b', 20],
      ['c', 30],
    ]);
    const hidden = new Set(['b']);
    expect(widthsOf(false, cols, widths, hidden)).toEqual([25, 0, 75]);
    expect(tableWidth(true, cols, widths, hidden)).toBeCloseTo(40 + 2 * SIDES);
    expect(charactersOf(false, cols, widths, 80, hidden)).toEqual([20 - SIDES, 20, 60 - SIDES]);
  });

  it('change only the column dragged, as in Excel, never below two characters', () => {
    expect(widened([10, 20, 15], 1, 32)).toEqual([10, 32, 15]);
    expect(widened([10, 20, 15], 0, -4)).toEqual([2, 20, 15]);
  });
});

describe('going from cell to cell', () => {
  it('passes over the hidden rows and columns', () => {
    const grids = new WholeGrids({
      grids: [
        whole('t', 'Skriveno', {
          ids: ['r1', 'r3'],
          numbers: { r1: 0, r3: 2 },
          hidden: { cols: ['a', 'c'] },
        }),
      ],
      looks: {},
    });
    const layout = new Layout(grids.grid('t')!, schema.nodes.table.create({ id: 't' }));
    const key = (placed: { key: string } | null) => placed?.key ?? null;
    expect(key(layout.first())).toBe('r1:b');
    expect(key(layout.neighbour(layout.placed('r1:b')!, 'down'))).toBe('r3:b');
    expect(key(layout.neighbour(layout.placed('r3:b')!, 'up'))).toBe('r1:b');
    expect(key(layout.neighbour(layout.placed('r1:b')!, 'right'))).toBe('r3:b');
    expect(key(layout.last())).toBe('r3:b');
  });
});

describe('a copied table', () => {
  const cell = (row: string, col: string, text: string) =>
    schema.nodes.cell.create({ row, col }, schema.nodes.paragraph.create(null, schema.text(text)));

  it('keeps a sized table its widths and its rows their heights', () => {
    const grid = { rows: ['r1', 'r2'], cols, widths: { a: 10, b: 20, c: 15 }, heights: { r2: 30 } };
    const copied = schema.nodes.table.create({ sized: true, grid }, [cell('r1', 'a', 'x')]);
    const element = tableElement(copied, () => document.createTextNode(''));
    expect([...element.querySelectorAll('col')].map((col) => col.style.width)).toEqual([
      '67.5pt',
      '135pt',
      '101.25pt',
    ]);
    expect([...element.rows].map((row) => row.style.height)).toEqual(['', '30pt']);
    const attrs = tableAttrsIn(element);
    expect(attrs.sized).toBe(true);
    expect(Object.values(attrs.grid.widths)).toEqual([10, 20, 15]);
    expect(attrs.grid.heights).toEqual({ [attrs.grid.rows[1]]: 30 });
  });

  it('keeps each cell its fill, and one from another program by its background', () => {
    const filled = (col: string, fill: string | null) =>
      schema.nodes.cell.create({ row: 'r1', col, fill }, schema.nodes.paragraph.create());
    const grid = { rows: ['r1'], cols, widths: {}, heights: {} };
    const copied = schema.nodes.table.create({ grid }, [
      filled('a', 'yellow'),
      filled('b', '#d9e2f3'),
      filled('c', null),
    ]);
    const element = tableElement(copied, () => document.createTextNode(''));
    const fills = (from: HTMLElement) => {
      const found: unknown[] = [];
      tableCellsIn(from, schema).forEach((cell) => found.push(cell.attrs.fill));
      return found;
    };
    expect(fills(element)).toEqual(['yellow', '#d9e2f3', null]);
    const foreign = document.createElement('table');
    foreign.innerHTML =
      '<tr><td style="background-color: rgb(255, 255, 0)">a</td><td bgcolor="#FDE68A">b</td>' +
      '<td style="background: #ffffff">c</td></tr>';
    expect(fills(foreign)).toEqual(['#ffff00', 'yellow', null]);
  });

  it("from another program shares the page's width and keeps its rows' heights", () => {
    const element = document.createElement('table');
    element.innerHTML =
      '<colgroup><col style="width: 100pt"><col style="width: 300pt"></colgroup>' +
      '<tr style="height: 20pt"><td>a</td><td>b</td></tr>';
    const attrs = tableAttrsIn(element);
    expect(attrs.sized).toBe(false);
    expect(Object.values(attrs.grid.widths)).toEqual([100, 300]);
    expect(Object.values(attrs.grid.heights)).toEqual([20]);
  });

  it('carries each cell as it shows, with what computes it and the grid it came from', () => {
    const grids = new WholeGrids({
      grids: [
        whole('t', 'BOM', {
          cols: [
            ['a', 10],
            ['b', null],
            ['c', null],
          ],
          merges: { 'r2:a': 'r2:b' },
          cells: {
            r1: {
              cells: {
                a: { text: 'Stavka' },
                b: { text: '2', format: '0.00' },
                c: { text: "'007" },
              },
              values: { b: { kind: 'number', text: '2,00' }, c: { kind: 'text', text: '007' } },
            },
            r2: {
              cells: { a: { formula: 'B1*2', to: 'r2:b' } },
              values: { a: { kind: 'number', text: '4' } },
            },
          },
        }),
      ],
      looks: {},
    });
    const grid = grids.grid('t')!;
    const bold = schema.text('Napomena', [schema.marks.strong.create()]);
    const source = schema.nodes.table.create({ id: 't', sized: true }, [
      schema.nodes.cell.create({ row: 'r2', col: 'c' }, schema.nodes.paragraph.create(null, bold)),
    ]);
    const layout = new Layout(grid, source);
    const copy = copiedTable(source, layout, grid, { top: 0, left: 0, bottom: 1, right: 2 });
    expect(copy.attrs.id).toBeNull();
    expect(copy.attrs.grid).toEqual({
      rows: ['r1', 'r2'],
      cols,
      widths: { a: 10 },
      heights: {},
      merges: { 'r2:a': 'r2:b' },
      name: 'BOM',
      from: 't',
    });
    expect(copy.attrs.copied).toEqual({
      origin: { row: 0, col: 0 },
      formulas: { 'r2:a': 'B1*2' },
      formats: { 'r1:b': '0.00' },
      typed: { 'r1:b': '2' },
    });
    expect(tableText(copy)).toBe('Stavka\t2,00\t007\n4\t\tNapomena');
    const kept = linesOf(null)(copy)!;
    expect(new Layout(kept, copy).at(1, 1)!.key).toBe('r2:a');
    expect(copy.lastChild!.firstChild!.firstChild!.marks.map((mark) => mark.type.name)).toEqual([
      'strong',
    ]);
  });
});
