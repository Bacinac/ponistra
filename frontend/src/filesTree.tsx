import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bookmark,
  Building2,
  Computer,
  Folder,
  FolderKanban,
  FolderOpen,
  LayoutDashboard,
  type LucideIcon,
  Network,
  Share2,
  Star,
  Trash2,
  Users,
} from 'lucide-react';
import { useMemo, type ReactNode } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { deleteJson, getJson } from './api';
import { useSession, useVisitor } from './auth';
import { hiddenName, listKey, type FileSource } from './files';
import { guestIcon, guestKey, guestsFailure, guestSource, useGuests } from './filesGuests';
import { TreeRow, type Rows, type TreeSource } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { locationSource } from './locations';
import { filesHref, LOCATION_ICONS, useLocations } from './locationsData';
import { ContextMenuArea, MenuItem } from './menu';
import { ponistraSource, rootKey, ROOTS, type Root } from './ponistraFiles';
import { workspaceSource } from './workspaceFiles';

export const BOOKMARKS = ['bookmarks'];

export interface Kept {
  id: number;
  source: string;
  path: string;
  name: string;
}

export const ROOT_LOOKS: Record<Root, { icon: LucideIcon; label: MessageKey }> = {
  mine: { icon: FolderOpen, label: 'tree.root' },
  company: { icon: Building2, label: 'tree.company' },
  shared: { icon: Users, label: 'tree.shared' },
  sharing: { icon: Share2, label: 'tree.sharedByMe' },
  favourites: { icon: Star, label: 'favourites.title' },
  boards: { icon: LayoutDashboard, label: 'boards.title' },
};

export interface Project {
  name: string | null;
  path: string;
}

/** The projects of the code workspace, for its owner alone. */
export function useProjects(enabled: boolean) {
  return useQuery({
    queryKey: ['workspace', 'projects', 'folders'],
    queryFn: () =>
      getJson<{ projects: Project[] }>('/api/workspace/projects').then(({ projects }) =>
        projects.map(({ name, path }) => ({ name, path })),
      ),
    enabled,
    staleTime: 60_000,
  });
}

export const projectName = (project: Project) =>
  project.name ?? project.path.split('/').pop() ?? '';

/** Every source the user reaches, by key: Ponistra's own places, the network's locations, the
 * guests of the machines they manage and, for its owner, the workspace's projects. */
export function useSources() {
  const { t } = useI18n();
  const owner = Boolean(useSession().data?.user?.workspace);
  const visitor = useVisitor();
  const locations = useLocations({ enabled: !visitor });
  const guests = useGuests({ enabled: !visitor });
  const projects = useProjects(owner);
  const sources = useMemo(() => {
    const all = new Map<string, FileSource>();
    for (const root of ROOTS)
      all.set(rootKey(root), ponistraSource(root, t(ROOT_LOOKS[root].label), t));
    for (const location of locations.data?.locations ?? []) {
      const source = locationSource(location);
      all.set(source.key, source);
    }
    for (const computer of guests.data ?? [])
      for (const guest of computer.guests) {
        const source = guestSource(computer, guest);
        all.set(source.key, source);
      }
    for (const project of projects.data ?? []) {
      const source = workspaceSource(project.path, projectName(project));
      all.set(source.key, source);
    }
    return all;
  }, [t, locations.data, guests.data, projects.data]);
  return {
    sources,
    owner,
    locations,
    guests,
    projects,
    pending:
      (!visitor && (locations.isPending || guests.isPending)) || (owner && projects.isPending),
  };
}

/** A row of the column of Files: a group of sources, a machine of the user's, a source's top, or a
 * folder of it. */
interface Place {
  key: string;
  group?: 'network' | 'computers' | 'computer' | 'workspace' | 'bookmarks';
  computer?: string;
  source?: string;
  path: string;
  name: string;
  icon: LucideIcon;
  href: string;
  bookmark?: number;
}

const placeKey = (source: string, path: string) => (path ? `${source}/${path}` : source);

export function useBookmarks() {
  return useQuery({
    queryKey: BOOKMARKS,
    queryFn: () => getJson<{ bookmarks: Kept[] }>('/api/files/bookmarks'),
  });
}

function usePlaceRows(
  sources: Map<string, FileSource>,
  locations: ReturnType<typeof useLocations>,
  guests: ReturnType<typeof useGuests>,
  projects: ReturnType<typeof useProjects>,
) {
  return function useRows(row: Place, enabled: boolean): Rows<Place> {
    const source = row.source ? sources.get(row.source) : undefined;
    const bookmarks = useBookmarks();
    const listing = useQuery({
      queryKey: source ? listKey(source, row.path) : ['files', 'none'],
      queryFn: () => source!.list(row.path),
      enabled: enabled && Boolean(source) && row.bookmark === undefined,
    });
    if (row.group === 'network')
      return {
        rows: locations.data?.locations.map((location) => ({
          key: `location:${location.id}`,
          source: `location:${location.id}`,
          path: '',
          name: location.name,
          icon: LOCATION_ICONS[location.kind],
          href: filesHref(`location:${location.id}`),
        })),
        error: locations.error,
      };
    if (row.group === 'computers')
      return {
        rows: guests.data?.map((computer) => ({
          key: `computers:${computer.id}`,
          group: 'computer' as const,
          computer: computer.id,
          path: '',
          name: computer.name,
          icon: Computer,
          href: '/files',
        })),
        error: guests.error,
      };
    if (row.group === 'computer') {
      const computer = guests.data?.find((each) => each.id === row.computer);
      const failure = computer && guestsFailure(computer);
      return {
        rows: failure
          ? undefined
          : computer?.guests.map((guest) => ({
              key: guestKey(computer.id, guest.name),
              source: guestKey(computer.id, guest.name),
              path: '',
              name: guest.name,
              icon: guestIcon(guest),
              href: filesHref(guestKey(computer.id, guest.name)),
            })),
        error: failure ?? guests.error,
      };
    }
    if (row.group === 'workspace')
      return {
        rows: projects.data?.map((project) => ({
          key: `workspace:${project.path}`,
          source: `workspace:${project.path}`,
          path: '',
          name: projectName(project),
          icon: FolderKanban,
          href: filesHref(`workspace:${project.path}`),
        })),
        error: projects.error,
      };
    if (row.group === 'bookmarks')
      return {
        rows: bookmarks.data?.bookmarks.map((kept) => ({
          key: `bookmark:${kept.id}`,
          source: kept.source,
          path: kept.path,
          name: kept.name,
          icon: Bookmark,
          href: filesHref(kept.source, kept.path),
          bookmark: kept.id,
        })),
        error: bookmarks.error,
      };
    if (row.bookmark !== undefined) return { rows: [], error: null };
    return {
      rows: listing.data?.entries
        .filter((entry) => entry.kind === 'folder' && !hiddenName(entry))
        .map((entry) => {
          const path = row.path ? `${row.path}/${entry.name}` : entry.name;
          return {
            key: placeKey(row.source!, path),
            source: row.source,
            path,
            name: entry.label ?? entry.name,
            icon: Folder,
            href: filesHref(row.source!, path),
          };
        }),
      error: listing.error,
    };
  };
}

function BookmarkMenu({ row, children }: { row: Place; along: Set<string>; children: ReactNode }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: (id: number) => deleteJson(`/api/files/bookmarks/${id}`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: BOOKMARKS }),
  });
  if (row.bookmark === undefined) return children;
  return (
    <ContextMenuArea
      items={
        <MenuItem
          icon={Trash2}
          label={t('files.unbookmark')}
          onSelect={() => remove.mutate(row.bookmark!)}
        />
      }
    >
      {children}
    </ContextMenuArea>
  );
}

/** What the side column holds beyond Ponistra's own places: the bookmarks, the network, the
 * machines the user manages and, for its owner, the workspace, each a tree of its folders. */
export function FilesGroups() {
  const { t } = useI18n();
  const { sources, owner, locations, guests, projects } = useSources();
  const { source: at } = useParams();
  const [params] = useSearchParams();
  const useRows = usePlaceRows(sources, locations, guests, projects);
  const along = useMemo(() => {
    const open = new Set<string>();
    if (!at) return open;
    open.add(at);
    if (at.startsWith('location:')) open.add('network');
    if (at.startsWith('computer:'))
      open.add('computers').add(`computers:${at.slice('computer:'.length).split('/')[0]}`);
    if (at.startsWith('workspace:')) open.add('workspace');
    const parts = (params.get('path') ?? '').split('/').filter(Boolean);
    parts.forEach((_, index) => open.add(placeKey(at, parts.slice(0, index + 1).join('/'))));
    return open;
  }, [at, params]);
  const here = at ? placeKey(at, params.get('path') ?? '') : null;
  const tree: TreeSource<Place> = {
    along,
    useRows,
    key: (row) => row.key,
    href: (row) => row.href,
    label: (row) => row.name,
    icon: (row) => row.icon,
    current: (row) =>
      row.bookmark === undefined && !row.group && here === placeKey(row.source!, row.path),
    Menu: BookmarkMenu,
  };
  const groups: Place[] = [
    {
      key: 'bookmarks',
      group: 'bookmarks',
      path: '',
      name: t('files.bookmarks'),
      icon: Bookmark,
      href: '/files',
    },
    {
      key: 'network',
      group: 'network' as const,
      path: '',
      name: t('locations.title'),
      icon: Network,
      href: '/files',
    },
    ...(guests.data?.length
      ? [
          {
            key: 'computers',
            group: 'computers' as const,
            path: '',
            name: t('files.computers'),
            icon: Computer,
            href: '/files',
          },
        ]
      : []),
    ...(owner
      ? [
          {
            key: 'workspace',
            group: 'workspace' as const,
            path: '',
            name: t('files.workspace'),
            icon: FolderKanban,
            href: '/files',
          },
        ]
      : []),
  ];
  return groups.map((row) => <TreeRow key={row.key} source={tree} row={row} depth={0} />);
}
