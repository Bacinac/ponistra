import { Trash2 } from 'lucide-react';
import {
  useEffect,
  useEffectEvent,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent,
} from 'react';
import { answered } from '../api';
import { TEXT_COLORS } from '../editor/colors';
import { Floating } from '../floating';
import { useI18n } from '../i18n';
import type { Pen } from '../pen';
import { iconButton } from '../styles';
import {
  dragged,
  EDITABLE,
  HANDLES,
  penOf,
  shownPoint,
  shownRect,
  sideways,
  uprightPoint,
  uprightRect,
  type Edits,
  type Handle,
  type Mark,
  type Ratio,
  type Rect,
  type Size,
  type Tool,
} from './edits';
import { boundsOf, fontOf, paint, paintDraft } from './paint';

/** The image upright as its file stores it, once it is read: `failed` where it cannot be,
 * `unsupported` where it is of a kind that is not edited. */
export function useBitmap(src: string | null): ImageBitmap | 'failed' | 'unsupported' | null {
  type Loaded = ImageBitmap | 'failed' | 'unsupported';
  const [loaded, setLoaded] = useState<{ src: string; bitmap: Loaded } | null>(null);
  useEffect(() => {
    if (src === null) return;
    let live = true;
    let made: ImageBitmap | null = null;
    const load = async (): Promise<Loaded> => {
      const response = await answered(src);
      if (!response.ok) throw new Error(`${response.status} ${src}`);
      const blob = await response.blob();
      if (!EDITABLE.has(blob.type)) return 'unsupported';
      made = await createImageBitmap(blob, { imageOrientation: 'from-image' });
      return made;
    };
    load()
      .then((bitmap) => {
        if (live) setLoaded({ src, bitmap });
        else made?.close();
      })
      .catch((error: unknown) => {
        console.error(error);
        if (live) setLoaded({ src, bitmap: 'failed' });
      });
    return () => {
      live = false;
      made?.close();
    };
  }, [src]);
  return loaded !== null && loaded.src === src ? loaded.bitmap : null;
}

export function shownSize(upright: Size, edits: Pick<Edits, 'turn'>): Size {
  return sideways(edits.turn) ? { width: upright.height, height: upright.width } : upright;
}

const CURSORS: Record<Handle, string> = {
  move: 'cursor-move',
  n: 'cursor-ns-resize',
  s: 'cursor-ns-resize',
  e: 'cursor-ew-resize',
  w: 'cursor-ew-resize',
  ne: 'cursor-nesw-resize',
  sw: 'cursor-nesw-resize',
  nw: 'cursor-nwse-resize',
  se: 'cursor-nwse-resize',
};

const place = (handle: Handle) => ({
  left: handle.includes('w') ? '0%' : handle.includes('e') ? '100%' : '50%',
  top: handle.includes('n') ? '0%' : handle.includes('s') ? '100%' : '50%',
});

/** Where a text's line starts on the canvas, at the font's baseline in a line as high as it. */
const BASELINE = 0.86;
/** The least a mark is drawn across on screen to be kept. */
const LEAST = 4;

interface Drag {
  handle: Handle;
  start: Rect;
  x: number;
  y: number;
  rect: Rect;
}

/** The marks drawn over the image by whoever edits it, with the tool and pen chosen. */
export interface Marking {
  tool: Tool | null;
  pen: Pen;
  me: number | null;
  onMark: (id: string, mark: Mark | null) => void;
  onTool: (tool: Tool | null) => void;
}

/** The image as its edits and marks show it, drawn as the backend draws its copy; while it is
 * cropped, the whole image with the crop to drag over it. */
export function ImageView({
  bitmap,
  title,
  edits,
  marks,
  cropping,
  onCrop,
  marking,
}: {
  bitmap: ImageBitmap;
  title: string;
  edits: Edits;
  marks: readonly [string, Mark][];
  cropping: Ratio | undefined;
  onCrop: (crop: Rect | null) => void;
  marking: Marking | null;
}) {
  const { t } = useI18n();
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const sketch = useRef<HTMLCanvasElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const [space, setSpace] = useState<Size | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [lettered, setLettered] = useState(false);
  const sketching = useRef<number[] | null>(null);
  const [draft, setDraft] = useState<Mark | null>(null);
  const writing = useRef<[number, number] | null>(null);
  const field = useRef<HTMLInputElement>(null);
  const [spot, setSpot] = useState<[number, number] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [anchor, setAnchor] = useState<DOMRectReadOnly | null>(null);
  const upright = { width: bitmap.width, height: bitmap.height };
  const full = shownSize(upright, edits);
  const crop = edits.crop && shownRect(edits.crop, upright, edits);
  const region =
    cropping === undefined && crop ? crop : { x: 0, y: 0, w: full.width, h: full.height };
  const scale = space ? Math.min(1, space.width / region.w, space.height / region.h) : 0;
  const width = region.w * scale;
  const height = region.h * scale;
  const tool = cropping === undefined ? (marking?.tool ?? null) : null;
  const choosing = marking !== null && cropping === undefined && tool === null;
  const live = choosing && marks.some(([id]) => id === chosen) ? chosen : null;

  useLayoutEffect(() => {
    if (!box) return;
    const observer = new ResizeObserver(([entry]) =>
      setSpace({ width: entry.contentRect.width, height: entry.contentRect.height }),
    );
    observer.observe(box);
    return () => observer.disconnect();
  }, [box]);

  useEffect(() => {
    let current = true;
    void document.fonts.load(fontOf(16)).then(() => current && setLettered(true));
    return () => {
      current = false;
    };
  }, []);

  const drawing = JSON.stringify([edits, marks, region, width, height, lettered]);
  useLayoutEffect(() => {
    const drawn = canvas.current;
    if (!drawn || width === 0) return;
    drawn.width = Math.max(1, Math.round(Math.min(region.w, width * devicePixelRatio)));
    drawn.height = Math.max(1, Math.round(Math.min(region.h, height * devicePixelRatio)));
    paint(drawn, bitmap, edits, marks, region);
  }, [bitmap, drawing]);

  useLayoutEffect(() => {
    const drawn = sketch.current;
    if (!drawn || !canvas.current) return;
    drawn.width = canvas.current.width;
    drawn.height = canvas.current.height;
    paintDraft(drawn, draft?.kind === 'blur' ? null : draft, edits, upright, region);
  }, [bitmap, drawing, draft]);

  useLayoutEffect(() => {
    const target = live && svg.current?.querySelector(`[data-mark="${live}"]`);
    setAnchor(target ? target.getBoundingClientRect() : null);
  }, [live, drawing]);

  const made = (kind: Tool, points: number[]): Mark => {
    const base = { points, by: marking?.me ?? null, at: new Date().toISOString() };
    if (kind === 'blur') return { ...base, kind };
    const pen = marking!.pen;
    if (kind === 'text') {
      return { ...base, kind, color: pen.color, size: penOf(pen.width, upright, kind), text: '' };
    }
    return { ...base, kind, color: pen.color, width: penOf(pen.width, upright, kind) };
  };

  const pointOf = (clientX: number, clientY: number): [number, number] => {
    const frame = svg.current!.getBoundingClientRect();
    const x = region.x + ((clientX - frame.left) / frame.width) * region.w;
    const y = region.y + ((clientY - frame.top) / frame.height) * region.h;
    const [across, down] = uprightPoint(x, y, upright, edits.turn, edits.flip);
    const within = (value: number, high: number) =>
      Math.round(Math.min(Math.max(value, 0), high) * 10) / 10;
    return [within(across, upright.width), within(down, upright.height)];
  };

  const written = (at: [number, number], text: string) => {
    if (writing.current !== at) return;
    writing.current = null;
    setSpot(null);
    const kept = text.trim();
    if (!kept || !marking) return;
    marking.onMark(crypto.randomUUID(), { ...made('text', at), text: kept } as Mark);
  };

  const down = (event: PointerEvent<SVGSVGElement>) => {
    if (!marking || !tool || event.button !== 0) return;
    event.preventDefault();
    const at = pointOf(event.clientX, event.clientY);
    if (writing.current) written(writing.current, field.current?.value ?? '');
    if (tool === 'text') {
      writing.current = at;
      setSpot(at);
      return;
    }
    event.currentTarget.setPointerCapture(event.pointerId);
    sketching.current = tool === 'stroke' ? [...at] : [...at, ...at];
    setDraft(made(tool, sketching.current));
  };
  const move = (event: PointerEvent<SVGSVGElement>) => {
    const points = sketching.current;
    if (!points || !tool) return;
    const events = event.nativeEvent.getCoalescedEvents?.() ?? [];
    for (const each of events.length ? events : [event.nativeEvent]) {
      const [x, y] = pointOf(each.clientX, each.clientY);
      if (tool !== 'stroke') points.splice(2, 2, x, y);
      else if (Math.hypot(x - points.at(-2)!, y - points.at(-1)!) * scale >= 1) points.push(x, y);
    }
    setDraft(made(tool, [...points]));
  };
  const up = () => {
    const points = sketching.current;
    sketching.current = null;
    setDraft(null);
    if (!points || !tool || !marking) return;
    const [x1, y1, x2, y2] = points;
    const across = Math.abs(x2 - x1) * scale;
    const down = Math.abs(y2 - y1) * scale;
    const large =
      tool === 'stroke' ||
      (tool === 'arrow' ? Math.hypot(across, down) >= LEAST : across >= LEAST && down >= LEAST);
    if (!large) return;
    marking.onMark(
      crypto.randomUUID(),
      made(tool, tool === 'blur' ? points.map((value) => Math.round(value)) : points),
    );
  };
  const cancel = () => {
    sketching.current = null;
    setDraft(null);
  };

  const key = useEffectEvent((event: globalThis.KeyboardEvent) => {
    const typing =
      'input:not([type="checkbox"], [type="radio"], [type="range"]), textarea, select, [contenteditable="true"]';
    if (!marking || (event.target as Element).closest(typing)) return;
    if ((event.key === 'Delete' || event.key === 'Backspace') && live) {
      event.preventDefault();
      marking.onMark(live, null);
      setChosen(null);
    } else if (event.key === 'Escape' && (sketching.current || tool || live)) {
      event.preventDefault();
      if (sketching.current) cancel();
      else if (tool) marking.onTool(null);
      else setChosen(null);
    }
  });
  useEffect(() => {
    const listener = (event: globalThis.KeyboardEvent) => key(event);
    window.addEventListener('keydown', listener);
    return () => window.removeEventListener('keydown', listener);
  }, []);

  const framed = drag?.rect ?? crop ?? { x: 0, y: 0, w: full.width, h: full.height };
  const begin = (handle: Handle) => (event: PointerEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ handle, start: framed, x: event.clientX, y: event.clientY, rect: framed });
  };
  const moveCrop = (event: PointerEvent<HTMLElement>) => {
    if (!drag) return;
    const dx = (event.clientX - drag.x) / scale;
    const dy = (event.clientY - drag.y) / scale;
    setDrag({ ...drag, rect: dragged(drag.start, drag.handle, dx, dy, full, cropping ?? null) });
  };
  const end = () => {
    if (!drag) return;
    setDrag(null);
    if (drag.rect === drag.start) return;
    const chosenCrop = uprightRect(drag.rect, upright, edits);
    const whole =
      chosenCrop.x === 0 &&
      chosenCrop.y === 0 &&
      chosenCrop.w === upright.width &&
      chosenCrop.h === upright.height;
    onCrop(whole ? null : chosenCrop);
  };
  const dragging = { onPointerMove: moveCrop, onPointerUp: end, onPointerCancel: end };

  const shown = (points: number[]) => {
    const pairs: string[] = [];
    for (let at = 0; at < points.length; at += 2) {
      pairs.push(shownPoint(points[at], points[at + 1], upright, edits.turn, edits.flip).join(' '));
    }
    return pairs.join(' ');
  };
  const outlined = (rect: Rect, dashed: boolean) => {
    const frame = {
      x: rect.x - 2 / scale,
      y: rect.y - 2 / scale,
      width: rect.w + 4 / scale,
      height: rect.h + 4 / scale,
      vectorEffect: 'non-scaling-stroke',
    } as const;
    return (
      <g className="pointer-events-none fill-none">
        <rect {...frame} strokeWidth={3} className="stroke-on-accent" />
        <rect
          {...frame}
          strokeWidth={1.5}
          strokeDasharray={dashed ? '4 3' : undefined}
          className="stroke-accent"
        />
      </g>
    );
  };
  const chosenMark = live ? marks.find(([id]) => id === live)?.[1] : undefined;
  const blurring = draft?.kind === 'blur' ? boundsOf(draft, edits, upright) : null;
  const typed = spot && marking && shownPoint(...spot, upright, edits.turn, edits.flip);
  const typedSize = marking ? penOf(marking.pen.width, upright, 'text') * scale : 0;

  return (
    <div
      ref={setBox}
      onPointerDown={(event) => {
        if (!(event.target as Element).closest('[data-mark], [role="toolbar"]')) setChosen(null);
      }}
      className="relative flex h-full items-center justify-center overflow-hidden p-6"
    >
      <div className="relative shrink-0 overflow-hidden" style={{ width, height }}>
        <canvas ref={canvas} role="img" aria-label={title} className="block size-full" />
        {marking && cropping === undefined && (
          <>
            <canvas
              ref={sketch}
              aria-hidden
              className="pointer-events-none absolute inset-0 size-full"
            />
            <svg
              ref={svg}
              viewBox={`${region.x} ${region.y} ${region.w} ${region.h}`}
              preserveAspectRatio="none"
              onPointerDown={down}
              onPointerMove={move}
              onPointerUp={up}
              onPointerCancel={cancel}
              className={`absolute inset-0 size-full ${
                tool === 'text'
                  ? 'cursor-text touch-none'
                  : tool
                    ? 'cursor-crosshair touch-none'
                    : 'pointer-events-none'
              }`}
            >
              {choosing &&
                marks.map(([id, mark]) => {
                  const label = t(`image.mark.${mark.kind}`);
                  const choose = () => setChosen(id);
                  const target = 'pointer-events-auto cursor-pointer';
                  if (mark.kind === 'arrow' || mark.kind === 'stroke') {
                    return (
                      <polyline
                        key={id}
                        data-mark={id}
                        role="button"
                        aria-label={label}
                        points={shown(mark.points)}
                        fill="none"
                        stroke="transparent"
                        strokeWidth={Math.max(mark.width, 12 / scale)}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        onClick={choose}
                        className={target}
                      />
                    );
                  }
                  const bounds = boundsOf(mark, edits, upright);
                  return (
                    <rect
                      key={id}
                      data-mark={id}
                      role="button"
                      aria-label={label}
                      x={bounds.x}
                      y={bounds.y}
                      width={bounds.w}
                      height={bounds.h}
                      fill="transparent"
                      onClick={choose}
                      className={target}
                    />
                  );
                })}
              {chosenMark && outlined(boundsOf(chosenMark, edits, upright), true)}
              {blurring && outlined(blurring, false)}
            </svg>
          </>
        )}
        {typed && marking && (
          <input
            ref={field}
            autoFocus
            aria-label={t('image.mark.text')}
            maxLength={500}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                written(spot, event.currentTarget.value);
              } else if (event.key === 'Escape') {
                event.preventDefault();
                writing.current = null;
                setSpot(null);
              }
            }}
            onBlur={(event) => written(spot, event.currentTarget.value)}
            style={{
              left: (typed[0] - region.x) * scale,
              top: (typed[1] - region.y) * scale - typedSize * BASELINE,
              font: fontOf(typedSize),
              color: TEXT_COLORS[marking.pen.color].light,
            }}
            className="absolute field-sizing-content min-w-8 border border-dashed border-accent bg-transparent p-0 leading-none outline outline-on-accent"
          />
        )}
        {cropping !== undefined && (
          <div
            role="group"
            aria-label={t('image.cropping')}
            {...dragging}
            onPointerDown={begin('move')}
            className={`absolute touch-none border-2 border-on-accent shadow-[0_0_0_9999px_var(--color-scrim)] outline outline-accent ${CURSORS.move}`}
            style={{
              left: framed.x * scale,
              top: framed.y * scale,
              width: framed.w * scale,
              height: framed.h * scale,
            }}
          >
            {HANDLES.map((handle) => (
              <span
                key={handle}
                data-handle={handle}
                {...dragging}
                onPointerDown={begin(handle)}
                className={`absolute size-3.5 -translate-1/2 rounded-sm border border-accent bg-surface ${CURSORS[handle]}`}
                style={place(handle)}
              />
            ))}
          </div>
        )}
      </div>
      {live && anchor && box && marking && (
        <Floating anchor={anchor} within={box} label={t('image.mark')}>
          <button
            type="button"
            onClick={() => {
              marking.onMark(live, null);
              setChosen(null);
            }}
            className={`${iconButton} flex gap-1.5`}
          >
            <Trash2 size={16} aria-hidden />
            {t('pdf.remove')}
          </button>
        </Floating>
      )}
    </div>
  );
}
