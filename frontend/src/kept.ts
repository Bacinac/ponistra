import { IndexeddbPersistence } from 'y-indexeddb';
import type * as Y from 'yjs';

/** What a device marked to work without the network keeps (D45): the server's answers the tree,
 * the documents and the recent mail are shown from, each kept document's rooms, the files the
 * recent mail carries, the documents its user marks, the mail written meanwhile and the app
 * itself. Nothing is kept on a device that is not marked. */

const FLAG = 'ponistra.offline';
const DATABASE = 'ponistra-offline';
const ANSWERS = 'answers';
const MARKS = 'marks';
const OUTBOX = 'outbox';
const ROOM = 'ponistra-room-';
export const SHELL = 'ponistra-shell';
const PARTS = 'ponistra-mail';
const MAIL = '/api/mail/';

// The user's own mailbox alone: what a shared one answers (`box=`) is never kept.
const KEPT_PATHS = [
  /^\/api\/auth\/session$/,
  /^\/api\/nodes(\/|\?|$)/,
  /^\/api\/actions$/,
  /^\/api\/mail\/(accounts|later|unsent|drafts)$/,
  /^\/api\/mail\/folders\/(\d+|flagged)\/messages(\?sort=[a-z]+&descending=[01])?$/,
  /^\/api\/mail\/messages\/\d+\?zone=[^&]+$/,
  /^\/api\/mail\/messages\/\d+\/draft\?as=(reply|all|forward)$/,
];

function flagged(): boolean {
  try {
    return localStorage.getItem(FLAG) === 'on';
  } catch {
    return false;
  }
}

let on = flagged();
const listeners = new Set<() => void>();

function told(): void {
  for (const each of listeners) each();
}

export function subscribeKeeping(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Whether this device is marked to work without the network. */
export function keeping(): boolean {
  return on;
}

export function setKeeping(next: boolean): void {
  try {
    if (next) localStorage.setItem(FLAG, 'on');
    else localStorage.removeItem(FLAG);
  } catch {
    // A browser that keeps no storage keeps nothing either; the flag lives on in this page.
  }
  on = next;
  told();
}

let database: Promise<IDBDatabase> | null = null;

function opened(): Promise<IDBDatabase> {
  database ??= new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 2);
    request.onupgradeneeded = () => {
      for (const name of [ANSWERS, MARKS, OUTBOX])
        if (!request.result.objectStoreNames.contains(name)) request.result.createObjectStore(name);
    };
    request.onsuccess = () => {
      // Emptying the device deletes the database, which waits for every connection to close.
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = () => reject(request.error);
  });
  return database;
}

async function stored<T>(
  name: string,
  mode: IDBTransactionMode,
  asked: (store: IDBObjectStore) => IDBRequest,
): Promise<T> {
  const store = (await opened()).transaction(name, mode).objectStore(name);
  return new Promise((resolve, reject) => {
    const request = asked(store);
    request.onsuccess = () => resolve(request.result as T);
    request.onerror = () => reject(request.error);
  });
}

interface Answer {
  body: unknown;
  at: number;
}

/** Whether the answer is one a marked device keeps: a folder that keeps what it holds in the
 * browser (D20) is never kept, nor what lies under it. */
function keepable(path: string, body: unknown): boolean {
  if (!KEPT_PATHS.some((pattern) => pattern.test(path))) return false;
  return !(body && typeof body === 'object' && (body as { confined?: boolean }).confined);
}

/** Keeps the server's answer to a read, or lets go of the one kept when the answer may no longer
 * be kept. */
export async function keepAnswer(path: string, body: unknown): Promise<void> {
  if (!on || !KEPT_PATHS.some((pattern) => pattern.test(path))) return;
  await stored(
    ANSWERS,
    'readwrite',
    keepable(path, body)
      ? (store) => store.put({ body, at: Date.now() } satisfies Answer, path)
      : (store) => store.delete(path),
  );
}

/** The answer kept for a read, while the server cannot be reached. */
export async function keptAnswer(path: string): Promise<{ body: unknown } | null> {
  if (!on) return null;
  const answer = await stored<Answer | undefined>(ANSWERS, 'readonly', (store) => store.get(path));
  return answer ? { body: answer.body } : null;
}

/** The reads among `paths` whose answers are kept, each kept anew as of now. */
export async function keptAgain(paths: string[]): Promise<Set<string>> {
  const store = (await opened()).transaction(ANSWERS, 'readwrite').objectStore(ANSWERS);
  const held = new Set<string>();
  await Promise.all(
    paths.map(
      (path) =>
        new Promise<void>((resolve, reject) => {
          const request = store.get(path);
          request.onsuccess = () => {
            const answer = request.result as Answer | undefined;
            if (answer) {
              held.add(path);
              store.put({ ...answer, at: Date.now() } satisfies Answer, path);
            }
            resolve();
          };
          request.onerror = () => reject(request.error);
        }),
    ),
  );
  return held;
}

/** Lets go of the answers no pass since `since` kept again: those of the mail, or all the rest. */
export async function forgetAnswersBefore(since: number, mail: boolean): Promise<void> {
  const store = (await opened()).transaction(ANSWERS, 'readwrite').objectStore(ANSWERS);
  await new Promise<void>((resolve, reject) => {
    const cursor = store.openCursor();
    cursor.onsuccess = () => {
      const at = cursor.result;
      if (!at) return resolve();
      const ours = String(at.key).startsWith(MAIL) === mail;
      if (ours && (at.value as Answer).at < since) at.delete();
      at.continue();
    };
    cursor.onerror = () => reject(cursor.error);
  });
}

/** Where the files the recent mail carries are kept, by the path each is read from. */
export function keptParts(): Promise<Cache> {
  return caches.open(PARTS);
}

/** The file a kept message carries, while the server cannot be reached. */
export async function keptPart(path: string): Promise<Blob | null> {
  if (!on) return null;
  const found = await (await keptParts()).match(path);
  return found ? found.blob() : null;
}

/** A message written without the network (D45): what the composer would have sent or kept
 * as unsent, waiting for the server to be reached again. `key` names it to the server, which
 * makes it once however often it is handed over. */
export interface Queued {
  key: string;
  message: Record<string, unknown> & { to: unknown[]; cc: unknown[]; subject: string };
  /** The unsent message the server keeps of it, where there was one before the network went. */
  unsent?: number;
  /** Whether it was sent rather than closed unfinished, and when it was asked to leave. */
  send: boolean;
  at?: string;
  written: number;
  /** Why the server refused it once reached; it stays until the user sends it again or lets it
   * go. */
  failed?: string;
}

const queueListeners = new Set<() => void>();

export function subscribeQueue(listener: () => void): () => void {
  queueListeners.add(listener);
  return () => queueListeners.delete(listener);
}

function queueTold(): void {
  for (const each of queueListeners) each();
}

export async function queue(entry: Queued): Promise<void> {
  await stored(OUTBOX, 'readwrite', (store) => store.put(entry, entry.key));
  queueTold();
}

export async function queued(): Promise<Queued[]> {
  if (!on) return [];
  const all = await stored<Queued[]>(OUTBOX, 'readonly', (store) => store.getAll());
  return all.sort((a, b) => a.written - b.written);
}

export async function dequeue(key: string): Promise<void> {
  if (!on) return;
  await stored(OUTBOX, 'readwrite', (store) => store.delete(key));
  queueTold();
}

/** The documents the user marked to keep on this device. */
export async function marks(): Promise<string[]> {
  if (!on) return [];
  return stored<string[]>(MARKS, 'readonly', (store) => store.getAllKeys());
}

export async function mark(ids: string[], kept: boolean): Promise<void> {
  const store = (await opened()).transaction(MARKS, 'readwrite').objectStore(MARKS);
  for (const id of ids) {
    if (kept) store.put(true, id);
    else store.delete(id);
  }
  await new Promise<void>((resolve, reject) => {
    store.transaction.oncomplete = () => resolve();
    store.transaction.onerror = () => reject(store.transaction.error);
  });
}

/** Keeps a room's state in the browser beside its socket, so it opens without the network and
 * what was written meanwhile joins the room once the socket is back. */
export function keptRoom(room: string, doc: Y.Doc): IndexeddbPersistence | null {
  return on ? new IndexeddbPersistence(`${ROOM}${room}`, doc) : null;
}

async function keptRooms(): Promise<string[]> {
  return (await indexedDB.databases())
    .map(({ name }) => name ?? '')
    .filter((name) => name.startsWith(ROOM))
    .map((name) => name.slice(ROOM.length));
}

function deleted(name: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    // A room open in an editor goes once the editor closes; nothing waits for it.
    request.onblocked = () => resolve();
  });
}

/** Lets go of the rooms that are not among those kept. */
export async function forgetRoomsBut(rooms: Set<string>): Promise<void> {
  await Promise.all(
    (await keptRooms()).filter((room) => !rooms.has(room)).map((room) => deleted(`${ROOM}${room}`)),
  );
}

/** Empties the device: signing out, ending it in the list of devices or taking its mark off. */
export async function empty(): Promise<void> {
  setKeeping(false);
  const closing = database;
  database = null;
  (await closing?.catch(() => null))?.close();
  await Promise.all([
    deleted(DATABASE),
    ...(await keptRooms()).map((room) => deleted(`${ROOM}${room}`)),
    caches.delete(SHELL),
    caches.delete(PARTS),
  ]);
  queueTold();
}
