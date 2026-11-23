import { getJson, patchJson, postJson, upload } from './api';
import type { FileEntry, FileSource, Listed } from './files';
import { kindOf, nodeHref, type ListedNode, type Placement, type TreeNode } from './tree';
import { placed } from './upload';

export type Root = 'mine' | 'company' | 'shared';

export const ROOTS: Root[] = ['mine', 'company', 'shared'];

export const rootKey = (root: Root) => `ponistra:${root}`;

const ROOT_LISTS: Record<Root, string> = {
  mine: '/api/nodes',
  company: '/api/nodes/company',
  shared: '/api/nodes/shared',
};

const idOf = (path: string) => path.split('/').pop() ?? '';
const above = (path: string) => path.replace(/\/?[^/]*$/, '');

/** Folders, documents and files; the collections of notes, links and boards and the links
 * themselves are no files. */
const kept = (node: ListedNode) =>
  node.kind !== 'link' && !node.notes && !node.links && !node.boards && !node.unplaced;

function entryOf(node: ListedNode): FileEntry {
  const shown = kindOf(node);
  return {
    name: node.id,
    label: node.kind === 'file' && node.extension ? `${node.title}.${node.extension}` : node.title,
    kind: node.kind === 'folder' ? 'folder' : 'file',
    shown,
    size: node.size,
    modified: node.updated_at,
  };
}

/** A place of Ponistra's own tree as a source of the file browser: paths are chains of node ids
 * from the place's top, the entries' labels their titles. Documents open in their editors, files
 * on their pages. */
export function ponistraSource(root: Root, name: string): FileSource {
  const pictures = new Map<string, string>();
  const nodes = new Map<string, TreeNode>();
  const remember = (children: ListedNode[]) =>
    children.forEach((node) => {
      nodes.set(node.id, node);
      if (node.picture) pictures.set(node.id, node.picture);
    });
  return {
    key: `ponistra:${root}`,
    name,
    writable: root === 'mine',
    list: async (path): Promise<Listed> => {
      if (!path) {
        const listing = await getJson<{ children: ListedNode[]; role?: string }>(ROOT_LISTS[root]);
        remember(listing.children);
        return {
          path,
          entries: listing.children.filter(kept).map(entryOf),
          writable: root === 'mine',
        };
      }
      const listing = await getJson<{ children: ListedNode[]; role: string }>(
        `/api/nodes?parent=${idOf(path)}`,
      );
      remember(listing.children);
      return {
        path,
        entries: listing.children.filter(kept).map(entryOf),
        writable: listing.role !== 'read',
      };
    },
    labels: async (path) => {
      const parts = path.split('/').filter(Boolean);
      if (!parts.length) return [];
      const placement = await getJson<Placement>(`/api/nodes/${parts.at(-1)}`);
      const titles = new Map(
        [...placement.path, placement.node].map((node) => [node.id, node.title]),
      );
      return parts.map((id) => titles.get(id) ?? nodes.get(id)?.title ?? id);
    },
    rawHref: (path, download) => `/api/nodes/${idOf(path)}/file${download ? '?download=1' : ''}`,
    pictureHref: (path) => {
      const picture = pictures.get(idOf(path));
      return picture ? `/api/nodes/${idOf(path)}/picture?v=${picture}` : '';
    },
    zipHref: (paths) =>
      `/api/nodes/zip?${new URLSearchParams(paths.map((path) => ['node', idOf(path)])).toString()}`,
    openHref: (path, entry) => {
      const node = nodes.get(idOf(path));
      if (node) return nodeHref(node);
      return nodeHref({
        id: idOf(path),
        kind: entry.kind === 'folder' ? 'folder' : 'document',
        title: entry.label ?? entry.name,
      });
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
  };
}
