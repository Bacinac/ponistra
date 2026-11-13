import type { Numbering } from './styling';

const ROMAN: [number, string][] = [
  [1000, 'm'],
  [900, 'cm'],
  [500, 'd'],
  [400, 'cd'],
  [100, 'c'],
  [90, 'xc'],
  [50, 'l'],
  [40, 'xl'],
  [10, 'x'],
  [9, 'ix'],
  [5, 'v'],
  [4, 'iv'],
  [1, 'i'],
];

export function letters(count: number): string {
  let found = '';
  for (let rest = count; rest > 0; rest = Math.floor((rest - 1) / 26)) {
    found = String.fromCharCode(97 + ((rest - 1) % 26)) + found;
  }
  return found;
}

export function roman(count: number): string {
  let found = '';
  let rest = count;
  for (const [value, digits] of ROMAN) {
    for (; rest >= value; rest -= value) found += digits;
  }
  return found;
}

export function numeral(count: number, numbering: Numbering): string {
  if (count < 1 || numbering === '1') return String(count);
  if (numbering === 'a') return letters(count);
  if (numbering === 'A') return letters(count).toUpperCase();
  if (numbering === 'i') return roman(count);
  if (numbering === 'I') return roman(count).toUpperCase();
  return '';
}
