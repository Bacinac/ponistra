import type { Node } from 'prosemirror-model';
import {
  Plugin,
  PluginKey,
  TextSelection,
  type EditorState,
  type Transaction,
} from 'prosemirror-state';
import { Decoration, DecorationSet, type EditorView } from 'prosemirror-view';
import { fontStack } from '../fonts';
import { PX_PER_CM, scaleOf } from './pages';
import { levelOf, listOf, schema } from './schema';
import {
  boxOf,
  type Background,
  layoutOf,
  ROLES,
  slidesOf,
  type Box,
  type Kind,
  type Layout,
  type Look,
  type Role,
  type Slide,
  type Template,
} from './slides';

/** PowerPoint's steps of shrinking a box's text to fit it. */
export const FITS = [1, 0.925, 0.85, 0.775, 0.7, 0.625, 0.55, 0.475, 0.4] as const;
/** PowerPoint's default inset of a text box's text, in cm. */
const INSET = { x: 0.254, y: 0.127 };
/** The strip above each slide that names it, in px. */
export const HEADER = 28;
const BETWEEN = 24;
const NOTES_GAP = 12;
/** The speaker notes under a slide start below their label, and end with a margin. */
export const NOTES_LABEL = 32;
const NOTES_SIDE = 16;
const NOTES_END = 12;

const COLOR = /^#[0-9a-f]{6}$/;
const ALIGNS = ['left', 'center', 'right', 'justify'];

/** What a template's text look sets, as CSS declarations: only values we know, since a
 * document's template is written by its other editors. Its size is the first list level's
 * unless it sets one for the block's level. */
export function lookDeclarations(look: Look | undefined, level = 0): [string, string][] {
  if (!look) return [];
  const declarations: [string, string][] = [];
  const size = look.levels?.[level] ?? look.size;
  if (typeof size === 'number' && size > 0 && size <= 400) {
    declarations.push(['font-size', `calc(${size}pt * var(--fit, 1))`]);
  }
  const font =
    look.font === 'headings' || look.font === 'text'
      ? `var(--font-${look.font})`
      : look.font && fontStack(look.font);
  if (font) declarations.push(['font-family', font]);
  if (look.color && COLOR.test(look.color)) declarations.push(['color', look.color]);
  if (typeof look.bold === 'boolean') declarations.push(['font-weight', look.bold ? '700' : '400']);
  if (typeof look.italic === 'boolean') {
    declarations.push(['font-style', look.italic ? 'italic' : 'normal']);
  }
  if (look.align && ALIGNS.includes(look.align)) declarations.push(['--slide-align', look.align]);
  return declarations;
}

/** A place on the slide in px from its top left corner. */
export interface Frame {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function frameOf(box: Pick<Box, 'x' | 'y' | 'w' | 'h'>): Frame {
  const px = (cm: number) => (Number.isFinite(cm) ? cm * PX_PER_CM : 0);
  return { x: px(box.x), y: px(box.y), w: px(box.w), h: px(box.h) };
}

export interface LaidBox extends Frame {
  key: string;
  role: Role;
  /** The layout's own box, which offers to be written where it is blank. */
  own: boolean;
  look: Look | undefined;
  /** Where its blocks start and end in the tab's text, the same where it holds none. */
  from: number;
  to: number;
  /** Whether it holds nothing written. */
  blank: boolean;
  /** How far its text is shrunk to fit it, of its look's sizes. */
  fit: number;
  /** Its text overflows it at the smallest fit. */
  over: boolean;
}

export interface LaidSlide {
  /** Where the slide shows, in px from the deck's top. */
  top: number;
  hidden: boolean;
  layout: Layout;
  /** Its own background, else its layout's. */
  background: Background | undefined;
  boxes: LaidBox[];
  notes: { top: number; height: number; end: number } | null;
}

interface Placed {
  pos: number;
  end: number;
  role: Role | 'notes' | 'before' | 'break';
  style: string;
  hidden: boolean;
}

export interface Deck {
  /** A slide's size in px. */
  width: number;
  height: number;
  /** How tall the deck shows, every slide with its notes. */
  total: number;
  slides: LaidSlide[];
  placed: Placed[];
}

interface Measure {
  pos: number;
  node: Node;
  height: number;
  before: number;
  after: number;
}

function measured(view: EditorView, node: Node, pos: number): Measure | null {
  const dom = view.nodeDOM(pos);
  if (!(dom instanceof HTMLElement)) return null;
  const style = getComputedStyle(dom);
  if (style.display === 'none') return null;
  return {
    pos,
    node,
    height: dom.offsetHeight,
    before: parseFloat(style.marginTop) || 0,
    after: parseFloat(style.marginBottom) || 0,
  };
}

/** The blocks one under another from `top`, their margins between them as in the flow of text;
 * each top is its margin's, as an absolutely placed block takes it. */
function stacked(blocks: readonly Measure[], top: number): { tops: number[]; height: number } {
  const tops: number[] = [];
  let y = top;
  let after = 0;
  blocks.forEach((block, index) => {
    const border = y + (index ? Math.max(after, block.before) : 0);
    tops.push(border - block.before);
    y = border + block.height;
    after = block.after;
  });
  return { tops, height: y - top };
}

/** How far a box's text is shrunk, kept between layouts: it grows back a step only while its
 * blocks are those it last fitted, so a step that overflowed is not tried again and again. */
export interface Fitting {
  step: number;
  nodes: readonly Node[];
  rose: boolean;
  stuck: boolean;
}

export function fitted(
  was: Fitting | undefined,
  nodes: readonly Node[],
  height: number,
  room: number,
) {
  const same =
    was !== undefined &&
    was.nodes.length === nodes.length &&
    was.nodes.every((node, index) => node === nodes[index]);
  const step = was?.step ?? 0;
  let stuck = same && was.stuck;
  const at = (next: number) => (height * FITS[next]) / FITS[step];
  if (height > room + 0.5 && step < FITS.length - 1) {
    if (was?.rose) stuck = true;
    let next = step + 1;
    while (next < FITS.length - 1 && at(next) > room) next++;
    return { step: next, nodes, rose: false, stuck };
  }
  if (step > 0 && !stuck && at(step - 1) <= room * 0.97) {
    return { step: step - 1, nodes, rose: true, stuck };
  }
  return { step, nodes, rose: false, stuck };
}

function inlineStyle(declarations: readonly [string, string][]): string {
  return declarations.map(([name, value]) => `${name}: ${value}`).join('; ');
}

function placedStyle(left: number, top: number, width: number | null, rest = ''): string {
  return `left: ${left}px; top: ${top}px; ${width === null ? '' : `width: ${width}px; `}${rest}`;
}

const blankBlock = (node: Node) =>
  (node.isTextblock && node.content.size === 0) ||
  node.type === schema.nodes.columnBreak ||
  node.type === schema.nodes.slideBreak;

/** The tab laid out as slides of `template`: each slide's blocks in the boxes of its layout,
 * shrunk to fit them, its speaker notes under it, and what comes before the first slide above
 * them all. */
function dealt(view: EditorView, template: Template, fittings: Map<string, Fitting>): Deck {
  const { doc } = view.state;
  const width = template.size.width * PX_PER_CM;
  const height = template.size.height * PX_PER_CM;
  const slides = slidesOf(doc);
  const placed: Placed[] = [];
  const laid: LaidSlide[] = [];
  const kept = new Set<number>();
  for (const slide of slides) {
    for (const { pos } of [...slide.placed, ...slide.notes]) kept.add(pos);
  }

  let y = 0;
  const before: Measure[] = [];
  doc.forEach((node, pos) => {
    if (kept.has(pos)) return;
    const block = measured(view, node, pos);
    if (block) before.push(block);
  });
  if (before.length) {
    const { tops, height: tall } = stacked(before, 0);
    before.forEach((block, index) => {
      placed.push({
        pos: block.pos,
        end: block.pos + block.node.nodeSize,
        role: 'before',
        style: placedStyle(0, tops[index], width),
        hidden: false,
      });
    });
    y = tall + BETWEEN;
  }

  slides.forEach((slide, index) => {
    const layout = layoutOf(slide, template);
    const top = y + HEADER;
    const groups = new Map<string, { role: Role; box: Box; blocks: Slide['placed'] }>();
    for (const block of slide.placed) {
      if (block.node.type === schema.nodes.slideBreak) {
        placed.push({
          pos: block.pos,
          end: block.pos + block.node.nodeSize,
          role: 'break',
          style: placedStyle(40, y + 4, null),
          hidden: slide.hidden,
        });
        continue;
      }
      const { box, key } = boxOf(layout, block.role, template.size);
      const group = groups.get(key) ?? { role: block.role, box, blocks: [] };
      group.blocks.push(block);
      groups.set(key, group);
    }
    for (const role of ROLES) {
      const box = layout.boxes[role];
      if (box && !groups.has(role)) groups.set(role, { role, box, blocks: [] });
    }

    const boxes: LaidBox[] = [];
    for (const [key, { role, box, blocks }] of groups) {
      const frame = frameOf(box);
      const inner = {
        x: frame.x + INSET.x * PX_PER_CM,
        y: frame.y + INSET.y * PX_PER_CM,
        w: Math.max(frame.w - 2 * INSET.x * PX_PER_CM, 1),
        h: Math.max(frame.h - 2 * INSET.y * PX_PER_CM, 0),
      };
      const shown = blocks.flatMap(({ node, pos }) => measured(view, node, pos) ?? []);
      const flow = shown.filter(({ node }) => node.type !== schema.nodes.columnBreak);
      const tall = stacked(flow, 0).height;
      const memory = `${index}:${key}`;
      const fitting = fitted(
        fittings.get(memory),
        blocks.map(({ node }) => node),
        tall,
        inner.h,
      );
      fittings.set(memory, fitting);
      const fit = FITS[fitting.step];
      const anchor = box.text?.anchor ?? 'top';
      const room = inner.h - tall;
      const offset =
        room <= 0 ? 0 : anchor === 'middle' ? room / 2 : anchor === 'bottom' ? room : 0;
      const start = top + inner.y + offset;
      const { tops } = stacked(flow, start);
      shown.forEach((block) => {
        const at = flow.indexOf(block);
        const level = listOf(block.node) ? levelOf(block.node) : 0;
        placed.push({
          pos: block.pos,
          end: block.pos + block.node.nodeSize,
          role,
          style: placedStyle(
            inner.x,
            at < 0 ? start : tops[at],
            inner.w,
            inlineStyle([['--fit', String(fit)], ...lookDeclarations(box.text, level)]),
          ),
          hidden: slide.hidden,
        });
      });
      const first = blocks[0];
      const last = blocks[blocks.length - 1];
      boxes.push({
        ...frame,
        key,
        role,
        own: layout.boxes[role] === box,
        look: box.text,
        from: first?.pos ?? slide.to,
        to: last ? last.pos + last.node.nodeSize : slide.to,
        blank: blocks.every(({ node }) => blankBlock(node)),
        fit,
        over: fitting.step === FITS.length - 1 && tall > inner.h + 0.5,
      });
    }

    let bottom = top + height;
    let notes: LaidSlide['notes'] = null;
    if (slide.notes.length) {
      const shown = slide.notes.flatMap(({ node, pos }) => measured(view, node, pos) ?? []);
      const notesTop = bottom + NOTES_GAP;
      const { tops, height: tall } = stacked(shown, notesTop + NOTES_LABEL);
      shown.forEach((block, at) => {
        placed.push({
          pos: block.pos,
          end: block.pos + block.node.nodeSize,
          role: 'notes',
          style: placedStyle(NOTES_SIDE, tops[at], width - 2 * NOTES_SIDE),
          hidden: false,
        });
      });
      const last = slide.notes[slide.notes.length - 1];
      notes = {
        top: notesTop,
        height: NOTES_LABEL + tall + NOTES_END,
        end: last.pos + last.node.nodeSize,
      };
      bottom = notesTop + notes.height;
    }
    const background = slide.background ?? layout.background;
    laid.push({ top, hidden: slide.hidden, layout, background, boxes, notes });
    y = bottom + BETWEEN;
  });

  return { width, height, total: Math.max(y - BETWEEN, 0), slides: laid, placed };
}

/** A box of a slide as a PowerPoint file keeps it, in cm from the slide's top left corner: where
 * it is and how its text shows, and where each of its blocks shows, by the block's place in the
 * tab's text. */
export interface MeasuredBox {
  key: string;
  role: Role;
  own: boolean;
  fit: number;
  x: number;
  y: number;
  w: number;
  h: number;
  look: Look | undefined;
  blocks: [index: number, x: number, y: number, w: number, h: number][];
}

export interface MeasuredSlide {
  /** Its layout by its place in the template, or the built-in one of a kind the template lacks. */
  layout: number | Kind;
  hidden: boolean;
  boxes: MeasuredBox[];
  /** Its speaker notes by their places in the tab's text. */
  notes: number[];
}

/** What of a block shows as a picture or a table of its own, rather than as the block's frame. */
const SHOWN = { image: 'img', table: 'table', pdf: '.ponistra-frame' } as Record<string, string>;

const centimetres = (px: number) => Math.round((px / PX_PER_CM) * 1000) / 1000;

/** The tab's slides as laid out in `view` by `deck` of `template`, measured for a PowerPoint
 * file. */
export function measuredSlides(view: EditorView, deck: Deck, template: Template): MeasuredSlide[] {
  const { doc } = view.state;
  const indices = new Map<number, number>();
  doc.forEach((_, pos, index) => indices.set(pos, index));
  const origin = view.dom.getBoundingClientRect();
  return slidesOf(doc).map((slide, at) => {
    const laid = deck.slides[at];
    const place = template.layouts.indexOf(laid.layout);
    return {
      layout: place < 0 ? laid.layout.kind : place,
      hidden: laid.hidden,
      notes: slide.notes.map(({ pos }) => indices.get(pos)!),
      boxes: laid.boxes.map((box) => ({
        key: box.key,
        role: box.role,
        own: box.own,
        fit: box.fit,
        x: centimetres(box.x),
        y: centimetres(box.y),
        w: centimetres(box.w),
        h: centimetres(box.h),
        look: box.look,
        blocks: slide.placed
          .filter(({ pos }) => pos >= box.from && pos < box.to)
          .flatMap(({ node, pos }): MeasuredBox['blocks'] => {
            const dom = view.nodeDOM(pos);
            if (!(dom instanceof HTMLElement)) return [];
            const selector = SHOWN[node.type.name];
            const shown = (selector && dom.querySelector(selector)) || dom;
            const { left, top, width, height } = shown.getBoundingClientRect();
            if (!width && !height) return [];
            return [
              [
                indices.get(pos)!,
                centimetres(left - origin.left),
                centimetres(top - origin.top - laid.top),
                centimetres(width),
                centimetres(height),
              ],
            ];
          }),
      })),
    };
  });
}

function sameDeck(a: Deck | null, b: Deck): boolean {
  return a !== null && JSON.stringify(a) === JSON.stringify(b);
}

function decorationsOf(doc: Node, deck: Deck): DecorationSet {
  return DecorationSet.create(
    doc,
    deck.placed
      .filter(({ end }) => end <= doc.content.size)
      .map(({ pos, end, role, style, hidden }) =>
        Decoration.node(pos, end, {
          class: 'ponistra-placed',
          'data-role': role,
          ...(hidden ? { 'data-slide-hidden': '' } : {}),
          style,
        }),
      ),
  );
}

interface Dealing {
  template: Template | null;
  deck: Deck | null;
  decorations: DecorationSet;
}

export const deckKey = new PluginKey<Dealing>('deck');

type Meta = { template: Template | null } | { deck: Deck };

export function dealingOf(state: EditorState): Dealing | undefined {
  return deckKey.getState(state);
}

/** Lays the tab out as slides of `template`, or as its text where null. */
export function showDeck(view: EditorView, template: Template | null): void {
  const now = dealingOf(view.state)?.template ?? null;
  if (now === template || JSON.stringify(now) === JSON.stringify(template)) return;
  view.dispatch(view.state.tr.setMeta(deckKey, { template } satisfies Meta));
}

/** The cursor in a slide's box: at the end of its text where it has any, else in the block
 * that starts writing it, the slide keeping the layout it shows meanwhile. */
function into(state: EditorState, slide: Slide, layout: Layout, box: LaidBox): Transaction {
  const { doc } = state;
  const blocks = slide.placed.filter(({ pos }) => pos >= box.from && pos < box.to);
  const written = blocks.filter(({ node }) => node.isTextblock);
  if (written.length) {
    const block = written[written.length - 1];
    const end = block.pos + block.node.nodeSize - 1;
    return state.tr.setSelection(TextSelection.create(doc, end));
  }
  const { heading, paragraph, subtitle, columnBreak, slideBreak } = schema.nodes;
  const { start } = slide;
  let tr = state.tr;
  let at: number;
  if (box.role === 'title') {
    if (start?.node.type === slideBreak) {
      const { layout: named, hidden } = start.node.attrs;
      tr = tr.replaceWith(
        start.pos,
        start.pos + start.node.nodeSize,
        heading.create({ level: 1, layout: named, hidden }),
      );
      return tr.setSelection(TextSelection.create(tr.doc, start.pos + 1));
    }
    at = slide.from;
    tr = tr.insert(at, heading.create({ level: 1 }));
  } else {
    const ahead = slide.placed.filter(({ role, node }) =>
      box.role === 'second' ? true : role !== 'second' && node.type !== columnBreak,
    );
    const last = ahead[ahead.length - 1];
    const after = blocks[blocks.length - 1] ?? (box.role === 'subtitle' ? start : last);
    at = after ? after.pos + after.node.nodeSize : slide.from;
    if (box.role === 'second' && !blocks.length) {
      tr = tr.insert(at, columnBreak.create());
      at += 1;
    }
    tr = tr.insert(at, (box.role === 'subtitle' ? subtitle : paragraph).create());
  }
  if (start && slide.layout === null && box.role !== 'title') {
    tr = tr.setNodeAttribute(tr.mapping.map(start.pos), 'layout', layout.id);
  }
  return tr.setSelection(TextSelection.create(tr.doc, at + 1));
}

function distance(box: Frame, x: number, y: number): number {
  const dx = Math.max(box.x - x, 0, x - box.x - box.w);
  const dy = Math.max(box.y - y, 0, y - box.y - box.h);
  return Math.hypot(dx, dy);
}

/** Where a click on a slide away from its text writes: the box under it or the nearest, or the
 * slide's speaker notes below it. */
function clicked(state: EditorState, deck: Deck, x: number, y: number): Transaction | null {
  const index = deck.slides.findLastIndex((slide) => slide.top - HEADER <= y);
  if (index < 0) return null;
  const laid = deck.slides[index];
  const slide = slidesOf(state.doc)[index];
  if (!slide) return null;
  if (laid.notes && y >= laid.notes.top) {
    const end = Math.min(laid.notes.end - 1, state.doc.content.size);
    return state.tr.setSelection(TextSelection.near(state.doc.resolve(end), -1));
  }
  const local = { x, y: y - laid.top };
  const near = [...laid.boxes].sort(
    (a, b) => distance(a, local.x, local.y) - distance(b, local.x, local.y),
  )[0];
  if (!near) return null;
  return into(state, slide, laid.layout, near);
}

class Dealer {
  private frame = 0;
  private fittings = new Map<string, Fitting>();
  private observer: ResizeObserver | null = null;
  private observed = new Set<Element>();
  private fonts = () => this.schedule();

  constructor(private view: EditorView) {}

  update(view: EditorView, previous: EditorState): void {
    const now = dealingOf(view.state)!;
    const was = dealingOf(previous)!;
    if (now.template !== was.template) this.fittings.clear();
    if (!now.template) {
      if (was.template) this.watch(false);
      return;
    }
    if (view.state.doc !== previous.doc || now.template !== was.template) this.schedule();
  }

  /** Lays the deck out again when a block's height or the fonts change, as an image loading
   * does, while there are slides. */
  private watch(on: boolean): void {
    if (!on) {
      this.observer?.disconnect();
      this.observer = null;
      this.observed.clear();
      document.fonts?.removeEventListener('loadingdone', this.fonts);
      return;
    }
    if (!this.observer) {
      this.observer = new ResizeObserver(() => this.schedule());
      document.fonts?.addEventListener('loadingdone', this.fonts);
    }
    const children = new Set(this.view.dom.children);
    for (const element of this.observed) {
      if (!children.has(element)) {
        this.observer.unobserve(element);
        this.observed.delete(element);
      }
    }
    for (const element of children) {
      if (this.observed.has(element)) continue;
      this.observer.observe(element);
      this.observed.add(element);
    }
  }

  schedule(): void {
    if (!dealingOf(this.view.state)?.template) return;
    cancelAnimationFrame(this.frame);
    this.frame = requestAnimationFrame(() => this.lay());
  }

  private lay(): void {
    const view = this.view;
    if (view.isDestroyed) return;
    const { template, deck } = dealingOf(view.state)!;
    if (!template) return;
    const next = dealt(view, template, this.fittings);
    this.watch(true);
    if (sameDeck(deck, next)) return;
    view.dispatch(
      view.state.tr.setMeta(deckKey, { deck: next } satisfies Meta).setMeta('addToHistory', false),
    );
    this.schedule();
  }

  destroy(): void {
    cancelAnimationFrame(this.frame);
    this.watch(false);
  }
}

export function deckPlugin(): Plugin<Dealing> {
  return new Plugin<Dealing>({
    key: deckKey,
    state: {
      init: () => ({ template: null, deck: null, decorations: DecorationSet.empty }),
      apply(tr, value) {
        const meta = tr.getMeta(deckKey) as Meta | undefined;
        if (meta && 'template' in meta) {
          return { template: meta.template, deck: null, decorations: DecorationSet.empty };
        }
        if (meta && 'deck' in meta) {
          return { ...value, deck: meta.deck, decorations: decorationsOf(tr.doc, meta.deck) };
        }
        return tr.docChanged
          ? { ...value, decorations: value.decorations.map(tr.mapping, tr.doc) }
          : value;
      },
    },
    props: {
      decorations: (state) => dealingOf(state)?.decorations,
      attributes: (state): Record<string, string> => {
        const deck = dealingOf(state)?.deck;
        return deck ? { style: `height: ${deck.total}px` } : {};
      },
      handleDOMEvents: {
        mousedown(view, event) {
          const deck = dealingOf(view.state)?.deck;
          if (!deck || event.target !== view.dom || event.button !== 0 || !view.editable) {
            return false;
          }
          const rect = view.dom.getBoundingClientRect();
          const scale = scaleOf(view.dom, rect);
          const tr = clicked(
            view.state,
            deck,
            (event.clientX - rect.left) / scale,
            (event.clientY - rect.top) / scale,
          );
          if (!tr) return false;
          event.preventDefault();
          view.focus();
          view.dispatch(tr.scrollIntoView());
          return true;
        },
      },
    },
    view: (view) => new Dealer(view),
  });
}
