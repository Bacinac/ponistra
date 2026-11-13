import palette from '../../../colors/colors.json';

export interface Swatch {
  light: string;
  dark: string;
}

export const TEXT_COLORS = palette.text satisfies Record<string, Swatch>;

export const HIGHLIGHTS = palette.highlight satisfies Record<string, Swatch>;

/** Chart series in this order: adjacent hues stay apart for colour-blind readers on both themes. */
export const CHART_COLORS = palette.chart satisfies Swatch[];

export type TextColor = keyof typeof TEXT_COLORS;
export type Highlight = keyof typeof HIGHLIGHTS;
export type Palette = typeof TEXT_COLORS | typeof HIGHLIGHTS;

/** The swatch as the page shows it: dark where the page is dark, light on paper. */
export function onScreen({ light, dark }: Swatch): string {
  return `light-dark(${light}, ${dark})`;
}

export function inPalette<P extends Palette>(palette: P, name: unknown): name is keyof P & string {
  return typeof name === 'string' && Object.hasOwn(palette, name);
}

const EXACT = /^#[0-9a-f]{6}$/;

/** A colour as a mark or a style carries it: a palette's by its name, or an imported file's own
 * as #rrggbb, whose dark shade is derived as the palette's are drawn: text as light as theirs, a
 * highlight or a fill as deep. */
export function swatchOf(palette: Palette, value: unknown): Swatch | null {
  if (inPalette(palette, value)) return palette[value];
  if (typeof value !== 'string' || !EXACT.test(value)) return null;
  return { light: value, dark: palette === HIGHLIGHTS ? deepened(value) : lightened(value) };
}

function lightened(hex: string): string {
  const [l, a, b] = oklab(hex);
  return l >= 0.72 ? hex : hexOf([Math.min(0.88, Math.max(0.72, 1.24 - l)), a, b]);
}

function deepened(hex: string): string {
  const [l, a, b] = oklab(hex);
  return l <= 0.45 ? hex : hexOf([Math.max(0.28, 1.32 - l), a * 0.8, b * 0.8]);
}

function oklab(hex: string): [number, number, number] {
  const [r, g, b] = [1, 3, 5].map((at) => {
    const channel = parseInt(hex.slice(at, at + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function hexOf([lightness, a, b]: [number, number, number]): string {
  const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const linear = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  return `#${linear
    .map((channel) => {
      const clipped = Math.min(1, Math.max(0, channel));
      const gamma = clipped <= 0.0031308 ? clipped * 12.92 : 1.055 * clipped ** (1 / 2.4) - 0.055;
      return Math.round(gamma * 255)
        .toString(16)
        .padStart(2, '0');
    })
    .join('')}`;
}

/** The palette name of a colour written out as its paper value, as PONISTRA copies it. */
export function named(palette: Palette, css: string): string | null {
  const probe = document.createElement('span');
  probe.style.color = css;
  const wanted = probe.style.color;
  for (const [name, { light }] of Object.entries(palette)) {
    probe.style.color = light;
    if (probe.style.color === wanted) return name;
  }
  return null;
}
