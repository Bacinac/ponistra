import { useSyncExternalStore } from 'react';
import { deleteJson, getJson, postJson } from './api';

/** A browser the user let notifications reach. */
export interface Subscribed {
  id: number;
  agent: string;
  language: string;
  created_at: string;
  used_at: string | null;
  current: boolean;
}

export interface PushState {
  key: string;
  on: boolean;
  subscriptions: Subscribed[];
}

interface InstallPrompt extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

interface Install {
  /** The browser offers to install the app, and `install` asks it to. */
  offered: boolean;
  /** The app runs as installed, in a window of its own. */
  installed: boolean;
}

export const pushWorks =
  'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

export const onIos = /iPhone|iPad|iPod/.test(navigator.userAgent);

const STANDALONE = '(display-mode: standalone)';

let prompt: InstallPrompt | null = null;
let install: Install = { offered: false, installed: false };
const listeners = new Set<() => void>();
let worker: Promise<ServiceWorkerRegistration> | null = null;

function changed(next: Partial<Install>): void {
  install = { ...install, ...next };
  for (const each of listeners) each();
}

/** Registers the service worker and catches the browser's offer to install the app; once, before
    the browser makes the offer. */
export function installPush(): void {
  install = { ...install, installed: matchMedia(STANDALONE).matches };
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    prompt = event as InstallPrompt;
    changed({ offered: true });
  });
  window.addEventListener('appinstalled', () => {
    prompt = null;
    changed({ offered: false, installed: true });
  });
  if (!('serviceWorker' in navigator)) return;
  worker = navigator.serviceWorker.register('/sw.js');
  worker.catch((error: unknown) => {
    console.error('The service worker did not register', error);
  });
}

function subscribeInstall(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useInstall(): Install {
  return useSyncExternalStore(subscribeInstall, () => install);
}

export async function askToInstall(): Promise<void> {
  if (!prompt) return;
  const asked = prompt;
  prompt = null;
  changed({ offered: false });
  await asked.prompt();
  if ((await asked.userChoice).outcome !== 'accepted') changed({ offered: true });
}

async function ready(): Promise<ServiceWorkerRegistration> {
  if (!worker) throw new Error('The service worker is not registered');
  await worker;
  return navigator.serviceWorker.ready;
}

/** This browser's subscription, if it made one. */
export async function current(): Promise<PushSubscription | null> {
  if (!pushWorks) return null;
  return (await ready()).pushManager.getSubscription();
}

function keyBytes(key: string): Uint8Array<ArrayBuffer> {
  const padded = key + '='.repeat((4 - (key.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

function sameKey(subscription: PushSubscription, key: string): boolean {
  const held = subscription.options.applicationServerKey;
  if (!held) return false;
  const bytes = new Uint8Array(held);
  const wanted = keyBytes(key);
  return bytes.length === wanted.length && bytes.every((byte, i) => byte === wanted[i]);
}

async function kept(subscription: PushSubscription, language: string): Promise<void> {
  await postJson('/api/push/subscriptions', { ...subscription.toJSON(), language });
}

/** Asks the user's leave, subscribes with the installation's key and tells the backend; the
    permission the browser gave. */
export async function subscribe(key: string, language: string): Promise<NotificationPermission> {
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return permission;
  const manager = (await ready()).pushManager;
  let subscription = await manager.getSubscription();
  if (subscription && !sameKey(subscription, key)) {
    await subscription.unsubscribe();
    subscription = null;
  }
  subscription ??= await manager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: keyBytes(key),
  });
  await kept(subscription, language);
  return permission;
}

export async function unsubscribe(): Promise<void> {
  const subscription = await current();
  if (!subscription) return;
  const state = await getJson<PushState>(
    `/api/push?endpoint=${encodeURIComponent(subscription.endpoint)}`,
  );
  const mine = state.subscriptions.find((each) => each.current);
  if (mine) await deleteJson(`/api/push/subscriptions/${mine.id}`);
  await subscription.unsubscribe();
}

/** Keeps the backend's copy of this browser's subscription current each time the app opens, in
    the language read now; a browser removed from the user's list elsewhere lets go of its
    subscription. */
export async function renew(language: string): Promise<void> {
  if (!pushWorks || Notification.permission !== 'granted') return;
  const subscription = await current();
  if (!subscription) return;
  const state = await getJson<PushState>(
    `/api/push?endpoint=${encodeURIComponent(subscription.endpoint)}`,
  );
  if (state.subscriptions.some((each) => each.current)) await kept(subscription, language);
  else await subscription.unsubscribe();
}
