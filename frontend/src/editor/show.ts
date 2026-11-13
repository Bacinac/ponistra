import type { Node } from 'prosemirror-model';
import { slidesOf } from './slides';

/** A slide of the show, in the reading order of the tabs, numbered by its place in it. */
export interface Shown {
  tab: string;
  index: number;
  hidden: boolean;
}

/** Where a show starts: on a tab's slide, or on the first. */
export type From = { tab: string; index: number } | 'start';

/** Where the show is: on a tab's slide, or on its closing screen past the last. */
export type Position = { tab: string; index: number } | null;

export type Move = 'next' | 'previous' | 'first' | 'last' | { to: number };

/** The time the show has run, paused while `since` is null. */
export interface Timer {
  since: number | null;
  before: number;
}

/** What the show and the presenter's window tell each other. */
export type Said =
  | { type: 'hello' }
  | { type: 'state'; at: Position; timer: Timer }
  | { type: 'move'; move: Move }
  | { type: 'timer'; change: 'pause' | 'resume' | 'restart' }
  | { type: 'end' };

export function runOf(tabs: readonly { id: string; doc: Node }[]): Shown[] {
  return tabs.flatMap(({ id, doc }) =>
    slidesOf(doc).map((slide, index) => ({ tab: id, index, hidden: slide.hidden })),
  );
}

/** The number of the first slide of each tab, less one. */
export function firstsOf(run: readonly Shown[]): Record<string, number> {
  const firsts: Record<string, number> = {};
  run.forEach((shown, at) => (firsts[shown.tab] ??= at));
  return firsts;
}

/** The show's place of a position, `run.length` being its closing screen. */
export function placeOf(run: readonly Shown[], at: Position): number {
  if (!at) return run.length;
  const found = run.findIndex((shown) => shown.tab === at.tab && shown.index === at.index);
  return found < 0 ? run.length : found;
}

export function positionOf(run: readonly Shown[], place: number): Position {
  const shown = run[place];
  return shown ? { tab: shown.tab, index: shown.index } : null;
}

function shownFrom(run: readonly Shown[], from: number, step: 1 | -1): number | null {
  for (let at = from; at >= 0 && at < run.length; at += step) {
    if (!run[at].hidden) return at;
  }
  return null;
}

/** Where the show starts: on the slide given, or the first shown after it. */
export function startOf(run: readonly Shown[], tab: string, index: number): number {
  const at = run.findIndex((shown) => shown.tab === tab && shown.index === index);
  return shownFrom(run, Math.max(at, 0), 1) ?? run.length;
}

/** Where a move takes the show from `at`, past hidden slides, except to one asked for by its
 * number. */
export function moved(run: readonly Shown[], at: number, move: Move): number {
  if (typeof move === 'object') {
    return move.to >= 1 && move.to <= run.length ? move.to - 1 : at;
  }
  switch (move) {
    case 'next':
      return at >= run.length ? at : (shownFrom(run, at + 1, 1) ?? run.length);
    case 'previous':
      return shownFrom(run, Math.min(at, run.length) - 1, -1) ?? at;
    case 'first':
      return shownFrom(run, 0, 1) ?? at;
    case 'last':
      return shownFrom(run, run.length - 1, -1) ?? at;
  }
}

const NEXT = new Set(['ArrowRight', 'ArrowDown', 'PageDown', ' ', 'Enter', 'n', 'N']);
const PREVIOUS = new Set(['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace', 'p', 'P']);

/** What a key does in the show, with the digits of a slide's number typed so far. */
export function keyed(key: string, typed: string): { move: Move | 'end' | null; typed: string } {
  if (/^[0-9]$/.test(key)) return { move: null, typed: typed + key };
  if (key === 'Enter' && typed) return { move: { to: Number(typed) }, typed: '' };
  if (NEXT.has(key)) return { move: 'next', typed: '' };
  if (PREVIOUS.has(key)) return { move: 'previous', typed: '' };
  if (key === 'Home') return { move: 'first', typed: '' };
  if (key === 'End') return { move: 'last', typed: '' };
  if (key === 'Escape') return { move: 'end', typed: '' };
  return { move: null, typed: '' };
}

export function elapsed(timer: Timer, now: number): number {
  return timer.before + (timer.since === null ? 0 : now - timer.since);
}

export function timed(timer: Timer, change: 'pause' | 'resume' | 'restart', now: number): Timer {
  switch (change) {
    case 'pause':
      return timer.since === null ? timer : { since: null, before: elapsed(timer, now) };
    case 'resume':
      return timer.since === null ? { since: now, before: timer.before } : timer;
    case 'restart':
      return { since: timer.since === null ? null : now, before: 0 };
  }
}

export function channelOf(show: string): string {
  return `ponistra-show-${show}`;
}

/** Takes the screen for a show, while the click that asked for it still lets the page. */
export function presentFullScreen(): void {
  document.documentElement.requestFullscreen?.().catch(() => {});
}

export function leaveFullScreen(): void {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
}
