import { useMutation, useQuery } from '@tanstack/react-query';
import { Download, Folder, Paperclip } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import Markdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { answered, ApiError, csrfToken, getJson, postJson } from './api';
import { formatSize } from './explorer';
import { Loading } from './frame';
import { useI18n } from './i18n';
import { HtmlBody } from './mailBody';
import { field, iconButton, primaryButton } from './styles';
import { errorMessage, Failure } from './tree';

/** What a file holds, shown by its kind rather than as its bytes (D23): read by the server from
 * the bytes, wherever the file is kept. */
export type HeldKind = 'picture' | 'archive' | 'message' | 'cards' | 'events' | 'markdown';

const PICTURES = [
  'image/bmp',
  'image/vnd.microsoft.icon',
  'image/tiff',
  'image/vnd.adobe.photoshop',
];
const ARCHIVES = [
  'application/zip',
  'application/x-tar',
  'application/gzip',
  'application/x-bzip2',
  'application/x-xz',
  'application/zstd',
  'application/x-lz4',
  'application/x-7z-compressed',
  'application/vnd.rar',
  'application/x-iso9660-image',
  'application/vnd.ms-cab-compressed',
  'application/x-lzh-compressed',
  'application/x-xar',
];
const MESSAGES = ['eml', 'mht', 'mhtml'];
const MARKDOWN_NAMES = ['md', 'markdown'];

export function heldKind(mediaType: string | null, extension: string | null): HeldKind | null {
  const named = extension?.toLowerCase() ?? '';
  if (!mediaType) return null;
  if (PICTURES.includes(mediaType)) return 'picture';
  if (ARCHIVES.includes(mediaType)) return 'archive';
  if (mediaType === 'application/vnd.ms-outlook') return 'message';
  if (mediaType === 'text/vcard') return 'cards';
  if (mediaType === 'text/calendar') return 'events';
  if (mediaType === 'text/plain' && MESSAGES.includes(named)) return 'message';
  if (mediaType === 'text/plain' && MARKDOWN_NAMES.includes(named)) return 'markdown';
  return null;
}

interface Entry {
  n: number;
  path: string;
  size: number | null;
  modified: string | null;
  folder: boolean;
}

interface Attachment {
  part: string;
  name: string;
  type: string;
  size: number;
}

interface Point {
  kind: 'email' | 'phone' | 'url' | 'address';
  label: string;
  value: string;
}

interface Person {
  name: string;
  organisation: string;
  title: string;
  points: Point[];
  photo: string | null;
}

interface Happening {
  summary: string;
  location: string;
  description: string;
  all_day: boolean;
  start: string | null;
  end: string | null;
  repeats: boolean;
  organizer: string;
}

type Held =
  | { kind: 'picture'; whole: string }
  | { kind: 'archive'; entries: Entry[]; count: number }
  | {
      kind: 'message' | 'outlook';
      subject: string;
      from: string;
      to: string;
      cc: string;
      date: string | null;
      html: string | null;
      text: string | null;
      remote: boolean;
      attachments: Attachment[];
    }
  | { kind: 'cards'; people: Person[]; count: number }
  | { kind: 'events'; name: string; events: Happening[]; count: number };

/** As much of a text file as a glance shows. */
const GLANCED_TEXT = 64 * 1024;
/** Entries a glance lists of an archive; the page lists all the server read. */
const GLANCED_ENTRIES = 50;

/** The file's contents by their kind; `base` is the file's address, under which the server
 * serves what it shows (`/shown`) and its text (`/text`). */
export function HeldView({
  base,
  kind,
  title,
  compact = false,
}: {
  base: string;
  kind: HeldKind;
  title: string;
  compact?: boolean;
}) {
  if (kind === 'picture')
    return (
      <img
        src={`${base}/shown/whole`}
        alt={title}
        className={
          compact
            ? 'max-h-96 w-full shrink-0 rounded border border-line object-contain'
            : 'max-h-full max-w-full object-contain'
        }
      />
    );
  if (kind === 'markdown') return <MarkdownText base={base} compact={compact} />;
  return <Read base={base} title={title} compact={compact} />;
}

function Read({ base, title, compact }: { base: string; title: string; compact: boolean }) {
  const [password, setPassword] = useState<string | null>(null);
  const read = useQuery({
    queryKey: ['held', base],
    queryFn: () => getJson<Held>(`${base}/shown`),
    retry: false,
  });
  const opened = useMutation({
    mutationFn: (given: string) => postJson<Held>(`${base}/shown`, { password: given }),
    onSuccess: (_, given) => setPassword(given),
  });
  const locked =
    read.error instanceof ApiError && read.error.code === 'archive_locked' && !opened.data;
  if (read.isPending) return <Loading />;
  if (locked)
    return <Locked onOpen={opened.mutate} pending={opened.isPending} error={opened.error} />;
  const held = opened.data ?? read.data;
  if (!held) return <Failure error={read.error!} />;
  switch (held.kind) {
    case 'archive':
      return <Archive base={base} held={held} password={password} compact={compact} />;
    case 'message':
    case 'outlook':
      return <Message base={base} held={held} title={title} />;
    case 'cards':
      return <Cards people={held.people} count={held.count} />;
    case 'events':
      return <Events name={held.name} events={held.events} count={held.count} />;
    default:
      return null;
  }
}

function Locked({
  onOpen,
  pending,
  error,
}: {
  onOpen: (password: string) => void;
  pending: boolean;
  error: Error | null;
}) {
  const { t } = useI18n();
  const [given, setGiven] = useState('');
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (given) onOpen(given);
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-2 text-sm">
      <p>{t('shown.locked')}</p>
      <div className="flex gap-2">
        <input
          type="password"
          autoComplete="off"
          aria-label={t('shown.password')}
          placeholder={t('shown.password')}
          value={given}
          onChange={(event) => setGiven(event.target.value)}
          className={`${field} min-w-0 flex-1`}
        />
        <button type="submit" disabled={!given || pending} className={primaryButton}>
          {t('shown.open')}
        </button>
      </div>
      {error && <p className="text-danger">{errorMessage(error, t)}</p>}
    </form>
  );
}

function Archive({
  base,
  held,
  password,
  compact,
}: {
  base: string;
  held: { entries: Entry[]; count: number };
  password: string | null;
  compact: boolean;
}) {
  const { t, formatNumber, formatDate } = useI18n();
  const [failed, setFailed] = useState<Error | null>(null);
  const shown = compact ? held.entries.slice(0, GLANCED_ENTRIES) : held.entries;
  if (held.count === 0) return <p className="text-sm text-muted">{t('shown.emptyArchive')}</p>;
  return (
    <div className="flex min-h-0 flex-col gap-1 text-sm">
      <ul
        className={`overflow-auto rounded border border-line ${compact ? 'max-h-96 shrink-0' : 'flex-1'}`}
      >
        {shown.map((entry) => {
          const depth = entry.path.replace(/\/$/, '').split('/').length - 1;
          const name = entry.path.replace(/\/$/, '').split('/').pop() || entry.path;
          return (
            <li
              key={entry.n}
              className="flex items-center gap-2 border-b border-line px-2 py-1 last:border-b-0"
              style={{ paddingLeft: `${0.5 + depth}rem` }}
            >
              {entry.folder && <Folder size={14} aria-hidden className="shrink-0 text-muted" />}
              <span className="min-w-0 flex-1 truncate" title={entry.path}>
                {name}
              </span>
              {!compact && entry.modified && (
                <span className="shrink-0 text-xs text-muted">{formatDate(entry.modified)}</span>
              )}
              {entry.size !== null && (
                <span className="shrink-0 text-xs text-muted">
                  {formatSize(entry.size, formatNumber)}
                </span>
              )}
              {!entry.folder && (
                <Taken
                  href={`${base}/shown/${entry.n}`}
                  name={name}
                  password={password}
                  onFailed={setFailed}
                />
              )}
            </li>
          );
        })}
      </ul>
      {shown.length < held.count && (
        <p className="text-xs text-muted">
          {t('shown.more')
            .replace('{shown}', formatNumber(shown.length))
            .replace('{count}', formatNumber(held.count))}
        </p>
      )}
      {failed && <p className="text-danger">{errorMessage(failed, t)}</p>}
    </div>
  );
}

/** A part saved: by its address, or, where the archive asked for a password, fetched with it. */
function Taken({
  href,
  name,
  password,
  onFailed,
}: {
  href: string;
  name: string;
  password: string | null;
  onFailed?: (error: Error) => void;
}) {
  const { t } = useI18n();
  const label = `${t('file.download')} ${name}`;
  if (password === null)
    return (
      <a href={href} title={label} aria-label={label} className={`${iconButton} -my-1`}>
        <Download size={14} aria-hidden />
      </a>
    );
  const save = async () => {
    const response = await answered(href, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify({ password }),
    });
    if (!response.ok) {
      const code = ((await response.json().catch(() => ({}))) as { error?: string }).error;
      throw new ApiError(href, response.status, code);
    }
    const address = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = address;
    link.download = name;
    link.click();
    URL.revokeObjectURL(address);
  };
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={() => save().catch((error: unknown) => onFailed?.(error as Error))}
      className={`${iconButton} -my-1`}
    >
      <Download size={14} aria-hidden />
    </button>
  );
}

function Message({
  base,
  held,
  title,
}: {
  base: string;
  held: Extract<Held, { kind: 'message' | 'outlook' }>;
  title: string;
}) {
  const { t, formatDate, formatNumber } = useI18n();
  return (
    <div className="flex min-w-0 flex-col gap-2 text-sm">
      <p className="font-semibold break-words">{held.subject || t('mail.noSubject')}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        {held.from && (
          <>
            <dt className="text-muted">{t('mail.from')}</dt>
            <dd className="break-words">{held.from}</dd>
          </>
        )}
        {held.to && (
          <>
            <dt className="text-muted">{t('mail.to')}</dt>
            <dd className="break-words">{held.to}</dd>
          </>
        )}
        {held.cc && (
          <>
            <dt className="text-muted">{t('mail.cc')}</dt>
            <dd className="break-words">{held.cc}</dd>
          </>
        )}
        {held.date && (
          <>
            <dt className="text-muted">{t('mail.date')}</dt>
            <dd>{formatDate(held.date)}</dd>
          </>
        )}
      </dl>
      {held.attachments.length > 0 && (
        <ul className="flex flex-col gap-1">
          {held.attachments.map((each) => (
            <li key={each.part} className="flex items-center gap-2">
              <Paperclip size={14} aria-hidden className="shrink-0 text-muted" />
              <span className="min-w-0 flex-1 truncate">{each.name}</span>
              <span className="shrink-0 text-xs text-muted">
                {formatSize(each.size, formatNumber)}
              </span>
              <Taken href={`${base}/shown/${each.part}`} name={each.name} password={null} />
            </li>
          ))}
        </ul>
      )}
      {held.html !== null ? (
        <HtmlBody title={title} html={held.html} />
      ) : (
        <p className="break-words whitespace-pre-wrap">{held.text}</p>
      )}
    </div>
  );
}

const POINT_LINKS: Partial<Record<Point['kind'], (value: string) => string>> = {
  email: (value) => `mailto:${value}`,
  phone: (value) => `tel:${value.replace(/\s/g, '')}`,
};

function Cards({ people, count }: { people: Person[]; count: number }) {
  const { t, formatNumber } = useI18n();
  if (people.length === 0) return <p className="text-sm text-muted">{t('shown.noPeople')}</p>;
  return (
    <div className="flex flex-col gap-2 text-sm">
      <ul className="flex flex-col gap-3">
        {people.map((person, index) => (
          <li key={index} className="flex gap-3">
            {person.photo ? (
              <img
                src={person.photo}
                alt=""
                className="size-12 shrink-0 rounded-full object-cover"
              />
            ) : (
              <span
                aria-hidden
                className="flex size-12 shrink-0 items-center justify-center rounded-full bg-raised font-semibold text-muted"
              >
                {person.name.slice(0, 1).toUpperCase()}
              </span>
            )}
            <div className="flex min-w-0 flex-col">
              <span className="font-semibold break-words">{person.name}</span>
              {(person.title || person.organisation) && (
                <span className="text-muted">
                  {[person.title, person.organisation].filter(Boolean).join(' · ')}
                </span>
              )}
              {person.points.map((point, at) => {
                const link = POINT_LINKS[point.kind];
                return (
                  <span key={at} className="break-words">
                    {point.label && <span className="text-muted">{point.label}: </span>}
                    {link ? (
                      <a href={link(point.value)} className="text-link hover:underline">
                        {point.value}
                      </a>
                    ) : (
                      point.value
                    )}
                  </span>
                );
              })}
            </div>
          </li>
        ))}
      </ul>
      {people.length < count && (
        <p className="text-xs text-muted">
          {t('shown.more')
            .replace('{shown}', formatNumber(people.length))
            .replace('{count}', formatNumber(count))}
        </p>
      )}
    </div>
  );
}

/** The last day an all-day event covers: iCalendar's end is the day after it. */
function lastDay(start: string, end: string | null): string {
  if (!end || end <= start) return start;
  const day = new Date(`${end}T12:00:00Z`);
  day.setUTCDate(day.getUTCDate() - 1);
  return day.toISOString().slice(0, 10);
}

function When({ event }: { event: Happening }) {
  const { t, formatDate, formatDays, formatTime } = useI18n();
  if (!event.start) return null;
  if (event.all_day)
    return (
      <span>
        {formatDays(event.start, lastDay(event.start, event.end))} · {t('calendar.allDay')}
      </span>
    );
  if (!event.end) return <span>{formatDate(event.start)}</span>;
  const starts = new Date(event.start);
  const ends = new Date(event.end);
  const sameDay = starts.toDateString() === ends.toDateString();
  return (
    <span>
      {formatDate(event.start)} – {sameDay ? formatTime(ends) : formatDate(event.end)}
    </span>
  );
}

function Events({ name, events, count }: { name: string; events: Happening[]; count: number }) {
  const { t, formatNumber } = useI18n();
  if (events.length === 0) return <p className="text-sm text-muted">{t('shown.noEvents')}</p>;
  return (
    <div className="flex flex-col gap-2 text-sm">
      {name && <p className="font-semibold">{name}</p>}
      <ul className="flex flex-col gap-2">
        {events.map((event, index) => (
          <li key={index} className="flex flex-col rounded border border-line px-2 py-1.5">
            <span className="font-semibold break-words">{event.summary}</span>
            <span className="text-muted">
              <When event={event} />
              {event.repeats && ` · ${t('shown.repeats')}`}
            </span>
            {event.location && <span className="break-words">{event.location}</span>}
            {event.organizer && (
              <span className="break-words text-muted">
                {t('calendar.organizer')}: {event.organizer}
              </span>
            )}
          </li>
        ))}
      </ul>
      {events.length < count && (
        <p className="text-xs text-muted">
          {t('shown.more')
            .replace('{shown}', formatNumber(events.length))
            .replace('{count}', formatNumber(count))}
        </p>
      )}
    </div>
  );
}

const MARKDOWN: Components = {
  a: ({ node: _, ...props }) => (
    <a {...props} target="_blank" rel="noopener noreferrer" className="text-link underline" />
  ),
  // An image of a text file is fetched from wherever it names, which nothing here may do.
  img: ({ node: _, src, alt }) =>
    typeof src === 'string' && src.startsWith('data:') ? <img src={src} alt={alt ?? ''} /> : null,
  h1: ({ node: _, ...props }) => <h1 {...props} className="mt-4 mb-2 text-xl font-semibold" />,
  h2: ({ node: _, ...props }) => <h2 {...props} className="mt-4 mb-2 text-lg font-semibold" />,
  h3: ({ node: _, ...props }) => <h3 {...props} className="mt-3 mb-1 font-semibold" />,
  p: ({ node: _, ...props }) => <p {...props} className="my-2" />,
  ul: ({ node: _, ...props }) => <ul {...props} className="my-2 list-disc pl-6" />,
  ol: ({ node: _, ...props }) => <ol {...props} className="my-2 list-decimal pl-6" />,
  blockquote: ({ node: _, ...props }) => (
    <blockquote {...props} className="my-2 border-l-2 border-line pl-3 text-muted" />
  ),
  code: ({ node: _, ...props }) => (
    <code {...props} className="rounded bg-raised px-1 font-mono text-[0.9em]" />
  ),
  pre: ({ node: _, ...props }) => (
    <pre {...props} className="my-2 overflow-x-auto rounded bg-raised p-2 text-xs" />
  ),
  table: ({ node: _, ...props }) => (
    <div className="my-2 overflow-x-auto">
      <table {...props} className="border-collapse" />
    </div>
  ),
  th: ({ node: _, ...props }) => (
    <th {...props} className="border border-line px-2 py-1 text-left font-semibold" />
  ),
  td: ({ node: _, ...props }) => <td {...props} className="border border-line px-2 py-1" />,
  hr: () => <hr className="my-4 border-line" />,
};

function MarkdownText({ base, compact }: { base: string; compact: boolean }) {
  const text = useQuery({
    queryKey: ['held', base, 'text', compact],
    queryFn: () =>
      getJson<{ text: string }>(compact ? `${base}/text?most=${GLANCED_TEXT}` : `${base}/text`),
  });
  if (text.isPending) return <Loading />;
  if (text.isError) return <Failure error={text.error} />;
  return (
    <div
      className={`min-w-0 text-sm break-words ${compact ? 'max-h-96 shrink-0 overflow-auto rounded border border-line p-3' : 'mx-auto w-full max-w-3xl p-6'}`}
    >
      <Markdown remarkPlugins={[remarkGfm]} components={MARKDOWN}>
        {text.data.text}
      </Markdown>
    </div>
  );
}
