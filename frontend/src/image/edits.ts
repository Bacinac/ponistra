import type * as Y from 'yjs';
import type { TextColor } from '../editor/colors';

/** What an image file's room keeps beside it, each on a key of its own, and the backend draws
 * into its copy (apps/blobs/edits.py): the crop in the pixels of the image upright, a turn
 * clockwise, a mirror across, the longer side at most, and the browser's filters of tone. */
export interface Edits {
  crop: Rect | null;
  turn: Turn;
  flip: boolean;
  side: number | null;
  brightness: number;
  contrast: number;
  saturation: number;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Size {
  width: number;
  height: number;
}

export type Turn = 0 | 90 | 180 | 270;
export type Tone = 'brightness' | 'contrast' | 'saturation';
export type Change = { [Key in keyof Edits]?: Edits[Key] | null };

export const EDITS = 'edits';
export const MARKS = 'marks';

interface Made {
  /** x and y of each point in turn. */
  points: number[];
  by: number | null;
  at: string;
}

/** An arrow, a rectangle, a line drawn by hand, a text or a blurred part, in the pixels of the
 * image upright, which the backend draws into the copy the same: a text's point is where its line
 * starts, and it reads across the image as it shows. */
export type Mark =
  | (Made & { kind: 'arrow' | 'rectangle' | 'stroke'; color: TextColor; width: number })
  | (Made & { kind: 'text'; color: TextColor; size: number; text: string })
  | (Made & { kind: 'blur' });

export type Tool = Mark['kind'];
export const TOOLS: Tool[] = ['arrow', 'rectangle', 'stroke', 'text', 'blur'];

/** A text's size by its pen's width, in the pen's units. */
export const TEXT_SIZE = 12;
/** An arrow's head, long and wide by so many of its line's widths. */
export const HEAD = 4;
export const SPREAD = 2.5;

/** A pen's width on this image, in units of a five hundredth of its longer side; a text's size
 * grows with it more slowly. */
export function penOf(width: number, upright: Size, kind: Tool): number {
  const unit = Math.max(1, Math.max(upright.width, upright.height) / 500);
  const drawn = kind === 'text' ? (TEXT_SIZE * unit * (1 + width)) / 2 : width * unit;
  return Math.round(drawn * 10) / 10;
}

/** The blur of a part, enough that what it covers cannot be read. */
export function blurOf([x1, y1, x2, y2]: number[]): number {
  return Math.min(64, Math.max(4, Math.min(Math.abs(x2 - x1), Math.abs(y2 - y1)) / 4));
}

/** The white edge round a text's letters, which keeps them legible on any image. */
export function haloOf(size: number): number {
  return Math.max(1, Math.round(size / 10));
}

/** The marks in the order they were made, which is the order they are drawn in. */
export function marksIn(kept: Y.Map<Mark>): [string, Mark][] {
  const order = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
  return [...kept.entries()].sort(
    ([a, first], [b, second]) => order(first.at, second.at) || order(a, b),
  );
}

/** How far a drawn mark reaches past its points, in the pixels of the image upright. */
export function reachOf(mark: Mark): number {
  if (mark.kind === 'arrow') return mark.width * SPREAD;
  return mark.kind === 'rectangle' || mark.kind === 'stroke' ? mark.width / 2 : 0;
}

export const TONES: Tone[] = ['brightness', 'contrast', 'saturation'];
export const SIDES = [2560, 1920, 1600, 1280, 800];
export const RATIOS = [null, 1, 4 / 3, 16 / 9] as const;
export type Ratio = (typeof RATIOS)[number];
/** The media types whose files are edited, each kept in its own format. */
export const EDITABLE = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/avif']);

export const NONE: Edits = {
  crop: null,
  turn: 0,
  flip: false,
  side: null,
  brightness: 1,
  contrast: 1,
  saturation: 1,
};

export function editsOf(kept: Y.Map<unknown>): Edits {
  const value = <Key extends keyof Edits>(key: Key): Edits[Key] =>
    (kept.get(key) as Edits[Key] | undefined) ?? NONE[key];
  return {
    crop: value('crop'),
    turn: value('turn'),
    flip: value('flip'),
    side: value('side'),
    brightness: value('brightness'),
    contrast: value('contrast'),
    saturation: value('saturation'),
  };
}

export function edited(edits: Edits): boolean {
  return (Object.keys(NONE) as (keyof Edits)[]).some((key) => edits[key] !== NONE[key]);
}

/** The browser's filters, which the backend computes the same. */
export function filterOf(edits: Edits): string {
  return `brightness(${edits.brightness}) contrast(${edits.contrast}) saturate(${edits.saturation})`;
}

export function sideways(turn: Turn): boolean {
  return turn === 90 || turn === 270;
}

function turned({ width, height }: Size, turn: Turn): Size {
  return sideways(turn) ? { width: height, height: width } : { width, height };
}

/** The size the copy comes out at: cropped, turned and made smaller. */
export function sizeOf(upright: Size, edits: Edits): Size {
  const crop = edits.crop ?? { x: 0, y: 0, w: upright.width, h: upright.height };
  const shown = turned({ width: crop.w, height: crop.h }, edits.turn);
  const longer = Math.max(shown.width, shown.height);
  if (edits.side === null || edits.side >= longer) return shown;
  // Pillow's thumbnail keeps the ratio, rounding the shorter side.
  const scale = edits.side / longer;
  return {
    width: Math.max(1, Math.round(shown.width * scale)),
    height: Math.max(1, Math.round(shown.height * scale)),
  };
}

/** A point of the image upright as the whole image shows it turned and mirrored. */
export function shownPoint(
  x: number,
  y: number,
  upright: Size,
  turn: Turn,
  flip: boolean,
): [number, number] {
  const { width, height } = upright;
  const [across, down] =
    turn === 90
      ? [height - y, x]
      : turn === 180
        ? [width - x, height - y]
        : turn === 270
          ? [y, width - x]
          : [x, y];
  return [flip ? turned(upright, turn).width - across : across, down];
}

/** A point of the whole image as it shows, in the image upright. */
export function uprightPoint(
  x: number,
  y: number,
  upright: Size,
  turn: Turn,
  flip: boolean,
): [number, number] {
  const { width, height } = upright;
  const across = flip ? turned(upright, turn).width - x : x;
  return turn === 90
    ? [y, height - across]
    : turn === 180
      ? [width - across, height - y]
      : turn === 270
        ? [width - y, across]
        : [across, y];
}

function spanning([x1, y1]: [number, number], [x2, y2]: [number, number]): Rect {
  return { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1) };
}

/** A rectangle of the image upright as the whole image shows it turned and mirrored. */
export function shownRect(rect: Rect, upright: Size, edits: Pick<Edits, 'turn' | 'flip'>): Rect {
  const corner = (x: number, y: number) => shownPoint(x, y, upright, edits.turn, edits.flip);
  return spanning(corner(rect.x, rect.y), corner(rect.x + rect.w, rect.y + rect.h));
}

/** A rectangle chosen on the image as it shows, in the whole pixels of the image upright. */
export function uprightRect(rect: Rect, upright: Size, edits: Pick<Edits, 'turn' | 'flip'>): Rect {
  const corner = (x: number, y: number) => uprightPoint(x, y, upright, edits.turn, edits.flip);
  const found = spanning(corner(rect.x, rect.y), corner(rect.x + rect.w, rect.y + rect.h));
  const within = (value: number, low: number, high: number) =>
    Math.min(Math.max(Math.round(value), low), high);
  const x = within(found.x, 0, upright.width - 1);
  const y = within(found.y, 0, upright.height - 1);
  return {
    x,
    y,
    w: within(found.x + found.w, x + 1, upright.width) - x,
    h: within(found.y + found.h, y + 1, upright.height) - y,
  };
}

/** The largest rectangle of the ratio, across over down, in the middle of the shown image. */
export function centred(shown: Size, ratio: number): Rect {
  const w = Math.min(shown.width, shown.height * ratio);
  const h = w / ratio;
  return { x: (shown.width - w) / 2, y: (shown.height - h) / 2, w, h };
}

export type Handle = 'move' | 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';
export const HANDLES: Exclude<Handle, 'move'>[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
const SMALLEST = 8;

/** The crop as a handle dragged by (dx, dy) leaves it, kept within the shown image and to its
 * ratio, where it has one. */
export function dragged(
  start: Rect,
  handle: Handle,
  dx: number,
  dy: number,
  shown: Size,
  ratio: Ratio,
): Rect {
  if (handle === 'move') {
    return {
      ...start,
      x: Math.min(Math.max(start.x + dx, 0), shown.width - start.w),
      y: Math.min(Math.max(start.y + dy, 0), shown.height - start.h),
    };
  }
  let left = start.x;
  let top = start.y;
  let right = start.x + start.w;
  let bottom = start.y + start.h;
  if (handle.includes('w')) left = Math.min(Math.max(left + dx, 0), right - SMALLEST);
  if (handle.includes('e')) right = Math.max(Math.min(right + dx, shown.width), left + SMALLEST);
  if (handle.includes('n')) top = Math.min(Math.max(top + dy, 0), bottom - SMALLEST);
  if (handle.includes('s')) bottom = Math.max(Math.min(bottom + dy, shown.height), top + SMALLEST);
  if (ratio === null) return { x: left, y: top, w: right - left, h: bottom - top };
  // The side dragged leads and the other follows, from the corner or edge held still.
  const down = handle === 'n' || handle === 's';
  let w = down ? (bottom - top) * ratio : right - left;
  let h = down ? bottom - top : (right - left) / ratio;
  const roomAcross = handle.includes('w')
    ? start.x + start.w
    : handle.includes('e')
      ? shown.width - start.x
      : shown.width;
  const roomDown = handle.includes('n')
    ? start.y + start.h
    : handle.includes('s')
      ? shown.height - start.y
      : shown.height;
  const fit = Math.min(1, roomAcross / w, roomDown / h);
  w *= fit;
  h *= fit;
  const x = handle.includes('w')
    ? start.x + start.w - w
    : handle.includes('e')
      ? start.x
      : start.x + (start.w - w) / 2;
  const y = handle.includes('n')
    ? start.y + start.h - h
    : handle.includes('s')
      ? start.y
      : start.y + (start.h - h) / 2;
  return {
    x: Math.min(Math.max(x, 0), shown.width - w),
    y: Math.min(Math.max(y, 0), shown.height - h),
    w,
    h,
  };
}

function turnedBy(turn: Turn, by: number): Turn {
  return ((((turn + by) % 360) + 360) % 360) as Turn;
}

/** The image as it shows turned a quarter clockwise or back: a mirrored image turns the other
 * way before its mirror. */
export function turnedShown(edits: Pick<Edits, 'turn' | 'flip'>, by: 90 | -90): Change {
  return { turn: turnedBy(edits.turn, edits.flip ? -by : by) };
}

/** The image as it shows mirrored down: across, and half a turn. */
export function mirroredDown(edits: Pick<Edits, 'turn' | 'flip'>): Change {
  return { flip: !edits.flip, turn: turnedBy(edits.turn, 180) };
}
