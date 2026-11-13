import { useEffect } from 'react';
import { useNavigate } from 'react-router';

// The Window Management API, which TypeScript's DOM library does not describe yet.
interface ScreenDetailed extends Screen {
  readonly availLeft: number;
  readonly availTop: number;
}
interface ScreenDetails extends EventTarget {
  readonly screens: readonly ScreenDetailed[];
  readonly currentScreen: ScreenDetailed;
}
declare global {
  interface Window {
    getScreenDetails?: () => Promise<ScreenDetails>;
  }
  interface Screen {
    readonly isExtended?: boolean;
  }
  interface FullscreenOptions {
    screen?: ScreenDetailed;
  }
}

const NAMED = 'ponistra-meeting-';

/** The screens, once the user has let the app place windows on them. */
let screens: ScreenDetails | undefined;

async function placing() {
  if (!window.getScreenDetails) return;
  const allowed = await navigator.permissions.query({
    name: 'window-management' as PermissionName,
  });
  const taken = async () => {
    screens = allowed.state === 'granted' ? await window.getScreenDetails?.() : undefined;
  };
  // Allowed in the meeting's own window, the app's window places the next one too.
  allowed.addEventListener('change', () => void taken());
  await taken();
}
void placing();

/** Whether the computer has more than one screen to move a meeting between. */
export function hasScreens(): boolean {
  return !!window.getScreenDetails && !!screen.isExtended;
}

/** Filling the largest screen other than the app's, where the user let the app place windows;
    otherwise over the app's window. */
function features(): string {
  const current = screens?.currentScreen;
  const other = screens?.screens
    .filter((each) => each !== current)
    .sort((a, b) => b.availWidth * b.availHeight - a.availWidth * a.availHeight)[0];
  if (other)
    return `popup,left=${other.availLeft},top=${other.availTop},width=${other.availWidth},height=${other.availHeight}`;
  const width = Math.min(1280, screen.availWidth);
  const height = Math.min(860, screen.availHeight);
  const left = Math.round(window.screenX + (window.outerWidth - width) / 2);
  const top = Math.round(window.screenY + (window.outerHeight - height) / 2);
  return `popup,left=${left},top=${top},width=${width},height=${height}`;
}

/** Shows the app's page at `path` in a window opened beside the app and brings it forward; a
    window already on that page keeps it, a meeting its call. */
function shown(beside: Window, path: string) {
  if (beside.location.pathname !== new URL(path, location.origin).pathname)
    beside.location.href = path;
  beside.focus();
}

/** A page of the app in the window of that name beside it, placed as a meeting's; false where
    the browser keeps it from opening. */
export function openBeside(name: string, path: string): boolean {
  const beside = window.open('', name, features());
  if (!beside) return false;
  shown(beside, path);
  return true;
}

/** A meeting's page in a window of its own, readied while the click still lets one open. */
export interface MeetingWindow {
  go: (path: string) => void;
  close: () => void;
}

/** A meeting opens beside the app on a computer, so that the work goes on during the call; on a
    phone it opens here, and where the browser keeps the window from opening, here saying so. */
export function useMeetingWindow(): {
  open: (path: string) => void;
  ready: () => MeetingWindow;
} {
  const navigate = useNavigate();
  const ready = (name: string): MeetingWindow => {
    const stays = () => undefined;
    if (!matchMedia('(pointer: fine)').matches)
      return { go: (path) => void navigate(path), close: stays };
    const beside = window.open('', name, features());
    if (!beside)
      return { go: (path) => void navigate(path, { state: { blocked: true } }), close: stays };
    return { go: (path) => shown(beside, path), close: () => beside.close() };
  };
  return {
    open: (path) => {
      const id = new URL(path, location.origin).pathname.split('/')[2];
      ready(`${NAMED}${id === 'new' ? crypto.randomUUID() : id}`).go(path);
    },
    ready: () => ready(`${NAMED}${crypto.randomUUID()}`),
  };
}

/** Names the window a meeting is in after it, so that joining it again finds that window. */
export function useMeetingName(id: string) {
  useEffect(() => {
    if (id === 'new') return;
    const before = window.name;
    window.name = `${NAMED}${id}`;
    return () => {
      window.name = before;
    };
  }, [id]);
}

/** Whether the page is in a window of its own beside the app, a meeting's or the Projects', which
    closes rather than going back. */
export function isBeside(): boolean {
  return window.opener !== null;
}

/** Moves the page to the next screen: its own window moves there and fills it, as a browser
    moves only the windows a page opened; a tab fills it in full screen. */
export async function toNextScreen(): Promise<void> {
  const details = await window.getScreenDetails?.();
  if (!details) return;
  const all = details.screens;
  const next = all[(all.indexOf(details.currentScreen) + 1) % all.length];
  if (isBeside()) {
    window.moveTo(next.availLeft, next.availTop);
    window.resizeTo(next.availWidth, next.availHeight);
  } else await document.documentElement.requestFullscreen({ screen: next });
}
