import { RenderingCancelledException, type PDFDocumentProxy } from 'pdfjs-dist';
import {
  ChevronLeft,
  ChevronRight,
  FileOutput,
  FilePlus,
  FolderTree,
  Redo2,
  RotateCcw,
  RotateCw,
  Save,
  Trash2,
  Undo2,
  Upload,
  X,
  type LucideIcon,
} from 'lucide-react';
import {
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  type DragEvent,
  type KeyboardEvent,
  type MouseEvent,
} from 'react';
import { useBlocker, useNavigate } from 'react-router';
import { postJson, upload } from '../api';
import { ConfirmDialog, FilePickDialog, NameDialog } from '../dialogs';
import { Loading } from '../frame';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { runJob } from '../jobs';
import { Menu, MenuItem } from '../menu';
import { watchNear } from '../near';
import { button, iconButton, primaryButton } from '../styles';
import { errorMessage, nodeHref, useTreeChange, type TreeNode } from '../tree';
import { named, useFilePicker } from '../upload';
import { failure, take, type Sealed } from './load';
import {
  begun,
  done,
  entries,
  inserted,
  moved,
  redone,
  same,
  sheetsOf,
  span,
  stepped,
  turned,
  undone,
  without,
  type History,
  type Sheet,
} from './pages';

const THUMB = 144;
const SHEETS = 'application/x-ponistra-sheets';
const PDF_ACCEPT = 'application/pdf,.pdf';

type Page = Awaited<ReturnType<PDFDocumentProxy['getPage']>>;

interface Source {
  pdf: PDFDocumentProxy;
  title: string;
}

const fileUrl = (id: string) => `/api/nodes/${id}/file`;

/** The file's pages laid out to be turned, removed, reordered and joined by pages of other
 * files, kept only when saved as a new file. */
export default function PagesView({
  file,
  url,
  onSealed,
}: {
  file: TreeNode;
  /** The file's bytes as it is shown; kept while the pages are laid out, as what is read in
   * them later replaces the bytes but not the pages. */
  url: string;
  onSealed: (how: Sealed) => void;
}) {
  const { t, formatNumber } = useI18n();
  const navigate = useNavigate();
  const sources = useRef(new Map<string, Source>());
  const live = useRef(true);
  const made = useRef(0);
  const grid = useRef<HTMLDivElement>(null);
  const steer = useRef(false);
  const dragging = useRef(false);
  const leaving = useRef(false);
  const decided = useRef(false);
  const [start, setStart] = useState<Sheet[] | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [anchor, setAnchor] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [gap, setGap] = useState<number | null>(null);
  const [failed, setFailed] = useState<{ text: string; sealed: boolean } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [dialog, setDialog] = useState<'pick' | 'save' | 'extract' | null>(null);
  const [shown] = useState(url);
  const key = () => `s${++made.current}`;

  const opened = useEffectEvent((pdf: PDFDocumentProxy) => {
    sources.current.set(file.id, { pdf, title: file.title });
    const sheets = sheetsOf(file.id, pdf.numPages, key);
    setStart(sheets);
    setHistory(begun(sheets));
  });
  const refused = useEffectEvent((how: Sealed) => {
    onSealed(how);
    setFailed({ text: t(`pages.sealed.${how}`), sealed: true });
  });
  const broken = useEffectEvent((error: Error) =>
    setFailed({ text: failure(error, shown, t), sealed: false }),
  );

  useEffect(() => {
    const kept = sources.current;
    let gone = false;
    live.current = true;
    take(shown).then(
      (taken) => {
        if (gone) {
          if (typeof taken !== 'string') void taken.loadingTask.destroy();
        } else if (typeof taken === 'string') refused(taken);
        else opened(taken);
      },
      (error: Error) => gone || broken(error),
    );
    return () => {
      gone = true;
      live.current = false;
      for (const { pdf } of kept.values()) void pdf.loadingTask.destroy();
      kept.clear();
    };
  }, [shown]);

  const sheets = history?.present ?? [];
  const keys = new Set(sheets.map((sheet) => sheet.key));
  const picked = new Set([...chosen].filter((each) => keys.has(each)));
  const current = focus && keys.has(focus) ? focus : (sheets[0]?.key ?? null);
  const dirty = !!start && !!history && !same(history.present, start);
  const several = new Set(sheets.map((sheet) => sheet.file)).size > 1;

  useEffect(() => {
    if (!steer.current) return;
    steer.current = false;
    grid.current?.querySelector<HTMLElement>(`[data-key="${current}"]`)?.focus();
  });

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty &&
      !leaving.current &&
      (nextLocation.pathname !== currentLocation.pathname ||
        new URLSearchParams(nextLocation.search).get('view') !== 'pages'),
  );

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const brought = useTreeChange(async (chosenFile: File) => {
    const stored = await upload(chosenFile);
    return postJson<TreeNode>('/api/nodes', {
      kind: 'file',
      blob: stored.sha256,
      title: named(chosenFile.name).title,
      beside: file.id,
    });
  });
  const picker = useFilePicker(
    ([chosenFile]) => brought.mutate(chosenFile, { onSuccess: (node) => void add(node) }),
    { accept: PDF_ACCEPT, multiple: false },
  );

  const change = (make: (now: Sheet[]) => Sheet[]) =>
    setHistory((now) => {
      if (!now) return now;
      const next = make(now.present);
      return same(next, now.present) ? now : done(now, next);
    });

  const choose = (next: string[], from: string | null, at: string | null) => {
    setChosen(new Set(next));
    setAnchor(from);
    setFocus(at);
  };
  const indexOf = (at: string) => sheets.findIndex((sheet) => sheet.key === at);
  const only = (at: string) => choose([at], at, at);
  const range = (to: string) => {
    const from = anchor && keys.has(anchor) ? anchor : to;
    const [first, last] = [indexOf(from), indexOf(to)].sort((a, b) => a - b);
    choose(
      sheets.slice(first, last + 1).map((sheet) => sheet.key),
      from,
      to,
    );
  };
  const toggle = (at: string) => {
    const next = new Set(picked);
    if (!next.delete(at)) next.add(at);
    choose([...next], at, at);
  };

  const turn = (by: 1 | -1) => change((now) => turned(now, picked, by));
  const step = (by: 1 | -1) => {
    steer.current = true;
    change((now) => stepped(now, picked, by));
  };
  const remove = () => {
    if (picked.size === 0) return;
    const first = sheets.findIndex((sheet) => picked.has(sheet.key));
    const rest = without(sheets, picked);
    const next = rest[Math.min(first, rest.length - 1)]?.key ?? null;
    change((now) => without(now, picked));
    choose([], next, next);
    steer.current = true;
  };
  const back = () => history && setHistory(undone(history));
  const again = () => history && setHistory(redone(history));

  async function add(node: TreeNode) {
    const after = sheets.findLast((sheet) => picked.has(sheet.key))?.key ?? null;
    let source = sources.current.get(node.id);
    if (!source) {
      setAdding(true);
      let taken: PDFDocumentProxy | Sealed;
      try {
        taken = await take(fileUrl(node.id));
      } catch (error) {
        if (live.current)
          setNotice(`${node.title}: ${failure(error as Error, fileUrl(node.id), t)}`);
        return;
      } finally {
        if (live.current) setAdding(false);
      }
      if (typeof taken === 'string') {
        if (live.current) setNotice(`${node.title}: ${t(`pages.sealed.${taken}`)}`);
        return;
      }
      if (!live.current) {
        void taken.loadingTask.destroy();
        return;
      }
      source = { pdf: taken, title: node.title };
      sources.current.set(node.id, source);
    }
    const added = sheetsOf(node.id, source.pdf.numPages, key);
    change((now) => {
      const at = after === null ? -1 : now.findIndex((sheet) => sheet.key === after);
      return inserted(now, added, at < 0 ? now.length : at + 1);
    });
    const first = added[0]?.key ?? null;
    choose(
      added.map((sheet) => sheet.key),
      first,
      first,
    );
  }

  const columns = () =>
    grid.current ? getComputedStyle(grid.current).gridTemplateColumns.split(' ').length : 1;

  function gridKey(event: KeyboardEvent<HTMLDivElement>) {
    if (!current) return;
    const at = indexOf(current);
    if (event.altKey) {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        step(event.key === 'ArrowLeft' ? -1 : 1);
      }
      return;
    }
    const moves: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -columns(),
      ArrowDown: columns(),
      Home: -sheets.length,
      End: sheets.length,
    };
    if (event.key in moves) {
      event.preventDefault();
      const next = sheets[Math.min(Math.max(at + moves[event.key], 0), sheets.length - 1)].key;
      steer.current = true;
      if (event.shiftKey) range(next);
      else if (event.ctrlKey || event.metaKey) setFocus(next);
      else only(next);
    } else if (event.key === ' ') {
      event.preventDefault();
      toggle(current);
    } else if (event.key === 'Delete' || event.key === 'Backspace') {
      event.preventDefault();
      remove();
    }
  }

  // Dialogs and menus render in portals, whose keys React still brings up through this view.
  function viewKey(event: KeyboardEvent<HTMLElement>) {
    if (!event.currentTarget.contains(event.target as Node)) return;
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    const pressed = event.key.toLowerCase();
    if (pressed === 'z' && !event.shiftKey) back();
    else if (pressed === 'y' || (pressed === 'z' && event.shiftKey)) again();
    else if (pressed === 'a') choose([...keys], sheets[0]?.key ?? null, current);
    else return;
    event.preventDefault();
  }

  function click(sheet: Sheet, event: MouseEvent) {
    const touch = (event.nativeEvent as PointerEvent).pointerType === 'touch';
    if (event.shiftKey) range(sheet.key);
    else if (touch || event.ctrlKey || event.metaKey) toggle(sheet.key);
    else only(sheet.key);
  }

  function dragStart(event: DragEvent<HTMLDivElement>, sheet: Sheet) {
    if (!picked.has(sheet.key)) only(sheet.key);
    dragging.current = true;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData(SHEETS, sheet.key);
  }

  function dragOver(event: DragEvent<HTMLDivElement>, index: number) {
    if (!dragging.current) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const box = event.currentTarget.getBoundingClientRect();
    setGap(index + (event.clientX > box.left + box.width / 2 ? 1 : 0));
  }

  function dragEnd() {
    dragging.current = false;
    setGap(null);
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    if (!dragging.current) return;
    event.preventDefault();
    if (gap !== null) change((now) => moved(now, picked, gap));
    dragEnd();
  }

  const compose = (list: Sheet[]) => (title: string) =>
    runJob<TreeNode>('compose', { title, beside: file.id, pages: entries(list) }, title);
  const show = (node: TreeNode) => {
    leaving.current = true;
    navigate(nodeHref(node));
  };
  const titleOf = (id: string) =>
    id === file.id ? file.title : (sources.current.get(id)?.title ?? '');
  const label = (sheet: Sheet) =>
    several ? `${titleOf(sheet.file)} · ${formatNumber(sheet.page)}` : formatNumber(sheet.page);
  const pickedSheets = sheets.filter((sheet) => picked.has(sheet.key));
  const extractTitle = pickedSheets.every((sheet) => sheet.file === file.id)
    ? `${file.title} – ${t('pages.short')} ${span(
        pickedSheets.map((sheet) => sheet.page),
        formatNumber,
      )}`
    : `${t('copy.of')} ${file.title}`;
  const shownNotice = notice ?? (brought.error ? errorMessage(brought.error, t) : null);
  const busy = adding || brought.isPending;
  const none = picked.size === 0;

  if (failed) {
    return (
      <p className={`p-6 text-center ${failed.sealed ? 'text-muted' : 'text-danger'}`}>
        {failed.text}
      </p>
    );
  }
  if (!history) return <Loading />;

  const tool = (labelKey: MessageKey, Icon: LucideIcon, action: () => void, disabled: boolean) => (
    <button
      type="button"
      aria-label={t(labelKey)}
      title={t(labelKey)}
      disabled={disabled}
      onClick={action}
      className={`${iconButton} disabled:opacity-40`}
    >
      <Icon size={16} aria-hidden />
    </button>
  );
  const divider = <span aria-hidden className="mx-1 h-5 w-px bg-line" />;

  return (
    <section onKeyDown={viewKey} className="flex h-full flex-col">
      <div className="pb-3">
        <div className="flex flex-wrap items-center gap-1 rounded-2xl bg-panel px-3 py-1">
          <span aria-live="polite" className="mr-1 text-sm text-muted tabular-nums">
            {none
              ? `${t('pages.total')}: ${formatNumber(sheets.length)}`
              : `${t('explorer.selected')}: ${formatNumber(picked.size)} ${t('pdf.of')} ${formatNumber(sheets.length)}`}
          </span>
          {divider}
          {tool('pages.turnLeft', RotateCcw, () => turn(-1), none)}
          {tool('pages.turnRight', RotateCw, () => turn(1), none)}
          {tool('pages.earlier', ChevronLeft, () => step(-1), none)}
          {tool('pages.later', ChevronRight, () => step(1), none)}
          {tool('pages.remove', Trash2, remove, none)}
          {divider}
          {tool('pages.undo', Undo2, back, history.past.length === 0)}
          {tool('pages.redo', Redo2, again, history.future.length === 0)}
          <div className="ml-auto flex flex-wrap items-center justify-end gap-2 py-1">
            {busy && <span className="text-sm text-muted">{t('pages.adding')}</span>}
            <Menu
              trigger={
                <button type="button" disabled={busy} className={button}>
                  <FilePlus size={16} aria-hidden />
                  <span className="sr-only sm:not-sr-only">{t('pages.add')}</span>
                </button>
              }
            >
              <MenuItem
                icon={FolderTree}
                label={t('pages.add.tree')}
                onSelect={() => setDialog('pick')}
              />
              <MenuItem icon={Upload} label={t('pages.add.computer')} onSelect={picker.open} />
            </Menu>
            <button
              type="button"
              disabled={none}
              onClick={() => setDialog('extract')}
              className={button}
            >
              <FileOutput size={16} aria-hidden />
              <span className="sr-only sm:not-sr-only">{t('pages.extract')}</span>
            </button>
            <button
              type="button"
              disabled={sheets.length === 0}
              onClick={() => setDialog('save')}
              className={primaryButton}
            >
              <Save size={16} aria-hidden />
              <span className="sr-only sm:not-sr-only">{t('pages.save')}</span>
            </button>
          </div>
        </div>
      </div>
      {shownNotice && (
        <div
          role="alert"
          className="mb-3 flex items-start gap-2 rounded-2xl bg-panel py-2 pr-1.5 pl-4 text-sm text-ink"
        >
          <p className="min-w-0 flex-1 py-1 break-words">{shownNotice}</p>
          <button
            type="button"
            aria-label={t('form.notice.close')}
            title={t('form.notice.close')}
            onClick={() => {
              setNotice(null);
              brought.reset();
            }}
            className={iconButton}
          >
            <X size={16} aria-hidden />
          </button>
        </div>
      )}
      <div className="-mx-4 -mb-4 min-h-0 flex-1 overflow-auto">
        {sheets.length === 0 ? (
          <p className="p-6 text-center text-muted">{t('pages.empty')}</p>
        ) : (
          <div
            ref={grid}
            role="listbox"
            aria-multiselectable
            aria-label={t('pages.list')}
            onKeyDown={gridKey}
            onDragOver={(event) => dragging.current && event.preventDefault()}
            onDrop={drop}
            className="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-x-5 gap-y-4 p-4"
          >
            {sheets.map((sheet, index) => (
              <div
                key={sheet.key}
                data-key={sheet.key}
                role="option"
                aria-selected={picked.has(sheet.key)}
                tabIndex={sheet.key === current ? 0 : -1}
                draggable
                onDragStart={(event) => dragStart(event, sheet)}
                onDragOver={(event) => dragOver(event, index)}
                onDragEnd={dragEnd}
                onClick={(event) => click(sheet, event)}
                onFocus={() => setFocus(sheet.key)}
                className="relative flex cursor-default flex-col items-center gap-1.5 rounded-lg p-2 outline-none select-none hover:bg-hover focus-visible:outline-2 focus-visible:outline-focus aria-selected:bg-selected"
              >
                <Thumb
                  pdf={sources.current.get(sheet.file)!.pdf}
                  page={sheet.page}
                  turn={sheet.turn}
                />
                <span className="max-w-full truncate text-xs text-muted tabular-nums">
                  {label(sheet)}
                  {sheet.turn > 0 && (
                    <span className="sr-only">
                      , {t('pages.turned')} {formatNumber(sheet.turn * 90)}°
                    </span>
                  )}
                </span>
                {gap === index && (
                  <span aria-hidden className="absolute inset-y-2 -left-3 w-0.5 rounded bg-focus" />
                )}
                {gap === sheets.length && index === sheets.length - 1 && (
                  <span
                    aria-hidden
                    className="absolute inset-y-2 -right-3 w-0.5 rounded bg-focus"
                  />
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      {picker.element}
      {dialog === 'pick' && (
        <FilePickDialog
          heading={t('pages.add.heading')}
          near={file}
          kind="file"
          onPick={(node) => void add(node)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'save' && (
        <NameDialog
          heading={t('pages.save.heading')}
          submitLabel={t('tree.create')}
          initial={`${t('copy.of')} ${file.title}`.slice(0, 200)}
          onSubmit={compose(sheets)}
          onDone={show}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'extract' && (
        <NameDialog
          heading={t('pages.extract.heading')}
          submitLabel={t('tree.create')}
          initial={extractTitle.slice(0, 200)}
          onSubmit={compose(pickedSheets)}
          onDone={show}
          onClose={() => setDialog(null)}
        />
      )}
      {blocker.state === 'blocked' && (
        <ConfirmDialog
          heading={t('pages.leave')}
          confirmLabel={t('pages.discard')}
          onConfirm={() => {
            decided.current = true;
            blocker.proceed();
          }}
          onClose={() => {
            if (!decided.current) blocker.reset();
            decided.current = false;
          }}
        >
          {t('pages.leave.body')}
        </ConfirmDialog>
      )}
    </section>
  );
}

/** A page drawn once it comes near the view, turned by the quarters asked on top of its own. */
function Thumb({ pdf, page, turn }: { pdf: PDFDocumentProxy; page: number; turn: number }) {
  const { t } = useI18n();
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [near, setNear] = useState(false);
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    const watcher = watchNear(box.current!, () => setNear(true));
    watcher.observe(box.current!);
    return () => watcher.disconnect();
  }, []);

  useEffect(() => {
    if (!near) return;
    let gone = false;
    let drawing: ReturnType<Page['render']> | null = null;
    const fail = (error: unknown) => {
      if (!gone && !(error instanceof RenderingCancelledException)) setBroken(true);
    };
    pdf.getPage(page).then((proxy) => {
      if (gone) return;
      const ratio = devicePixelRatio;
      const natural = proxy.getViewport({ scale: 1 });
      const viewport = proxy.getViewport({
        scale: (THUMB * ratio) / Math.max(natural.width, natural.height),
      });
      const target = canvas.current!;
      target.width = Math.round(viewport.width);
      target.height = Math.round(viewport.height);
      target.style.width = `${viewport.width / ratio}px`;
      target.style.height = `${viewport.height / ratio}px`;
      drawing = proxy.render({ canvas: target, viewport });
      drawing.promise.catch(fail);
    }, fail);
    return () => {
      gone = true;
      drawing?.cancel();
    };
  }, [near, pdf, page]);

  return (
    <div ref={box} className="flex size-36 items-center justify-center">
      {broken ? (
        <span className="text-center text-xs text-danger">{t('pages.unshown')}</span>
      ) : (
        <canvas
          ref={canvas}
          style={{ transform: `rotate(${turn * 90}deg)` }}
          className="shadow-sm"
        />
      )}
    </div>
  );
}
