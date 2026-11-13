import { useQueryClient } from '@tanstack/react-query';
import { EyeOff, MessageSquare, MessageSquarePlus, Trash2 } from 'lucide-react';
import {
  useCallback,
  useEffect,
  useEffectEvent,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type PointerEvent,
} from 'react';
import { createPortal } from 'react-dom';
import * as Y from 'yjs';
import { useSession } from '../auth';
import { threadsKey, useDesk, useThreads, type PageAnchor, type PageRect } from '../comments';
import {
  HIGHLIGHTS,
  TEXT_COLORS,
  type Highlight,
  type Swatch,
  type TextColor,
} from '../editor/colors';
import { watchNews } from '../editor/news';
import { Floating } from '../floating';
import { useI18n } from '../i18n';
import { PenChoice, SwatchButton, type Pen } from '../pen';
import { joinRoom, useRecheck } from '../room';
import { iconButton } from '../styles';
import {
  chosenIn,
  drawn,
  marksOf,
  OWN,
  placeOf,
  pointOn,
  redactionsOf,
  spanned,
  type Chosen,
  type Mark,
  type Redaction,
  type Viewport,
} from './notes';
import { fieldsIn, type Filled } from './form';

/** The file's own room: its highlights and strokes, its form's values, what is marked to be
 * blacked out of a copy, and what this reader takes back of theirs. */
export interface FileRoom {
  write: (change: (marks: Y.Map<Mark>) => void) => void;
  redact: (change: (redactions: Y.Map<Redaction>) => void) => void;
  fields: Y.Map<Filled>;
  fill: (change: (fields: Y.Map<Filled>) => void, origin: string) => void;
  undo: Y.UndoManager;
  subscribe: (changed: () => void) => () => void;
  current: () => readonly [string, Mark][];
  redactions: () => readonly [string, Redaction][];
}

/** Joins the file's room once it has synced; the room also tells when its comments change. */
export function useFileRoom(room: string, fileId: string): FileRoom | null {
  const recheck = useRecheck(fileId);
  const queryClient = useQueryClient();
  const [joined, setJoined] = useState<FileRoom | null>(null);
  useEffect(() => {
    const doc = new Y.Doc();
    const marks = marksOf(doc);
    const fields = fieldsIn(doc);
    const redactions = redactionsOf(doc);
    // A field's typing and what the form's scripts reckon of it make one step, which the form
    // ends when another field is entered; a note is a step of its own.
    const undo = new Y.UndoManager([marks, fields, redactions], {
      trackedOrigins: new Set([OWN]),
      captureTimeout: Infinity,
    });
    const listeners = new Set<() => void>();
    let snapshot: readonly [string, Mark][] = [];
    let marked: readonly [string, Redaction][] = [];
    const tell = () => {
      for (const listener of listeners) listener();
    };
    marks.observe(() => {
      snapshot = [...marks.entries()];
      tell();
    });
    redactions.observe(() => {
      marked = [...redactions.entries()];
      tell();
    });
    const step = (change: () => void) => {
      undo.stopCapturing();
      doc.transact(change, OWN);
      undo.stopCapturing();
    };
    const { provider, leave } = joinRoom(room, doc, recheck);
    let ready = false;
    provider.on('sync', (synced: boolean) => {
      if (!synced || ready) return;
      ready = true;
      snapshot = [...marks.entries()];
      marked = [...redactions.entries()];
      setJoined({
        write: (change) => step(() => change(marks)),
        redact: (change) => step(() => change(redactions)),
        fields,
        fill: (change, origin) => doc.transact(() => change(fields), origin),
        undo,
        subscribe: (changed) => {
          listeners.add(changed);
          return () => listeners.delete(changed);
        },
        current: () => snapshot,
        redactions: () => marked,
      });
    });
    watchNews(provider, 'comments', () =>
      queryClient.invalidateQueries({ queryKey: threadsKey(fileId) }),
    );
    return () => {
      leave();
      undo.destroy();
      doc.destroy();
      setJoined(null);
    };
  }, [room, fileId, recheck, queryClient]);
  return joined;
}

const NONE: readonly [string, Mark][] = [];
const unsubscribed = () => () => {};

export function useMarks(room: FileRoom | null): readonly [string, Mark][] {
  return useSyncExternalStore(room?.subscribe ?? unsubscribed, room?.current ?? (() => NONE));
}

const UNMARKED: readonly [string, Redaction][] = [];

export function useRedactions(room: FileRoom | null): readonly [string, Redaction][] {
  return useSyncExternalStore(
    room?.subscribe ?? unsubscribed,
    room?.redactions ?? (() => UNMARKED),
  );
}

export type Tool = 'read' | 'draw' | 'pin' | 'redact';

const separator = <span aria-hidden className="mx-1 h-5 w-px bg-line" />;

/** A thread on a page, as the page shows it. */
export interface Placed {
  id: string;
  anchor: PageAnchor;
}

/** The side of a point comment's icon in points, its top left corner on the point, as the backend
 * writes it into the file. */
const ICON = 20;

function area(viewport: Viewport, rects: PageRect[]): string {
  return rects
    .map((rect) => {
      const { x, y, width, height } = drawn(viewport, rect);
      return `M${x} ${y}h${width}v${height}h${-width}Z`;
    })
    .join('');
}

function line(viewport: Viewport, points: number[]): string {
  const at: string[] = [];
  for (let index = 0; index < points.length; index += 2) {
    const [x, y] = viewport.convertToViewportPoint(points[index], points[index + 1]);
    at.push(`${x} ${y}`);
  }
  return `M${at[0]}L${(at.length > 1 ? at.slice(1) : at).join(' ')}`;
}

/** The box of a mark in the overlay's units. */
export function boundsOf(viewport: Viewport, mark: Mark | Redaction): PageRect {
  if (mark.kind !== 'stroke') {
    const boxes = mark.rects.map((rect) => drawn(viewport, rect));
    return [
      Math.min(...boxes.map((box) => box.x)),
      Math.min(...boxes.map((box) => box.y)),
      Math.max(...boxes.map((box) => box.x + box.width)),
      Math.max(...boxes.map((box) => box.y + box.height)),
    ];
  }
  const xs: number[] = [];
  const ys: number[] = [];
  for (let index = 0; index < mark.points.length; index += 2) {
    const [x, y] = viewport.convertToViewportPoint(mark.points[index], mark.points[index + 1]);
    xs.push(x);
    ys.push(y);
  }
  const reach = mark.width / 2;
  return [
    Math.min(...xs) - reach,
    Math.min(...ys) - reach,
    Math.max(...xs) + reach,
    Math.max(...ys) + reach,
  ];
}

/** What a page shows over the file: its highlights, strokes, threads and what is marked to be
 * blacked out, and the stroke or rectangle being drawn or the point being chosen. */
export function PageNotes({
  page,
  viewport,
  marks,
  redactions,
  threads,
  draft,
  active,
  chosen,
  tool,
  pen,
  editable,
  onChoose,
  onShow,
  onStroke,
  onPin,
  onBox,
}: {
  page: number;
  viewport: Viewport;
  marks: readonly [string, Mark][];
  redactions: readonly [string, Redaction][];
  threads: readonly Placed[];
  draft: PageAnchor | null;
  active: string | null;
  chosen: string | null;
  tool: Tool;
  pen: { color: TextColor; width: number };
  editable: boolean;
  onChoose: (mark: string) => void;
  onShow: (thread: string) => void;
  onStroke: (page: number, points: number[]) => void;
  onPin: (page: number, at: [number, number]) => void;
  onBox: (page: number, rect: PageRect) => void;
}) {
  const { t } = useI18n();
  const svg = useRef<SVGSVGElement>(null);
  const drawing = useRef<number[] | null>(null);
  const [stroke, setStroke] = useState<number[] | null>(null);
  const framing = useRef<[[number, number], [number, number]] | null>(null);
  const [frame, setFrame] = useState<PageRect | null>(null);
  const hatch = `ponistra-hatch-${page}`;
  const pointsOf = (event: PointerEvent<SVGSVGElement>) => {
    const box = svg.current!.getBoundingClientRect();
    const events = event.nativeEvent.getCoalescedEvents?.() ?? [];
    return (events.length ? events : [event.nativeEvent]).map((each) =>
      pointOn(viewport, box, each.clientX, each.clientY),
    );
  };

  const down = (event: PointerEvent<SVGSVGElement>) => {
    if (tool === 'read' || event.button !== 0) return;
    if (tool === 'redact' && (event.target as Element).closest('[data-mark]')) return;
    event.preventDefault();
    const [at] = pointsOf(event);
    if (tool === 'pin') return onPin(page, at);
    event.currentTarget.setPointerCapture(event.pointerId);
    if (tool === 'redact') {
      framing.current = [at, at];
      setFrame([...at, ...at]);
      return;
    }
    drawing.current = [...at];
    setStroke(drawing.current);
  };
  const move = (event: PointerEvent<SVGSVGElement>) => {
    const corners = framing.current;
    if (corners) {
      corners[1] = pointsOf(event).at(-1)!;
      const [[x1, y1], [x2, y2]] = corners;
      setFrame([Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)]);
      return;
    }
    const points = drawing.current;
    if (!points) return;
    for (const [x, y] of pointsOf(event)) {
      const [lastX, lastY] = points.slice(-2);
      if (Math.hypot(x - lastX, y - lastY) >= 0.5) points.push(x, y);
    }
    setStroke([...points]);
  };
  const up = () => {
    const corners = framing.current;
    framing.current = null;
    setFrame(null);
    const rect = corners && spanned(...corners);
    if (rect) onBox(page, rect);
    const points = drawing.current;
    drawing.current = null;
    setStroke(null);
    if (points) onStroke(page, points);
  };
  const cancel = () => {
    framing.current = null;
    setFrame(null);
    drawing.current = null;
    setStroke(null);
  };

  const chosenMark = [...marks, ...redactions].find(([id]) => id === chosen)?.[1];
  const outline = chosenMark && boundsOf(viewport, chosenMark);
  const pinOf = (anchor: PageAnchor & { at: [number, number] }) => {
    const [x, y] = viewport.convertToViewportPoint(...anchor.at);
    return { x, y };
  };
  const anchorOf = (anchor: PageAnchor, current: boolean, label: string, onClick?: () => void) => {
    const fill = current ? 'fill-comment-active' : 'fill-comment';
    if ('rects' in anchor) {
      return (
        <path
          d={area(viewport, anchor.rects)}
          role={onClick && 'button'}
          aria-label={label}
          onClick={onClick}
          className={`${fill} ${onClick ? 'pointer-events-auto cursor-pointer' : ''}`}
        />
      );
    }
    const { x, y } = pinOf(anchor);
    return (
      <g
        role={onClick && 'button'}
        aria-label={label}
        onClick={onClick}
        className={onClick ? 'pointer-events-auto cursor-pointer' : ''}
      >
        <rect x={x} y={y} width={ICON} height={ICON} rx={3} className={fill} />
        <MessageSquare
          x={x + 3}
          y={y + 3}
          width={ICON - 6}
          height={ICON - 6}
          aria-hidden
          className="text-ink"
        />
      </g>
    );
  };

  return (
    <svg
      ref={svg}
      viewBox={`0 0 ${viewport.width} ${viewport.height}`}
      preserveAspectRatio="none"
      data-page={page}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={cancel}
      className={`absolute inset-0 size-full overflow-visible ${
        tool === 'draw' || tool === 'redact'
          ? 'pointer-events-auto cursor-crosshair touch-none'
          : tool === 'pin'
            ? 'pointer-events-auto cursor-copy'
            : ''
      }`}
    >
      <defs>
        <pattern
          id={hatch}
          width={6}
          height={6}
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <line x1={0} y1={0} x2={0} y2={6} strokeWidth={2} className="stroke-redact" />
        </pattern>
      </defs>
      {threads.map((thread) => (
        <g key={thread.id} data-thread={thread.id}>
          {anchorOf(thread.anchor, thread.id === active, t('pdf.comment'), () => onShow(thread.id))}
        </g>
      ))}
      {draft && <g data-draft>{anchorOf(draft, true, t('comment.new'))}</g>}
      {marks.map(([id, mark]) => {
        const clickable = editable && tool === 'read';
        const choose = clickable ? () => onChoose(id) : undefined;
        return mark.kind === 'highlight' ? (
          <path
            key={id}
            data-mark={id}
            role={clickable ? 'button' : undefined}
            aria-label={t('pdf.mark.highlight')}
            d={area(viewport, mark.rects)}
            fill={HIGHLIGHTS[mark.color]?.light}
            onClick={choose}
            className={clickable ? 'pointer-events-auto cursor-pointer' : ''}
          />
        ) : (
          <g
            key={id}
            data-mark={id}
            role={clickable ? 'button' : undefined}
            aria-label={t('pdf.mark.stroke')}
            onClick={choose}
            className={clickable ? 'pointer-events-auto cursor-pointer' : ''}
          >
            <path
              d={line(viewport, mark.points)}
              fill="none"
              stroke={TEXT_COLORS[mark.color]?.light}
              strokeWidth={mark.width}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {clickable && (
              <path
                d={line(viewport, mark.points)}
                fill="none"
                stroke="transparent"
                strokeWidth={mark.width + 8}
                strokeLinecap="round"
              />
            )}
          </g>
        );
      })}
      {redactions.map(([id, redaction]) => {
        const clickable = editable && (tool === 'read' || tool === 'redact');
        return (
          <path
            key={id}
            data-mark={id}
            role={clickable ? 'button' : undefined}
            aria-label={t('pdf.mark.redaction')}
            d={area(viewport, redaction.rects)}
            fill={`url(#${hatch})`}
            strokeWidth={1.5}
            vectorEffect="non-scaling-stroke"
            onClick={clickable ? () => onChoose(id) : undefined}
            className={`stroke-redact ${clickable ? 'pointer-events-auto cursor-pointer' : ''}`}
          />
        );
      })}
      {frame && (
        <path
          data-framing
          d={area(viewport, [frame])}
          fill={`url(#${hatch})`}
          strokeWidth={1.5}
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
          className="stroke-redact"
        />
      )}
      {outline && (
        <rect
          x={outline[0] - 2}
          y={outline[1] - 2}
          width={outline[2] - outline[0] + 4}
          height={outline[3] - outline[1] + 4}
          strokeDasharray="4 3"
          vectorEffect="non-scaling-stroke"
          className="fill-none stroke-focus"
        />
      )}
      {stroke && (
        <path
          d={line(viewport, stroke)}
          fill="none"
          stroke={TEXT_COLORS[pen.color].light}
          strokeWidth={pen.width}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
    </svg>
  );
}

/** What pdf.js's page view holds that the notes need. */
interface PageView {
  div: HTMLDivElement;
  pdfPage: unknown;
  viewport: Viewport & { clone(params: { scale: number }): Viewport };
}

/** What the notes need of pdf.js's viewer. */
export interface Pages {
  pagesCount: number;
  getPageView(index: number): unknown;
  scrollPageIntoView(params: { pageNumber: number; destArray: unknown[] }): void;
}

/** Whether the file may be blacked out, and what saving its blacked-out copy needs said. */
export interface Redacting {
  /** Why the file cannot be blacked out, or null where it can. */
  refusal: string | null;
  signed: boolean;
  onSave: () => void;
}

/** The file's notes over its pages, the bars that make them, and its threads' places for the
 * comments beside it. */
export function FileNotes({
  pages,
  box,
  field,
  room,
  fileId,
  editable,
  tool,
  redacting,
  onTool,
  onNoted,
}: {
  pages: Pages;
  box: HTMLElement;
  field: HTMLElement;
  room: FileRoom | null;
  fileId: string;
  editable: boolean;
  tool: Tool;
  redacting: Redacting;
  onTool: (tool: Tool) => void;
  onNoted: (noted: boolean) => void;
}) {
  const { t } = useI18n();
  const desk = useDesk();
  const me = useSession().data?.user?.id ?? null;
  const marks = useMarks(room);
  const redactions = useRedactions(room);
  const threads = useThreads(fileId);
  const [hosts, setHosts] = useState<HTMLDivElement[]>([]);
  const [, setLoaded] = useState(0);
  const [selected, setSelected] = useState<Chosen | null>(null);
  const [chosen, setChosen] = useState<{ id: string; bounds: DOMRectReadOnly } | null>(null);
  const [pen, setPen] = useState<Pen>({ color: 'red', width: 2 });
  const pressing = useRef(false);

  const viewOf = useCallback(
    (page: number) => pages.getPageView(page - 1) as PageView | undefined,
    [pages],
  );
  const viewportOf = useCallback(
    (page: number) => {
      const view = viewOf(page);
      return view?.pdfPage ? view.viewport.clone({ scale: 1 }) : null;
    },
    [viewOf],
  );
  const markBounds = useCallback(
    (id: string) =>
      [...box.querySelectorAll(`[data-mark="${CSS.escape(id)}"]`)]
        .map((element) => element.getBoundingClientRect())
        .find((bounds) => bounds.width || bounds.height) ?? null,
    [box],
  );

  useEffect(() => {
    const made = Array.from({ length: pages.pagesCount }, () => {
      const host = document.createElement('div');
      host.className = 'ponistra-notes';
      return host;
    });
    const attach = () =>
      made.forEach((host, index) => {
        const view = viewOf(index + 1);
        if (view && host.parentNode !== view.div) view.div.append(host);
      });
    const sized = new Set<number>();
    const look = () => {
      attach();
      const before = sized.size;
      made.forEach((_, index) => viewOf(index + 1)?.pdfPage && sized.add(index));
      if (sized.size > before) setLoaded((count) => count + 1);
    };
    // pdf.js empties a page of all but its own layers each time it draws it again, and a page
    // knows its own size only once it is first drawn.
    const watcher = new MutationObserver(look);
    for (let page = 1; page <= made.length; page++) {
      const view = viewOf(page);
      if (view) watcher.observe(view.div, { childList: true });
    }
    look();
    setHosts(made);
    return () => {
      watcher.disconnect();
      made.forEach((host) => host.remove());
      setHosts([]);
    };
  }, [pages, viewOf]);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    const look = () => {
      if (pressing.current) return;
      setSelected(chosenIn(document.getSelection(), box, viewportOf));
      setChosen((now) => now && { id: now.id, bounds: markBounds(now.id) ?? now.bounds });
    };
    document.addEventListener('selectionchange', look, { signal });
    box.addEventListener('scroll', look, { signal, passive: true });
    box.addEventListener(
      'pointerdown',
      (event) => {
        pressing.current = true;
        setSelected(null);
        if (!(event.target as Element).closest('[data-mark]')) setChosen(null);
      },
      { signal },
    );
    const lift = () => {
      if (!pressing.current) return;
      pressing.current = false;
      look();
    };
    window.addEventListener('pointerup', lift, { signal });
    window.addEventListener('pointercancel', lift, { signal });
    const resized = new ResizeObserver(look);
    resized.observe(box);
    if (box.firstElementChild) resized.observe(box.firstElementChild);
    return () => {
      controller.abort();
      resized.disconnect();
    };
  }, [box, viewportOf, markBounds]);

  const noted = marks.length > 0;
  useEffect(() => onNoted(noted), [noted, onNoted]);

  const placed = useMemo(
    () =>
      (threads.data ?? []).flatMap((thread) =>
        thread.tab === null &&
        'page' in thread.anchor &&
        (!thread.resolved_at || thread.id === desk?.active)
          ? [{ id: thread.id, anchor: thread.anchor }]
          : [],
      ),
    [threads.data, desk?.active],
  );
  const order = useMemo(
    () =>
      (threads.data ?? [])
        .flatMap((thread) =>
          'page' in thread.anchor ? [{ id: thread.id, anchor: thread.anchor }] : [],
        )
        .toSorted((a, b) => {
          const [ax, ay] = placeOf(a.anchor);
          const [bx, by] = placeOf(b.anchor);
          return a.anchor.page - b.anchor.page || by - ay || ax - bx;
        })
        .map(({ id }) => id)
        .join(' '),
    [threads.data],
  );
  const place = desk?.place;
  useEffect(() => place?.({ order: order ? order.split(' ') : [], lost: [] }), [place, order]);
  useEffect(() => () => place?.(null), [place]);

  const target = placed.find((thread) => thread.id === desk?.active)?.anchor ?? null;
  const reveal = useEffectEvent(() => {
    if (!target) return;
    const view = viewOf(target.page);
    if (!view) return;
    const [x, y] = placeOf(target);
    const [, top] = view.viewport.convertToViewportPoint(x, y);
    const spot = view.div.getBoundingClientRect().top + top;
    const shown = box.getBoundingClientRect();
    if (spot >= shown.top + 24 && spot <= shown.bottom - 24) return;
    pages.scrollPageIntoView({
      pageNumber: target.page,
      destArray: [null, { name: 'XYZ' }, null, y + 24, null],
    });
  });
  const targetKey = target && JSON.stringify(target);
  useEffect(() => reveal(), [targetKey, desk?.shown]);

  const highlight = (color: Highlight) => {
    if (!room || !selected) return;
    const at = new Date().toISOString();
    room.write((held) => {
      for (const { page, rects } of selected.parts) {
        held.set(crypto.randomUUID(), { kind: 'highlight', page, color, rects, by: me, at });
      }
    });
    document.getSelection()?.removeAllRanges();
  };
  const comment = () => {
    if (!selected) return;
    const [{ page, rects }] = selected.parts;
    desk?.start({ tab: null, anchor: { page, rects }, quote: selected.quote });
    document.getSelection()?.removeAllRanges();
  };
  const stroke = (page: number, points: number[]) =>
    room?.write((held) =>
      held.set(crypto.randomUUID(), {
        kind: 'stroke',
        page,
        color: pen.color,
        width: pen.width,
        points,
        by: me,
        at: new Date().toISOString(),
      }),
    );
  const pin = (page: number, at: [number, number]) => {
    desk?.start({ tab: null, anchor: { page, at }, quote: '' });
    onTool('read');
  };
  const frame = (page: number, rect: PageRect) =>
    room?.redact((held) =>
      held.set(crypto.randomUUID(), {
        kind: 'redaction',
        page,
        rects: [rect],
        by: me,
        at: new Date().toISOString(),
      }),
    );
  const blackOut = () => {
    if (!room || !selected) return;
    const at = new Date().toISOString();
    room.redact((held) => {
      for (const { page, rects } of selected.parts) {
        held.set(crypto.randomUUID(), { kind: 'redaction', page, rects, by: me, at });
      }
    });
    document.getSelection()?.removeAllRanges();
  };
  const hiding = chosen !== null && redactions.some(([id]) => id === chosen.id);
  const live = chosen && (hiding || marks.some(([id]) => id === chosen.id)) ? chosen : null;
  const remove = () => {
    if (!live) return;
    if (hiding) room?.redact((held) => held.delete(live.id));
    else room?.write((held) => held.delete(live.id));
    setChosen(null);
  };

  const key = useEffectEvent((event: globalThis.KeyboardEvent) => {
    const typing =
      'input:not([type="checkbox"], [type="radio"]), textarea, [contenteditable="true"]';
    if ((event.target as Element).closest(typing)) return;
    const letter = event.key.toLowerCase();
    if ((event.ctrlKey || event.metaKey) && !event.altKey && (letter === 'z' || letter === 'y')) {
      if (!room || !editable) return;
      event.preventDefault();
      if (letter === 'y' || event.shiftKey) room.undo.redo();
      else room.undo.undo();
    } else if ((event.key === 'Delete' || event.key === 'Backspace') && live) {
      event.preventDefault();
      remove();
    } else if (event.key === 'Escape' && (tool !== 'read' || live)) {
      event.preventDefault();
      if (tool !== 'read') onTool('read');
      else setChosen(null);
    }
  });
  useEffect(() => {
    const listener = (event: globalThis.KeyboardEvent) => key(event);
    window.addEventListener('keydown', listener);
    return () => window.removeEventListener('keydown', listener);
  }, []);

  const drafted = desk?.draft?.tab === null ? desk.draft.anchor : null;
  const draft = drafted && 'page' in drafted ? drafted : null;

  return (
    <>
      {hosts.map((host, index) => {
        const page = index + 1;
        const viewport = viewportOf(page);
        return (
          viewport &&
          createPortal(
            <PageNotes
              page={page}
              viewport={viewport}
              marks={marks.filter(([, mark]) => mark.page === page)}
              redactions={redactions.filter(([, redaction]) => redaction.page === page)}
              threads={placed.filter((thread) => thread.anchor.page === page)}
              draft={draft?.page === page ? draft : null}
              active={desk?.active ?? null}
              chosen={live?.id ?? null}
              tool={tool}
              pen={pen}
              editable={editable && room !== null}
              onChoose={(id) => setChosen({ id, bounds: markBounds(id)! })}
              onShow={(thread) => desk?.show(thread)}
              onStroke={stroke}
              onPin={pin}
              onBox={frame}
            />,
            host,
          )
        );
      })}
      {tool === 'read' && selected && (
        <Floating anchor={selected.bounds} within={field} label={t('pdf.selection')}>
          {editable && room && (
            <>
              {(Object.entries(HIGHLIGHTS) as [Highlight, Swatch][]).map(([name, swatch]) => (
                <SwatchButton
                  key={name}
                  swatch={swatch}
                  label={`${t('pdf.highlight')}: ${t(`color.${name}`)}`}
                  onClick={() => highlight(name)}
                />
              ))}
              {separator}
              <button
                type="button"
                disabled={redacting.refusal !== null}
                title={redacting.refusal ?? undefined}
                onClick={blackOut}
                className={`${iconButton} flex gap-1.5 disabled:opacity-40`}
              >
                <EyeOff size={16} aria-hidden />
                {t('pdf.redact')}
              </button>
              {separator}
            </>
          )}
          <button type="button" onClick={comment} className={`${iconButton} flex gap-1.5`}>
            <MessageSquarePlus size={16} aria-hidden />
            {t('command.comment')}
          </button>
        </Floating>
      )}
      {(tool === 'read' || tool === 'redact') && live && (
        <Floating
          anchor={live.bounds}
          within={field}
          label={hiding ? t('pdf.mark.redaction') : t('pdf.mark')}
        >
          <button type="button" onClick={remove} className={`${iconButton} flex gap-1.5`}>
            <Trash2 size={16} aria-hidden />
            {t('pdf.remove')}
          </button>
        </Floating>
      )}
      {tool !== 'read' && (
        <div
          role="toolbar"
          aria-label={
            tool === 'draw' ? t('pdf.pen') : tool === 'pin' ? t('pdf.pin') : t('pdf.redact.tool')
          }
          className="absolute top-3 left-1/2 z-20 flex w-max max-w-[calc(100%-1rem)] -translate-x-1/2 flex-wrap items-center justify-center gap-0.5 rounded border border-line bg-raised p-1 text-sm shadow-lg"
        >
          {tool === 'draw' ? (
            <PenChoice pen={pen} onPen={setPen} />
          ) : tool === 'pin' ? (
            <span className="px-2 text-muted">{t('pdf.pin.hint')}</span>
          ) : (
            <>
              <span className="px-2 text-muted">{t('pdf.redact.hint')}</span>
              {redacting.signed && (
                <span className="px-2 text-muted">{t('pdf.redact.signed')}</span>
              )}
              {separator}
              <button
                type="button"
                disabled={!redactions.length}
                onClick={redacting.onSave}
                className={`${iconButton} px-2 disabled:opacity-40`}
              >
                {t('pdf.redact.save')}
              </button>
            </>
          )}
          {separator}
          <button type="button" onClick={() => onTool('read')} className={`${iconButton} px-2`}>
            {t('pdf.tool.close')}
          </button>
        </div>
      )}
    </>
  );
}
