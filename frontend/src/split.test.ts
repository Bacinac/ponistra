// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { clampWidth, storedWidth, type Column } from './split';

const LIST: Column = { name: 'list', initial: 448, min: 288, max: 768 };

describe('the width of a column', () => {
  beforeEach(() => localStorage.clear());

  it('stays within its bounds, in whole pixels', () => {
    expect([100, 300.6, 2000].map((width) => clampWidth(LIST, width))).toEqual([288, 301, 768]);
  });

  it('is the one its reader left it at, else its initial width', () => {
    expect(storedWidth(LIST)).toBe(448);
    localStorage.setItem('ponistra.width.list', '512');
    expect(storedWidth(LIST)).toBe(512);
  });

  it('comes back within its bounds when what the browser keeps is out of them or no number', () => {
    localStorage.setItem('ponistra.width.list', '5000');
    expect(storedWidth(LIST)).toBe(768);
    localStorage.setItem('ponistra.width.list', 'wide');
    expect(storedWidth(LIST)).toBe(448);
  });
});
