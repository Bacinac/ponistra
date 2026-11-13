import { ChevronLeft, ChevronRight, Pause, Play, RotateCcw, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useI18n } from '../i18n';
import type { DocumentLocale, Tab } from '../tree';
import {
  channelOf,
  elapsed,
  keyed,
  moved,
  placeOf,
  type Move,
  type Position,
  type Said,
  type Timer,
} from './show';
import type { GridSource } from './grids';
import { SpeakerNotes, Stage, useShows } from './Stage';
import { useTitle } from '../title';

const button =
  'flex items-center gap-2 rounded px-3 py-1.5 text-sm hover:bg-hover disabled:opacity-40';

/** The presenter's own window beside a show: its slide and the next, the slide's notes and the
 * time, moving the show as the show moves it. */
export default function Presenter({
  show,
  title,
  own,
  tabs,
  states,
  grids,
  locale,
}: {
  show: string;
  title: string;
  own: Uint8Array;
  tabs: readonly Pick<Tab, 'id'>[];
  states: readonly Uint8Array[];
  grids: GridSource;
  locale: DocumentLocale;
}) {
  const { t, formatNumber, formatDuration, formatTime } = useI18n();
  const shows = useShows(own, tabs, states, grids, locale);
  const { run } = shows;
  const [told, setTold] = useState<{ at: Position; timer: Timer } | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const channel = useRef<BroadcastChannel | null>(null);
  const typed = useRef('');

  useEffect(() => {
    const heard = new BroadcastChannel(channelOf(show));
    channel.current = heard;
    heard.onmessage = ({ data }: MessageEvent<Said>) => {
      if (data.type === 'state') setTold({ at: data.at, timer: data.timer });
      else if (data.type === 'end') {
        setTold(null);
        window.close();
      }
    };
    heard.postMessage({ type: 'hello' } satisfies Said);
    return () => {
      heard.close();
      channel.current = null;
    };
  }, [show]);

  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, []);

  useTitle(`${t('show.presenter')}: ${title}`);

  const say = (said: Said) => channel.current?.postMessage(said);
  const go = (move: Move | 'end') => say(move === 'end' ? { type: 'end' } : { type: 'move', move });
  const goNow = useRef(go);
  goNow.current = go;

  useEffect(() => {
    const pressed = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if ((event.target as Element | null)?.closest('button')) {
        if (event.key === 'Enter' || event.key === ' ') return;
      }
      const { move, typed: next } = keyed(event.key, typed.current);
      typed.current = next;
      if (!move) return;
      event.preventDefault();
      goNow.current(move);
    };
    window.addEventListener('keydown', pressed);
    return () => window.removeEventListener('keydown', pressed);
  }, []);

  if (!told) {
    return (
      <main className="grid h-dvh place-items-center bg-surface text-muted">
        <p>{t('show.waiting')}</p>
      </main>
    );
  }

  const at = placeOf(run, told.at);
  const next = at < run.length ? moved(run, at, 'next') : null;
  const running = told.timer.since !== null;
  return (
    <main className="flex h-dvh flex-col gap-3 bg-surface p-3 text-ink">
      <header className="flex flex-wrap items-center gap-3">
        <button type="button" className={button} onClick={() => go('end')}>
          <X size={16} aria-hidden />
          {t('show.end')}
        </button>
        <span className="text-sm text-muted">
          {at < run.length
            ? `${t('show.slide')} ${formatNumber(at + 1)} / ${formatNumber(run.length)}`
            : t('show.over')}
        </span>
        <span className="ml-auto flex items-center gap-1">
          <span
            aria-label={t('show.elapsed')}
            className="text-2xl tabular-nums"
            data-testid="show-elapsed"
          >
            {formatDuration(elapsed(told.timer, now))}
          </span>
          <button
            type="button"
            className={button}
            aria-label={t(running ? 'show.pause' : 'show.resume')}
            title={t(running ? 'show.pause' : 'show.resume')}
            onClick={() => say({ type: 'timer', change: running ? 'pause' : 'resume' })}
          >
            {running ? <Pause size={16} aria-hidden /> : <Play size={16} aria-hidden />}
          </button>
          <button
            type="button"
            className={button}
            aria-label={t('show.restart')}
            title={t('show.restart')}
            onClick={() => say({ type: 'timer', change: 'restart' })}
          >
            <RotateCcw size={16} aria-hidden />
          </button>
        </span>
        <span aria-label={t('show.clock')} className="text-2xl text-muted tabular-nums">
          {formatTime(new Date(now))}
        </span>
      </header>
      <div className="flex min-h-0 flex-1 gap-3">
        <section
          aria-label={t('show.current')}
          className="ponistra-presenting relative min-w-0 flex-[3]"
        >
          <style>{shows.sheet}</style>
          <Stage shows={shows} at={at} />
          {at >= run.length && <p className="ponistra-show-ended">{t('show.ended')}</p>}
        </section>
        <aside className="flex min-w-0 flex-[2] flex-col gap-3">
          <section aria-label={t('show.next')} className="flex flex-col gap-1">
            <h2 className="text-sm text-muted">{t('show.next')}</h2>
            <div className="ponistra-presenting relative aspect-video">
              {next !== null && <Stage shows={shows} at={next} />}
              {(next === null || next >= run.length) && (
                <p className="ponistra-show-ended">{t('show.over')}</p>
              )}
            </div>
          </section>
          <section
            aria-label={t('command.speakerNotes')}
            className="flex min-h-0 flex-1 flex-col gap-1"
          >
            <h2 className="text-sm text-muted">{t('command.speakerNotes')}</h2>
            <div className="min-h-0 flex-1 overflow-auto rounded bg-panel p-3">
              <SpeakerNotes shows={shows} at={at} />
            </div>
          </section>
        </aside>
      </div>
      <footer className="flex gap-2">
        <button type="button" className={button} onClick={() => go('previous')}>
          <ChevronLeft size={16} aria-hidden />
          {t('show.previous')}
        </button>
        <button type="button" className={button} onClick={() => go('next')}>
          {t('show.next')}
          <ChevronRight size={16} aria-hidden />
        </button>
      </footer>
    </main>
  );
}
