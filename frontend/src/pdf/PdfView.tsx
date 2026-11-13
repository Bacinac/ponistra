import 'pdfjs-dist/web/pdf_viewer.css';
// pdf_viewer.mjs takes the library from globalThis.pdfjsLib as it loads, which pdf.mjs sets.
import { AnnotationMode, PasswordResponses, type PDFDocumentProxy } from 'pdfjs-dist';
import {
  EventBus,
  FindState,
  LinkTarget,
  PDFFindController,
  PDFLinkService,
  PDFScriptingManager,
  PDFViewer,
} from 'pdfjs-dist/web/pdf_viewer.mjs';
import { useMutation } from '@tanstack/react-query';
import {
  ChevronDown,
  ChevronUp,
  EyeOff,
  MessageSquarePlus,
  PenLine,
  Search,
  X,
} from 'lucide-react';
import {
  useEffect,
  useEffectEvent,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router';
import { getJson } from '../api';
import { useSession } from '../auth';
import { ZoomChoices } from '../choices';
import type { PageRect } from '../comments';
import { Cancel, Modal, NameDialog } from '../dialogs';
import { useI18n } from '../i18n';
import { runJob } from '../jobs';
import { field, iconButton, primaryButton, smallField } from '../styles';
import type { Heading, OutlineStore } from '../tabs';
import { errorMessage, LONGEST_TITLE, nodeHref, type TreeNode } from '../tree';
import { useZoom, type Zoom } from '../views';
import { FormFill } from './form';
import {
  DATA,
  failure,
  forbidsAssembly,
  forbidsChange,
  load,
  type Sealed,
  type Unchangeable,
} from './load';
import { FileNotes, useFileRoom, type Tool } from './Notes';
import { Words } from './words';

type Destination = string | unknown[];
type Item = Awaited<ReturnType<PDFDocumentProxy['getOutline']>>[number];

interface Marked {
  heading: Heading;
  page: number;
  destination: Destination;
}

interface Opened {
  viewer: PDFViewer;
  links: PDFLinkService;
  bus: EventBus;
  marked: Marked[];
  box: HTMLDivElement;
  field: HTMLDivElement;
  form: FormFill;
}

type Asked = { wrong: boolean; answer: (password: string) => void };

interface Matches {
  current: number;
  total: number;
  state: number;
}

async function pageOf(pdf: PDFDocumentProxy, destination: Destination): Promise<number | null> {
  const explicit =
    typeof destination === 'string' ? await pdf.getDestination(destination) : destination;
  const target: unknown = explicit?.[0];
  if (Number.isInteger(target)) return (target as number) + 1;
  if (target && typeof target === 'object') {
    return (await pdf.getPageIndex(target as Parameters<typeof pdf.getPageIndex>[0])) + 1;
  }
  return null;
}

/** The file's bookmarks that lead to a page, each named by its place among its siblings. */
async function bookmarks(pdf: PDFDocumentProxy): Promise<Marked[]> {
  const flat: { item: Item; id: string; level: number }[] = [];
  const walk = (items: Item[], level: number, above: string) =>
    items.forEach((item, index) => {
      const id = above ? `${above}.${index + 1}` : `${index + 1}`;
      flat.push({ item, id, level });
      walk(item.items, level + 1, id);
    });
  walk((await pdf.getOutline()) ?? [], 1, '');
  const found = await Promise.all(
    flat.map(async ({ item, id, level }) => {
      const destination = item.dest;
      if (!destination) return null;
      const page = await pageOf(pdf, destination).catch(() => null);
      if (!page) return null;
      return { heading: { id, level, number: null, text: item.title }, page, destination };
    }),
  );
  return found.filter((each) => each !== null);
}

/** Pages as wide as the pane leaves room for, or their real size where that is narrower. */
function fit(viewer: PDFViewer, zoom: Zoom) {
  const view = viewer.getPageView(viewer.currentPageNumber - 1);
  if (!view) return;
  const style = getComputedStyle(viewer.viewer!);
  const room =
    viewer.viewer!.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  if (room <= 0) return;
  const natural = view.viewport.width / view.scale;
  viewer.currentScale = Math.min(room / natural, zoom === 'page' ? 1 : Infinity);
}

export default function PdfView({
  file,
  page,
  heading,
  find,
  visit,
  outline,
  notes,
  onNoted,
  onSealed,
  status,
}: {
  file: string;
  page: number | null;
  heading: string | null;
  find: string | null;
  /** Changes with each arrival, which goes to its place again. */
  visit: string;
  outline: OutlineStore;
  notes: { room: string; fileId: string; title: string; editable: boolean };
  onNoted: (noted: boolean) => void;
  /** Called once the file asks for its password, which notes are never written into, or is
   * found to forbid its pages being taken into another. */
  onSealed: (how: Sealed) => void;
  /** Said in the bar beside the page number, while nothing is being searched. */
  status: ReactNode;
}) {
  const say = useI18n();
  const { t, formatNumber } = say;
  const box = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLDivElement>(null);
  const pages = useRef<HTMLDivElement>(null);
  const findField = useRef<HTMLInputElement>(null);
  const pageField = useId();
  const [zoom, setZoom] = useZoom();
  const [opened, setOpened] = useState<Opened | null>(null);
  const [asked, setAsked] = useState<Asked | null>(null);
  const [locked, setLocked] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [at, setAt] = useState(1);
  const [typed, setTyped] = useState<string | null>(null);
  const [query, setQuery] = useState<string | null>(null);
  const [matches, setMatches] = useState<Matches | null>(null);
  const [tool, setTool] = useState<Tool>('read');
  const [notice, setNotice] = useState<string | null>(null);
  const [marked, setMarked] = useState(false);
  const [filled, setFilled] = useState(false);
  const [unchangeable, setUnchangeable] = useState<Unchangeable | null>(null);
  const [signed, setSigned] = useState(false);
  const [saving, setSaving] = useState(false);
  const room = useFileRoom(notes.room, notes.fileId);
  const me = useSession().data?.user?.id ?? null;
  const navigate = useNavigate();
  const resumed = useRef<number | null>(null);
  const fitAsChosen = useEffectEvent((viewer: PDFViewer) => fit(viewer, zoom));
  const sealed = useEffectEvent(onSealed);
  const resume = useEffectEvent((open: Opened, number: number) => {
    open.viewer.currentPageNumber = Math.min(number, open.viewer.pagesCount);
    if (query) search(open, query, '');
  });

  useEffect(() => {
    if (locked) return;
    const controller = new AbortController();
    const words = new Words(say.language, say);
    const bus = new EventBus();
    const links = new PDFLinkService({
      eventBus: bus,
      externalLinkTarget: LinkTarget.BLANK,
      externalLinkRel: 'noopener noreferrer nofollow',
    });
    const finder = new PDFFindController({ eventBus: bus, linkService: links });
    const form = new FormFill(bus, box.current!, `${DATA}wasm/`, say, setNotice, (number) =>
      viewer.getPageView(number - 1),
    );
    const scripting = new PDFScriptingManager({
      eventBus: bus,
      externalServices: { createScripting: () => form.scripting() },
    });
    const options: ConstructorParameters<typeof PDFViewer>[0] & { abortSignal: AbortSignal } = {
      container: box.current!,
      viewer: pages.current!,
      eventBus: bus,
      linkService: links,
      findController: finder,
      removePageBorders: true,
      annotationMode: AnnotationMode.ENABLE_FORMS,
      scriptingManager: scripting,
      imageResourcesPath: `${DATA}web/images/`,
      l10n: words as unknown as ConstructorParameters<typeof PDFViewer>[0]['l10n'],
      abortSignal: controller.signal,
    };
    const viewer = new PDFViewer(options);
    links.setViewer(viewer);
    scripting.setViewer(viewer);
    words.translate(pages.current!);

    const task = load(file);
    task.onPassword = (answer: (password: string) => void, reason: number) => {
      sealed('password');
      setUnchangeable('password');
      setAsked({ wrong: reason === PasswordResponses.INCORRECT_PASSWORD, answer });
    };

    task.promise.then(
      async (pdf) => {
        if (controller.signal.aborted) return;
        setAsked(null);
        const [marked, , forbidden, fixed] = await Promise.all([
          bookmarks(pdf),
          form.open(pdf),
          forbidsAssembly(pdf),
          forbidsChange(pdf),
        ]);
        if (controller.signal.aborted) return;
        if (forbidden) sealed('assembly');
        if (fixed) setUnchangeable((now) => now ?? 'modify');
        setSigned(form.signed);
        bus.on(
          'pagesinit',
          () => {
            fitAsChosen(viewer);
            setAt(viewer.currentPageNumber);
            setOpened({
              viewer,
              links,
              bus,
              marked,
              box: box.current!,
              field: field.current!,
              form,
            });
          },
          { signal: controller.signal },
        );
        bus.on('pagechanging', ({ pageNumber }: { pageNumber: number }) => setAt(pageNumber), {
          signal: controller.signal,
        });
        const counted = ({ matchesCount, state }: { matchesCount: Matches; state?: number }) =>
          setMatches((now) => ({
            current: matchesCount.current,
            total: matchesCount.total,
            state: state ?? now?.state ?? FindState.PENDING,
          }));
        bus.on('updatefindmatchescount', counted, { signal: controller.signal });
        bus.on('updatefindcontrolstate', counted, { signal: controller.signal });
        viewer.setDocument(pdf);
        links.setDocument(pdf);
      },
      (error: Error) => {
        if (!controller.signal.aborted) setFailed(failure(error, file, t));
      },
    );

    return () => {
      if (viewer.pagesCount) resumed.current = viewer.currentPageNumber;
      controller.abort();
      form.destroy();
      void scripting.setDocument(null);
      setOpened(null);
      setNotice(null);
      setUnchangeable(null);
      setSigned(false);
      setTool('read');
      setAsked(null);
      outline.set(null);
      void words.destroy();
      void task.destroy();
    };
  }, [file, locked, say, t, outline]);

  useEffect(() => {
    if (!opened) return;
    opened.form.attach(room, notes.editable);
  }, [opened, room, notes.editable]);

  useEffect(() => {
    if (!room) return;
    const look = () => setFilled(room.fields.size > 0);
    look();
    room.fields.observe(look);
    return () => room.fields.unobserve(look);
  }, [room]);

  useEffect(() => onNoted(marked || filled), [marked, filled, onNoted]);

  useEffect(() => {
    if (!opened) return;
    fit(opened.viewer, zoom);
    let width = box.current!.clientWidth;
    const watcher = new ResizeObserver(() => {
      if (box.current!.clientWidth === width) return;
      width = box.current!.clientWidth;
      fit(opened.viewer, zoom);
    });
    watcher.observe(box.current!);
    return () => watcher.disconnect();
  }, [opened, zoom]);

  useEffect(() => {
    if (!opened) return;
    const headings = opened.marked.map(({ heading }) => heading);
    const chosen = opened.marked.find((each) => each.heading.id === heading);
    const current =
      chosen?.page === at
        ? chosen.heading.id
        : (opened.marked.findLast((each) => each.page <= at)?.heading.id ?? null);
    outline.set({ headings, current });
  }, [opened, at, heading, outline]);

  useEffect(() => {
    if (!opened) return;
    const left = resumed.current;
    resumed.current = null;
    if (left) return resume(opened, left);
    const target = heading && opened.marked.find((each) => each.heading.id === heading);
    if (target) void opened.links.goToDestination(target.destination);
    else if (page) opened.viewer.currentPageNumber = Math.min(page, opened.viewer.pagesCount);
    if (find) {
      setQuery(find);
      search(opened, find, '');
    }
  }, [opened, visit, page, heading, find]);

  useEffect(() => {
    const open = (event: globalThis.KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || event.altKey || event.key.toLowerCase() !== 'f') {
        return;
      }
      event.preventDefault();
      setQuery((now) => now ?? '');
      findField.current?.focus();
      findField.current?.select();
    };
    window.addEventListener('keydown', open);
    return () => window.removeEventListener('keydown', open);
  }, []);

  function search(open: Opened, text: string, type: '' | 'again', previous = false) {
    open.bus.dispatch('find', {
      source: null,
      type,
      query: text,
      caseSensitive: false,
      entireWord: false,
      highlightAll: true,
      findPrevious: previous,
      matchDiacritics: false,
    });
  }

  function seek(previous: boolean) {
    if (opened && query) search(opened, query, 'again', previous);
  }

  function closeFind() {
    setQuery(null);
    setMatches(null);
    opened?.bus.dispatch('findbarclose', { source: null });
  }

  function findKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault();
      seek(event.shiftKey);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      closeFind();
    }
  }

  const blackOut = useMutation({
    mutationFn: (text: string) =>
      getJson<{ hits: { page: number; rects: PageRect[] }[] }>(
        `/api/nodes/${notes.fileId}/found?${new URLSearchParams({ q: text })}`,
      ),
    onSuccess: ({ hits }) => {
      const at = new Date().toISOString();
      room?.redact((held) => {
        for (const { page, rects } of hits) {
          held.set(crypto.randomUUID(), { kind: 'redaction', page, rects, by: me, at });
        }
      });
      setNotice(`${t('pdf.redact.marked')}: ${formatNumber(hits.length)}`);
    },
    onError: (error) => setNotice(errorMessage(error, t)),
  });
  const refusal = unchangeable && t(`pdf.redact.sealed.${unchangeable}`);
  const suffix = t('pdf.redact.suffix');

  function goTo(event: FormEvent) {
    event.preventDefault();
    const wanted = Number(typed?.replace(/\D/g, ''));
    if (opened && wanted >= 1 && wanted <= opened.viewer.pagesCount) {
      opened.viewer.currentPageNumber = wanted;
    }
    setTyped(null);
  }

  const count =
    query && matches
      ? matches.total === 0 && matches.state === FindState.NOT_FOUND
        ? t('pdf.find.none')
        : matches.total > 0
          ? `${formatNumber(matches.current)} ${t('pdf.of')} ${formatNumber(matches.total)}`
          : ''
      : '';

  return (
    <section className="flex h-full flex-col">
      <div className="pb-3">
        <div className="flex items-center gap-2 rounded-full bg-panel px-3 py-1">
          {opened && (
            <form
              onSubmit={goTo}
              className={`${query === null ? 'flex' : 'hidden sm:flex'} shrink-0 items-center gap-1.5 text-sm text-muted`}
            >
              <label htmlFor={pageField} className="sr-only sm:not-sr-only">
                {t('pdf.page')}
              </label>
              <input
                id={pageField}
                inputMode="numeric"
                value={typed ?? formatNumber(at)}
                onChange={(event) => setTyped(event.target.value)}
                onFocus={(event) => event.currentTarget.select()}
                onBlur={() => setTyped(null)}
                className={`${smallField} w-14 text-center tabular-nums`}
              />
              <span className="tabular-nums">
                {t('pdf.of')} {formatNumber(opened.viewer.pagesCount)}
              </span>
            </form>
          )}
          <div role="status" className="flex min-w-0 items-center gap-1 text-sm text-muted">
            {query === null && status}
          </div>
          <div className="ml-auto flex min-w-0 flex-1 items-center justify-end gap-0.5">
            {query !== null ? (
              <div
                role="search"
                aria-label={t('pdf.find')}
                className="flex min-w-0 flex-1 items-center justify-end gap-1"
              >
                <input
                  ref={findField}
                  autoFocus
                  type="search"
                  aria-label={t('pdf.find')}
                  placeholder={t('pdf.find')}
                  value={query}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    if (opened) search(opened, event.target.value, '');
                  }}
                  onKeyDown={findKey}
                  className={`${smallField} min-w-0 flex-1 sm:w-40 sm:flex-none [&::-webkit-search-cancel-button]:hidden`}
                />
                <span
                  aria-live="polite"
                  className="text-sm whitespace-nowrap text-muted tabular-nums"
                >
                  {count}
                </span>
                {notes.editable && room && (
                  <button
                    type="button"
                    aria-label={t('pdf.redact.found')}
                    title={refusal ?? t('pdf.redact.found')}
                    disabled={!matches?.total || refusal !== null || blackOut.isPending}
                    onClick={() => blackOut.mutate(query)}
                    className={`${iconButton} disabled:opacity-40`}
                  >
                    <EyeOff size={16} aria-hidden />
                  </button>
                )}
                <button
                  type="button"
                  aria-label={t('pdf.find.previous')}
                  title={t('pdf.find.previous')}
                  disabled={!matches?.total}
                  onClick={() => seek(true)}
                  className={`${iconButton} disabled:opacity-40`}
                >
                  <ChevronUp size={16} aria-hidden />
                </button>
                <button
                  type="button"
                  aria-label={t('pdf.find.next')}
                  title={t('pdf.find.next')}
                  disabled={!matches?.total}
                  onClick={() => seek(false)}
                  className={`${iconButton} disabled:opacity-40`}
                >
                  <ChevronDown size={16} aria-hidden />
                </button>
                <button
                  type="button"
                  aria-label={t('pdf.find.close')}
                  title={t('pdf.find.close')}
                  onClick={closeFind}
                  className={iconButton}
                >
                  <X size={16} aria-hidden />
                </button>
              </div>
            ) : (
              <>
                {notes.editable && (
                  <button
                    type="button"
                    aria-label={t('pdf.draw')}
                    title={t('pdf.draw')}
                    aria-pressed={tool === 'draw'}
                    disabled={!opened}
                    onClick={() => setTool(tool === 'draw' ? 'read' : 'draw')}
                    className={`${iconButton} aria-pressed:bg-selected aria-pressed:text-ink`}
                  >
                    <PenLine size={16} aria-hidden />
                  </button>
                )}
                {notes.editable && (
                  <button
                    type="button"
                    aria-label={t('pdf.redact')}
                    title={refusal ?? t('pdf.redact')}
                    aria-pressed={tool === 'redact'}
                    disabled={!opened || refusal !== null}
                    onClick={() => setTool(tool === 'redact' ? 'read' : 'redact')}
                    className={`${iconButton} aria-pressed:bg-selected aria-pressed:text-ink disabled:opacity-40`}
                  >
                    <EyeOff size={16} aria-hidden />
                  </button>
                )}
                <button
                  type="button"
                  aria-label={t('pdf.pin')}
                  title={t('pdf.pin')}
                  aria-pressed={tool === 'pin'}
                  disabled={!opened}
                  onClick={() => setTool(tool === 'pin' ? 'read' : 'pin')}
                  className={`${iconButton} aria-pressed:bg-selected aria-pressed:text-ink`}
                >
                  <MessageSquarePlus size={16} aria-hidden />
                </button>
                <button
                  type="button"
                  aria-label={t('pdf.find')}
                  title={t('pdf.find')}
                  disabled={!opened}
                  onClick={() => setQuery('')}
                  className={iconButton}
                >
                  <Search size={16} aria-hidden />
                </button>
              </>
            )}
            <div className="hidden items-center sm:flex">
              <span aria-hidden className="mx-1 h-5 w-px bg-line" />
              <ZoomChoices zoom={zoom} onChoose={setZoom} />
            </div>
          </div>
        </div>
      </div>
      {notice && (
        <div
          role="alert"
          className="mb-3 flex items-start gap-2 rounded-2xl bg-panel py-2 pr-1.5 pl-4 text-sm text-ink"
        >
          <p className="min-w-0 flex-1 py-1 break-words">{notice}</p>
          <button
            type="button"
            aria-label={t('form.notice.close')}
            title={t('form.notice.close')}
            onClick={() => setNotice(null)}
            className={iconButton}
          >
            <X size={16} aria-hidden />
          </button>
        </div>
      )}
      <div ref={field} className="relative -mx-4 -mb-4 min-h-0 flex-1">
        <div ref={box} className="ponistra-pdf absolute inset-0 overflow-auto">
          <div ref={pages} className="pdfViewer" />
        </div>
        {opened && (
          <FileNotes
            pages={opened.viewer}
            box={opened.box}
            field={opened.field}
            room={room}
            fileId={notes.fileId}
            editable={notes.editable}
            tool={tool}
            redacting={{ refusal, signed, onSave: () => setSaving(true) }}
            onTool={setTool}
            onNoted={setMarked}
          />
        )}
        {(failed || locked) && (
          <div className="absolute inset-x-0 top-0 flex flex-col items-center gap-3 p-6 text-center">
            <p className={failed ? 'text-danger' : 'text-muted'}>{failed ?? t('pdf.locked')}</p>
            {locked && (
              <button type="button" className={primaryButton} onClick={() => setLocked(false)}>
                {t('pdf.unlock')}
              </button>
            )}
          </div>
        )}
      </div>
      {saving && (
        <NameDialog
          heading={t('pdf.redact.save.heading')}
          submitLabel={t('tree.create')}
          initial={`${notes.title.slice(0, LONGEST_TITLE - suffix.length - 1)} ${suffix}`}
          note={
            signed
              ? `${t('pdf.redact.save.note')} ${t('pdf.redact.signed')}`
              : t('pdf.redact.save.note')
          }
          onSubmit={(title) => runJob<TreeNode>('redact', { file: notes.fileId, title }, title)}
          onDone={(node) => navigate(nodeHref(node))}
          onClose={() => setSaving(false)}
        />
      )}
      {asked && (
        <PasswordDialog
          wrong={asked.wrong}
          onAnswer={(password) => {
            asked.answer(password);
            setAsked(null);
          }}
          onClose={() => {
            setAsked(null);
            setLocked(true);
          }}
        />
      )}
    </section>
  );
}

function PasswordDialog({
  wrong,
  onAnswer,
  onClose,
}: {
  wrong: boolean;
  onAnswer: (password: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [password, setPassword] = useState('');
  return (
    <Modal heading={t('pdf.locked')} onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onAnswer(password);
        }}
        className="flex flex-col gap-4"
      >
        <label className="flex flex-col gap-1 text-sm">
          {t('pdf.password')}
          <input
            type="password"
            required
            autoFocus
            autoComplete="off"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={field}
          />
        </label>
        {wrong && <p className="text-sm text-danger">{t('pdf.wrongPassword')}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton}>
            {t('pdf.unlock')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
