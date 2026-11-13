import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ChevronDown,
  ChevronRight,
  File,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FilePlay,
  FileSpreadsheet,
  FileText,
  FileType,
  Folder,
  Globe,
  LayoutDashboard,
  type LucideIcon,
  Presentation,
} from 'lucide-react';
import {
  type ComponentProps,
  Fragment,
  type ReactNode,
  useCallback,
  useEffect,
  useState,
} from 'react';
import { Link, Navigate, useNavigate } from 'react-router';
import { segment } from './address';
import { ApiError, getJson, postJson } from './api';
import { useDropTarget } from './drag';
import type { User } from './auth';
import { isMessageKey, useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { Menu } from './menu';

export type NodeKind = 'folder' | 'document' | 'file' | 'link';

/** The longest title the backend takes. */
export const LONGEST_TITLE = 200;

export type Role = 'read' | 'edit' | 'own';

export type Root = 'mine' | 'company' | 'shared';

const RANK: Record<Role, number> = { read: 1, edit: 2, own: 3 };

export function covers(role: Role | null | undefined, needs: Role): boolean {
  return !!role && RANK[role] >= RANK[needs];
}

export interface Grantee {
  kind: 'user' | 'group' | 'everyone';
  id: number | null;
  name: string | null;
  email?: string;
  /** Someone outside the installation, given the node by their address (D39). */
  outside?: boolean;
}

/** What an import could not carry over; a spreadsheet's also names the functions we do not
 * compute and the first cells whose value differs from the file's, and a file with macros
 * gives their source to read. */
export interface ImportReport {
  fonts: { from: string; to: string | null }[];
  lost: Record<string, number>;
  accepted: number;
  functions?: string[];
  cells?: string[];
  macros?: { name: string; code: string }[];
}

/** How a document's tables read the numbers and dates typed into them, `en` being American
 * English. */
export const DOCUMENT_LOCALES = ['hr', 'en', 'en-GB', 'de', 'fr', 'it', 'es'] as const;
export type DocumentLocale = (typeof DOCUMENT_LOCALES)[number];

export interface TreeNode {
  id: string;
  parent: string | null;
  kind: NodeKind;
  title: string;
  locale: DocumentLocale;
  updated_at: string;
  updated_by: User | null;
  /** A file's bytes, or what a document's content takes as stored once it is measured. */
  size: number | null;
  /** What a document holds by its content, once it is measured. */
  holds: 'text' | 'table' | 'slides' | null;
  /** What a file's bytes are, which decides how PONISTRA shows it: a PDF, an image, or bytes
   * of a kind it only keeps. */
  media_type: string | null;
  /** The id of an image's or a PDF's picture for a glance once it is drawn, of a link's site's
   * icon once its page is read. */
  picture: string | null;
  /** The extension of a file's name, which names its kind. */
  extension: string | null;
  /** A link's page, and what the page says of itself once it is read. */
  href: string | null;
  description: string;
  trashed_at: string | null;
  /** The Office format the file the document came from was read as. */
  original: 'docx' | 'xlsx' | 'pptx' | null;
  /** The file the document came from, by the extension it keeps. */
  origin: { extension: string; size: number } | null;
  /** The format that gives back the macros of the file the document came from. */
  macros: 'docm' | 'xlsm' | 'pptm' | null;
  imported: ImportReport | null;
  /** A top-level folder the administrator lays out for the company. */
  company: boolean;
  /** A folder whose documents leave the browser only for their owners. */
  confined: boolean;
  /** The top-level folder of its owner's notes. */
  notes: boolean;
  /** The top-level folder of its owner's links, whose folders are its groups. */
  links: boolean;
  /** The top-level folder of its owner's boards, whose folders are its groups. */
  boards: boolean;
  /** How many columns the page of links lays a group's tiles in at most. */
  columns: number | null;
  /** The folder of the code workspace a board's agent starts in, chosen by its owner. */
  agent_folder: string | null;
}

/** A node listed away from its folder, with the path the user finds it along. */
export interface FoundNode extends TreeNode {
  path: Pick<TreeNode, 'id' | 'kind' | 'title' | 'notes' | 'links' | 'boards'>[];
  root: Root;
}

export const ROOT_LABELS: Record<Root, MessageKey> = {
  mine: 'tree.root',
  company: 'tree.company',
  shared: 'tree.shared',
};

/** A step on a way: a place of the user's own goes by the interface's name for it, whatever the
 * language it was made in. */
export function stepTitle(
  step: Pick<TreeNode, 'title' | 'notes' | 'links' | 'boards'>,
  t: (key: MessageKey) => string,
): string {
  if (step.notes) return t('notes.title');
  if (step.links) return t('links.title');
  return step.boards ? t('boards.title') : step.title;
}

export function placeText(node: FoundNode, t: (key: MessageKey) => string): string {
  const [top] = node.path;
  const titles = node.path.map((above) => stepTitle(above, t));
  return (
    top?.notes || top?.links || top?.boards ? titles : [t(ROOT_LABELS[node.root]), ...titles]
  ).join(' › ');
}

export interface ListedNode extends TreeNode {
  role: Role;
  audience: (Grantee & { role: Role })[];
  wider: boolean;
  /** A folder on its way keeps it in the browser; said only by a list across folders. */
  kept?: boolean;
}

export interface Tab {
  id: string;
  parent: string | null;
  title: string;
  position: number;
}

export interface LiveTab extends Tab {
  room: string;
}

export interface Place {
  path: TreeNode[];
  root: Root;
  role: Role;
  /** Whether a folder on the way keeps what is here in the browser for this user. */
  confined: boolean;
}

interface Listing extends Place {
  folder: TreeNode | null;
  children: ListedNode[];
}

/** The bytes a file is shown from, and how far the reading of its pages without text got:
 * `checking` until it is known whether any page lacks text. */
export interface FileBytes {
  served: string;
  recognised: boolean;
  ocr: 'checking' | 'waiting' | 'done' | 'refused' | 'failed' | null;
  reason: 'encrypted' | 'signed' | null;
  /** The language of its text once it is read, where code can tell it. */
  language: string | null;
}

export interface Placement extends Place {
  node: TreeNode;
  /** A document's own room, for its theme and styles; a file's, for its notes. */
  room: string | null;
  tabs: LiveTab[];
  pdf: FileBytes | null;
}

export const TREE = ['tree'];

export function nodeKey(id: string) {
  return [...TREE, 'node', id];
}

/** A folder's listing; `stays` keeps the one shown before while the next loads, as a page going
 * from folder to folder does, and a listing not `enabled` is only read where it was loaded. It is
 * read again while a link in it waits for its page to be read. */
export function useFolder(id: string | null, { stays = false, enabled = true } = {}) {
  return useQuery({
    queryKey: [...TREE, 'folder', id],
    queryFn: () => getJson<Listing>(id ? `/api/nodes?parent=${id}` : '/api/nodes'),
    placeholderData: stays ? keepPreviousData : undefined,
    enabled,
  });
}

export function useShared(byMe = false) {
  return useQuery({
    queryKey: [...TREE, 'shared', byMe ? 'me' : 'others'],
    queryFn: () => getJson<{ children: ListedNode[] }>(`/api/nodes/shared${byMe ? '?by=me' : ''}`),
  });
}

export function useCompany() {
  return useQuery({
    queryKey: [...TREE, 'company'],
    queryFn: () => getJson<{ children: ListedNode[] }>('/api/nodes/company'),
  });
}

export function useBoards() {
  return useQuery({
    queryKey: [...TREE, 'boards'],
    queryFn: () => getJson<{ children: (ListedNode & FoundNode)[] }>('/api/nodes/boards'),
  });
}

export function useFavourites() {
  return useQuery({
    queryKey: [...TREE, 'favourites'],
    queryFn: () => getJson<{ children: (ListedNode & FoundNode)[] }>('/api/nodes/favourites'),
  });
}

export function useRecent() {
  return useQuery({
    queryKey: [...TREE, 'recent'],
    queryFn: () => getJson<{ items: FoundNode[] }>('/api/nodes/recent'),
  });
}

export function useNode(id: string | null) {
  return useQuery({
    queryKey: nodeKey(id ?? ''),
    queryFn: () => getJson<Placement>(`/api/nodes/${id}`),
    enabled: id !== null,
    refetchInterval: ({ state }) =>
      state.data?.pdf?.ocr === 'checking' || state.data?.pdf?.ocr === 'waiting' ? 2000 : false,
  });
}

export function useTrash() {
  return useQuery({
    queryKey: [...TREE, 'trash'],
    queryFn: () =>
      getJson<{
        items: (TreeNode & { role: Role; kept: 'held' | 'retained' | null })[];
      }>('/api/trash'),
  });
}

export function useTreeChange<V, R>(mutationFn: (variables: V) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TREE }),
  });
}

/** Moves nodes into a folder; given the child to stand before, or null for after them all, lays
 * them out there. */
export function useMove() {
  return useTreeChange(
    ({ ids, parent, before }: { ids: string[]; parent: string | null; before?: string | null }) =>
      postJson('/api/nodes/move', { nodes: ids, parent, before }),
  );
}

export function useToTrash() {
  return useTreeChange((ids: string[]) => postJson('/api/nodes/trash', { nodes: ids }));
}

const ROUTES: Record<Exclude<NodeKind, 'link'>, string> = { folder: 'f', document: 'd', file: 'p' };

/** Where a node opens: in PONISTRA at its route, a link at its page. */
export function nodeHref(
  node: Pick<TreeNode, 'id' | 'kind' | 'title'> & { href?: string | null },
): string {
  if (node.kind === 'link') return node.href ?? '';
  return `/${ROUTES[node.kind]}/${segment(node.title, node.id)}`;
}

/** Whether an address leaves PONISTRA, as a link's page does: it opens in a tab of its own. */
export function leaves(href: string): boolean {
  return /^https?:\/\//i.test(href);
}

/** Opens an address: one in PONISTRA by the router, a link's page in a tab of its own. */
export function useOpen() {
  const navigate = useNavigate();
  return useCallback(
    (href: string) => {
      if (leaves(href)) window.open(href, '_blank', 'noopener,noreferrer');
      else void navigate(href);
    },
    [navigate],
  );
}

/** The router's link, or for a link's page an anchor that opens it in a tab of its own. */
export function PlaceLink({ to, ...props }: ComponentProps<typeof Link> & { to: string }) {
  if (!leaves(to)) return <Link to={to} {...props} />;
  const { replace: _replace, state: _state, ...anchor } = props;
  return <a href={to} target="_blank" rel="noopener noreferrer" {...anchor} />;
}

/** A node reached at a route not of its kind goes where it opens; a link's page replaces the
 * tab, as an address typed would. */
export function Elsewhere({ node }: { node: Pick<TreeNode, 'id' | 'kind' | 'title' | 'href'> }) {
  const href = nodeHref(node);
  useEffect(() => {
    if (leaves(href)) window.location.replace(href);
  }, [href]);
  return leaves(href) ? null : <Navigate to={href} replace />;
}

/** What a node is to its reader: a document is text, a table or slides by what it holds; a file
 * is a PDF, an image, a board (a page of HTML named as one, D36), or another file PONISTRA only
 * keeps. */
export type ShownKind =
  NodeKind | 'table' | 'slides' | 'board' | 'image' | 'text' | 'video' | 'audio' | 'other';

export function kindOf(
  node: Pick<TreeNode, 'kind' | 'media_type' | 'holds'> & { extension?: string | null },
): ShownKind {
  if (node.kind === 'document')
    return node.holds === 'table' || node.holds === 'slides' ? node.holds : 'document';
  if (node.kind !== 'file' || node.media_type === 'application/pdf') return node.kind;
  if (node.media_type === 'text/html' && BOARD_NAMES.includes(node.extension?.toLowerCase() ?? ''))
    return 'board';
  const kind = node.media_type?.split('/')[0];
  return kind === 'image' || kind === 'text' || kind === 'video' || kind === 'audio'
    ? kind
    : 'other';
}

const BOARD_NAMES = ['html', 'htm', ''];

export const KIND_ICONS: Record<ShownKind, LucideIcon> = {
  folder: Folder,
  link: Globe,
  document: FileText,
  table: FileSpreadsheet,
  slides: Presentation,
  board: LayoutDashboard,
  file: FileType,
  image: FileImage,
  text: FileCode,
  video: FilePlay,
  audio: FileAudio,
  other: File,
};

/** The look of a file PONISTRA only keeps, by the kind its extension names. */
const EXTENSION_ICONS: [LucideIcon, string[]][] = [
  [FilePlay, ['mp4', 'm4v', 'mov', 'avi', 'mkv', 'webm', 'wmv', 'mpg', 'mpeg']],
  [FileAudio, ['mp3', 'wav', 'flac', 'm4a', 'aac', 'ogg', 'opus', 'wma', 'pcm']],
  [FileArchive, ['zip', 'gz', 'tgz', 'tar', 'bz2', 'xz', '7z', 'rar', 'apk', 'jar', 'iso']],
  [
    FileCode,
    [
      'json',
      'xml',
      'yml',
      'yaml',
      'toml',
      'ini',
      'sh',
      'ps1',
      'bat',
      'py',
      'js',
      'ts',
      'sql',
      'html',
      'css',
      'md',
    ],
  ],
];

function iconOf(kind: ShownKind, extension: string | null | undefined): LucideIcon {
  const by =
    (kind === 'other' || kind === 'text') &&
    EXTENSION_ICONS.find(([, names]) => names.includes(extension ?? ''));
  return by ? by[0] : KIND_ICONS[kind];
}

const NAMED: ShownKind[] = ['folder', 'document', 'table', 'slides', 'board', 'link'];

/** What a node is called in a list; a file by its extension, as an Explorer names it. */
export function kindLabel(
  kind: ShownKind,
  extension: string | null | undefined,
  t: (key: MessageKey) => string,
): string {
  if (NAMED.includes(kind)) return t(`kind.${kind}`);
  return extension ? `${extension.toUpperCase()} ${t('kind.typed')}` : t(`kind.${kind}`);
}

export function KindIcon({
  kind,
  extension,
  decorative,
  size = 18,
}: {
  kind: ShownKind;
  extension?: string | null;
  decorative?: boolean;
  size?: number;
}) {
  const { t } = useI18n();
  const Icon = iconOf(kind, extension);
  const label = decorative
    ? { 'aria-hidden': true }
    : { role: 'img', 'aria-label': kindLabel(kind, extension, t) };
  return <Icon size={size} className="shrink-0 text-muted" {...label} />;
}

/** A node's look in a list: a link by its site's icon once its page is read, any other by its
 * kind. */
export function NodeIcon({
  node,
  decorative,
  size = 18,
}: {
  node: Pick<TreeNode, 'id' | 'kind' | 'media_type' | 'holds' | 'extension' | 'picture'>;
  decorative?: boolean;
  size?: number;
}) {
  const { t } = useI18n();
  const [missing, setMissing] = useState(false);
  const kind = kindOf(node);
  if (kind !== 'link' || !node.picture || missing)
    return <KindIcon kind={kind} extension={node.extension} decorative={decorative} size={size} />;
  return (
    <img
      src={`/api/nodes/${node.id}/picture?v=${node.picture}`}
      alt={decorative ? '' : kindLabel(kind, null, t)}
      onError={() => setMissing(true)}
      width={size}
      height={size}
      className="shrink-0 rounded-sm object-contain"
    />
  );
}

const LETTERS = [
  'bg-account-1/15 text-account-1',
  'bg-account-2/15 text-account-2',
  'bg-account-3/15 text-account-3',
  'bg-account-4/15 text-account-4',
  'bg-account-5/15 text-account-5',
  'bg-account-6/15 text-account-6',
  'bg-account-7/15 text-account-7',
];

/** A link's icon as a tile shows it: the one given or its site's, else the first letter of its
 * name on a colour its site keeps. */
export function LinkIcon({
  link,
  src,
}: {
  link: Pick<TreeNode, 'id' | 'title' | 'href' | 'picture'>;
  /** An image picked for the icon and not yet kept. */
  src?: string | null;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  const picture = link.picture && `/api/nodes/${link.id}/picture?v=${link.picture}`;
  const shown = src ?? (picture !== failed ? picture : null);
  if (shown)
    return (
      <span className="grid size-11 shrink-0 place-items-center rounded-lg bg-surface ring-1 ring-line">
        <img
          src={shown}
          alt=""
          onError={() => setFailed(shown)}
          width={28}
          height={28}
          className="object-contain"
        />
      </span>
    );
  const site = URL.parse(link.href ?? '')?.hostname ?? link.title;
  const colour = [...site].reduce((sum, letter) => sum + letter.charCodeAt(0), 0) % LETTERS.length;
  return (
    <span
      aria-hidden
      className={`grid size-11 shrink-0 place-items-center rounded-lg text-lg font-semibold ${LETTERS[colour]}`}
    >
      {(link.title.trim()[0] ?? '·').toLocaleUpperCase('hr')}
    </span>
  );
}

// What a status means when the answer carries no code: Cloudflare refuses an
// oversized upload with its own page before the request reaches us.
const BARE_STATUS: Record<number, string> = { 404: 'not_found', 413: 'too_large' };

export function errorMessage(error: Error, t: (key: MessageKey) => string): string {
  if (error instanceof ApiError) {
    const key = `error.${error.code ?? BARE_STATUS[error.status] ?? ''}`;
    if (isMessageKey(key)) return t(key);
  }
  return `${t('error.unexpected')}: ${error.message}`;
}

/** The text of an error a source recorded, which comes as a code rather than a response. */
export function codeText(code: string, t: (key: MessageKey) => string): string {
  const key = `error.${code}`;
  return isMessageKey(key) ? t(key) : `${t('error.unexpected')}: ${code}`;
}

export function Failure({ error }: { error: Error }) {
  const { t } = useI18n();
  return (
    <div className="flex w-full max-w-4xl flex-col items-start gap-2">
      <p className="text-danger">{errorMessage(error, t)}</p>
      <Link to="/documents" className="text-sm underline">
        {t('tree.backToRoot')}
      </Link>
    </div>
  );
}

export const SHARED = 'shared';
export const COMPANY = 'company';

export const ROOT_CRUMBS: Record<Root, { href: string; folder: string | null }> = {
  mine: { href: '/documents', folder: null },
  company: { href: '/company', folder: COMPANY },
  shared: { href: '/shared', folder: SHARED },
};

interface Crumb {
  key: string;
  title: string;
  href?: string;
  folder?: string | null;
}

/** What moves the nodes dropped onto a folder into it, null for the user's own documents. */
export type MoveTo = (parent: string | null) => (ids: string[]) => void;

/** A step of the way back, which takes what is dragged onto it into its folder. */
function Step({
  crumb,
  className,
  title,
  moveTo,
}: {
  crumb: Crumb;
  className: string;
  title?: string;
  moveTo?: MoveTo;
}) {
  const folder = crumb.folder === COMPANY || crumb.folder === SHARED ? undefined : crumb.folder;
  const drop = useDropTarget({
    id: folder,
    onNodes: moveTo && folder !== undefined ? moveTo(folder) : undefined,
  });
  return (
    <Link
      to={crumb.href!}
      title={title}
      {...drop.props}
      className={`${className} rounded ${drop.over ? 'outline-2 -outline-offset-2 outline-focus' : ''}`}
    >
      {crumb.title}
    </Link>
  );
}

export function Breadcrumbs({
  path,
  root = 'mine',
  after = [],
  onSelect,
  moveTo,
  compact,
  alone,
  menu,
}: {
  path: TreeNode[];
  root?: Root;
  after?: { title: string; href?: string }[];
  onSelect?: (folder: string | null) => void;
  /** Where the steps take what is dragged onto them. */
  moveTo?: MoveTo;
  compact?: boolean;
  /** Only the page's own step, where the folder tree beside it shows the way. */
  alone?: boolean;
  /** What the last step's own menu offers. */
  menu?: ReactNode;
}) {
  const { t } = useI18n();
  const way: Crumb[] = [
    { key: 'root', title: t(ROOT_LABELS[root]), ...ROOT_CRUMBS[root] },
    ...path.map((node) => ({
      key: node.id,
      title: stepTitle(node, t),
      href: nodeHref(node),
      folder: node.id,
    })),
    ...after.map((crumb, index) => ({ key: `after-${index}`, ...crumb })),
  ];
  const crumbs = alone ? way.slice(-1) : way;
  // A compact trail gives way from its folders first, so the page's own name stays readable
  // longest; the padding inside the clip keeps the steps' focus outlines.
  const step = `text-muted hover:text-ink ${compact ? 'hidden min-w-10 shrink-100 truncate sm:inline' : ''}`;
  const chevron = `shrink-0 text-muted ${compact ? 'hidden sm:block' : ''}`;
  return (
    <nav
      aria-label={t('tree.location')}
      className={`flex min-w-0 items-center gap-1 ${compact ? '-m-1 overflow-hidden p-1 whitespace-nowrap' : 'flex-wrap'}`}
    >
      {crumbs.map((crumb, index) => (
        <Fragment key={crumb.key}>
          {index > 0 && <ChevronRight size={14} aria-hidden className={chevron} />}
          {index === crumbs.length - 1 ? (
            menu ? (
              <Menu
                align="start"
                trigger={
                  <button
                    type="button"
                    aria-current="page"
                    className="flex min-w-0 items-center gap-1 rounded px-1 font-semibold hover:bg-hover"
                  >
                    <span className="truncate">{crumb.title}</span>
                    <ChevronDown size={14} aria-hidden className="shrink-0 text-muted" />
                  </button>
                }
              >
                {menu}
              </Menu>
            ) : (
              <span aria-current="page" className="truncate font-semibold">
                {crumb.title}
              </span>
            )
          ) : onSelect && crumb.folder !== undefined ? (
            <button
              type="button"
              title={compact ? crumb.title : undefined}
              onClick={() => onSelect(crumb.folder!)}
              className={step}
            >
              {crumb.title}
            </button>
          ) : (
            <Step
              crumb={crumb}
              className={step}
              title={compact ? crumb.title : undefined}
              moveTo={moveTo}
            />
          )}
        </Fragment>
      ))}
    </nav>
  );
}
