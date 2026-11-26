import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Bookmark,
  Columns2,
  EyeOff,
  Eye,
  FolderKanban,
  LayoutGrid,
  List,
  type LucideIcon,
  Plus,
  X,
} from 'lucide-react';
import { Fragment, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from 'react-router';
import { postJson } from './api';
import { Cancel, Modal } from './dialogs';
import { DeskContext, FileBrowser, type Clip, type Desk, type FileSource } from './files';
import { Addressed, Frame, Loading, Missing } from './frame';
import { BOOKMARKS, projectName, ROOT_LOOKS, useBookmarks, useSources } from './filesTree';
import { guestIcon, guestKey } from './filesGuests';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { filesHref, LOCATION_ICONS } from './locationsData';
import { rootKey, ROOTS, type Root } from './ponistraFiles';
import { button, iconButton, primaryButton } from './styles';
import { conflictsOf, startTransfer, Transfers, type Conflict } from './transfers';
import {
  errorMessage,
  groupHref,
  nodeHref,
  useNode,
  type Root as TreeRoot,
  type TreeNode,
} from './tree';
import { idIn } from './address';

/** A folder shown in a pane: the source it lies in, by key, and its path there. */
interface Pane {
  source: string;
  path: string;
}

interface Tab {
  panes: Pane[];
  focus: number;
}

interface Tabs {
  tabs: Tab[];
  current: number;
}

const TABS = 'ponistra.files.tabs';
const LOOK = 'ponistra.files.look';

function stored<T>(key: string, fallback: T): T {
  try {
    const kept = localStorage.getItem(key);
    return kept ? (JSON.parse(kept) as T) : fallback;
  } catch {
    return fallback;
  }
}

function store(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // A browser that keeps nothing opens Files with one tab, as a new one does.
  }
}

/** Files with no folder open: every source as a tile, the bookmarks first. */
function Overview({ sources, locations, guests, projects, owner }: ReturnType<typeof useSources>) {
  const { t } = useI18n();
  const bookmarks = useBookmarks();
  const tile = `${button} min-w-0 justify-start`;
  const section = (title: string, items: { href: string; icon: LucideIcon; name: string }[]) =>
    items.length > 0 && (
      <section className="flex flex-col gap-2">
        <h2 className="text-sm text-muted">{title}</h2>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(12rem,1fr))] gap-2">
          {items.map(({ href, icon: Icon, name }) => (
            <Link key={href} to={href} className={tile}>
              <Icon size={18} aria-hidden className="shrink-0 text-muted" />
              <span className="truncate">{name}</span>
            </Link>
          ))}
        </div>
      </section>
    );
  return (
    <div className="flex w-full max-w-5xl flex-col gap-6">
      {section(
        t('files.bookmarks'),
        (bookmarks.data?.bookmarks ?? []).map((kept) => ({
          href: filesHref(kept.source, kept.path),
          icon: Bookmark,
          name: kept.name,
        })),
      )}
      {section(
        t('rail.documents'),
        ROOTS.filter((root) => root !== 'sharing').map((root) => ({
          href: filesHref(rootKey(root)),
          icon: ROOT_LOOKS[root].icon,
          name: sources.get(rootKey(root))!.name,
        })),
      )}
      {locations.isError ? (
        <p className="text-sm text-danger">{errorMessage(locations.error, t)}</p>
      ) : (locations.data?.locations.length ?? 1) === 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm text-muted">{t('locations.title')}</h2>
          <p className="text-muted">
            {t('locations.none')}{' '}
            <Link to="/settings/locations" className="underline">
              {t('locations.settings')}
            </Link>
          </p>
        </section>
      ) : (
        section(
          t('locations.title'),
          (locations.data?.locations ?? []).map((location) => ({
            href: filesHref(`location:${location.id}`),
            icon: LOCATION_ICONS[location.kind],
            name: location.name,
          })),
        )
      )}
      {section(
        t('files.computers'),
        (guests.data ?? []).flatMap((computer) =>
          computer.guests.map((guest) => ({
            href: filesHref(guestKey(computer.id, guest.name)),
            icon: guestIcon(guest),
            name: `${computer.name} / ${guest.name}`,
          })),
        ),
      )}
      {owner &&
        section(
          t('files.workspace'),
          (projects.data ?? []).map((project) => ({
            href: filesHref(`workspace:${project.path}`),
            icon: FolderKanban,
            name: projectName(project),
          })),
        )}
    </div>
  );
}

const CONFLICTS: { value: Conflict; label: MessageKey }[] = [
  { value: 'skip', label: 'files.conflict.skip' },
  { value: 'replace', label: 'files.conflict.replace' },
  { value: 'keep', label: 'files.conflict.keep' },
];

interface Asked {
  names: string[];
  go: (conflict: Conflict) => void;
}

/** What to do with the names a copy or a move finds already in the folder it goes into, asked
 * once for all it carries. */
function ConflictDialog({ asked, onClose }: { asked: Asked; onClose: () => void }) {
  const { t, formatNumber } = useI18n();
  const shown = asked.names.slice(0, 8);
  return (
    <Modal heading={t('files.conflict')} onClose={onClose}>
      <p className="text-sm">{`${t('files.conflictBody')} ${formatNumber(asked.names.length)}`}</p>
      <ul className="flex flex-col text-sm text-muted">
        {shown.map((name) => (
          <li key={name} className="truncate">
            {name}
          </li>
        ))}
        {asked.names.length > shown.length && <li>…</li>}
      </ul>
      <div className="flex flex-wrap justify-end gap-2">
        <Cancel />
        {CONFLICTS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            onClick={() => {
              onClose();
              asked.go(value);
            }}
            className={value === 'keep' ? primaryButton : button}
          >
            {t(label)}
          </button>
        ))}
      </div>
    </Modal>
  );
}

/** Files (D55): every source the user reaches in one tree, its folders in one or two panes and
 * in tabs, entries copied, cut, pasted and dragged within a source and between any two. */
/** The places of Ponistra's own tree by the addresses they keep. */
const PLACES: Record<string, Root> = {
  '/documents': 'mine',
  '/company': 'company',
  '/shared': 'shared',
  '/favourites': 'favourites',
  '/boards': 'boards',
};

/** The page that shows a folder of a place of its own, the notes, the links or the boards; null
 * for a folder Files shows. */
function placePage(folder: TreeNode): string | null {
  if (folder.notes) return '/notes';
  if (folder.links) return '/links';
  if (folder.boards) return '/boards';
  return null;
}

/** The folder the address names: a source and a path of it, a folder of Ponistra's tree by its
 * own address, read from where it lies; where the address is not yet the folder's own, the one
 * it is put right to. While a folder is read, the one before it stays. */
function useHere(): {
  here: Pane | null;
  pending: boolean;
  missing: boolean;
  href: string | null;
  /** Where in Ponistra's tree the folder lies, for the column and the crumbs. */
  trail: { path: TreeNode[]; root?: TreeRoot; title?: MessageKey } | null;
} {
  const { source: at, folder, group } = useParams();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const queryClient = useQueryClient();
  const id = folder !== undefined ? idIn(folder) : group !== undefined ? idIn(group) : null;
  const placement = useNode(id);
  const before = useRef<Pane | null>(null);
  const read = id !== null ? placement.data : undefined;
  const boarded = read?.path[0]?.boards ?? false;
  const steps = read ? [...(boarded ? read.path.slice(1) : read.path), read.node] : [];
  const chain = steps.map((step) => step.id).join('/');
  const titles = steps.map((step) => step.title);
  const readSource = read ? rootKey(boarded ? 'boards' : read.root) : null;
  useEffect(() => {
    if (readSource) queryClient.setQueryData(['files', readSource, 'labels', chain], titles);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the titles follow the chain read
  }, [queryClient, readSource, chain]);
  const found = ((): { here: Pane | null; href: string | null } => {
    if (at) return { here: { source: at, path: params.get('path') ?? '' }, href: null };
    const place = PLACES[pathname];
    if (place)
      return {
        here: {
          source: rootKey(place === 'shared' && params.get('by') === 'me' ? 'sharing' : place),
          path: '',
        },
        href: null,
      };
    if (!read) return { here: null, href: null };
    const own = placePage(read.node);
    if (own) return { here: null, href: own };
    return {
      here: { source: readSource!, path: chain },
      href: boarded ? groupHref(read.node) : nodeHref(read.node),
    };
  })();
  if (found.here) before.current = found.here;
  const pending = id !== null && placement.isPending;
  const place = PLACES[pathname];
  const trail =
    place === 'favourites' || place === 'boards'
      ? { path: [], title: ROOT_LOOKS[place].label }
      : place
        ? { path: [], root: place as TreeRoot }
        : read && !boarded
          ? { path: [...read.path, read.node], root: read.root }
          : read
            ? { path: [], title: ROOT_LOOKS.boards.label }
            : null;
  return {
    trail,
    here: found.here ?? (pending ? before.current : null),
    pending,
    missing: id === null ? folder !== undefined || group !== undefined : placement.isError,
    href: found.href,
  };
}

export function FilesPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const known = useSources();
  const { sources } = known;
  const placed = useHere();
  const [tabs, setTabs] = useState<Tabs>(() => stored(TABS, { tabs: [], current: 0 }));
  const [look, setLook] = useState(() => stored(LOOK, { view: 'list', hidden: false }));
  const [clip, setClip] = useState<Clip | null>(null);
  const [asked, setAsked] = useState<Asked | null>(null);
  const [panelAt, setPanelAt] = useState<HTMLElement | null>(null);
  const [failure, setFailure] = useState<Error | null>(null);
  const [dirty, setDirty] = useState(false);
  const { here } = placed;
  const file = params.get('file');

  const tab: Tab | undefined = tabs.tabs[tabs.current];
  useEffect(() => {
    if (!here) return;
    setTabs((now) => {
      const open = now.tabs[now.current];
      if (!open) return { tabs: [{ panes: [here], focus: 0 }], current: 0 };
      const was = open.panes[open.focus];
      if (was?.source === here.source && was.path === here.path) return now;
      const panes = open.panes.map((pane, index) => (index === open.focus ? here : pane));
      return {
        ...now,
        tabs: now.tabs.map((each, index) => (index === now.current ? { ...open, panes } : each)),
      };
    });
  }, [here?.source, here?.path]);
  useEffect(() => store(TABS, tabs), [tabs]);
  useEffect(() => store(LOOK, look), [look]);

  const goTo = (pane: Pane, replace = false) =>
    void navigate(filesHref(pane.source, pane.path), { replace });
  const moved = (index: number, path: string, opened?: string) => {
    if (!tab) return;
    if (index === tab.focus) {
      void navigate(filesHref(tab.panes[index].source, path, opened));
      return;
    }
    setTabs((now) => ({
      ...now,
      tabs: now.tabs.map((each, number) =>
        number === now.current
          ? {
              ...each,
              panes: each.panes.map((pane, place) => (place === index ? { ...pane, path } : pane)),
            }
          : each,
      ),
    }));
  };
  const focus = (index: number) => {
    if (!tab || index === tab.focus || dirty) return;
    setTabs((now) => ({
      ...now,
      tabs: now.tabs.map((each, number) =>
        number === now.current ? { ...each, focus: index } : each,
      ),
    }));
    goTo(tab.panes[index], true);
  };
  const split = () => {
    if (!tab || !here) return;
    setTabs((now) => ({
      ...now,
      tabs: now.tabs.map((each, number) =>
        number !== now.current
          ? each
          : each.panes.length > 1
            ? { panes: [each.panes[each.focus]], focus: 0 }
            : { panes: [each.panes[0], { ...here }], focus: 0 },
      ),
    }));
  };
  const openTab = () => {
    if (!here) return;
    setTabs((now) => ({
      tabs: [...now.tabs, { panes: [{ ...here }], focus: 0 }],
      current: now.tabs.length,
    }));
  };
  const showTab = (index: number) => {
    const shown = tabs.tabs[index];
    setTabs((now) => ({ ...now, current: index }));
    goTo(shown.panes[shown.focus]);
  };
  const closeTab = (index: number) => {
    const left = tabs.tabs.filter((_, number) => number !== index);
    const current = Math.min(
      index === tabs.current ? index : tabs.current - Number(index < tabs.current),
      left.length - 1,
    );
    setTabs({ tabs: left, current: Math.max(current, 0) });
    if (index === tabs.current) {
      const next = left[current];
      if (next) goTo(next.panes[next.focus]);
      else void navigate('/files');
    }
  };

  const renaming = useMutation({
    mutationFn: async ({
      from,
      paths,
      folder,
    }: {
      from: FileSource;
      to: FileSource;
      paths: string[];
      folder: string;
    }) => {
      for (const path of paths)
        await from.rename(path, `${folder ? `${folder}/` : ''}${path.split('/').pop()}`);
    },
    onSettled: (_, __, { from, to }) =>
      Promise.all(
        [from.key, to.key].map((key) =>
          queryClient.invalidateQueries({ queryKey: ['files', key] }),
        ),
      ),
    onError: setFailure,
  });
  const desk: Desk = {
    view: look.view === 'grid' ? 'grid' : 'list',
    hidden: look.hidden,
    clip,
    setClip,
    sourceOf: (key) => sources.get(key),
    put: (from, paths, to, folder, move) => {
      setFailure(null);
      const parent = (path: string) => path.replace(/\/?[^/]*$/, '');
      if (paths.every((path) => parent(path) === folder) && from.key === to.key) return;
      const tree = (source: FileSource) => source.key.split(':')[0];
      const together =
        from.key === to.key || (tree(from) === 'ponistra' && tree(to) === 'ponistra');
      if (move && together) {
        renaming.mutate({ from, to, paths, folder });
        return;
      }
      const go = (conflict: Conflict | null) =>
        startTransfer({ from, paths, to, path: folder, move, conflict }).catch(setFailure);
      conflictsOf(from, paths, to, folder)
        .then((names) => (names.length ? setAsked({ names, go }) : go(null)))
        .catch(setFailure);
    },
    bookmark: (source, path) => {
      const name = path
        ? (queryClient.getQueryData<string[]>(['files', source.key, 'labels', path])?.at(-1) ??
          path.split('/').pop()!)
        : source.name;
      postJson('/api/files/bookmarks', { source: source.key, path, name })
        .then(() => queryClient.invalidateQueries({ queryKey: BOOKMARKS }))
        .catch(setFailure);
    },
  };

  const looks = (
    <>
      <button
        type="button"
        aria-pressed={look.view === 'grid'}
        aria-label={t(look.view === 'grid' ? 'files.list' : 'files.grid')}
        title={t(look.view === 'grid' ? 'files.list' : 'files.grid')}
        onClick={() => setLook({ ...look, view: look.view === 'grid' ? 'list' : 'grid' })}
        className={iconButton}
      >
        {look.view === 'grid' ? (
          <List size={16} aria-hidden />
        ) : (
          <LayoutGrid size={16} aria-hidden />
        )}
      </button>
      <button
        type="button"
        aria-pressed={look.hidden}
        aria-label={t('files.hidden')}
        title={t('files.hidden')}
        onClick={() => setLook({ ...look, hidden: !look.hidden })}
        className={`${iconButton} aria-pressed:bg-selected`}
      >
        {look.hidden ? <Eye size={16} aria-hidden /> : <EyeOff size={16} aria-hidden />}
      </button>
    </>
  );
  if (placed.missing) return <Missing />;
  if (!here && placed.href) return <Navigate to={placed.href} replace />;
  if (!here && placed.pending)
    return (
      <Frame title={t('rail.files')}>
        <Loading />
      </Frame>
    );
  if (!here)
    return (
      <Frame title={t('rail.files')} actions={looks}>
        <Overview {...known} />
      </Frame>
    );
  const shown = tab ?? { panes: [here], focus: 0 };
  const panes = shown.panes.map((pane, index) => (index === shown.focus ? here : pane));
  const missing = panes.some((pane) => !sources.get(pane.source));
  if (missing && known.pending)
    return (
      <Frame title={t('rail.files')}>
        <Loading />
      </Frame>
    );
  const twin = panes.length > 1;
  return (
    <DeskContext.Provider value={desk}>
      <Addressed href={placed.href}>
        <Frame
          title={placed.trail ? placed.trail.title && t(placed.trail.title) : t('rail.files')}
          path={placed.trail?.path}
          root={placed.trail?.root}
          actions={
            <>
              {looks}
              <button
                type="button"
                aria-pressed={twin}
                aria-label={t('files.twin')}
                title={t('files.twin')}
                onClick={split}
                className={`${iconButton} hidden aria-pressed:bg-selected md:inline-flex`}
              >
                <Columns2 size={16} aria-hidden />
              </button>
            </>
          }
          panel={<div ref={setPanelAt} className="contents" />}
        >
          <div className="flex h-full min-h-0 flex-col gap-2">
            {tabs.tabs.length > 1 || tab ? (
              <div
                role="group"
                aria-label={t('files.tabs')}
                className="flex min-w-0 items-center gap-1 overflow-x-auto"
              >
                {tabs.tabs.map((each, index) => {
                  const pane = each.panes[each.focus];
                  const source = sources.get(pane.source);
                  const name = pane.path
                    ? (queryClient
                        .getQueryData<string[]>(['files', pane.source, 'labels', pane.path])
                        ?.at(-1) ?? pane.path.split('/').pop())
                    : source?.name;
                  return (
                    <div
                      key={index}
                      className={`flex max-w-56 min-w-0 shrink-0 items-center rounded-lg text-sm ${index === tabs.current ? 'bg-selected' : ''}`}
                    >
                      <button
                        type="button"
                        aria-current={index === tabs.current || undefined}
                        onClick={() => showTab(index)}
                        className="min-w-0 truncate px-2 py-1"
                      >
                        {name ?? pane.source}
                      </button>
                      {tabs.tabs.length > 1 && (
                        <button
                          type="button"
                          aria-label={t('files.closeTab')}
                          onClick={() => closeTab(index)}
                          className={iconButton}
                        >
                          <X size={14} aria-hidden />
                        </button>
                      )}
                    </div>
                  );
                })}
                <button
                  type="button"
                  aria-label={t('files.newTab')}
                  title={t('files.newTab')}
                  onClick={openTab}
                  className={iconButton}
                >
                  <Plus size={16} aria-hidden />
                </button>
              </div>
            ) : null}
            <div className="flex min-h-0 flex-1 gap-3">
              {panes.map((pane, index) => {
                const source = sources.get(pane.source);
                const focused = index === shown.focus;
                return (
                  <section
                    key={`${index}:${pane.source}`}
                    aria-label={source?.name ?? pane.source}
                    className={`flex min-h-0 min-w-0 flex-1 flex-col gap-2 ${twin ? `rounded-lg border p-2 ${focused ? 'border-focus' : 'border-line'}` : ''}`}
                  >
                    {!source ? (
                      <p className="text-sm text-danger">{t('error.not_found')}</p>
                    ) : (
                      <FileBrowser
                        key={pane.source}
                        source={source}
                        path={pane.path}
                        file={focused ? file : null}
                        onGo={(path, opened) => moved(index, path, opened)}
                        onFocus={() => focus(index)}
                        onDirty={focused ? setDirty : undefined}
                        frame={({ actions, primary, panel, children }) => (
                          <>
                            <div className="flex items-center justify-end gap-2">
                              {actions}
                              {primary}
                            </div>
                            <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
                            {focused && panelAt && panel && createPortal(panel, panelAt)}
                          </>
                        )}
                      />
                    )}
                  </section>
                );
              })}
            </div>
            {failure && (
              <p role="alert" className="text-sm text-danger">
                {errorMessage(failure, t)}
              </p>
            )}
            <Transfers />
          </div>
          {asked && <ConflictDialog asked={asked} onClose={() => setAsked(null)} />}
          {[...new Set(panes.map((pane) => pane.source))].map((key) => (
            <Fragment key={key}>{sources.get(key)?.host}</Fragment>
          ))}
        </Frame>
      </Addressed>
    </DeskContext.Provider>
  );
}
