import * as Dialog from '@radix-ui/react-dialog';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { type UseQueryResult } from '@tanstack/react-query';
import {
  Building2,
  ChevronRight,
  CircleHelp,
  Folder,
  Folders,
  Globe,
  Info,
  Languages,
  LogOut,
  Menu as MenuIcon,
  Pencil,
  Settings,
  FolderKanban,
  LayoutDashboard,
  StickyNote,
  SunMoon,
  Video,
  Trash2,
  Users,
  Vault,
  X,
  type LucideIcon,
  Star,
} from 'lucide-react';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type Dispatch,
  type MouseEvent,
  type ReactNode,
  type SetStateAction,
} from 'react';
import { createPortal } from 'react-dom';
import { Link, Navigate, NavLink, useLocation, useNavigate } from 'react-router';
import { AboutDialog, Signature } from './about';
import { helpFrom, useHelpKey } from './helpKey';
import { ApiError, patchJson } from './api';
import { dayOf, linkOf, nextOf, untilText, useNow, useWindow } from './calendarData';
import { useLogout, useSession, useVisitor } from './auth';
import { Brand, BrandIcon } from './Brand';
import { endDrag, refuseStrayFiles, startDrag, useDropTarget } from './drag';
import { LANGUAGE_NAMES, LANGUAGES, useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { Launches } from './launch';
import { useFollowed } from './followed';
import { useLive, waitingIn } from './live';
import { JoinLink } from './meeting';
import { NameDialog } from './dialogs';
import { ActionsMenu, ContextMenuArea, MenuChoices, MenuItem, MenuSub } from './menu';
import { useMenuPress } from './press';
import { useNoteShortcut } from './notes';
import { initials } from './people';
import { PaletteProvider } from './palette';
import { useKeeper } from './offline';
import { SearchBox } from './search';
import { VoiceButton } from './voice';
import { useGoToProjects } from './workspace';
import { MODULES, type Module } from './modules';
import { PLACES } from './places';
import { Splitter, useWidth, type Column } from './split';
import {
  choosePageTheme,
  chooseTheme,
  PAGE_THEMES,
  type Page,
  usePageTheme,
  THEMES,
  useTheme,
} from './theme';
import { button, iconButton, menu, menuItem, overlay, primaryButton, sideRow } from './styles';
import {
  Breadcrumbs,
  covers,
  errorMessage,
  Failure,
  nodeHref,
  useCompany,
  useFolder,
  useMove,
  useShared,
  useToTrash,
  type ListedNode,
  type MoveTo,
  type Root,
  type TreeNode,
} from './tree';
import { useTitle } from './title';
import { UploadProvider, useUploads, type Picked } from './upload';
import { useAccounts } from './mailData';

type Expansion = [Record<string, boolean>, Dispatch<SetStateAction<Record<string, boolean>>>];

const WIDE = '(min-width: 768px)';
export const FOLDERS: Column = { name: 'folders', initial: 256, min: 192, max: 448 };
/** The separator beside the side column, wherever that column stands. */
export const SIDE_SEPARATOR =
  'w-2 [&>span]:bg-line hover:[&>span]:bg-control active:[&>span]:bg-accent';
const PANEL: Column = { name: 'panel', initial: 320, min: 256, max: 640 };
export const WIDE_PANEL: Column = { name: 'widePanel', initial: 720, min: 320, max: 1200 };

function onWide(change: () => void) {
  const query = matchMedia(WIDE);
  query.addEventListener('change', change);
  return () => query.removeEventListener('change', change);
}

/** Whether the shell has its side column, Tailwind's `md`: below it the column is the drawer. */
export function useWide(): boolean {
  return useSyncExternalStore(onWide, () => matchMedia(WIDE).matches);
}

const ExpansionContext = createContext<Expansion | null>(null);

function DropLink({
  to,
  end,
  folder,
  fixed,
  onNodes,
  onFiles,
  className = '',
  children,
}: {
  to: string;
  end?: boolean;
  folder?: string;
  /** A company folder, which stays where the administrator laid it out. */
  fixed?: boolean;
  onNodes?: (ids: string[]) => void;
  onFiles?: (picked: Promise<Picked[]>) => void;
  className?: string;
  children: ReactNode;
}) {
  const drop = useDropTarget({ id: folder, onNodes, onFiles });
  return (
    <NavLink
      to={to}
      end={end}
      {...drop.props}
      draggable={!!folder && !!onNodes && !fixed}
      onDragStart={folder ? (event) => startDrag(event, [folder]) : undefined}
      onDragEnd={endDrag}
      className={`${sideRow} ${className} ${drop.over ? 'outline-2 -outline-offset-2 outline-focus' : ''}`}
    >
      {children}
    </NavLink>
  );
}

/** What puts the files dropped onto a folder into it, and shows the folder they go into. */
type UploadTo = (folder: string | null, href: string) => (picked: Promise<Picked[]>) => void;

function useUploadTo(): UploadTo {
  const uploads = useUploads();
  const navigate = useNavigate();
  return (folder, href) => (picked) => {
    uploads.start(picked, folder);
    void navigate(href);
  };
}

interface Level {
  depth: number;
  along: Set<string>;
  moveTo: MoveTo;
  uploadTo: UploadTo;
}

function Branch({ parent, ...level }: Level & { parent: string | null }) {
  const listing = useFolder(parent);
  return <FolderRows listing={listing} {...level} />;
}

function SharedBranch(level: Level) {
  const listing = useShared();
  return <FolderRows listing={listing} {...level} />;
}

function CompanyBranch(level: Level) {
  const { t } = useI18n();
  const listing = useCompany();
  if (!listing.data?.children.length) return null;
  return (
    <>
      <NavLink to="/company" end className={sideRow}>
        <Building2 size={16} aria-hidden className="shrink-0 text-muted" />
        {t('tree.company')}
      </NavLink>
      <FolderRows listing={listing} {...level} />
    </>
  );
}

function FolderRows({
  listing,
  ...level
}: Level & {
  listing: UseQueryResult<{ children: ListedNode[] }>;
}) {
  const { t } = useI18n();
  if (listing.isPending) return null;
  if (listing.isError) {
    return (
      <p
        style={{ paddingLeft: `${level.depth * 0.75}rem` }}
        className="px-2 py-1 text-sm text-danger"
      >
        {errorMessage(listing.error, t)}
      </p>
    );
  }
  return listing.data.children
    .filter((node) => node.kind === 'folder' && !node.notes && !node.links && !node.boards)
    .map((folder) => <FolderRow key={folder.id} folder={folder} {...level} />);
}

/** A folder of the tree, with the folders in it once it is opened; a folder known to hold none
 * has nothing to open. */
function FolderRow({ folder, ...level }: Level & { folder: ListedNode }) {
  const { depth, along, moveTo, uploadTo } = level;
  const { t } = useI18n();
  const [open, setOpen] = useContext(ExpansionContext)!;
  const expanded = open[folder.id] ?? along.has(folder.id);
  const listing = useFolder(folder.id, { enabled: expanded });
  const empty = listing.data?.children.every((node) => node.kind !== 'folder');
  const navigate = useNavigate();
  const press = useMenuPress();
  const toTrash = useToTrash();
  const [renaming, setRenaming] = useState(false);
  const fixed = !covers(folder.role, 'edit') || folder.company;
  return (
    <>
      <ContextMenuArea
        items={
          <>
            <MenuItem
              icon={Pencil}
              label={t('tree.rename')}
              disabled={fixed}
              onSelect={() => setRenaming(true)}
            />
            <MenuItem
              icon={Trash2}
              label={t('tree.toTrash')}
              disabled={fixed || toTrash.isPending}
              onSelect={() =>
                toTrash.mutate([folder.id], {
                  onSuccess: () => {
                    if (level.along.has(folder.id)) void navigate('/documents');
                  },
                })
              }
            />
          </>
        }
      >
        <div
          {...press}
          style={{ paddingLeft: `${depth * 0.75}rem` }}
          className="flex items-center select-none [-webkit-touch-callout:none]"
        >
          {empty ? (
            <span aria-hidden className="w-6 shrink-0" />
          ) : (
            <button
              type="button"
              aria-expanded={expanded}
              aria-label={t(expanded ? 'frame.collapse' : 'frame.expand')}
              onClick={() => setOpen((state) => ({ ...state, [folder.id]: !expanded }))}
              className="shrink-0 rounded p-1 text-muted hover:bg-hover hover:text-ink"
            >
              <ChevronRight size={16} className={expanded ? 'rotate-90' : undefined} />
            </button>
          )}
          <DropLink
            to={nodeHref(folder)}
            folder={folder.id}
            fixed={folder.company}
            onNodes={covers(folder.role, 'edit') ? moveTo(folder.id) : undefined}
            onFiles={
              covers(folder.role, 'edit') ? uploadTo(folder.id, nodeHref(folder)) : undefined
            }
            className="flex-1"
          >
            <Folder size={16} aria-hidden className="shrink-0 text-muted" />
            <span className="truncate">{folder.title}</span>
          </DropLink>
        </div>
      </ContextMenuArea>
      {renaming && (
        <NameDialog
          heading={t('tree.rename')}
          submitLabel={t('tree.save')}
          initial={folder.title}
          onSubmit={(renamed) => patchJson(`/api/nodes/${folder.id}`, { title: renamed })}
          onDone={() => setRenaming(false)}
          onClose={() => setRenaming(false)}
        />
      )}
      {expanded && <FolderRows listing={listing} {...level} depth={depth + 1} />}
    </>
  );
}

const KEPT_APART: { to: string; end: boolean; icon: LucideIcon; label: MessageKey }[] = [
  { to: '/notes', end: true, icon: StickyNote, label: 'notes.title' },
  { to: '/links', end: true, icon: Globe, label: 'links.title' },
  { to: '/boards', end: true, icon: LayoutDashboard, label: 'boards.title' },
  { to: '/vault', end: false, icon: Vault, label: 'vault.title' },
];

const PHONE_PLACES: { to: string; icon: LucideIcon; label: MessageKey }[] = [
  { to: '/favourites', icon: Star, label: 'favourites.title' },
  ...KEPT_APART,
  { to: '/trash', icon: Trash2, label: 'trash.title' },
];

function FolderTree({
  path,
  moveTo,
  moving,
}: {
  path: TreeNode[];
  moveTo: MoveTo;
  moving: Error | null;
}) {
  const { t } = useI18n();
  const toTrash = useToTrash();
  const uploadTo = useUploadTo();
  const level = { depth: 0, along: new Set(path.map((node) => node.id)), moveTo, uploadTo };
  const failure = moving ?? toTrash.error;
  if (useVisitor()) {
    return (
      <nav aria-label={t('frame.folders')} className="flex flex-col gap-0.5">
        <NavLink to="/shared" end className={sideRow}>
          <Users size={16} aria-hidden className="shrink-0 text-muted" />
          {t('tree.shared')}
        </NavLink>
        <SharedBranch {...level} />
        {failure && <p className="px-2 text-sm text-danger">{errorMessage(failure, t)}</p>}
      </nav>
    );
  }
  return (
    <nav aria-label={t('frame.folders')} className="flex flex-col gap-0.5">
      <NavLink to="/favourites" end className={sideRow}>
        <Star size={16} aria-hidden className="shrink-0 text-muted" />
        {t('favourites.title')}
      </NavLink>
      <DropLink to="/documents" end onNodes={moveTo(null)} onFiles={uploadTo(null, '/documents')}>
        <Folders size={16} aria-hidden className="shrink-0 text-muted" />
        {t('tree.root')}
      </DropLink>
      <Branch parent={null} {...level} />
      <CompanyBranch {...level} />
      <NavLink to="/shared" end className={sideRow}>
        <Users size={16} aria-hidden className="shrink-0 text-muted" />
        {t('tree.shared')}
      </NavLink>
      <SharedBranch {...level} />
      {KEPT_APART.map(({ to, end, icon: Icon, label }) => (
        <NavLink key={to} to={to} end={end} className={sideRow}>
          <Icon size={16} aria-hidden className="shrink-0 text-muted" />
          {t(label)}
        </NavLink>
      ))}
      <div className="my-2 h-px bg-line" />
      <DropLink to="/trash" onNodes={(ids) => toTrash.mutate(ids)}>
        <Trash2 size={16} aria-hidden className="shrink-0 text-muted" />
        {t('trash.title')}
      </DropLink>
      {failure && <p className="px-2 text-sm text-danger">{errorMessage(failure, t)}</p>}
    </nav>
  );
}

/** The help about the page the user is on, as F1 opens it. */
function HelpButton() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  return (
    <button
      type="button"
      aria-label={t('help.title')}
      title={`${t('help.title')} (F1)`}
      onClick={() => void navigate(helpFrom(pathname))}
      className={`${iconButton} shrink-0`}
    >
      <CircleHelp size={18} />
    </button>
  );
}

/** The places on a phone's page of documents, where the column they stand in is out of sight. */
export function PhonePlaces() {
  const { t } = useI18n();
  return (
    <nav aria-label={t('frame.places')} className="grid grid-cols-3 gap-2 md:hidden">
      {PHONE_PLACES.map(({ to, icon: Icon, label }) => (
        <Link key={to} to={to} className={`${button} min-w-0 flex-col justify-center`}>
          <Icon size={20} aria-hidden className="shrink-0 text-muted" />
          <span className="max-w-full truncate">{t(label)}</span>
        </Link>
      ))}
    </nav>
  );
}

/** The theme of a page that opens in a window of its own: Ponistra's, or light or dark. */
function PageThemeMenu({ page, icon }: { page: Page; icon: LucideIcon }) {
  const { t } = useI18n();
  const theme = usePageTheme(page);
  return (
    <MenuSub icon={icon} label={t(`frame.theme.${page}`)}>
      <MenuChoices
        value={theme}
        choices={PAGE_THEMES.map((value) => ({ value, label: t(`frame.theme.${value}`) }))}
        onChange={(value) => choosePageTheme(page, value)}
      />
    </MenuSub>
  );
}

function UserMenu() {
  const { language, setLanguage, t } = useI18n();
  const theme = useTheme();
  const navigate = useNavigate();
  const user = useSession().data?.user;
  const logout = useLogout();
  const [about, setAbout] = useState(false);
  if (!user) return null;
  const name = user.name || t('log.outsider');

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          aria-label={`${t('frame.account')} ${initials(name)}`}
          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-on-accent"
        >
          {initials(name)}
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={4} className={menu}>
          <DropdownMenu.Label className="max-w-64 truncate px-3 py-1.5 text-sm font-semibold">
            {name}
          </DropdownMenu.Label>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <MenuSub icon={Languages} label={t('frame.language')}>
            <MenuChoices
              value={language}
              choices={LANGUAGES.map((code) => ({ value: code, label: LANGUAGE_NAMES[code] }))}
              onChange={setLanguage}
            />
          </MenuSub>
          <MenuSub icon={SunMoon} label={t('frame.theme')}>
            <MenuChoices
              value={theme}
              choices={THEMES.map((value) => ({ value, label: t(`frame.theme.${value}`) }))}
              onChange={chooseTheme}
            />
          </MenuSub>
          {user.workspace && <PageThemeMenu page="projects" icon={FolderKanban} />}
          <PageThemeMenu page="meetings" icon={Video} />
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          {!user.visitor && (
            <DropdownMenu.Item className={menuItem} onSelect={() => navigate('/settings')}>
              <Settings size={16} aria-hidden className="text-muted" />
              {t('settings.title')}
            </DropdownMenu.Item>
          )}
          <DropdownMenu.Item className={menuItem} onSelect={() => logout.mutate()}>
            <LogOut size={16} aria-hidden className="text-muted" />
            {t('auth.signOut')}
          </DropdownMenu.Item>
          <DropdownMenu.Separator className="my-1 h-px bg-line" />
          <DropdownMenu.Item className={menuItem} onSelect={() => setAbout(true)}>
            <Info size={16} aria-hidden className="text-muted" />
            {t('about.title')}
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
      {about && <AboutDialog onClose={() => setAbout(false)} />}
    </DropdownMenu.Root>
  );
}

function Drawer({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={overlay} />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col gap-2 overflow-y-auto border-r border-line bg-panel p-2 text-ink"
        >
          <Dialog.Title className="px-2 py-1 font-semibold">Ponistra</Dialog.Title>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function Panel({
  title,
  column = PANEL,
  onClose,
  children,
}: {
  title: string;
  column?: Column;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const [width, setWidth] = useWidth(column);
  return (
    <>
      <Splitter
        column={column}
        width={width}
        onWidth={setWidth}
        from="right"
        className="hidden w-2 md:flex"
      />
      <aside
        aria-label={title}
        style={{ '--panel': `${width}px` } as CSSProperties}
        className="fixed inset-0 z-30 flex flex-col bg-panel md:static md:z-auto md:w-(--panel) md:max-w-[50%] md:shrink-0 md:overflow-hidden md:rounded-2xl md:bg-surface md:shadow-sm"
      >
        <div className="flex h-12 shrink-0 items-center gap-2 border-b border-line px-3">
          <h2 className="flex-1 font-semibold">{title}</h2>
          <button
            type="button"
            aria-label={t('frame.close')}
            onClick={onClose}
            className={iconButton}
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">{children}</div>
      </aside>
    </>
  );
}

export function Lobby({ children }: { children: ReactNode }) {
  const { language, setLanguage } = useI18n();
  return (
    <div className="flex min-h-dvh flex-col items-center gap-6 bg-surface px-4 py-12 text-ink">
      <h1>
        <Brand />
      </h1>
      {children}
      <div className="flex gap-1 text-sm">
        {LANGUAGES.map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => setLanguage(code)}
            aria-pressed={language === code}
            className="rounded px-2 py-1 uppercase text-muted aria-pressed:bg-selected aria-pressed:text-ink"
          >
            {code}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Loading() {
  const { t } = useI18n();
  return <p className="text-muted">{t('tree.loading')}</p>;
}

export function Loaded<T>({
  query,
  children,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) {
    return (
      <Frame>
        <Loading />
      </Frame>
    );
  }
  if (query.isError) {
    return (
      <Frame>
        <Failure error={query.error} />
      </Frame>
    );
  }
  return children(query.data);
}

/** A page is found by the id in its address; any other part that has gone stale is put right,
 * once the page shows what the address names (`href` null until then). */
export function Addressed({ href, children }: { href: string | null; children: ReactNode }) {
  const { pathname, search } = useLocation();
  // The page stays mounted while its address is put right: a rename seen live before its own
  // answer would otherwise mount the page anew and lose what its open dialog waits for.
  return (
    <>
      {children}
      {href !== null && pathname !== href && <Navigate to={`${href}${search}`} replace />}
    </>
  );
}

export function Missing() {
  const { pathname } = useLocation();
  return (
    <Frame>
      <Failure error={new ApiError(pathname, 404, undefined)} />
    </Frame>
  );
}

interface Chrome {
  searchable: boolean;
  /** Whether the page's own side column, a document's tabs and headings, has moved the folders
      of the documents into the drawer. A module's own panel, as Mail's, takes their place. */
  sided: boolean;
  /** Whether the drawer holds anything: the page's own side column or the folders of the documents. */
  drawn: boolean;
  here: Pick<TreeNode, 'id' | 'title'> | undefined;
}

interface Slots {
  crumbs: HTMLElement | null;
  actions: HTMLElement | null;
  side: HTMLElement | null;
  panel: HTMLElement | null;
  drawer: HTMLElement | null;
  report: (chrome: Chrome) => void;
}

const SlotsContext = createContext<Slots | null>(null);

function same(a: Chrome, b: Chrome): boolean {
  return (
    a.searchable === b.searchable &&
    a.sided === b.sided &&
    a.drawn === b.drawn &&
    a.here?.id === b.here?.id &&
    a.here?.title === b.here?.title
  );
}

/** The settings of the installation keep their addresses; the settings column lists them. */
export const INSTALLATION_PATHS = [
  '/users',
  '/resources',
  '/workdays',
  '/meetings',
  '/ai',
  '/providers',
  '/applications',
  '/retention',
  '/journal',
  '/health',
];

function moduleAt(pathname: string): Module | null {
  if (pathname === '/' || pathname === '/tasks') return 'today';
  if (pathname === '/calendar' || pathname.startsWith('/calendar/')) return 'calendar';
  if (pathname === '/mail' || pathname.startsWith('/mail/')) return 'mail';
  if (pathname === '/chat' || pathname.startsWith('/chat/')) return 'chat';
  if (pathname === '/contacts' || pathname.startsWith('/contacts/')) return 'chat';
  if (pathname === '/settings' || pathname.startsWith('/settings/')) return null;
  if (pathname === '/help' || pathname.startsWith('/help/')) return null;
  if (pathname === '/workspace') return null;
  return INSTALLATION_PATHS.includes(pathname) ? null : 'documents';
}

/** The module a place within it goes up to, as Contacts to Chat; none for a module's own pages. */
function upOf(pathname: string): Module | null {
  const within = PLACES.some(
    (place) =>
      !MODULES.some((module) => module.id === place.id) &&
      (pathname === place.to || pathname.startsWith(`${place.to}/`)),
  );
  return within ? moduleAt(pathname) : null;
}

const railItem =
  'flex min-h-14 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl text-[0.625rem] tracking-tight text-muted md:w-[76px] md:flex-none md:px-0.5 md:text-xs md:tracking-normal';

function RailItem({
  to,
  icon: Icon,
  label,
  current,
  count,
  className,
  onClick,
}: {
  to: string;
  icon: LucideIcon;
  label: string;
  current: boolean;
  count?: [number, MessageKey];
  className: string;
  onClick?: (event: MouseEvent) => void;
}) {
  const { t, formatNumber } = useI18n();
  return (
    <Link
      to={to}
      onClick={onClick}
      aria-current={current ? 'page' : undefined}
      className={`${railItem} ${className} hover:bg-hover hover:text-ink aria-[current=page]:bg-selected aria-[current=page]:font-semibold aria-[current=page]:text-ink`}
    >
      <span className="relative">
        <Icon size={20} aria-hidden />
        {count && count[0] > 0 && (
          <span
            aria-label={t(count[1])}
            className="absolute -right-2.5 -top-1.5 min-w-4 rounded-full bg-accent px-1 text-center text-[0.625rem] font-semibold leading-4 text-on-accent tabular-nums"
          >
            {formatNumber(count[0])}
          </span>
        )}
      </span>
      <span className="max-w-full truncate">{label}</span>
    </Link>
  );
}

/** What waits unread: new mail in the accounts' inboxes and the others' messages in the
    conversations, known once both have come. */
function useWaiting() {
  const accounts = useAccounts();
  const live = useLive();
  return {
    mail: accounts.data?.accounts.reduce((sum, account) => sum + account.unseen, 0) ?? 0,
    chat: live.conversations.reduce((sum, each) => sum + waitingIn(each), 0),
    known: Boolean(accounts.data) && live.at > 0,
  };
}

/** All that waits unread, counted on the installed app's icon; while the app is closed the
    service worker counts it from what is pushed. */
function useAppBadge() {
  const { mail, chat, known } = useWaiting();
  const total = mail + chat;
  useEffect(() => {
    if (!known || !('setAppBadge' in navigator)) return;
    void (total > 0 ? navigator.setAppBadge(total) : navigator.clearAppBadge());
  }, [known, total]);
}

/** The suite's modules: a column at the left, a bar of their groups along the bottom of a phone.
    A group leads back to the module of it last open. */
function Rail({ className }: { className: string }) {
  const { t } = useI18n();
  const { pathname } = useLocation();
  const here = moduleAt(pathname);
  const { mail, chat } = useWaiting();
  const owner = Boolean(useSession().data?.user?.workspace);
  const goToProjects = useGoToProjects();
  const counts: Partial<Record<Module, [number, MessageKey]>> = {
    mail: [mail, 'mail.unseen'],
    chat: [chat, 'chat.unread'],
  };
  return (
    <nav
      aria-label={t('rail.label')}
      className={`shrink-0 justify-around border-t border-line p-1 md:w-[84px] md:gap-1 md:flex-col md:items-center md:justify-start md:border-t-0 md:px-0 md:pt-0 md:pb-3 ${className}`}
    >
      <NavLink
        to="/"
        title={t('rail.today')}
        className="relative mb-3 hidden h-12 shrink-0 items-center justify-center self-stretch md:flex"
      >
        {/* The logo's mark is centred at 19.8 % of its width (x 390 of its 70–1686 view box), so
            it stands on the rail's axis. */}
        <span className="absolute left-1/2 w-max -translate-x-[19.8%]">
          <Brand compact />
        </span>
      </NavLink>
      {MODULES.map(({ id, icon, to }) => (
        <RailItem
          key={id}
          to={to}
          icon={icon}
          label={t(`rail.${id}`)}
          current={id === here}
          count={counts[id]}
          className="flex"
        />
      ))}
      {owner && (
        <RailItem
          to="/workspace"
          icon={FolderKanban}
          label={t('rail.projects')}
          current={pathname === '/workspace'}
          className="flex"
          onClick={(event) => {
            event.preventDefault();
            goToProjects();
          }}
        />
      )}
      <div className="mt-auto hidden flex-col items-center gap-2 md:flex">
        <NextUp />
      </div>
    </nav>
  );
}

/** The next meeting, in sight at the foot of the rail with its link (D17). */
function NextUp() {
  const { t, language, formatTime } = useI18n();
  const now = useNow();
  const today = dayOf(now);
  const shown = useWindow(today, today);
  const next = shown.data ? nextOf(shown.data.events, now) : undefined;
  if (!next) return null;
  const link = linkOf(next);
  const started = new Date(next.start).getTime() <= now.getTime();
  return (
    <div className="flex w-[76px] flex-col items-center gap-1 rounded-xl bg-raised p-2 text-center text-xs">
      <Link
        to={`/calendar/day/${today}`}
        title={next.summary}
        className="flex w-full flex-col items-center rounded hover:bg-hover"
      >
        <span className="text-muted">{t('today.next')}</span>
        <span className="font-semibold">{formatTime(new Date(next.start))}</span>
        <span className="w-full truncate text-muted">
          {started ? t('today.now') : untilText(language, next.start, now)}
        </span>
      </Link>
      {link && (
        <JoinLink link={link} compact className={`${primaryButton} w-full justify-center px-0`} />
      )}
    </div>
  );
}

/** The header, folder column and drawer every page shares. They stay mounted while pages come
    and go, so what is typed into the search box survives a page that is still loading. The page
    itself never scrolls, only the panes in it: an absolute element deep in a scrolled list, whose
    pane is not positioned, is placed against the shell and clipped there instead of lengthening
    the page. */
/** What only a member of the installation is watched for: the note's key and what waits unread. */
function Member() {
  useNoteShortcut();
  useAppBadge();
  return null;
}

export function Shell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const visitor = useVisitor();
  useHelpKey();
  useFollowed();
  useKeeper();
  const { key } = useLocation();
  const expansion = useState<Record<string, boolean>>({});
  const [drawerAt, setDrawerAt] = useState<string | null>(null);
  const [chrome, setChrome] = useState<Chrome>({
    searchable: true,
    sided: false,
    drawn: true,
    here: undefined,
  });
  const [crumbs, setCrumbs] = useState<HTMLElement | null>(null);
  const [actions, setActions] = useState<HTMLElement | null>(null);
  const [side, setSide] = useState<HTMLElement | null>(null);
  const [panel, setPanel] = useState<HTMLElement | null>(null);
  const [drawer, setDrawer] = useState<HTMLElement | null>(null);
  const [folders, setFolders, foldersStyle] = useWidth(FOLDERS);
  const report = useCallback(
    (next: Chrome) => setChrome((now) => (same(now, next) ? now : next)),
    [],
  );
  const slots = useMemo(
    () => ({ crumbs, actions, side, panel, drawer, report }),
    [crumbs, actions, side, panel, drawer, report],
  );

  return (
    <ExpansionContext value={expansion}>
      <PaletteProvider>
        <UploadProvider>
          {!visitor && <Launches />}
          {!visitor && <Member />}
          <SlotsContext value={slots}>
            <div
              onDragOver={refuseStrayFiles}
              className="relative flex h-dvh flex-col overflow-clip bg-panel text-ink md:flex-row"
            >
              {!visitor && (
                <Rail
                  className={`order-last md:order-first md:flex ${chrome.sided ? 'hidden' : 'flex'}`}
                />
              )}
              <div
                style={foldersStyle}
                className="hidden w-(--folders) max-w-[30%] shrink-0 flex-col md:flex"
              >
                <div className="h-12 shrink-0" />
                <div ref={setSide} className="min-h-0 flex-1 overflow-y-auto px-2 pt-4 pb-2" />
                <div className="shrink-0 px-4 pb-3">
                  <Signature />
                </div>
              </div>
              <Splitter
                column={FOLDERS}
                width={folders}
                onWidth={setFolders}
                className={`hidden md:flex ${SIDE_SEPARATOR}`}
              />
              <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                <header className="relative flex h-12 shrink-0 items-center gap-2 border-b border-line px-2 md:border-b-0">
                  <NavLink to="/" title={t('rail.today')} className="shrink-0 rounded-lg md:hidden">
                    <BrandIcon />
                  </NavLink>
                  {chrome.drawn && (
                    <button
                      type="button"
                      aria-label={t('frame.folders')}
                      onClick={() => setDrawerAt(key)}
                      className={`${iconButton} ${chrome.sided ? '' : 'md:hidden'}`}
                    >
                      <MenuIcon size={18} />
                    </button>
                  )}
                  <div ref={setCrumbs} className="min-w-0 flex-1" />
                  <div ref={setActions} className="flex shrink-0 items-center gap-2 empty:hidden" />
                  {chrome.searchable && !visitor && <SearchBox here={chrome.here} />}
                  {!visitor && <VoiceButton />}
                  <HelpButton />
                  <UserMenu />
                </header>
                <div className="flex min-h-0 flex-1 md:pr-2 md:pb-2">
                  <main className="min-w-0 flex-1 overflow-y-auto bg-surface p-4 md:rounded-2xl md:shadow-sm">
                    {children}
                  </main>
                  <div ref={setPanel} className="contents" />
                </div>
              </div>
              <Drawer open={drawerAt === key} onClose={() => setDrawerAt(null)}>
                <div ref={setDrawer} className="contents" />
              </Drawer>
            </div>
          </SlotsContext>
        </UploadProvider>
      </PaletteProvider>
    </ExpansionContext>
  );
}

/** The one button a page leads with, at the right of its header beside the account on every
    page: what the page makes. Its label stays for a screen reader on a phone. */
export function PrimaryAction({
  icon: Icon,
  label,
  onClick,
  disabled,
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} className={primaryButton}>
      <Icon size={16} aria-hidden />
      <span className="sr-only sm:not-sr-only">{label}</span>
    </button>
  );
}

/** A page's part of the shell: its title or path, actions, side column and panel. The header
    reads the same on every page: the page's other buttons, then its primary action, then its
    menu of the rest, then the account. */
export function Frame({
  path,
  root,
  after,
  menu,
  title,
  actions,
  primary,
  more,
  side,
  panel,
  searchable = true,
  folders = true,
  children,
}: {
  path?: TreeNode[];
  root?: Root;
  after?: { title: string; href?: string }[];
  menu?: ReactNode;
  title?: string;
  actions?: ReactNode;
  primary?: ReactNode;
  /** The items of the page's menu of further actions. */
  more?: ReactNode;
  side?: ReactNode;
  panel?: ReactNode;
  searchable?: boolean;
  /** Whether the folders of the documents are at hand: in the side column, or the drawer. */
  folders?: boolean;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const slots = useContext(SlotsContext)!;
  const { report } = slots;
  const up = upOf(useLocation().pathname);
  const wide = useWide();
  const sided = Boolean(side) && folders;
  const drawn = Boolean(side) || folders;
  const here = path?.findLast((node) => node.kind === 'folder');
  useLayoutEffect(
    () => report({ searchable, sided, drawn, here }),
    [report, searchable, sided, drawn, here],
  );
  const name = title ?? path?.at(-1)?.title;
  useTitle(name);

  const move = useMove();
  const moveTo: MoveTo = (parent) => (ids) => move.mutate({ ids, parent });
  const tree = folders && <FolderTree path={path ?? []} moveTo={moveTo} moving={move.error} />;
  const into = (slot: HTMLElement | null, content: ReactNode) =>
    slot && createPortal(content, slot);
  return (
    <>
      {into(
        slots.crumbs,
        title ? (
          <div className="-m-1 flex min-w-0 items-center gap-1 overflow-hidden p-1 whitespace-nowrap">
            {up && (
              <>
                <Link
                  to={MODULES.find((module) => module.id === up)!.to}
                  title={t(`rail.${up}`)}
                  className="hidden min-w-10 shrink-100 truncate text-muted hover:text-ink sm:inline"
                >
                  {t(`rail.${up}`)}
                </Link>
                <ChevronRight
                  size={14}
                  aria-hidden
                  className="hidden shrink-0 text-muted sm:block"
                />
              </>
            )}
            <h1 className="truncate font-semibold">{title}</h1>
          </div>
        ) : (
          path && (
            <Breadcrumbs
              compact
              alone={wide && folders && !side}
              path={path}
              root={root}
              after={after}
              menu={menu}
              moveTo={moveTo}
            />
          )
        ),
      )}
      {into(
        slots.actions,
        <>
          {actions}
          {primary}
          {more && <ActionsMenu>{more}</ActionsMenu>}
        </>,
      )}
      {into(slots.side, side ?? tree)}
      {into(slots.panel, panel)}
      {into(
        slots.drawer,
        <>
          {side && (
            <div className={`md:hidden ${tree ? 'border-b border-line pb-2' : ''}`}>{side}</div>
          )}
          {tree}
        </>,
      )}
      {children}
    </>
  );
}
