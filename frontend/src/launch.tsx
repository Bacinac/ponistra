import { useEffect, useEffectEvent, useRef, useState, type ReactNode } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';
import { csrfToken, postBytes, postJson } from './api';
import { useI18n } from './i18n';
import { answerOf } from './jobs';
import { button } from './styles';
import { errorMessage, nodeHref, type TreeNode } from './tree';
import { loose, useUploads } from './upload';

// The Launch Handler and File Handling APIs, which TypeScript's DOM library does not describe yet.
interface LaunchParams {
  readonly targetURL?: string;
  readonly files: readonly FileSystemFileHandle[];
}
declare global {
  interface Window {
    launchQueue?: { setConsumer(consumer: (params: LaunchParams) => void): void };
  }
}

/** What a launch of the installed app asks for: the address it leads to and the files it opens. */
export interface Launch {
  target?: string;
  files: File[];
}

const CHANNEL = 'ponistra-launch';
/** Held by the main window that takes what a launch into another window of the app asks. */
const LEAD = 'ponistra-main';
const LEADING = 'leading';

/** The name of a window a file opened from the computer is read in, before its key, and the
 * channel that window asks the one holding the file for it. */
const OPENED = 'ponistra-opened:';

/** Whether this window is one a file opened from the computer is read in, alone across it. */
export function isAlone(): boolean {
  return window.name.startsWith(OPENED);
}

/** The files this window holds for the windows it opened to read them in, by their keys. */
const handing = new Map<string, File>();
type Handing = { want: string } | { took: string } | { key: string; file: File };

const waiting: Launch[] = [];
/** Takes a launch, or declines it to leave it waiting. */
let taker: ((launch: Launch) => boolean) | null = null;

// Set once for the page: the browser hands a consumer each launch only once, and one that comes
// while no window takes it, signed out or before the app has drawn, waits for the next that does.
window.launchQueue?.setConsumer(async ({ targetURL, files }) => {
  const launch = {
    target: targetURL,
    files: await Promise.all(files.map((each) => each.getFile())),
  };
  if (!taker?.(launch)) waiting.push(launch);
});

/** `take` returns false for a launch it leaves to wait for the next taker. */
function useLaunches(take: (launch: Launch) => boolean | void) {
  const taken = useEffectEvent(take);
  useEffect(() => {
    const mine = (launch: Launch) => taken(launch) !== false;
    taker = mine;
    waiting.push(...waiting.splice(0).filter((launch) => !mine(launch)));
    return () => {
      if (taker === mine) taker = null;
    };
  }, []);
}

function told(message: Launch | typeof LEADING) {
  const channel = new BroadcastChannel(CHANNEL);
  channel.postMessage(message);
  channel.close();
}

async function led(): Promise<boolean> {
  return Boolean((await navigator.locks.query()).held?.some((lock) => lock.name === LEAD));
}

/** Whether a launch opens only PDF files, which the browser shows without the server. */
export function onlyPdfs({ files }: Launch): boolean {
  return (
    files.length > 0 &&
    files.every((file) => file.type === 'application/pdf' || /\.pdf$/i.test(file.name))
  );
}

/** What a browser that opened files while nobody was signed in keeps of them: the key that gives
 * them to whoever signs in from it, and the files. */
const OPENER = 'ponistra-opener';
type Opened = Pick<TreeNode, 'id' | 'kind' | 'title'>;
interface Opener {
  key: string;
  files: Opened[];
}

export function opener(): Opener | null {
  const kept = sessionStorage.getItem(OPENER);
  return kept ? (JSON.parse(kept) as Opener) : null;
}

export function forgetOpener() {
  sessionStorage.removeItem(OPENER);
}

/** Places each file on the server for a visitor this browser becomes, then reads the first in
 * this window, alone. */
async function openedSignedOut(files: File[]): Promise<void> {
  const kept = opener();
  let key = kept?.key ?? '';
  const placed: Opened[] = [...(kept?.files ?? [])];
  for (const file of files) {
    const sent = await postBytes<{ job: string; key?: string }>(
      `/api/opened?${new URLSearchParams({ name: file.name })}`,
      file,
    );
    key = sent.key ?? key;
    const { id, kind, title } = await answerOf<TreeNode>(sent.job, file.name);
    placed.push({ id, kind, title });
  }
  sessionStorage.setItem(OPENER, JSON.stringify({ key, files: placed } satisfies Opener));
  window.name = `${OPENED}signed-out`;
  location.assign(nodeHref(placed[kept?.files.length ?? 0]));
}

interface SignedOutLaunch {
  pdfs: File[];
  closePdfs: () => void;
  /** The files placed on the server meanwhile, and what refused them. */
  opening: { files: File[]; error: Error | null } | null;
  closeOpening: () => void;
}

/** What a launch opens while nobody is signed in: PDF files the browser shows itself, without
 * the server; any other file is placed for a visitor of its own, who only reads it. */
export function useSignedOutLaunch(): SignedOutLaunch {
  const [pdfs, setPdfs] = useState<File[]>([]);
  const [opening, setOpening] = useState<SignedOutLaunch['opening']>(null);
  useLaunches(({ files }) => {
    if (files.length === 0) return false;
    if (onlyPdfs({ files })) return setPdfs(files);
    setOpening({ files, error: null });
    openedSignedOut(files).catch((error: unknown) =>
      setOpening({ files, error: error instanceof Error ? error : new Error(String(error)) }),
    );
  });
  return {
    pdfs,
    closePdfs: () => setPdfs([]),
    opening,
    closeOpening: () => setOpening(null),
  };
}

/** Where a launch leads the window at `here`: nowhere when the window is there already, or when
 * it is the app's own start, which only brings the open window to the front. */
export function ledTo(target: string | undefined, here: string): string | null {
  if (!target) return null;
  const { pathname, search, hash } = new URL(target);
  const to = pathname + search + hash;
  return to === here || to === '/' ? null : to;
}

/** Whether the server answers an address itself, as the app has no page for it. */
export function forTheServer(path: string): boolean {
  return /^\/(api|dav|android|\.well-known)(\/|$)/.test(path);
}

function windowFor(key: string): boolean {
  return window.open(`/opened/${key}`, OPENED + key) !== null;
}

/** Opens each file a launch brings in a window of its own, where it is read alone. A browser
 * that refuses a window the user did not click for keeps the file here, with a button that
 * opens it. */
function useOpening(): [(files: File[]) => void, ReactNode] {
  const { t } = useI18n();
  const [held, setHeld] = useState<{ key: string; name: string }[]>([]);
  useEffect(() => {
    const channel = new BroadcastChannel(OPENED);
    channel.onmessage = ({ data }: MessageEvent<Handing>) => {
      if ('want' in data) {
        const file = handing.get(data.want);
        if (file) channel.postMessage({ key: data.want, file } satisfies Handing);
      } else if ('took' in data) handing.delete(data.took);
    };
    return () => channel.close();
  }, []);
  const open = (files: File[]) => {
    for (const file of files) {
      const key = crypto.randomUUID();
      handing.set(key, file);
      if (!windowFor(key)) setHeld((now) => [...now, { key, name: file.name }]);
    }
  };
  const rows = held.length > 0 && (
    <div role="group" aria-label={t('launch.held')} className="flex flex-col gap-2">
      {held.map(({ key, name }) => (
        <div key={key} className="flex items-center gap-3">
          <p className="min-w-0 flex-1 truncate">{name}</p>
          <button
            type="button"
            onClick={() => {
              if (windowFor(key)) setHeld((now) => now.filter((each) => each.key !== key));
            }}
            className={button}
          >
            {t('launch.window')}
          </button>
        </div>
      ))}
    </div>
  );
  return [open, rows];
}

function LaunchBar({ children }: { children: ReactNode }) {
  return (
    <div
      role="status"
      className="fixed right-4 bottom-4 z-40 flex max-w-[calc(100vw-2rem)] flex-col gap-2 rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink shadow-lg empty:hidden"
    >
      {children}
    </div>
  );
}

/** The window a file opened from the computer is read in: it takes the file from the window
 * that opened it and places it in no folder, then shows it. */
export function OpenedPage() {
  const { t } = useI18n();
  const { key } = useParams();
  const navigate = useNavigate();
  const uploads = useUploads();
  const [name, setName] = useState<string | null>(null);
  const [lost, setLost] = useState(false);
  const take = useEffectEvent((file: File) => {
    setName(file.name);
    uploads.start(
      loose([file]),
      null,
      (placed) => {
        if (placed[0]) void navigate(nodeHref(placed[0]), { replace: true });
      },
      true,
    );
  });
  useEffect(() => {
    if (!key) return;
    const channel = new BroadcastChannel(OPENED);
    // The window that opened this one answers at once while it is open; one closed meanwhile,
    // or reloaded, no longer holds the file.
    const gone = setTimeout(() => setLost(true), 10_000);
    channel.onmessage = ({ data }: MessageEvent<Handing>) => {
      if (!('key' in data) || data.key !== key) return;
      clearTimeout(gone);
      channel.postMessage({ took: key } satisfies Handing);
      channel.close();
      take(data.file);
    };
    channel.postMessage({ want: key } satisfies Handing);
    return () => {
      clearTimeout(gone);
      channel.close();
    };
  }, [key]);
  const failed = uploads.failed[0]?.error ?? uploads.error;
  if (failed) return <p className="text-sm text-danger">{errorMessage(failed, t)}</p>;
  if (lost && !name) return <p className="text-sm text-muted">{t('launch.lost')}</p>;
  return (
    <div className="flex flex-col gap-1 text-sm">
      {name && <p className="font-medium">{name}</p>}
      <p className="text-muted">{t('launch.receiving')}</p>
    </div>
  );
}

/** Any other place of the app a window reading a file alone is led to, from its menus or a link,
 * opens in the main window, or in a new one while none is open; the file stays in sight. */
export function ToMain() {
  const navigate = useNavigate();
  const { pathname, search, hash } = useLocation();
  const handed = useRef(false);
  useEffect(() => {
    if (handed.current) return;
    handed.current = true;
    const to = pathname + search + hash;
    void led().then((leading) => {
      if (!leading) return void window.open(to, '_blank');
      told({ target: window.location.origin + to, files: [] });
      window.opener?.focus();
    });
    if ((window.history.state as { idx?: number } | null)?.idx) void navigate(-1);
    else window.close();
  }, [navigate, pathname, search, hash]);
  return null;
}

/** The main window's part: it opens what a launch asks, each file opened from the computer in a
 * window of its own, and takes what a launch into another window of the app hands it. */
export function Launches() {
  const navigate = useNavigate();
  const [open, held] = useOpening();
  function opened({ target, files }: Launch) {
    if (files.length > 0) return open(files);
    const to = ledTo(target, location.pathname + location.search + location.hash);
    if (!to) return;
    if (forTheServer(to)) location.assign(to);
    else void navigate(to);
  }
  useLaunches(opened);
  const forwarded = useEffectEvent(opened);
  useEffect(() => {
    const leading = new AbortController();
    navigator.locks
      .request(
        LEAD,
        { signal: leading.signal },
        () =>
          new Promise<void>((released) => {
            const channel = new BroadcastChannel(CHANNEL);
            channel.onmessage = ({ data }: MessageEvent<Launch | typeof LEADING>) => {
              if (data !== LEADING) forwarded(data);
            };
            told(LEADING);
            leading.signal.addEventListener('abort', () => {
              channel.close();
              released();
            });
          }),
      )
      .catch((error: unknown) => {
        if (!leading.signal.aborted) throw error;
      });
    return () => leading.abort();
  }, []);
  return <LaunchBar>{held}</LaunchBar>;
}

/** A window a launch never leads away, a meeting's, a presenter's or a file's read alone: it
 * opens the files a launch brings each in a window of its own, hands any other launch to the
 * main window, and while none is open says so and opens one. */
export function LaunchesElsewhere() {
  const { t } = useI18n();
  const [held, setHeld] = useState<Launch[]>([]);
  const [open, opening] = useOpening();
  useLaunches((launch) => {
    if (launch.files.length > 0) return open(launch.files);
    void led().then((leading) => {
      if (!leading) return setHeld((now) => [...now, launch]);
      told(launch);
      window.opener?.focus();
    });
  });
  useEffect(() => {
    if (held.length === 0) return;
    let handed = false;
    const hand = () => {
      if (handed) return;
      handed = true;
      held.forEach(told);
      setHeld([]);
    };
    const channel = new BroadcastChannel(CHANNEL);
    channel.onmessage = ({ data }) => {
      if (data === LEADING) hand();
    };
    // A main window that began to lead before this listened has told it already.
    void led().then((leading) => leading && hand());
    return () => {
      handed = true;
      channel.close();
    };
  }, [held]);
  return (
    <LaunchBar>
      {opening}
      {held.length > 0 && (
        <div className="flex items-center gap-3">
          <p className="min-w-0 flex-1">{t('launch.elsewhere')}</p>
          <button type="button" onClick={() => window.open('/', '_blank')} className={button}>
            {t('launch.open')}
          </button>
        </div>
      )}
    </LaunchBar>
  );
}

/** Whether this window's page has been told where it goes: to a sign-in, which keeps the files
 * for whoever signs in, or closed, which removed them already. */
let leaving = false;

function sendClosed(): Promise<Response> {
  return fetch('/api/opened/closed', {
    method: 'POST',
    headers: { 'X-CSRFToken': csrfToken() },
    keepalive: true,
  });
}

/** Closes the window of files opened while nobody was signed in, once they are removed. */
export async function closeOpened() {
  leaving = true;
  forgetOpener();
  window.name = '';
  await sendClosed();
  window.close();
  location.assign('/');
}

/** Leads to the sign-in, after which whoever signed in takes the files and saves them. */
export async function signInToSave() {
  leaving = true;
  await postJson('/api/auth/logout');
  location.assign('/');
}

/** The part of a window reading files opened while nobody was signed in: another launch's files
 * join them, the others are a click away, and the window that goes removes them. */
export function OpenerLaunches() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [failed, setFailed] = useState<Error | null>(null);
  useLaunches(({ files }) => {
    if (files.length === 0) return false;
    openedSignedOut(files).catch((error: unknown) =>
      setFailed(error instanceof Error ? error : new Error(String(error))),
    );
  });
  useEffect(() => {
    const gone = (event: PageTransitionEvent) => {
      if (event.persisted || leaving) return;
      forgetOpener();
      void sendClosed();
    };
    window.addEventListener('pagehide', gone);
    return () => window.removeEventListener('pagehide', gone);
  }, []);
  const files = opener()?.files ?? [];
  return (
    <LaunchBar>
      {failed && <p className="text-danger">{errorMessage(failed, t)}</p>}
      {files.length > 1 && (
        <nav aria-label={t('device.files')} className="flex flex-wrap gap-1">
          {files.map((file) => (
            <button
              key={file.id}
              type="button"
              aria-current={pathname === nodeHref(file) ? 'page' : undefined}
              onClick={() => void navigate(nodeHref(file))}
              className="max-w-48 truncate rounded-full px-3 py-1 text-muted aria-[current=page]:bg-selected aria-[current=page]:text-ink"
            >
              {file.title}
            </button>
          ))}
        </nav>
      )}
    </LaunchBar>
  );
}

/** Gives whoever just signed in the files their browser opened before, then reads the first
 * alone, where they save it. */
export function Claim() {
  const { t } = useI18n();
  const [failed, setFailed] = useState<Error | null>(null);
  const claimed = useRef(false);
  useEffect(() => {
    const kept = opener();
    if (claimed.current || !kept) return;
    claimed.current = true;
    postJson<{ nodes: TreeNode[] }>('/api/opened/taken', { key: kept.key })
      .then(({ nodes }) => {
        forgetOpener();
        if (nodes[0]) location.assign(nodeHref(nodes[0]));
        else location.assign('/');
      })
      .catch((error: unknown) => {
        forgetOpener();
        window.name = '';
        setFailed(error instanceof Error ? error : new Error(String(error)));
      });
  }, []);
  if (!failed) return <p className="text-sm text-muted">{t('launch.receiving')}</p>;
  return (
    <div className="flex flex-col items-start gap-2 text-sm">
      <p className="text-danger">{errorMessage(failed, t)}</p>
      <button type="button" onClick={() => location.assign('/')} className={button}>
        {t('launch.open')}
      </button>
    </div>
  );
}
