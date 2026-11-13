import { describe, expect, it } from 'vitest';
import * as Y from 'yjs';
import { saveStyling, stylesheet, stylingOf, type Style } from './styling';

const TEXT: Style = {
  kind: 'text',
  name: '',
  font: 'text',
  size: 12,
  bold: false,
  italic: false,
  color: null,
  align: null,
  before: 0,
  after: 9,
  line: 1.6,
  numbering: '',
  prefix: '',
  suffix: '',
  nested: false,
  kerning: true,
};

function seeded(styles: Record<string, object>, theme = {}): Y.Doc {
  const doc = new Y.Doc();
  doc.transact(() => {
    for (const [role, font] of Object.entries(theme)) doc.getMap('theme').set(role, font);
    for (const [id, style] of Object.entries(styles)) {
      doc.getMap('styles').set(id, new Y.Map(Object.entries(style)));
    }
  });
  return doc;
}

function synced(from: Y.Doc, to: Y.Doc): void {
  Y.applyUpdate(to, Y.encodeStateAsUpdate(from, Y.encodeStateVector(to)));
}

describe('the styling a document carries', () => {
  it('lets only values it knows through, since its other editors write them', () => {
    const doc = seeded(
      {
        text: { ...TEXT, font: 'Comic Sans; } body { display: none', size: 9000, color: 'red;' },
        h1: { ...TEXT, kind: 'text' },
        'bad id!': { ...TEXT },
        note: { ...TEXT, name: 'Napomena', align: 'sideways', line: 'tall', bold: 'yes' },
      },
      { headings: 'Wingdings', text: 'IBM Plex Serif' },
    );
    const { theme, styles } = stylingOf(doc);
    expect(theme).toEqual({ headings: 'Inter', text: 'IBM Plex Serif' });
    expect(Object.keys(styles).sort()).toEqual(['note', 'text']);
    expect(styles.text).toMatchObject({ font: 'text', size: 400, color: null });
    expect(styles.note).toMatchObject({ align: null, line: 1.25, bold: false, name: 'Napomena' });
    expect(styles.text.kerning).toBe(true);
  });

  it("writes rules in which a block's own style wins over its kind's", () => {
    const sheet = stylesheet('s1', {
      theme: { headings: 'IBM Plex Sans', text: 'Noto Serif' },
      styles: {
        text: TEXT,
        note: {
          ...TEXT,
          name: 'Napomena',
          font: 'Liberation Mono',
          italic: true,
          color: 'gray',
          kerning: false,
        },
      },
    });
    expect(sheet).toContain('--font-headings: "IBM Plex Sans", sans-serif');
    expect(sheet).toContain('--font-text: "Noto Serif", serif');
    const builtIn = sheet.indexOf(':where(p:not([data-block]))');
    const own = sheet.indexOf(':where(p:not([data-block])[data-style="note"])');
    expect(builtIn).toBeGreaterThan(-1);
    expect(own).toBeGreaterThan(builtIn);
    expect(sheet.slice(own)).toMatch(
      /font-family: "Liberation Mono", monospace; .*font-style: italic.*font-kerning: none/,
    );
    expect(sheet.slice(builtIn, own)).toContain('font-kerning: normal');
  });

  it('saves field by field, so what another editor changed meanwhile stays', () => {
    const mine = seeded({ text: TEXT, h1: { ...TEXT, kind: 'h1', size: 21 }, old: { ...TEXT } });
    const theirs = new Y.Doc();
    synced(mine, theirs);
    const before = stylingOf(mine);

    theirs.getMap<Y.Map<unknown>>('styles').get('h1')!.set('size', 24);
    synced(theirs, mine);

    const { old: _gone, ...kept } = before.styles;
    saveStyling(mine, before, {
      theme: { ...before.theme, headings: 'Caladea' },
      styles: {
        ...kept,
        h1: { ...before.styles.h1, bold: true },
        note: { ...TEXT, name: 'Napomena' },
      },
    });
    synced(mine, theirs);

    const { theme, styles } = stylingOf(theirs);
    expect(theme.headings).toBe('Caladea');
    expect(styles.h1).toMatchObject({ size: 24, bold: true });
    expect(Object.keys(styles).sort()).toEqual(['h1', 'note', 'text']);
  });
});
