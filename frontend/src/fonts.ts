import registry from '../../fonts/fonts.json';

interface Family {
  name: string;
  generic: 'serif' | 'sans-serif' | 'monospace';
  licence: string;
  replaces?: string[];
  resembles?: string[];
}

export const FAMILIES: readonly Family[] = registry.families as Family[];
export const FONT_NAMES: readonly string[] = FAMILIES.map((family) => family.name);

/** The document's theme: a font pair every style draws on. */
export interface Theme {
  headings: string;
  text: string;
}

export const THEMES: readonly { id: string; theme: Theme }[] = [
  { id: 'ponistra', theme: { headings: 'Inter', text: 'Inter' } },
  { id: 'classic', theme: { headings: 'Source Serif 4', text: 'Source Serif 4' } },
  { id: 'plex', theme: { headings: 'IBM Plex Sans', text: 'IBM Plex Serif' } },
  { id: 'noto', theme: { headings: 'Noto Sans', text: 'Noto Serif' } },
  { id: 'office', theme: { headings: 'Caladea', text: 'Carlito' } },
];

const FACES = [
  { file: 'Regular', weight: 400, style: 'normal' },
  { file: 'Bold', weight: 700, style: 'normal' },
  { file: 'Italic', weight: 400, style: 'italic' },
  { file: 'BoldItalic', weight: 700, style: 'italic' },
] as const;

const FILES = import.meta.glob<string>('../../fonts/*/*.ttf', {
  query: '?url',
  import: 'default',
  eager: true,
});

function fileOf(family: Family, face: string): string {
  const stem = family.name.replaceAll(' ', '');
  const url = FILES[`../../fonts/${stem}/${stem}-${face}.ttf`];
  if (!url) throw new Error(`font file missing: ${stem}-${face}.ttf`);
  return url;
}

export function fontFaces(): string {
  return FAMILIES.flatMap((family) =>
    FACES.map(
      (face) =>
        `@font-face { font-family: "${family.name}"; src: url("${fileOf(family, face.file)}") format("truetype"); font-weight: ${face.weight}; font-style: ${face.style}; font-display: swap; }`,
    ),
  ).join('\n');
}

export function installFonts(): void {
  const sheet = document.createElement('style');
  sheet.textContent = fontFaces();
  document.head.append(sheet);
}

function familyNamed(name: string): Family | undefined {
  const wanted = name.trim().toLowerCase();
  const named = (names?: string[]) => names?.some((found) => found.toLowerCase() === wanted);
  return (
    FAMILIES.find((family) => family.name.toLowerCase() === wanted) ??
    FAMILIES.find((family) => named(family.replaces)) ??
    FAMILIES.find((family) => named(family.resembles))
  );
}

/** The font we show for a name a document carries: ours, the metric equal of an Office font,
 * or its look-alike; nothing for a font we have no stand-in for. */
export function substitute(name: string): string | null {
  return familyNamed(name)?.name ?? null;
}

/** The Office font one of ours stands for: its metric equal, else its look-alike. */
export function officeOf(family: Family): string | undefined {
  return (family.replaces ?? family.resembles)?.[0];
}

/** The CSS font stack of one of our fonts. Only names from the registry reach a stylesheet,
 * since a document's fonts are written by its other editors. */
export function fontStack(name: string): string | null {
  const family = FAMILIES.find((found) => found.name === name);
  return family ? `"${family.name}", ${family.generic}` : null;
}
