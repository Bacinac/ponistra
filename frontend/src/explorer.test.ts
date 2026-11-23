import { describe, expect, it } from 'vitest';
import { between, formatSize } from './explorer';
describe('between', () => {
  it('takes the range in either direction', () => {
    expect(between(['a', 'b', 'c', 'd'], 'c', 'a')).toEqual(['a', 'b', 'c']);
  });

  it('falls back to the clicked item when the anchor is gone', () => {
    expect(between(['a', 'b'], 'x', 'b')).toEqual(['b']);
  });
});

describe('formatSize', () => {
  const format = (value: number) => new Intl.NumberFormat('hr-HR').format(value);

  it('steps through the units with one decimal', () => {
    expect(formatSize(512, format)).toBe('512 B');
    expect(formatSize(1_234_567, format)).toBe('1,2 MB');
  });
});
