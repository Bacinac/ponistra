import { useQuery } from '@tanstack/react-query';
import { Cake, CalendarPlus, ChevronRight, Mail, MapPin, Star } from 'lucide-react';
import { useId, useState } from 'react';
import { Link } from 'react-router';
import { getJson } from './api';
import { EventDialog } from './calendar';
import {
  BIRTHDAYS,
  colorOf,
  dayOf,
  formOf,
  HOLIDAYS,
  linkOf,
  nextOf,
  untilText,
  useCalendars,
  useHidden,
  useNow,
  useWindow,
  type Occurrence,
} from './calendarData';
import { MiniMonth } from './calendar';
import { Frame, Loading, PrimaryAction } from './frame';
import { useI18n } from './i18n';
import { JoinLink } from './meeting';
import { mailHref } from './search';
import { primaryButton } from './styles';
import { TasksTile } from './tasks';
import { useDark } from './theme';
import {
  errorMessage,
  Failure,
  type FoundNode,
  nodeHref,
  NodeIcon,
  placeText,
  PlaceLink,
  useFavourites,
  useRecent,
} from './tree';
import { correspondents, type Person, useAccounts } from './mailData';

type Dialog = { type: 'new' } | { type: 'event'; occurrence: Occurrence };

export function TodayPage() {
  const { t, language, formatDay } = useI18n();
  const now = useNow();
  const today = dayOf(now);
  const [hidden] = useHidden();
  const calendars = useCalendars();
  const shown = useWindow(today, today);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const events = (shown.data?.events ?? []).filter((each) => !hidden.has(each.calendar));
  const holidays = hidden.has(HOLIDAYS) ? [] : (shown.data?.holidays ?? []);
  const birthdays = hidden.has(BIRTHDAYS) ? [] : (shown.data?.birthdays ?? []);
  const writable = (calendars.data?.calendars ?? []).filter((each) => !each.read_only);
  const summary = [
    `${events.length} ${t(`today.event.${formOf(events.length, language)}`)}`,
    ...holidays.map((each) => each[language]),
    birthdays.length > 0
      ? `${birthdays.length} ${t(`today.birthday.${formOf(birthdays.length, language)}`)}`
      : null,
  ].filter(Boolean);
  return (
    <Frame
      title={t('rail.today')}
      folders={false}
      side={<MiniMonth day={today} view="day" />}
      primary={
        writable.length > 0 && (
          <PrimaryAction
            icon={CalendarPlus}
            label={t('calendar.newEvent')}
            onClick={() => setDialog({ type: 'new' })}
          />
        )
      }
    >
      <div className="flex w-full max-w-5xl flex-col gap-5">
        <div>
          <p className="text-2xl font-semibold first-letter:uppercase">{formatDay(now)}</p>
          {shown.data && <p className="text-sm text-muted">{summary.join(' · ')}</p>}
        </div>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          <div className="contents lg:flex lg:min-w-0 lg:flex-1 lg:flex-col lg:gap-4">
            <div className="order-1">
              <Schedule
                today={today}
                now={now}
                events={events}
                holidays={holidays}
                birthdays={birthdays}
                pending={shown.isPending}
                error={shown.error}
                onOpen={(occurrence) => setDialog({ type: 'event', occurrence })}
              />
            </div>
            <div className="order-3">
              <Waiting />
            </div>
            <div className="order-5">
              <Favourites />
            </div>
          </div>
          <div className="contents lg:flex lg:min-w-0 lg:flex-1 lg:flex-col lg:gap-4">
            <div className="order-2">
              <TasksTile />
            </div>
            <div className="order-4">
              <Recent />
            </div>
          </div>
        </div>
      </div>
      {dialog?.type === 'new' && (
        <EventDialog calendars={writable} start={{ day: today }} onClose={() => setDialog(null)} />
      )}
      {dialog?.type === 'event' && (
        <EventDialog
          calendars={writable}
          occurrence={dialog.occurrence}
          onClose={() => setDialog(null)}
        />
      )}
    </Frame>
  );
}

function Schedule({
  today,
  now,
  events,
  holidays,
  birthdays,
  pending,
  error,
  onOpen,
}: {
  today: string;
  now: Date;
  events: Occurrence[];
  holidays: { date: string; hr: string; en: string }[];
  birthdays: { contact: number; name: string; age: number | null }[];
  pending: boolean;
  error: Error | null;
  onOpen: (occurrence: Occurrence) => void;
}) {
  const { t, language, formatTime } = useI18n();
  const dark = useDark();
  const calendars = useCalendars();
  const byId = new Map((calendars.data?.calendars ?? []).map((each) => [each.id, each]));
  const heading = useId();
  const next = nextOf(events, now);
  const listed = [...events].sort(
    (a, b) => Number(b.all_day) - Number(a.all_day) || a.start.localeCompare(b.start),
  );
  const nowAt = now.getTime();
  const past = (each: Occurrence) => !each.all_day && new Date(each.end).getTime() <= nowAt;
  const started = (each: Occurrence) => new Date(each.start).getTime() <= nowAt;
  const nowLineBefore = listed.find((each) => !each.all_day && !started(each));
  const nowLineLast = !nowLineBefore && listed.some((each) => !each.all_day);
  const key = (each: Occurrence) => `${each.event}:${each.recurrence_id ?? ''}`;
  return (
    <section aria-labelledby={heading} className="flex flex-col gap-2 rounded-xl bg-raised p-3">
      <div className="flex items-center gap-2 px-2">
        <h2 id={heading} className="font-semibold">
          {t('today.schedule')}
        </h2>
        <Link
          to={`/calendar/day/${today}`}
          className="ml-auto flex items-center gap-0.5 rounded text-sm text-link hover:underline"
        >
          {t('rail.calendar')}
          <ChevronRight size={16} aria-hidden />
        </Link>
      </div>
      {pending ? (
        <Loading />
      ) : error ? (
        <p className="px-2 text-sm text-danger">{errorMessage(error, t)}</p>
      ) : listed.length + holidays.length + birthdays.length === 0 ? (
        <p className="px-2 text-sm text-muted">{t('today.noEvents')}</p>
      ) : (
        <ul className="flex flex-col">
          {holidays.map((each) => (
            <li key={each.hr} className="px-2 py-1 text-sm text-link">
              {each[language]}
            </li>
          ))}
          {birthdays.map((each) => (
            <li key={each.contact}>
              <Link
                to={`/contacts/${each.contact}`}
                className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-hover"
              >
                <Cake size={14} aria-hidden className="text-muted" />
                {t('calendar.birthday')}: {each.name}
                {each.age !== null && ` (${each.age})`}
              </Link>
            </li>
          ))}
          {listed.map((occurrence) => {
            const link = linkOf(occurrence);
            const upcoming = occurrence === next;
            return (
              <li key={key(occurrence)} className="flex flex-col">
                {occurrence === nowLineBefore && <NowLine now={now} />}
                <div
                  className={`flex min-w-0 items-center gap-3 rounded px-2 ${
                    upcoming ? 'bg-selected' : ''
                  } ${past(occurrence) ? 'opacity-60' : ''}`}
                >
                  <button
                    type="button"
                    onClick={() => onOpen(occurrence)}
                    className="flex min-w-0 flex-1 items-center gap-3 py-1.5 text-left hover:underline"
                  >
                    <span className="flex w-12 shrink-0 flex-col text-sm text-muted">
                      {occurrence.all_day ? (
                        <span className="text-xs">{t('calendar.allDay')}</span>
                      ) : (
                        <>
                          <span>{formatTime(new Date(occurrence.start))}</span>
                          <span className="text-xs">{formatTime(new Date(occurrence.end))}</span>
                        </>
                      )}
                    </span>
                    <span
                      aria-hidden
                      className="size-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: colorOf(byId.get(occurrence.calendar), dark) }}
                    />
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="flex min-w-0 items-center gap-2">
                        <span
                          className={`truncate text-sm font-medium ${
                            occurrence.status === 'cancelled' ? 'line-through' : ''
                          }`}
                        >
                          {occurrence.summary || '—'}
                        </span>
                        {occurrence.response === 'needs-action' && (
                          <span className="shrink-0 rounded bg-panel px-1.5 text-xs text-muted">
                            {t('calendar.awaiting')}
                          </span>
                        )}
                      </span>
                      <span className="flex items-center gap-1 truncate text-xs text-muted">
                        {upcoming && (
                          <span>
                            {started(occurrence)
                              ? t('today.now')
                              : untilText(language, occurrence.start, now)}
                          </span>
                        )}
                        {upcoming && occurrence.location && !link && <span>·</span>}
                        {occurrence.location && !link && (
                          <>
                            <MapPin size={10} aria-hidden />
                            <span className="truncate">{occurrence.location}</span>
                          </>
                        )}
                      </span>
                    </span>
                  </button>
                  {link && upcoming && (
                    <JoinLink link={link} className={`${primaryButton} shrink-0`} />
                  )}
                </div>
              </li>
            );
          })}
          {nowLineLast && (
            <li>
              <NowLine now={now} />
            </li>
          )}
        </ul>
      )}
    </section>
  );
}

function NowLine({ now }: { now: Date }) {
  const { t, formatTime } = useI18n();
  return (
    <div
      aria-hidden
      className="my-1 flex items-center gap-2 px-2 text-xs font-semibold text-danger"
    >
      {t('today.now')} {formatTime(now)}
      <span className="h-px flex-1 bg-danger" />
    </div>
  );
}

interface WaitingMessage {
  id: number;
  folder: number;
  account: number | null;
  subject: string;
  sender: Partial<Person>;
  to: Person[];
  date: string;
  seen: boolean;
  flagged: boolean;
}

function Waiting() {
  const { t, formatDate, formatNumber } = useI18n();
  const heading = useId();
  const waiting = useQuery({
    queryKey: ['mail', 'waiting'],
    queryFn: () => getJson<{ messages: WaitingMessage[]; count: number }>('/api/mail/waiting'),
  });
  const accounts = useAccounts().data?.accounts ?? [];
  return (
    <section aria-labelledby={heading} className="flex flex-col gap-2 rounded-xl bg-raised p-3">
      <div className="flex items-center gap-2 px-2">
        <h2 id={heading} className="font-semibold">
          {t('today.mail')}
        </h2>
        <Link
          to="/mail"
          className="ml-auto flex items-center gap-0.5 rounded text-sm text-link hover:underline"
        >
          {t('rail.mail')}
          {waiting.data &&
            waiting.data.count > waiting.data.messages.length &&
            ` (${formatNumber(waiting.data.count)})`}
          <ChevronRight size={16} aria-hidden />
        </Link>
      </div>
      {waiting.isPending ? (
        <Loading />
      ) : waiting.isError ? (
        <Failure error={waiting.error} />
      ) : waiting.data.count === 0 ? (
        <p className="flex items-center gap-2 px-2 text-sm text-muted">
          <Mail size={14} aria-hidden />
          {t('today.noMail')}
        </p>
      ) : (
        <ul className="flex flex-col">
          {waiting.data.messages.map((message) => (
            <li key={message.id}>
              <Link
                to={mailHref(message, accounts)}
                className="flex min-w-0 items-center gap-3 rounded px-2 py-2 hover:bg-hover"
              >
                {message.flagged ? (
                  <Star
                    size={16}
                    role="img"
                    aria-label={t('favourites.title')}
                    className="shrink-0 text-accent"
                  />
                ) : (
                  <Mail size={16} aria-hidden className="shrink-0 text-muted" />
                )}
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className={`truncate ${message.seen ? '' : 'font-medium'}`}>
                    {message.subject || t('mail.noSubject')}
                  </span>
                  <span className="truncate text-xs text-muted">
                    {correspondents(message, 'inbox')}
                  </span>
                </span>
                <span className="hidden shrink-0 text-xs text-muted sm:block">
                  {formatDate(message.date)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function NodeRows({ nodes }: { nodes: FoundNode[] }) {
  const { t, formatDate } = useI18n();
  return (
    <ul className="flex flex-col">
      {nodes.map((node) => (
        <li key={node.id}>
          <PlaceLink
            to={nodeHref(node)}
            className="flex min-w-0 items-center gap-3 rounded px-2 py-2 hover:bg-hover"
          >
            <NodeIcon node={node} decorative />
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate font-medium">{node.title}</span>
              <span className="truncate text-xs text-muted">{placeText(node, t)}</span>
            </span>
            <span className="hidden shrink-0 flex-col items-end text-xs text-muted sm:flex">
              <span>{formatDate(node.updated_at)}</span>
              {node.updated_by && <span>{node.updated_by.name}</span>}
            </span>
          </PlaceLink>
        </li>
      ))}
    </ul>
  );
}

const FAVOURITES_SHOWN = 8;

/** Shows nothing until the user keeps something at hand. */
function Favourites() {
  const { t, formatNumber } = useI18n();
  const favourites = useFavourites();
  const heading = useId();
  if (favourites.isPending) return null;
  if (favourites.isError) return <Failure error={favourites.error} />;
  if (favourites.data.children.length === 0) return null;
  return (
    <section aria-labelledby={heading} className="flex flex-col gap-2 rounded-xl bg-raised p-3">
      <div className="flex items-center gap-2 px-2">
        <h2 id={heading} className="font-semibold">
          {t('favourites.title')}
        </h2>
        <Link
          to="/favourites"
          aria-label={t('favourites.title')}
          className="ml-auto flex items-center gap-0.5 rounded text-sm text-link hover:underline"
        >
          {formatNumber(favourites.data.children.length)}
          <ChevronRight size={16} aria-hidden />
        </Link>
      </div>
      <NodeRows nodes={favourites.data.children.slice(0, FAVOURITES_SHOWN)} />
    </section>
  );
}

function Recent() {
  const { t } = useI18n();
  const recent = useRecent();
  const heading = useId();
  return (
    <section aria-labelledby={heading} className="flex flex-col gap-2 rounded-xl bg-raised p-3">
      <div className="flex items-center gap-2 px-2">
        <h2 id={heading} className="font-semibold">
          {t('today.recent')}
        </h2>
        <Link
          to="/documents"
          className="ml-auto flex items-center gap-0.5 rounded text-sm text-link hover:underline"
        >
          {t('rail.documents')}
          <ChevronRight size={16} aria-hidden />
        </Link>
      </div>
      {recent.isPending ? (
        <Loading />
      ) : recent.isError ? (
        <Failure error={recent.error} />
      ) : recent.data.items.length === 0 ? (
        <p className="px-2 text-sm text-muted">{t('today.none')}</p>
      ) : (
        <NodeRows nodes={recent.data.items} />
      )}
    </section>
  );
}
