import { useQueryClient } from '@tanstack/react-query';
import {
  Combine,
  Copy,
  FileText,
  Globe,
  LayoutDashboard,
  Lock,
  Pencil,
  ScanLine,
  Share2,
  Star,
  TableProperties,
  Trash2,
} from 'lucide-react';
import { lazy, Suspense, useEffect, useState, useSyncExternalStore, type DragEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { AccessPanel, Audience } from './access';
import { getJson, patchJson, postJson, upload } from './api';
import { useVisitor } from './auth';
import { CopyDialog, LinkDialog, MoveDialog, NameDialog } from './dialogs';
import { startDrag } from './drag';
import { useAi } from './editor/runs';
import { FavouriteItem, useFavouriteMarks } from './favourites';
import type { FileEntry, FileSource, Listed, SavedFile } from './files';
import { PhonePlaces, useWide } from './frame';
import { GatherDialog, useFollowedRun, type Gathering } from './gather';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { formatSize } from './explorer';
import { EDITABLE } from './image/edits';
import { lazily } from './lazily';
import { filesHref, PONISTRA_HREFS } from './locationsData';
import { useReachable } from './live';
import { MenuItem, MenuSeparator } from './menu';
import { KeepItem } from './offline';
import { PreviewPanel } from './preview';
import { button, iconButton } from './styles';
import {
  errorMessage,
  boardGroups,
  covers,
  kindOf,
  nodeHref,
  NodeIcon,
  placeText,
  type FoundNode,
  type ListedNode,
  type Placement,
  type Role,
  type TreeNode,
} from './tree';
import { placed, savedName, useUploads } from './upload';

const JoinDialog = lazy(() => import('./pdf/Join'));
const ScanDialog = lazily(() => import('./scan'), 'ScanDialog');

/** The places of Ponistra's own tree Files shows: the three trees, what the user shared, the
 * favourites and the boards, each listing nodes the rest of a path goes down from. */
export type Root = 'mine' | 'company' | 'shared' | 'sharing' | 'favourites' | 'boards';

export const ROOTS: Root[] = ['mine', 'company', 'shared', 'sharing', 'favourites', 'boards'];

export const rootKey = (root: Root) => `ponistra:${root}`;

const ROOT_LISTS: Record<Root, string> = {
  mine: '/api/nodes',
  company: '/api/nodes/company',
  shared: '/api/nodes/shared',
  sharing: '/api/nodes/shared?by=me',
  favourites: '/api/nodes/favourites',
  boards: '/api/nodes/boards',
};

const EMPTY: Record<Root, MessageKey> = {
  mine: 'tree.empty',
  company: 'tree.companyEmpty',
  shared: 'tree.sharedEmpty',
  sharing: 'tree.sharedByMeEmpty',
  favourites: 'favourites.empty',
  boards: 'boards.empty',
};

const idOf = (path: string) => path.split('/').pop() ?? '';
const above = (path: string) => path.replace(/\/?[^/]*$/, '');

/** Folders, documents, files and links; the collections of notes, links and boards are places
 * of their own. */
const kept = (node: ListedNode) => !node.notes && !node.links && !node.boards && !node.unplaced;

const editable = (nodes: ListedNode[]) =>
  nodes.length > 0 && nodes.every((node) => covers(node.role, 'edit') && !node.company);

/** A file as it is saved, a PDF with its notes, an image with its edits. */
function savedOf(node: TreeNode): SavedFile | undefined {
  if (node.kind !== 'file') return undefined;
  const bytes =
    kindOf(node) === 'file' ? 'noted' : EDITABLE.has(node.media_type ?? '') ? 'edited' : 'file';
  return {
    name: savedName(node),
    type: node.media_type ?? 'application/octet-stream',
    href: `/api/nodes/${node.id}/${bytes}?download=1`,
  };
}

function entryOf(node: ListedNode, heading?: string): FileEntry {
  return {
    name: node.id,
    label: node.title,
    fileName:
      node.kind === 'file' && node.extension ? `${node.title}.${node.extension}` : undefined,
    extension: node.extension,
    kind: node.kind === 'folder' ? 'folder' : 'file',
    shown: kindOf(node),
    size: node.size,
    modified: node.updated_at,
    by: node.updated_by?.name ?? null,
    heading,
    kept: node.kept,
  };
}

type Dialog =
  | { type: 'document'; parent: string | null; title?: string }
  | { type: 'link'; parent: string | null }
  | { type: 'scan'; parent: string | null }
  | { type: 'copy'; node: TreeNode }
  | { type: 'editLink'; node: TreeNode }
  | { type: 'group'; node: TreeNode }
  | { type: 'rename'; node: Pick<TreeNode, 'id' | 'title'> }
  | { type: 'join'; nodes: ListedNode[] }
  | { type: 'gather'; nodes: ListedNode[]; name: string | null };

/** What a place's menus open, held apart from the menus, which close as they open it. */
function dialogs() {
  let shown: Dialog | null = null;
  const told = new Set<() => void>();
  return {
    open: (dialog: Dialog | null) => {
      shown = dialog;
      told.forEach((tell) => tell());
    },
    get: () => shown,
    subscribe: (tell: () => void) => {
      told.add(tell);
      return () => told.delete(tell);
    },
  };
}

type Dialogs = ReturnType<typeof dialogs>;

interface Held {
  root: Root;
  nodes: Map<string, ListedNode>;
  folders: Map<string, { node: TreeNode | null; role: Role; confined: boolean }>;
  desk: Dialogs;
  /** The group of boards each heading of the boards' list stands for. */
  groups: Map<string, Pick<TreeNode, 'id' | 'title'>>;
}

const nodesOf = (held: Held, paths: string[]) =>
  paths.map((path) => held.nodes.get(idOf(path))).filter((node) => node !== undefined);

/** What an upload into a place is doing and what it could not import, as Ponistra imports. */
function Uploading() {
  const { t, formatNumber } = useI18n();
  const upload = useUploads();
  const named = (each: { name: string; error: Error }[]) =>
    each.map(({ name, error }) => `${name} (${errorMessage(error, t)})`).join(', ');
  return (
    <>
      {upload.pending && (
        <p className="text-sm text-muted" role="status">
          {upload.progress
            ? `${t('upload.progress')} ${formatNumber(upload.progress.done)} / ${formatNumber(upload.progress.total)} · ${formatSize(upload.progress.sent, formatNumber)} / ${formatSize(upload.progress.size, formatNumber)}`
            : t('file.uploading')}
        </p>
      )}
      {upload.unimported.length > 0 && (
        <p className="text-sm text-danger">
          {t('upload.unimported')} {named(upload.unimported)}
        </p>
      )}
      {upload.failed.length > 0 && (
        <p className="text-sm text-danger">
          {t('upload.failed')} {named(upload.failed)}
        </p>
      )}
    </>
  );
}

function Host({ held }: { held: Held }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const dialog = useSyncExternalStore(held.desk.subscribe, held.desk.get);
  const [gathering, setGathering] = useState<Gathering | null>(null);
  const followed = useFollowedRun(gathering, () => setGathering(null), true);
  const close = () => held.desk.open(null);
  const settled = () => queryClient.invalidateQueries({ queryKey: ['files', rootKey(held.root)] });
  useEffect(() => () => held.desk.open(null), [held]);
  useEffect(() => {
    if (params.get('create') !== 'document' || held.root !== 'mine') return;
    held.desk.open({ type: 'document', parent: null, title: params.get('title') ?? '' });
    setParams(
      (now) => {
        now.delete('create');
        now.delete('title');
        return now;
      },
      { replace: true },
    );
  }, [params, setParams, held]);
  return (
    <>
      {followed.bar && (
        <div className="pointer-events-none fixed inset-x-0 bottom-4 z-10 flex flex-col items-center gap-2 *:pointer-events-auto">
          {followed.bar}
        </div>
      )}
      {followed.failure && <p className="text-sm text-danger">{followed.failure.message}</p>}
      <Uploading />
      {dialog?.type === 'document' && (
        <NameDialog
          heading={t('tree.newDocument')}
          submitLabel={t('tree.create')}
          initial={dialog.title}
          onSubmit={(title) =>
            postJson<TreeNode>('/api/nodes', { kind: 'document', title, parent: dialog.parent })
          }
          onDone={(node) => {
            close();
            void navigate(nodeHref(node));
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'link' && (
        <LinkDialog
          heading={t('create.link')}
          submitLabel={t('tree.create')}
          onSubmit={(given) =>
            postJson<TreeNode>('/api/nodes', {
              kind: 'link',
              parent: dialog.parent,
              ...given,
            }).then(settled)
          }
          onClose={close}
        />
      )}
      {dialog?.type === 'editLink' && (
        <LinkDialog
          heading={t('tree.editLink')}
          submitLabel={t('tree.save')}
          link={dialog.node}
          onSubmit={(given) => patchJson(`/api/nodes/${dialog.node.id}`, given).then(settled)}
          onClose={close}
        />
      )}
      {dialog?.type === 'copy' && <CopyDialog node={dialog.node} onDone={close} onClose={close} />}
      {dialog?.type === 'group' && (
        <NameDialog
          heading={t('boards.group')}
          submitLabel={t('tree.move')}
          onSubmit={(group) => postJson('/api/nodes/boards', { node: dialog.node.id, group })}
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
          initial={dialog.node.title}
          onSubmit={(title) => patchJson(`/api/nodes/${dialog.node.id}`, { title })}
          onDone={() => {
            close();
            void settled();
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'gather' && (
        <GatherDialog
          nodes={dialog.nodes}
          name={dialog.name}
          onStarted={setGathering}
          onClose={close}
        />
      )}
      {dialog?.type === 'join' && (
        <Suspense fallback={null}>
          <JoinDialog
            files={dialog.nodes}
            onDone={(joined) => navigate(nodeHref(joined))}
            onClose={close}
          />
        </Suspense>
      )}
      {dialog?.type === 'scan' && (
        <Suspense fallback={null}>
          <ScanDialog
            parent={dialog.parent}
            onDone={(scanned) => navigate(nodeHref(scanned))}
            onClose={close}
          />
        </Suspense>
      )}
    </>
  );
}

function Create({ held, path }: { held: Held; path: string }) {
  const { t } = useI18n();
  const parent = idOf(path) || null;
  const folder = held.folders.get(path);
  const disabled =
    held.root === 'boards' ||
    !(path ? folder && covers(folder.role, 'edit') : held.root === 'mine');
  return (
    <>
      <MenuItem
        icon={FileText}
        label={t('tree.newDocument')}
        disabled={disabled}
        onSelect={() => held.desk.open({ type: 'document', parent })}
      />
      <MenuItem
        icon={Globe}
        label={t('create.link')}
        disabled={disabled}
        onSelect={() => held.desk.open({ type: 'link', parent })}
      />
      <MenuItem
        icon={ScanLine}
        label={t('create.scan')}
        disabled={disabled}
        onSelect={() => held.desk.open({ type: 'scan', parent })}
      />
    </>
  );
}

/** Two files or more chosen are joined from the bar of the chosen, as from their menu. */
function Join({ held, paths }: { held: Held; paths: string[] }) {
  const { t } = useI18n();
  const nodes = nodesOf(held, paths);
  if (nodes.length < 2 || !nodes.every((node) => kindOf(node) === 'file')) return null;
  const inside = folderKept(held, above(paths[0])) || nodes.some((node) => node.kept);
  return (
    <button
      type="button"
      aria-label={t('join.make')}
      title={inside ? t('confined.hint') : t('join.make')}
      disabled={inside}
      onClick={() => held.desk.open({ type: 'join', nodes })}
      className={iconButton}
    >
      <Combine size={16} aria-hidden />
    </button>
  );
}

function folderKept(held: Held, path: string) {
  const folder = held.folders.get(path);
  return Boolean(folder?.confined && !covers(folder.role, 'edit'));
}

function More({ held, paths, done }: { held: Held; paths: string[]; done: () => void }) {
  const { t } = useI18n();
  const visitor = useVisitor();
  const reachable = useReachable();
  const ai = useAi();
  const marks = useFavouriteMarks();
  const [, setParams] = useSearchParams();
  const nodes = nodesOf(held, paths);
  if (!nodes.length) return null;
  const [single] = nodes.length === 1 ? nodes : [];
  const changeable = editable(nodes) && reachable;
  const inside = folderKept(held, above(paths[0])) || nodes.some((node) => node.kept);
  const files = nodes.length > 1 && nodes.every((node) => kindOf(node) === 'file');
  const folder = held.folders.get(above(paths[0]))?.node;
  return (
    <>
      {single?.kind === 'link' && (
        <MenuItem
          icon={Pencil}
          label={t('tree.editLink')}
          disabled={!changeable}
          onSelect={() => held.desk.open({ type: 'editLink', node: single })}
        />
      )}
      {single?.kind === 'document' && (
        <MenuItem
          icon={Copy}
          label={t('copy.make')}
          disabled={inside}
          hint={inside ? t('confined.hint') : undefined}
          onSelect={() => held.desk.open({ type: 'copy', node: single })}
        />
      )}
      {files && (
        <MenuItem
          icon={Combine}
          label={t('join.make')}
          disabled={inside}
          hint={inside ? t('confined.hint') : undefined}
          onSelect={() => held.desk.open({ type: 'join', nodes })}
        />
      )}
      <MenuItem
        icon={TableProperties}
        label={t('action.nodesExtract.ask')}
        disabled={
          !ai.data || inside || nodes.every((node) => savedOf(node) && kindOf(node) !== 'file')
        }
        hint={ai.data === false ? t('ai.off') : inside ? t('confined.hint') : undefined}
        onSelect={() => {
          held.desk.open({
            type: 'gather',
            nodes,
            name: single ? single.title : (folder?.title ?? null),
          });
          done();
        }}
      />
      {single && kindOf(single) === 'board' && (
        <MenuItem
          icon={LayoutDashboard}
          label={t('boards.group')}
          disabled={!changeable}
          onSelect={() => held.desk.open({ type: 'group', node: single })}
        />
      )}
      {single && !visitor && (
        <MenuItem
          icon={Share2}
          label={t('access.share')}
          onSelect={() => setParams({ panel: 'access', node: single.id })}
        />
      )}
      <FavouriteItem nodes={nodes} marks={marks} />
      <KeepItem nodes={nodes} confined={inside} />
    </>
  );
}

/** A group of boards is renamed or trashed from its own menu, as no list shows it. */
function GroupItems({ held, path }: { held: Held; path: string }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const reachable = useReachable();
  const folder = held.folders.get(path);
  if (!folder?.node) return null;
  const node = folder.node;
  const changeable = reachable && covers(folder.role, 'edit');
  return (
    <>
      <MenuSeparator />
      <MenuItem
        icon={Pencil}
        label={t('tree.rename')}
        disabled={!changeable}
        onSelect={() => held.desk.open({ type: 'rename', node })}
      />
      <MenuItem
        icon={Trash2}
        label={t('tree.toTrash')}
        disabled={!changeable}
        onSelect={() =>
          void postJson('/api/nodes/trash', { nodes: [node.id] }).then(() =>
            navigate(filesHref(rootKey(held.root), above(path)), { replace: true }),
          )
        }
      />
    </>
  );
}

/** A heading of the boards' list is its group, renamed or trashed from its own menu. */
function HeadingItems({ held, heading }: { held: Held; heading: string }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const reachable = useReachable();
  const group = held.groups.get(heading);
  if (!group) return null;
  return (
    <>
      <MenuItem
        icon={Pencil}
        label={t('tree.rename')}
        disabled={!reachable}
        onSelect={() => held.desk.open({ type: 'rename', node: group })}
      />
      <MenuItem
        icon={Trash2}
        label={t('tree.toTrash')}
        disabled={!reachable}
        onSelect={() =>
          void postJson('/api/nodes/trash', { nodes: [group.id] }).then(() =>
            queryClient.invalidateQueries({ queryKey: ['files', rootKey(held.root)] }),
          )
        }
      />
    </>
  );
}

function Marks({ held, path }: { held: Held; path: string }) {
  const { t } = useI18n();
  const { ids } = useFavouriteMarks();
  const node = held.nodes.get(idOf(path));
  return (
    <>
      {ids.has(idOf(path)) && (
        <Star
          size={14}
          role="img"
          aria-label={t('favourites.title')}
          className="shrink-0 fill-current text-accent"
        />
      )}
      {node?.confined && (
        <Lock
          size={14}
          role="img"
          aria-label={t('confined.label')}
          className="shrink-0 text-muted"
        />
      )}
    </>
  );
}

/** The folder's own sharing, and that of an entry its menu asked for. */
function useAccess(held: Held, path: string) {
  const [params, setParams] = useSearchParams();
  if (params.get('panel') !== 'access') return null;
  const id = params.get('node') ?? idOf(path);
  const node = held.nodes.get(id) ?? held.folders.get(path)?.node;
  if (!node || node.id !== id) return null;
  return <AccessPanel key={node.id} node={node} onClose={() => setParams({})} />;
}

function ShareFolder({ held, path }: { held: Held; path: string }) {
  const { t } = useI18n();
  const visitor = useVisitor();
  const [params, setParams] = useSearchParams();
  const folder = held.folders.get(path)?.node;
  if (!folder || visitor) return null;
  const shown = params.get('panel') === 'access' && params.get('node') === folder.id;
  return (
    <button
      type="button"
      aria-pressed={shown}
      onClick={() => setParams(shown ? {} : { panel: 'access', node: folder.id })}
      className={`${button} aria-pressed:bg-selected`}
    >
      <Share2 size={16} aria-hidden />
      <span className="sr-only sm:not-sr-only">{t('access.share')}</span>
    </button>
  );
}

function SharedToggle({ root }: { root: Root }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  return (
    <div
      role="group"
      aria-label={t('tree.shared')}
      className="flex self-start rounded-lg bg-raised p-0.5"
    >
      {(['shared', 'sharing'] as const).map((each) => (
        <button
          key={each}
          type="button"
          aria-pressed={each === root}
          onClick={() => void navigate(PONISTRA_HREFS[each], { replace: true })}
          className="rounded-md px-3 py-1 text-sm text-muted hover:text-ink aria-pressed:bg-surface aria-pressed:font-semibold aria-pressed:text-ink aria-pressed:shadow-sm"
        >
          {t(each === 'sharing' ? 'tree.sharedByMe' : 'tree.sharedWithMe')}
        </button>
      ))}
    </div>
  );
}

function Places() {
  return useWide() ? null : <PhonePlaces />;
}

/** What the lists of a place have shown, one for every source made of it: the listings stay in
 * the query cache when the tree makes its sources anew, and opening an entry needs its node. */
const HELD = new Map<Root, Held>();

function heldOf(root: Root): Held {
  let held = HELD.get(root);
  if (!held) {
    held = { root, nodes: new Map(), folders: new Map(), desk: dialogs(), groups: new Map() };
    HELD.set(root, held);
  }
  return held;
}

/** A place of Ponistra's own tree as a source of the file browser: paths are chains of node ids
 * from the place's top, the entries' labels their titles. Documents open in their editors, files
 * on their pages; what Ponistra does beyond files comes through the source's menus and panels. */
export function ponistraSource(
  root: Root,
  name: string,
  t: (key: MessageKey) => string,
): FileSource {
  const held = heldOf(root);
  const remember = (children: ListedNode[]) =>
    children.forEach((node) => held.nodes.set(node.id, node));
  const headings = (children: (ListedNode & FoundNode)[]) => {
    if (root === 'favourites')
      return new Map(children.map((node) => [node.id, placeText(node, t)]));
    if (root === 'boards')
      return new Map(
        boardGroups(children, t).flatMap(({ title, group, boards }) => {
          if (group) held.groups.set(title, group);
          return boards.map((board) => [board.id, title] as const);
        }),
      );
    return new Map<string, string>();
  };
  return {
    key: rootKey(root),
    name,
    writable: root === 'mine',
    trash: true,
    list: async (path): Promise<Listed> => {
      if (!path) {
        const listing = await getJson<{
          children: (ListedNode & FoundNode)[];
          role?: Role;
          confined?: boolean;
        }>(ROOT_LISTS[root]);
        remember(listing.children);
        held.folders.set('', {
          node: null,
          role: listing.role ?? 'read',
          confined: Boolean(listing.confined),
        });
        const under = headings(listing.children);
        const shown = listing.children.filter(kept);
        return {
          path,
          entries: (root === 'boards'
            ? boardGroups(shown, t).flatMap((group) => group.boards)
            : shown
          ).map((node) => entryOf(node, under.get(node.id))),
          writable: root === 'mine',
        };
      }
      const listing = await getJson<{
        folder: TreeNode;
        children: ListedNode[];
        role: Role;
        confined: boolean;
      }>(`/api/nodes?parent=${idOf(path)}`);
      remember(listing.children);
      held.folders.set(path, {
        node: listing.folder,
        role: listing.role,
        confined: listing.confined,
      });
      return {
        path,
        entries: listing.children.filter(kept).map((node) => entryOf(node)),
        writable: covers(listing.role, 'edit'),
        kept: listing.confined && !covers(listing.role, 'edit'),
      };
    },
    labels: async (path) => {
      const parts = path.split('/').filter(Boolean);
      if (!parts.length) return [];
      const placement = await getJson<Placement>(`/api/nodes/${parts.at(-1)}`);
      const titles = new Map(
        [...placement.path, placement.node].map((node) => [node.id, node.title]),
      );
      return parts.map((id) => titles.get(id) ?? held.nodes.get(id)?.title ?? id);
    },
    rawHref: (path, download) => `/api/nodes/${idOf(path)}/file${download ? '?download=1' : ''}`,
    pictureHref: (path) => {
      const picture = held.nodes.get(idOf(path))?.picture;
      return picture ? `/api/nodes/${idOf(path)}/picture?v=${picture}` : '';
    },
    zipHref: (paths) =>
      `/api/nodes/zip?${new URLSearchParams(paths.map((path) => ['node', idOf(path)])).toString()}`,
    openHref: (path, entry) => {
      const node = held.nodes.get(idOf(path));
      if (node) return nodeHref(node);
      return nodeHref({
        id: idOf(path),
        kind: entry.kind === 'folder' ? 'folder' : 'document',
        title: entry.label ?? entry.name,
      });
    },
    saved: (path) => {
      const node = held.nodes.get(idOf(path));
      return node && savedOf(node);
    },
    read: () => Promise.reject(new Error('not_text')),
    write: () => Promise.reject(new Error('not_text')),
    folder: (path, title) =>
      postJson('/api/nodes', { kind: 'folder', title, parent: idOf(path) || null }),
    rename: async (path, to) => {
      if (above(path) !== above(to))
        return postJson('/api/nodes/move', {
          nodes: [idOf(path)],
          parent: idOf(above(to)) || null,
        });
      return patchJson(`/api/nodes/${idOf(path)}`, { title: idOf(to) });
    },
    remove: (paths) => postJson('/api/nodes/trash', { nodes: paths.map(idOf) }),
    put: async (path, _name, file) =>
      placed(await upload(file), file.name, idOf(path) || null, file.lastModified),
    icon: (path) => {
      const node = held.nodes.get(idOf(path));
      return node ? <NodeIcon node={node} /> : undefined;
    },
    marks: (path) => <Marks held={held} path={path} />,
    columns: [
      {
        label: 'explorer.updatedBy',
        className: 'hidden text-sm text-muted lg:table-cell',
        cell: (_, entry) => entry.by,
      },
      {
        label: 'access.title',
        className: 'hidden text-sm text-muted sm:table-cell',
        cell: (path) => {
          const node = held.nodes.get(idOf(path));
          return node && <Audience node={node} />;
        },
      },
    ],
    create: (path) => <Create held={held} path={path} />,
    moveTo: (paths, onClose) => <MoveDialog nodes={nodesOf(held, paths)} onClose={onClose} />,
    more: (paths, done) => <More held={held} paths={paths} done={done} />,
    chosenActions: (paths) => <Join held={held} paths={paths} />,
    headingItems: (heading) => <HeadingItems held={held} heading={heading} />,
    changes: (paths) => editable(nodesOf(held, paths)),
    useSend: function useSend() {
      const uploads = useUploads();
      return (path, picked) => uploads.start(picked, idOf(path) || null);
    },
    actions: (path) => (path ? <ShareFolder held={held} path={path} /> : null),
    folderItems: (path) =>
      root === 'boards' && path ? <GroupItems held={held} path={path} /> : null,
    usePanel(path) {
      return useAccess(held, path);
    },
    preview: (path, chosen, onClose) => (
      <PreviewPanel
        chosen={nodesOf(held, chosen)}
        kept={folderKept(held, path) || nodesOf(held, chosen).some((node) => node.kept)}
        onClose={onClose}
      />
    ),
    showing: () => root === 'boards',
    makes: () => root !== 'boards',
    empty: (path) => (path && root !== 'boards' ? 'tree.empty' : EMPTY[root]),
    aside: (path) =>
      root === 'shared' || root === 'sharing' ? (
        path ? null : (
          <SharedToggle root={root} />
        )
      ) : root === 'mine' && !path ? (
        <Places />
      ) : null,
    dragged: (event: DragEvent, paths, saved) => startDrag(event, paths.map(idOf), saved),
    host: <Host held={held} />,
  };
}
