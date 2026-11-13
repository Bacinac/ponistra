import { describe, expect, it, vi } from 'vitest';
import { dropPlace, outlineStore, tabDepths, tabMoves } from './tabs';
import type { Tab } from './tree';

function tab(id: string, parent: string | null = null): Tab {
  return { id, parent, title: '', position: 0 };
}

// a
//   a1
//   a2
// b
// c
//   c1
const tabs = [tab('a'), tab('a1', 'a'), tab('a2', 'a'), tab('b'), tab('c'), tab('c1', 'c')];
const byId = (id: string) => tabs.find((each) => each.id === id)!;

describe('tabDepths', () => {
  it('indents each subtab one level below its parent', () => {
    const depths = tabDepths([tab('a'), tab('b', 'a'), tab('c', 'b'), tab('d')]);
    expect([...depths.values()]).toEqual([0, 1, 2, 0]);
  });
});

describe('tabMoves', () => {
  it('moves along the row, under the tab above and out after the parent', () => {
    expect(tabMoves(tabs, byId('b'))).toEqual({
      up: { parent: null, position: 0 },
      down: { parent: null, position: 2 },
      indent: { parent: 'a', position: 2 },
      outdent: null,
    });
    expect(tabMoves(tabs, byId('a2'))).toEqual({
      up: { parent: 'a', position: 0 },
      down: null,
      indent: { parent: 'a1', position: 0 },
      outdent: { parent: null, position: 1 },
    });
  });

  it('has nowhere to go from the first tab of a row but down', () => {
    expect(tabMoves(tabs, byId('a'))).toEqual({
      up: null,
      down: { parent: null, position: 1 },
      indent: null,
      outdent: null,
    });
  });
});

describe('dropPlace', () => {
  it('drops before a tab, after it, or as its last subtab', () => {
    expect(dropPlace(tabs, 'b', byId('a'), 'before')).toEqual({
      parent: null,
      position: 0,
    });
    expect(dropPlace(tabs, 'a', byId('b'), 'after')).toEqual({
      parent: null,
      position: 1,
    });
    expect(dropPlace(tabs, 'b', byId('a'), 'inside')).toEqual({
      parent: 'a',
      position: 2,
    });
  });

  it('drops after a tab with other subtabs as its first', () => {
    expect(dropPlace(tabs, 'b', byId('c'), 'after')).toEqual({
      parent: 'c',
      position: 0,
    });
    expect(dropPlace(tabs, 'c1', byId('c'), 'after')).toEqual({
      parent: null,
      position: 3,
    });
    expect(dropPlace(tabs, 'a2', byId('a'), 'after')).toEqual({
      parent: 'a',
      position: 0,
    });
  });

  it('refuses a drop on the tab itself, below it, or where it already is', () => {
    expect(dropPlace(tabs, 'a', byId('a'), 'inside')).toBeNull();
    expect(dropPlace(tabs, 'a', byId('a1'), 'before')).toBeNull();
    expect(dropPlace(tabs, 'b', byId('c'), 'before')).toBeNull();
    expect(dropPlace(tabs, 'a2', byId('a1'), 'after')).toBeNull();
  });
});

describe('outlineStore', () => {
  it('tells its readers only of a change they would see', () => {
    const store = outlineStore();
    const told = vi.fn();
    store.subscribe(told);
    const heading = { id: 'h', level: 1, number: null, text: 'Uvod' };
    store.set({ headings: [heading], current: null });
    store.set({ headings: [{ ...heading }], current: null });
    expect(told).toHaveBeenCalledTimes(1);
    store.set({ headings: [heading], current: 'h' });
    store.set({ headings: [{ ...heading, number: '1.' }], current: 'h' });
    store.set(null);
    expect(told).toHaveBeenCalledTimes(4);
    expect(store.get()).toBeNull();
  });
});
