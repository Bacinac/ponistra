import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { LocalTrack, ScreenShareCaptureOptions } from 'livekit-client';
import {
  AppWindow,
  Check,
  ChevronDown,
  ExternalLink,
  Globe,
  LayoutDashboard,
  ListChecks,
  Monitor,
  MonitorUp,
  Pencil,
  PictureInPicture2,
  Square,
  X,
} from 'lucide-react';
import {
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { getJson, patchJson } from './api';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import type { PreparedTab, Shown } from './MeetingPage';
import { Menu, MenuItem, MenuSeparator, MenuSub } from './menu';
import { button, dangerButton, field, iconButton, primaryButton } from './styles';
import { errorMessage, nodeHref, useBoards, useFavourites, useRecent } from './tree';
import { useLinks } from './linksData';

export type Surface = 'browser' | 'window' | 'monitor';

/** The kind chosen first in the browser's picker, which still offers the others; a tab shared is
    swapped for another from that tab's own bar, and the meeting's own tab is never offered. */
export const sharedAs = (surface: Surface): ScreenShareCaptureOptions => ({
  video: { displaySurface: surface },
  selfBrowserSurface: 'exclude',
  surfaceSwitching: 'include',
});

const CHOSEN: { surface: Surface; label: MessageKey; icon: typeof Globe }[] = [
  { surface: 'browser', label: 'meeting.shareTab', icon: Globe },
  { surface: 'window', label: 'meeting.shareWindow', icon: AppWindow },
  { surface: 'monitor', label: 'meeting.shareScreen', icon: Monitor },
];

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

/** What the user shares, as the others see it, small beside the stop: the people stay in view. */
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
    <section
      aria-label={t(SURFACES[surface])}
      className="flex shrink-0 items-center gap-3 rounded-lg bg-panel p-2 ring-2 ring-danger"
    >
      <Preview track={track} className="h-24 max-w-44 shrink-0 rounded object-contain" />
      <div className="flex min-w-0 flex-1 flex-col items-start gap-2">
        <span className="flex max-w-full items-center gap-2 text-sm">
          <MonitorUp size={16} className="shrink-0 text-accent" aria-hidden />
          <span className="truncate">{t(SURFACES[surface])}</span>
        </span>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={onStop} className={dangerButton}>
            <Square size={16} aria-hidden />
            {t('meeting.stopSharing')}
          </button>
          {floating.can && (
            <button type="button" onClick={onFloat} className={button}>
              <PictureInPicture2 size={16} aria-hidden />
              <span className="sr-only sm:not-sr-only">{t('meeting.float')}</span>
            </button>
          )}
        </div>
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
    </section>
  );
}

/** Opens the tab apart from the meeting; false where the browser kept it from opening. */
function openTab(tab: string): boolean {
  const tabbed = window.open(tab, '_blank');
  if (tabbed) tabbed.opener = null;
  return !!tabbed;
}

/** What to share: a kind of surface while nothing is shared, the stop while it is, and the
    meeting's tabs to open for sharing below. */
export function ShareMenu({
  meeting,
  sharing,
  taken,
  staged,
  onShare,
  onBoard,
  onStop,
  onBlocked,
  onTabs,
}: {
  meeting?: Shown;
  sharing: boolean;
  taken: boolean;
  /** The board on the stage now. */
  staged: string | null;
  onShare?: (surface: Surface) => void;
  onBoard?: (board: string) => void;
  onStop: () => void;
  onBlocked: () => void;
  onTabs: () => void;
}) {
  const { t } = useI18n();
  const tabs = meeting?.tabs ?? [];
  const trigger = (
    <button type="button" className={sharing ? primaryButton : button}>
      <MonitorUp size={16} aria-hidden />
      <span className="sr-only sm:not-sr-only">{t('meeting.share')}</span>
      <ChevronDown size={14} aria-hidden />
    </button>
  );
  return (
    <Menu trigger={trigger} align="start">
      {sharing ? (
        <MenuItem icon={Square} label={t('meeting.stopSharing')} onSelect={onStop} />
      ) : (
        onShare &&
        CHOSEN.map(({ surface, label, icon }) => (
          <MenuItem
            key={surface}
            icon={icon}
            label={t(label)}
            disabled={taken}
            onSelect={() => onShare(surface)}
          />
        ))
      )}
      {meeting && onBoard && (
        <MenuSub icon={ListChecks} label={t('meeting.prepared')}>
          <Prepared
            tabs={tabs}
            taken={taken}
            staged={staged}
            onBoard={onBoard}
            onBlocked={onBlocked}
            onTabs={onTabs}
          />
        </MenuSub>
      )}
    </Menu>
  );
}

/** What the meeting's people prepared to share: a board goes on the stage, any other address
    opens as a tab of its own for the browser to share. */
function Prepared({
  tabs,
  taken,
  staged,
  onBoard,
  onBlocked,
  onTabs,
}: {
  tabs: PreparedTab[];
  taken: boolean;
  staged: string | null;
  onBoard: (board: string) => void;
  onBlocked: () => void;
  onTabs: () => void;
}) {
  const { t } = useI18n();
  const opened = tabs.filter((tab) => !tab.board).map((tab) => tab.address);
  return (
    <>
      {tabs.map(({ address, title, board }) =>
        board ? (
          <MenuItem
            key={address}
            icon={LayoutDashboard}
            label={title ?? shortened(address)}
            disabled={taken}
            checked={board === staged}
            onSelect={() => onBoard(board)}
          />
        ) : (
          <MenuItem
            key={address}
            icon={ExternalLink}
            label={title ?? shortened(address)}
            onSelect={() => {
              if (!openTab(address)) onBlocked();
            }}
          />
        ),
      )}
      {!tabs.length && (
        <MenuItem
          icon={ListChecks}
          label={t('meeting.nothingPrepared')}
          disabled
          onSelect={() => {}}
        />
      )}
      {opened.length > 1 && (
        <MenuItem
          icon={ExternalLink}
          label={t('meeting.openTabs')}
          onSelect={() => {
            if (!opened.map(openTab).every(Boolean)) onBlocked();
          }}
        />
      )}
      <MenuSeparator />
      <MenuItem icon={Pencil} label={t('meeting.editTabs')} onSelect={onTabs} />
    </>
  );
}

function shortened(address: string): string {
  const { host, pathname, search } = new URL(address);
  return `${host}${pathname === '/' ? '' : pathname}${search}`;
}

/** The addresses a meeting's people mean to share, opened as tabs before the sharing picks them. */
export function SharedTabs({
  meeting,
  blocked,
  staged,
  onBlocked,
  onBoard,
  onClose,
}: {
  meeting: Shown;
  blocked: boolean;
  /** The board on the stage now. */
  staged: string | null;
  onBlocked: (blocked: boolean) => void;
  onBoard: (board: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const client = useQueryClient();
  const [address, setAddress] = useState('');
  const saved = useMutation({
    mutationFn: (change: { add: string } | { remove: string }) =>
      patchJson<Shown>(`/api/meetings/${meeting.id}`, change),
    onSuccess: (shown) => client.setQueryData(['meeting', meeting.id], shown),
  });
  const tabs = meeting.tabs.map((tab) => tab.address);
  const opened = meeting.tabs.filter((tab) => !tab.board).map((tab) => tab.address);
  const added = (event: FormEvent) => {
    event.preventDefault();
    const given = address.trim();
    const tab = /^[a-z][a-z0-9+.-]*:/i.test(given) ? given : `https://${given}`;
    saved.mutate({ add: tab }, { onSuccess: () => setAddress('') });
  };
  return (
    <section aria-label={t('meeting.tabsTitle')} className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex items-center gap-2">
        <h2 className="min-w-0 flex-1 truncate font-semibold">{t('meeting.tabsTitle')}</h2>
        {opened.length > 1 && (
          <button
            type="button"
            className={button}
            onClick={() => onBlocked(!opened.map(openTab).every(Boolean))}
          >
            <ExternalLink size={16} aria-hidden />
            {t('meeting.openTabs')}
          </button>
        )}
        <button
          type="button"
          aria-label={t('frame.close')}
          title={t('frame.close')}
          onClick={onClose}
          className={iconButton}
        >
          <X size={16} aria-hidden />
        </button>
      </div>
      {blocked && (
        <p role="alert" className="text-sm text-danger">
          {t('meeting.tabsBlocked')}
        </p>
      )}
      <ul className="flex min-h-0 flex-col gap-1 overflow-y-auto">
        {meeting.tabs.map(({ address, title, board }) => (
          <li key={address} className="flex items-center gap-1">
            <button
              type="button"
              title={address}
              aria-pressed={board ? board === staged : undefined}
              onClick={() => (board ? onBoard(board) : onBlocked(!openTab(address)))}
              className="flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-1 text-left text-sm hover:bg-hover aria-pressed:bg-selected"
            >
              {board ? (
                <LayoutDashboard size={14} aria-hidden className="shrink-0 text-muted" />
              ) : (
                <ExternalLink size={14} aria-hidden className="shrink-0 text-muted" />
              )}
              <span className="min-w-0 flex-1 truncate">{title ?? shortened(address)}</span>
              {board && board === staged && (
                <Check size={14} aria-hidden className="shrink-0 text-accent" />
              )}
            </button>
            <button
              type="button"
              aria-label={t('meeting.removeTab')}
              title={t('meeting.removeTab')}
              disabled={saved.isPending}
              onClick={() => saved.mutate({ remove: address })}
              className={iconButton}
            >
              <X size={14} aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={added} className="flex gap-2">
        <TabAddress
          value={address}
          left={tabs}
          onChange={setAddress}
          onChosen={(tab) => saved.mutate({ add: tab }, { onSuccess: () => setAddress('') })}
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

interface Offered {
  title: string;
  address: string;
}

/** What the user may mean to share: the tabs of their meetings before, then their favourites,
 * links and what they opened lately, each once. */
function useOffered(left: string[]): Offered[] {
  const before = useQuery({
    queryKey: ['meeting-tabs'],
    queryFn: () => getJson<{ tabs: PreparedTab[] }>('/api/meetings/tabs'),
  });
  const boards = useBoards();
  const favourites = useFavourites();
  const links = useLinks();
  const recent = useRecent();
  const here = (node: Parameters<typeof nodeHref>[0]) => {
    const href = nodeHref(node);
    return href && new URL(href, window.location.origin).href;
  };
  const offered = [
    ...(before.data?.tabs ?? []).map(({ address, title }) => ({
      title: title ?? shortened(address),
      address,
    })),
    ...(boards.data?.children ?? []).map((node) => ({ title: node.title, address: here(node) })),
    ...(favourites.data?.children ?? []).map((node) => ({
      title: node.title,
      address: here(node),
    })),
    ...(links.data?.links ?? []).map((node) => ({ title: node.title, address: here(node) })),
    ...(recent.data?.items ?? []).map((node) => ({ title: node.title, address: here(node) })),
  ];
  const seen = new Set(left);
  return offered.filter(({ title, address }) => {
    if (!/^https?:\/\//.test(address) || seen.has(address)) return false;
    seen.add(address);
    return Boolean(title);
  });
}

/** The address of a tab to share, written or chosen from what the user may mean. */
function TabAddress({
  value,
  left,
  onChange,
  onChosen,
}: {
  value: string;
  left: string[];
  onChange: (value: string) => void;
  onChosen: (address: string) => void;
}) {
  const { t } = useI18n();
  const list = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const typed = value.trim().toLowerCase();
  const offered = useOffered(left).filter(
    ({ title, address }) =>
      !typed || title.toLowerCase().includes(typed) || address.toLowerCase().includes(typed),
  );
  const shown = open && offered.length > 0;
  const chosen = (each: Offered) => {
    onChosen(each.address);
    setActive(-1);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!offered.length) return;
      event.preventDefault();
      setOpen(true);
      const next = active + (event.key === 'ArrowDown' ? 1 : -1);
      setActive(next >= offered.length ? -1 : next < -1 ? offered.length - 1 : next);
    } else if (event.key === 'Enter' && shown && offered[active]) {
      event.preventDefault();
      chosen(offered[active]);
    } else if (event.key === 'Escape' && shown) {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
    }
  };
  return (
    <div className="relative min-w-0 flex-1">
      <input
        value={value}
        role="combobox"
        autoComplete="off"
        spellCheck={false}
        aria-autocomplete="list"
        aria-expanded={shown}
        aria-controls={list}
        aria-activedescendant={shown && active >= 0 ? `${list}-${active}` : undefined}
        aria-label={t('meeting.tabAddress')}
        placeholder={t('meeting.tabAddress')}
        onChange={(event) => {
          onChange(event.target.value);
          setActive(-1);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className={`${field} w-full`}
      />
      {shown && (
        <div
          id={list}
          role="listbox"
          aria-label={t('meeting.tabAddress')}
          onMouseDown={(event) => event.preventDefault()}
          className="absolute top-full right-0 left-0 z-50 mt-1 max-h-72 overflow-y-auto rounded border border-line bg-raised p-1 text-ink shadow-lg"
        >
          {offered.map((each, index) => (
            <div
              key={each.address}
              id={`${list}-${index}`}
              role="option"
              aria-selected={index === active}
              title={each.address}
              onClick={() => chosen(each)}
              className="flex cursor-pointer flex-col rounded px-2 py-1.5 text-sm hover:bg-hover aria-selected:bg-selected"
            >
              <span className="truncate">{each.title}</span>
              <span className="truncate text-muted">{shortened(each.address)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
