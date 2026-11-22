import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Download,
  FileUp,
  Folder,
  FolderInput,
  FolderOpen,
  PanelRight,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from 'react';
import { ChoiceBar, useChoice } from './choice';
import { CodeEditor, type Opened, type Written } from './codeEditor';
import { Cancel, ConfirmDialog, Modal, NameDialog } from './dialogs';
import { useDropTarget } from './drag';
import {
  formatSize,
  storedPreview,
  storedSort,
  storePreview,
  storeSort,
  type Sort,
  type SortKey,
} from './explorer';
import { Loading, Panel, useWide } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { ActionsMenu, ContextMenuArea, Menu, MenuItem, MenuSeparator } from './menu';
import { button, iconButton, primaryButton } from './styles';
import { errorMessage, KindIcon, kindLabel, type ShownKind } from './tree';
import { loose, useFilePicker, type Picked } from './upload';

export interface FileEntry {
  name: string;
  /** Anything but a folder or a file is listed and nothing more. */
  kind: string;
  size: number | null;
  modified: string | null;
}

/** Where a file browser's files live: a location on the network, a project of the workspace. The
 * browser knows nothing else of it. Paths are relative, their parts joined by a slash, the top
 * the empty one. */
export interface FileSource {
  /** Tells the source from every other among the page's queries. */
  key: string;
  name: string;
  writable: boolean;
  list: (path: string) => Promise<{ path: string; entries: FileEntry[] }>;
  rawHref: (path: string, download?: boolean) => string;
  /** An image or a PDF's first page drawn small, where the source draws them. */
  pictureHref?: (path: string) => string;
  read: (path: string) => Promise<Opened>;
  write: (path: string, text: string, hash: string) => Promise<Written>;
  folder: (path: string, name: string) => Promise<unknown>;
  /** Renames, and moves to another folder of the source. */
  rename: (path: string, to: string) => Promise<unknown>;
  remove: (paths: string[]) => Promise<unknown>;
  put: (path: string, name: string, file: File) => Promise<unknown>;
  /** What else the source does with the entries chosen, as items of their menu. */
  more?: (paths: string[], done: () => void) => ReactNode;
}

export interface Framed {
  title: string;
  actions: ReactNode;
  primary: ReactNode;
  panel: ReactNode;
  children: ReactNode;
}

const within = (folder: string, name: string) => (folder ? `${folder}/${name}` : name);
const above = (path: string) => path.replace(/\/?[^/]*$/, '');
const nameOf = (path: string) => path.split('/').pop() ?? path;
export const listKey = (source: FileSource, path: string) => ['files', source.key, 'list', path];
const fileKey = (source: FileSource, path: string) => ['files', source.key, 'file', path];

const PICTURES = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif', 'tif', 'tiff', 'heic'];
const SOUND = ['mp3', 'm4a', 'ogg', 'oga', 'wav', 'flac'];
const VIDEO = ['mp4', 'm4v', 'webm', 'mov', 'ogv'];
/** As much of a text file as a glance reads and shows. */
const GLANCED = 256 * 1024;
const GLANCED_TEXT = 20_000;

const extensionOf = (name: string) =>
  name.includes('.', 1) ? name.slice(name.lastIndexOf('.') + 1).toLowerCase() : '';

function kindOf(entry: FileEntry): ShownKind {
  if (entry.kind === 'folder') return 'folder';
  const extension = extensionOf(entry.name);
  if (extension === 'pdf') return 'file';
  if (PICTURES.includes(extension) || extension === 'svg') return 'image';
  if (SOUND.includes(extension)) return 'audio';
  if (VIDEO.includes(extension)) return 'video';
  return 'other';
}

/** What a browser shows by itself, in a tab of its own. */
const played = (entry: FileEntry) => ['file', 'image', 'audio', 'video'].includes(kindOf(entry));

const collator = new Intl.Collator('hr', { numeric: true, sensitivity: 'base' });

function compare(a: FileEntry, b: FileEntry, key: SortKey): number {
  switch (key) {
    case 'kind':
      return collator.compare(extensionOf(a.name), extensionOf(b.name));
    case 'updated_at':
      return Date.parse(a.modified ?? '') - Date.parse(b.modified ?? '') || 0;
    case 'size':
      return (a.size ?? -1) - (b.size ?? -1);
    default:
      return 0;
  }
}

function sorted(entries: FileEntry[], sort: Sort): FileEntry[] {
  return [...entries].sort((a, b) => {
    const folders = Number(b.kind === 'folder') - Number(a.kind === 'folder');
    if (folders !== 0) return folders;
    const order = compare(a, b, sort.key) || collator.compare(a.name, b.name);
    return sort.descending ? -order : order;
  });
}

const COLUMNS: { key: SortKey; label: MessageKey; className: string }[] = [
  { key: 'title', label: 'tree.name', className: 'w-full' },
  { key: 'kind', label: 'explorer.kind', className: 'hidden md:table-cell' },
  { key: 'updated_at', label: 'explorer.updated', className: 'hidden sm:table-cell' },
  { key: 'size', label: 'explorer.size', className: 'hidden md:table-cell text-right' },
];

/** The folders from the source's top down to the one shown, each a step back to it. */
function Crumbs({
  source,
  path,
  onGo,
}: {
  source: FileSource;
  path: string;
  onGo: (path: string) => void;
}) {
  const parts = path ? path.split('/') : [];
  const crumb = 'truncate rounded px-1 hover:bg-hover';
  return (
    <nav className="flex min-w-0 flex-wrap items-center gap-1 text-sm text-muted">
      <button type="button" onClick={() => onGo('')} className={crumb}>
        {source.name}
      </button>
      {parts.map((part, index) => (
        <span key={index} className="flex min-w-0 items-center gap-1">
          <ChevronRight size={14} aria-hidden className="shrink-0" />
          <button
            type="button"
            aria-current={index === parts.length - 1 ? 'page' : undefined}
            onClick={() => onGo(parts.slice(0, index + 1).join('/'))}
            className={`${crumb} aria-[current]:text-ink`}
          >
            {part}
          </button>
        </span>
      ))}
    </nav>
  );
}

/** A folder of the source to move what was chosen into. */
function FolderPick({
  source,
  from,
  moving,
  onPick,
  onClose,
}: {
  source: FileSource;
  from: string;
  /** The paths being moved: none goes into itself. */
  moving: string[];
  onPick: (folder: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [path, setPath] = useState(from);
  const listed = useQuery({ queryKey: listKey(source, path), queryFn: () => source.list(path) });
  const folders = (listed.data?.entries ?? []).filter(
    (entry) => entry.kind === 'folder' && !moving.includes(within(path, entry.name)),
  );
  return (
    <Modal heading={t('tree.move')} onClose={onClose}>
      <Crumbs source={source} path={path} onGo={setPath} />
      <ul className="flex max-h-72 min-h-24 flex-col overflow-y-auto">
        {listed.isPending ? (
          <Loading />
        ) : folders.length === 0 ? (
          <li className="text-sm text-muted">{t('tree.noSubfolders')}</li>
        ) : (
          folders.map((entry) => (
            <li key={entry.name}>
              <button
                type="button"
                onClick={() => setPath(within(path, entry.name))}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-hover"
              >
                <Folder size={16} aria-hidden className="shrink-0 text-muted" />
                <span className="truncate">{entry.name}</span>
              </button>
            </li>
          ))
        )}
      </ul>
      {listed.error && <p className="text-sm text-danger">{errorMessage(listed.error, t)}</p>}
      <div className="flex justify-end gap-2">
        <Cancel />
        <button
          type="button"
          disabled={path === from || listed.isPending}
          onClick={() => onPick(path)}
          className={primaryButton}
        >
          {t('tree.moveHere')}
        </button>
      </div>
    </Modal>
  );
}

function Glance({ source, path, entry }: { source: FileSource; path: string; entry: FileEntry }) {
  const { t, formatDate, formatNumber } = useI18n();
  const kind = kindOf(entry);
  const extension = extensionOf(entry.name);
  const [missing, setMissing] = useState(false);
  const reads = kind === 'other' && entry.size !== null && entry.size <= GLANCED;
  const read = useQuery({
    queryKey: fileKey(source, path),
    queryFn: () => source.read(path),
    enabled: reads,
  });
  const pictured = source.pictureHref && (kind === 'file' || PICTURES.includes(extension));
  return (
    <>
      <h3 className="flex items-start gap-2 font-semibold break-words">
        <KindIcon kind={kind} extension={extension} decorative />
        <span className="min-w-0">{entry.name}</span>
      </h3>
      {pictured && !missing && (
        <img
          src={source.pictureHref!(path)}
          alt={entry.name}
          onError={() => setMissing(true)}
          className="max-h-96 w-full shrink-0 rounded border border-line object-contain"
        />
      )}
      {kind === 'video' && (
        <video src={source.rawHref(path)} controls preload="metadata" className="w-full rounded" />
      )}
      {kind === 'audio' && (
        <audio src={source.rawHref(path)} controls preload="metadata" className="w-full" />
      )}
      {read.data?.kind === 'text' && (
        <pre className="max-h-96 shrink-0 overflow-auto rounded border border-line p-2 font-mono text-xs whitespace-pre-wrap">
          {read.data.text!.slice(0, GLANCED_TEXT)}
        </pre>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">{t('explorer.kind')}</dt>
        <dd>{kindLabel(kind, extension, t)}</dd>
        {entry.size !== null && (
          <>
            <dt className="text-muted">{t('explorer.size')}</dt>
            <dd>{formatSize(entry.size, formatNumber)}</dd>
          </>
        )}
        {entry.modified && (
          <>
            <dt className="text-muted">{t('explorer.updated')}</dt>
            <dd>{formatDate(entry.modified)}</dd>
          </>
        )}
      </dl>
    </>
  );
}

/** A file opened in the browser's place: its text to edit, or what it is and a download. */
function FileView({
  source,
  path,
  onBack,
  onDirty,
}: {
  source: FileSource;
  path: string;
  onBack: () => void;
  onDirty?: (dirty: boolean) => void;
}) {
  const { t, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const [dirty, setDirtyHere] = useState(false);
  const told = useRef(onDirty);
  useEffect(() => {
    told.current = onDirty;
  });
  const setDirty = (now: boolean) => {
    setDirtyHere(now);
    told.current?.(now);
  };
  useEffect(() => () => told.current?.(false), []);
  const [leaving, setLeaving] = useState(false);
  const opened = useQuery({ queryKey: fileKey(source, path), queryFn: () => source.read(path) });
  return (
    <div className="flex min-h-full w-full flex-col gap-2">
      <div>
        <button
          type="button"
          onClick={() => (dirty ? setLeaving(true) : onBack())}
          className={button}
        >
          <ArrowLeft size={16} aria-hidden />
          {t('workspace.files.back')}
        </button>
      </div>
      {opened.isPending ? (
        <Loading />
      ) : opened.isError ? (
        <p className="text-sm text-danger">{errorMessage(opened.error, t)}</p>
      ) : opened.data.kind === 'text' ? (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded border border-line">
          <CodeEditor
            source={source.key}
            path={path}
            opened={opened.data}
            read={() => source.read(path)}
            write={(text, hash) => source.write(path, text, hash)}
            readOnly={!source.writable}
            onWritten={(written, text) => {
              queryClient.setQueryData<Opened>(fileKey(source, path), (before) =>
                before ? { ...before, ...written, text } : before,
              );
              void queryClient.invalidateQueries({ queryKey: listKey(source, above(path)) });
            }}
            onRead={(now) => queryClient.setQueryData(fileKey(source, path), now)}
            onDirty={setDirty}
          />
        </div>
      ) : (
        <div className="flex flex-col items-start gap-3 text-sm">
          <p className="font-mono text-xs text-muted">{path}</p>
          <p>
            {t(opened.data.kind === 'large' ? 'workspace.files.large' : 'workspace.files.binary')}{' '}
            <span className="text-muted">{formatSize(opened.data.size, formatNumber)}</span>
          </p>
          <a href={source.rawHref(path, true)} download={nameOf(path)} className={button}>
            <Download size={14} aria-hidden />
            {t('file.download')}
          </a>
        </div>
      )}
      {leaving && (
        <ConfirmDialog
          heading={t('workspace.files.discard')}
          confirmLabel={t('workspace.files.discardConfirm')}
          onConfirm={onBack}
          onClose={() => setLeaving(false)}
        >
          {t('workspace.files.discardBody')}
        </ConfirmDialog>
      )}
    </div>
  );
}

type Dialog =
  | { type: 'folder' }
  | { type: 'rename'; name: string }
  | { type: 'move'; names: string[] }
  | { type: 'remove'; names: string[] };

/** The files of a source as My documents lists its own: a click shows, a double click opens, a
 * long press or Ctrl-click chooses; what the source lets be changed is made, renamed, moved,
 * deleted, uploaded and edited here. The page it stands on lays out what `frame` is given. */
export function FileBrowser({
  source,
  path,
  file,
  onGo,
  onDirty,
  frame,
}: {
  source: FileSource;
  path: string;
  /** The file opened in the browser's place, none while it lists the folder. */
  file: string | null;
  onGo: (path: string, file?: string) => void;
  /** Whether the file opened holds changes not yet saved, for a page that guards leaving it. */
  onDirty?: (dirty: boolean) => void;
  frame: (parts: Framed) => ReactNode;
}) {
  const { t, formatDate, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const wide = useWide();
  const [sort, setSort] = useState<Sort>(storedSort);
  const [previewing, setPreviewing] = useState(storedPreview);
  const [glance, setGlance] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [menuOn, setMenuOn] = useState<'folder' | 'selection'>('folder');
  const [sending, setSending] = useState<{ done: number; total: number } | null>(null);
  const listed = useQuery({ queryKey: listKey(source, path), queryFn: () => source.list(path) });
  const entries = sorted(listed.data?.entries ?? [], sort);
  const names = entries.map((entry) => entry.name);
  const choice = useChoice(names);
  const chosen = entries.filter((entry) => choice.has(entry.name));
  const glimpsed = entries.find((entry) => entry.name === glance);
  const glanced = chosen.length > 0 ? chosen : glimpsed ? [glimpsed] : [];
  const beside = wide && previewing;
  const close = () => setDialog(null);
  const settled = () => {
    choice.choose([]);
    setGlance(null);
    return queryClient.invalidateQueries({ queryKey: ['files', source.key] });
  };
  const changing = useMutation({ mutationFn: (change: () => Promise<unknown>) => change() });
  const change = (made: () => Promise<unknown>) =>
    changing.mutate(made, { onSettled: () => void settled() });

  const sent = async (picked: Picked[]) => {
    const made = new Set<string>();
    let done = 0;
    setSending({ done, total: picked.length });
    try {
      for (const { file: each, folders } of picked) {
        let into = path;
        for (const folder of folders) {
          const next = within(into, folder);
          if (!made.has(next)) {
            made.add(next);
            await source.folder(into, folder).catch(() => undefined);
          }
          into = next;
        }
        await source.put(into, each.name, each);
        setSending({ done: ++done, total: picked.length });
      }
    } finally {
      setSending(null);
    }
  };
  const send = (picked: Picked[] | Promise<Picked[]>) => change(async () => sent(await picked));
  const picker = useFilePicker((files) => send(loose(files)));
  const area = useDropTarget({ onFiles: source.writable ? send : undefined });

  const open = (entry: FileEntry) => {
    const at = within(path, entry.name);
    if (entry.kind === 'folder') onGo(at);
    else if (entry.kind !== 'file') return;
    else if (played(entry)) window.open(source.rawHref(at), '_blank', 'noopener,noreferrer');
    else onGo(path, at);
  };
  const toggled = useRef<string | null>(null);
  const select = (entry: FileEntry, event: MouseEvent) => {
    if (choice.pressed() || event.detail > 1) return;
    const choosing = choice.many > 0 || event.ctrlKey || event.metaKey;
    toggled.current = choosing ? entry.name : null;
    if (choosing) choice.toggle(entry.name, event.shiftKey);
    else if (beside) setGlance(entry.name);
    else open(entry);
  };
  const sortBy = (key: SortKey) => {
    const next = { key, descending: sort.key === key && !sort.descending };
    setSort(next);
    storeSort(next);
  };
  const preview = (on: boolean) => {
    setPreviewing(on);
    storePreview(on);
  };

  const newItems = (
    <>
      <MenuItem
        icon={Folder}
        label={t('create.folder')}
        disabled={!source.writable}
        onSelect={() => setDialog({ type: 'folder' })}
      />
      <MenuItem
        icon={FileUp}
        label={t('create.upload')}
        disabled={!source.writable}
        onSelect={picker.open}
      />
    </>
  );
  const itemsFor = (those: FileEntry[]) => {
    const [single] = those;
    const alone = those.length === 1;
    const paths = those.map((entry) => within(path, entry.name));
    return (
      <>
        {alone && (
          <MenuItem
            icon={single.kind === 'folder' ? FolderOpen : Pencil}
            label={t('tree.open')}
            disabled={single.kind !== 'folder' && single.kind !== 'file'}
            onSelect={() => open(single)}
          />
        )}
        {alone && single.kind === 'file' && (
          <MenuItem
            icon={Download}
            label={t('file.download')}
            onSelect={() => window.open(source.rawHref(paths[0], true), '_self')}
          />
        )}
        {source.more?.(paths, () => choice.choose([]))}
        <MenuSeparator />
        {alone && (
          <MenuItem
            icon={Pencil}
            label={t('tree.rename')}
            disabled={!source.writable}
            onSelect={() => setDialog({ type: 'rename', name: single.name })}
          />
        )}
        <MenuItem
          icon={FolderInput}
          label={t('tree.move')}
          disabled={!source.writable}
          onSelect={() => setDialog({ type: 'move', names: those.map((entry) => entry.name) })}
        />
        <MenuItem
          icon={Trash2}
          label={t('files.delete')}
          disabled={!source.writable}
          onSelect={() => setDialog({ type: 'remove', names: those.map((entry) => entry.name) })}
        />
      </>
    );
  };

  const cell = 'px-2 py-2 whitespace-nowrap';
  const title = [source.name, ...(path ? path.split('/') : [])].join(' / ');
  if (file !== null)
    return frame({
      title: `${nameOf(file)} – ${source.name}`,
      actions: null,
      primary: null,
      panel: null,
      children: (
        <FileView
          key={file}
          source={source}
          path={file}
          onBack={() => onGo(path)}
          onDirty={onDirty}
        />
      ),
    });
  return frame({
    title,
    actions: (
      <>
        <button
          type="button"
          aria-label={t('files.refresh')}
          title={t('files.refresh')}
          onClick={() => void queryClient.invalidateQueries({ queryKey: ['files', source.key] })}
          className={iconButton}
        >
          <RefreshCw size={16} aria-hidden className={listed.isFetching ? 'animate-spin' : ''} />
        </button>
        {wide && (
          <button
            type="button"
            aria-pressed={previewing}
            onClick={() => preview(!previewing)}
            className={`${button} aria-pressed:bg-selected`}
          >
            <PanelRight size={16} aria-hidden />
            <span className="sr-only lg:not-sr-only">{t('preview.title')}</span>
          </button>
        )}
      </>
    ),
    primary: (
      <Menu
        trigger={
          <button type="button" disabled={!source.writable} className={primaryButton}>
            <Plus size={16} aria-hidden />
            <span className="sr-only sm:not-sr-only">{t('create.new')}</span>
            <ChevronDown size={16} aria-hidden />
          </button>
        }
      >
        {newItems}
      </Menu>
    ),
    panel: beside && (
      <Panel title={t('preview.title')} onClose={() => preview(false)}>
        {glanced.length === 0 ? (
          <p className="text-sm text-muted">{t('preview.none')}</p>
        ) : glanced.length > 1 ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="text-muted">{t('explorer.selected')}</dt>
            <dd>{formatNumber(glanced.length)}</dd>
            <dt className="text-muted">{t('explorer.size')}</dt>
            <dd>
              {formatSize(
                glanced.reduce((sum, entry) => sum + (entry.size ?? 0), 0),
                formatNumber,
              )}
            </dd>
          </dl>
        ) : (
          <Glance
            key={glanced[0].name}
            source={source}
            path={within(path, glanced[0].name)}
            entry={glanced[0]}
          />
        )}
      </Panel>
    ),
    children: (
      <>
        <ContextMenuArea
          items={menuOn === 'selection' ? itemsFor(chosen) : newItems}
          onOpen={(event) => {
            const name = (event.target as HTMLElement)
              .closest('tr[data-name]')
              ?.getAttribute('data-name');
            if (name && !choice.has(name)) choice.choose([name], name);
            setMenuOn(name ? 'selection' : 'folder');
          }}
        >
          <div
            {...area.props}
            onClick={() => {
              choice.choose([]);
              setGlance(null);
            }}
            onKeyDown={(event) =>
              choice.onKeyDown(event, () => {
                if (source.writable) setDialog({ type: 'remove', names: choice.chosen });
              })
            }
            className={`flex min-h-full w-full max-w-5xl flex-col gap-3 rounded ${area.over ? 'outline-2 -outline-offset-2 outline-dashed outline-muted' : ''}`}
          >
            <Crumbs source={source} path={path} onGo={(to) => onGo(to)} />
            {listed.isPending ? (
              <Loading />
            ) : listed.isError ? (
              <p className="text-sm text-danger">{errorMessage(listed.error, t)}</p>
            ) : entries.length === 0 ? (
              <p className="text-muted">{t('workspace.files.empty')}</p>
            ) : (
              <div>
                {chosen.length > 0 && (
                  <ChoiceBar all={choice.all} over>
                    <button
                      type="button"
                      aria-label={t('tree.move')}
                      title={t('tree.move')}
                      disabled={!source.writable}
                      onClick={() => setDialog({ type: 'move', names: choice.chosen })}
                      className={iconButton}
                    >
                      <FolderInput size={16} aria-hidden />
                    </button>
                    <button
                      type="button"
                      aria-label={t('files.delete')}
                      title={t('files.delete')}
                      disabled={!source.writable}
                      onClick={() => setDialog({ type: 'remove', names: choice.chosen })}
                      className={iconButton}
                    >
                      <Trash2 size={16} aria-hidden />
                    </button>
                    <ActionsMenu>{itemsFor(chosen)}</ActionsMenu>
                  </ChoiceBar>
                )}
                <table className="w-full border-collapse">
                  <thead className="text-left text-sm text-muted">
                    <tr className="h-10 border-b border-line">
                      <th className="w-10 px-3" />
                      {COLUMNS.map((column) => (
                        <th
                          key={column.key}
                          aria-sort={
                            sort.key === column.key
                              ? sort.descending
                                ? 'descending'
                                : 'ascending'
                              : undefined
                          }
                          className={`px-2 py-2 font-normal whitespace-nowrap ${column.className}`}
                        >
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              sortBy(column.key);
                            }}
                            className="inline-flex items-center gap-1 hover:text-ink"
                          >
                            {t(column.label)}
                            {sort.key === column.key &&
                              (sort.descending ? (
                                <ChevronDown size={14} aria-hidden />
                              ) : (
                                <ChevronUp size={14} aria-hidden />
                              ))}
                          </button>
                        </th>
                      ))}
                      <th className="w-10" />
                    </tr>
                  </thead>
                  <tbody onClick={(event) => event.stopPropagation()}>
                    {entries.map((entry) => {
                      const selected = choice.has(entry.name);
                      const current =
                        beside && chosen.length === 0 && glanced[0]?.name === entry.name;
                      const extension = extensionOf(entry.name);
                      return (
                        <tr
                          key={entry.name}
                          {...choice.press(() => choice.toggle(entry.name))}
                          data-name={entry.name}
                          aria-selected={selected}
                          aria-current={current ? 'true' : undefined}
                          tabIndex={0}
                          onClick={(event) => select(entry, event)}
                          onDoubleClick={() => {
                            if (beside || toggled.current === entry.name) open(entry);
                          }}
                          onKeyDown={(event: KeyboardEvent) => {
                            if (event.target !== event.currentTarget) return;
                            if (event.key === 'Enter') open(entry);
                            if (event.key === ' ') {
                              event.preventDefault();
                              choice.toggle(entry.name);
                            }
                          }}
                          className={`cursor-default border-b border-line select-none [-webkit-touch-callout:none] ${selected || current ? 'bg-selected' : 'hover:bg-hover'}`}
                        >
                          <td className="px-3" onClick={(event) => event.stopPropagation()}>
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => choice.toggle(entry.name)}
                              aria-label={t('explorer.select')}
                              className={`align-middle ${chosen.length > 0 ? '' : 'invisible'}`}
                            />
                          </td>
                          <td className={`${cell} max-w-0`}>
                            <div className="flex items-center gap-3">
                              <KindIcon kind={kindOf(entry)} extension={extension} />
                              <span className="truncate">{entry.name}</span>
                            </div>
                          </td>
                          <td className={`${cell} hidden text-sm text-muted md:table-cell`}>
                            {kindLabel(kindOf(entry), extension, t)}
                          </td>
                          <td className={`${cell} hidden text-sm text-muted sm:table-cell`}>
                            {entry.modified && formatDate(entry.modified)}
                          </td>
                          <td
                            className={`${cell} hidden text-right text-sm text-muted md:table-cell`}
                          >
                            {entry.size !== null && formatSize(entry.size, formatNumber)}
                          </td>
                          <td
                            className="pr-2"
                            onClick={(event) => event.stopPropagation()}
                            onDoubleClick={(event) => event.stopPropagation()}
                          >
                            <ActionsMenu>{itemsFor([entry])}</ActionsMenu>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {sending && (
              <p className="text-sm text-muted" role="status">
                {`${t('upload.progress')} ${formatNumber(sending.done)} / ${formatNumber(sending.total)}`}
              </p>
            )}
            {changing.error && (
              <p role="alert" className="text-sm text-danger">
                {errorMessage(changing.error, t)}
              </p>
            )}
          </div>
        </ContextMenuArea>
        {picker.element}
        {dialog?.type === 'folder' && (
          <NameDialog
            heading={t('create.folder')}
            submitLabel={t('tree.create')}
            maxLength={255}
            onSubmit={(name) => source.folder(path, name)}
            onDone={() => {
              close();
              void settled();
            }}
            onClose={close}
          />
        )}
        {dialog?.type === 'rename' && (
          <NameDialog
            heading={t('tree.rename')}
            submitLabel={t('tree.save')}
            initial={dialog.name}
            maxLength={255}
            onSubmit={(name) => source.rename(within(path, dialog.name), within(path, name))}
            onDone={() => {
              close();
              void settled();
            }}
            onClose={close}
          />
        )}
        {dialog?.type === 'move' && (
          <FolderPick
            source={source}
            from={path}
            moving={dialog.names.map((name) => within(path, name))}
            onPick={(folder) => {
              const moving = dialog.names;
              close();
              change(async () => {
                for (const name of moving)
                  await source.rename(within(path, name), within(folder, name));
              });
            }}
            onClose={close}
          />
        )}
        {dialog?.type === 'remove' && (
          <ConfirmDialog
            heading={t('files.deleteHeading')}
            confirmLabel={t('files.delete')}
            onConfirm={() => {
              const removing = dialog.names.map((name) => within(path, name));
              change(() => source.remove(removing));
            }}
            onClose={close}
          >
            {t('files.deleteBody')}
          </ConfirmDialog>
        )}
      </>
    ),
  });
}
