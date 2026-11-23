import { getJson, postJson, upload } from './api';
import type { Opened, Written } from './codeEditor';
import { segment, type FileEntry, type FileSource, type FileStat } from './files';
import { runJob } from './jobs';

const asked = (folder: string, path: string, more: Record<string, string> = {}) =>
  new URLSearchParams({ folder, path, ...more }).toString();

/** A project of the workspace as a source of Files (ML6, D55). */
export function workspaceSource(folder: string, name: string): FileSource {
  const key = `workspace:${folder}`;
  return {
    key,
    name,
    writable: true,
    list: (path) =>
      getJson<{ path: string; entries: FileEntry[] }>(
        `/api/workspace/files?${asked(folder, path)}`,
      ),
    rawHref: (path, download) =>
      `/api/workspace/file/raw?${asked(folder, path, download ? { download: '1' } : {})}`,
    pictureHref: (path) => `/api/workspace/file/picture?${asked(folder, path)}`,
    heldBase: (path) => `/api/workspace/held/${segment(folder)}/${segment(path)}`,
    zipHref: (paths) =>
      `/api/workspace/files/zip?${new URLSearchParams([['folder', folder], ...paths.map((path) => ['path', path])]).toString()}`,
    read: (path) => getJson<Opened>(`/api/workspace/file?${asked(folder, path)}`),
    write: (path, text, hash) =>
      postJson<Written>('/api/workspace/file', { folder, path, text, hash }),
    folder: (path, name) => postJson('/api/workspace/files/folder', { folder, path, name }),
    rename: (path, to) => postJson('/api/workspace/files/rename', { folder, path, to }),
    remove: (paths) => postJson('/api/workspace/files/remove', { folder, paths }),
    put: async (path, name, file) =>
      postJson('/api/workspace/files/put', {
        folder,
        path,
        name,
        blob: (await upload(file)).sha256,
      }),
    stat: (path) => getJson<FileStat>(`/api/workspace/files/stat?${asked(folder, path)}`),
    mode: (path, mode) => postJson<FileStat>('/api/workspace/files/mode', { folder, path, mode }),
    owner: (path, uid, gid) =>
      postJson<FileStat>('/api/workspace/files/owner', { folder, path, uid, gid }),
    search: (path, query) =>
      getJson(`/api/workspace/files/search?${asked(folder, path, { q: query })}`),
    folderSize: (path) => getJson(`/api/workspace/files/size?${asked(folder, path)}`),
    checksum: (path, algorithm) =>
      runJob('checksum', { source: key, path, algorithm }, path.split('/').pop() ?? path),
  };
}
