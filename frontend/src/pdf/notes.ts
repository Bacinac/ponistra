import * as Y from 'yjs';
import type { PageAnchor, PageRect } from '../comments';
import type { Highlight, TextColor } from '../editor/colors';

/** A highlight or a stroke on one page, in the page's own coordinates: what the file's room keeps
 * beside the file and the backend writes into its copies (apps/exports/annotated.py). */
export type Mark =
  | {
      kind: 'highlight';
      page: number;
      color: Highlight;
      rects: PageRect[];
      by: number | null;
      at: string;
    }
  | {
      kind: 'stroke';
      page: number;
      color: TextColor;
      width: number;
      /** x and y of each point in turn. */
      points: number[];
      by: number | null;
      at: string;
    };

/** What a reader marked to be blacked out of a copy of the file, in the page's own coordinates
 * (apps/imports/redacted.py). */
export interface Redaction {
  kind: 'redaction';
  page: number;
  rects: PageRect[];
  by: number | null;
  at: string;
}

/** Marks this reader writes, which their own undo takes back. */
export const OWN = 'own notes';

export function marksOf(doc: Y.Doc): Y.Map<Mark> {
  return doc.getMap<Mark>('marks');
}

export function redactionsOf(doc: Y.Doc): Y.Map<Redaction> {
  return doc.getMap<Redaction>('redactions');
}

/** The smallest side in points of a rectangle drawn to be blacked out; less is taken for a click. */
export const SMALLEST = 2;

/** The rectangle between two of the page's own points, or null where it is too small to mean one. */
export function spanned(from: [number, number], to: [number, number]): PageRect | null {
  const rect: PageRect = [
    Math.min(from[0], to[0]),
    Math.min(from[1], to[1]),
    Math.max(from[0], to[0]),
    Math.max(from[1], to[1]),
  ];
  return rect[2] - rect[0] >= SMALLEST && rect[3] - rect[1] >= SMALLEST ? rect : null;
}

/** What converts between the page's own coordinates and a box the page fills, as pdf.js's page
 * viewport at scale 1 does. */
export interface Viewport {
  width: number;
  height: number;
  convertToPdfPoint(x: number, y: number): number[];
  convertToViewportPoint(x: number, y: number): number[];
}

const round = (value: number) => Math.round(value * 100) / 100;

/** The page's own point under a point on screen, where the page fills `box`. */
export function pointOn(
  viewport: Viewport,
  box: DOMRectReadOnly,
  x: number,
  y: number,
): [number, number] {
  const [left, top] = viewport.convertToPdfPoint(
    ((x - box.left) / box.width) * viewport.width,
    ((y - box.top) / box.height) * viewport.height,
  );
  return [round(left), round(top)];
}

/** The page's own rectangle under a rectangle on screen. */
export function rectOn(viewport: Viewport, box: DOMRectReadOnly, rect: DOMRectReadOnly): PageRect {
  const [x1, y1] = pointOn(viewport, box, rect.left, rect.top);
  const [x2, y2] = pointOn(viewport, box, rect.right, rect.bottom);
  return [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)];
}

/** A page rectangle in the units of the box the overlay draws in. */
export function drawn(
  viewport: Viewport,
  [left, bottom, right, top]: PageRect,
): { x: number; y: number; width: number; height: number } {
  const [x1, y1] = viewport.convertToViewportPoint(left, bottom);
  const [x2, y2] = viewport.convertToViewportPoint(right, top);
  return {
    x: Math.min(x1, x2),
    y: Math.min(y1, y2),
    width: Math.abs(x2 - x1),
    height: Math.abs(y2 - y1),
  };
}

/** The pieces of one line as one rectangle each: a line's words come as many boxes, which drawn
 * one over another would darken where they overlap. */
export function merged(rects: PageRect[]): PageRect[] {
  const lines: PageRect[] = [];
  const sorted = rects.toSorted((a, b) => b[3] - a[3] || a[0] - b[0]);
  for (const rect of sorted) {
    const at = lines.findIndex((each) => {
      const shared = Math.min(each[3], rect[3]) - Math.max(each[1], rect[1]);
      const height = Math.min(each[3] - each[1], rect[3] - rect[1]);
      const gap = Math.max(each[0], rect[0]) - Math.min(each[2], rect[2]);
      return shared > height / 2 && gap < height / 2;
    });
    if (at < 0) {
      lines.push([...rect]);
      continue;
    }
    const line = lines[at];
    lines[at] = [
      Math.min(line[0], rect[0]),
      Math.min(line[1], rect[1]),
      Math.max(line[2], rect[2]),
      Math.max(line[3], rect[3]),
    ];
  }
  return lines;
}

/** The text chosen across the file's pages: each page's rectangles of it and where it ends on
 * screen, for what is offered on it. */
export interface Chosen {
  parts: { page: number; rects: PageRect[] }[];
  quote: string;
  bounds: DOMRectReadOnly;
}

const LONGEST_QUOTE = 500;

/** The selection as the file's text layers hold it, or null when it is not on them. */
export function chosenIn(
  selection: Selection | null,
  root: HTMLElement,
  viewportOf: (page: number) => Viewport | null,
): Chosen | null {
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null;
  const range = selection.getRangeAt(0);
  const common = range.commonAncestorContainer;
  if (!root.contains(common)) return null;
  const parts = new Map<number, PageRect[]>();
  const walker = document.createTreeWalker(
    common.nodeType === Node.TEXT_NODE ? common.parentNode! : common,
    NodeFilter.SHOW_TEXT,
  );
  for (let text = walker.nextNode(); text; text = walker.nextNode()) {
    if (!range.intersectsNode(text)) continue;
    const layer = text.parentElement?.closest<HTMLElement>('.textLayer');
    const page = Number(layer?.closest<HTMLElement>('.page')?.dataset.pageNumber);
    const viewport = page ? viewportOf(page) : null;
    if (!layer || !viewport) continue;
    const piece = document.createRange();
    piece.selectNodeContents(text);
    if (text === range.startContainer) piece.setStart(text, range.startOffset);
    if (text === range.endContainer) piece.setEnd(text, range.endOffset);
    if (!piece.toString().trim()) continue;
    const box = layer.getBoundingClientRect();
    const rects = parts.get(page) ?? [];
    for (const rect of piece.getClientRects()) {
      if (rect.width > 0 && rect.height > 0) rects.push(rectOn(viewport, box, rect));
    }
    parts.set(page, rects);
  }
  const quote = selection.toString().replace(/\s+/g, ' ').trim().slice(0, LONGEST_QUOTE);
  if (!parts.size || !quote) return null;
  return {
    parts: [...parts].map(([page, rects]) => ({ page, rects: merged(rects) })),
    quote,
    bounds: range.getBoundingClientRect(),
  };
}

/** Where a thread sits on its page: its text's top left, or its point. */
export function placeOf(anchor: PageAnchor): [number, number] {
  if ('at' in anchor) return anchor.at;
  const top = anchor.rects.reduce((highest, rect) => (rect[3] > highest[3] ? rect : highest));
  return [top[0], top[3]];
}
