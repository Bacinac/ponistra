import { describe, expect, it, vi } from 'vitest';
import { KeptGrids, type KeptOutlines } from './grids';

const outlines: KeptOutlines = {
  grids: [
    {
      table: 't',
      name: '',
      cols: [['a', null]],
      rows: 3,
      heights: {},
      looks: {},
      hidden: {},
      merges: {},
      frozen: null,
      at: { r0: 0, r2: 2 },
    } as never,
  ],
  looks: {},
};

async function settled(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve));
}

describe('KeptGrids', () => {
  it('reads the rows a view shows and lets go of the rest', async () => {
    const read = vi.fn((path: string) =>
      Promise.resolve(
        path.includes('spans=0-1')
          ? {
              at: { r0: 0, r1: 1 },
              rows: {
                r0: { cells: { a: { text: 'x' } }, values: {} },
                r1: { cells: {}, values: {} },
              },
              looks: {},
            }
          : { at: { r2: 2 }, rows: { r2: { cells: {}, values: {} } }, looks: {} },
      ),
    );
    const grids = new KeptGrids(outlines, read);
    const told = vi.fn();
    grids.subscribe('t', told);
    const owner = {};
    grids.show(owner, 't', [[0, 1]]);
    await settled();
    const grid = grids.grid('t')!;
    expect(read).toHaveBeenCalledOnce();
    expect(read.mock.calls[0]![0]).toBe('rows?table=t&spans=0-1');
    expect([...grid.held.keys()]).toEqual(['r0', 'r1']);
    expect(grid.rowId(1)).toBe('r1');
    expect(told).toHaveBeenCalled();

    grids.show(owner, 't', [[2, 2]]);
    await settled();
    expect([...grid.held.keys()]).toEqual(['r2']);

    grids.forget(owner);
    await settled();
    expect(grid.held.size).toBe(0);
    expect(read).toHaveBeenCalledTimes(2);
  });

  it('asks the version where rows it does not hold stand', async () => {
    const read = vi.fn((path: string) =>
      Promise.resolve(
        path.startsWith('standing?table=t&places')
          ? { places: { 1: 'r1' }, rows: {}, numbered: {} }
          : { places: {}, rows: {}, numbered: { 7: 6 } },
      ),
    );
    const grids = new KeptGrids(outlines, read);
    await expect(grids.rowIds('t', [1])).resolves.toEqual(['r1']);
    await expect(grids.numberedPlaces('t', [7, 9])).resolves.toEqual([6, -1]);
  });
});
