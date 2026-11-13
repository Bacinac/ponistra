import type { Attrs, Node, NodeType } from 'prosemirror-model';
import { useMemo, useSyncExternalStore } from 'react';
import * as Y from 'yjs';
import { FONT_NAMES, fontStack, type Theme } from '../fonts';
import type { MessageKey } from '../i18n/hr';
import { onScreen, swatchOf, TEXT_COLORS } from './colors';
import { ALIGNMENTS, LEVELS, schema, type Alignment } from './schema';

/** The built-in styles, one per kind of block; each is the style with its kind as id. */
export const KINDS = ['text', 'title', 'subtitle', 'h1', 'h2', 'h3', 'h4'] as const;
export type Kind = (typeof KINDS)[number];

export const KIND_LABELS: Record<Kind, MessageKey> = {
  text: 'command.paragraph',
  title: 'command.title',
  subtitle: 'command.subtitle',
  h1: 'command.heading1',
  h2: 'command.heading2',
  h3: 'command.heading3',
  h4: 'command.heading4',
};

/** How a style numbers its blocks: not at all, or in digits, letters or Roman numerals. */
export const NUMBERINGS = ['', '1', 'a', 'A', 'i', 'I'] as const;
export type Numbering = (typeof NUMBERINGS)[number];

export const AFFIX_MAX = 40;

export interface Style {
  kind: Kind;
  name: string;
  /** "headings" or "text" for the theme's font, else one of ours. */
  font: string;
  size: number;
  bold: boolean;
  italic: boolean;
  /** A palette's name or a file's own colour (`swatchOf`). */
  color: string | null;
  align: Alignment | null;
  before: number;
  after: number;
  line: number;
  numbering: Numbering;
  /** The words before and after the number, as "Članak " and ".". */
  prefix: string;
  suffix: string;
  /** A heading's number leads with the numbers of the headings above it, as 1.2. */
  nested: boolean;
  kerning: boolean;
}

export interface Styling {
  theme: Theme;
  styles: Record<string, Style>;
}

export const THEME_FONTS = ['headings', 'text'] as const;

const ID = /^[A-Za-z0-9_-]{1,32}$/;

function themeOf(doc: Y.Doc): Y.Map<string> {
  return doc.getMap('theme');
}

function stylesOf(doc: Y.Doc): Y.Map<Y.Map<unknown>> {
  return doc.getMap('styles');
}

function number(value: unknown, min: number, max: number, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.min(max, Math.max(min, value))
    : fallback;
}

function font(value: unknown, fallback: string): string {
  return typeof value === 'string' && FONT_NAMES.includes(value) ? value : fallback;
}

function affix(value: unknown): string {
  return typeof value === 'string' ? value.slice(0, AFFIX_MAX) : '';
}

function styleFrom(id: string, data: Record<string, unknown>): Style | null {
  const kind = KINDS.find((found) => found === data.kind);
  if (!kind || !ID.test(id) || ((KINDS as readonly string[]).includes(id) && id !== kind)) {
    return null;
  }
  return {
    kind,
    name: typeof data.name === 'string' ? data.name : '',
    font: (THEME_FONTS as readonly unknown[]).includes(data.font)
      ? (data.font as string)
      : font(data.font, 'text'),
    size: number(data.size, 1, 400, 12),
    bold: data.bold === true,
    italic: data.italic === true,
    color: swatchOf(TEXT_COLORS, data.color) ? (data.color as string) : null,
    align: ALIGNMENTS.find((found) => found === data.align) ?? null,
    before: number(data.before, 0, 400, 0),
    after: number(data.after, 0, 400, 0),
    line: number(data.line, 0.5, 5, 1.25),
    numbering: NUMBERINGS.find((found) => found === data.numbering) ?? '',
    prefix: affix(data.prefix),
    suffix: affix(data.suffix),
    nested: data.nested === true,
    kerning: data.kerning !== false,
  };
}

/** The document's theme and styles. Its other editors write them, so only values we know reach
 * a stylesheet. */
export function stylingOf(doc: Y.Doc): Styling {
  const theme = themeOf(doc);
  const styles: Record<string, Style> = {};
  for (const [id, data] of Object.entries(stylesOf(doc).toJSON())) {
    const style = styleFrom(id, data);
    if (style) styles[id] = style;
  }
  return {
    theme: {
      headings: font(theme.get('headings'), FONT_NAMES[0]),
      text: font(theme.get('text'), FONT_NAMES[0]),
    },
    styles,
  };
}

/** The document's own styles, beside the built-in ones, by name. */
export function ownStyles(styling: Styling): [string, Style][] {
  return Object.entries(styling.styles)
    .filter(([id, style]) => id !== style.kind)
    .sort(([, a], [, b]) => a.name.localeCompare(b.name));
}

export function useStyling(doc: Y.Doc): Styling {
  const store = useMemo(() => {
    let current = stylingOf(doc);
    return {
      subscribe(changed: () => void) {
        const refresh = () => {
          current = stylingOf(doc);
          changed();
        };
        themeOf(doc).observe(refresh);
        stylesOf(doc).observeDeep(refresh);
        return () => {
          themeOf(doc).unobserve(refresh);
          stylesOf(doc).unobserveDeep(refresh);
        };
      },
      snapshot: () => current,
    };
  }, [doc]);
  return useSyncExternalStore(store.subscribe, store.snapshot);
}

/** Writes what changed from `before` to `after`, field by field, so another editor's change to
 * the same style in the meantime survives. */
export function saveStyling(doc: Y.Doc, before: Styling, after: Styling): void {
  doc.transact(() => {
    const theme = themeOf(doc);
    for (const role of THEME_FONTS) {
      if (after.theme[role] !== before.theme[role]) theme.set(role, after.theme[role]);
    }
    const styles = stylesOf(doc);
    for (const id of Object.keys(before.styles)) {
      if (!(id in after.styles)) styles.delete(id);
    }
    for (const [id, style] of Object.entries(after.styles)) {
      const was = before.styles[id];
      const stored = styles.get(id);
      if (!was || !stored) {
        styles.set(id, new Y.Map(Object.entries(style)));
        continue;
      }
      for (const [field, value] of Object.entries(style)) {
        if (was[field as keyof Style] !== value) stored.set(field, value);
      }
    }
  });
}

const { paragraph, title, subtitle, heading } = schema.nodes;

export function kindOf(node: Node): Kind | null {
  if (node.type === paragraph) return 'text';
  if (node.type === title) return 'title';
  if (node.type === subtitle) return 'subtitle';
  if (node.type === heading) return `h${node.attrs.level as (typeof LEVELS)[number]}`;
  return null;
}

export function blockOf(kind: Kind): { type: NodeType; attrs: Attrs } {
  if (kind === 'text') return { type: paragraph, attrs: {} };
  if (kind === 'title' || kind === 'subtitle') return { type: schema.nodes[kind], attrs: {} };
  return { type: heading, attrs: { level: Number(kind.slice(1)) } };
}

/** The id of the block's own style, or null where it shows its kind's built-in one. */
export function styleOf(node: Node, styling: Styling): string | null {
  const id: string | null = node.attrs.style;
  return id && styling.styles[id]?.kind === kindOf(node) ? id : null;
}

const SELECTORS: Record<Kind, string> = {
  text: 'p:not([data-block])',
  title: 'p[data-block="title"]',
  subtitle: 'p[data-block="subtitle"]',
  h1: 'h1',
  h2: 'h2',
  h3: 'h3',
  h4: 'h4',
};

function declarations(style: Style): string {
  const family =
    style.font === 'headings' || style.font === 'text'
      ? `var(--font-${style.font})`
      : fontStack(style.font);
  return [
    `font-family: ${family}`,
    `font-size: ${style.size}pt`,
    `font-weight: ${style.bold ? 700 : 400}`,
    `font-style: ${style.italic ? 'italic' : 'normal'}`,
    `line-height: ${style.line}`,
    `margin-top: ${style.before}pt`,
    `margin-bottom: ${style.after}pt`,
    `color: ${style.color ? onScreen(swatchOf(TEXT_COLORS, style.color)!) : 'inherit'}`,
    `text-align: ${style.align ?? 'start'}`,
    `font-kerning: ${style.kerning ? 'normal' : 'none'}`,
  ].join('; ');
}

/** The rules that give each block its style inside `[data-styling=<scope>]`. All weigh the same,
 * so a block's own style, written after the built-ins, wins over its kind's. */
export function stylesheet(scope: string, { theme, styles }: Styling): string {
  const root = `[data-styling="${scope}"]`;
  // A cell's text reads the same drawn as in its editor.
  const text = `${root} :is(.ProseMirror, .ponistra-cell, .ponistra-part)`;
  const builtIn = KINDS.filter((kind) => styles[kind]).map(
    (kind) => `${text} > :where(${SELECTORS[kind]}) { ${declarations(styles[kind])} }`,
  );
  const own = Object.entries(styles)
    .filter(([id, style]) => id !== style.kind)
    .map(
      ([id, style]) =>
        `${text} > :where(${SELECTORS[style.kind]}[data-style="${id}"]) { ${declarations(style)} }`,
    );
  // A value a table computed reads as the text it stands in for.
  const values = styles.text
    ? [`${root} :where(.ponistra-cell-value) { ${declarations(styles.text)} }`]
    : [];
  return [
    `${root} { --font-headings: ${fontStack(theme.headings)}; --font-text: ${fontStack(theme.text)}; font-family: var(--font-text); }`,
    ...builtIn,
    ...own,
    ...values,
    `${text} > :first-child { margin-top: 0; }`,
  ].join('\n');
}
