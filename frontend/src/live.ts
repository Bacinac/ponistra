import { useEffect, useSyncExternalStore } from 'react';
import { heardRelease } from './release';

/** A colleague ringing the user into a meeting. */
export interface Ringing {
  id: number;
  meeting: string;
  title: string;
  by: string;
  /** The seconds it rings for once this state came. */
  left: number;
}

/** A ring the user made lately; unanswered with no seconds left, it stopped. */
export interface Rung {
  id: number;
  meeting: string;
  name: string;
  address: string;
  answer: '' | 'joined' | 'declined';
  left: number;
}

/** A conversation the user is in, with its last message and how many of the others' they have
    not read: a meeting's once someone has written to it, one started from people from its start. */
export interface Summary {
  id: string;
  kind: 'meeting' | 'direct' | 'group' | 'channel';
  title: string;
  removable: boolean;
  private: boolean;
  /** Everyone in it but the user, which names one without a title. */
  people: string[];
  /** Those of them with Ponistra open right now. */
  online: string[];
  unread: number;
  /** Unread messages that name the user, all that counts of a channel. */
  mentions: number;
  /** Unread replies in the threads the user follows. */
  threads: number;
  /** When a message was last written, edited or taken back. */
  changed: string;
  last: {
    id: number;
    by: string;
    text: string;
    at: string;
    files: number;
    meeting: boolean;
  } | null;
}

/** What waits for the user in a conversation, on its row and on the rail. */
export function waitingIn(summary: Summary): number {
  return summary.kind === 'channel' ? summary.mentions + summary.threads : summary.unread;
}

/** A guest waiting at the door of a meeting the user is in (S2-2). */
export interface Waiting {
  id: number;
  meeting: string;
  name: string;
}

export interface Live {
  ringing: Ringing[];
  rung: Rung[];
  lobby: Waiting[];
  /** The latest written to first. */
  conversations: Summary[];
  release: string;
  /** When the state came, as `Date.now()` gives it. */
  at: number;
}

const RECONNECT_FIRST = 500;
const RECONNECT_MOST = 10_000;
const REFUSED = 4403;
const NONE: Live = { ringing: [], rung: [], lobby: [], conversations: [], release: '', at: 0 };

/** Takes the areas of the user's data that changed on the server; `*` is every area. */
export type Heard = (areas: string[]) => void;

let state = NONE;
let socket: WebSocket | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
let wait = RECONNECT_FIRST;
let lost = false;
const listeners = new Set<() => void>();
const hearing = new Set<Heard>();
const reaching = new Set<() => void>();
let reached = true;

function reach(next: boolean): void {
  if (reached === next) return;
  reached = next;
  for (const each of reaching) each();
}

function heard(areas: string[]): void {
  for (const each of hearing) each(areas);
}

function connect(): void {
  timer = null;
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const opened = new WebSocket(`${scheme}//${location.host}/api/live`);
  socket = opened;
  opened.addEventListener('open', () => {
    wait = RECONNECT_FIRST;
    reach(true);
    // What changed while the socket was lost was told to no one.
    if (lost) heard(['*']);
    lost = false;
  });
  opened.addEventListener('message', (event) => {
    const { type, ...given } = JSON.parse(event.data as string);
    if (socket !== opened) return;
    if (type === 'changed') heard((given as { areas: string[] }).areas);
    if (type !== 'state') return;
    state = { ...(given as Omit<Live, 'at'>), at: Date.now() };
    heardRelease(state.release);
    for (const each of listeners) each();
  });
  opened.addEventListener('close', ({ code }) => {
    if (socket !== opened) return;
    socket = null;
    lost = true;
    // Refused, the tab has no one signed in, as a guest at a meeting's door or the sign-in page:
    // the server answered, and the socket is asked for again for when someone signs in.
    reach(code === REFUSED);
    timer = setTimeout(connect, wait);
    wait = Math.min(wait * 2, RECONNECT_MOST);
  });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (listeners.size === 1) connect();
  return () => {
    listeners.delete(listener);
    if (listeners.size > 0) return;
    if (timer) clearTimeout(timer);
    timer = null;
    const closing = socket;
    socket = null;
    state = NONE;
    wait = RECONNECT_FIRST;
    lost = false;
    reach(true);
    if (closing?.readyState === WebSocket.CONNECTING) {
      closing.addEventListener('open', () => closing.close(), { once: true });
    } else closing?.close();
  };
}

/** What the signed-in user hears as it happens, over one socket a tab (`/api/live`). */
export function useLive(): Live {
  return useSyncExternalStore(subscribe, () => state);
}

/** Calls `told` with the areas of the user's data that changed on the server, by another tab or
    device, a sync or a colleague, until the function it answers is called; `['*']` once the
    socket is back after it was lost. */
export function hear(told: Heard): () => void {
  hearing.add(told);
  const leave = subscribe(() => {});
  return () => {
    hearing.delete(told);
    leave();
  };
}

/** Calls `told` with the areas of the user's data that changed on the server, by another tab or
    device, a sync or a colleague, while the tab holds the socket open. */
export function useChanges(told: Heard): void {
  useEffect(() => hear(told), [told]);
}

function subscribeReach(listener: () => void): () => void {
  reaching.add(listener);
  const leave = subscribe(() => {});
  return () => {
    reaching.delete(listener);
    leave();
  };
}

/** Whether the server can be reached, as `useReachable` says it. */
export function reachable(): boolean {
  return reached;
}

/** Whether the server can be reached: false from the moment the tab's socket is lost until it is
    back, so what needs the server is disabled rather than refused after a try (D45). */
export function useReachable(): boolean {
  return useSyncExternalStore(subscribeReach, () => reached);
}
