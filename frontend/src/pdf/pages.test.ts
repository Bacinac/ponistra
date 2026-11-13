import { describe, expect, it } from 'vitest';
import {
  begun,
  done,
  entries,
  inserted,
  moved,
  redone,
  same,
  sheetsOf,
  span,
  stepped,
  turned,
  undone,
  without,
  type Sheet,
} from './pages';

let made = 0;
const key = () => `k${++made}`;
const pages = (sheets: Sheet[]) => sheets.map((sheet) => sheet.page);
const of = (sheets: Sheet[], ...numbers: number[]) =>
  new Set(sheets.filter((sheet) => numbers.includes(sheet.page)).map((sheet) => sheet.key));

describe('sheets', () => {
  const sheets = sheetsOf('a', 5, key);

  it('turn the chosen ones a quarter either way', () => {
    const once = turned(sheets, of(sheets, 2), 1);
    expect(once.map((sheet) => sheet.turn)).toEqual([0, 1, 0, 0, 0]);
    expect(turned(once, of(sheets, 2, 3), -1).map((sheet) => sheet.turn)).toEqual([0, 0, 3, 0, 0]);
  });

  it('go, move to a gap and step one place, gathered where they were apart', () => {
    expect(pages(without(sheets, of(sheets, 2, 4)))).toEqual([1, 3, 5]);
    expect(pages(moved(sheets, of(sheets, 4, 5), 0))).toEqual([4, 5, 1, 2, 3]);
    expect(pages(moved(sheets, of(sheets, 1, 2), 5))).toEqual([3, 4, 5, 1, 2]);
    expect(pages(moved(sheets, of(sheets, 1, 2), 4))).toEqual([3, 4, 1, 2, 5]);
    expect(pages(stepped(sheets, of(sheets, 3), -1))).toEqual([1, 3, 2, 4, 5]);
    expect(pages(stepped(sheets, of(sheets, 5), 1))).toEqual([1, 2, 3, 4, 5]);
    expect(pages(stepped(sheets, of(sheets, 1, 3), 1))).toEqual([2, 4, 1, 3, 5]);
    expect(pages(stepped(sheets, of(sheets, 1, 3), -1))).toEqual([1, 3, 2, 4, 5]);
    expect(pages(stepped(sheets, new Set(), 1))).toEqual([1, 2, 3, 4, 5]);
  });

  it('take pages of another file in at a place', () => {
    const added = sheetsOf('b', 2, key);
    const joined = inserted(sheets, added, 2);
    expect(joined.map((sheet) => `${sheet.file}${sheet.page}`)).toEqual([
      'a1',
      'a2',
      'b1',
      'b2',
      'a3',
      'a4',
      'a5',
    ]);
    expect(entries(turned(joined, of(added, 1), 1)).slice(1, 3)).toEqual([
      { file: 'a', page: 2 },
      { file: 'b', page: 1, turn: 1 },
    ]);
  });

  it('are the same as the file while every page stands as it came', () => {
    expect(same(sheets, sheetsOf('a', 5, key))).toBe(true);
    expect(same(sheets, turned(sheets, of(sheets, 1), 1))).toBe(false);
    expect(same(sheets, moved(sheets, of(sheets, 1), 2))).toBe(false);
  });
});

describe('span', () => {
  it('joins runs of pages', () => {
    const number = (value: number) => String(value);
    expect(span([2, 3, 4, 5, 7], number)).toBe('2–5, 7');
    expect(span([3, 1], number)).toBe('3, 1');
  });
});

describe('history', () => {
  it('takes back steps and makes them again until something new is done', () => {
    const first = sheetsOf('a', 2, key);
    const second = turned(first, new Set([first[0].key]), 1);
    const third = without(second, new Set([first[1].key]));
    let history = done(done(begun(first), second), third);
    history = undone(undone(history));
    expect(history.present).toBe(first);
    history = redone(history);
    expect(history.present).toBe(second);
    history = done(history, first);
    expect(history.future).toEqual([]);
    expect(undone(begun(first))).toEqual(begun(first));
  });
});
