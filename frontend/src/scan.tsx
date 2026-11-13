import { Camera, ImagePlus, LoaderCircle, Maximize, Trash2 } from 'lucide-react';
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type PointerEvent,
} from 'react';
import { postJson, upload } from './api';
import { Cancel, Modal } from './dialogs';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { runJob } from './jobs';
import { button, field, iconButton, primaryButton } from './styles';
import { errorMessage, type TreeNode } from './tree';
import { useFilePicker } from './upload';

type Point = [number, number];
/** Top left first and on clockwise, each across and down the upright photo from 0 to 1. */
type Corners = [Point, Point, Point, Point];

const WHOLE: Corners = [
  [0, 0],
  [1, 0],
  [1, 1],
  [0, 1],
];
const CORNERS: MessageKey[] = [
  'scan.corner.topLeft',
  'scan.corner.topRight',
  'scan.corner.bottomRight',
  'scan.corner.bottomLeft',
];
const PHOTOS = 'image/jpeg,image/png,image/webp';
const STEP = 0.01;

interface Shot {
  key: number;
  url: string;
  blob: string | null;
  corners: Corners | null;
  error: Error | null;
}

/** The file a scan attached to a mail becomes. */
export interface Scanned {
  sha256: string;
  size: number;
  media_type: string;
  name: string;
}

const clamp = (value: number) => Math.min(1, Math.max(0, value));

function today(): string {
  const now = new Date();
  const two = (value: number) => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}`;
}

/** A scan into a folder, or the top of the user's own documents, becomes a file there; one for
 * a mail comes back to be attached. */
type Into =
  | { attached?: false; parent: string | null; onDone: (made: TreeNode) => void }
  | { attached: true; onDone: (made: Scanned) => void };

/** Pages photographed one after another, each with the corners the server finds on it, which
 * the user may move, made into one PDF file whose text is read (D43). */
export function ScanDialog({ onClose, ...props }: Into & { onClose: () => void }) {
  const { t, formatDays } = useI18n();
  const [shots, setShots] = useState<Shot[]>([]);
  const [shown, setShown] = useState<number | null>(null);
  const [title, setTitle] = useState(() => `${t('scan.title')} ${formatDays(today(), today())}`);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<Error | null>(null);
  const counter = useRef(0);
  const urls = useRef<string[]>([]);
  const touch = typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches;

  useEffect(() => () => urls.current.forEach((url) => URL.revokeObjectURL(url)), []);

  const change = (key: number, fields: Partial<Shot>) =>
    setShots((all) => all.map((shot) => (shot.key === key ? { ...shot, ...fields } : shot)));

  const add = (files: File[]) => {
    const added = files.map((file) => {
      const url = URL.createObjectURL(file);
      urls.current.push(url);
      return {
        file,
        shot: { key: ++counter.current, url, blob: null, corners: null, error: null },
      };
    });
    setShots((all) => [...all, ...added.map((each) => each.shot)]);
    setShown(added[added.length - 1].shot.key);
    for (const { file, shot } of added) {
      void (async () => {
        try {
          const { sha256 } = await upload(file);
          change(shot.key, { blob: sha256 });
          const found = await postJson<{ corners: Corners }>('/api/scans/corners', {
            blob: sha256,
          });
          change(shot.key, { corners: found.corners });
        } catch (error) {
          change(shot.key, { error: error as Error });
        }
      })();
    }
  };
  const camera = useFilePicker(add, { accept: PHOTOS, multiple: false, camera: true });
  const photos = useFilePicker(add, { accept: PHOTOS });

  const current = shots.find((shot) => shot.key === shown) ?? shots[shots.length - 1];
  const ready = shots.length > 0 && shots.every((shot) => shot.blob && shot.corners);

  const remove = (key: number) => {
    const at = shots.findIndex((shot) => shot.key === key);
    const left = shots.filter((shot) => shot.key !== key);
    setShots(left);
    setShown(left[Math.min(at, left.length - 1)]?.key ?? null);
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    setSaving(true);
    setFailure(null);
    const pages = shots.map((shot) => ({ blob: shot.blob, corners: shot.corners }));
    try {
      const into = props.attached ? { attached: true } : { parent: props.parent };
      props.onDone(await runJob<never>('scan', { ...into, pages, title }, title));
    } catch (error) {
      setFailure(error as Error);
      setSaving(false);
    }
  }

  return (
    <Modal heading={t('scan.heading')} wide onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        {camera.element}
        {photos.element}
        {current && (
          <Outline
            shot={current}
            onMove={(corners) => change(current.key, { corners })}
            onRemove={() => remove(current.key)}
          />
        )}
        {shots.length > 0 && (
          <ol aria-label={t('scan.pages')} className="flex gap-2 overflow-x-auto pb-1">
            {shots.map((shot, index) => (
              <li key={shot.key} className="shrink-0">
                <button
                  type="button"
                  aria-label={`${t('scan.page')} ${index + 1}`}
                  aria-current={shot.key === current?.key}
                  onClick={() => setShown(shot.key)}
                  className={`relative block h-20 w-16 overflow-hidden rounded border-2 ${
                    shot.key === current?.key ? 'border-accent' : 'border-line'
                  }`}
                >
                  <img src={shot.url} alt="" className="size-full object-cover" />
                  <span className="absolute right-0 bottom-0 rounded-tl bg-raised px-1 text-xs">
                    {index + 1}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        )}
        <div className="flex flex-wrap gap-2">
          {touch && (
            <button type="button" onClick={camera.open} className={primaryButton}>
              <Camera size={16} aria-hidden />
              {t('scan.take')}
            </button>
          )}
          <button type="button" onClick={photos.open} className={button}>
            <ImagePlus size={16} aria-hidden />
            {t('scan.add')}
          </button>
        </div>
        {shots.length > 0 && (
          <label className="flex flex-col gap-1 text-sm">
            {t('tree.name')}
            <input
              required
              maxLength={196}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className={field}
            />
          </label>
        )}
        {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={!ready || saving} className={primaryButton}>
            {saving && <LoaderCircle size={16} aria-hidden className="animate-spin" />}
            {t(props.attached ? 'scan.attach' : 'scan.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** The photo with the page's outline over it, each corner dragged or moved with the arrow keys. */
function Outline({
  shot,
  onMove,
  onRemove,
}: {
  shot: Shot;
  onMove: (corners: Corners) => void;
  onRemove: () => void;
}) {
  const { t } = useI18n();
  const frame = useRef<HTMLDivElement>(null);
  const corners = shot.corners;

  const moved = (index: number, point: Point) =>
    corners && onMove(corners.map((each, at) => (at === index ? point : each)) as Corners);

  const drag = (index: number) => (event: PointerEvent<HTMLButtonElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId) || !frame.current) return;
    const box = frame.current.getBoundingClientRect();
    moved(index, [
      clamp((event.clientX - box.left) / box.width),
      clamp((event.clientY - box.top) / box.height),
    ]);
  };

  const keyed = (index: number) => (event: KeyboardEvent<HTMLButtonElement>) => {
    const by: Record<string, Point> = {
      ArrowLeft: [-STEP, 0],
      ArrowRight: [STEP, 0],
      ArrowUp: [0, -STEP],
      ArrowDown: [0, STEP],
    };
    const step = by[event.key];
    if (!step || !corners) return;
    event.preventDefault();
    const [x, y] = corners[index];
    moved(index, [clamp(x + step[0]), clamp(y + step[1])]);
  };

  return (
    <div className="flex flex-col items-center gap-2">
      <div ref={frame} className="relative touch-none select-none">
        <img
          src={shot.url}
          alt=""
          draggable={false}
          className="block max-h-[55dvh] max-w-full rounded"
        />
        {corners && (
          <svg
            viewBox="0 0 1 1"
            preserveAspectRatio="none"
            aria-hidden
            className="pointer-events-none absolute inset-0 size-full"
          >
            <polygon
              points={corners.map(([x, y]) => `${x},${y}`).join(' ')}
              vectorEffect="non-scaling-stroke"
              strokeWidth={2}
              className="fill-accent/15 stroke-accent"
            />
          </svg>
        )}
        {corners?.map(([x, y], index) => (
          <button
            key={CORNERS[index]}
            type="button"
            aria-label={t(CORNERS[index])}
            title={t(CORNERS[index])}
            style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
            onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)}
            onPointerMove={drag(index)}
            onKeyDown={keyed(index)}
            className="absolute size-9 -translate-x-1/2 -translate-y-1/2 cursor-move touch-none rounded-full border-2 border-accent bg-raised/60"
          />
        ))}
        {!corners && !shot.error && (
          <span className="absolute inset-0 flex items-center justify-center">
            <LoaderCircle
              size={32}
              aria-label={t('scan.preparing')}
              className="animate-spin text-accent"
            />
          </span>
        )}
      </div>
      {shot.error && <p className="text-sm text-danger">{errorMessage(shot.error, t)}</p>}
      <div className="flex gap-1">
        <button
          type="button"
          disabled={!corners}
          aria-label={t('scan.whole')}
          title={t('scan.whole')}
          onClick={() => onMove(WHOLE)}
          className={iconButton}
        >
          <Maximize size={16} aria-hidden />
        </button>
        <button
          type="button"
          aria-label={t('scan.remove')}
          title={t('scan.remove')}
          onClick={onRemove}
          className={iconButton}
        >
          <Trash2 size={16} aria-hidden />
        </button>
      </div>
    </div>
  );
}
