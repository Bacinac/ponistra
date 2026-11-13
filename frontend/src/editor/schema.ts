import {
  Schema,
  type AttributeSpec,
  type Attrs,
  type DOMOutputSpec,
  type Mark,
  type MarkSpec,
  type Node,
  type NodeSpec,
} from 'prosemirror-model';
import spec from '../../../schema/schema.json';
import { HIGHLIGHTS, named, onScreen, swatchOf, TEXT_COLORS, type Palette } from './colors';
import { SEGMENT } from '../address';
import { fontStack, substitute } from '../fonts';
import { endMarksAttr, endMarksOf, marksFrom } from './ends';
import { changeOf } from './proposals';
import { tableAttrsIn, tableCellsIn } from './tables';

const DEFS = spec.$defs;

export const LEVELS = DEFS.level.enum;
export type Level = (typeof LEVELS)[number];

export const ALIGNMENTS = DEFS.align.enum;
export type Alignment = (typeof ALIGNMENTS)[number];

/** One indent step, as Word steps a paragraph in. */
export const INDENT_STEP = DEFS.indent.step;
export const INDENT_MAX = DEFS.indent.maximum;

export const LISTS = DEFS.list.enum;
export type ListKind = (typeof LISTS)[number];

/** How deep the contents list headings by default, as Word's do. */
export const CONTENTS_DEPTH = spec.nodes.contents.attrs.depth.default;

export const NOTES = DEFS.note.enum;

export const TAB_KINDS = DEFS.tabKind.enum;
export type TabKind = (typeof TAB_KINDS)[number];
export const LEADERS = DEFS.leader.enum;
export type Leader = (typeof LEADERS)[number];

/** A tab stop, in cm from the text's left edge, where Word measures it from the margin. */
export interface TabStop {
  at: number;
  kind: TabKind;
  leader?: Leader;
}

const STOP_MAX = DEFS.tabStop.properties.at.maximum;
/** How close two stops may stand, in cm, before they are one. */
export const STOP_NEAR = 0.05;

/** A paragraph's tab stops as its attribute holds them, each checked, as they come from every
 * editor's Yjs updates. */
export function stopsOf(value: unknown): TabStop[] {
  if (!Array.isArray(value)) return [];
  const stops: TabStop[] = [];
  for (const each of value as Partial<Record<keyof TabStop, unknown>>[]) {
    const at = Math.round(Number(each?.at) * 100) / 100;
    const kind = TAB_KINDS.find((known) => known === each?.kind);
    const leader = LEADERS.find((known) => known === each?.leader);
    if (!kind || !(at >= 0 && at <= STOP_MAX)) continue;
    if (stops.some((stop) => Math.abs(stop.at - at) < STOP_NEAR)) continue;
    stops.push({ at, kind, ...(leader && { leader }) });
  }
  return stops.sort((a, b) => a.at - b.at);
}

function stopsIn(element: HTMLElement): TabStop[] | null {
  try {
    const stops = stopsOf(JSON.parse(element.dataset.tabs ?? 'null'));
    return stops.length ? stops : null;
  } catch {
    return null;
  }
}

/** Values a page fills in where a field stands in its header or footer. */
export const FIELDS = DEFS.field.enum;
export type FieldKind = (typeof FIELDS)[number];

function fieldOf(value: string | undefined): FieldKind {
  return FIELDS.find((kind) => kind === value) ?? 'page';
}
export type NoteKind = (typeof NOTES)[number];

export const CHART_KINDS = DEFS.chartKind.enum;
export type ChartKind = (typeof CHART_KINDS)[number];
/** The kinds whose series can stack. */
export const STACKING: readonly ChartKind[] = DEFS.stacking.enum;
export const CHART_TITLE_LENGTH = DEFS.chartTitle.maxLength;

/** The cells a chart is drawn over: its table's id and the ids of the first and last row and
 * column, as a formula keeps a range (D4). */
export interface ChartRange {
  table: string;
  from: { row: string; col: string };
  to: { row: string; col: string };
}

/** What a chart's attributes say, each checked, as they come from every editor's Yjs updates. */
export interface Chart {
  range: ChartRange | null;
  kind: ChartKind;
  stacked: boolean;
  by: 'rows' | 'cols';
  names: boolean | null;
  labels: boolean | null;
  title: string;
  legend: boolean;
}

const SHA256 = new RegExp(spec.nodes.image.attrs.blob.schema.pattern);
const IMAGE_SRC = /^\/api\/images\/([0-9a-f]{64})$/;
const INTERNAL = new RegExp(`^/(?:d|p|f)/${SEGMENT}(?:/${SEGMENT})?(?:\\?[\\w%=&.-]*)?$`);
const SCHEMES = ['http:', 'https:', 'mailto:', 'tel:'];

const STYLE_ID = new RegExp(spec.attrSets.textblock.style.schema.pattern);
const ID = new RegExp(spec.$defs.id.pattern);

function alignOf(element: HTMLElement): Alignment | null {
  const align = element.style.textAlign;
  return align === 'center' || align === 'right' || align === 'justify' ? align : null;
}

function indentOf(element: HTMLElement): number | null {
  const indent = Number(element.dataset.indent);
  return indent > 0 ? Math.min(indent, INDENT_MAX) : null;
}

function lengthOf(value: unknown, least: number): number | null {
  const length = Number(value);
  return Number.isFinite(length) && length ? Math.min(Math.max(length, least), INDENT_MAX) : null;
}

function endMarksIn(element: HTMLElement): Attrs | null {
  try {
    return endMarksAttr(marksFrom(schema, JSON.parse(element.dataset.endMarks ?? 'null')));
  } catch {
    return null;
  }
}

function parsed(element: HTMLElement, attrs: Attrs = {}): Attrs {
  const style = element.dataset.style;
  return {
    ...attrs,
    align: alignOf(element),
    indent: indentOf(element),
    firstLine: lengthOf(element.dataset.firstLine, -INDENT_MAX),
    right: lengthOf(element.dataset.right, 0),
    tabs: stopsIn(element),
    style: style && STYLE_ID.test(style) ? style : null,
    restart: element.dataset.restart === 'true',
    endMarks: endMarksIn(element),
  };
}

// Attributes come from every editor's Yjs updates, so only known values reach the page.
function laidOut(node: Node, attrs: Record<string, string> = {}): Record<string, string> {
  const align = ALIGNMENTS.find((found) => found === node.attrs.align);
  const indent = Number(node.attrs.indent) || 0;
  const first = lengthOf(node.attrs.firstLine, -INDENT_MAX);
  const right = lengthOf(node.attrs.right, 0);
  const stops = stopsOf(node.attrs.tabs);
  const style = typeof node.attrs.style === 'string' && STYLE_ID.test(node.attrs.style);
  const rules = [
    align && `text-align: ${align}`,
    indent && `margin-left: ${indent}cm`,
    first && `text-indent: ${first}cm`,
    right && `margin-right: ${right}cm`,
  ].filter(Boolean);
  const ends = endMarksAttr(endMarksOf(node));
  return {
    ...attrs,
    ...(ends ? { 'data-end-marks': JSON.stringify(ends) } : {}),
    ...(style ? { 'data-style': node.attrs.style } : {}),
    ...(node.attrs.restart === true ? { 'data-restart': 'true' } : {}),
    ...(indent ? { 'data-indent': String(indent) } : {}),
    ...(first ? { 'data-first-line': String(first) } : {}),
    ...(right ? { 'data-right': String(right) } : {}),
    ...(stops.length ? { 'data-tabs': JSON.stringify(stops) } : {}),
    ...(rules.length ? { style: rules.join('; ') } : {}),
  };
}

type Drawn = Pick<NodeSpec, 'parseDOM' | 'toDOM'>;
type MarkDrawn = Pick<MarkSpec, 'parseDOM' | 'toDOM'>;

function textblock(
  tags: { tag: string; attrs?: Attrs }[],
  render: (node: Node) => [string, Record<string, string>?],
  own: (element: HTMLElement) => Attrs = () => ({}),
): Drawn {
  return {
    parseDOM: tags.map(({ tag, attrs }) => ({
      tag,
      priority: tag.includes('[') || tag.includes('.') ? 60 : 50,
      getAttrs: (element: HTMLElement) => parsed(element, { ...attrs, ...own(element) }),
    })),
    toDOM: (node: Node): DOMOutputSpec => {
      const [tag, attrs] = render(node);
      return [tag, laidOut(node, attrs), 0];
    },
  };
}

export function noteKind(node: Node): NoteKind {
  return node.attrs.kind === 'end' ? 'end' : 'foot';
}

export function listOf(node: Node): ListKind | null {
  return LISTS.find((kind) => kind === node.attrs.list) ?? null;
}

/** How deep in its list an item is, from its indent. */
export function levelOf(node: Node): number {
  const steps = Math.round((Number(node.attrs.indent) || 0) / INDENT_STEP);
  return Math.min(Math.max(steps, 0), INDENT_MAX / INDENT_STEP);
}

function listParsed(element: HTMLElement): Attrs {
  const list = LISTS.find((kind) => kind === element.dataset.list) ?? null;
  return {
    speaker: element.dataset.speaker === 'true',
    list,
    checked: list === 'check' && element.dataset.checked === 'true',
    continued: list === 'number' && element.dataset.continued === 'true',
    format: list === 'bullet' || list === 'number' ? (element.dataset.format ?? null) : null,
  };
}

function slideParsed(element: HTMLElement): Attrs {
  const layout = element.dataset.layout;
  return {
    layout: layout && ID.test(layout) ? layout : null,
    hidden: element.dataset.hidden === 'true',
  };
}

function slideShown(node: Node): Record<string, string> {
  const { layout, hidden } = node.attrs;
  return {
    ...(typeof layout === 'string' && ID.test(layout) ? { 'data-layout': layout } : {}),
    ...(hidden === true ? { 'data-hidden': 'true' } : {}),
  };
}

function listed(node: Node): Record<string, string> {
  const speaker: Record<string, string> =
    node.attrs.speaker === true ? { 'data-speaker': 'true' } : {};
  const list = listOf(node);
  if (!list) return speaker;
  return {
    ...speaker,
    'data-list': list,
    ...(list === 'check' && node.attrs.checked === true ? { 'data-checked': 'true' } : {}),
    ...(list === 'number' && node.attrs.continued === true ? { 'data-continued': 'true' } : {}),
    ...(list !== 'check' && node.attrs.format ? { 'data-format': node.attrs.format } : {}),
  };
}

/** The address a link may lead to: the web, mail and phone, or a page of PONISTRA itself, which
 * stays a path also when it arrives as this server's full address. */
export function safeHref(value: unknown, origin = globalThis.location?.origin): string | null {
  if (typeof value !== 'string') return null;
  const href = value.trim();
  if (INTERNAL.test(href)) return href;
  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return null;
  }
  const path = url.pathname + url.search;
  if (url.origin === origin && INTERNAL.test(path)) return path;
  return SCHEMES.includes(url.protocol) ? url.href : null;
}

export function isInternal(href: string): boolean {
  return href.startsWith('/');
}

export function imageUrl(blob: string): string {
  return `/api/images/${blob}`;
}

/** The stored image an address shows, when it is one of PONISTRA's own. */
export function blobOf(src: string | null, origin = globalThis.location?.origin): string | null {
  if (!src) return null;
  let url: URL;
  try {
    url = new URL(src, origin);
  } catch {
    return null;
  }
  return url.origin === origin ? (IMAGE_SRC.exec(url.pathname)?.[1] ?? null) : null;
}

function blobAttr(node: Node): string | null {
  return typeof node.attrs.blob === 'string' && SHA256.test(node.attrs.blob)
    ? node.attrs.blob
    : null;
}

/** Of the column, in per cent. */
function depthOf(value: string | undefined): Level {
  const depth = Number(value);
  return LEVELS.find((level) => level === depth) ?? CONTENTS_DEPTH;
}

export function widthOf(value: unknown): number | null {
  const width = Math.round(Number(value));
  return width >= 5 && width <= 100 ? width : null;
}

function imageParsed(img: HTMLImageElement | null, holder: HTMLElement): Attrs | false {
  if (!img) return false;
  const pending = holder.dataset.imageId ?? img.dataset.imageId;
  const blob = holder.dataset.blob ?? blobOf(img.getAttribute('src'));
  if (!blob && !pending) return false;
  const align = holder.dataset.align;
  return {
    id: pending ?? null,
    blob: blob && SHA256.test(blob) ? blob : null,
    alt: img.getAttribute('alt') ?? '',
    width: widthOf(holder.dataset.width ?? img.style.width.replace(/%$/, '')),
    align: align === 'center' || align === 'right' ? align : null,
  };
}

export function imageSpec(node: Node, src = imageUrl): DOMOutputSpec {
  const blob = blobAttr(node);
  const width = widthOf(node.attrs.width);
  const align = node.attrs.align === 'center' || node.attrs.align === 'right';
  const attrs = {
    'data-image': '',
    ...(blob ? { 'data-blob': blob } : {}),
    ...(align ? { 'data-align': node.attrs.align } : {}),
    ...(width ? { 'data-width': String(width) } : {}),
  };
  if (!blob) return ['figure', attrs];
  const img = { src: src(blob), alt: String(node.attrs.alt ?? '') };
  return ['figure', attrs, ['img', width ? { ...img, style: `width: ${width}%` } : img]];
}

export function pdfUrl(blob: string): string {
  return `/api/pdfs/${blob}`;
}

/** A page of a PDF, counted from 1. */
export function pageOf(value: unknown): number | null {
  const page = Number(value);
  return value != null && value !== '' && Number.isInteger(page) && page >= 1 ? page : null;
}

function pdfParsed(holder: HTMLElement): Attrs | false {
  const pending = holder.dataset.pdfId;
  const blob = holder.dataset.blob;
  const known = blob && SHA256.test(blob) ? blob : null;
  if (!known && !pending) return false;
  const align = holder.dataset.align;
  return {
    id: pending ?? null,
    blob: known,
    title: (holder.dataset.title ?? '').slice(0, spec.nodes.pdf.attrs.title.schema.maxLength),
    first: pageOf(holder.dataset.first),
    last: pageOf(holder.dataset.last),
    width: widthOf(holder.dataset.width),
    align: align === 'center' || align === 'right' ? align : null,
  };
}

export function pdfSpec(node: Node): DOMOutputSpec {
  const blob = blobAttr(node);
  const width = widthOf(node.attrs.width);
  const first = pageOf(node.attrs.first);
  const last = pageOf(node.attrs.last);
  const align = node.attrs.align === 'center' || node.attrs.align === 'right';
  return [
    'figure',
    {
      'data-pdf': '',
      ...(blob ? { 'data-blob': blob } : {}),
      ...(node.attrs.title ? { 'data-title': String(node.attrs.title) } : {}),
      ...(first ? { 'data-first': String(first) } : {}),
      ...(last ? { 'data-last': String(last) } : {}),
      ...(align ? { 'data-align': node.attrs.align } : {}),
      ...(width ? { 'data-width': String(width) } : {}),
    },
  ];
}

function paint(
  palette: Palette,
  tag: string,
  property: 'color' | 'background-color',
  dataset: string,
): MarkDrawn {
  const key = `data-${dataset}`;
  return {
    parseDOM: [
      {
        tag: `${tag}[${key}]`,
        getAttrs: (element: HTMLElement) => {
          const name = element.getAttribute(key);
          return swatchOf(palette, name) ? { color: name } : false;
        },
      },
      {
        style: property,
        getAttrs: (value: string) => {
          const name = named(palette, value);
          return name ? { color: name } : false;
        },
      },
    ],
    toDOM: (mark: Mark): DOMOutputSpec => {
      const name: string = mark.attrs.color;
      const swatch = swatchOf(palette, name);
      if (!swatch) return [tag, 0];
      return [tag, { [key]: name, style: `${property}: ${onScreen(swatch)}` }, 0];
    },
  };
}

function point(value: unknown): { row: string; col: string } | null {
  if (typeof value !== 'object' || value === null) return null;
  const { row, col } = value as Record<string, unknown>;
  return typeof row === 'string' && typeof col === 'string' ? { row, col } : null;
}

export function chartRangeOf(value: unknown): ChartRange | null {
  if (typeof value !== 'object' || value === null) return null;
  const range = value as Record<string, unknown>;
  const from = point(range.from);
  const to = point(range.to ?? range.from);
  return typeof range.table === 'string' && from && to ? { table: range.table, from, to } : null;
}

function flag(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

export function chartOf(attrs: Attrs): Chart {
  const kind = CHART_KINDS.find((each) => each === attrs.kind) ?? 'column';
  return {
    range: chartRangeOf(attrs.range),
    kind,
    stacked: STACKING.includes(kind) && attrs.stacked === true,
    by: attrs.by === 'rows' ? 'rows' : 'cols',
    names: flag(attrs.names),
    labels: flag(attrs.labels),
    title: typeof attrs.title === 'string' ? attrs.title.slice(0, CHART_TITLE_LENGTH) : '',
    legend: attrs.legend !== false,
  };
}

/** A chart's attributes as a node keeps them, from what was checked. */
export function chartAttrs(chart: Chart): Attrs {
  return { ...chart, title: chart.title.trim() || null };
}

function chartParsed(element: HTMLElement): Attrs {
  let attrs: Attrs = {};
  try {
    const found: unknown = JSON.parse(element.dataset.attrs ?? '{}');
    if (typeof found === 'object' && found !== null) attrs = found as Attrs;
  } catch {
    // What another program wrote there is no chart's; the figure keeps the defaults.
  }
  return chartAttrs(chartOf({ ...attrs, kind: element.dataset.chart }));
}

function chartSpec(node: Node): DOMOutputSpec {
  const { kind, ...rest } = chartOf(node.attrs);
  const attrs = { 'data-chart': kind, 'data-attrs': JSON.stringify(rest) };
  return rest.title ? ['figure', attrs, ['figcaption', rest.title]] : ['figure', attrs];
}

function sizeOf(value: unknown): number | null {
  const pt = Number(value);
  return pt >= 1 && pt <= 400 ? pt : null;
}

/** A size mark's span; in the editor its size follows `--fit`, by which the Slides view shrinks a
 * box's text to fit the box. */
export function sizedSpan(mark: Mark, fitted: boolean): DOMOutputSpec {
  const pt = sizeOf(mark.attrs.pt);
  if (!pt) return ['span', {}, 0];
  const size = fitted ? `calc(${pt}pt * var(--fit, 1))` : `${pt}pt`;
  return ['span', { 'data-font-size': String(pt), style: `font-size: ${size}` }, 0];
}

function proposalAttrs(attrs: Attrs): Record<string, string> {
  const change = changeOf(attrs);
  if (!change) return {};
  return {
    'data-proposal': change.id,
    'data-author': change.author,
    ...(change.user !== null ? { 'data-user': String(change.user) } : {}),
    ...(change.date ? { 'data-date': change.date } : {}),
  };
}

function proposalParsed(element: HTMLElement): Attrs | false {
  const { proposal: id, author, user, date } = element.dataset;
  if (!id || !author) return false;
  return { id, author, user: user ? Number(user) || null : null, date: date ?? null };
}

function proposal(tag: 'ins' | 'del'): MarkDrawn {
  return {
    parseDOM: [{ tag: `${tag}[data-proposal]`, priority: 60, getAttrs: proposalParsed }],
    toDOM: (mark) => [tag, proposalAttrs(mark.attrs), 0],
  };
}

function formattingParsed(element: HTMLElement): Attrs | false {
  const change = proposalParsed(element);
  if (!change) return false;
  try {
    const before = marksFrom(schema, JSON.parse(element.dataset.formatting ?? 'null'));
    return { ...change, before: endMarksAttr(before) ?? {} };
  } catch {
    return false;
  }
}

function decorated(line: string) {
  return {
    style: 'text-decoration',
    getAttrs: (value: string) => value.includes(line) && null,
  };
}

type NodeName = keyof typeof spec.nodes;
type MarkName = keyof typeof spec.marks;

/** What schema.json says of an attribute: its default and the values it may take. */
interface Attribute {
  default?: unknown;
  schema?: unknown;
}

/** What schema.json says of a node or a mark. */
interface Defined {
  attrSets?: readonly (keyof typeof spec.attrSets)[];
  attrs?: Record<string, Attribute>;
  content?: string;
  group?: string;
  excludes?: string;
  inclusive?: boolean;
}

const NODES: Record<NodeName, Defined> = spec.nodes;
const MARKS: Record<MarkName, Defined> = spec.marks;

/** The attributes as ProseMirror takes them, each with its default where it has one; the
 * values they may take are checked where content is written, on the server. */
function attrsOf({ attrSets = [], attrs }: Defined): Record<string, AttributeSpec> {
  const all = Object.assign({}, ...attrSets.map((name) => spec.attrSets[name]), attrs);
  return Object.fromEntries(
    Object.entries<Attribute>(all).map(([name, attr]) => [
      name,
      'default' in attr ? { default: attr.default } : {},
    ]),
  );
}

/** The file's nodes or marks, in its order, each with what the editor adds to draw it. */
function joined<N extends string, S>(defined: Record<N, Defined>, drawn: Record<N, Partial<S>>) {
  const entries = Object.entries<Defined>(defined).map(([name, each]) => {
    const attrs = attrsOf(each);
    const own = Object.entries(each).filter(([key]) => key !== 'attrs' && key !== 'attrSets');
    const structure = {
      ...Object.fromEntries(own),
      ...(Object.keys(attrs).length ? { attrs } : {}),
    };
    return [name, { ...structure, ...drawn[name as N] }];
  });
  return Object.fromEntries(entries) as Record<N, S>;
}

export const schema = new Schema<NodeName, MarkName>({
  nodes: joined<NodeName, NodeSpec>(NODES, {
    doc: {},
    paragraph: textblock([{ tag: 'p' }], (node) => ['p', listed(node)], listParsed),
    title: textblock(
      [{ tag: 'p[data-block=title]' }, { tag: 'p.MsoTitle' }],
      (node) => ['p', { 'data-block': 'title', ...slideShown(node) }],
      slideParsed,
    ),
    subtitle: textblock([{ tag: 'p[data-block=subtitle]' }, { tag: 'p.MsoSubtitle' }], () => [
      'p',
      { 'data-block': 'subtitle' },
    ]),
    heading: textblock(
      LEVELS.map((level) => ({ tag: `h${level}`, attrs: { level } })),
      (node) => [`h${node.attrs.level}`, slideShown(node)],
      slideParsed,
    ),
    table: {
      parseDOM: [
        {
          tag: 'table',
          getAttrs: (element) => tableAttrsIn(element),
          getContent: (element, schema) => tableCellsIn(element as HTMLElement, schema),
        },
      ],
      toDOM: () => ['table', ['tbody', 0]],
    },
    cell: {
      toDOM: (node) => {
        const fill = swatchOf(HIGHLIGHTS, node.attrs.fill);
        return fill
          ? [
              'td',
              { 'data-fill': node.attrs.fill, style: `background-color: ${onScreen(fill)}` },
              0,
            ]
          : ['td', 0];
      },
    },
    image: {
      parseDOM: [
        {
          tag: 'figure[data-image]',
          getAttrs: (element) => imageParsed(element.querySelector('img'), element),
        },
        { tag: 'img', getAttrs: (element) => imageParsed(element as HTMLImageElement, element) },
      ],
      toDOM: (node) => imageSpec(node),
    },
    pdf: {
      parseDOM: [{ tag: 'figure[data-pdf]', getAttrs: (element) => pdfParsed(element) }],
      toDOM: (node) => pdfSpec(node),
    },
    contents: {
      parseDOM: [
        {
          tag: 'nav[data-contents]',
          getAttrs: (element) => ({ depth: depthOf(element.dataset.contents) }),
        },
      ],
      toDOM: (node) => ['nav', { 'data-contents': String(node.attrs.depth) }],
    },
    chart: {
      parseDOM: [{ tag: 'figure[data-chart]', getAttrs: (element) => chartParsed(element) }],
      toDOM: (node) => chartSpec(node),
    },
    horizontalRule: {
      parseDOM: [{ tag: 'hr' }],
      toDOM: () => ['hr'],
    },
    pageBreak: {
      parseDOM: [{ tag: 'div[data-page-break]' }],
      toDOM: () => ['div', { 'data-page-break': '' }],
    },
    sectionBreak: {
      parseDOM: [{ tag: 'div[data-section-break]' }],
      toDOM: () => ['div', { 'data-section-break': '' }],
    },
    slideBreak: {
      parseDOM: [{ tag: 'div[data-slide-break]', getAttrs: (element) => slideParsed(element) }],
      toDOM: (node) => ['div', { 'data-slide-break': '', ...slideShown(node) }],
    },
    columnBreak: {
      parseDOM: [{ tag: 'div[data-column-break]' }],
      toDOM: () => ['div', { 'data-column-break': '' }],
    },
    field: {
      parseDOM: [
        {
          tag: 'span[data-field]',
          getAttrs: (element) => ({ kind: fieldOf(element.dataset.field) }),
        },
      ],
      toDOM: (node) => ['span', { 'data-field': node.attrs.kind }],
    },
    footnote: {
      parseDOM: [
        {
          tag: 'span[data-note]',
          getAttrs: (element) => ({ kind: element.dataset.note === 'end' ? 'end' : 'foot' }),
        },
      ],
      toDOM: (node) => ['span', { 'data-note': noteKind(node) }, 0],
    },
    text: {},
  }),
  marks: joined<MarkName, MarkSpec>(MARKS, {
    link: {
      parseDOM: [
        {
          tag: 'a[href]',
          getAttrs: (element) => {
            const href = safeHref(element.getAttribute('href'));
            return href ? { href } : false;
          },
        },
      ],
      toDOM: (mark) => {
        const href = safeHref(mark.attrs.href);
        return ['a', href ? { href, rel: 'noopener noreferrer' } : {}, 0];
      },
    },
    strong: {
      parseDOM: [
        { tag: 'strong' },
        { tag: 'b', getAttrs: (node) => node.style.fontWeight !== 'normal' && null },
        { style: 'font-weight=bold' },
      ],
      toDOM: () => ['strong', 0],
    },
    em: {
      parseDOM: [{ tag: 'em' }, { tag: 'i' }, { style: 'font-style=italic' }],
      toDOM: () => ['em', 0],
    },
    underline: {
      parseDOM: [{ tag: 'u' }, decorated('underline')],
      toDOM: () => ['u', 0],
    },
    strike: {
      parseDOM: [{ tag: 's' }, { tag: 'del' }, { tag: 'strike' }, decorated('line-through')],
      toDOM: () => ['s', 0],
    },
    sub: {
      parseDOM: [{ tag: 'sub' }, { style: 'vertical-align=sub' }],
      toDOM: () => ['sub', 0],
    },
    sup: {
      parseDOM: [{ tag: 'sup' }, { style: 'vertical-align=super' }],
      toDOM: () => ['sup', 0],
    },
    color: paint(TEXT_COLORS, 'span', 'color', 'color'),
    highlight: paint(HIGHLIGHTS, 'mark', 'background-color', 'highlight'),
    font: {
      parseDOM: [
        { tag: 'span[data-font]', getAttrs: (element) => ({ family: element.dataset.font }) },
      ],
      toDOM: (mark) => {
        const family = String(mark.attrs.family);
        const shown = substitute(family);
        const stack = shown && fontStack(shown);
        return [
          'span',
          { 'data-font': family, ...(stack ? { style: `font-family: ${stack}` } : {}) },
          0,
        ];
      },
    },
    insertion: proposal('ins'),
    deletion: proposal('del'),
    formatting: {
      parseDOM: [{ tag: 'span[data-formatting]', priority: 60, getAttrs: formattingParsed }],
      toDOM: (mark) => [
        'span',
        { ...proposalAttrs(mark.attrs), 'data-formatting': JSON.stringify(mark.attrs.before) },
        0,
      ],
    },
    size: {
      parseDOM: [
        {
          tag: 'span[data-font-size]',
          getAttrs: (element) => {
            const pt = sizeOf(element.dataset.fontSize);
            return pt ? { pt } : false;
          },
        },
      ],
      toDOM: (mark) => sizedSpan(mark, true),
    },
    kerning: {
      parseDOM: [
        {
          tag: 'span[data-kerning]',
          getAttrs: (element) => ({ on: element.dataset.kerning === 'normal' }),
        },
      ],
      toDOM: (mark) => {
        const kerning = mark.attrs.on ? 'normal' : 'none';
        return ['span', { 'data-kerning': kerning, style: `font-kerning: ${kerning}` }, 0];
      },
    },
  }),
});
