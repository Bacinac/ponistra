import { createContext, useContext, useRef, useState, type ReactNode } from 'react';
import { ApiError, postJson, upload } from './api';
import { IMPORTED } from './importable';
import { runJob } from './jobs';
import { useHeldRelease } from './release';
import { useTreeChange, type TreeNode } from './tree';

export const IMPORT_ACCEPT = [...Object.entries(IMPORTED).flat(), '.csv', 'text/csv'].join(',');
/** The bookmarks a browser exports, which a new import makes into a folder of links. */
const BOOKMARKS = 'text/x-netscape-bookmarks';
/** Pictures, which a file shows as they are. */
const IMAGES: Record<string, string[]> = {
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/gif': ['.gif'],
  'image/webp': ['.webp'],
  'image/avif': ['.avif'],
  'image/svg+xml': ['.svg'],
};
export const IMAGE_ACCEPT = Object.entries(IMAGES).flat(2).join(',');
/** An extension as Windows reads one: the letters and digits after the name's last dot. */
const EXTENSION = /\.([a-z0-9]*[a-z][a-z0-9]*)$/i;
/** What an import refuses in the file itself, which then stays the file it is. */
const UNIMPORTABLE = new Set([
  'unreadable',
  'too_many_cells',
  'too_many_formulas',
  'too_large',
  'newer_file',
]);

/** A file's name as PONISTRA keeps it: the title, and apart from it the extension that names
 * the file's kind. */
export function named(name: string): { title: string; extension: string } {
  const found = EXTENSION.exec(name);
  const extension = found && found.index > 0 && found[1].length <= 10 ? found[1] : '';
  const title = extension ? name.slice(0, found!.index).trim() : name.trim();
  return { title: (title || name).slice(0, 200), extension: extension.toLowerCase() };
}

/** The name a file is saved under, as the server gives it. */
export function savedName({ title, extension }: Pick<TreeNode, 'title' | 'extension'>): string {
  return extension ? `${title}.${extension}` : title;
}

export interface Placed {
  node: TreeNode;
  /** Why a file of a kind PONISTRA imports was kept as the file it is. */
  unimported?: ApiError;
}

/** A stored file placed among the documents: made into a document, or bookmarks into a folder
 * of links, where PONISTRA imports its kind and can read it, else kept as the file it is; last
 * changed when the file was, where its disk tells. */
export async function placed(
  stored: { sha256: string; media_type: string },
  name: string,
  parent: string | null,
  lastModified?: number,
): Promise<Placed> {
  const { title, extension } = named(name);
  const modified = lastModified ? { modified: new Date(lastModified).toISOString() } : {};
  const kept = () =>
    postJson<TreeNode>('/api/nodes', {
      kind: 'file',
      parent,
      blob: stored.sha256,
      title,
      extension,
      ...modified,
    });
  const delimited = extension === 'csv' && stored.media_type === 'text/plain';
  if (!(stored.media_type in IMPORTED) && stored.media_type !== BOOKMARKS && !delimited)
    return { node: await kept() };
  try {
    return {
      node: await runJob<TreeNode>(
        'import',
        { blob: stored.sha256, title, parent, ...modified },
        name,
      ),
    };
  } catch (error) {
    if (!(error instanceof ApiError && UNIMPORTABLE.has(error.code ?? ''))) throw error;
    return { node: await kept(), unimported: error };
  }
}

/** A file to upload and the folders it lies in below the one it goes into. */
export interface Picked {
  file: File;
  folders: string[];
}

export function loose(files: File[]): Picked[] {
  return files.map((file) => ({ file, folders: [] }));
}

/** The files of a folder picked whole, each in the folders its path names, the picked one first. */
export function inFolder(files: File[]): Picked[] {
  return files.map((file) => ({ file, folders: file.webkitRelativePath.split('/').slice(0, -1) }));
}

/** A file whose name, or a folder's below the one picked, starts with a dot: kept out of sight. */
export function isHidden({ file, folders }: Picked): boolean {
  return (
    folders.length > 0 && [...folders.slice(1), file.name].some((name) => name.startsWith('.'))
  );
}

export function pathOf({ file, folders }: Picked): string {
  return [...folders, file.name].join('/');
}

/** Places the picked files among the documents, a folder made for each one they lie in; a file
 * that fails is told and the others go on, and those placed are told at the end. */
function useUpload() {
  const [unimported, setUnimported] = useState<{ name: string; error: Error }[]>([]);
  const [failed, setFailed] = useState<{ name: string; error: Error }[]>([]);
  const [progress, setProgress] = useState<{
    done: number;
    total: number;
    sent: number;
    size: number;
  } | null>(null);
  const create = useTreeChange(
    async ({ picked, parent }: { picked: Promise<Picked[]>; parent: string | null }) => {
      const shown = (await picked).filter((each) => !isHidden(each));
      setUnimported([]);
      setFailed([]);
      const made = new Map<string, Promise<string | null>>();
      const folderOf = (folders: string[]): Promise<string | null> => {
        if (!folders.length) return Promise.resolve(parent);
        const key = folders.join('/');
        let folder = made.get(key);
        if (!folder) {
          folder = folderOf(folders.slice(0, -1))
            .then((above) =>
              postJson<TreeNode>('/api/nodes', {
                kind: 'folder',
                title: folders.at(-1),
                parent: above,
              }),
            )
            .then((node) => node.id);
          made.set(key, folder);
        }
        return folder;
      };
      const size = shown.reduce((sum, each) => sum + each.file.size, 0);
      const nodes: TreeNode[] = [];
      let before = 0;
      try {
        for (const [index, each] of shown.entries()) {
          const start = before;
          before += each.file.size;
          const told = (sent: number) =>
            setProgress({ done: index, total: shown.length, sent: start + sent, size });
          told(0);
          try {
            const parent = await folderOf(each.folders);
            const stored = await upload(each.file, told);
            const { node, unimported } = await placed(
              stored,
              each.file.name,
              parent,
              each.file.lastModified,
            );
            nodes.push(node);
            if (unimported)
              setUnimported((kept) => [...kept, { name: pathOf(each), error: unimported }]);
          } catch (error) {
            const named = error instanceof Error ? error : new Error(String(error));
            setFailed((kept) => [...kept, { name: pathOf(each), error: named }]);
          }
        }
      } finally {
        setProgress(null);
      }
      return nodes;
    },
  );
  const start = (
    picked: Picked[] | Promise<Picked[]>,
    parent: string | null,
    onPlaced?: (nodes: TreeNode[]) => void,
  ) => create.mutate({ picked: Promise.resolve(picked), parent }, { onSuccess: onPlaced });
  useHeldRelease(create.isPending);
  return { start, unimported, failed, progress, pending: create.isPending, error: create.error };
}

type Uploads = ReturnType<typeof useUpload>;

const UploadContext = createContext<Uploads | null>(null);

/** The app's uploads, which go on and are told wherever the user goes meanwhile. */
export function UploadProvider({ children }: { children: ReactNode }) {
  return <UploadContext value={useUpload()}>{children}</UploadContext>;
}

export function useUploads(): Uploads {
  return useContext(UploadContext)!;
}

export function useFilePicker(
  onPick: (files: File[]) => void,
  {
    accept,
    multiple = true,
    folder = false,
    camera = false,
  }: { accept?: string; multiple?: boolean; folder?: boolean; camera?: boolean } = {},
) {
  const input = useRef<HTMLInputElement>(null);
  const element = (
    <input
      ref={input}
      type="file"
      accept={accept}
      capture={camera ? 'environment' : undefined}
      multiple={multiple}
      hidden
      onChange={(event) => {
        const files = Array.from(event.target.files ?? []);
        event.target.value = '';
        if (files.length > 0) onPick(files);
      }}
    />
  );
  const open = () => {
    if (!input.current) return;
    input.current.webkitdirectory = folder;
    input.current.click();
  };
  return { element, open };
}
