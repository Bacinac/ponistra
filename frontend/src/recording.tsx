import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Room, RoomEvent } from 'livekit-client';
import { Circle, FileText, Folder, Pause, Play, RotateCcw, Square } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { deleteJson, getJson, postJson } from './api';
import { useSession } from './auth';
import { Modal } from './dialogs';
import { useI18n } from './i18n';
import { useReachable } from './live';
import { button, dangerButton, primaryButton } from './styles';
import { codeText, errorMessage } from './tree';

export interface Recorded {
  id: string;
  state: 'recording' | 'saving' | 'done' | 'failed';
  started_by: number | null;
  started_at: string;
  ended_at: string | null;
  folder: string | null;
  minutes: string | null;
  error: string;
  saves_again: boolean;
}

interface Track {
  node?: string;
  identity: string;
  name?: string;
  media: 'audio' | 'video';
  source?: string;
  start: number;
  end: number;
}

interface Asked {
  recording: boolean | Recorded | null;
  asks: boolean;
}

/** Whether the room is being recorded, as the server told everyone in it. */
function useRecorded(room: Room): boolean {
  const read = () => {
    try {
      return JSON.parse(room.metadata || '{}').recording === true;
    } catch {
      return false;
    }
  };
  const [recorded, setRecorded] = useState(read);
  useEffect(() => {
    const changed = () => setRecorded(read());
    room.on(RoomEvent.RoomMetadataChanged, changed);
    changed();
    return () => void room.off(RoomEvent.RoomMetadataChanged, changed);
  }, [room]);
  return recorded;
}

/** The recording's mark in the call, the question whether one's speech goes into the minutes'
    transcript, and for a member the button that starts and stops it. A guest's answers go
    through their own key. */
export function useRecording(room: Room, meeting: string, guestKey: string | null | undefined) {
  const { t } = useI18n();
  const reachable = useReachable();
  const recorded = useRecorded(room);
  const queryClient = useQueryClient();
  const path =
    guestKey === undefined
      ? `/api/meetings/${meeting}/recording`
      : `/api/meetings/${meeting}/guests/${guestKey}/recording`;
  const key = ['meeting-recordings', meeting, 'running', guestKey ?? ''];
  const asked = useQuery({
    queryKey: [...key, recorded],
    queryFn: () => getJson<Asked>(path),
    enabled: recorded && guestKey !== null,
  });
  const answer = useMutation({
    mutationFn: (agreed: boolean) =>
      postJson(guestKey === undefined ? `${path}/consent` : path, { agreed }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });
  const switching = useMutation({
    mutationFn: () =>
      recorded
        ? deleteJson(`/api/meetings/${meeting}/recording`)
        : postJson(`/api/meetings/${meeting}/recording`),
  });
  const error = switching.error ?? answer.error;

  const mark = recorded && (
    <span role="status" className="flex items-center gap-1 text-sm text-danger">
      <Circle size={10} fill="currentColor" aria-hidden />
      {t('recording.on')}
    </span>
  );
  const question = (
    <>
      {recorded && asked.data?.asks && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-2 border-b border-line bg-panel px-4 py-2"
        >
          <p className="min-w-0 flex-1 text-sm">{t('recording.ask')}</p>
          <button
            type="button"
            onClick={() => answer.mutate(true)}
            disabled={answer.isPending}
            className={primaryButton}
          >
            {t('recording.agree')}
          </button>
          <button
            type="button"
            onClick={() => answer.mutate(false)}
            disabled={answer.isPending}
            className={button}
          >
            {t('recording.refuse')}
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="bg-panel px-4 py-1 text-sm text-danger">
          {errorMessage(error, t)}
        </p>
      )}
    </>
  );
  const control = guestKey === undefined && (
    <button
      type="button"
      onClick={() => switching.mutate()}
      disabled={switching.isPending || !reachable}
      title={reachable ? undefined : t('offline.needed')}
      aria-pressed={recorded}
      className={recorded ? dangerButton : button}
    >
      {recorded ? <Square size={16} aria-hidden /> : <Circle size={16} aria-hidden />}
      <span className="sr-only sm:not-sr-only">
        {t(recorded ? 'recording.stop' : 'recording.start')}
      </span>
    </button>
  );
  return { mark, question, control };
}

/** The meeting's recordings, each with its folder, its minutes and its tracks played together. */
export function Recordings({ meeting }: { meeting: string }) {
  const { t, formatDate } = useI18n();
  const me = useSession().data?.user?.id;
  const listed = useQuery({
    queryKey: ['meeting-recordings', meeting],
    queryFn: () =>
      getJson<{ recordings: (Recorded & { tracks: Track[] })[] }>(
        `/api/meetings/${meeting}/recordings`,
      ),
    enabled: !!meeting,
  });
  const again = useMutation({
    mutationFn: (id: string) => postJson(`/api/meetings/recordings/${id}/again`),
  });
  const [playing, setPlaying] = useState<Track[] | null>(null);
  const recordings = listed.data?.recordings ?? [];
  if (!recordings.length) return null;
  return (
    <section className="flex flex-col gap-2 text-sm">
      <h2 className="font-semibold">{t('recording.list')}</h2>
      <ul className="flex flex-col gap-1">
        {recordings.map((each) => {
          const tracks = each.tracks.filter((track) => track.node);
          return (
            <li key={each.id} className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 flex-1 truncate">
                {formatDate(each.started_at)}
                {each.state !== 'done' && (
                  <span className={each.state === 'failed' ? 'text-danger' : 'text-muted'}>
                    {' · '}
                    {each.state === 'failed'
                      ? codeText(each.error, t)
                      : t(each.state === 'saving' ? 'recording.saving' : 'recording.on')}
                  </span>
                )}
              </span>
              {tracks.length > 0 && (
                <button type="button" onClick={() => setPlaying(tracks)} className={button}>
                  <Play size={14} aria-hidden />
                  {t('recording.play')}
                </button>
              )}
              {each.folder && (
                <Link to={`/f/${each.folder}`} className={button}>
                  <Folder size={14} aria-hidden />
                  {t('recording.folder')}
                </Link>
              )}
              {each.minutes && (
                <Link to={`/d/${each.minutes}`} className={button}>
                  <FileText size={14} aria-hidden />
                  {t('recording.minutes')}
                </Link>
              )}
              {each.saves_again && each.started_by === me && (
                <button
                  type="button"
                  onClick={() => again.mutate(each.id)}
                  disabled={again.isPending}
                  className={button}
                >
                  <RotateCcw size={14} aria-hidden />
                  {t('recording.again')}
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {again.error && <p className="text-danger">{errorMessage(again.error, t)}</p>}
      {playing && <Player tracks={playing} onClose={() => setPlaying(null)} />}
    </section>
  );
}

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}:${String(whole % 60).padStart(2, '0')}`;
}

/** The recording's tracks played on one clock: each starts where it began in the meeting. */
function Player({ tracks, onClose }: { tracks: Track[]; onClose: () => void }) {
  const { t } = useI18n();
  const length = Math.max(...tracks.map((each) => each.end)) / 1000;
  const elements = useRef(new Map<Track, HTMLMediaElement>());
  const [at, setAt] = useState(0);
  const [running, setRunning] = useState(false);
  const started = useRef({ wall: 0, at: 0 });
  const placed = useRef(-1);

  const place = (to: number, play: boolean) => {
    for (const [track, element] of elements.current) {
      const own = to - track.start / 1000;
      const inside = own >= 0 && own < (track.end - track.start) / 1000;
      if (inside && Math.abs(element.currentTime - own) > 0.3) element.currentTime = own;
      if (inside && play) void element.play().catch(() => setRunning(false));
      else element.pause();
    }
  };

  useEffect(() => {
    if (!running) return;
    let frame = 0;
    const tick = () => {
      const now = started.current.at + (performance.now() - started.current.wall) / 1000;
      if (now >= length) {
        setRunning(false);
        setAt(length);
        place(length, false);
        return;
      }
      setAt(now);
      if (Math.floor(now * 4) !== placed.current) {
        placed.current = Math.floor(now * 4);
        place(now, true);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [running, length]);

  const toggle = () => {
    if (running) {
      setRunning(false);
      place(at, false);
    } else {
      const from = at >= length ? 0 : at;
      started.current = { wall: performance.now(), at: from };
      setAt(from);
      place(from, true);
      setRunning(true);
    }
  };
  const seek = (to: number) => {
    setAt(to);
    started.current = { wall: performance.now(), at: to };
    place(to, running);
  };
  const shown = tracks.filter((each) => each.media === 'video');
  const heard = tracks.filter((each) => each.media === 'audio');
  const kept = (track: Track) => (element: HTMLMediaElement | null) => {
    if (element) elements.current.set(track, element);
    else elements.current.delete(track);
  };
  return (
    <Modal heading={t('recording.play')} wide onClose={onClose}>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {shown.map((track) => (
          <figure key={`${track.node}`} className="flex flex-col gap-1">
            <video
              ref={kept(track)}
              src={`/api/nodes/${track.node}/file`}
              preload="auto"
              muted
              playsInline
              className="aspect-video w-full rounded bg-panel"
            />
            <figcaption className="truncate text-xs text-muted">
              {track.name || track.identity}
            </figcaption>
          </figure>
        ))}
      </div>
      {heard.map((track) => (
        <audio
          key={`${track.node}`}
          ref={kept(track)}
          src={`/api/nodes/${track.node}/file`}
          preload="auto"
        />
      ))}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={toggle}
          aria-label={t(running ? 'recording.pause' : 'recording.play')}
          className={primaryButton}
        >
          {running ? <Pause size={16} aria-hidden /> : <Play size={16} aria-hidden />}
        </button>
        <input
          type="range"
          min={0}
          max={length}
          step={0.1}
          value={at}
          onChange={(event) => seek(Number(event.target.value))}
          aria-label={t('recording.position')}
          className="min-w-0 flex-1 accent-accent"
        />
        <span className="text-sm tabular-nums text-muted">
          {clock(at)} / {clock(length)}
        </span>
      </div>
    </Modal>
  );
}
