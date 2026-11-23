import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  Bookmark,
  ChevronDown,
  ChevronUp,
  ClipboardPaste,
  Copy,
  Download,
  FileArchive,
  FileUp,
  Folder,
  FolderUp,
  Lock,
  FolderInput,
  FolderOpen,
  Info,
  Link2,
  PanelRight,
  Pencil,
  Plus,
  RefreshCw,
  Scissors,
  Search,
  Trash2,
} from 'lucide-react';
import {
  createContext,
  Fragment,
  useContext,
  useEffect,
  useRef,
  useState,
  type DragEvent,
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
  saveFrom,
  storedPreview,
  storedSort,
  storePreview,
  storeSort,
  type Sort,
  type SortKey,
} from './explorer';
import { AddressBar, Properties } from './filesParts';
import { Loading, Panel, useWide } from './frame';
import { useI18n } from './i18n';
import { HeldView, type HeldKind } from './kinds';
import { useReachable } from './live';
import { filesHref } from './locationsData';
import type { MessageKey } from './i18n/hr';
import { ActionsMenu, ContextMenuArea, Menu, MenuItem, MenuSeparator } from './menu';
import { button, field, iconButton, primaryButton } from './styles';
import { errorMessage, KindIcon, kindLabel, useOpen, type ShownKind } from './tree';
import { inFolder, loose, useFilePicker, type Picked } from './upload';

export interface FileEntry {
  name: string;
  /** Anything but a folder or a file is listed and nothing more. A symbolic link has its
   * target's kind, `link` where the target does not exist. */
  kind: string;
  size: number | null;
  modified: string | null;
  /** Where a symbolic link points. */
  link?: string | null;
  /** Hidden by the source itself, as SMB's attribute, beside a name that begins with a dot. */
  hidden?: boolean;
  /** The name shown where `name` is an id, as a node of Ponistra's tree. */
  label?: string;
  /** Its name as a file where the label leaves out the extension, as a document's title. */
  fileName?: string;
  extension?: string | null;
  /** What the entry is, where its source knows it better than its name tells. */
  shown?: ShownKind;
  /** Who changed it last, where the source knows. */
  by?: string | null;
  /** The heading it is listed under, where the source divides its list. */
  heading?: string;
  /** It stays in the browser: neither downloaded nor dragged out. */
  kept?: boolean;
}

export interface Listed {
  path: string;
  entries: FileEntry[];
  /** Whether the folder takes changes, where the source tells it folder by folder. */
  writable?: boolean;
  /** What the folder holds stays in the browser, as a folder on its way keeps it. */
  kept?: boolean;
}

/** A column a source adds to the list beside the browser's own. */
export interface SourceColumn {
  label: MessageKey;
  className: string;
  cell: (path: string, entry: FileEntry) => ReactNode;
}

/** A file as it is saved, its name and type for a drag out of the browser. */
export interface SavedFile {
  name: string;
  type: string;
  href: string;
}

export interface FileStat extends FileEntry {
  path: string;
  /** Unix bits (07777), none where the source has them not, as SMB. */
  mode: number | null;
  owner: string | null;
  group: string | null;
  uid: number | null;
  gid: number | null;
  /** SMB's: readonly, hidden, system, archive. */
  attributes?: string[];
}

export interface Found extends FileEntry {
  path: string;
}

/** Where a file browser's files live: a location on the network, a project of the workspace,
 * Ponistra's own tree. The browser knows nothing else of it. Paths are relative, their parts
 * joined by a slash, the top the empty one. What a source does not do, the browser does not
 * offer. */
export interface FileSource {
  /** Tells the source from every other among the page's queries, in a bookmark and to the
   * backend copying and moving between sources: `location:<id>`, `workspace:<folder>`,
   * `ponistra:<mine|company|shared>`, whose paths are chains of node ids. */
  key: string;
  name: string;
  writable: boolean;
  list: (path: string) => Promise<Listed>;
  rawHref: (path: string, download?: boolean) => string;
  /** An image or a PDF's first page drawn small, where the source draws them. */
  pictureHref?: (path: string) => string;
  /** The file's address that what it holds is shown under, as a file of Documents shows it. */
  heldBase?: (path: string) => string;
  /** The files and folders as one zip, a folder with all it holds. */
  zipHref?: (paths: string[]) => string;
  /** Where a file opens when Ponistra itself opens it, as a document in its editor. */
  openHref?: (path: string, entry: FileEntry) => string | null;
  /** The names of the folders along a path, where its parts are ids. */
  labels?: (path: string) => Promise<string[]>;
  read: (path: string) => Promise<Opened>;
  write: (path: string, text: string, hash: string) => Promise<Written>;
  folder: (path: string, name: string) => Promise<unknown>;
  /** Renames, and moves to another folder of the source. */
  rename: (path: string, to: string) => Promise<unknown>;
  remove: (paths: string[]) => Promise<unknown>;
  put: (path: string, name: string, file: File) => Promise<unknown>;
  /** What else the source does with the entries chosen, as items of their menu. */
  more?: (paths: string[], done: () => void) => ReactNode;
  /** The menu of a heading the source groups its entries under, as a group of boards. */
  headingItems?: (heading: string) => ReactNode;
  /** Buttons on the bar of the chosen entries, before moving and removing them. */
  chosenActions?: (paths: string[]) => ReactNode;
  /** Shown above a folder's entries, as a Docker stack beside its files; read again whenever
   * the folder's listing is. */
  aside?: (path: string, listedAt: number) => ReactNode;
  stat?: (path: string) => Promise<FileStat>;
  mode?: (path: string, mode: number) => Promise<FileStat>;
  owner?: (path: string, uid: number, gid: number) => Promise<FileStat>;
  /** Entries below a folder by name. */
  search?: (path: string, query: string) => Promise<{ entries: Found[]; partial: boolean }>;
  /** A folder's size with all it holds. */
  folderSize?: (
    path: string,
  ) => Promise<{ size: number; files: number; folders: number; partial: boolean }>;
  checksum?: (
    path: string,
    algorithm: 'sha256' | 'sha1' | 'md5',
  ) => Promise<{ algorithm: string; digest: string }>;
  /** What is removed goes to a trash it can be brought back from, so nothing is asked first. */
  trash?: boolean;
  /** A file downloaded or dragged out as the source saves it, none where it is no file. */
  saved?: (path: string, entry: FileEntry) => SavedFile | undefined;
  icon?: (path: string, entry: FileEntry) => ReactNode;
  /** Shown after an entry's name, as the favourite's star. */
  marks?: (path: string, entry: FileEntry) => ReactNode;
  columns?: SourceColumn[];
  /** More of the New menu, after a folder and an upload. */
  create?: (path: string) => ReactNode;
  /** Whether the entries may be renamed, moved and removed, as each node of Ponistra's tree
   * answers by its own role wherever it is listed; the folder's writability otherwise. */
  changes?: (paths: string[]) => boolean;
  /** False where a folder takes nothing new though its entries change, as a group of boards. */
  makes?: (path: string) => boolean;
  /** More of the folder's own menu. */
  folderItems?: (path: string) => ReactNode;
  /** More buttons above the list. */
  actions?: (path: string) => ReactNode;
  /** The preview beside the list, in place of the browser's own glance. */
  preview?: (path: string, chosen: string[], onClose: () => void) => ReactNode;
  /** A panel the source opens itself, shown before the preview while it is open. */
  usePanel?: (path: string) => ReactNode;
  /** Takes what is picked or dropped in the place of the file browser's own upload, as Ponistra
   * imports documents and reports what it kept as files. */
  useSend?: () => ((path: string, picked: Picked[]) => void) | null;
  /** The list is there to show what it holds: the preview opens on the first of them. */
  showing?: (path: string) => boolean;
  empty?: (path: string) => MessageKey;
  /** Told of a drag of its entries, to say them also as what else takes them. */
  dragged?: (event: DragEvent, paths: string[], saved?: SavedFile) => void;
  /** Its own dialog for moving entries, in place of the browser's pick of a folder of it. */
  moveTo?: (paths: string[], onClose: () => void) => ReactNode;
  /** Rendered once on the page for the source, whatever pane shows it: its dialogs. */
  host?: ReactNode;
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
/** A path as one segment of an address, base64url without padding. */
export const segment = (path: string) =>
  btoa(String.fromCharCode(...new TextEncoder().encode(path)))
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replace(/=+$/, '');
export const listKey = (source: FileSource, path: string) => ['files', source.key, 'list', path];
const fileKey = (source: FileSource, path: string) => ['files', source.key, 'file', path];

const PICTURES = [
  'png',
  'jpg',
  'jpeg',
  'gif',
  'webp',
  'bmp',
  'avif',
  'tif',
  'tiff',
  'heic',
  'ico',
  'psd',
];
const SOUND = ['mp3', 'm4a', 'ogg', 'oga', 'wav', 'flac'];
const VIDEO = ['mp4', 'm4v', 'webm', 'mov', 'ogv'];
/** As much of a text file as a glance reads and shows. */
const GLANCED = 256 * 1024;
const GLANCED_TEXT = 20_000;

const extensionOf = (name: string) =>
  name.includes('.', 1) ? name.slice(name.lastIndexOf('.') + 1).toLowerCase() : '';

/** What the server shows of what a file holds, told by its name, as Documents tells it by its
 * bytes. */
const HELD: Record<string, HeldKind> = {
  bmp: 'picture',
  ico: 'picture',
  tif: 'picture',
  tiff: 'picture',
  psd: 'picture',
  ...Object.fromEntries(
    [
      'zip',
      'tar',
      'gz',
      'tgz',
      'bz2',
      'xz',
      'zst',
      'lz4',
      '7z',
      'rar',
      'iso',
      'cab',
      'lzh',
      'xar',
    ].map((extension) => [extension, 'archive' as const]),
  ),
  eml: 'message',
  mht: 'message',
  mhtml: 'message',
  msg: 'message',
  vcf: 'cards',
  ics: 'events',
  md: 'markdown',
  markdown: 'markdown',
};

const heldOf = (source: FileSource, name: string): HeldKind | null =>
  (source.heldBase && HELD[extensionOf(name)]) || null;

const iconExtension = (entry: FileEntry) =>
  entry.extension !== undefined ? (entry.extension ?? '') : extensionOf(shownName(entry));

/** The name an entry is shown by. */
export const shownName = (entry: FileEntry) => entry.label ?? entry.name;

export const hiddenName = (entry: FileEntry) => entry.hidden || shownName(entry).startsWith('.');

function kindOf(entry: FileEntry): ShownKind {
  if (entry.shown) return entry.shown;
  if (entry.kind === 'folder') return 'folder';
  const extension = extensionOf(entry.name);
  if (extension === 'pdf') return 'file';
  if (PICTURES.includes(extension) || extension === 'svg') return 'image';
  if (SOUND.includes(extension)) return 'audio';
  if (VIDEO.includes(extension)) return 'video';
  return 'other';
}

/** What a browser shows by itself, in a tab of its own. */
const played = (source: FileSource, entry: FileEntry) =>
  !heldOf(source, entry.name) && ['file', 'image', 'audio', 'video'].includes(kindOf(entry));

const collator = new Intl.Collator('hr', { numeric: true, sensitivity: 'base' });

function compare(a: FileEntry, b: FileEntry, key: SortKey): number {
  switch (key) {
    case 'kind':
      return collator.compare(iconExtension(a), iconExtension(b));
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
    const order = compare(a, b, sort.key) || collator.compare(shownName(a), shownName(b));
    return sort.descending ? -order : order;
  });
}

const noPanel = (): ReactNode => null;
const noSend = () => null;

/** The entries under the headings the source lists them by, in the order it gave the headings,
 * each heading's entries as they are sorted. */
function grouped(entries: FileEntry[], given: FileEntry[]): FileEntry[] {
  if (!given.some((entry) => entry.heading)) return entries;
  const order = new Map<string, number>();
  for (const entry of given)
    if (!order.has(entry.heading ?? '')) order.set(entry.heading ?? '', order.size);
  return entries
    .map((entry, index) => ({ entry, index }))
    .sort(
      (one, other) =>
        order.get(one.entry.heading ?? '')! - order.get(other.entry.heading ?? '')! ||
        one.index - other.index,
    )
    .map(({ entry }) => entry);
}

/** A file as it is saved; the browser's own download where the source opens no file itself. */
const savedOf = (source: FileSource, path: string, entry: FileEntry): SavedFile | undefined =>
  entry.kind !== 'file'
    ? undefined
    : source.saved
      ? source.saved(path, entry)
      : source.openHref
        ? undefined
        : {
            name: shownName(entry),
            type: 'application/octet-stream',
            href: source.rawHref(path, true),
          };

const COLUMNS: { key: SortKey; label: MessageKey; className: string }[] = [
  { key: 'title', label: 'tree.name', className: 'w-full' },
  { key: 'kind', label: 'explorer.kind', className: 'hidden md:table-cell' },
  { key: 'updated_at', label: 'explorer.updated', className: 'hidden sm:table-cell' },
  { key: 'size', label: 'explorer.size', className: 'hidden md:table-cell text-right' },
];

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
      <AddressBar source={source} path={path} onGo={setPath} />
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
                <span className="truncate">{shownName(entry)}</span>
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
  const extension = iconExtension(entry);
  const [missing, setMissing] = useState(false);
  const held = entry.kind === 'file' ? heldOf(source, entry.name) : null;
  const reads = !held && kind === 'other' && entry.size !== null && entry.size <= GLANCED;
  const read = useQuery({
    queryKey: fileKey(source, path),
    queryFn: () => source.read(path),
    enabled: reads,
  });
  const pictured =
    !held && source.pictureHref?.(path) && (kind === 'file' || PICTURES.includes(extension));
  return (
    <>
      <h3 className="flex items-start gap-2 font-semibold break-words">
        <KindIcon kind={kind} extension={extension} decorative />
        <span className="min-w-0">{shownName(entry)}</span>
      </h3>
      {pictured && !missing && (
        <img
          src={source.pictureHref!(path)}
          alt={shownName(entry)}
          onError={() => setMissing(true)}
          className="max-h-96 w-full shrink-0 rounded border border-line object-contain"
        />
      )}
      {held && <HeldView base={source.heldBase!(path)} kind={held} title={entry.name} compact />}
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
  const found = heldOf(source, nameOf(path));
  const held = found === 'markdown' ? null : found;
  const opened = useQuery({
    queryKey: fileKey(source, path),
    queryFn: () => source.read(path),
    enabled: !held,
  });
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
      {held ? (
        <div className="flex min-h-0 flex-1 flex-col items-start gap-3">
          <a href={source.rawHref(path, true)} download={nameOf(path)} className={button}>
            <Download size={14} aria-hidden />
            {t('file.download')}
          </a>
          <div className="flex min-h-0 w-full flex-1 flex-col items-center overflow-auto">
            <HeldView base={source.heldBase!(path)} kind={held} title={nameOf(path)} />
          </div>
        </div>
      ) : opened.isPending ? (
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

/** What was copied or cut, to be pasted into a folder of the same source or another. */
export interface Clip {
  source: FileSource;
  paths: string[];
  cut: boolean;
}

/** What the page of Files gives each pane it shows: how entries are laid out, the clipboard
 * the panes share, and what puts entries of one source into a folder of another. */
export interface Desk {
  view: 'list' | 'grid';
  hidden: boolean;
  clip: Clip | null;
  setClip: (clip: Clip | null) => void;
  put: (from: FileSource, paths: string[], to: FileSource, folder: string, move: boolean) => void;
  /** The source entries dragged from another pane come from. */
  sourceOf: (key: string) => FileSource | undefined;
  bookmark: (source: FileSource, path: string) => void;
}

export const DeskContext = createContext<Desk | null>(null);

const ENTRIES = 'application/x-ponistra-files';
/** The source of the entries being dragged, which a drop target cannot read before the drop. */
let draggedFrom: string | null = null;

type Dialog =
  | { type: 'folder' }
  | { type: 'rename'; name: string; label: string }
  | { type: 'move'; names: string[] }
  | { type: 'remove'; names: string[] }
  | { type: 'properties'; entry: FileEntry };

/** The entries below a folder whose names hold what was typed, as the source finds them. */
function Searched({
  source,
  path,
  query,
  onOpen,
}: {
  source: FileSource;
  path: string;
  query: string;
  onOpen: (found: Found) => void;
}) {
  const { t, formatNumber } = useI18n();
  const found = useQuery({
    queryKey: ['files', source.key, 'search', path, query],
    queryFn: () => source.search!(path, query),
  });
  if (found.isPending) return <Loading />;
  if (found.isError) return <p className="text-sm text-danger">{errorMessage(found.error, t)}</p>;
  const { entries, partial } = found.data;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-muted" role="status">
        {`${t('files.found')} ${formatNumber(entries.length)}`}
        {partial && ` (${t('files.partial')})`}
      </p>
      <ul className="flex flex-col">
        {entries.map((entry) => (
          <li key={entry.path}>
            <button
              type="button"
              onClick={() => onOpen(entry)}
              className="flex w-full min-w-0 items-center gap-3 rounded px-2 py-1.5 text-left hover:bg-hover"
            >
              <KindIcon kind={kindOf(entry)} extension={iconExtension(entry)} />
              <span className="truncate">{shownName(entry)}</span>
              <span className="ml-auto truncate font-mono text-xs text-muted">
                {above(entry.path)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** An entry drawn small in the grid: its picture where the source draws one, else its icon. */
function Thumb({ source, path, entry }: { source: FileSource; path: string; entry: FileEntry }) {
  const [missing, setMissing] = useState(false);
  const kind = kindOf(entry);
  const extension = iconExtension(entry);
  const picture =
    entry.kind === 'file' &&
    (kind === 'file' || PICTURES.includes(extension)) &&
    source.pictureHref?.(path);
  if (picture && !missing)
    return (
      <img
        src={picture}
        alt=""
        loading="lazy"
        onError={() => setMissing(true)}
        className="h-full w-full object-contain"
      />
    );
  return <KindIcon kind={kind} extension={extension} size={40} />;
}

/** The files of a source as My documents lists its own: a click shows, a double click opens, a
 * long press or Ctrl-click chooses; what the source lets be changed is made, renamed, moved,
 * deleted, uploaded and edited here, copied, cut and pasted with the keyboard and dragged
 * between panes. The page it stands on lays out what `frame` is given. */
export function FileBrowser({
  source,
  path,
  file,
  onGo,
  onDirty,
  onFocus,
  frame,
}: {
  source: FileSource;
  path: string;
  /** The file opened in the browser's place, none while it lists the folder. */
  file: string | null;
  onGo: (path: string, file?: string) => void;
  /** Whether the file opened holds changes not yet saved, for a page that guards leaving it. */
  onDirty?: (dirty: boolean) => void;
  /** Told when the user turns to this browser, of two side by side. */
  onFocus?: () => void;
  frame: (parts: Framed) => ReactNode;
}) {
  const { t, formatDate, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const desk = useContext(DeskContext);
  const wide = useWide();
  const [sort, setSort] = useState<Sort>(storedSort);
  const showing = source.showing?.(path) ?? false;
  const [previewing, setPreviewing] = useState(() => showing || storedPreview());
  const [glance, setGlance] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [menuOn, setMenuOn] = useState<'folder' | 'selection'>('folder');
  const [menuHeading, setMenuHeading] = useState<string | null>(null);
  const opened = useOpen();
  const usePanel = source.usePanel ?? noPanel;
  const sidePanel = usePanel(path);
  const [sending, setSending] = useState<{ done: number; total: number } | null>(null);
  const [typed, setTyped] = useState('');
  const [query, setQuery] = useState('');
  const [over, setOver] = useState<string | null>(null);
  useEffect(() => {
    const wait = setTimeout(() => setQuery(typed.trim()), 300);
    return () => clearTimeout(wait);
  }, [typed]);
  useEffect(() => {
    setTyped('');
    setQuery('');
  }, [path, source.key]);
  const listed = useQuery({
    queryKey: listKey(source, path),
    queryFn: () => source.list(path),
    placeholderData: keepPreviousData,
  });
  const labels = useQuery({
    queryKey: ['files', source.key, 'labels', path],
    queryFn: () => source.labels!(path),
    enabled: Boolean(source.labels && path),
    staleTime: 60_000,
  });
  const reachable = useReachable();
  const writable = (listed.data?.writable ?? source.writable) && reachable;
  const keptHere = Boolean(listed.data?.kept);
  const stays = (those: FileEntry[]) => keptHere || those.some((entry) => entry.kept);
  const hidden = desk?.hidden ?? true;
  const entries = grouped(
    sorted(
      (listed.data?.entries ?? []).filter((entry) => hidden || !hiddenName(entry)),
      sort,
    ),
    listed.data?.entries ?? [],
  );
  const grid = desk?.view === 'grid';
  const names = entries.map((entry) => entry.name);
  const choice = useChoice(names);
  const chosen = entries.filter((entry) => choice.has(entry.name));
  const glimpsed = entries.find((entry) => entry.name === glance);
  const glanced =
    chosen.length > 0 ? chosen : glimpsed ? [glimpsed] : showing ? entries.slice(0, 1) : [];
  const beside = wide && previewing && !sidePanel;
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
  const sends = (source.useSend ?? noSend)();
  const send = (picked: Picked[] | Promise<Picked[]>) =>
    sends
      ? void Promise.resolve(picked).then((all) => sends(path, all))
      : change(async () => sent(await picked));
  const picker = useFilePicker((files) => send(loose(files)));
  const folderPicker = useFilePicker((files) => send(inFolder(files)), { folder: true });
  const area = useDropTarget({ onFiles: writable ? send : undefined });
  const changeable = (names: string[]) =>
    names.length > 0 && (source.changes ? reachable && source.changes(pathsOf(names)) : writable);

  const pathsOf = (those: string[]) => those.map((name) => within(path, name));
  const remove = (names: string[]) => {
    if (!names.length) return;
    if (!source.trash) return setDialog({ type: 'remove', names });
    setGlance(null);
    change(() => source.remove(pathsOf(names)));
  };
  const copy = (names: string[], cut: boolean) =>
    desk && names.length > 0 && desk.setClip({ source, paths: pathsOf(names), cut });
  const paste = (into = path) => {
    const clip = desk?.clip;
    if (!desk || !clip || !writable) return;
    desk.put(clip.source, clip.paths, source, into, clip.cut);
    if (clip.cut) desk.setClip(null);
  };
  const takes = (event: DragEvent) =>
    Boolean(desk && writable && event.dataTransfer.types.includes(ENTRIES));
  const moves = (event: DragEvent) => draggedFrom === source.key && !event.ctrlKey && !event.altKey;
  /** Where entries dragged from a pane land: the folder shown, or a folder of it. */
  const dropOn = (folder: string | null) => ({
    onDragOver: (event: DragEvent) => {
      if (!takes(event)) return;
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = moves(event) ? 'move' : 'copy';
      setOver(folder ?? '');
    },
    onDragLeave: (event: DragEvent) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(null);
    },
    onDrop: (event: DragEvent) => {
      if (!takes(event)) return;
      event.preventDefault();
      event.stopPropagation();
      setOver(null);
      const given = JSON.parse(event.dataTransfer.getData(ENTRIES)) as {
        source: string;
        paths: string[];
      };
      const from = desk!.sourceOf(given.source);
      const into = folder === null ? path : within(path, folder);
      if (!from || given.paths.some((each) => into === each || into.startsWith(`${each}/`))) return;
      desk!.put(from, given.paths, source, into, moves(event));
    },
  });
  const pane = dropOn(null);
  const drag = (entry: FileEntry) => ({
    draggable: Boolean(desk),
    onDragStart: (event: DragEvent) => {
      const names = choice.has(entry.name) ? choice.chosen : [entry.name];
      const alone = names.length === 1 && !stays([entry]);
      source.dragged?.(
        event,
        pathsOf(names),
        alone ? savedOf(source, within(path, entry.name), entry) : undefined,
      );
      draggedFrom = source.key;
      event.dataTransfer.setData(
        ENTRIES,
        JSON.stringify({ source: source.key, paths: pathsOf(names) }),
      );
      event.dataTransfer.effectAllowed = 'copyMove';
    },
    onDragEnd: () => {
      draggedFrom = null;
    },
  });

  const open = (entry: FileEntry) => {
    const at = within(path, entry.name);
    if (entry.kind === 'folder') return onGo(at);
    if (entry.kind !== 'file') return;
    const href = source.openHref?.(at, entry);
    if (href) opened(href);
    else if (played(source, entry))
      window.open(source.rawHref(at), '_blank', 'noopener,noreferrer');
    else onGo(path, at);
  };
  const openFound = (found: Found) => {
    if (found.kind === 'folder') return onGo(found.path);
    const href = source.openHref?.(found.path, found);
    if (href) opened(href);
    else if (played(source, found))
      window.open(source.rawHref(found.path), '_blank', 'noopener,noreferrer');
    else onGo(above(found.path), found.path);
  };
  const toggled = useRef<string | null>(null);
  const select = (entry: FileEntry, event: MouseEvent) => {
    if (choice.pressed() || event.detail > 1) return;
    const choosing = choice.many > 0 || event.ctrlKey || event.metaKey;
    toggled.current = choosing ? entry.name : null;
    if (choosing) choice.toggle(entry.name, event.shiftKey);
    else if (beside || grid) setGlance(entry.name);
    else open(entry);
  };
  const sortBy = (key: SortKey) => {
    const next = { key, descending: sort.key === key && !sort.descending };
    setSort(next);
    storeSort(next);
  };
  const preview = (on: boolean) => {
    setPreviewing(on);
    if (!showing) storePreview(on);
  };

  const makes = writable && source.makes?.(path) !== false;
  const newItems = (
    <>
      <MenuItem
        icon={Folder}
        label={t('create.folder')}
        disabled={!makes}
        onSelect={() => setDialog({ type: 'folder' })}
      />
      <MenuItem icon={FileUp} label={t('create.upload')} disabled={!makes} onSelect={picker.open} />
      <MenuItem
        icon={FolderUp}
        label={t('create.uploadFolder')}
        disabled={!makes}
        onSelect={folderPicker.open}
      />
      {source.create?.(path)}
    </>
  );
  const folderItems = (
    <>
      {newItems}
      {desk && (
        <>
          <MenuSeparator />
          <MenuItem
            icon={ClipboardPaste}
            label={t('files.paste')}
            disabled={!desk.clip || !writable}
            onSelect={() => paste()}
          />
          <MenuItem
            icon={Bookmark}
            label={t('files.bookmark')}
            onSelect={() => desk.bookmark(source, path)}
          />
        </>
      )}
      {source.zipHref && (
        <>
          <MenuSeparator />
          <MenuItem
            icon={FileArchive}
            label={t('zip.folder')}
            disabled={keptHere}
            hint={keptHere ? t('confined.hint') : undefined}
            onSelect={() => saveFrom(source.zipHref!([path]))}
          />
        </>
      )}
      {source.folderItems?.(path)}
    </>
  );
  const itemsFor = (those: FileEntry[]) => {
    const [single] = those;
    const alone = those.length === 1;
    const paths = those.map((entry) => within(path, entry.name));
    const names = those.map((entry) => entry.name);
    const saved = alone ? savedOf(source, paths[0], single) : undefined;
    const inside = stays(those);
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
        {saved && (
          <MenuItem
            icon={Download}
            label={t('file.download')}
            disabled={inside}
            hint={inside ? t('confined.hint') : undefined}
            onSelect={() => window.open(saved.href, '_self')}
          />
        )}
        {source.zipHref && !saved && (
          <MenuItem
            icon={FileArchive}
            label={t('zip.download')}
            disabled={inside}
            hint={inside ? t('confined.hint') : undefined}
            onSelect={() => saveFrom(source.zipHref!(paths))}
          />
        )}
        {source.more?.(paths, () => choice.choose([]))}
        {desk && (
          <>
            <MenuSeparator />
            <MenuItem icon={Copy} label={t('files.copy')} onSelect={() => copy(names, false)} />
            <MenuItem
              icon={Scissors}
              label={t('files.cut')}
              disabled={!changeable(names)}
              onSelect={() => copy(names, true)}
            />
            {alone && single.kind === 'folder' && (
              <>
                <MenuItem
                  icon={ClipboardPaste}
                  label={t('files.pasteInto')}
                  disabled={!desk.clip}
                  onSelect={() => paste(paths[0])}
                />
                <MenuItem
                  icon={Bookmark}
                  label={t('files.bookmark')}
                  onSelect={() => desk.bookmark(source, paths[0])}
                />
              </>
            )}
          </>
        )}
        <MenuSeparator />
        {alone && (
          <MenuItem
            icon={Pencil}
            label={t('tree.rename')}
            disabled={!changeable(names)}
            onSelect={() =>
              setDialog({ type: 'rename', name: single.name, label: shownName(single) })
            }
          />
        )}
        <MenuItem
          icon={FolderInput}
          label={t('tree.move')}
          disabled={!changeable(names)}
          onSelect={() => setDialog({ type: 'move', names })}
        />
        <MenuItem
          icon={Trash2}
          label={t(source.trash ? 'tree.toTrash' : 'files.delete')}
          disabled={!changeable(names)}
          onSelect={() => remove(names)}
        />
        {alone && (
          <>
            <MenuSeparator />
            <MenuItem
              icon={Info}
              label={t('files.properties')}
              onSelect={() => setDialog({ type: 'properties', entry: single })}
            />
          </>
        )}
      </>
    );
  };

  const keys = (event: KeyboardEvent) => {
    if (desk && (event.ctrlKey || event.metaKey) && !event.altKey) {
      const key = event.key.toLowerCase();
      if (key === 'c' || key === 'x') {
        if (key === 'x' && !changeable(choice.chosen)) return;
        event.preventDefault();
        copy(choice.chosen.length ? choice.chosen : glance ? [glance] : [], key === 'x');
        return;
      }
      if (key === 'v') {
        event.preventDefault();
        paste();
        return;
      }
    }
    choice.onKeyDown(event, () => {
      if (changeable(choice.chosen)) remove(choice.chosen);
    });
  };
  const cutHere = (entry: FileEntry) =>
    Boolean(
      desk?.clip?.cut &&
      desk.clip.source.key === source.key &&
      desk.clip.paths.includes(within(path, entry.name)),
    );

  const cell = 'px-2 py-2 whitespace-nowrap';
  const title = [
    source.name,
    ...(path ? (labels.data ?? (source.labels ? [] : path.split('/'))) : []),
  ].join(' / ');
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
  const rowOf = (entry: FileEntry) => {
    const selected = choice.has(entry.name);
    const current = (beside || grid) && chosen.length === 0 && glanced[0]?.name === entry.name;
    const folder = entry.kind === 'folder';
    return {
      ...choice.press(() => choice.toggle(entry.name)),
      ...drag(entry),
      ...(folder ? dropOn(entry.name) : {}),
      'data-name': entry.name,
      'aria-selected': selected,
      'aria-current': current ? ('true' as const) : undefined,
      tabIndex: 0,
      onClick: (event: MouseEvent) => select(entry, event),
      onDoubleClick: () => {
        if (beside || grid || toggled.current === entry.name) open(entry);
      },
      onAuxClick: (event: MouseEvent) => {
        if (event.button !== 1) return;
        const at = within(path, entry.name);
        const href =
          entry.kind === 'folder' ? filesHref(source.key, at) : source.openHref?.(at, entry);
        if (!href) return;
        event.preventDefault();
        window.open(href, '_blank');
      },
      onKeyDown: (event: KeyboardEvent) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === 'Enter') open(entry);
        if (event.key === ' ') {
          event.preventDefault();
          choice.toggle(entry.name);
        }
      },
      shade: `${selected || current ? 'bg-selected' : 'hover:bg-hover'} ${over === entry.name ? 'outline-2 -outline-offset-2 outline-dashed outline-muted' : ''} ${cutHere(entry) ? 'opacity-50' : ''}`,
    };
  };
  const listing = grid ? (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))] gap-2">
      {entries.map((entry) => {
        const { shade, ...row } = rowOf(entry);
        return (
          <li
            key={entry.name}
            {...row}
            className={`flex cursor-default flex-col items-center gap-1 rounded p-2 select-none [-webkit-touch-callout:none] ${shade}`}
          >
            <div className="flex h-20 w-full items-center justify-center overflow-hidden rounded">
              <Thumb source={source} path={within(path, entry.name)} entry={entry} />
            </div>
            <span className="line-clamp-2 w-full text-center text-sm break-words">
              {entry.link !== undefined && entry.link !== null && (
                <Link2 size={12} aria-label={t('files.link')} className="mr-1 inline" />
              )}
              {shownName(entry)}
            </span>
          </li>
        );
      })}
    </ul>
  ) : (
    <table className="w-full border-collapse">
      <thead className="text-left text-sm text-muted">
        <tr className="h-10 border-b border-line">
          <th className="w-10 px-3" />
          {COLUMNS.map((column) => (
            <th
              key={column.key}
              aria-sort={
                sort.key === column.key ? (sort.descending ? 'descending' : 'ascending') : undefined
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
          {source.columns?.map((column) => (
            <th
              key={column.label}
              className={`px-2 py-2 font-normal whitespace-nowrap ${column.className}`}
            >
              {t(column.label)}
            </th>
          ))}
          <th className="w-10" />
        </tr>
      </thead>
      <tbody onClick={(event) => event.stopPropagation()}>
        {entries.map((entry, index) => {
          const { shade, ...row } = rowOf(entry);
          const selected = choice.has(entry.name);
          const extension = iconExtension(entry);
          const at = within(path, entry.name);
          const heading =
            entry.heading !== undefined && entry.heading !== entries[index - 1]?.heading
              ? entry.heading
              : null;
          return (
            <Fragment key={entry.name}>
              {heading !== null && (
                <tr>
                  <th
                    scope="rowgroup"
                    colSpan={COLUMNS.length + (source.columns?.length ?? 0) + 2}
                    className="px-3 pt-4 pb-1 text-left font-normal"
                  >
                    <span className="flex items-baseline gap-2">
                      <h2 data-heading={heading} className="font-semibold">
                        {heading}
                      </h2>
                      <span className="text-sm text-muted">
                        {formatNumber(entries.filter((each) => each.heading === heading).length)}
                      </span>
                    </span>
                  </th>
                </tr>
              )}
              <tr
                key={entry.name}
                {...row}
                className={`cursor-default border-b border-line select-none [-webkit-touch-callout:none] ${shade}`}
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
                    {source.icon?.(at, entry) ?? (
                      <KindIcon kind={kindOf(entry)} extension={extension} />
                    )}
                    <span className="truncate">{shownName(entry)}</span>
                    {source.marks?.(at, entry)}
                    {entry.link !== undefined && entry.link !== null && (
                      <span
                        title={entry.link}
                        className="flex min-w-0 shrink items-center gap-1 text-sm text-muted"
                      >
                        <Link2 size={14} aria-label={t('files.link')} className="shrink-0" />
                        <span className="truncate font-mono text-xs">{entry.link}</span>
                      </span>
                    )}
                  </div>
                </td>
                <td className={`${cell} hidden text-sm text-muted md:table-cell`}>
                  {kindLabel(kindOf(entry), extension, t)}
                </td>
                <td className={`${cell} hidden text-sm text-muted sm:table-cell`}>
                  {entry.modified && formatDate(entry.modified)}
                </td>
                <td className={`${cell} hidden text-right text-sm text-muted md:table-cell`}>
                  {entry.size !== null &&
                    entry.kind !== 'folder' &&
                    formatSize(entry.size, formatNumber)}
                </td>
                {source.columns?.map((column) => (
                  <td key={column.label} className={`${cell} ${column.className}`}>
                    {column.cell(at, entry)}
                  </td>
                ))}
                <td
                  className="pr-2"
                  onClick={(event) => event.stopPropagation()}
                  onDoubleClick={(event) => event.stopPropagation()}
                >
                  <ActionsMenu>{itemsFor([entry])}</ActionsMenu>
                </td>
              </tr>
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
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
        {source.actions?.(path)}
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
          <button type="button" disabled={!writable} className={primaryButton}>
            <Plus size={16} aria-hidden />
            <span className="sr-only sm:not-sr-only">{t('create.new')}</span>
            <ChevronDown size={16} aria-hidden />
          </button>
        }
      >
        {newItems}
      </Menu>
    ),
    panel:
      sidePanel ||
      (beside &&
        (source.preview ? (
          source.preview(
            path,
            glanced.map((entry) => within(path, entry.name)),
            () => preview(false),
          )
        ) : (
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
        ))),
    children: (
      <>
        <ContextMenuArea
          items={
            menuHeading !== null && source.headingItems
              ? source.headingItems(menuHeading)
              : menuOn === 'selection'
                ? itemsFor(chosen)
                : folderItems
          }
          onOpen={(event) => {
            setMenuHeading(
              (event.target as HTMLElement)
                .closest('[data-heading]')
                ?.getAttribute('data-heading') ?? null,
            );
            const name = (event.target as HTMLElement)
              .closest('[data-name]')
              ?.getAttribute('data-name');
            if (name && !choice.has(name)) choice.choose([name], name);
            setMenuOn(name ? 'selection' : 'folder');
          }}
        >
          <div
            {...area.props}
            onDragOver={(event) =>
              takes(event) ? pane.onDragOver(event) : area.props.onDragOver(event)
            }
            onDragLeave={(event) => {
              pane.onDragLeave(event);
              area.props.onDragLeave(event);
            }}
            onDrop={(event) => (takes(event) ? pane.onDrop(event) : area.props.onDrop(event))}
            onFocusCapture={onFocus}
            onPointerDownCapture={onFocus}
            onClick={() => {
              choice.choose([]);
              setGlance(null);
            }}
            onKeyDown={keys}
            className={`flex min-h-full w-full flex-col gap-3 rounded ${desk ? '' : 'max-w-5xl'} ${area.over || over === '' ? 'outline-2 -outline-offset-2 outline-dashed outline-muted' : ''}`}
          >
            <div
              className="flex min-w-0 items-center gap-2"
              onClick={(event) => event.stopPropagation()}
            >
              <AddressBar source={source} path={path} onGo={(to) => onGo(to)} />
              {source.search && (
                <label className="relative shrink-0">
                  <Search
                    size={14}
                    aria-hidden
                    className="pointer-events-none absolute top-1/2 left-2 -translate-y-1/2 text-muted"
                  />
                  <input
                    type="search"
                    value={typed}
                    onChange={(event) => setTyped(event.target.value)}
                    placeholder={t('files.search')}
                    aria-label={t('files.search')}
                    className={`${field} w-36 pl-7 text-sm sm:w-48`}
                  />
                </label>
              )}
            </div>
            {source.aside?.(path, listed.dataUpdatedAt)}
            {keptHere && (
              <p className="flex items-center gap-2 text-sm text-muted">
                <Lock size={14} aria-hidden />
                {t('confined.hint')}
              </p>
            )}
            {query && source.search ? (
              <Searched source={source} path={path} query={query} onOpen={openFound} />
            ) : listed.isPending ? (
              <Loading />
            ) : listed.isError ? (
              <p className="text-sm text-danger">{errorMessage(listed.error, t)}</p>
            ) : entries.length === 0 ? (
              <p className="text-muted">{t(source.empty?.(path) ?? 'workspace.files.empty')}</p>
            ) : (
              <div>
                {chosen.length > 0 && (
                  <ChoiceBar all={choice.all} over>
                    {source.chosenActions?.(pathsOf(choice.chosen))}
                    <button
                      type="button"
                      aria-label={t('tree.move')}
                      title={t('tree.move')}
                      disabled={!changeable(choice.chosen)}
                      onClick={() => setDialog({ type: 'move', names: choice.chosen })}
                      className={iconButton}
                    >
                      <FolderInput size={16} aria-hidden />
                    </button>
                    <button
                      type="button"
                      aria-label={t(source.trash ? 'tree.toTrash' : 'files.delete')}
                      title={t(source.trash ? 'tree.toTrash' : 'files.delete')}
                      disabled={!changeable(choice.chosen)}
                      onClick={() => remove(choice.chosen)}
                      className={iconButton}
                    >
                      <Trash2 size={16} aria-hidden />
                    </button>
                    <ActionsMenu>{itemsFor(chosen)}</ActionsMenu>
                  </ChoiceBar>
                )}
                <div inert={listed.isPlaceholderData}>{listing}</div>
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
        {folderPicker.element}
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
            initial={dialog.label}
            maxLength={255}
            onSubmit={(name) => source.rename(within(path, dialog.name), within(path, name))}
            onDone={() => {
              close();
              void settled();
            }}
            onClose={close}
          />
        )}
        {dialog?.type === 'move' && source.moveTo && (
          <>
            {source.moveTo(pathsOf(dialog.names), () => {
              close();
              void settled();
            })}
          </>
        )}
        {dialog?.type === 'move' && !source.moveTo && (
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
        {dialog?.type === 'properties' && (
          <Properties
            source={source}
            path={within(path, dialog.entry.name)}
            entry={dialog.entry}
            onClose={close}
          />
        )}
      </>
    ),
  });
}
