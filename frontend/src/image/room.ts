import { useEffect, useState, useSyncExternalStore } from 'react';
import * as Y from 'yjs';
import { joinRoom, useRecheck } from '../room';
import { EDITS, editsOf, MARKS, marksIn, NONE, type Change, type Edits, type Mark } from './edits';

const OWN = 'own edits';
const AS_IT_CAME: Kept = { edits: NONE, marks: [], undoable: false, redoable: false };

export interface Kept {
  edits: Edits;
  marks: readonly [string, Mark][];
  undoable: boolean;
  redoable: boolean;
}

/** The image file's room: its edits and marks, each change a step this editor takes back. */
export interface ImageRoom {
  change: (patch: Change) => void;
  mark: (id: string, mark: Mark | null) => void;
  /** Takes every edit and mark away, as one step. */
  reset: () => void;
  undo: () => void;
  redo: () => void;
  subscribe: (changed: () => void) => () => void;
  current: () => Kept;
}

/** The image's edits and marks as the doc keeps them, and what tells the page when they change. */
function held(doc: Y.Doc): { room: ImageRoom; tell: () => void; destroy: () => void } {
  const edits = doc.getMap<unknown>(EDITS);
  const marks = doc.getMap<Mark>(MARKS);
  const undo = new Y.UndoManager([edits, marks], {
    trackedOrigins: new Set([OWN]),
    captureTimeout: 0,
  });
  const listeners = new Set<() => void>();
  let kept = AS_IT_CAME;
  const tell = () => {
    kept = {
      edits: editsOf(edits),
      marks: marksIn(marks),
      undoable: undo.canUndo(),
      redoable: undo.canRedo(),
    };
    for (const listener of listeners) listener();
  };
  edits.observe(tell);
  marks.observe(tell);
  for (const event of ['stack-item-added', 'stack-item-popped', 'stack-cleared'] as const) {
    undo.on(event, tell);
  }
  return {
    room: {
      change: (patch) =>
        doc.transact(() => {
          for (const [key, value] of Object.entries(patch) as [keyof Edits, unknown][]) {
            if (value === null || value === NONE[key]) edits.delete(key);
            else edits.set(key, value);
          }
        }, OWN),
      mark: (id, mark) => doc.transact(() => (mark ? marks.set(id, mark) : marks.delete(id)), OWN),
      reset: () =>
        doc.transact(() => {
          edits.clear();
          marks.clear();
        }, OWN),
      undo: () => undo.undo(),
      redo: () => undo.redo(),
      subscribe: (changed) => {
        listeners.add(changed);
        return () => listeners.delete(changed);
      },
      current: () => kept,
    },
    tell,
    destroy: () => undo.destroy(),
  };
}

/** Joins the image file's room once it has synced; without a room, nothing is joined. */
export function useImageRoom(room: string | null, fileId: string): ImageRoom | null {
  const recheck = useRecheck(fileId);
  const [joined, setJoined] = useState<ImageRoom | null>(null);
  useEffect(() => {
    if (room === null) return;
    const doc = new Y.Doc();
    const kept = held(doc);
    const { provider, leave } = joinRoom(room, doc, recheck);
    let ready = false;
    provider.on('sync', (synced: boolean) => {
      if (!synced || ready) return;
      ready = true;
      kept.tell();
      setJoined(kept.room);
    });
    return () => {
      leave();
      kept.destroy();
      doc.destroy();
      setJoined(null);
    };
  }, [room, fileId, recheck]);
  return joined;
}

/** Edits and marks kept only in this page, for an image a document shows, which takes the copy
 * they draw as a new image of its own. */
export function useOwnImageRoom(): ImageRoom | null {
  const [own, setOwn] = useState<ImageRoom | null>(null);
  useEffect(() => {
    const doc = new Y.Doc();
    const kept = held(doc);
    setOwn(kept.room);
    return () => {
      kept.destroy();
      doc.destroy();
      setOwn(null);
    };
  }, []);
  return own;
}

/** The edits and marks as the backend reads them: each edit only where it changes the image. */
export function sentOf(kept: Kept): { edits: Partial<Edits>; marks: Record<string, Mark> } {
  return {
    edits: Object.fromEntries(
      (Object.keys(NONE) as (keyof Edits)[])
        .filter((key) => kept.edits[key] !== NONE[key])
        .map((key) => [key, kept.edits[key]]),
    ),
    marks: Object.fromEntries(kept.marks),
  };
}

const unsubscribed = () => () => {};

export function useKept(room: ImageRoom | null): Kept {
  return useSyncExternalStore(room?.subscribe ?? unsubscribed, room?.current ?? (() => AS_IT_CAME));
}
