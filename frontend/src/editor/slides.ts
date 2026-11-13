import type { Node } from 'prosemirror-model';
import { splitBlockAs } from 'prosemirror-commands';
import { Plugin, TextSelection, type Command } from 'prosemirror-state';
import { Decoration, DecorationSet } from 'prosemirror-view';
import * as Y from 'yjs';
import template from '../../../schema/slides.json';
import { schema } from './schema';

export type Kind = (typeof template.$defs.kind.enum)[number];
export const KINDS: readonly Kind[] = template.$defs.kind.enum;
export const ROLES = ['title', 'subtitle', 'body', 'second'] as const;
export type Role = (typeof ROLES)[number];
type ShapeType = (typeof template.$defs.shape.properties.type.enum)[number];
export type Anchor = (typeof template.$defs.text.properties.anchor.enum)[number];

export interface Look {
  font?: string;
  size?: number;
  levels?: readonly number[];
  color?: string;
  bold?: boolean;
  italic?: boolean;
  align?: 'left' | 'center' | 'right' | 'justify';
  anchor?: Anchor;
}

/** A place on the slide, in cm from its top left corner. */
export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
  text?: Look;
}

export interface Shape extends Box {
  type: ShapeType;
  fill?: string;
  line?: { color: string; width: number };
  flip?: boolean;
  blob?: string;
  content?: string;
}

export interface Background {
  color?: string;
  image?: string;
}

export interface Layout {
  id: string;
  name?: string;
  kind: Kind;
  background?: Background;
  shapes: readonly Shape[];
  boxes: Partial<Record<Role, Box>>;
}

export interface Size {
  width: number;
  height: number;
}

export interface Template {
  size: Size;
  layouts: readonly Layout[];
  /** Whether the layouts are the built-in ones, which name themselves in the interface's language. */
  builtIn: boolean;
}

const SLIDES = 'slides';
const BUILT_IN_SIZE: Size = template.size;
const BUILT_IN: readonly Layout[] = template.layouts;
export const SIZES: Record<keyof typeof template.sizes, Size> = template.sizes;

function isSize(width: unknown, height: unknown): boolean {
  const { minimum, maximum } = template.$defs.size.properties.width;
  return [width, height].every(
    (length) => typeof length === 'number' && length >= minimum && length <= maximum,
  );
}

function isLayout(value: unknown): value is Layout {
  if (!value || typeof value !== 'object') return false;
  const { id, kind, shapes, boxes } = value as Partial<Layout>;
  return (
    typeof id === 'string' &&
    KINDS.includes(kind as Kind) &&
    Array.isArray(shapes) &&
    Boolean(boxes) &&
    typeof boxes === 'object'
  );
}

/** The document's slide template, in its own state: its own layouts where it has them, else the
 * built-in ones, at its slide size. */
export function templateOf(own: Y.Doc): Template {
  const kept = own.getMap(SLIDES);
  const width = kept.get('width');
  const height = kept.get('height');
  const size = isSize(width, height)
    ? { width: width as number, height: height as number }
    : BUILT_IN_SIZE;
  const stored = kept.get('layouts');
  const layouts = Array.isArray(stored) ? stored.filter(isLayout) : [];
  return layouts.length
    ? { size, layouts, builtIn: false }
    : { size, layouts: BUILT_IN.map((layout) => scaledLayout(layout, size)), builtIn: true };
}

export function setSlideSize(own: Y.Doc, size: Size): void {
  const kept = own.getMap(SLIDES);
  own.transact(() => {
    kept.set('width', size.width);
    kept.set('height', size.height);
  });
}

/** Whether a block of the tab's text starts a slide. */
export function startsSlide(node: Node): boolean {
  const { title, heading, slideBreak } = schema.nodes;
  return (
    node.type === title ||
    node.type === slideBreak ||
    (node.type === heading && node.attrs.level === 1)
  );
}

export function isSpeaker(node: Node): boolean {
  return node.type === schema.nodes.paragraph && node.attrs.speaker === true;
}

export interface Placed {
  node: Node;
  pos: number;
  role: Role;
}

export interface Slide {
  /** Where its blocks start and end in the tab's text. */
  from: number;
  to: number;
  /** The block that starts it and carries its layout, its own background and whether it is
   * hidden, if any does. */
  start: { node: Node; pos: number } | null;
  kind: Kind;
  layout: string | null;
  background: Background | null;
  hidden: boolean;
  placed: Placed[];
  notes: { node: Node; pos: number }[];
}

function holdsAnything(nodes: readonly { node: Node }[]): boolean {
  return nodes.some(({ node }) => !node.isTextblock || node.content.size > 0);
}

function slideOf(blocks: readonly { node: Node; pos: number }[]): Slide {
  const [first] = blocks;
  const start = startsSlide(first.node) ? first : null;
  const placed: Placed[] = [];
  const notes: Slide['notes'] = [];
  let role: Role = 'body';
  let columns = false;
  for (const [index, block] of blocks.entries()) {
    const { node } = block;
    if (isSpeaker(node)) {
      notes.push(block);
      continue;
    }
    if (index === 0 && start && node.type !== schema.nodes.slideBreak) {
      placed.push({ ...block, role: 'title' });
      role = 'subtitle';
      continue;
    }
    if (node.type === schema.nodes.columnBreak) {
      role = 'second';
      columns = true;
    } else if (role === 'subtitle' && node.type !== schema.nodes.subtitle) {
      role = 'body';
    }
    placed.push({ ...block, role });
  }
  const content = placed.filter((each) => each.role !== 'title');
  const kind: Kind =
    start?.node.type === schema.nodes.title
      ? 'title'
      : columns
        ? 'two'
        : start?.node.type === schema.nodes.heading
          ? holdsAnything(content)
            ? 'content'
            : 'section'
          : 'blank';
  const last = blocks[blocks.length - 1];
  return {
    from: first.pos,
    to: last.pos + last.node.nodeSize,
    start,
    kind,
    layout: typeof start?.node.attrs.layout === 'string' ? start.node.attrs.layout : null,
    background: (start?.node.attrs.background as Background | null | undefined) ?? null,
    hidden: start?.node.attrs.hidden === true,
    placed,
    notes,
  };
}

/** The tab's slides: each title, heading 1 and slide break at the text's top level starts one,
 * and what comes before the first is one when it holds anything or is all there is. */
export function slidesOf(doc: Node): Slide[] {
  const runs: { node: Node; pos: number }[][] = [];
  doc.forEach((node, pos) => {
    if (startsSlide(node) || !runs.length) runs.push([]);
    runs[runs.length - 1].push({ node, pos });
  });
  const kept = runs.filter(
    (run, index) =>
      index > 0 || startsSlide(run[0].node) || holdsAnything(run) || runs.length === 1,
  );
  return kept.map(slideOf);
}

function scaled<T extends Box>(box: T, { width, height }: Size): T {
  const across = width / BUILT_IN_SIZE.width;
  const down = height / BUILT_IN_SIZE.height;
  return { ...box, x: box.x * across, y: box.y * down, w: box.w * across, h: box.h * down };
}

/** A built-in layout on slides of `size`, its boxes and shapes stretched as the slide is. */
function scaledLayout(layout: Layout, size: Size): Layout {
  if (size.width === BUILT_IN_SIZE.width && size.height === BUILT_IN_SIZE.height) return layout;
  const boxes: Layout['boxes'] = {};
  for (const role of ROLES) {
    const box = layout.boxes[role];
    if (box) boxes[role] = scaled(box, size);
  }
  return { ...layout, boxes, shapes: layout.shapes.map((shape) => scaled(shape, size)) };
}

function builtInOf(kind: Kind, size: Size): Layout {
  return scaledLayout(
    BUILT_IN.find((layout) => layout.kind === kind)!,
    size,
  );
}

/** The layout a slide shows in: the one it names, else the template's first of its kind, else the
 * built-in one of its kind. */
export function layoutOf(slide: Pick<Slide, 'kind' | 'layout'>, template: Template): Layout {
  return (
    template.layouts.find((layout) => layout.id === slide.layout) ??
    template.layouts.find((layout) => layout.kind === slide.kind) ??
    builtInOf(slide.kind, template.size)
  );
}

/** The box a role's blocks go in: the layout's own, else where the built-in layout of its kind
 * puts them, so no text is lost by a change of layout. A subtitle goes with the body where the
 * layout has no place for it, and the body under a title slide's subtitle. */
export function boxOf(layout: Layout, role: Role, size: Size): { box: Box; key: string } {
  const own = (name: Role) => layout.boxes[name] && { box: layout.boxes[name], key: name };
  const base = (kind: Kind, name: Role) => {
    const box = builtInOf(kind, size).boxes[name];
    return box && { box, key: `${kind}.${name}` };
  };
  switch (role) {
    case 'title':
      return own('title') ?? base(layout.kind, 'title') ?? base('content', 'title')!;
    case 'subtitle':
      return own('subtitle') ?? base(layout.kind, 'subtitle') ?? boxOf(layout, 'body', size);
    case 'body':
      return (
        own('body') ??
        base(layout.kind, 'body') ??
        own('subtitle') ??
        base(layout.kind, 'subtitle') ??
        base('content', 'body')!
      );
    case 'second':
      return own('second') ?? base(layout.kind, 'second') ?? base('two', 'second')!;
  }
}

/** How many slides every tab has, kept by the editors of each tab so the tabs after it number
 * their slides on without loading it. */
export function slideCounts(own: Y.Doc): Y.Map<number> {
  return own.getMap<number>('slideCounts');
}

export function writeSlideCount(own: Y.Doc, tab: string, count: number): void {
  if (slideCounts(own).get(tab) === count) return;
  own.transact(() => slideCounts(own).set(tab, count));
}

/** How many slides the tabs before `tab` have, after which its own are numbered. */
export function slidesBefore(own: Y.Doc, tabs: readonly string[], tab: string): number {
  let count = 0;
  for (const id of tabs) {
    if (id === tab) break;
    count += slideCounts(own).get(id) ?? 0;
  }
  return count;
}

export function slideAt(doc: Node, pos: number): Slide | null {
  const $pos = doc.resolve(pos);
  const top = $pos.depth ? $pos.before(1) : pos;
  return slidesOf(doc).find((slide) => top >= slide.from && top < slide.to) ?? null;
}

/** To the end of the speaker notes of the cursor's slide, opening them at the slide's end where it
 * has none. */
export const speakerNotes: Command = (state, dispatch) => {
  const slide = slideAt(state.doc, state.selection.from);
  if (!slide) return false;
  if (dispatch) {
    const last = slide.notes[slide.notes.length - 1];
    if (last) {
      const end = last.pos + last.node.nodeSize - 1;
      dispatch(state.tr.setSelection(TextSelection.create(state.doc, end)).scrollIntoView());
    } else {
      const tr = state.tr.insert(slide.to, schema.nodes.paragraph.create({ speaker: true }));
      dispatch(tr.setSelection(TextSelection.create(tr.doc, slide.to + 1)).scrollIntoView());
    }
  }
  return true;
};

function inNotes(state: Parameters<Command>[0]): boolean {
  const { $from } = state.selection;
  return $from.depth === 1 && isSpeaker($from.parent);
}

const continueNotes = splitBlockAs(() => ({
  type: schema.nodes.paragraph,
  attrs: { speaker: true },
}));

function outOfNotes(state: Parameters<Command>[0]) {
  return state.tr.setNodeAttribute(state.selection.$from.before(), 'speaker', false);
}

/** Enter: the notes' next paragraph, or out of the notes from an empty one. */
const enter: Command = (state, dispatch, view) => {
  if (!inNotes(state) || !state.selection.empty) return false;
  if (state.selection.$from.parent.content.size) return continueNotes(state, dispatch, view);
  dispatch?.(outOfNotes(state));
  return true;
};

/** Backspace at the start of the notes leaves their first paragraph on the slide. */
const unnote: Command = (state, dispatch) => {
  const { $from, empty } = state.selection;
  if (!empty || $from.parentOffset > 0 || !inNotes(state)) return false;
  const before = $from.index(0) > 0 ? state.doc.child($from.index(0) - 1) : null;
  if (before && isSpeaker(before)) return false;
  dispatch?.(outOfNotes(state));
  return true;
};

export const speakerKeys: Record<string, Command> = {
  Enter: enter,
  Backspace: unnote,
};

/** Names each run of speaker notes above it. */
export function speakerLabels(label: () => string): Plugin {
  return new Plugin({
    props: {
      decorations: (state) => {
        const labels: Decoration[] = [];
        let before: Node | null = null;
        state.doc.forEach((node, pos) => {
          if (isSpeaker(node) && !(before && isSpeaker(before))) {
            labels.push(
              Decoration.widget(
                pos,
                () => {
                  const element = document.createElement('div');
                  element.className = 'ponistra-speaker-label';
                  element.contentEditable = 'false';
                  element.textContent = label();
                  return element;
                },
                { side: -1, key: 'speaker', ignoreSelection: true },
              ),
            );
          }
          before = node;
        });
        return DecorationSet.create(state.doc, labels);
      },
    },
  });
}
