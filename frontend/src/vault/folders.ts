import type { Bytes } from './crypto';
import { sealJson } from './secret';

/** A folder of a collection; its name is sealed with the collection's key until the browser
    opens it. */
export interface Folder {
  id: string;
  parent: string | null;
  name: string;
}

/** The names from the collection's top down to the folder. */
export function pathOf(id: string | null, folders: Folder[]): string[] {
  const byId = new Map(folders.map((folder) => [folder.id, folder]));
  const names: string[] = [];
  for (let at = id ? byId.get(id) : undefined; at; at = at.parent ? byId.get(at.parent) : undefined)
    names.unshift(at.name);
  return names;
}

/** How many items each folder holds, in it or in the folders under it. */
export function counted(folders: Folder[], filed: (string | null)[]): Map<string, number> {
  const byId = new Map(folders.map((folder) => [folder.id, folder]));
  const counts = new Map<string, number>();
  for (const id of filed)
    for (
      let at = id ? byId.get(id) : undefined;
      at;
      at = at.parent ? byId.get(at.parent) : undefined
    )
      counts.set(at.id, (counts.get(at.id) ?? 0) + 1);
  return counts;
}

/** The folders as a tree lists them: each after its parent, those of one parent by name, with
    how deep each lies. */
export function laidOut(
  folders: Folder[],
  compare: (a: string, b: string) => number,
): { folder: Folder; depth: number }[] {
  const children = new Map<string | null, Folder[]>();
  for (const folder of folders)
    children.set(folder.parent, [...(children.get(folder.parent) ?? []), folder]);
  const listed: { folder: Folder; depth: number }[] = [];
  const visit = (parent: string | null, depth: number) => {
    for (const folder of (children.get(parent) ?? []).sort((a, b) => compare(a.name, b.name))) {
      listed.push({ folder, depth });
      visit(folder.id, depth + 1);
    }
  };
  visit(null, 0);
  return listed;
}

/** The folders to make so that each path exists, given as the names of its levels, those the
    collection has reused by name; and for each path the folder it ends in, none for an empty
    one. */
export function planned(
  paths: string[][],
  folders: Folder[],
): { made: Folder[]; ends: (string | null)[] } {
  const all = [...folders];
  const made: Folder[] = [];
  const ends = paths.map((path) => {
    let parent: string | null = null;
    for (const name of path.map((level) => level.trim()).filter(Boolean)) {
      const wanted = name.toLocaleLowerCase();
      let found = all.find(
        (folder) => folder.parent === parent && folder.name.toLocaleLowerCase() === wanted,
      );
      if (!found) {
        found = { id: crypto.randomUUID(), parent, name };
        all.push(found);
        made.push(found);
      }
      parent = found.id;
    }
    return parent;
  });
  return { made, ends };
}

/** The folders as the server takes them, each name sealed with the collection's key. */
export function sealedFolders(key: Bytes, folders: Folder[]): Promise<Folder[]> {
  return Promise.all(
    folders.map(async (folder) => ({ ...folder, name: await sealJson(key, folder.name) })),
  );
}
