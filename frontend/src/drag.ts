import { useState, type DragEvent } from 'react';
import type { Picked } from './upload';

const NODES = 'application/x-ponistra-nodes';

let dragging: string[] = [];

/** A file as the desktop takes it from a drag. */
export interface Saved {
  name: string;
  type: string;
  href: string;
}

/** Drags nodes to another folder; a file dragged alone can also be dropped out of the browser,
 * where Chromium saves it. */
export function startDrag(event: DragEvent, ids: string[], saved?: Saved) {
  dragging = ids;
  event.dataTransfer.setData(NODES, JSON.stringify(ids));
  if (saved) {
    const url = new URL(saved.href, location.href);
    event.dataTransfer.setData('DownloadURL', `${saved.type}:${saved.name}:${url}`);
  }
  event.dataTransfer.effectAllowed = saved ? 'copyMove' : 'move';
}

export function endDrag() {
  dragging = [];
}

// A drop the page does not take would make the browser open the dropped file in
// place of the app.
export function refuseStrayFiles(event: DragEvent) {
  if (!event.dataTransfer.types.includes('Files')) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = 'none';
}

export function useDropTarget({
  id,
  onNodes,
  onFiles,
}: {
  id?: string | null;
  onNodes?: (ids: string[]) => void;
  onFiles?: (picked: Promise<Picked[]>) => void;
}) {
  const [over, setOver] = useState(false);
  const accepts = (event: DragEvent) => {
    const types = event.dataTransfer.types;
    if (types.includes(NODES)) return !!onNodes && !(id && dragging.includes(id));
    return !!onFiles && types.includes('Files');
  };
  return {
    over,
    props: {
      onDragOver: (event: DragEvent) => {
        if (!accepts(event)) return;
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = event.dataTransfer.types.includes(NODES) ? 'move' : 'copy';
        setOver(true);
      },
      onDragLeave: (event: DragEvent) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(false);
      },
      onDrop: (event: DragEvent) => {
        if (!accepts(event)) return;
        event.preventDefault();
        event.stopPropagation();
        setOver(false);
        const nodes = event.dataTransfer.getData(NODES);
        if (nodes) onNodes?.(JSON.parse(nodes) as string[]);
        else onFiles?.(dropped(event.dataTransfer));
      },
    },
  };
}

/** What was dropped, a folder with every file below it; the browser hands over its entries only
 * while the drop is handled, and they are read after. */
export function dropped(transfer: DataTransfer): Promise<Picked[]> {
  const entries = [...transfer.items].flatMap((item) => {
    const entry = item.kind === 'file' ? item.webkitGetAsEntry() : null;
    return entry ? [entry] : [];
  });
  if (!entries.length)
    return Promise.resolve([...transfer.files].map((file) => ({ file, folders: [] })));
  return Promise.all(entries.map((entry) => below(entry, []))).then((all) => all.flat());
}

async function below(entry: FileSystemEntry, folders: string[]): Promise<Picked[]> {
  if (folders.length && entry.name.startsWith('.')) return [];
  if (entry.isFile) {
    const file = await new Promise<File>((done, fail) =>
      (entry as FileSystemFileEntry).file(done, fail),
    );
    return [{ file, folders }];
  }
  if (!entry.isDirectory) return [];
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const read = () => new Promise<FileSystemEntry[]>((done, fail) => reader.readEntries(done, fail));
  const children: FileSystemEntry[] = [];
  // A folder gives its entries a batch at a time, until an empty one.
  for (let batch = await read(); batch.length; batch = await read()) children.push(...batch);
  const inside = [...folders, entry.name];
  return (await Promise.all(children.map((child) => below(child, inside)))).flat();
}
