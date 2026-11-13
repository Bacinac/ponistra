import { useEffect, useEffectEvent, useState } from 'react';
import { useNavigate } from 'react-router';
import { useI18n } from './i18n';
import { button } from './styles';
import { nodeHref } from './tree';
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

const waiting: Launch[] = [];
let taker: ((launch: Launch) => void) | null = null;

// Set once for the page: the browser hands a consumer each launch only once, and one that comes
// while no window takes it, signed out or before the app has drawn, waits for the next that does.
window.launchQueue?.setConsumer(async ({ targetURL, files }) => {
  const launch = {
    target: targetURL,
    files: await Promise.all(files.map((each) => each.getFile())),
  };
  if (taker) taker(launch);
  else waiting.push(launch);
});

function useLaunches(take: (launch: Launch) => void) {
  const taken = useEffectEvent(take);
  useEffect(() => {
    const mine = (launch: Launch) => taken(launch);
    taker = mine;
    waiting.splice(0).forEach(mine);
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

/** The main window's part: it opens what a launch asks, a file opened from the computer placed
 * among the user's documents like an upload, and takes what a launch into a meeting's or a
 * presenter's window hands it. */
export function Launches() {
  const navigate = useNavigate();
  const uploads = useUploads();
  function opened({ target, files }: Launch) {
    if (files.length > 0) {
      void navigate('/documents');
      uploads.start(loose(files), null, (placed) => {
        if (placed.length === 1) void navigate(nodeHref(placed[0]));
      });
      return;
    }
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
  return null;
}

/** A meeting's or a presenter's window, which a launch never leads away: it hands the launch to
 * the main window, and while none is open says so and opens one. */
export function LaunchesElsewhere() {
  const { t } = useI18n();
  const [held, setHeld] = useState<Launch[]>([]);
  useLaunches((launch) => {
    void led().then((open) => {
      if (!open) return setHeld((now) => [...now, launch]);
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
    void led().then((open) => open && hand());
    return () => {
      handed = true;
      channel.close();
    };
  }, [held]);
  if (held.length === 0) return null;
  return (
    <div
      role="status"
      className="fixed right-4 bottom-4 z-40 flex max-w-[calc(100vw-2rem)] items-center gap-3 rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink shadow-lg"
    >
      <p className="min-w-0 flex-1">{t('launch.elsewhere')}</p>
      <button type="button" onClick={() => window.open('/', '_blank')} className={button}>
        {t('launch.open')}
      </button>
    </div>
  );
}
