import type { Node } from 'prosemirror-model';
import { describe, expect, it } from 'vitest';
import * as Y from 'yjs';
import { schema } from './schema';
import {
  elapsed,
  firstsOf,
  keyed,
  moved,
  placeOf,
  positionOf,
  runOf,
  startOf,
  timed,
} from './show';
import { slidesBefore, writeSlideCount } from './slides';

const { nodes } = schema;
const h = (value: string, hidden = false) =>
  nodes.heading.create({ level: 1, hidden }, schema.text(value));
const doc = (...blocks: Node[]) => nodes.doc.create(null, blocks);

const run = runOf([
  { id: 'a', doc: doc(h('Uvod'), h('Skriveni', true), h('Cijene')) },
  { id: 'b', doc: doc(h('Pitanja'), h('Kraj', true)) },
]);

describe('the run of a show', () => {
  it('takes every tab’s slides in reading order, numbered through the tabs', () => {
    expect(run).toEqual([
      { tab: 'a', index: 0, hidden: false },
      { tab: 'a', index: 1, hidden: true },
      { tab: 'a', index: 2, hidden: false },
      { tab: 'b', index: 0, hidden: false },
      { tab: 'b', index: 1, hidden: true },
    ]);
    expect(firstsOf(run)).toEqual({ a: 0, b: 3 });
    expect(placeOf(run, { tab: 'b', index: 0 })).toBe(3);
    expect(placeOf(run, null)).toBe(run.length);
    expect(positionOf(run, run.length)).toBeNull();
  });

  it('moves past hidden slides, to the closing screen after the last shown', () => {
    expect(moved(run, 0, 'next')).toBe(2);
    expect(moved(run, 3, 'next')).toBe(run.length);
    expect(moved(run, run.length, 'next')).toBe(run.length);
    expect(moved(run, 2, 'previous')).toBe(0);
    expect(moved(run, 0, 'previous')).toBe(0);
    expect(moved(run, run.length, 'previous')).toBe(3);
    expect(moved(run, 3, 'first')).toBe(0);
    expect(moved(run, 0, 'last')).toBe(3);
  });

  it('goes to a slide by its number, hidden or not, and stays for a number past the end', () => {
    expect(moved(run, 0, { to: 2 })).toBe(1);
    expect(moved(run, 0, { to: 9 })).toBe(0);
    expect(moved(run, 0, { to: 0 })).toBe(0);
  });

  it('starts on the cursor’s slide, or on the first shown after a hidden one', () => {
    expect(startOf(run, 'a', 2)).toBe(2);
    expect(startOf(run, 'a', 1)).toBe(2);
    expect(startOf(run, 'b', 1)).toBe(run.length);
  });
});

describe('keys of a show', () => {
  it('moves by PowerPoint’s keys and goes to a number typed before Enter', () => {
    for (const key of ['ArrowRight', 'ArrowDown', 'PageDown', ' ', 'Enter', 'n']) {
      expect(keyed(key, '').move).toBe('next');
    }
    for (const key of ['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace', 'p']) {
      expect(keyed(key, '').move).toBe('previous');
    }
    expect(keyed('Home', '').move).toBe('first');
    expect(keyed('End', '').move).toBe('last');
    expect(keyed('Escape', '').move).toBe('end');
    expect(keyed('1', '')).toEqual({ move: null, typed: '1' });
    expect(keyed('2', '1')).toEqual({ move: null, typed: '12' });
    expect(keyed('Enter', '12')).toEqual({ move: { to: 12 }, typed: '' });
    expect(keyed('x', '12')).toEqual({ move: null, typed: '' });
  });
});

describe('the show’s timer', () => {
  it('pauses, resumes and restarts', () => {
    const started = { since: 1000, before: 0 };
    expect(elapsed(started, 4000)).toBe(3000);
    const paused = timed(started, 'pause', 4000);
    expect(paused).toEqual({ since: null, before: 3000 });
    expect(elapsed(paused, 9000)).toBe(3000);
    const resumed = timed(paused, 'resume', 10000);
    expect(elapsed(resumed, 12000)).toBe(5000);
    expect(timed(resumed, 'restart', 12000)).toEqual({ since: 12000, before: 0 });
    expect(timed(paused, 'restart', 12000)).toEqual({ since: null, before: 0 });
  });
});

describe('slide numbers through the tabs', () => {
  it('counts the slides of the tabs before, as their editors keep them', () => {
    const own = new Y.Doc();
    writeSlideCount(own, 'a', 3);
    writeSlideCount(own, 'b', 2);
    expect(slidesBefore(own, ['a', 'b', 'c'], 'a')).toBe(0);
    expect(slidesBefore(own, ['a', 'b', 'c'], 'c')).toBe(5);
    expect(slidesBefore(own, ['x', 'a', 'b'], 'b')).toBe(3);
  });
});
