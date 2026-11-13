import { useMutation, useQuery } from '@tanstack/react-query';
import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { getJson, patchJson, postJson } from './api';
import { LoginForm } from './auth';
import { Loading, Lobby } from './frame';
import { useI18n } from './i18n';
import { useLive } from './live';
import type { Talk } from './chat';
import type { Shown } from './MeetingPage';
import { button, primaryButton } from './styles';
import { useTitle } from './title';
import { errorMessage } from './tree';

const Call = lazy(() => import('./call'));

type State = 'waiting' | 'admitted' | 'refused';

/** What someone outside the installation sees of a meeting before they are in it. */
interface Door {
  id: string;
  title: string;
  /** How the key their link or this tab holds was asked or came, where it is still theirs. */
  guest: { name: string; state: State } | null;
}

/** A guest's way into the call (S2-2), which `Call` takes in place of a signed-in user's. */
/** The key a participant enters the room with, and the installation's relay where it has one:
 * the ICE servers in place of those LiveKit offers. */
export interface Joining {
  token: string;
  ice: RTCIceServer[] | null;
}

export interface Guesting {
  name: string;
  onName: (name: string) => void;
  /** Whether the guest waits at the door for someone in the meeting to let them in. */
  waiting: boolean;
  /** The guest's own key, once they are in the meeting. */
  key: string | null;
  /** What the guest enters the room with, once they are let in. */
  enter: () => Promise<Joining>;
  /** Stops waiting at the door. */
  cancel: () => void;
  signIn: () => void;
  /** The meeting's conversation as the guest reads it in the call. */
  talk: Talk;
}

/** What the door's socket says: the guest's state, and once they are let in, how far the
    meeting's conversation has moved. */
interface Said {
  state: State;
  changed?: string;
  unread?: number;
}

const RECONNECT = 2000;
const CLOSED_UNKNOWN = 4404;

function storedKey(meeting: string): string {
  return `ponistra.guest.${meeting}`;
}

function kept(meeting: string): string | null {
  try {
    return sessionStorage.getItem(storedKey(meeting));
  } catch {
    return null;
  }
}

function keep(meeting: string, key: string): void {
  try {
    sessionStorage.setItem(storedKey(meeting), key);
  } catch {
    // Blocked storage only costs a reload its place at the door.
  }
}

class Cancelled extends Error {}

/** A socket of the key's at the meeting's door, opened again whenever it drops, until the
    function returned closes it or the server knows no such key. */
function atDoor(key: string, onSaid: (said: Said) => void, onUnknown: () => void): () => void {
  let socket: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let done = false;
  const close = () => {
    done = true;
    clearTimeout(timer);
    socket?.close();
  };
  const connect = () => {
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const opened = new WebSocket(`${scheme}//${location.host}/api/lobby`);
    socket = opened;
    opened.addEventListener('open', () => opened.send(JSON.stringify({ key })));
    opened.addEventListener('message', (event) => onSaid(JSON.parse(event.data as string) as Said));
    opened.addEventListener('close', (event) => {
      if (done) return;
      if (event.code === CLOSED_UNKNOWN) {
        close();
        onUnknown();
      } else timer = setTimeout(connect, RECONNECT);
    });
  };
  connect();
  return close;
}

/** Waits at the door until someone in the meeting answers. */
function answered(key: string, cancelled: (cancel: () => void) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const close = atDoor(
      key,
      ({ state }) => {
        if (state === 'waiting') return;
        close();
        resolve();
      },
      resolve,
    );
    cancelled(() => {
      close();
      reject(new Cancelled());
    });
  });
}

/** The meeting's conversation as a guest in its call reads it, followed at the door. */
function useGuestTalk(meeting: string, key: string | null): Talk {
  const [said, setSaid] = useState<Said | null>(null);
  useEffect(() => {
    if (!key) return;
    return atDoor(key, setSaid, () => setSaid(null));
  }, [key]);
  return {
    at: `/api/meetings/${meeting}/guests/${encodeURIComponent(key ?? '')}`,
    changed: said?.changed,
    unread: said?.unread ?? 0,
  };
}

function useGuesting(id: string, door: Door, given: string | null, signIn: () => void): Guesting {
  const [name, setName] = useState(door.guest?.name ?? '');
  const [waiting, setWaiting] = useState(false);
  const [inside, setInside] = useState<string | null>(null);
  const key = useRef(door.guest ? given : null);
  const cancel = useRef<() => void>(() => {});
  useEffect(() => () => cancel.current(), []);
  const talk = useGuestTalk(id, inside);
  return {
    name,
    onName: setName,
    waiting,
    talk,
    key: inside,
    enter: async () => {
      const came = await postJson<{ key: string; state: State }>(
        `/api/meetings/${id}/guests`,
        key.current ? { key: key.current, name } : { name },
      );
      key.current = came.key;
      keep(id, came.key);
      if (came.state === 'waiting') {
        setWaiting(true);
        try {
          await answered(came.key, (stop) => (cancel.current = stop));
        } finally {
          setWaiting(false);
        }
      }
      const joining = await postJson<Joining>(`/api/meetings/${id}/guests/join`, {
        key: came.key,
      });
      setInside(came.key);
      return joining;
    },
    cancel: () => cancel.current(),
    signIn,
  };
}

/** A meeting's page for someone not signed in: they come as a guest under the name they give,
    or sign in. */
export function GuestMeetingPage() {
  const { t } = useI18n();
  const id = useParams().id ?? '';
  const [params] = useSearchParams();
  const given = params.get('guest') ?? kept(id);
  const [signingIn, setSigningIn] = useState(false);
  const door = useQuery({
    queryKey: ['door', id, given],
    queryFn: () =>
      getJson<Door>(
        `/api/meetings/${id}/door${given ? `?guest=${encodeURIComponent(given)}` : ''}`,
      ),
  });
  useTitle(door.data && (door.data.title || t('meeting.untitled')));
  if (signingIn) {
    return (
      <Lobby>
        <LoginForm />
        <button type="button" onClick={() => setSigningIn(false)} className="text-sm underline">
          {t('meeting.asGuest')}
        </button>
      </Lobby>
    );
  }
  return (
    <div className="flex h-dvh flex-col bg-surface text-ink">
      {door.error ? (
        <p className="m-auto max-w-md p-4 text-danger">{errorMessage(door.error, t)}</p>
      ) : door.data ? (
        <Suspense fallback={<Centered />}>
          <GuestCall door={door.data} given={given} signIn={() => setSigningIn(true)} />
        </Suspense>
      ) : (
        <Centered />
      )}
    </div>
  );
}

function GuestCall({
  door,
  given,
  signIn,
}: {
  door: Door;
  given: string | null;
  signIn: () => void;
}) {
  const guest = useGuesting(door.id, door, given, signIn);
  const meeting: Shown = {
    id: door.id,
    title: door.title,
    link: '',
    conversation: '',
    present: [],
    planned: true,
  };
  return <Call meeting={meeting} guest={guest} onInside={() => {}} />;
}

function Centered() {
  return (
    <div className="m-auto">
      <Loading />
    </div>
  );
}

/** The guests waiting at the meeting's door, for anyone of the installation in it to let in or
    turn away. */
export function AtDoor({ meeting }: { meeting: string }) {
  const { t } = useI18n();
  const { lobby } = useLive();
  const answer = useMutation({
    mutationFn: ({ guest, state }: { guest: number; state: State }) =>
      patchJson(`/api/meetings/${meeting}/guests/${guest}`, { state }),
  });
  const waiting = lobby.filter((each) => each.meeting === meeting);
  if (!waiting.length) return null;
  return (
    <ul aria-label={t('lobby.title')} className="flex flex-col gap-2">
      {waiting.map((each) => (
        <li key={each.id} className="flex flex-wrap items-center gap-2 text-sm">
          <span className="min-w-0 flex-1 truncate">
            {t('lobby.waits').replace('{name}', each.name)}
          </span>
          <button
            type="button"
            onClick={() => answer.mutate({ guest: each.id, state: 'refused' })}
            className={button}
          >
            {t('lobby.refuse')}
          </button>
          <button
            type="button"
            onClick={() => answer.mutate({ guest: each.id, state: 'admitted' })}
            className={primaryButton}
          >
            {t('lobby.admit')}
          </button>
        </li>
      ))}
      {answer.error && <li className="text-sm text-danger">{errorMessage(answer.error, t)}</li>}
    </ul>
  );
}
