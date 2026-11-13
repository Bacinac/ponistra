import type { Attrs } from 'prosemirror-model';
import type { Command } from 'prosemirror-state';
import { reshape } from './blocks';
import { LEAST_TEXT, type PageSetup } from './pages';
import { INDENT_MAX, INDENT_STEP, LISTS } from './schema';

/** Where a dragged marker settles: the nearest quarter centimetre, or anywhere with Alt. */
export const SNAP = 0.25;
/** The narrowest a paragraph's lines may be left between its indents. */
export const LEAST_LINE = 1;
const HEADER_MAX = 15;
const MARGIN_MAX = 30;

const hundredths = (cm: number) => Math.round(cm * 100) / 100;
const within = (value: number, least: number, most: number) =>
  Math.min(Math.max(value, least), Math.max(least, most));

export function snapped(cm: number, free: boolean): number {
  return hundredths(free ? cm : Math.round(cm / SNAP) * SNAP);
}

export type Edge = 'left' | 'right' | 'top' | 'bottom' | 'header' | 'footer';

const FACING = { left: 'right', right: 'left', top: 'bottom', bottom: 'top' } as const;

/** The page setup with one edge moved to a length from the paper's edge, never past room for
 * text. */
export function movedEdge(setup: PageSetup, edge: Edge, length: number): PageSetup {
  if (edge === 'header' || edge === 'footer') {
    return { ...setup, [edge]: within(hundredths(length), 0, HEADER_MAX) };
  }
  const size = edge === 'left' || edge === 'right' ? setup.width : setup.height;
  const most = Math.min(MARGIN_MAX, size - setup[FACING[edge]] - LEAST_TEXT);
  return { ...setup, [edge]: within(hundredths(length), 0, most) };
}

/** A paragraph's indents in cm: its lines' left, its first line's offset from them (negative
 * where it hangs) and its right. */
export interface Indents {
  left: number;
  first: number;
  right: number;
}

export function indentsOf(attrs: Attrs): Indents {
  return {
    left: Number(attrs.indent) || 0,
    first: Number(attrs.firstLine) || 0,
    right: Number(attrs.right) || 0,
  };
}

/** The first line's marker, the hanging one beneath it that moves the other lines, the box under
 * that which moves both, and the right one. */
export type IndentMarker = 'first' | 'hanging' | 'left' | 'right';

/** A paragraph's indents with one marker moved to a length from the text's left edge, the right
 * one from its right edge, as far as its lines keep their room in a text this wide. An item of a
 * list moves a whole level at a time. */
export function movedIndent(
  indents: Indents,
  marker: IndentMarker,
  at: number,
  width: number,
  listed: boolean,
): Indents {
  const { left, first, right } = indents;
  const opening = width - right - LEAST_LINE;
  if (marker === 'right') {
    const most = width - Math.max(left, left + first) - LEAST_LINE;
    return { ...indents, right: within(hundredths(at), 0, most) };
  }
  if (listed) {
    const most = Math.floor(Math.min(INDENT_MAX, opening) / INDENT_STEP);
    return { ...indents, left: within(Math.round(at / INDENT_STEP), 0, most) * INDENT_STEP };
  }
  if (marker === 'first') return { ...indents, first: hundredths(within(at, 0, opening) - left) };
  if (marker === 'hanging') {
    const moved = hundredths(within(at, 0, Math.min(INDENT_MAX, opening)));
    return { ...indents, left: moved, first: hundredths(left + first - moved) };
  }
  const most = Math.min(INDENT_MAX, opening, opening - first);
  return { ...indents, left: hundredths(within(at, Math.max(0, -first), most)) };
}

/** Moves one indent marker of every selected paragraph. */
export function setIndent(marker: IndentMarker, at: number, width: number): Command {
  return reshape((attrs) => {
    const before = indentsOf(attrs);
    const listed = LISTS.some((kind) => kind === attrs.list);
    const { left, first, right } = movedIndent(before, marker, at, width, listed);
    if (left === before.left && first === before.first && right === before.right) return null;
    return { indent: left || null, firstLine: first || null, right: right || null };
  });
}
