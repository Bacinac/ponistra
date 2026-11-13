import { describe, expect, it } from 'vitest';
import { drawn, merged, placeOf, pointOn, rectOn, spanned, type Viewport } from './notes';

const page: Viewport = {
  width: 600,
  height: 800,
  convertToPdfPoint: (x, y) => [x, 800 - y],
  convertToViewportPoint: (x, y) => [x, 800 - y],
};

const box = (left: number, top: number, width: number, height: number) =>
  ({ left, top, width, height, right: left + width, bottom: top + height }) as DOMRectReadOnly;

describe('page coordinates', () => {
  it('turn a point on screen into the page’s own, whatever the page is zoomed to', () => {
    expect(pointOn(page, box(100, 50, 1200, 1600), 300, 250)).toEqual([100, 700]);
    expect(pointOn(page, box(0, 0, 300, 400), 100.333, 0)).toEqual([200.67, 800]);
  });

  it('keep a rectangle’s left and bottom below its right and top', () => {
    expect(rectOn(page, box(0, 0, 600, 800), box(72, 60, 100, 20))).toEqual([72, 720, 172, 740]);
  });

  it('draw a page rectangle from its top left in the overlay', () => {
    expect(drawn(page, [72, 720, 172, 740])).toEqual({ x: 72, y: 60, width: 100, height: 20 });
  });
});

describe('merged', () => {
  it('makes one rectangle of a line’s words and keeps lines apart', () => {
    expect(
      merged([
        [72, 720, 110, 734],
        [193, 700, 260, 714],
        [113, 721, 160, 733],
        [72, 700, 190, 714],
      ]),
    ).toEqual([
      [72, 720, 160, 734],
      [72, 700, 260, 714],
    ]);
  });

  it('keeps apart pieces of one line with a column between them', () => {
    expect(
      merged([
        [72, 720, 110, 734],
        [300, 720, 340, 734],
      ]),
    ).toHaveLength(2);
  });
});

describe('placeOf', () => {
  it('puts a thread at its point, or at the top left of its text', () => {
    expect(placeOf({ page: 2, at: [480, 760] })).toEqual([480, 760]);
    expect(
      placeOf({
        page: 1,
        rects: [
          [72, 700, 98, 714],
          [90, 716, 140, 731],
        ],
      }),
    ).toEqual([90, 731]);
  });
});

describe('a rectangle drawn to be blacked out', () => {
  it('spans its two corners whichever way it was drawn', () => {
    expect(spanned([172, 700], [72, 740])).toEqual([72, 700, 172, 740]);
  });

  it('is no rectangle where it is too thin to mean one, as a click is', () => {
    expect(spanned([72, 700], [72.5, 740])).toBeNull();
    expect(spanned([72, 700], [172, 701])).toBeNull();
    expect(spanned([72, 700], [74, 702])).toEqual([72, 700, 74, 702]);
  });
});
