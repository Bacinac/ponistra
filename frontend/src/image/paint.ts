import { TEXT_COLORS } from '../editor/colors';
import {
  blurOf,
  filterOf,
  haloOf,
  HEAD,
  reachOf,
  shownPoint,
  sideways,
  SPREAD,
  type Edits,
  type Mark,
  type Rect,
  type Size,
} from './edits';

/** The font a text mark is written in, which the backend writes it in too. */
export function fontOf(size: number): string {
  return `700 ${size}px Inter`;
}

let measuring: OffscreenCanvasRenderingContext2D | null = null;

/** The box a mark covers on the image as it shows. */
export function boundsOf(mark: Mark, edits: Edits, upright: Size): Rect {
  const shown = (at: number) =>
    shownPoint(mark.points[at], mark.points[at + 1], upright, edits.turn, edits.flip);
  if (mark.kind === 'text') {
    const [x, y] = shown(0);
    measuring ??= new OffscreenCanvas(1, 1).getContext('2d')!;
    measuring.font = fontOf(mark.size);
    const measured = measuring.measureText(mark.text);
    const ascent = measured.actualBoundingBoxAscent;
    const halo = haloOf(mark.size);
    return {
      x: x - halo,
      y: y - ascent - halo,
      w: measured.width + 2 * halo,
      h: ascent + measured.actualBoundingBoxDescent + 2 * halo,
    };
  }
  const xs: number[] = [];
  const ys: number[] = [];
  for (let at = 0; at < mark.points.length; at += 2) {
    const [x, y] = shown(at);
    xs.push(x);
    ys.push(y);
  }
  const reach = reachOf(mark);
  const left = Math.min(...xs) - reach;
  const top = Math.min(...ys) - reach;
  return { x: left, y: top, w: Math.max(...xs) + reach - left, h: Math.max(...ys) + reach - top };
}

/** Turns the context from the image as it shows to the image upright. */
function toUpright(context: CanvasRenderingContext2D, edits: Edits, upright: Size) {
  if (edits.flip) {
    context.translate(sideways(edits.turn) ? upright.height : upright.width, 0);
    context.scale(-1, 1);
  }
  if (edits.turn === 90) context.translate(upright.height, 0);
  else if (edits.turn === 180) context.translate(upright.width, upright.height);
  else if (edits.turn === 270) context.translate(0, upright.width);
  context.rotate((edits.turn * Math.PI) / 180);
}

/** Places the context's units on the pixels of the image upright, from the region it shows. */
function placed(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  region: Rect,
  edits: Edits,
  upright: Size,
) {
  const across = canvas.width / region.w;
  const down = canvas.height / region.h;
  context.setTransform(across, 0, 0, down, -region.x * across, -region.y * down);
  toUpright(context, edits, upright);
}

/** The part blurred within the image upright, with what lies round it to blur from. */
function blurred(
  context: CanvasRenderingContext2D,
  bitmap: ImageBitmap,
  points: number[],
  edits: Edits,
  scale: number,
) {
  const [x1, y1, x2, y2] = points;
  const left = Math.max(0, Math.round(Math.min(x1, x2)));
  const top = Math.max(0, Math.round(Math.min(y1, y2)));
  const right = Math.min(bitmap.width, Math.round(Math.max(x1, x2)));
  const bottom = Math.min(bitmap.height, Math.round(Math.max(y1, y2)));
  if (right <= left || bottom <= top) return;
  const radius = blurOf(points);
  const margin = Math.ceil(radius * 3);
  const x = Math.max(0, left - margin);
  const y = Math.max(0, top - margin);
  const w = Math.min(bitmap.width, right + margin) - x;
  const h = Math.min(bitmap.height, bottom + margin) - y;
  context.save();
  context.beginPath();
  context.rect(left, top, right - left, bottom - top);
  context.clip();
  // A filter's lengths are the canvas's own pixels, whatever the transform.
  context.filter = `blur(${radius * scale}px) ${filterOf(edits)}`;
  context.drawImage(bitmap, x, y, w, h, x, y, w, h);
  context.restore();
}

/** An arrow, a rectangle or a line drawn by hand, in the pixels of the image upright. */
function shaped(context: CanvasRenderingContext2D, mark: Mark) {
  if (mark.kind === 'text' || mark.kind === 'blur') return;
  const color = TEXT_COLORS[mark.color].light;
  const [x1, y1, x2, y2] = mark.points;
  context.strokeStyle = color;
  context.fillStyle = color;
  context.lineWidth = mark.width;
  if (mark.kind === 'rectangle') {
    context.lineJoin = 'miter';
    context.strokeRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
    return;
  }
  context.lineJoin = 'round';
  context.lineCap = 'round';
  let line = mark.points;
  if (mark.kind === 'arrow') {
    const length = Math.hypot(x2 - x1, y2 - y1);
    if (length === 0) return;
    const across = (x2 - x1) / length;
    const down = (y2 - y1) / length;
    const head = Math.min(mark.width * HEAD, length);
    const spread = mark.width * SPREAD;
    const bx = x2 - across * head;
    const by = y2 - down * head;
    context.beginPath();
    context.moveTo(x2, y2);
    context.lineTo(bx - down * spread, by + across * spread);
    context.lineTo(bx + down * spread, by - across * spread);
    context.closePath();
    context.fill();
    line = [x1, y1, bx, by];
  }
  context.beginPath();
  context.moveTo(line[0], line[1]);
  for (let at = 2; at < line.length; at += 2) context.lineTo(line[at], line[at + 1]);
  if (line.length === 2) context.lineTo(line[0], line[1]);
  context.stroke();
}

/** A text from where its line starts, reading across, in the canvas's own pixels. */
function written(context: CanvasRenderingContext2D, text: string, color: string, size: number) {
  context.font = fontOf(size);
  context.textAlign = 'left';
  context.textBaseline = 'alphabetic';
  context.lineJoin = 'round';
  context.lineWidth = 2 * haloOf(size);
  context.strokeStyle = 'white';
  context.strokeText(text, 0, 0);
  context.fillStyle = color;
  context.fillText(text, 0, 0);
}

/** The region of the image as its edits and marks show it, drawn by the backend's steps: the
 * parts blurred, then the image cropped, turned, mirrored and toned, then each mark over it. */
export function paint(
  canvas: HTMLCanvasElement,
  bitmap: ImageBitmap,
  edits: Edits,
  marks: readonly [string, Mark][],
  region: Rect,
) {
  const context = canvas.getContext('2d')!;
  const upright = { width: bitmap.width, height: bitmap.height };
  const across = canvas.width / region.w;
  const down = canvas.height / region.h;
  placed(context, canvas, region, edits, upright);
  context.imageSmoothingQuality = 'high';
  context.filter = filterOf(edits);
  context.drawImage(bitmap, 0, 0);
  for (const [, mark] of marks) {
    if (mark.kind === 'blur') blurred(context, bitmap, mark.points, edits, across);
  }
  context.filter = 'none';
  for (const [, mark] of marks) {
    if (mark.kind === 'text') {
      const [x, y] = shownPoint(mark.points[0], mark.points[1], upright, edits.turn, edits.flip);
      context.setTransform(1, 0, 0, 1, (x - region.x) * across, (y - region.y) * down);
      const size = Math.max(1, Math.round(mark.size * across));
      written(context, mark.text, TEXT_COLORS[mark.color].light, size);
    } else if (mark.kind !== 'blur') {
      placed(context, canvas, region, edits, upright);
      shaped(context, mark);
    }
  }
}

/** The mark being drawn, alone over the image. */
export function paintDraft(
  canvas: HTMLCanvasElement,
  mark: Mark | null,
  edits: Edits,
  upright: Size,
  region: Rect,
) {
  const context = canvas.getContext('2d')!;
  context.resetTransform();
  context.clearRect(0, 0, canvas.width, canvas.height);
  if (!mark) return;
  placed(context, canvas, region, edits, upright);
  shaped(context, mark);
}
