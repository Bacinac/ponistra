// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, test } from 'vitest';
import type { Detail } from './calendarData';
import type { Found } from './search';
import { open, serve } from './testing';
import { chooseTheme } from './theme';

const NOTHING: Found = {
  filters: [],
  documents: [],
  mail: [],
  conversations: [],
  events: [],
  tasks: [],
  people: [],
  versions: [],
  help: [],
};

const CALENDARS = {
  calendars: [{ id: 7, name: 'Servis', color: 3, kind: 'own', read_only: false, account: null }],
  next_color: 4,
  unfollowed: [],
  failed: [],
  zone: 'Europe/Zagreb',
};

beforeEach(() => {
  localStorage.clear();
  chooseTheme('system');
});

test('settings, the theme and the language stand in the box as commands on every page', async () => {
  serve({
    'GET /api/tasks': () => ({ tasks: [] }),
    'GET /api/calendar/days-off': () => ({ days_off: [] }),
    'GET /api/search': () => NOTHING,
    'PATCH /api/auth/preferences': async (request) => ({
      user: { id: 1, email: 'ja@example.com', name: 'Ja', ...(await request.json()) },
    }),
  });
  const { user, router, settled } = open('/tasks');
  await settled();
  const search = screen.getByRole('combobox', { name: 'Pretraži' });
  const option = (name: string) => screen.findByRole('option', { name });
  const choose = async (typed: string, name: string) => {
    await user.clear(search);
    await user.type(search, typed);
    await user.click(await option(name));
  };

  await user.type(search, 'tema');
  expect((await option('Tema: Kao sustav')).getAttribute('aria-disabled')).toBe('true');
  await user.click(await option('Tema: Tamna'));
  await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
  await choose('kao sustav', 'Tema: Kao sustav');
  await waitFor(() => expect(document.documentElement.dataset.theme).toBeUndefined());
  await choose('lozink', 'Postavke: Lozinka');
  await waitFor(() => expect(router.state.location.pathname).toBe('/settings/password'));
  await user.clear(search);
  await user.type(search, 'jezik');
  expect((await option('Jezik: Hrvatski')).getAttribute('aria-disabled')).toBe('true');
  await option('Jezik: English');
  await choose('tema', 'Tema: Tamna');
  await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
  await choose('kao sustav', 'Tema: Kao sustav');
  await waitFor(() => expect(document.documentElement.dataset.theme).toBeUndefined());
});

test('events, tasks and people stand in the box in their groups, and a hit opens its event or task', async () => {
  const event: Detail = {
    id: 21,
    calendar: 7,
    master: null,
    recurrence_id: null,
    summary: 'Vulkanizer',
    location: 'Jurić',
    conference: '',
    description: '',
    all_day: false,
    start: '2026-11-03T09:00',
    end: '2026-11-03T10:00',
    zone: 'Europe/Zagreb',
    rrule: '',
    day_off: null,
    exdates: [],
    status: 'confirmed',
    busy: true,
    private: false,
    organizer: {},
    attendees: [],
    response: '',
    reminders: [],
    read_only: false,
    resources: [],
  };
  const task = {
    id: 31,
    text: 'Nazvati vulkanizera',
    due: '2026-11-02',
    done: false,
    done_at: null,
    source: null,
    changed_at: '2026-11-01T10:00:00Z',
  };
  serve({
    'GET /api/nodes/recent': () => ({ items: [] }),
    'GET /api/mail/waiting': () => ({ messages: [] }),
    'GET /api/calendar': () => CALENDARS,
    'GET /api/calendar/days-off': () => ({ days_off: [] }),
    'GET /api/calendar/resources': () => ({ resources: [] }),
    'GET /api/tasks': () => ({ tasks: [task] }),
    'GET /api/search': () => ({
      ...NOTHING,
      events: [
        {
          id: 21,
          master: null,
          calendar: { id: 7, name: 'Servis', color: 3, account: null },
          summary: 'Vulkanizer',
          marked: 'Vulkanizer',
          snippet: '',
          location: 'Jurić',
          all_day: false,
          start: '2026-11-03T09:00',
          end: '2026-11-03T10:00',
          recurring: false,
          hits: 1,
        },
      ],
      tasks: [{ id: 31, text: task.text, marked: task.text, due: task.due, done: false }],
      people: [
        {
          kind: 'contact',
          id: 41,
          name: 'Vulkanizer Jurić',
          organisation: 'Gume',
          title: '',
          email: 'jura@example.com',
          phone: '',
        },
      ],
    }),
    'GET /api/calendar/events': () => ({
      events: [
        {
          event: 21,
          master: 21,
          calendar: 7,
          recurrence_id: null,
          summary: 'Vulkanizer',
          location: 'Jurić',
          conference: '',
          all_day: false,
          start: '2026-11-03T09:00',
          end: '2026-11-03T10:00',
          status: 'confirmed',
          busy: true,
          private: false,
          recurring: false,
          moved: false,
          response: '',
          attendees: 0,
        },
      ],
      bookings: [],
      holidays: [],
      days_off: [],
      birthdays: [],
    }),
    'GET /api/calendar/events/:id': () => event,
  });
  const { user, router, settled } = open('/');
  await settled();

  const search = screen.getByRole('combobox', { name: 'Pretraži' });
  await user.type(search, 'vulkanizer');
  const list = await screen.findByRole('listbox', { name: 'Pretraži' });
  await within(list).findByText('Događaji');
  within(list).getByText('Zadaci');
  within(list).getByText('Ljudi');
  const hit = screen.getByRole('option', { name: /^Vulkanizer(?! Jurić)/ });
  expect(hit.textContent).toContain('Servis');
  expect(screen.getByRole('option', { name: /Vulkanizer Jurić/ }).textContent).toContain('Gume');
  await user.click(hit);
  await waitFor(() => expect(router.state.location.pathname).toBe('/calendar/day/2026-11-03'));
  const opened = await screen.findByRole('dialog', { name: 'Uredi događaj' });
  await waitFor(() =>
    expect(within(opened).getByLabelText('Naziv')).toHaveProperty('value', 'Vulkanizer'),
  );
  await user.click(within(opened).getByRole('button', { name: 'Odustani' }));

  await user.clear(search);
  await user.type(search, 'vulkanizera');
  await user.click(await screen.findByRole('option', { name: /Nazvati vulkanizera/ }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/tasks'));
  const edited = await screen.findByRole('dialog', { name: 'Uredi zadatak' });
  expect(within(edited).getByLabelText('Što')).toHaveProperty('value', 'Nazvati vulkanizera');
});

test('filters are typed or added as chips, and each can be taken out', async () => {
  const title = 'Ponuda za dizalicu';
  const found = {
    id: '6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b',
    parent: null,
    kind: 'document',
    title,
    locale: 'hr',
    updated_at: '2026-11-10T08:00:00Z',
    updated_by: null,
    size: null,
    holds: null,
    media_type: null,
    picture: null,
    extension: null,
    href: null,
    description: '',
    trashed_at: null,
    original: null,
    origin: null,
    macros: null,
    imported: null,
    company: false,
    confined: false,
    notes: false,
    links: false,
    boards: false,
    path: [],
    root: 'mine',
    source: 'title',
    tab: null,
    page: null,
    block: null,
    address: null,
    thread: null,
    hits: 1,
    snippet: title,
  };
  /** The filters as the backend reads them out of the words: a kind it knows, a date it cannot. */
  const read = (q: string) => {
    const filters = [];
    for (const [token, filter] of [
      ['vrsta:dokument', { key: 'kind', raw: 'dokument', value: 'document' }],
      ['datum:jučer', { key: 'date', raw: 'jučer', error: 'invalid_date' }],
    ] as const) {
      const start = q.indexOf(token);
      if (start >= 0) filters.push({ ...filter, token, start, end: start + token.length });
    }
    return filters;
  };
  serve({
    'GET /api/search': (request) => {
      const filters = read(new URL(request.url).searchParams.get('q') ?? '');
      return {
        ...NOTHING,
        filters,
        documents: filters.some((each) => 'error' in each) ? [] : [found],
      };
    },
  });
  const { user, settled } = open(`/search?q=${encodeURIComponent(title)}`);
  await settled();
  const box = screen.getByRole('searchbox', { name: 'Pretraži' });
  await screen.findByRole('heading', { name: 'Dokumenti' });

  await user.click(screen.getByRole('button', { name: 'Dodaj filtar' }));
  // jsdom lays nothing out, so a pointer leaving a submenu's trigger finds no way into it.
  screen.getByRole('menuitem', { name: 'Vrsta' }).focus();
  await user.keyboard('{ArrowRight}');
  (await screen.findByRole('menuitem', { name: 'Dokumenti' })).focus();
  await user.keyboard('{Enter}');
  await waitFor(() => expect(box).toHaveProperty('value', `${title} vrsta:dokument`));
  await waitFor(() =>
    expect(
      screen.getAllByRole('listitem').find((each) => each.textContent?.includes('Vrsta:'))
        ?.textContent,
    ).toContain('Dokumenti'),
  );
  await screen.findByRole('link', { name: new RegExp(title) });
  expect(screen.queryByRole('heading', { name: 'Pošta' })).toBeNull();

  await user.clear(box);
  await user.type(box, `${title} datum:jučer{Enter}`);
  await screen.findByText(/„datum:jučer”: Datum se piše kao/);
  await waitFor(() => expect(screen.queryByRole('link', { name: new RegExp(title) })).toBeNull());
  await user.click(screen.getByRole('button', { name: 'Ukloni filtar datum:jučer' }));
  await waitFor(() => expect(box).toHaveProperty('value', title));
  await screen.findByRole('link', { name: new RegExp(title) });
});
