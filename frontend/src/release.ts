import { useEffect } from 'react';
import { getJson, type Revision } from './api';

const RELOADED = 'ponistra.reloaded';
const AGAIN_AFTER = 10_000;
const TRIES = 30;
const RETRY = 2_000;

let came: string | undefined;
let outdated = false;
let holds = 0;
const typed = new Set<HTMLElement>();
const WRITTEN = new Set(['text', 'search', 'email', 'url', 'tel', 'number', 'password']);

function written(target: EventTarget | null): target is HTMLElement {
  if (target instanceof HTMLTextAreaElement) return true;
  if (target instanceof HTMLInputElement) return WRITTEN.has(target.type);
  return target instanceof HTMLElement && target.isContentEditable;
}

/** What the user typed and has not sent: a field they wrote in that still holds text. */
function unsent(): boolean {
  for (const field of typed) {
    if (!field.isConnected) {
      typed.delete(field);
      continue;
    }
    const text =
      field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement
        ? field.value
        : field.textContent;
    if (text?.trim()) return true;
  }
  return false;
}

function playing(): boolean {
  return [...document.querySelectorAll('audio, video')].some(
    (media) => !(media as HTMLMediaElement).paused,
  );
}

function takeable(): boolean {
  return outdated && holds === 0 && !unsent() && !playing();
}

/** A page reloaded in a loop would never show the error that keeps it from loading. */
export function reloadOnce(): void {
  if (Date.now() - Number(sessionStorage.getItem(RELOADED)) < AGAIN_AFTER) return;
  sessionStorage.setItem(RELOADED, String(Date.now()));
  location.reload();
}

/** Takes the release the server says it runs: the first is the one this page came with. */
export function heardRelease(release: string): void {
  if (!release) return;
  came ??= release;
  outdated = release !== came;
  if (document.hidden && takeable()) reloadOnce();
}

export function cameWith(): string | undefined {
  return came;
}

/** Called as the user goes to another page and as the page goes out of sight, when it has
 * nothing to lose: a page that stays open, as Projects in its own window, never goes to another. */
export function takeNewRelease(): void {
  if (takeable()) reloadOnce();
}

/** Notes the fields the user writes in, and takes a new release as the page goes out of sight. */
export function followPage(): () => void {
  const wrote = (event: Event) => {
    if (written(event.target)) typed.add(event.target);
  };
  const seen = () => {
    if (document.hidden) takeNewRelease();
  };
  document.addEventListener('input', wrote, true);
  document.addEventListener('visibilitychange', seen);
  return () => {
    document.removeEventListener('input', wrote, true);
    document.removeEventListener('visibilitychange', seen);
  };
}

/** After a crash the socket is gone with the page, and the server may still be coming up. */
export function recoverFromCrash(tries = TRIES): void {
  if (came === undefined) return;
  getJson<Revision>('/api/version').then(
    ({ version }) => {
      if (version !== came) reloadOnce();
    },
    () => {
      if (tries > 1) setTimeout(() => recoverFromCrash(tries - 1), RETRY);
    },
  );
}

/** Keeps the page from taking a new release while `busy`: work that goes on across pages. */
export function useHeldRelease(busy: boolean): void {
  useEffect(() => {
    if (!busy) return;
    holds += 1;
    return () => {
      holds -= 1;
    };
  }, [busy]);
}
