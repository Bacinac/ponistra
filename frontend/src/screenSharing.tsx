import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { LocalTrack, ScreenShareCaptureOptions } from 'livekit-client';
import { ExternalLink, MonitorUp, PictureInPicture2, X } from 'lucide-react';
import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { patchJson } from './api';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import type { Shown } from './MeetingPage';
import { button, dangerButton, field, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';

/** A tab first in the browser's picker, a window next and the whole screen last; a tab shared is
    swapped for another from that tab's own bar, and the meeting's own tab is never offered. */
export const SHARED: ScreenShareCaptureOptions = {
  video: { displaySurface: 'browser' },
  selfBrowserSurface: 'exclude',
  surfaceSwitching: 'include',
};

type Surface = 'browser' | 'window' | 'monitor';

const SURFACES: Record<Surface, MessageKey> = {
  browser: 'meeting.sharingTab',
  window: 'meeting.sharingWindow',
  monitor: 'meeting.sharingScreen',
};

function surfaceOf(track: LocalTrack): Surface {
  const surface = track.mediaStreamTrack.getSettings().displaySurface;
  return surface === 'browser' || surface === 'window' ? surface : 'monitor';
}

interface Pictured {
  requestWindow(options?: { width?: number; height?: number }): Promise<Window>;
  window: Window | null;
}

function pictured(): Pictured | undefined {
  return (window as Window & { documentPictureInPicture?: Pictured }).documentPictureInPicture;
}

/** A window above every other, opened while the screen is shared, which closes with the sharing. */
export function useFloating(sharing: boolean) {
  const [floating, setFloating] = useState<Window | null>(null);
  const open = useCallback(async () => {
    const picture = pictured();
    if (!picture) return;
    let opened: Window;
    try {
      opened = await picture.requestWindow({ width: 340, height: 230 });
    } catch (error) {
      // Opened only on a press of the user's: the sharing's own press may have run out.
      if ((error as Error).name === 'NotAllowedError') return;
      throw error;
    }
    for (const style of document.querySelectorAll('link[rel="stylesheet"], style'))
      opened.document.head.append(style.cloneNode(true));
    for (const { name, value } of document.documentElement.attributes)
      opened.document.documentElement.setAttribute(name, value);
    opened.document.body.className = 'm-0 bg-surface text-ink';
    opened.addEventListener('pagehide', () => setFloating(null), { once: true });
    setFloating(opened);
  }, []);
  useEffect(() => {
    if (!sharing) floating?.close();
  }, [sharing, floating]);
  useEffect(() => () => pictured()?.window?.close(), []);
  return { floating, open, can: !!pictured() && !floating };
}

function Preview({ track, className }: { track: LocalTrack; className: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    // A video in the floating window belongs to its document, which LiveKit's attach rejects.
    element.srcObject = new MediaStream([track.mediaStreamTrack]);
    void element.play().catch(() => {});
    return () => {
      element.srcObject = null;
    };
  }, [track]);
  return <video ref={ref} muted playsInline autoPlay className={className} />;
}

/** What the user shares, as the others see it: a whole screen small, as it shows itself again. */
export function OwnShare({
  track,
  floating,
  onFloat,
  onStop,
}: {
  track: LocalTrack;
  floating: ReturnType<typeof useFloating>;
  onFloat: () => void;
  onStop: () => void;
}) {
  const { t } = useI18n();
  const surface = surfaceOf(track);
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-3 py-2">
        <MonitorUp size={16} className="text-accent" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-sm">{t(SURFACES[surface])}</span>
        {floating.can && (
          <button type="button" onClick={onFloat} className={button}>
            <PictureInPicture2 size={16} aria-hidden />
            <span className="sr-only sm:not-sr-only">{t('meeting.float')}</span>
          </button>
        )}
      </div>
      <div className="flex min-h-0 flex-1 items-center justify-center p-2">
        <Preview
          track={track}
          className={
            surface === 'monitor' ? 'max-h-48 max-w-80 rounded' : 'size-full object-contain'
          }
        />
      </div>
      {floating.floating &&
        createPortal(
          <div className="relative flex h-screen flex-col gap-2 p-2">
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 border-4 border-danger motion-safe:animate-pulse"
            />
            <Preview track={track} className="min-h-0 flex-1 object-contain" />
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-sm">{t(SURFACES[surface])}</span>
              <button type="button" onClick={onStop} className={dangerButton}>
                {t('meeting.stopSharing')}
              </button>
            </div>
          </div>,
          floating.floating.document.body,
        )}
    </div>
  );
}

function shortened(address: string): string {
  const { host, pathname, search } = new URL(address);
  return `${host}${pathname === '/' ? '' : pathname}${search}`;
}

/** The addresses a meeting's people mean to share, opened as tabs before the sharing picks them. */
export function SharedTabs({ meeting }: { meeting: Shown }) {
  const { t } = useI18n();
  const client = useQueryClient();
  const [address, setAddress] = useState('');
  const [blocked, setBlocked] = useState(false);
  const saved = useMutation({
    mutationFn: (tabs: string[]) => patchJson<Shown>(`/api/meetings/${meeting.id}`, { tabs }),
    onSuccess: (shown) => client.setQueryData(['meeting', meeting.id], shown),
  });
  const tabs = meeting.tabs;
  const opened = (tab: string) => {
    const tabbed = window.open(tab, '_blank');
    if (tabbed) tabbed.opener = null;
    return !!tabbed;
  };
  const added = (event: FormEvent) => {
    event.preventDefault();
    const given = address.trim();
    const tab = /^[a-z][a-z0-9+.-]*:/i.test(given) ? given : `https://${given}`;
    saved.mutate([...tabs, tab], { onSuccess: () => setAddress('') });
  };
  return (
    <section aria-label={t('meeting.tabsTitle')} className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex items-center gap-2">
        <h2 className="min-w-0 flex-1 truncate font-semibold">{t('meeting.tabsTitle')}</h2>
        {tabs.length > 1 && (
          <button
            type="button"
            className={button}
            onClick={() => setBlocked(!tabs.map(opened).every(Boolean))}
          >
            <ExternalLink size={16} aria-hidden />
            {t('meeting.openTabs')}
          </button>
        )}
      </div>
      {blocked && (
        <p role="alert" className="text-sm text-danger">
          {t('meeting.tabsBlocked')}
        </p>
      )}
      <ul className="flex min-h-0 flex-col gap-1 overflow-y-auto">
        {tabs.map((tab) => (
          <li key={tab} className="flex items-center gap-1">
            <button
              type="button"
              title={tab}
              onClick={() => setBlocked(!opened(tab))}
              className="min-w-0 flex-1 truncate rounded px-2 py-1 text-left text-sm hover:bg-hover"
            >
              {shortened(tab)}
            </button>
            <button
              type="button"
              aria-label={t('meeting.removeTab')}
              title={t('meeting.removeTab')}
              disabled={saved.isPending}
              onClick={() => saved.mutate(tabs.filter((each) => each !== tab))}
              className={iconButton}
            >
              <X size={14} aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={added} className="flex gap-2">
        <input
          value={address}
          onChange={(event) => setAddress(event.target.value)}
          aria-label={t('meeting.tabAddress')}
          placeholder={t('meeting.tabAddress')}
          className={`${field} min-w-0 flex-1`}
        />
        <button
          type="submit"
          disabled={!address.trim() || saved.isPending}
          className={primaryButton}
        >
          {t('meeting.addTab')}
        </button>
      </form>
      {saved.error && <p className="text-sm text-danger">{errorMessage(saved.error, t)}</p>}
    </section>
  );
}
