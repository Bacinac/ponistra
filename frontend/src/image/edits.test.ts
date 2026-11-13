import { describe, expect, it } from 'vitest';
import * as Y from 'yjs';
import {
  blurOf,
  centred,
  dragged,
  EDITS,
  edited,
  editsOf,
  haloOf,
  MARKS,
  marksIn,
  mirroredDown,
  NONE,
  penOf,
  reachOf,
  shownPoint,
  shownRect,
  sizeOf,
  turnedShown,
  uprightPoint,
  uprightRect,
  type Mark,
  type Turn,
} from './edits';

const UPRIGHT = { width: 400, height: 300 };
const TURNS: Turn[] = [0, 90, 180, 270];

describe('edits', () => {
  it('reads what the room keeps over what is left as it came', () => {
    const doc = new Y.Doc();
    const kept = doc.getMap<unknown>(EDITS);
    expect(editsOf(kept)).toEqual(NONE);
    expect(edited(editsOf(kept))).toBe(false);
    kept.set('turn', 90);
    kept.set('brightness', 1.2);
    expect(editsOf(kept)).toEqual({ ...NONE, turn: 90, brightness: 1.2 });
    expect(edited(editsOf(kept))).toBe(true);
  });

  it('finds a crop chosen on the image turned and mirrored where it lies upright', () => {
    const crop = { x: 10, y: 20, w: 100, h: 50 };
    for (const turn of TURNS) {
      for (const flip of [false, true]) {
        const shown = shownRect(crop, UPRIGHT, { turn, flip });
        expect(uprightRect(shown, UPRIGHT, { turn, flip })).toEqual(crop);
      }
    }
    expect(shownRect(crop, UPRIGHT, { turn: 90, flip: false })).toEqual({
      x: 230,
      y: 10,
      w: 50,
      h: 100,
    });
    expect(shownRect(crop, UPRIGHT, { turn: 0, flip: true })).toEqual({
      x: 290,
      y: 20,
      w: 100,
      h: 50,
    });
  });

  it('keeps a crop within the image in whole pixels', () => {
    expect(uprightRect({ x: -5, y: 0.4, w: 500.6, h: 99.5 }, UPRIGHT, NONE)).toEqual({
      x: 0,
      y: 0,
      w: 400,
      h: 100,
    });
  });

  it('gives the size the copy comes out at, the longer side made smaller', () => {
    expect(sizeOf(UPRIGHT, NONE)).toEqual(UPRIGHT);
    const crop = { x: 0, y: 0, w: 200, h: 100 };
    expect(sizeOf(UPRIGHT, { ...NONE, crop, turn: 270 })).toEqual({ width: 100, height: 200 });
    expect(sizeOf(UPRIGHT, { ...NONE, side: 80 })).toEqual({ width: 80, height: 60 });
    expect(sizeOf(UPRIGHT, { ...NONE, side: 800 })).toEqual(UPRIGHT);
  });

  it('places the largest crop of a ratio in the middle', () => {
    expect(centred(UPRIGHT, 1)).toEqual({ x: 50, y: 0, w: 300, h: 300 });
    expect(centred(UPRIGHT, 16 / 9)).toEqual({ x: 0, y: 37.5, w: 400, h: 225 });
  });

  it('drags a crop within the image, to its ratio where it has one', () => {
    const start = { x: 100, y: 100, w: 100, h: 100 };
    expect(dragged(start, 'move', 500, -500, UPRIGHT, null)).toEqual({
      x: 300,
      y: 0,
      w: 100,
      h: 100,
    });
    expect(dragged(start, 'se', 50, 10, UPRIGHT, null)).toEqual({ x: 100, y: 100, w: 150, h: 110 });
    expect(dragged(start, 'se', 50, 10, UPRIGHT, 1)).toEqual({ x: 100, y: 100, w: 150, h: 150 });
    expect(dragged(start, 'nw', -500, 0, UPRIGHT, 1)).toEqual({ x: 0, y: 0, w: 200, h: 200 });
    expect(dragged(start, 's', 0, 100, UPRIGHT, 2)).toEqual({ x: 0, y: 100, w: 400, h: 200 });
  });

  it('turns and mirrors the image as it shows', () => {
    expect(turnedShown({ turn: 0, flip: false }, 90)).toEqual({ turn: 90 });
    expect(turnedShown({ turn: 0, flip: true }, 90)).toEqual({ turn: 270 });
    expect(turnedShown({ turn: 270, flip: false }, 90)).toEqual({ turn: 0 });
    expect(mirroredDown({ turn: 90, flip: false })).toEqual({ flip: true, turn: 270 });
  });

  it('takes a point back from the image as it shows to the image upright', () => {
    for (const turn of TURNS) {
      for (const flip of [false, true]) {
        const [x, y] = shownPoint(30, 70, UPRIGHT, turn, flip);
        expect(uprightPoint(x, y, UPRIGHT, turn, flip)).toEqual([30, 70]);
      }
    }
    expect(shownPoint(30, 70, UPRIGHT, 90, false)).toEqual([230, 30]);
    expect(shownPoint(30, 70, UPRIGHT, 90, true)).toEqual([70, 30]);
  });

  it('sizes a pen by the image and a text by its pen, more slowly', () => {
    expect(penOf(2, { width: 400, height: 300 }, 'arrow')).toBe(2);
    expect(penOf(2, { width: 4000, height: 3000 }, 'stroke')).toBe(16);
    expect(penOf(1, { width: 4000, height: 3000 }, 'text')).toBe(96);
    expect(penOf(4, { width: 4000, height: 3000 }, 'text')).toBe(240);
  });

  it('blurs a part enough that it cannot be read and edges a text by its size', () => {
    expect(blurOf([0, 0, 10, 100])).toBe(4);
    expect(blurOf([100, 100, 20, 0])).toBe(20);
    expect(blurOf([0, 0, 1000, 1000])).toBe(64);
    expect(haloOf(8)).toBe(1);
    expect(haloOf(96)).toBe(10);
  });

  it('keeps the marks in the order they were made and how far each reaches', () => {
    const doc = new Y.Doc();
    const kept = doc.getMap<Mark>(MARKS);
    const made = { by: null, color: 'red', width: 4 } as const;
    kept.set('b', { ...made, kind: 'stroke', points: [0, 0], at: '2026-10-28T10:00:00.000Z' });
    kept.set('a', { ...made, kind: 'arrow', points: [0, 0, 9, 9], at: '2026-10-28T10:00:00.000Z' });
    kept.set('c', { kind: 'blur', points: [0, 0, 9, 9], by: 1, at: '2026-10-28T09:00:00.000Z' });
    const marks = marksIn(kept);
    expect(marks.map(([id]) => id)).toEqual(['c', 'a', 'b']);
    expect(marks.map(([, mark]) => reachOf(mark))).toEqual([0, 10, 2]);
  });
});
