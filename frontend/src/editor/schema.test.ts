// @vitest-environment jsdom
import { DOMParser as Parser, DOMSerializer } from 'prosemirror-model';
import { describe, expect, it } from 'vitest';
import spec from '../../../schema/schema.json';
import slides from '../../../schema/slides.json';
import { segment } from '../address';
import { blobOf, imageSpec, safeHref, schema, widthOf } from './schema';

const SHA = 'ab'.repeat(32);
const UUID = '6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b';
const NODE = segment('Ponuda za najam', UUID);
const ORIGIN = 'https://ponistra.example.org';
const IDENTIFIER = /^[A-Za-z_$][\w$]*$/;

/** The JSON's value as its own literal type, so TypeScript knows each list's values. */
function literal(value: unknown, depth = 0): string {
  if (Array.isArray(value))
    return `readonly [${value.map((each) => literal(each, depth)).join(', ')}]`;
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  const pad = '  '.repeat(depth + 1);
  const entries = Object.entries(value).map(([key, each]) => {
    const name = IDENTIFIER.test(key) ? key : JSON.stringify(key);
    return `${pad}readonly ${name}: ${literal(each, depth + 1)};`;
  });
  return entries.length ? `{\n${entries.join('\n')}\n${'  '.repeat(depth)}}` : '{}';
}

describe('the schema', () => {
  it('has its types declared as schema.json holds them', async () => {
    const declaration = [
      '// Derived from schema.json: `vitest run src/editor/schema.test.ts -u` writes it.',
      `declare const schema: ${literal(spec)};`,
      'export default schema;',
      '',
    ].join('\n');
    await expect(declaration).toMatchFileSnapshot('../../../schema/schema.d.json.ts');
  });

  it('has the slide template’s types declared as slides.json holds them', async () => {
    const declaration = [
      '// Derived from slides.json: `vitest run src/editor/schema.test.ts -u` writes it.',
      `declare const slides: ${literal(slides)};`,
      'export default slides;',
      '',
    ].join('\n');
    await expect(declaration).toMatchFileSnapshot('../../../schema/slides.d.json.ts');
  });

  it('builds its nodes and marks in the file’s order', () => {
    expect(Object.keys(schema.nodes)).toEqual(Object.keys(spec.nodes));
    expect(Object.keys(schema.marks)).toEqual(Object.keys(spec.marks));
    expect(schema.nodes.heading.spec.attrs?.level).toEqual({ default: 1 });
    expect(schema.nodes.paragraph.spec.attrs?.list).toEqual({ default: null });
    expect(schema.marks.link.spec.attrs?.href).toEqual({});
  });
});

describe('link addresses', () => {
  it('lead only to the web, mail, phone or a page of PONISTRA', () => {
    expect(safeHref(' https://example.com/a?b=1 ', ORIGIN)).toBe('https://example.com/a?b=1');
    expect(safeHref('mailto:ivo@example.com', ORIGIN)).toBe('mailto:ivo@example.com');
    expect(safeHref('tel:+38512345678', ORIGIN)).toBe('tel:+38512345678');
    expect(safeHref(`/d/${NODE}/${NODE}?block=Ab-_9`, ORIGIN)).toBe(
      `/d/${NODE}/${NODE}?block=Ab-_9`,
    );
    expect(safeHref(`${ORIGIN}/p/${NODE}?page=3`, ORIGIN)).toBe(`/p/${NODE}?page=3`);
    for (const refused of [
      'javascript:alert(1)',
      'data:text/html,<script>',
      'vbscript:x',
      'file:///etc/passwd',
      '/api/nodes',
      `/d/${UUID}`,
      '//evil.example/x',
      'Ponuda',
      42,
    ]) {
      expect(safeHref(refused, ORIGIN)).toBeNull();
    }
  });

  it('are dropped from a pasted link that leads anywhere else', () => {
    const html =
      '<p><a href="javascript:alert(1)">Klik</a> <a href="https://example.com">Web</a></p>';
    const element = document.createElement('div');
    element.innerHTML = html;
    const parsed = Parser.fromSchema(schema).parse(element);
    const links: string[] = [];
    parsed.descendants((node) => {
      const link = schema.marks.link.isInSet(node.marks);
      if (link) links.push(`${node.text}:${link.attrs.href}`);
    });
    expect(links).toEqual(['Web:https://example.com/']);
  });
});

describe('images', () => {
  it('know their own stored pictures by address', () => {
    expect(blobOf(`/api/images/${SHA}`, ORIGIN)).toBe(SHA);
    expect(blobOf(`${ORIGIN}/api/images/${SHA}`, ORIGIN)).toBe(SHA);
    expect(blobOf(`https://elsewhere.example/api/images/${SHA}`, ORIGIN)).toBeNull();
    expect(blobOf('https://example.com/slika.png', ORIGIN)).toBeNull();
  });

  it('keep a width within the column and their alignment', () => {
    expect([widthOf(50), widthOf('33.4'), widthOf(3), widthOf(120), widthOf('x')]).toEqual([
      50,
      33,
      null,
      null,
      null,
    ]);
    const image = schema.nodes.image.create({
      blob: SHA,
      alt: 'Shema',
      width: 40,
      align: 'center',
    });
    const dom = DOMSerializer.renderSpec(document, imageSpec(image)).dom as HTMLElement;
    expect(dom.outerHTML).toBe(
      `<figure data-image="" data-blob="${SHA}" data-align="center" data-width="40">` +
        `<img src="/api/images/${SHA}" alt="Shema" style="width: 40%;"></figure>`,
    );
    const element = document.createElement('div');
    element.append(dom);
    expect(Parser.fromSchema(schema).parse(element).firstChild!.attrs).toEqual({
      id: null,
      blob: SHA,
      alt: 'Shema',
      width: 40,
      align: 'center',
      insertion: null,
      deletion: null,
    });
    const hostile = schema.nodes.image.create({ blob: '../../x', alt: 'x' });
    expect(DOMSerializer.renderSpec(document, imageSpec(hostile)).dom.childNodes).toHaveLength(0);
  });
});
