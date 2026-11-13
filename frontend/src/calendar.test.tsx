// @vitest-environment jsdom
import { screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { open, serve } from './testing';

function wide(width: number) {
  vi.stubGlobal(
    'matchMedia',
    (query: string) =>
      ({
        matches: Number(query.match(/min-width:\s*(\d+)px/)?.[1] ?? Infinity) <= width,
        media: query,
        onchange: null,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {},
        dispatchEvent: () => false,
      }) as MediaQueryList,
  );
}

test('a shared mailbox shows its own calendars to whom it is shared with', async () => {
  const asked: string[] = [];
  serve({
    'GET /api/calendar': (request) => {
      const box = new URL(request.url).searchParams.get('box');
      asked.push(box ?? '');
      return {
        calendars: [
          box
            ? { id: 2, name: 'Prodaja', color: 1, kind: 'own', read_only: true, account: null }
            : { id: 1, name: 'Moj', color: 0, kind: 'own', read_only: false, account: null },
        ],
        role: box ? 'read' : null,
        next_color: 0,
        unfollowed: [],
        failed: [],
        zone: 'Europe/Zagreb',
      };
    },
    'GET /api/calendar/events': () => ({
      events: [],
      bookings: [],
      holidays: [],
      days_off: [],
      birthdays: [],
    }),
    'GET /api/calendar/days-off': () => ({ days_off: [] }),
    'GET /api/calendar/resources': () => ({ resources: [] }),
    'GET /api/tasks': () => ({ tasks: [] }),
    'GET /api/mail/mailboxes': () => ({
      mailboxes: [{ id: 7, name: 'Prodaja', role: 'read', unseen: 3 }],
    }),
  });
  wide(1400);
  const { user, router, settled } = open('/calendar/month/2026-11-12?box=7');
  await settled();
  const shared = await screen.findByRole('link', { name: 'Prodaja' });
  expect(shared.getAttribute('aria-current')).toBe('page');
  expect(screen.queryByRole('button', { name: 'Novi događaj' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Tjedan' }));
  await waitFor(() => expect(router.state.location.search).toBe('?box=7'));

  await user.click(screen.getByRole('link', { name: 'Moj kalendar' }));
  await waitFor(() => expect(router.state.location.search).toBe(''));
  await screen.findByRole('button', { name: 'Novi događaj' });
  expect(asked).toContain('7');
  expect(asked).toContain('');
});

test('the calendar opens as a list on a phone and as a month on a wide screen', async () => {
  serve({
    'GET /api/calendar': () => ({
      calendars: [],
      next_color: 0,
      unfollowed: [],
      failed: [],
      zone: 'Europe/Zagreb',
    }),
    'GET /api/calendar/days-off': () => ({ days_off: [] }),
    'GET /api/calendar/resources': () => ({ resources: [] }),
    'GET /api/tasks': () => ({ tasks: [] }),
  });
  wide(390);
  const { user, router, settled } = open('/calendar');
  await settled();
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Popis' }).getAttribute('aria-pressed')).toBe('true'),
  );
  await user.click(screen.getByRole('button', { name: 'Mjesec' }));
  await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/calendar\/month\//));
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Mjesec' }).getAttribute('aria-pressed')).toBe(
      'true',
    ),
  );

  wide(1400);
  await router.navigate('/calendar');
  await settled();
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Mjesec' }).getAttribute('aria-pressed')).toBe(
      'true',
    ),
  );
});
