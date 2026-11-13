import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Cake,
  CalendarPlus,
  Check,
  CircleHelp,
  ChevronLeft,
  ChevronRight,
  Lock,
  MapPin,
  Pencil,
  Plus,
  Repeat as RepeatIcon,
  ListTodo,
  Settings,
  Trash2,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useId, useMemo, useState, type CSSProperties, type FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { ContextMenuArea, MenuItem } from './menu';
import { useMenuPress } from './press';
import { Recipients } from './recipients';
import {
  BIRTHDAYS,
  HOLIDAYS,
  RESPONSES,
  ZONE,
  respond,
  type Response,
  colorCount,
  colorOf,
  dayOf,
  heldBy,
  useCalendars,
  type Calendars,
  useChanged,
  useDaysOff,
  useFree,
  useOffers,
  useHidden,
  useNow,
  useResources,
  useShownResources,
  shownOf,
  useWindow,
  type Calendar,
  type Detail,
  type Occurrence,
  type Resource,
  type Window,
} from './calendarData';
import { Cancel, Labelled, Modal, Picker } from './dialogs';
import { Frame, Loading, PrimaryAction, useWide } from './frame';
import { lastDay } from './away';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { ConferenceField } from './meeting';
import { PlainBody } from './plain';
import {
  DAYS_OFF,
  REPEATS,
  fitted,
  placeOf,
  repeatOf,
  ruleOf,
  untilOf,
  type DayOff,
  type Repeat,
} from './recurrence';
import { button, dangerButton, field, iconButton, primaryButton } from './styles';
import { TaskDialog, taskShown, useTasks, type Task } from './tasks';
import { useDark } from './theme';
import { codeText, errorMessage } from './tree';
import { BoxContext, inBox, type Person, useBox } from './mailData';
import { BoxLinks } from './mailShared';

export const VIEWS = ['month', 'week', 'day', 'agenda'] as const;
export type View = (typeof VIEWS)[number];
const HOUR = 48;
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);
const FIRST_SHOWN = 7;
const AGENDA_DAYS = 30;
const SHOWN_IN_CELL = 3;
const REMINDERS = ['', '0', '5', '10', '15', '30', '60', '120', '1440'] as const;
const SCOPES = ['this', 'following', 'all'] as const;
type Scope = (typeof SCOPES)[number];

function fromDay(day: string): Date {
  const [year, month, date] = day.split('-').map(Number);
  return new Date(year, month - 1, date);
}

function shifted(day: string, days: number): string {
  const date = fromDay(day);
  date.setDate(date.getDate() + days);
  return dayOf(date);
}

function mondayOf(day: string): string {
  const date = fromDay(day);
  return shifted(day, -((date.getDay() + 6) % 7));
}

function monthOf(day: string): string {
  return day.slice(0, 7);
}

function shiftedMonths(day: string, months: number): string {
  const date = fromDay(day);
  const kept = date.getDate();
  date.setDate(1);
  date.setMonth(date.getMonth() + months);
  const last = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
  date.setDate(Math.min(kept, last));
  return dayOf(date);
}

function timeOf(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function minutesOf(date: Date): number {
  return date.getHours() * 60 + date.getMinutes();
}

/** The days a month view shows: six weeks from the Monday on or before the first. */
function monthGrid(day: string): string[] {
  const first = mondayOf(`${monthOf(day)}-01`);
  return Array.from({ length: 42 }, (_, index) => shifted(first, index));
}

function spanOf(view: View, day: string): [string, string] {
  switch (view) {
    case 'month': {
      const grid = monthGrid(day);
      return [grid[0], grid[grid.length - 1]];
    }
    case 'week': {
      const monday = mondayOf(day);
      return [monday, shifted(monday, 6)];
    }
    case 'day':
      return [day, day];
    case 'agenda':
      return [day, shifted(day, AGENDA_DAYS - 1)];
  }
}

/** The days an occurrence touches among the days shown. */
function daysOf(occurrence: Occurrence, first: string, last: string): string[] {
  const start = occurrence.all_day ? occurrence.start : dayOf(new Date(occurrence.start));
  const end = occurrence.all_day ? occurrence.end : dayOf(new Date(occurrence.end));
  const days: string[] = [];
  for (let day = start < first ? first : start; day <= end && day <= last; day = shifted(day, 1)) {
    days.push(day);
  }
  return days.length ? days : [start];
}

type Dialog =
  | { type: 'new'; day: string; time?: string; allDay?: boolean }
  | { type: 'event'; occurrence: Occurrence }
  | { type: 'calendar'; calendar?: Calendar }
  | { type: 'task'; task: Task };

export function CalendarPage() {
  const [search] = useSearchParams();
  const box = Number(search.get('box')) || null;
  return (
    <BoxContext key={box ?? 0} value={box}>
      <CalendarShown />
    </BoxContext>
  );
}

function CalendarShown() {
  const { t, formatMonth, formatDays, formatDay } = useI18n();
  const box = useBox();
  const navigate = useNavigate();
  const params = useParams();
  const today = dayOf(new Date());
  const wide = useWide();
  const view = (VIEWS as readonly string[]).includes(params.view ?? '')
    ? (params.view as View)
    : wide
      ? 'month'
      : 'agenda';
  const day = /^\d{4}-\d{2}-\d{2}$/.test(params.date ?? '') ? params.date! : today;
  const [first, last] = spanOf(view, day);
  const calendars = useCalendars();
  const resources = useResources();
  const tasks = useTasks();
  const [hidden, toggleHidden] = useHidden();
  const [shownResources, toggleResource] = useShownResources();
  const shown = useWindow(first, last, [...shownResources]);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [query, setQuery] = useSearchParams();
  const wanted = Number(query.get('event'));
  useEffect(() => {
    if (!wanted || !shown.data || shown.isFetching) return;
    const found = shown.data.events.find((each) => each.event === wanted || each.master === wanted);
    if (found) setDialog({ type: 'event', occurrence: found });
    const rest = new URLSearchParams(query);
    rest.delete('event');
    setQuery(rest, { replace: true });
  }, [wanted, shown.data, shown.isFetching, query, setQuery]);
  const byId = useMemo(
    () => new Map((calendars.data?.calendars ?? []).map((each) => [each.id, each])),
    [calendars.data],
  );
  const visible = useMemo(() => {
    const named = new Map((resources.data?.resources ?? []).map((each) => [each.id, each.name]));
    const held = (shown.data?.bookings ?? []).map((each) =>
      heldBy(each, named.get(each.resource) ?? ''),
    );
    const due = (box === null ? (tasks.data?.tasks ?? []) : [])
      .filter((each) => each.due !== null && each.due >= first && each.due <= last)
      .map(taskShown);
    return [
      ...(shown.data?.events ?? []).filter((each) => !hidden.has(each.calendar)),
      ...held,
      ...due,
    ].sort((a, b) => a.start.localeCompare(b.start) || a.end.localeCompare(b.end));
  }, [shown.data, hidden, resources.data, tasks.data, first, last, box]);
  const window = shownOf(
    shown.data ?? { events: [], bookings: [], holidays: [], days_off: [], birthdays: [] },
    hidden,
  );
  const writable = (calendars.data?.calendars ?? []).filter((each) => !each.read_only);
  const reader = calendars.data?.role === 'read';
  const go = (next: View, at: string) => navigate(inBox(`/calendar/${next}/${at}`, box));
  const step = (direction: 1 | -1) => {
    switch (view) {
      case 'month':
        return go(view, shiftedMonths(`${monthOf(day)}-01`, direction));
      case 'week':
        return go(view, shifted(day, 7 * direction));
      case 'day':
        return go(view, shifted(day, direction));
      case 'agenda':
        return go(view, shifted(day, AGENDA_DAYS * direction));
    }
  };
  const heading =
    view === 'month'
      ? formatMonth(monthOf(day))
      : view === 'day'
        ? formatDay(fromDay(day))
        : formatDays(first, last);
  const close = () => setDialog(null);
  const open = (occurrence: Occurrence) => {
    if (occurrence.task) {
      const task = tasks.data?.tasks.find((each) => each.id === occurrence.task);
      if (task) setDialog({ type: 'task', task });
    } else if (!occurrence.resource) {
      setDialog({ type: 'event', occurrence });
    }
  };
  const create = (at: string, time?: string, allDay?: boolean) => {
    if (reader) return;
    setDialog(writable.length > 0 ? { type: 'new', day: at, time, allDay } : { type: 'calendar' });
  };

  return (
    <Frame
      title={t('rail.calendar')}
      folders={false}
      side={
        <div className="flex flex-col gap-4">
          <CalendarPanel
            day={day}
            view={view}
            hidden={hidden}
            onToggle={toggleHidden}
            resources={{
              list: resources.data?.resources ?? [],
              shown: shownResources,
              onToggle: toggleResource,
            }}
          />
          <BoxLinks page="calendar" />
        </div>
      }
      primary={
        reader ? undefined : (
          <PrimaryAction
            icon={CalendarPlus}
            label={t('calendar.newEvent')}
            onClick={() => create(view === 'month' ? today : day)}
          />
        )
      }
    >
      <div className="flex h-full min-h-0 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => step(-1)}
            aria-label={t('calendar.previous')}
            className={iconButton}
          >
            <ChevronLeft size={18} aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => step(1)}
            aria-label={t('calendar.next')}
            className={iconButton}
          >
            <ChevronRight size={18} aria-hidden />
          </button>
          <button type="button" onClick={() => go(view, today)} className={button}>
            {t('calendar.today')}
          </button>
          <h2 className="min-w-0 flex-1 truncate text-lg font-semibold first-letter:uppercase">
            {heading}
          </h2>
          <div
            role="group"
            aria-label={t('calendar.view')}
            className="flex rounded-lg bg-raised p-0.5"
          >
            {VIEWS.map((each) => (
              <button
                key={each}
                type="button"
                aria-pressed={each === view}
                onClick={() => go(each, day)}
                className="rounded-md px-3 py-1 text-sm text-muted hover:text-ink aria-pressed:bg-surface aria-pressed:font-semibold aria-pressed:text-ink aria-pressed:shadow-sm"
              >
                {t(`calendar.view.${each}`)}
              </button>
            ))}
          </div>
        </div>
        {shown.isError && <p className="text-sm text-danger">{errorMessage(shown.error, t)}</p>}
        {shown.isPending || calendars.isPending ? (
          <Loading />
        ) : view === 'month' ? (
          <Month
            day={day}
            today={today}
            events={visible}
            window={window}
            byId={byId}
            onOpen={open}
            onDay={(at) => go('day', at)}
            onCreate={(at) => create(at)}
          />
        ) : view === 'agenda' ? (
          <Agenda
            first={first}
            last={last}
            today={today}
            events={visible}
            window={window}
            byId={byId}
            onOpen={open}
          />
        ) : (
          <Week
            days={view === 'week' ? Array.from({ length: 7 }, (_, i) => shifted(first, i)) : [day]}
            today={today}
            events={visible}
            window={window}
            byId={byId}
            onOpen={open}
            onDay={(at) => go('day', at)}
            onCreate={create}
          />
        )}
      </div>
      {dialog?.type === 'new' && (
        <EventDialog calendars={writable} start={dialog} onClose={close} />
      )}
      {dialog?.type === 'event' && (
        <EventDialog calendars={writable} occurrence={dialog.occurrence} onClose={close} />
      )}
      {dialog?.type === 'calendar' && <CalendarDialog calendar={dialog.calendar} onClose={close} />}
      {dialog?.type === 'task' && <TaskDialog task={dialog.task} onClose={close} />}
    </Frame>
  );
}

/** The month and the calendars, beside Today and the calendar alike. */
interface ShownResources {
  list: Resource[];
  shown: Set<number>;
  onToggle: (id: number) => void;
}

export function CalendarPanel({
  day,
  view,
  hidden,
  onToggle,
  resources,
}: {
  day: string;
  view: View;
  hidden: Set<number>;
  onToggle: (id: number) => void;
  resources?: ShownResources;
}) {
  const calendars = useCalendars();
  const [editing, setEditing] = useState<{ calendar?: Calendar } | null>(null);
  return (
    <>
      <Side
        day={day}
        view={view}
        calendars={calendars.data?.calendars ?? []}
        unfollowed={calendars.data?.unfollowed ?? []}
        failed={calendars.data?.failed ?? []}
        hidden={hidden}
        onToggle={onToggle}
        resources={resources}
        onEdit={(calendar) => setEditing({ calendar })}
        onNew={calendars.data?.role === 'read' ? undefined : () => setEditing({})}
      />
      {editing && <CalendarDialog calendar={editing.calendar} onClose={() => setEditing(null)} />}
    </>
  );
}

function Side({
  day,
  view,
  calendars,
  unfollowed,
  failed,
  hidden,
  onToggle,
  onEdit,
  onNew,
  resources,
}: {
  day: string;
  view: View;
  calendars: Calendar[];
  unfollowed: Calendars['unfollowed'];
  failed: { account: string; error: string }[];
  hidden: Set<number>;
  onToggle: (id: number) => void;
  onEdit: (calendar: Calendar) => void;
  /** None where the calendars are only read. */
  onNew?: () => void;
  resources?: ShownResources;
}) {
  const changed = useChanged();
  const follow = useMutation({
    mutationFn: (id: number) => postJson(`/api/calendar/feeds/${id}`, {}),
    onSuccess: changed,
  });
  const { t } = useI18n();
  const dark = useDark();
  const heading = useId();
  const resourcesHeading = useId();
  const list = useId();
  const press = useMenuPress();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex flex-col gap-4">
      <MiniMonth day={day} view={view} />
      <section aria-labelledby={heading} className="flex flex-col gap-1">
        <div className="flex items-center gap-2 px-2">
          <h2
            id={heading}
            className="flex-1 text-xs font-semibold tracking-wide text-muted uppercase"
          >
            {t('calendar.calendars')}
          </h2>
          <button
            type="button"
            onClick={() => setOpen((now) => !now)}
            aria-expanded={open}
            aria-controls={list}
            aria-label={t('calendar.settings')}
            title={t('calendar.settings')}
            className={`${iconButton} aria-expanded:bg-selected aria-expanded:text-ink`}
          >
            <Settings size={16} aria-hidden />
          </button>
        </div>
        {open && (
          <div id={list} className="flex flex-col gap-1">
            <ul className="flex flex-col">
              {calendars.map((each) => (
                <ContextMenuArea
                  key={each.id}
                  items={
                    <MenuItem
                      icon={Pencil}
                      label={t('calendar.editCalendar')}
                      onSelect={() => onEdit(each)}
                    />
                  }
                >
                  <li
                    {...press}
                    className="flex items-center gap-2 rounded px-2 py-1 select-none hover:bg-hover [-webkit-touch-callout:none]"
                  >
                    <input
                      type="checkbox"
                      checked={!hidden.has(each.id)}
                      onChange={() => onToggle(each.id)}
                      aria-label={each.name}
                      className="size-4 shrink-0"
                      style={{ accentColor: colorOf(each, dark) }}
                    />
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-sm">{each.name}</span>
                      {each.account && each.account !== each.name && (
                        <span className="truncate text-xs text-muted">{each.account}</span>
                      )}
                    </span>
                    {each.read_only && (
                      <span title={t('calendar.readOnly')} className="text-muted">
                        <Lock size={12} aria-hidden />
                        <span className="sr-only">{t('calendar.readOnly')}</span>
                      </span>
                    )}
                  </li>
                </ContextMenuArea>
              ))}
              {(
                [
                  [HOLIDAYS, t('calendar.holidays')],
                  [BIRTHDAYS, t('calendar.birthdays')],
                ] as const
              ).map(([id, label]) => (
                <li key={id} className="flex items-center gap-2 rounded px-2 py-1 hover:bg-hover">
                  <input
                    type="checkbox"
                    checked={!hidden.has(id)}
                    onChange={() => onToggle(id)}
                    aria-label={label}
                    className="size-4 shrink-0"
                  />
                  <span className="truncate text-sm">{label}</span>
                </li>
              ))}
            </ul>
            {unfollowed.length > 0 && (
              <ul
                aria-label={t('calendar.unfollowed')}
                className="flex flex-col border-t border-line pt-1"
              >
                {unfollowed.map((each) => (
                  <li
                    key={each.id}
                    className="flex items-center gap-2 rounded px-2 py-1 hover:bg-hover"
                  >
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-sm text-muted">{each.name}</span>
                      {each.account !== each.name && (
                        <span className="truncate text-xs text-muted">{each.account}</span>
                      )}
                    </span>
                    <button
                      type="button"
                      onClick={() => follow.mutate(each.id)}
                      disabled={follow.isPending}
                      aria-label={`${t('calendar.follow')}: ${each.name}`}
                      className={`${button} py-0.5 text-xs`}
                    >
                      {t('calendar.follow')}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {failed.map((each) => (
              <p key={each.account} className="px-2 text-xs text-danger">
                {each.account}: {codeText(each.error, t)}
              </p>
            ))}
            {onNew && (
              <button
                type="button"
                onClick={onNew}
                className="flex items-center gap-2 rounded px-2 py-1 text-sm text-muted hover:bg-hover hover:text-ink"
              >
                <Plus size={14} aria-hidden />
                {t('calendar.newCalendar')}
              </button>
            )}
          </div>
        )}
      </section>
      {resources && resources.list.length > 0 && (
        <section aria-labelledby={resourcesHeading} className="flex flex-col gap-1">
          <h2
            id={resourcesHeading}
            className="px-2 text-xs font-semibold tracking-wide text-muted uppercase"
          >
            {t('calendar.resources')}
          </h2>
          <ul className="flex flex-col">
            {resources.list.map((each) => (
              <li
                key={each.id}
                className="flex items-center gap-2 rounded px-2 py-1 hover:bg-hover"
              >
                <input
                  type="checkbox"
                  checked={resources.shown.has(each.id)}
                  onChange={() => resources.onToggle(each.id)}
                  aria-label={each.name}
                  className="size-4 shrink-0"
                />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm">{each.name}</span>
                  {(each.place || each.capacity) && (
                    <span className="truncate text-xs text-muted">
                      {[each.place, each.capacity && `${each.capacity} ${t('calendar.seats')}`]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** The month at hand, the side of Today and Tasks as well as the calendar's own. */
export function MiniMonth({ day, view }: { day: string; view: View }) {
  const { t, formatMonth, language } = useI18n();
  const box = useBox();
  const [month, setMonth] = useState(monthOf(day));
  useEffect(() => setMonth(monthOf(day)), [day]);
  const grid = monthGrid(`${month}-01`);
  const off = useDaysOff(grid[0], grid[grid.length - 1]);
  const today = dayOf(new Date());
  const weekdays = useMemo(() => {
    const format = new Intl.DateTimeFormat(language, { weekday: 'narrow' });
    return grid.slice(0, 7).map((each) => format.format(fromDay(each)));
  }, [language, grid]);
  return (
    <div className="flex flex-col gap-1 px-1">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => setMonth(monthOf(shiftedMonths(`${month}-01`, -1)))}
          aria-label={t('calendar.previousMonth')}
          className={iconButton}
        >
          <ChevronLeft size={14} aria-hidden />
        </button>
        <span className="flex-1 text-center text-sm font-semibold first-letter:uppercase">
          {formatMonth(month)}
        </span>
        <button
          type="button"
          onClick={() => setMonth(monthOf(shiftedMonths(`${month}-01`, 1)))}
          aria-label={t('calendar.nextMonth')}
          className={iconButton}
        >
          <ChevronRight size={14} aria-hidden />
        </button>
      </div>
      <div className="grid grid-cols-7 text-center text-[0.65rem] text-muted">
        {weekdays.map((each, index) => (
          <span key={index}>{each}</span>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {grid.map((each) => (
          <Link
            key={each}
            to={inBox(`/calendar/${view}/${each}`, box)}
            aria-current={each === day ? 'date' : undefined}
            className={`flex h-6 items-center justify-center rounded-full text-xs hover:bg-hover aria-[current=date]:bg-accent aria-[current=date]:text-on-accent ${
              each === today && each !== day
                ? 'font-bold text-link'
                : monthOf(each) !== month
                  ? 'text-muted'
                  : off.has(each)
                    ? 'text-day-off-ink'
                    : ''
            }`}
          >
            {Number(each.slice(8))}
          </Link>
        ))}
      </div>
    </div>
  );
}

function Chip({
  occurrence,
  calendar,
  compact,
  onOpen,
}: {
  occurrence: Occurrence;
  calendar: Calendar | undefined;
  compact?: boolean;
  onOpen: (occurrence: Occurrence) => void;
}) {
  const { formatTime } = useI18n();
  const dark = useDark();
  const color = colorOf(calendar, dark);
  const time = occurrence.all_day ? '' : formatTime(new Date(occurrence.start));
  const cancelled = occurrence.status === 'cancelled';
  return (
    <button
      type="button"
      onClick={() => onOpen(occurrence)}
      title={occurrence.summary}
      className={`flex w-full min-w-0 items-center gap-1 rounded px-1 text-left text-xs hover:bg-hover ${
        cancelled ? 'line-through opacity-60' : ''
      }`}
    >
      <span
        aria-hidden
        className="size-2 shrink-0 rounded-full"
        style={{ backgroundColor: color, opacity: occurrence.status === 'tentative' ? 0.5 : 1 }}
      />
      {time && !compact && <span className="shrink-0 text-muted">{time}</span>}
      <span className="truncate">{occurrence.summary || '—'}</span>
      {occurrence.recurring && <RepeatIcon size={10} aria-hidden className="shrink-0 text-muted" />}
    </button>
  );
}

function Extras({
  day,
  window,
  t,
  language,
}: {
  day: string;
  window: Window;
  t: (key: MessageKey) => string;
  language: 'hr' | 'en';
}) {
  const holidays = window.holidays.filter((each) => each.date === day);
  const birthdays = window.birthdays.filter((each) => each.date === day);
  return (
    <>
      {holidays.map((each) => (
        <p
          key={each.date + each.hr}
          className="truncate px-1 text-xs text-link"
          title={each[language]}
        >
          {each[language]}
        </p>
      ))}
      {birthdays.map((each) => (
        <Link
          key={each.contact}
          to={`/contacts/${each.contact}`}
          className="flex min-w-0 items-center gap-1 rounded px-1 text-xs hover:bg-hover"
          title={`${t('calendar.birthday')}: ${each.name}`}
        >
          <Cake size={10} aria-hidden className="shrink-0 text-muted" />
          <span className="truncate">
            {each.name}
            {each.age !== null && ` (${each.age})`}
          </span>
        </Link>
      ))}
    </>
  );
}

function Month({
  day,
  today,
  events,
  window,
  byId,
  onOpen,
  onDay,
  onCreate,
}: {
  day: string;
  today: string;
  events: Occurrence[];
  window: Window;
  byId: Map<number, Calendar>;
  onOpen: (occurrence: Occurrence) => void;
  onDay: (day: string) => void;
  onCreate: (day: string) => void;
}) {
  const { t, language, formatDay } = useI18n();
  const grid = monthGrid(day);
  const month = monthOf(day);
  const byDay = useMemo(() => {
    const found = new Map<string, Occurrence[]>();
    for (const each of events) {
      for (const at of daysOf(each, grid[0], grid[grid.length - 1])) {
        found.set(at, [...(found.get(at) ?? []), each]);
      }
    }
    return found;
  }, [events, grid]);
  const weekdays = useMemo(() => {
    const format = new Intl.DateTimeFormat(language, { weekday: 'short' });
    return grid.slice(0, 7).map((each) => format.format(fromDay(each)));
  }, [language, grid]);
  const off = new Set(window.days_off);
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-line">
      <div className="grid grid-cols-7 border-b border-line bg-raised text-center text-xs text-muted">
        {weekdays.map((each) => (
          <span key={each} className="py-1">
            {each}
          </span>
        ))}
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-7 grid-rows-6 overflow-y-auto">
        {grid.map((each) => {
          const listed = byDay.get(each) ?? [];
          const more = listed.length - SHOWN_IN_CELL;
          return (
            <div
              key={each}
              onDoubleClick={() => onCreate(each)}
              className={`flex min-h-24 min-w-0 flex-col gap-0.5 border-r border-b border-line p-1 last:border-r-0 ${
                off.has(each) ? 'bg-day-off' : monthOf(each) !== month ? 'bg-raised/60' : ''
              } ${monthOf(each) !== month ? 'text-muted' : ''}`}
            >
              <button
                type="button"
                onClick={() => onDay(each)}
                aria-label={formatDay(fromDay(each))}
                className={`self-start rounded-full px-1.5 text-xs leading-5 hover:bg-hover ${
                  each === today
                    ? 'bg-accent font-semibold text-on-accent'
                    : off.has(each)
                      ? 'text-day-off-ink'
                      : ''
                }`}
              >
                {Number(each.slice(8))}
              </button>
              <Extras day={each} window={window} t={t} language={language} />
              {listed.slice(0, SHOWN_IN_CELL).map((occurrence) => (
                <Chip
                  key={`${occurrence.event}:${occurrence.recurrence_id ?? ''}`}
                  occurrence={occurrence}
                  calendar={byId.get(occurrence.calendar)}
                  onOpen={onOpen}
                />
              ))}
              {more > 0 && (
                <button
                  type="button"
                  onClick={() => onDay(each)}
                  className="self-start px-1 text-xs text-link hover:underline"
                >
                  +{more}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface Placed {
  occurrence: Occurrence;
  top: number;
  height: number;
  lane: number;
  lanes: number;
}

/** Timed occurrences of one day laid side by side where they overlap. */
function placed(day: string, events: Occurrence[]): Placed[] {
  const start = fromDay(day).getTime();
  const end = fromDay(shifted(day, 1)).getTime();
  const timed = events
    .filter(
      (each) =>
        !each.all_day &&
        new Date(each.start).getTime() < end &&
        new Date(each.end).getTime() > start,
    )
    .map((each) => {
      const from = Math.max(new Date(each.start).getTime(), start);
      const to = Math.min(new Date(each.end).getTime(), end);
      return { each, from, to: Math.max(to, from + 20 * 60 * 1000) };
    })
    .sort((a, b) => a.from - b.from || b.to - a.to);
  const found: Placed[] = [];
  let cluster: { from: number; to: number; items: Placed[]; ends: number[] } | null = null;
  for (const { each, from, to } of timed) {
    if (!cluster || from >= cluster.to) {
      cluster = { from, to, items: [], ends: [] };
    }
    let lane = cluster.ends.findIndex((at) => at <= from);
    if (lane === -1) {
      lane = cluster.ends.length;
      cluster.ends.push(to);
    } else {
      cluster.ends[lane] = to;
    }
    cluster.to = Math.max(cluster.to, to);
    const item = {
      occurrence: each,
      top: ((from - start) / 3_600_000) * HOUR,
      height: ((to - from) / 3_600_000) * HOUR,
      lane,
      lanes: 1,
    };
    cluster.items.push(item);
    for (const held of cluster.items) held.lanes = cluster.ends.length;
    found.push(item);
  }
  return found;
}

function Week({
  days,
  today,
  events,
  window,
  byId,
  onOpen,
  onDay,
  onCreate,
}: {
  days: string[];
  today: string;
  events: Occurrence[];
  window: Window;
  byId: Map<number, Calendar>;
  onOpen: (occurrence: Occurrence) => void;
  onDay: (day: string) => void;
  onCreate: (day: string, time?: string, allDay?: boolean) => void;
}) {
  const { t, language, formatTime } = useI18n();
  const dark = useDark();
  const now = useNow();
  const weekday = useMemo(
    () => new Intl.DateTimeFormat(language, { weekday: 'short' }),
    [language],
  );
  const allDay = (day: string) =>
    events.filter(
      (each) =>
        (each.all_day || dayOf(new Date(each.start)) !== dayOf(new Date(each.end))) &&
        daysOf(each, day, day).includes(day),
    );
  const columns = `repeat(${days.length}, minmax(0, 1fr))`;
  const off = new Set(window.days_off);
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-line">
      <div
        className="grid border-b border-line bg-raised"
        style={{ gridTemplateColumns: `3.5rem ${columns}` }}
      >
        <span />
        {days.map((each) => (
          <div
            key={each}
            className={`flex min-w-0 flex-col gap-0.5 border-l border-line p-1 ${
              off.has(each) ? 'bg-day-off' : ''
            }`}
          >
            <button
              type="button"
              onClick={() => onDay(each)}
              className="flex items-center gap-1 self-start rounded px-1 text-sm hover:bg-hover"
            >
              <span className={off.has(each) ? 'text-day-off-ink' : 'text-muted'}>
                {weekday.format(fromDay(each))}
              </span>
              <span
                className={`rounded-full px-1.5 leading-6 ${
                  each === today
                    ? 'bg-accent font-semibold text-on-accent'
                    : off.has(each)
                      ? 'font-semibold text-day-off-ink'
                      : 'font-semibold'
                }`}
              >
                {Number(each.slice(8))}
              </span>
            </button>
            <Extras day={each} window={window} t={t} language={language} />
            {allDay(each).map((occurrence) => (
              <Chip
                key={`${occurrence.event}:${occurrence.recurrence_id ?? ''}`}
                occurrence={occurrence}
                calendar={byId.get(occurrence.calendar)}
                compact
                onOpen={onOpen}
              />
            ))}
            <button
              type="button"
              onClick={() => onCreate(each, undefined, true)}
              className="self-start px-1 text-xs text-muted hover:text-link"
            >
              {t('calendar.addAllDay')}
            </button>
          </div>
        ))}
      </div>
      <div
        ref={(grid) => {
          if (grid && grid.scrollTop === 0) grid.scrollTop = FIRST_SHOWN * HOUR;
        }}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        <div
          className="relative grid"
          style={{ gridTemplateColumns: `3.5rem ${columns}`, height: HOUR * 24 }}
        >
          <div className="relative">
            {HOURS.map((hour) => (
              <span
                key={hour}
                className="absolute right-1 -translate-y-1/2 text-[0.65rem] text-muted"
                style={{ top: hour * HOUR }}
              >
                {hour === 0 ? '' : formatTime(new Date(2000, 0, 1, hour))}
              </span>
            ))}
          </div>
          {days.map((each) => {
            const items = placed(each, events);
            return (
              <div
                key={each}
                className={`relative border-l border-line ${off.has(each) ? 'bg-day-off' : ''}`}
              >
                {HOURS.map((hour) => (
                  <button
                    key={hour}
                    type="button"
                    aria-label={`${each} ${String(hour).padStart(2, '0')}:00`}
                    onClick={() => onCreate(each, `${String(hour).padStart(2, '0')}:00`)}
                    className="absolute inset-x-0 border-t border-line hover:bg-hover/60"
                    style={{ top: hour * HOUR, height: HOUR }}
                  />
                ))}
                {each === today && (
                  <div
                    aria-hidden
                    className="pointer-events-none absolute inset-x-0 z-10 border-t-2 border-danger"
                    style={{ top: (minutesOf(now) / 60) * HOUR }}
                  />
                )}
                {items.map(({ occurrence, top, height, lane, lanes }) => {
                  const calendar = byId.get(occurrence.calendar);
                  const color = colorOf(calendar, dark);
                  const style: CSSProperties = {
                    top,
                    height,
                    left: `calc(${(lane / lanes) * 100}% + 2px)`,
                    width: `calc(${100 / lanes}% - 4px)`,
                    borderLeftColor: color,
                  };
                  return (
                    <button
                      key={`${occurrence.event}:${occurrence.recurrence_id ?? ''}`}
                      type="button"
                      onClick={() => onOpen(occurrence)}
                      title={occurrence.summary}
                      style={style}
                      className={`absolute flex flex-col overflow-hidden rounded border-l-4 bg-raised px-1 text-left text-xs shadow-sm hover:bg-hover ${
                        occurrence.status === 'cancelled' ? 'line-through opacity-60' : ''
                      } ${occurrence.status === 'tentative' ? 'opacity-70' : ''}`}
                    >
                      <span className="truncate font-medium">{occurrence.summary || '—'}</span>
                      <span className="truncate text-muted">
                        {formatTime(new Date(occurrence.start))}–
                        {formatTime(new Date(occurrence.end))}
                        {occurrence.location && ` · ${occurrence.location}`}
                      </span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Agenda({
  first,
  last,
  today,
  events,
  window,
  byId,
  onOpen,
}: {
  first: string;
  last: string;
  today: string;
  events: Occurrence[];
  window: Window;
  byId: Map<number, Calendar>;
  onOpen: (occurrence: Occurrence) => void;
}) {
  const { t, language, formatDay, formatTime } = useI18n();
  const dark = useDark();
  const days: string[] = [];
  for (let day = first; day <= last; day = shifted(day, 1)) days.push(day);
  const shown = days
    .map((day) => ({
      day,
      events: events.filter((each) => daysOf(each, day, day).includes(day)),
      holidays: window.holidays.filter((each) => each.date === day),
      birthdays: window.birthdays.filter((each) => each.date === day),
    }))
    .filter((each) => each.events.length || each.holidays.length || each.birthdays.length);
  if (shown.length === 0) {
    return <p className="text-sm text-muted">{t('calendar.nothingAhead')}</p>;
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
      {shown.map(({ day, events: listed, holidays, birthdays }) => (
        <section key={day} className="flex flex-col gap-1">
          <h3
            className={`text-sm font-semibold first-letter:uppercase ${
              day === today ? 'text-link' : ''
            }`}
          >
            {formatDay(fromDay(day))}
          </h3>
          {holidays.map((each) => (
            <p key={each.hr} className="px-2 text-sm text-link">
              {each[language]}
            </p>
          ))}
          {birthdays.map((each) => (
            <Link
              key={each.contact}
              to={`/contacts/${each.contact}`}
              className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-hover"
            >
              <Cake size={14} aria-hidden className="text-muted" />
              {t('calendar.birthday')}: {each.name}
              {each.age !== null && ` (${each.age})`}
            </Link>
          ))}
          {listed.map((occurrence) => (
            <button
              key={`${occurrence.event}:${occurrence.recurrence_id ?? ''}`}
              type="button"
              onClick={() => onOpen(occurrence)}
              className="flex min-w-0 items-center gap-3 rounded px-2 py-1.5 text-left hover:bg-hover"
            >
              <span
                aria-hidden
                className="size-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: colorOf(byId.get(occurrence.calendar), dark) }}
              />
              <span className="w-28 shrink-0 text-sm text-muted">
                {occurrence.all_day
                  ? t('calendar.allDay')
                  : `${formatTime(new Date(occurrence.start))}–${formatTime(new Date(occurrence.end))}`}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span
                  className={`truncate text-sm ${occurrence.status === 'cancelled' ? 'line-through' : ''}`}
                >
                  {occurrence.summary || '—'}
                </span>
                {occurrence.location && (
                  <span className="flex items-center gap-1 truncate text-xs text-muted">
                    <MapPin size={10} aria-hidden />
                    {occurrence.location}
                  </span>
                )}
              </span>
              {occurrence.recurring && <RepeatIcon size={12} aria-hidden className="text-muted" />}
            </button>
          ))}
        </section>
      ))}
    </div>
  );
}

export function EventDialog({
  calendars,
  start,
  occurrence,
  onClose,
}: {
  calendars: Calendar[];
  start?: Start;
  occurrence?: Occurrence;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const changed = useChanged();
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ['calendar-event', occurrence?.event],
    queryFn: () => getJson<Detail>(`/api/calendar/events/${occurrence!.event}?zone=${ZONE}`),
    enabled: occurrence !== undefined,
  });
  if (occurrence && detail.isPending) {
    return (
      <Modal heading={t('calendar.event')} onClose={onClose}>
        <Loading />
      </Modal>
    );
  }
  if (occurrence && detail.isError) {
    return (
      <Modal heading={t('calendar.event')} onClose={onClose}>
        <p className="text-sm text-danger">{errorMessage(detail.error, t)}</p>
      </Modal>
    );
  }
  return (
    <EventForm
      calendars={calendars}
      start={start}
      occurrence={occurrence}
      detail={detail.data}
      onSaved={() => {
        queryClient.removeQueries({ queryKey: ['calendar-event', occurrence?.event] });
        changed();
        onClose();
      }}
      onClose={onClose}
    />
  );
}

/** Where a new event starts, and what else it is given before the user changes it. */
export interface Start {
  day: string;
  time?: string;
  allDay?: boolean;
  endDay?: string;
  endTime?: string;
  summary?: string;
  location?: string;
  description?: string;
}

interface Form {
  summary: string;
  calendar: number;
  allDay: boolean;
  startDay: string;
  startTime: string;
  endDay: string;
  endTime: string;
  location: string;
  conference: string;
  description: string;
  repeat: Repeat;
  until: string;
  dayOff: DayOff;
  reminder: string;
  busy: boolean;
  private: boolean;
  attendees: Person[];
  resources: number[];
}

/** Whether the meeting is the user's to call: theirs, or not a meeting yet. */
function callable(detail: Detail | undefined): boolean {
  return !detail || detail.response === 'organizer' || detail.attendees.length === 0;
}

/** The day the series' rule gives the occurrence, which days off or a change of its own may have
 * moved it from. */
function ruleDayOf(occurrence: Occurrence | undefined): string | null {
  if (!occurrence?.recurrence_id) return null;
  return occurrence.all_day ? occurrence.recurrence_id : dayOf(new Date(occurrence.recurrence_id));
}

function initialForm(
  calendars: Calendar[],
  start: Start | undefined,
  occurrence: Occurrence | undefined,
  detail: Detail | undefined,
): Form {
  if (occurrence && detail) {
    const from = occurrence.all_day ? null : new Date(occurrence.start);
    const to = occurrence.all_day ? null : new Date(occurrence.end);
    const startDay = from ? dayOf(from) : occurrence.start;
    return {
      summary: detail.summary,
      calendar: detail.calendar,
      allDay: occurrence.all_day,
      startDay,
      startTime: from ? timeOf(from) : '09:00',
      endDay: to ? dayOf(to) : occurrence.end,
      endTime: to ? timeOf(to) : '10:00',
      location: detail.location,
      conference: detail.conference,
      description: detail.description,
      repeat: repeatOf(detail.rrule, ruleDayOf(occurrence) ?? startDay),
      until: untilOf(detail.rrule),
      dayOff: detail.day_off,
      reminder: detail.reminders.length ? String(detail.reminders[0]) : '',
      busy: detail.busy,
      private: detail.private,
      attendees: callable(detail)
        ? detail.attendees.map((each) => ({ name: each.name, address: each.email }))
        : [],
      resources: detail.resources,
    };
  }
  const day = start?.day ?? dayOf(new Date());
  const [hour, minute = 0] = (start?.time ?? '09:00').split(':').map(Number);
  const pad = (value: number) => String(value).padStart(2, '0');
  return {
    summary: start?.summary ?? '',
    calendar: calendars[0]?.id ?? 0,
    allDay: start?.allDay ?? false,
    startDay: day,
    startTime: `${pad(hour)}:${pad(minute)}`,
    endDay: start?.endDay ?? (hour >= 23 ? shifted(day, 1) : day),
    endTime: start?.endTime ?? `${pad((hour + 1) % 24)}:${pad(minute)}`,
    location: start?.location ?? '',
    conference: '',
    description: start?.description ?? '',
    repeat: 'none',
    until: '',
    dayOff: '',
    reminder: '',
    busy: true,
    private: false,
    attendees: [],
    resources: [],
  };
}

function EventForm({
  calendars,
  start,
  occurrence,
  detail,
  onSaved,
  onClose,
}: {
  calendars: Calendar[];
  start?: Start;
  occurrence?: Occurrence;
  detail?: Detail;
  onSaved: () => void;
  onClose: () => void;
}) {
  const { t, language, formatDay, formatTime } = useI18n();
  const [initial] = useState(() => initialForm(calendars, start, occurrence, detail));
  const [form, setForm] = useState(initial);
  const [asking, setAsking] = useState<'save' | 'delete' | null>(null);
  const [tasking, setTasking] = useState(false);
  const readOnly = detail?.read_only ?? false;
  const recurring = occurrence?.recurring ?? false;
  const ours = callable(detail);
  const worded =
    form.conference !== '' && `${form.location}\n${form.description}`.includes(form.conference);
  const set = <K extends keyof Form>(name: K, value: Form[K]) =>
    setForm((now) => ({ ...now, [name]: value }));
  const resources = useResources();
  const offered = resources.data?.resources ?? [];
  const chosen = form.resources.filter((id) => offered.some((each) => each.id === id));
  const toggleResource = (id: number) =>
    set('resources', chosen.includes(id) ? chosen.filter((each) => each !== id) : [...chosen, id]);
  const span = {
    start: form.allDay ? form.startDay : `${form.startDay}T${form.startTime}`,
    end: form.allDay ? shifted(form.endDay, 1) : `${form.endDay}T${form.endTime}`,
  };
  const dayShape = /^\d{4}-\d{2}-\d{2}$/;
  const timeShape = /^\d{2}:\d{2}$/;
  const spanValid =
    dayShape.test(form.startDay) &&
    dayShape.test(form.endDay) &&
    (form.allDay || (timeShape.test(form.startTime) && timeShape.test(form.endTime))) &&
    span.start < span.end;
  const day =
    form.startDay !== initial.startDay && dayShape.test(form.startDay)
      ? form.startDay
      : (ruleDayOf(occurrence) ?? initial.startDay);
  const asked = ours ? form.attendees.map((each) => each.address) : [];
  const free = useFree(
    {
      ...span,
      people: asked,
      resources: offered.map((each) => each.id),
      except: detail?.master ?? detail?.id,
    },
    !readOnly && spanValid && asked.length + offered.length > 0,
  );
  const busy = form.attendees.filter(
    (each) => free.data?.people[each.address.toLowerCase()] === 'busy',
  );
  const awayThen = form.attendees.flatMap((each) => {
    const until = free.data?.away[each.address.toLowerCase()];
    return until ? [{ who: each.name || each.address, until }] : [];
  });
  const unknown = form.attendees.filter(
    (each) => free.data?.people[each.address.toLowerCase()] === 'unknown',
  );
  const clash =
    busy.length > 0 ||
    awayThen.length > 0 ||
    chosen.some((id) => free.data?.resources[String(id)] === 'busy');
  const offers = useOffers(
    { ...span, people: asked, resources: chosen, except: detail?.master ?? detail?.id },
    !readOnly && !form.allDay && spanValid && clash,
  );
  const take = (offer: { start: string; end: string }) =>
    setForm((now) => ({
      ...now,
      startDay: offer.start.slice(0, 10),
      startTime: offer.start.slice(11, 16),
      endDay: offer.end.slice(0, 10),
      endTime: offer.end.slice(11, 16),
    }));
  const body = () => ({
    calendar: form.calendar,
    summary: form.summary.trim(),
    location: form.location.trim(),
    conference: form.conference,
    description: form.description.trim(),
    all_day: form.allDay,
    start: form.allDay ? form.startDay : `${form.startDay}T${form.startTime}`,
    end: form.allDay ? form.endDay : `${form.endDay}T${form.endTime}`,
    zone: ZONE,
    rrule:
      form.repeat === initial.repeat &&
      form.until === initial.until &&
      form.startDay === initial.startDay
        ? (detail?.rrule ?? '')
        : ruleOf(
            form.repeat,
            day,
            detail?.rrule ?? '',
            form.until === initial.until ? null : form.until,
          ),
    day_off: form.repeat === 'none' ? '' : form.dayOff,
    reminders: form.reminder === '' ? [] : [Number(form.reminder)],
    busy: form.busy,
    private: form.private,
    language,
    resources: chosen,
    ...(ours
      ? { attendees: form.attendees.map((each) => ({ email: each.address, name: each.name })) }
      : {}),
  });
  const where = (scope: Scope | null) => {
    const query = new URLSearchParams({ zone: ZONE, language });
    if (scope) {
      query.set('scope', scope);
      if (occurrence?.recurrence_id) query.set('recurrence_id', occurrence.recurrence_id);
    }
    return `/api/calendar/events/${occurrence!.recurring ? occurrence!.master : occurrence!.event}?${query}`;
  };
  const save = useMutation({
    mutationFn: (scope: Scope | null) => {
      if (!occurrence) return postJson<Detail>('/api/calendar/events', body());
      const sent: Record<string, unknown> = body();
      const timing = ['allDay', 'startDay', 'startTime', 'endDay', 'endTime'] as const;
      const retimed = timing.some((each) => form[each] !== initial[each]);
      if (scope && scope !== 'all') {
        delete sent.calendar;
        if (scope === 'this') {
          delete sent.rrule;
          delete sent.day_off;
        }
      } else if (scope === 'all' && retimed) {
        sent.recurrence_id = occurrence.recurrence_id;
      }
      if ((scope === 'all' || scope === 'following') && !retimed) {
        delete sent.all_day;
        delete sent.start;
        delete sent.end;
      }
      return patchJson<Detail>(where(scope), sent);
    },
    onSuccess: onSaved,
  });
  const remove = useMutation({
    mutationFn: (scope: Scope | null) => deleteJson(where(scope)),
    onSuccess: onSaved,
  });
  const answer = useMutation({
    mutationFn: (response: Response) => respond(detail!.id, response, language),
    onSuccess: onSaved,
  });
  const answerId = useId();
  const needsScope = recurring;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (readOnly) return onClose();
    if (!form.summary.trim()) return;
    if (needsScope) return setAsking('save');
    save.mutate(null);
  }

  const heading = occurrence
    ? readOnly
      ? t('calendar.event')
      : t('calendar.editEvent')
    : t('calendar.newEvent');
  const error = save.error ?? remove.error ?? answer.error;
  const options = calendars.map((each) => [String(each.id), each.name] as const);
  const place = placeOf(day);
  const repeatLabel = (each: Repeat) => {
    if (each === 'monthly')
      return t('calendar.repeat.monthly').replace('{date}', String(place.date));
    if (each === 'nth' && place.nth)
      return t(`calendar.repeat.nth.${place.weekday}`).replace(
        '{n}',
        t(`calendar.ordinal.${place.nth}`),
      );
    if (each === 'nth' || each === 'last') return t(`calendar.repeat.last.${place.weekday}`);
    return t(`calendar.repeat.${each}`);
  };
  const repeats = REPEATS.filter(
    (each) => fitted(each, day) === each && (each !== 'custom' || initial.repeat === 'custom'),
  ).map((each) => [each, repeatLabel(each)] as const);
  const daysOff = DAYS_OFF.map(
    (each) => [each, t(`calendar.dayOff.${each === '' ? 'held' : each}`)] as const,
  );
  const reminders = REMINDERS.map(
    (each) => [each, t(`calendar.reminder.${each === '' ? 'none' : each}`)] as const,
  );

  return (
    <Modal heading={heading} wide onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <fieldset disabled={readOnly} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            {t('calendar.field.summary')}
            <input
              value={form.summary}
              onChange={(event) => set('summary', event.target.value)}
              maxLength={200}
              required
              autoFocus={!occurrence}
              className={field}
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              {t('calendar.field.startDay')}
              <input
                type="date"
                value={form.startDay}
                onChange={(event) => {
                  const next = event.target.value;
                  set('startDay', next);
                  if (form.endDay < next) set('endDay', next);
                }}
                required
                className={field}
              />
            </label>
            {!form.allDay && (
              <label className="flex flex-col gap-1 text-sm">
                {t('calendar.field.startTime')}
                <input
                  type="time"
                  value={form.startTime}
                  onChange={(event) => set('startTime', event.target.value)}
                  required
                  className={field}
                />
              </label>
            )}
            <label className="flex flex-col gap-1 text-sm">
              {t('calendar.field.endDay')}
              <input
                type="date"
                value={form.endDay}
                min={form.startDay}
                onChange={(event) => set('endDay', event.target.value)}
                required
                className={field}
              />
            </label>
            {!form.allDay && (
              <label className="flex flex-col gap-1 text-sm">
                {t('calendar.field.endTime')}
                <input
                  type="time"
                  value={form.endTime}
                  onChange={(event) => set('endTime', event.target.value)}
                  required
                  className={field}
                />
              </label>
            )}
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.allDay}
                onChange={(event) => set('allDay', event.target.checked)}
                className="size-4"
              />
              {t('calendar.allDay')}
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.busy}
                onChange={(event) => set('busy', event.target.checked)}
                className="size-4"
              />
              {t('calendar.field.busy')}
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.private}
                onChange={(event) => set('private', event.target.checked)}
                className="size-4"
              />
              {t('calendar.field.private')}
            </label>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {!readOnly && (
              <Picker
                label={t('calendar.field.calendar')}
                value={String(form.calendar)}
                options={options}
                onChange={(value) => set('calendar', Number(value))}
              />
            )}
            <label className="flex flex-col gap-1 text-sm">
              {t('calendar.field.location')}
              <input
                value={form.location}
                onChange={(event) => set('location', event.target.value)}
                maxLength={2000}
                className={field}
              />
            </label>
            <Picker
              label={t('calendar.field.repeat')}
              value={fitted(form.repeat, day)}
              options={repeats}
              onChange={(value) => set('repeat', value)}
            />
            {form.repeat !== 'none' && (
              <Picker
                label={t('calendar.field.dayOff')}
                value={form.dayOff}
                options={daysOff}
                onChange={(value) => set('dayOff', value)}
              />
            )}
            {form.repeat !== 'none' && (
              <label className="flex flex-col gap-1 text-sm">
                {t('calendar.field.until')}
                <input
                  type="date"
                  value={form.until}
                  min={form.startDay}
                  onChange={(event) => set('until', event.target.value)}
                  className={field}
                />
              </label>
            )}
            <Picker
              label={t('calendar.field.reminder')}
              value={form.reminder}
              options={reminders}
              onChange={(value) => set('reminder', value)}
            />
          </div>
          {readOnly ? (
            form.description && (
              <Labelled label={t('calendar.field.description')}>
                {(id) => (
                  <div
                    id={id}
                    className="max-h-48 overflow-y-auto rounded border border-control px-3 py-2"
                  >
                    <PlainBody text={form.description} />
                  </div>
                )}
              </Labelled>
            )
          ) : (
            <label className="flex flex-col gap-1 text-sm">
              {t('calendar.field.description')}
              <textarea
                rows={3}
                value={form.description}
                onChange={(event) => set('description', event.target.value)}
                maxLength={20000}
                className={field}
              />
            </label>
          )}
        </fieldset>
        <ConferenceField
          link={form.conference}
          title={form.summary}
          editable={ours && !readOnly && !worded}
          onChange={(link) => set('conference', link)}
        />
        {ours && !readOnly && (
          <Labelled label={t('calendar.field.attendees')}>
            {(id) => (
              <div className="flex flex-col gap-1">
                <Recipients
                  id={id}
                  people={form.attendees}
                  onChange={(people) => set('attendees', people)}
                />
                {busy.length > 0 && (
                  <p className="text-xs text-danger">
                    {t('calendar.busyThen')}:{' '}
                    {busy.map((each) => each.name || each.address).join(', ')}
                  </p>
                )}
                {awayThen.length > 0 && (
                  <p className="text-xs text-danger">
                    {t('away.then')}:{' '}
                    {awayThen
                      .map(
                        ({ who, until }) =>
                          `${who} (${t('away.until').replace('{when}', formatDay(lastDay(until)))})`,
                      )
                      .join(', ')}
                  </p>
                )}
                {form.attendees.length > 0 && (
                  <p className="text-xs text-muted">{t('calendar.inviteNote')}</p>
                )}
              </div>
            )}
          </Labelled>
        )}
        {!readOnly && offered.length > 0 && (
          <fieldset className="flex flex-col gap-1 text-sm">
            <legend className="mb-1 text-muted">{t('calendar.resources')}</legend>
            {offered.map((each) => {
              const taken =
                !chosen.includes(each.id) && free.data?.resources[String(each.id)] === 'busy';
              return (
                <label
                  key={each.id}
                  className={`flex items-center gap-2 ${taken ? 'text-muted' : ''}`}
                >
                  <input
                    type="checkbox"
                    checked={chosen.includes(each.id)}
                    disabled={taken}
                    onChange={() => toggleResource(each.id)}
                  />
                  <span className="truncate">{each.name}</span>
                  {each.place && <span className="text-xs text-muted">{each.place}</span>}
                  {taken && <span className="text-xs">({t('calendar.taken')})</span>}
                </label>
              );
            })}
          </fieldset>
        )}
        {clash && !readOnly && !form.allDay && offers.data?.offers && (
          <section className="flex flex-col gap-1 text-sm" aria-labelledby="calendar-offers">
            <h3 id="calendar-offers" className="text-muted">
              {t('calendar.offers')}
            </h3>
            {offers.data.offers.length === 0 ? (
              <p className="text-xs text-muted">{t('calendar.noOffers')}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {offers.data.offers.map((each) => (
                  <button
                    key={each.start}
                    type="button"
                    onClick={() => take(each)}
                    className="rounded border border-control px-2 py-1 hover:bg-hover"
                  >
                    {formatDay(new Date(each.start))} {formatTime(new Date(each.start))}–
                    {formatTime(new Date(each.end))}
                  </button>
                ))}
              </div>
            )}
            {unknown.length > 0 && (
              <p className="text-xs text-muted">
                {t('calendar.unknownThen')}:{' '}
                {unknown.map((each) => each.name || each.address).join(', ')}
              </p>
            )}
          </section>
        )}
        {readOnly && detail && detail.resources.length > 0 && (
          <Labelled label={t('calendar.resources')}>
            {(id) => (
              <p id={id} className="text-sm">
                {detail.resources
                  .map((each) => offered.find((one) => one.id === each)?.name)
                  .filter(Boolean)
                  .join(', ')}
              </p>
            )}
          </Labelled>
        )}
        {detail && detail.attendees.length > 0 && (
          <Labelled label={t('calendar.attendees')}>
            {(id) => (
              <ul id={id} className="flex flex-col gap-0.5 text-sm">
                {'email' in detail.organizer && (
                  <li className="text-muted">
                    {t('calendar.organizer')}: {detail.organizer.name || detail.organizer.email}
                  </li>
                )}
                {detail.attendees.map((each) => (
                  <li key={each.email} className="flex gap-2">
                    <span className="truncate">{each.name || each.email}</span>
                    <span className="text-xs text-muted">
                      {t(`calendar.status.${statusKey(each.status)}`)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Labelled>
        )}
        {detail && detail.response && detail.response !== 'organizer' && (
          <div role="group" aria-labelledby={answerId} className="flex flex-col gap-1 text-sm">
            <span id={answerId} className="text-muted">
              {t('calendar.yourAnswer')}
            </span>
            <ResponseButtons
              current={detail.response}
              disabled={answer.isPending}
              onPick={(response) => answer.mutate(response)}
            />
          </div>
        )}
        {error && <p className="text-sm text-danger">{errorMessage(error, t)}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          {occurrence && !readOnly && (
            <button
              type="button"
              onClick={() => (needsScope ? setAsking('delete') : remove.mutate(null))}
              disabled={remove.isPending}
              className={`${dangerButton} mr-auto`}
            >
              <Trash2 size={16} aria-hidden />
              {t('calendar.delete')}
            </button>
          )}
          {occurrence && (
            <button
              type="button"
              onClick={() => setTasking(true)}
              className={`${button} ${readOnly ? 'mr-auto' : ''}`}
            >
              <ListTodo size={16} aria-hidden />
              {t('tasks.fromEvent')}
            </button>
          )}
          <Cancel />
          {!readOnly && (
            <button type="submit" disabled={save.isPending} className={primaryButton}>
              {t('tree.save')}
            </button>
          )}
        </div>
        {tasking && occurrence && (
          <TaskDialog
            draft={{
              text: form.summary.trim(),
              due: form.startDay,
              source: {
                kind: 'event',
                label: form.summary.trim(),
                link: `/calendar/day/${form.startDay}`,
              },
            }}
            onClose={() => setTasking(false)}
          />
        )}
      </form>
      {asking && (
        <ScopeDialog
          deleting={asking === 'delete'}
          onPick={(scope) => {
            setAsking(null);
            if (asking === 'delete') remove.mutate(scope);
            else save.mutate(scope);
          }}
          onClose={() => setAsking(null)}
        />
      )}
    </Modal>
  );
}

const RESPONSE_ICONS: Record<Response, LucideIcon> = {
  accepted: Check,
  tentative: CircleHelp,
  declined: X,
};

/** Accept, maybe or decline, the one given pressed. */
export function ResponseButtons({
  current,
  disabled,
  onPick,
}: {
  current: string;
  disabled: boolean;
  onPick: (response: Response) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap gap-2">
      {RESPONSES.map((response) => {
        const Icon = RESPONSE_ICONS[response];
        const pressed = current === response;
        return (
          <button
            key={response}
            type="button"
            aria-pressed={pressed}
            disabled={disabled}
            onClick={pressed ? undefined : () => onPick(response)}
            className={`${button} ${pressed ? 'bg-selected' : ''}`}
          >
            <Icon size={16} aria-hidden />
            {t(`calendar.respond.${response}`)}
          </button>
        );
      })}
    </div>
  );
}

function statusKey(status: string): 'accepted' | 'declined' | 'tentative' | 'needsAction' {
  if (status === 'accepted' || status === 'declined' || status === 'tentative') return status;
  return 'needsAction';
}

function ScopeDialog({
  deleting,
  onPick,
  onClose,
}: {
  deleting: boolean;
  onPick: (scope: Scope) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [scope, setScope] = useState<Scope>('this');
  const name = useId();
  return (
    <Modal
      heading={t(deleting ? 'calendar.deleteRecurring' : 'calendar.editRecurring')}
      onClose={onClose}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onPick(scope);
        }}
        className="flex flex-col gap-4"
      >
        <div role="radiogroup" aria-label={t('calendar.scope')} className="flex flex-col gap-2">
          {SCOPES.map((each) => (
            <label key={each} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name={name}
                checked={scope === each}
                onChange={() => setScope(each)}
                className="size-4"
              />
              {t(`calendar.scope.${each}`)}
            </label>
          ))}
        </div>
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={deleting ? dangerButton : primaryButton}>
            {t(deleting ? 'calendar.delete' : 'tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function CalendarDialog({ calendar, onClose }: { calendar?: Calendar; onClose: () => void }) {
  const { t } = useI18n();
  const box = useBox();
  const dark = useDark();
  const changed = useChanged();
  const [name, setName] = useState(calendar?.name ?? '');
  const calendars = useCalendars();
  const [color, setColor] = useState(calendar?.color ?? calendars.data?.next_color ?? 0);
  const [confirming, setConfirming] = useState(false);
  const save = useMutation({
    mutationFn: () =>
      calendar
        ? patchJson<Calendar>(`/api/calendar/${calendar.id}`, {
            ...(calendar.read_only ? {} : { name: name.trim() }),
            color,
          })
        : postJson<Calendar>(inBox('/api/calendar', box), { name: name.trim(), color }),
    // Closed once the list holds the change: a new event asked for before then would find no
    // calendar to go in and ask for one again.
    onSuccess: async () => {
      await changed();
      onClose();
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteJson(`/api/calendar/${calendar!.id}`),
    onSuccess: async () => {
      await changed();
      onClose();
    },
  });
  const followed = calendar?.kind === 'own' && calendar.account !== null;
  const error = save.error ?? remove.error;
  return (
    <Modal
      heading={t(calendar ? 'calendar.editCalendar' : 'calendar.newCalendar')}
      onClose={onClose}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim() || calendar?.read_only) save.mutate();
        }}
        className="flex flex-col gap-4"
      >
        <label className="flex flex-col gap-1 text-sm">
          {t('calendar.field.name')}
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            disabled={calendar?.read_only}
            maxLength={200}
            required={!calendar?.read_only}
            autoFocus
            className={field}
          />
          {calendar?.read_only && (
            <span className="text-xs text-muted">{t('calendar.organisationCalendar')}</span>
          )}
        </label>
        <div role="radiogroup" aria-label={t('calendar.field.color')} className="flex gap-2">
          {Array.from({ length: colorCount() }, (_, index) => (
            <button
              key={index}
              type="button"
              role="radio"
              aria-checked={index === color}
              aria-label={t(`calendar.color.${index}` as MessageKey)}
              onClick={() => setColor(index)}
              className="size-7 rounded-full border-2 border-transparent aria-checked:border-ink"
              style={{ backgroundColor: colorOf({ color: index }, dark) }}
            />
          ))}
        </div>
        {error && <p className="text-sm text-danger">{errorMessage(error, t)}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          {calendar && (followed || !calendar.read_only) && (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className={`${dangerButton} mr-auto`}
            >
              <Trash2 size={16} aria-hidden />
              {t(followed ? 'calendar.unfollow' : 'calendar.deleteCalendar')}
            </button>
          )}
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t('tree.save')}
          </button>
        </div>
      </form>
      {confirming && (
        <Modal
          heading={t(followed ? 'calendar.unfollow' : 'calendar.deleteCalendar')}
          onClose={() => setConfirming(false)}
        >
          <form
            onSubmit={(event) => {
              event.preventDefault();
              remove.mutate();
            }}
            className="flex flex-col gap-4"
          >
            <p className="text-sm">
              {followed
                ? t('calendar.unfollowNote').replace('{account}', calendar!.account!)
                : t('calendar.deleteCalendarNote')}
            </p>
            <div className="flex justify-end gap-2">
              <Cancel />
              <button type="submit" disabled={remove.isPending} className={dangerButton}>
                {t(followed ? 'calendar.unfollow' : 'calendar.delete')}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </Modal>
  );
}
