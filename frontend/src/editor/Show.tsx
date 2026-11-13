import { AppWindow, ChevronLeft, ChevronRight, Maximize, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { compact } from '../address';
import { useI18n } from '../i18n';
import { useSaved } from '../saved';
import { errorMessage, type DocumentLocale, type Tab } from '../tree';
import {
  channelOf,
  keyed,
  leaveFullScreen,
  moved,
  positionOf,
  presentFullScreen,
  startOf,
  timed,
  type From,
  type Move,
  type Said,
  type Timer,
} from './show';
import type { GridSource } from './grids';
import { Stage, useShows } from './Stage';

/** How long the show's controls stay after the mouse last moved. */
const STIRRED = 2500;

export function presenterHref(nodeId: string, show: string): string {
  return `/present/${compact(nodeId)}?${new URLSearchParams({ show })}`;
}

/** Keeps the page under the show out of reach and the focus on the show, which ends when the
 * screen is given back, except while opening the presenter's window takes it. Whether the show
 * has the whole screen. */
function useCover(
  root: RefObject<HTMLElement | null>,
  onLeft: () => void,
  opening: RefObject<number>,
): boolean {
  const [full, setFull] = useState(() => Boolean(document.fullscreenElement));
  const left = useRef(onLeft);
  left.current = onLeft;
  useEffect(() => {
    const page = document.getElementById('root');
    const before = document.activeElement;
    if (page) page.inert = true;
    root.current!.focus();
    const changed = () => {
      const now = Boolean(document.fullscreenElement);
      setFull(now);
      if (!now && Date.now() > opening.current) left.current();
    };
    document.addEventListener('fullscreenchange', changed);
    return () => {
      document.removeEventListener('fullscreenchange', changed);
      if (page) page.inert = false;
      if (before instanceof HTMLElement) before.focus({ preventScroll: true });
    };
  }, [root, opening]);
  return full;
}

function Bar({ children, stirred }: { children: ReactNode; stirred: boolean }) {
  return (
    <div
      className="ponistra-show-bar"
      data-stirred={stirred || undefined}
      onClick={(event) => event.stopPropagation()}
    >
      {children}
    </div>
  );
}

function BarButton({
  label,
  icon: Icon,
  onClick,
}: {
  label: string;
  icon: typeof X;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
    >
      <Icon size={18} aria-hidden />
    </button>
  );
}

function Running({
  nodeId,
  show,
  from,
  own,
  tabs,
  states,
  grids,
  locale,
  onEnd,
}: {
  nodeId: string;
  show: string;
  from: From;
  own: Uint8Array;
  tabs: readonly Pick<Tab, 'id'>[];
  states: readonly Uint8Array[];
  grids: GridSource;
  locale: DocumentLocale;
  onEnd: () => void;
}) {
  const { t } = useI18n();
  const shows = useShows(own, tabs, states, grids, locale);
  const { run } = shows;
  const [at, setAt] = useState(() =>
    from === 'start' ? moved(run, run.length, 'first') : startOf(run, from.tab, from.index),
  );
  const atNow = useRef(at);
  const [timer, setTimer] = useState<Timer>(() => ({ since: Date.now(), before: 0 }));
  const timerNow = useRef(timer);
  timerNow.current = timer;
  const [stirred, setStirred] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const opening = useRef(0);
  const typed = useRef('');
  const channel = useRef<BroadcastChannel | null>(null);
  const root = useRef<HTMLDivElement>(null);

  const go = useCallback(
    (move: Move | 'end') => {
      if (move === 'end' || (move === 'next' && atNow.current >= run.length)) {
        leaveFullScreen();
        return onEnd();
      }
      atNow.current = moved(run, atNow.current, move);
      setAt(atNow.current);
    },
    [run, onEnd],
  );
  const goNow = useRef(go);
  goNow.current = go;
  const full = useCover(root, () => go('end'), opening);

  useEffect(() => {
    const told = new BroadcastChannel(channelOf(show));
    channel.current = told;
    told.onmessage = ({ data }: MessageEvent<Said>) => {
      if (data.type === 'hello') {
        told.postMessage({
          type: 'state',
          at: positionOf(run, atNow.current),
          timer: timerNow.current,
        } satisfies Said);
      } else if (data.type === 'move') {
        goNow.current(data.move);
      } else if (data.type === 'timer') {
        setTimer((was) => timed(was, data.change, Date.now()));
      } else if (data.type === 'end') {
        goNow.current('end');
      }
    };
    return () => {
      told.postMessage({ type: 'end' } satisfies Said);
      told.close();
      channel.current = null;
    };
  }, [show, run]);

  useEffect(() => {
    channel.current?.postMessage({ type: 'state', at: positionOf(run, at), timer } satisfies Said);
  }, [run, at, timer]);

  useEffect(() => {
    if (!stirred) return;
    const still = setTimeout(() => setStirred(false), STIRRED);
    return () => clearTimeout(still);
  }, [stirred]);

  const openPresenter = () => {
    // Firefox leaves full screen when a page opens a window, which here must not end the show.
    opening.current = Date.now() + 1000;
    const opened = window.open(presenterHref(nodeId, show), `ponistra-presenter-${show}`, 'popup');
    setBlocked(!opened);
  };

  return (
    <div
      ref={root}
      tabIndex={-1}
      role="dialog"
      aria-modal
      aria-label={t('show.title')}
      className="ponistra-show"
      data-stirred={stirred || undefined}
      onClick={() => go('next')}
      onMouseMove={() => setStirred(true)}
      onKeyDown={(event) => {
        if (event.altKey || event.ctrlKey || event.metaKey) return;
        if (event.target !== root.current && (event.key === 'Enter' || event.key === ' ')) return;
        const { move, typed: next } = keyed(event.key, typed.current);
        typed.current = next;
        if (!move) return;
        event.preventDefault();
        go(move);
      }}
    >
      <style>{shows.sheet}</style>
      <Stage shows={shows} at={at} />
      {at >= run.length && <p className="ponistra-show-ended">{t('show.ended')}</p>}
      <Bar stirred={stirred || blocked}>
        <BarButton label={t('show.previous')} icon={ChevronLeft} onClick={() => go('previous')} />
        <BarButton label={t('show.next')} icon={ChevronRight} onClick={() => go('next')} />
        <BarButton label={t('show.presenter')} icon={AppWindow} onClick={openPresenter} />
        {!full && (
          <BarButton label={t('show.fullScreen')} icon={Maximize} onClick={presentFullScreen} />
        )}
        <BarButton label={t('show.end')} icon={X} onClick={() => go('end')} />
        {blocked && <span role="alert">{t('show.blocked')}</span>}
      </Bar>
    </div>
  );
}

/** The document's slides on the whole screen, from `from`, until the show ends. */
export function Show({
  nodeId,
  show,
  from,
  locale,
  onEnd,
}: {
  nodeId: string;
  show: string;
  from: From;
  locale: DocumentLocale;
  onEnd: () => void;
}) {
  const { placement, own, states, grids, error } = useSaved(nodeId, `show:${show}`);
  return createPortal(
    error || !placement || !own || !states || !grids ? (
      <Waiting error={error} onEnd={onEnd} />
    ) : (
      <Running
        nodeId={nodeId}
        show={show}
        from={from}
        own={own}
        tabs={placement.tabs}
        states={states}
        grids={grids}
        locale={locale}
        onEnd={onEnd}
      />
    ),
    document.body,
  );
}

/** The cover of a show whose slides are on their way, or could not be read. */
function Waiting({ error, onEnd }: { error: Error | null; onEnd: () => void }) {
  const { t } = useI18n();
  const root = useRef<HTMLDivElement>(null);
  const never = useRef(0);
  const end = () => {
    leaveFullScreen();
    onEnd();
  };
  useCover(root, end, never);
  useEffect(() => {
    if (error) leaveFullScreen();
  }, [error]);
  return (
    <div
      ref={root}
      tabIndex={-1}
      role="dialog"
      aria-modal
      aria-label={t('show.title')}
      className="ponistra-show"
      onKeyDown={(event) => event.key === 'Escape' && end()}
      onClick={() => error && end()}
    >
      {error && (
        <p role="alert" className="ponistra-show-ended">
          {errorMessage(error, t)}
        </p>
      )}
    </div>
  );
}
