import { describe, expect, it } from 'vitest';
import { HIGHLIGHTS, swatchOf, TEXT_COLORS } from './colors';

function lightness(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16));
  return (Math.max(r, g, b) + Math.min(r, g, b)) / 2 / 255;
}

describe('swatchOf', () => {
  it('takes a palette colour by its name', () => {
    expect(swatchOf(TEXT_COLORS, 'blue')).toBe(TEXT_COLORS.blue);
    expect(swatchOf(HIGHLIGHTS, 'blue')).toBe(HIGHLIGHTS.blue);
  });

  it("keeps a file's own colour on paper and derives a shade the dark page reads", () => {
    const text = swatchOf(TEXT_COLORS, '#2f5496')!;
    expect(text.light).toBe('#2f5496');
    expect(lightness(text.dark)).toBeGreaterThan(0.6);
    const fill = swatchOf(HIGHLIGHTS, '#ffff00')!;
    expect(fill.light).toBe('#ffff00');
    expect(lightness(fill.dark)).toBeLessThan(0.35);
    expect(swatchOf(TEXT_COLORS, '#ffffff')).toEqual({ light: '#ffffff', dark: '#ffffff' });
    expect(swatchOf(HIGHLIGHTS, '#1f3864')).toEqual({ light: '#1f3864', dark: '#1f3864' });
  });

  it('takes nothing else', () => {
    expect(swatchOf(TEXT_COLORS, 'crimson')).toBeNull();
    expect(swatchOf(TEXT_COLORS, '#FFF')).toBeNull();
    expect(swatchOf(TEXT_COLORS, null)).toBeNull();
  });
});
