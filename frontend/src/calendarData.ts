import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import palette from '../../colors/colors.json';
import { getJson, postJson } from './api';
import { inBox, type Mailbox, useBox } from './mailData';
import type { DayOff } from './recurrence';

export const CALENDAR = ['calendar'] as const;
export const ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;
const COLORS = palette.calendar as { light: string; dark: string }[];
const HIDDEN_KEY = 'ponistra.calendar.hidden';
/** Holidays and birthdays stand among the calendars with ids no calendar has. */
export const HOLIDAYS = -1;
export const BIRTHDAYS = -2;
const SHOWN_RESOURCES_KEY = 'ponistra.calendar.resources';
const MINUTE = 60_000;

export interface Calendar {
  id: number;
  name: string;
  color: number;
  kind: 'own' | 'organisation';
  read_only: boolean;
  account: string | null;
}

export interface Calendars {
  calendars: Calendar[];
  /** The user's role in the shared mailbox whose calendars these are; none in their own. */
  role: Mailbox['role'] | null;
  next_color: number;
  /** The calendars of the user's accounts they stopped following, to follow again. */
  unfollowed: { id: number; name: string; account: string }[];
  failed: { account: string; error: string }[];
  zone: string;
}

export interface Resource {
  id: number;
  name: string;
  kind: 'room' | 'equipment' | 'vehicle' | 'other';
  capacity: number | null;
  place: string;
  active: boolean;
}

export const RESOURCE_KINDS: Resource['kind'][] = ['room', 'equipment', 'vehicle', 'other'];

/** A time a resource is held, as the window gives it to whoever shows the resource. */
export interface Booking {
  resource: number;
  start: string;
  end: string;
  all_day: boolean;
  by: string;
  summary: string;
}

export interface Free {
  people: Record<string, 'free' | 'busy' | 'unknown'>;
  away: Record<string, string>;
  resources: Record<string, 'free' | 'busy'>;
  offers?: { start: string; end: string }[];
}

export interface Occurrence {
  event: number;
  master: number;
  calendar: number;
  recurrence_id: string | null;
  summary: string;
  location: string;
  /** Where the meeting is joined online: a PONISTRA meeting's link or another service's. */
  conference: string;
  all_day: boolean;
  start: string;
  end: string;
  status: 'confirmed' | 'tentative' | 'cancelled';
  busy: boolean;
  private: boolean;
  recurring: boolean;
  moved: boolean;
  response: string;
  attendees: number;
  /** Set where the entry is a resource's booking shown among the events, not an event. */
  resource?: number;
  /** Set where the entry is a task on its day, not an event. */
  task?: number;
}

export interface Window {
  events: Occurrence[];
  bookings: Booking[];
  holidays: { date: string; hr: string; en: string }[];
  /** The installation's days off in the window: its weekend, holidays and closed days. */
  days_off: string[];
  birthdays: { date: string; contact: number; name: string; age: number | null }[];
}

export interface Detail {
  id: number;
  calendar: number;
  master: number | null;
  recurrence_id: string | null;
  summary: string;
  location: string;
  conference: string;
  description: string;
  all_day: boolean;
  start: string;
  end: string;
  zone: string;
  rrule: string;
  day_off: DayOff;
  exdates: string[];
  status: 'confirmed' | 'tentative' | 'cancelled';
  busy: boolean;
  private: boolean;
  organizer: { email: string; name: string } | Record<string, never>;
  attendees: { email: string; name: string; role: string; status: string }[];
  response: string;
  reminders: number[];
  read_only: boolean;
  resources: number[];
}

export type Response = 'accepted' | 'tentative' | 'declined';
export const RESPONSES: Response[] = ['accepted', 'tentative', 'declined'];

/** What a message says of a meeting, and where the meeting stands in the user's calendars. */
export interface Invitation {
  method: 'request' | 'cancel' | 'reply' | 'counter';
  event: {
    summary: string;
    location: string;
    all_day: boolean;
    start: string;
    end: string;
    zone: string;
    rrule: string;
    status: string;
    organizer: { email: string; name: string } | Record<string, never>;
    attendees: { email: string; name: string; role: string; status: string }[];
  };
  attendee: { email: string; name: string; status: string } | Record<string, never>;
  held: {
    id: number;
    calendar: number;
    response: string;
    status: string;
    day: string;
    outdated: boolean;
  } | null;
}

/** The user's answer to a meeting, told to whoever asked. */
export function respond(event: number, response: Response, language: string) {
  return postJson<Detail>(`/api/calendar/events/${event}/response?zone=${ZONE}`, {
    response,
    language,
  });
}

/** The day a local instant falls on, as YYYY-MM-DD. */
export function dayOf(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function colorOf(calendar: Pick<Calendar, 'color'> | undefined, dark: boolean): string {
  const swatch = COLORS[(calendar?.color ?? 0) % COLORS.length];
  return dark ? swatch.dark : swatch.light;
}

export function colorCount(): number {
  return COLORS.length;
}

export function useWindow(first: string, last: string, resources: number[] = []) {
  const box = useBox();
  const asked = [...resources].sort((a, b) => a - b).join(',');
  return useQuery({
    queryKey: [...CALENDAR, 'window', box, first, last, asked],
    queryFn: () => {
      const query = new URLSearchParams({ from: first, to: last, zone: ZONE });
      if (asked) query.set('resources', asked);
      return getJson<Window>(inBox(`/api/calendar/events?${query}`, box));
    },
    placeholderData: keepPreviousData,
  });
}

/** The installation's days off from the first day to the last, for a calendar without events. */
export function useDaysOff(first: string, last: string): Set<string> {
  const { data } = useQuery({
    queryKey: [...CALENDAR, 'days-off', first, last],
    queryFn: () =>
      getJson<{ days_off: string[] }>(`/api/calendar/days-off?from=${first}&to=${last}`),
    placeholderData: keepPreviousData,
  });
  return new Set(data?.days_off);
}

export function useResources() {
  return useQuery({
    queryKey: [...CALENDAR, 'resources'],
    queryFn: () => getJson<{ resources: Resource[] }>('/api/calendar/resources'),
  });
}

/** Who of the people and which of the resources is free for the time being arranged. */
export function useFree(
  asked: { start: string; end: string; people: string[]; resources: number[]; except?: number },
  enabled: boolean,
) {
  const query = new URLSearchParams({ zone: ZONE, start: asked.start, end: asked.end });
  if (asked.people.length > 0) query.set('people', asked.people.join(','));
  if (asked.resources.length > 0) query.set('resources', asked.resources.join(','));
  if (asked.except) query.set('except', String(asked.except));
  const path = inBox(`/api/calendar/free?${query}`, useBox());
  return useQuery({
    queryKey: [...CALENDAR, 'free', path],
    queryFn: () => getJson<Free>(path),
    enabled,
    placeholderData: keepPreviousData,
  });
}

/** The first times from the chosen day on, of the span's length, at which the user, the people
 * and the resources are all free. */
export function useOffers(
  asked: { start: string; end: string; people: string[]; resources: number[]; except?: number },
  enabled: boolean,
) {
  const query = new URLSearchParams({
    zone: ZONE,
    start: asked.start,
    end: asked.end,
    offers: '1',
  });
  if (asked.people.length > 0) query.set('people', asked.people.join(','));
  if (asked.resources.length > 0) query.set('resources', asked.resources.join(','));
  if (asked.except) query.set('except', String(asked.except));
  const path = inBox(`/api/calendar/free?${query}`, useBox());
  return useQuery({
    queryKey: [...CALENDAR, 'free', path],
    queryFn: () => getJson<Free>(path),
    enabled,
  });
}

/** A booking in the shape the views draw, under the resource's name and never opened. */
export function heldBy(booking: Booking, resource: string): Occurrence {
  return {
    event: -booking.resource,
    master: -booking.resource,
    calendar: -1,
    recurrence_id: booking.start,
    summary: `${resource}: ${booking.summary || booking.by}`,
    location: booking.summary ? booking.by : '',
    conference: '',
    all_day: booking.all_day,
    start: booking.start,
    end: booking.end,
    status: 'tentative',
    busy: true,
    private: false,
    recurring: false,
    moved: false,
    response: '',
    attendees: 0,
    resource: booking.resource,
  };
}

export function useCalendars() {
  const box = useBox();
  return useQuery({
    queryKey: [...CALENDAR, 'list', box],
    queryFn: () => getJson<Calendars>(inBox('/api/calendar', box)),
  });
}

export function useChanged() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: CALENDAR });
}

function readSet(key: string): Set<number> {
  try {
    const kept = localStorage.getItem(key);
    return new Set(kept ? (JSON.parse(kept) as number[]) : []);
  } catch {
    return new Set();
  }
}

function useRemembered(key: string): [Set<number>, (id: number) => void] {
  const [kept, setKept] = useState(() => readSet(key));
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify([...kept]));
    } catch {
      // Blocked storage only costs remembering the choice between visits.
    }
  }, [key, kept]);
  const toggle = (id: number) =>
    setKept((now) => {
      const next = new Set(now);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return [kept, toggle];
}

/** The calendars the user has hidden, remembered in this browser. */
export function useHidden(): [Set<number>, (id: number) => void] {
  return useRemembered(HIDDEN_KEY);
}

/** The window's holidays and birthdays, unless the user hid them. */
export function shownOf<W extends { holidays: unknown[]; birthdays: unknown[] }>(
  window: W,
  hidden: Set<number>,
): W {
  return {
    ...window,
    holidays: hidden.has(HOLIDAYS) ? [] : window.holidays,
    birthdays: hidden.has(BIRTHDAYS) ? [] : window.birthdays,
  };
}

/** The resources whose bookings the user shows among the events, remembered in this browser. */
export function useShownResources(): [Set<number>, (id: number) => void] {
  return useRemembered(SHOWN_RESOURCES_KEY);
}

/** The current minute, kept current. */
export function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), MINUTE);
    return () => clearInterval(timer);
  }, []);
  return now;
}

/** The timed occurrence under way or nearest ahead among those of the day. */
export function nextOf(events: Occurrence[], now: Date): Occurrence | undefined {
  const at = now.getTime();
  return events
    .filter((each) => !each.all_day && new Date(each.end).getTime() > at)
    .sort((a, b) => a.start.localeCompare(b.start))[0];
}

/** A meeting's link, where its place is one. */
export function linkOf(occurrence: Occurrence): string | null {
  if (occurrence.conference) return occurrence.conference;
  return /^https?:\/\/\S+$/.test(occurrence.location) ? occurrence.location : null;
}

/** "in 12 minutes", "in 2 hours" or "now", in the user's language. */
export function untilText(language: string, start: string, now: Date): string {
  const minutes = Math.round((new Date(start).getTime() - now.getTime()) / MINUTE);
  const format = new Intl.RelativeTimeFormat(language, { numeric: 'always' });
  if (minutes < 60) return format.format(Math.max(minutes, 1), 'minute');
  return format.format(Math.round(minutes / 60), 'hour');
}

/** The plural form a count takes: Croatian has one for 1, one for 2 to 4, one for the rest. */
export function formOf(count: number, language: string): 'one' | 'few' | 'many' {
  if (language !== 'hr') return count === 1 ? 'one' : 'many';
  const last = count % 10;
  const tens = count % 100;
  if (last === 1 && tens !== 11) return 'one';
  if (last >= 2 && last <= 4 && (tens < 12 || tens > 14)) return 'few';
  return 'many';
}
