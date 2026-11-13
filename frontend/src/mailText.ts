import {
  DOMParser,
  DOMSerializer,
  Fragment,
  Schema,
  type Node,
  type NodeSpec,
} from 'prosemirror-model';
import { bulletList, listItem, orderedList } from 'prosemirror-schema-list';
import type { EditorState, Transaction } from 'prosemirror-state';
import { TEXT_COLORS, inPalette, named } from './editor/colors';
import { FAMILIES, officeOf } from './fonts';

/** The images mail carries as clients show them everywhere. */
export const MAIL_IMAGES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];

/** The fonts a recipient's computer has, each drawn here by the font of ours that stands for
 * it where this one lacks it. */
export const MAIL_FONTS = FAMILIES.flatMap((family) => {
  const office = officeOf(family);
  return office
    ? [{ name: office, stack: `"${office}", "${family.name}", ${family.generic}` }]
    : [];
});
export const MAIL_FONT = 'Arial';

export const MAIL_SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 36];
export const MAIL_SIZE = 11;

function fontOf(css: string): string | null {
  const first = css
    .split(',')[0]
    .trim()
    .replace(/^["']|["']$/g, '')
    .toLowerCase();
  const family = FAMILIES.find(({ name }) => name.toLowerCase() === first);
  const found = family && officeOf(family);
  return (
    MAIL_FONTS.find(({ name }) => name.toLowerCase() === (found ?? first).toLowerCase())?.name ??
    null
  );
}

/** The size in points nearest to the one written, which may be in pixels. */
function sizeOf(css: string): number | null {
  const found = /^([\d.]+)(pt|px)$/.exec(css.trim());
  if (!found) return null;
  const points = Number(found[1]) * (found[2] === 'px' ? 0.75 : 1);
  return MAIL_SIZES.reduce((best, size) =>
    Math.abs(size - points) < Math.abs(best - points) ? size : best,
  );
}

export const MAIL_SPACINGS = [1, 1.15, 1.5, 2];
export const MAIL_SPACING = 1.15;

/** The line spacing of those offered nearest to the one written; none where it is the usual. */
function spacingOf(css: string): number | null {
  const found = /^([\d.]+)(%)?$/.exec(css.trim());
  if (!found) return null;
  const wanted = Number(found[1]) / (found[2] ? 100 : 1);
  const spacing = MAIL_SPACINGS.reduce((best, each) =>
    Math.abs(each - wanted) < Math.abs(best - wanted) ? each : best,
  );
  return spacing === MAIL_SPACING ? null : spacing;
}

const IMAGE_SRC = /^\/api\/mail\/inline\/([0-9a-f]{64})$/;

export function mailImageUrl(blob: string): string {
  return `/api/mail/inline/${blob}`;
}

const nodes: Record<string, NodeSpec> = {
  doc: { content: 'block+' },
  paragraph: {
    content: 'inline*',
    group: 'block',
    attrs: { spacing: { default: null } },
    parseDOM: [
      { tag: 'p', getAttrs: (dom) => ({ spacing: spacingOf(dom.style.lineHeight) }) },
      {
        tag: 'div',
        priority: 10,
        getAttrs: (dom) => ({ spacing: spacingOf(dom.style.lineHeight) }),
      },
    ],
    toDOM: (node) =>
      node.attrs.spacing ? ['p', { style: `line-height: ${node.attrs.spacing}` }, 0] : ['p', 0],
  },
  /** The account's signature, which the composer puts in and swaps for another sender's. */
  signature: {
    content: '(paragraph | bullet_list | ordered_list | horizontal_rule)+',
    group: 'block',
    defining: true,
    parseDOM: [{ tag: 'div[data-signature]' }],
    toDOM: () => ['div', { 'data-signature': '' }, 0],
  },
  horizontal_rule: { group: 'block', parseDOM: [{ tag: 'hr' }], toDOM: () => ['hr'] },
  text: { group: 'inline' },
  image: {
    inline: true,
    group: 'inline',
    draggable: true,
    attrs: { blob: {}, alt: { default: '' } },
    parseDOM: [
      {
        tag: 'img[src]',
        getAttrs: (dom) => {
          const blob = IMAGE_SRC.exec(dom.getAttribute('src') ?? '')?.[1];
          return blob ? { blob, alt: dom.getAttribute('alt') ?? '' } : false;
        },
      },
    ],
    toDOM: (node) => ['img', { src: mailImageUrl(node.attrs.blob), alt: node.attrs.alt }],
  },
  hard_break: {
    inline: true,
    group: 'inline',
    selectable: false,
    parseDOM: [{ tag: 'br' }],
    toDOM: () => ['br'],
  },
  bullet_list: { ...bulletList, content: 'list_item+', group: 'block' },
  ordered_list: { ...orderedList, content: 'list_item+', group: 'block' },
  list_item: { ...listItem, content: 'paragraph (bullet_list | ordered_list)*' },
};

export const mailSchema = new Schema({
  nodes,
  marks: {
    link: {
      attrs: { href: {} },
      inclusive: false,
      parseDOM: [{ tag: 'a[href]', getAttrs: (dom) => ({ href: dom.getAttribute('href') }) }],
      toDOM: (mark) => ['a', { href: mark.attrs.href }, 0],
    },
    strong: {
      parseDOM: [
        { tag: 'strong' },
        { tag: 'b', getAttrs: (dom) => dom.style.fontWeight !== 'normal' && null },
        {
          style: 'font-weight',
          getAttrs: (value) => /^(bold(er)?|[6-9]\d{2,})$/.test(value) && null,
        },
      ],
      toDOM: () => ['strong', 0],
    },
    em: {
      parseDOM: [{ tag: 'i' }, { tag: 'em' }, { style: 'font-style=italic' }],
      toDOM: () => ['em', 0],
    },
    underline: {
      parseDOM: [{ tag: 'u' }, { style: 'text-decoration=underline' }],
      toDOM: () => ['u', 0],
    },
    strike: {
      parseDOM: [{ tag: 's' }, { tag: 'del' }, { style: 'text-decoration=line-through' }],
      toDOM: () => ['s', 0],
    },
    font: {
      attrs: { name: {} },
      parseDOM: [
        {
          style: 'font-family',
          getAttrs: (value) => {
            const name = fontOf(value);
            return name ? { name } : false;
          },
        },
      ],
      toDOM: (mark) => [
        'span',
        {
          style: `font-family: ${MAIL_FONTS.find(({ name }) => name === mark.attrs.name)?.stack}`,
        },
        0,
      ],
    },
    size: {
      attrs: { points: {} },
      parseDOM: [
        {
          style: 'font-size',
          getAttrs: (value) => {
            const points = sizeOf(value);
            return points ? { points } : false;
          },
        },
      ],
      toDOM: (mark) => ['span', { style: `font-size: ${mark.attrs.points}pt` }, 0],
    },
    color: {
      attrs: { name: {} },
      parseDOM: [
        {
          style: 'color',
          getAttrs: (value) => {
            const name = named(TEXT_COLORS, value);
            return name ? { name } : false;
          },
        },
      ],
      toDOM: (mark) => [
        'span',
        {
          style: inPalette(TEXT_COLORS, mark.attrs.name)
            ? `color: ${TEXT_COLORS[mark.attrs.name].light}`
            : '',
        },
        0,
      ],
    },
  },
});

const { paragraph, signature } = mailSchema.nodes;

function parsed(html: string): Fragment {
  const holder = document.createElement('div');
  holder.innerHTML = html;
  return DOMParser.fromSchema(mailSchema).parse(holder).content;
}

/** The HTML the message or signature is written as, which the server makes safe again. */
export function mailHtml(content: Node | Fragment): string {
  const holder = document.createElement('div');
  const fragment = content instanceof Fragment ? content : content.content;
  holder.append(DOMSerializer.fromSchema(mailSchema).serializeFragment(fragment));
  return holder.innerHTML;
}

/** A document of the HTML, as a signature is kept. */
export function mailDoc(html: string): Node {
  const content = parsed(html);
  return mailSchema.node('doc', null, content.size ? content : paragraph.create());
}

function signatureOf(html: string): Node | null {
  const content = parsed(html);
  let shown = false;
  content.descendants((node) => {
    shown ||= node.isText ? node.text!.trim() !== '' : node.type === mailSchema.nodes.image;
  });
  return shown ? signature.create(null, content) : null;
}

/** What the user starts writing: a line for each line of the text given, an empty line, then the
 * signature of the account it goes from. */
export function opening(text: string, signed: string): Node {
  const lines = text.replace(/\n+$/, '').split('\n');
  const written = lines.map((line) => paragraph.create(null, line ? mailSchema.text(line) : null));
  const sign = signatureOf(signed);
  return mailSchema.node('doc', null, sign ? [...written, paragraph.create(), sign] : written);
}

/** The signature of the account the message now goes from in place of the one before; where there
 * was none, at the end under an empty line. */
export function resign(state: EditorState, signed: string): Transaction {
  const sign = signatureOf(signed);
  const tr = state.tr;
  let at = -1;
  state.doc.forEach((node, pos) => {
    if (node.type === signature) at = pos;
  });
  if (at >= 0) {
    const end = at + state.doc.child(state.doc.resolve(at).index()).nodeSize;
    return sign ? tr.replaceWith(at, end, sign) : tr.delete(at, end);
  }
  if (!sign) return tr;
  return tr.insert(state.doc.content.size, [paragraph.create(), sign]);
}
