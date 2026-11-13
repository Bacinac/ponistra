import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { HardDriveDownload, HardDriveUpload } from 'lucide-react';
import { useEffect, useSyncExternalStore } from 'react';
import * as Y from 'yjs';
import { answered, ApiError, getFreshJson, patchJson, postJson, putJson, unavailable } from './api';
import { useI18n } from './i18n';
import {
  dequeue,
  empty,
  forgetAnswersBefore,
  forgetRoomsBut,
  keepAnswer,
  keeping,
  keptAgain,
  keptAnswer,
  keptParts,
  mark,
  marks,
  queue,
  queued,
  type Queued,
  setKeeping,
  SHELL,
  subscribeKeeping,
} from './kept';
import { hear, reachable, useReachable } from './live';
import { type Accounts, draftPath, listPath, messagePath, storedMailSort } from './mailData';
import { MenuItem } from './menu';
import { joinRoom } from './room';
import type { FoundNode, ListedNode, Placement } from './tree';

/** Whether this device is marked to work without the network (D45). */
export function useKeeping(): boolean {
  return useSyncExternalStore(subscribeKeeping, keeping);
}

const ROOTS = [
  '/api/nodes',
  '/api/nodes/company',
  '/api/nodes/shared',
  '/api/nodes/shared?by=me',
  '/api/nodes/favourites',
];
const PARALLEL = 4;
const ROOM_WAIT = 20_000;
// A change heard while the device keeps waits this long for the ones that follow it.
const SETTLE = 60_000;
const PASSED = 'ponistra.offline.passed';
// The mail kept: what came or left in the last month, the latest first, and the files it carries
// up to the size of a common attachment limit.
const RECENT = 30 * 24 * 60 * 60 * 1000;
const MOST_MESSAGES = 200;
const LARGEST_PART = 25 * 1024 * 1024;
const WAYS = ['reply', 'all', 'forward'] as const;
const PART = /\/api\/mail\/messages\/\d+\/parts\/[\w.-]+/g;

export interface Pass {
  /** When the device last kept everything, as `Date.now()` gave it. */
  at: number | null;
  failed: string | null;
  running: boolean;
}

function passedAt(): number | null {
  try {
    return Number(localStorage.getItem(PASSED)) || null;
  } catch {
    return null;
  }
}

let pass: Pass = { at: passedAt(), failed: null, running: false };
const passListeners = new Set<() => void>();

function passed(next: Partial<Pass>): void {
  pass = { ...pass, ...next };
  if (next.at) {
    try {
      localStorage.setItem(PASSED, String(next.at));
    } catch {
      // The time shows in this page alone.
    }
  }
  for (const each of passListeners) each();
}

function subscribePass(listener: () => void): () => void {
  passListeners.add(listener);
  return () => passListeners.delete(listener);
}

export function usePass(): Pass {
  return useSyncExternalStore(subscribePass, () => pass);
}

async function each<T>(items: T[], work: (item: T) => Promise<void>): Promise<void> {
  let next = 0;
  await Promise.all(
    Array.from({ length: Math.min(PARALLEL, items.length) }, async () => {
      while (next < items.length) await work(items[next++]);
    }),
  );
}

interface Listing {
  confined?: boolean;
  children: ListedNode[];
}

/** Reads every folder the user reaches, so the tree is kept; a folder that keeps what it holds in
 * the browser (D20) is never read through. */
async function walkTree(): Promise<void> {
  const seen = new Set<string>();
  let folders: string[] = [];
  const found = (listing: Listing) => {
    if (listing.confined) return;
    for (const child of listing.children) {
      if (child.kind !== 'folder' || child.kept || seen.has(child.id)) continue;
      seen.add(child.id);
      folders.push(child.id);
    }
  };
  await each(ROOTS, async (path) => found(await getFreshJson<Listing>(path)));
  while (folders.length > 0) {
    const level = folders;
    folders = [];
    await each(level, async (id) => found(await getFreshJson<Listing>(`/api/nodes?parent=${id}`)));
  }
}

/** Joins the room until it has synced, which keeps its state in the browser. */
function keptRoomNow(room: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const doc = new Y.Doc();
    const joined = joinRoom(room, doc, () => {}, true);
    const left = (error?: Error) => {
      clearTimeout(timer);
      joined.leave();
      doc.destroy();
      if (error) reject(error);
      else resolve();
    };
    const timer = setTimeout(() => left(new Error(`room ${room} did not sync`)), ROOM_WAIT);
    joined.provider.on('sync', (synced: boolean) => synced && left());
  });
}

/** The rooms of the documents opened lately and of those the user marked; a mark on a document
 * the user no longer reaches is taken off. */
async function keptRooms(): Promise<Set<string>> {
  const recent = await getFreshJson<{ items: FoundNode[] }>('/api/nodes/recent');
  const ids = new Set([
    ...recent.items.filter((node) => node.kind === 'document').map((node) => node.id),
    ...(await marks()),
  ]);
  const rooms = new Set<string>();
  const gone: string[] = [];
  await each([...ids], async (id) => {
    let placed: Placement;
    try {
      placed = await getFreshJson<Placement>(`/api/nodes/${id}`);
    } catch (error) {
      if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
        gone.push(id);
        return;
      }
      throw error;
    }
    if (placed.confined || placed.node.kind !== 'document' || placed.node.trashed_at) return;
    for (const room of [placed.room, ...placed.tabs.map((tab) => tab.room)])
      if (room) rooms.add(room);
  });
  if (gone.length > 0) await mark(gone, false);
  return rooms;
}

/** Keeps the whole app by the list its build makes, so every page opens without the network. */
async function keepShell(): Promise<void> {
  if (import.meta.env.DEV) return;
  await navigator.serviceWorker.register('/sw.js');
  const listed = await fetch('/assets.json', { cache: 'no-store' });
  if (!listed.ok) throw new Error(`/assets.json: HTTP ${listed.status}`);
  const assets = (await listed.json()) as string[];
  const cache = await caches.open(SHELL);
  const held = new Set((await cache.keys()).map((request) => new URL(request.url).pathname));
  await each(
    assets.filter((asset) => !held.has(asset)),
    (asset) => cache.add(asset),
  );
  const page = await fetch('/', { cache: 'no-store' });
  if (!page.ok) throw new Error(`/: HTTP ${page.status}`);
  await cache.put('/', page);
  const wanted = new Set([...assets, '/']);
  await Promise.all(
    (await cache.keys())
      .filter((request) => !wanted.has(new URL(request.url).pathname))
      .map((request) => cache.delete(request)),
  );
}

interface MailPage {
  messages: { id: number; date: string }[];
}

interface OpenedMail {
  attachments: { part: string; size: number }[];
  html: string | null;
}

/** Keeps a message as the reader opens it, without it counting as opened by its user. */
async function openedMail(id: number, held: Set<string>): Promise<OpenedMail | null> {
  const path = messagePath(id);
  if (held.has(path)) {
    const kept = await keptAnswer(path);
    if (kept) return kept.body as OpenedMail;
  }
  try {
    const opened = await getFreshJson<OpenedMail>(`${path}&kept=1`);
    await keepAnswer(path, opened);
    return opened;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Keeps the files of the recent mail, and lets go of those no longer among them. */
async function keepParts(paths: Set<string>): Promise<void> {
  const cache = await keptParts();
  const held = new Set((await cache.keys()).map((request) => new URL(request.url).pathname));
  await each(
    [...paths].filter((path) => !held.has(path)),
    async (path) => {
      const response = await answered(path);
      if (response.ok) await cache.put(path, response);
      else if (response.status !== 404) throw new Error(`${path}: HTTP ${response.status}`);
    },
  );
  await Promise.all(
    (await cache.keys())
      .filter((request) => !paths.has(new URL(request.url).pathname))
      .map((request) => cache.delete(request)),
  );
}

/** Keeps the user's own mail as its pages read it: every folder's first page, the recent
 * messages with their replies begun and the files they carry, and what waits to be sent. */
async function keepMail(): Promise<void> {
  const began = Date.now();
  const accounts = await getFreshJson<Accounts>('/api/mail/accounts');
  await each(['/api/mail/later', '/api/mail/unsent', '/api/mail/drafts'], (path) =>
    getFreshJson(path),
  );
  const sort = storedMailSort();
  const dates = new Map<number, number>();
  await each([...accounts.folders.map((folder) => folder.id), 'flagged' as const], async (id) => {
    const page = await getFreshJson<MailPage>(listPath(id, sort, null));
    for (const message of page.messages) dates.set(message.id, Date.parse(message.date));
  });
  const since = Date.now() - RECENT;
  const recent = [...dates]
    .filter(([, at]) => at >= since)
    .sort((a, b) => b[1] - a[1])
    .slice(0, MOST_MESSAGES)
    .map(([id]) => id);
  const held = await keptAgain(
    recent.flatMap((id) => [messagePath(id), ...WAYS.map((way) => draftPath(id, way))]),
  );
  const parts = new Set<string>();
  await each(recent, async (id) => {
    const opened = await openedMail(id, held);
    if (!opened) return;
    for (const way of WAYS) {
      const path = draftPath(id, way);
      if (!held.has(path)) await getFreshJson(path);
    }
    for (const attachment of opened.attachments)
      if (attachment.size <= LARGEST_PART)
        parts.add(`/api/mail/messages/${id}/parts/${attachment.part}`);
    for (const found of opened.html?.match(PART) ?? []) parts.add(found);
  });
  await keepParts(parts);
  await forgetAnswersBefore(began, true);
}

async function walked(): Promise<void> {
  const began = Date.now();
  await getFreshJson('/api/auth/session');
  await walkTree();
  const rooms = await keptRooms();
  const missed: string[] = [];
  await each([...rooms], (room) =>
    keptRoomNow(room).catch((error: Error) => {
      missed.push(error.message);
    }),
  );
  await keepMail();
  await keepShell();
  if (missed.length > 0) throw new Error(missed.join('; '));
  await forgetAnswersBefore(began, false);
  await forgetRoomsBut(rooms);
}

let running: Promise<void> | null = null;

/** Keeps again what the device keeps, or its mail alone; a pass already running is the one
 * waited for. */
export function keepNow(mail = false): Promise<void> {
  if (!keeping()) return Promise.resolve();
  running ??= (async () => {
    passed({ running: true });
    try {
      await (mail ? keepMail() : walked());
      if (keeping()) passed({ at: Date.now(), failed: null });
    } catch (error) {
      console.error('keeping the device for offline work failed', error);
      passed({ failed: error instanceof Error ? error.message : String(error) });
    } finally {
      running = null;
      passed({ running: false });
    }
  })();
  return running;
}

/** Keeps what the device keeps while the user is signed in on it: at once, when the server is
 * back and a while after the user's data changed. */
export function useKeeper(): void {
  const on = useKeeping();
  useEffect(() => {
    if (!on) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const soon = (wait: number) => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        void keepNow();
      }, wait);
    };
    let mailTimer: ReturnType<typeof setTimeout> | null = null;
    soon(0);
    const leave = hear((areas) => {
      if (areas.includes('*')) soon(0);
      else if (areas.includes('nodes')) soon(SETTLE);
      else if (areas.includes('mail') && !timer && !mailTimer)
        mailTimer = setTimeout(() => {
          mailTimer = null;
          void keepNow(true);
        }, SETTLE);
    });
    return () => {
      leave();
      if (timer) clearTimeout(timer);
      if (mailTimer) clearTimeout(mailTimer);
    };
  }, [on]);
  const reached = useReachable();
  useEffect(() => {
    if (on && reached) void sendQueued();
  }, [on, reached]);
}

const holding = new Set<string>();

/** Keeps the queue from handing over what a composer still has open; once it closes, what it
 * left is handed over. */
export function hold(key: string): () => void {
  holding.add(key);
  return () => {
    holding.delete(key);
    void sendQueued();
  };
}

/** Whether what the user writes waits on this device for the server to be reached again. */
export function queueing(reachable: boolean): boolean {
  return keeping() && !reachable;
}

async function handedOver({ key, message, unsent, send, at }: Queued): Promise<void> {
  const given = { ...message, queued: key };
  const kept = async (pk: number | undefined) => {
    if (send)
      await postJson('/api/mail/later', {
        ...given,
        ...(pk && { unsent: pk }),
        at: at ?? new Date().toISOString(),
      });
    else if (pk) await putJson(`/api/mail/unsent/${pk}`, given);
    else await postJson('/api/mail/unsent', given);
  };
  try {
    await kept(unsent);
  } catch (error) {
    // The unsent message it changed was sent or let go elsewhere meanwhile: it is one of its own.
    if (!unsent || !(error instanceof ApiError && error.status === 404)) throw error;
    await kept(undefined);
  }
}

let sending: Promise<void> | null = null;

/** Hands over to the server what was written while it could not be reached, the oldest first:
 * what was sent leaves through the queue of messages that leave later (D40). */
export function sendQueued(): Promise<void> {
  if (!keeping() || !reachable()) return Promise.resolve();
  sending ??= (async () => {
    try {
      for (const entry of await queued()) {
        if (holding.has(entry.key) || entry.failed) continue;
        try {
          await handedOver(entry);
          await dequeue(entry.key);
        } catch (error) {
          if (unavailable(error)) return;
          console.error('handing over mail written without the network failed', error);
          const failed = error instanceof ApiError ? (error.code ?? 'unexpected') : 'unexpected';
          await queue({ ...entry, failed });
        }
      }
    } finally {
      sending = null;
    }
  })();
  return sending;
}

/** Marks this device to work without the network, or takes the mark off and empties it. */
export function useKeepDevice() {
  return useMutation({
    mutationFn: async (next: boolean) => {
      await patchJson('/api/sessions', { offline: next });
      if (!next) return empty();
      setKeeping(true);
      await keepNow();
    },
  });
}

const MARKS_KEY = ['offline', 'marks'];

/** Keeps the documents on this device whatever was opened lately, or lets them go. */
export function KeepItem({
  nodes,
  confined,
}: {
  nodes: Pick<ListedNode, 'id' | 'kind'>[];
  confined: boolean;
}) {
  const { t } = useI18n();
  const on = useKeeping();
  const queryClient = useQueryClient();
  const documents = nodes.filter((node) => node.kind === 'document').map((node) => node.id);
  const marked = useQuery({
    queryKey: MARKS_KEY,
    queryFn: async () => new Set(await marks()),
    enabled: on,
  });
  const change = useMutation({
    mutationFn: (kept: boolean) => mark(documents, kept),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: MARKS_KEY });
      void keepNow();
    },
  });
  if (!on || documents.length === 0 || documents.length !== nodes.length) return null;
  const all = marked.data !== undefined && documents.every((id) => marked.data.has(id));
  return (
    <MenuItem
      icon={all ? HardDriveUpload : HardDriveDownload}
      label={t(all ? 'offline.unmark' : 'offline.mark')}
      disabled={confined || !marked.isSuccess || change.isPending}
      hint={confined ? t('confined.hint') : undefined}
      onSelect={() => change.mutate(!all)}
    />
  );
}
