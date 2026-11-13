import { useMutation } from '@tanstack/react-query';
import { Check, Copy, ExternalLink, Video, X } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { postJson } from './api';
import { useSession } from './auth';
import { useI18n } from './i18n';
import { useMeetingWindow } from './meetingWindow';
import { button, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';

export interface Meeting {
  id: string;
  title: string;
  link: string;
  /** What its people write to each other, kept once the call ends. */
  conversation: string;
}

/** The page of this installation's meeting a link leads to, or null for another service's. The
    link carries the installation's outside address, whichever one the user came by. */
function useMeetingPath(): (link: string) => string | null {
  const site = useSession().data?.site;
  return (link) => {
    try {
      const url = new URL(link);
      const ours = url.origin === window.location.origin || url.origin === site;
      return ours && /^\/meet\/[0-9a-f-]{36}$/.test(url.pathname) ? url.pathname : null;
    } catch {
      return null;
    }
  };
}

/** Joining a meeting: PONISTRA's opens here, another service's in a tab of its own. A compact
    one is its icon alone. */
export function JoinLink({
  link,
  className,
  compact,
}: {
  link: string;
  className: string;
  compact?: boolean;
}) {
  const { t } = useI18n();
  const path = useMeetingPath()(link);
  const Icon = path || compact ? Video : ExternalLink;
  const content = (
    <>
      <Icon size={compact ? 16 : 14} aria-hidden />
      {!compact && t('meeting.join')}
    </>
  );
  const named = compact ? { 'aria-label': t('meeting.join'), title: t('meeting.join') } : {};
  return path ? (
    <MeetingLink path={path} className={className} {...named}>
      {content}
    </MeetingLink>
  ) : (
    <a href={link} target="_blank" rel="noopener noreferrer" className={className} {...named}>
      {content}
    </a>
  );
}

/** A link into one of this installation's meetings, which a plain click opens beside the app. */
export function MeetingLink({
  path,
  children,
  ...rest
}: {
  path: string;
  className: string;
  children: ReactNode;
  'aria-label'?: string;
  title?: string;
}) {
  const meetingWindow = useMeetingWindow();
  return (
    <Link
      to={path}
      onClick={(event) => {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
          return;
        event.preventDefault();
        meetingWindow.open(path);
      }}
      {...rest}
    >
      {children}
    </Link>
  );
}

function hostOf(link: string): string {
  try {
    return new URL(link).host;
  } catch {
    return link;
  }
}

export function CopyLink({ link }: { link: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button type="button" onClick={() => void copy()} className={button}>
      {copied ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}
      {t(copied ? 'meeting.copied' : 'meeting.copyLink')}
    </button>
  );
}

/** An event's way in online: a meeting of PONISTRA's made for it, or another service's. */
export function ConferenceField({
  link,
  title,
  editable,
  onChange,
}: {
  link: string;
  title: string;
  editable: boolean;
  onChange: (link: string) => void;
}) {
  const { t } = useI18n();
  const meetingPath = useMeetingPath();
  const make = useMutation({
    mutationFn: () => postJson<Meeting>('/api/meetings', { title: title.trim() }),
    onSuccess: (made) => onChange(made.link),
  });
  if (!link && !editable) return null;
  return (
    <fieldset className="flex flex-col gap-1 text-sm">
      <legend className="mb-1 text-muted">{t('calendar.field.conference')}</legend>
      {link ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="min-w-0 flex-1 truncate">
            {meetingPath(link) ? t('meeting.ours') : hostOf(link)}
          </span>
          <JoinLink link={link} className={primaryButton} />
          <CopyLink link={link} />
          {editable && (
            <button
              type="button"
              onClick={() => onChange('')}
              aria-label={t('meeting.remove')}
              title={t('meeting.remove')}
              className={iconButton}
            >
              <X size={16} aria-hidden />
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => make.mutate()}
          disabled={make.isPending}
          className={`${button} self-start`}
        >
          <Video size={14} aria-hidden />
          {t('meeting.add')}
        </button>
      )}
      {make.error && <p className="text-xs text-danger">{errorMessage(make.error, t)}</p>}
    </fieldset>
  );
}
