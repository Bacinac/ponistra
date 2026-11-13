// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

/** What the pages a module holds ask for, as an account with nothing in them answers. */
const PAGES = {
  'GET /api/nodes/recent': () => ({ items: [] }),
  'GET /api/calendar': () => ({
    calendars: [],
    next_color: 0,
    unfollowed: [],
    failed: [],
    zone: 'Europe/Zagreb',
  }),
  'GET /api/calendar/days-off': () => ({ days_off: [] }),
  'GET /api/tasks': () => ({ tasks: [] }),
  'GET /api/contacts': () => ({ contacts: [], failed: [], directories: [] }),
  'GET /api/mail/waiting': () => ({ messages: [] }),
  'GET /api/notes': () => ({ folder: null, notes: [] }),
  'GET /api/passkeys': () => ({ passkeys: [] }),
};

test('a place within a module goes up to it from the header, a module’s own page does not', async () => {
  serve(PAGES);
  const { user, router, settled } = open('/contacts');
  const modules = /^(Danas|Kalendar|Pošta|Razgovori|Dokumenti)$/;
  for (const [place, title, up, address] of [
    ['/contacts', 'Kontakti', 'Razgovori', '/chat'],
    ['/tasks', 'Zadaci', 'Danas', '/'],
    ['/notes', 'Bilješke', 'Dokumenti', '/documents'],
  ] as const) {
    await router.navigate(place);
    await settled();
    const header = screen.getByRole('banner');
    await within(header).findByRole('heading', { name: title, level: 1 });
    await user.click(within(header).getByRole('link', { name: up }));
    await waitFor(() => expect(router.state.location.pathname).toBe(address));
    await settled();
    await waitFor(() =>
      expect(within(screen.getByRole('banner')).queryAllByRole('link', { name: modules })).toEqual(
        [],
      ),
    );
  }
  await router.navigate('/settings');
  await settled();
  const header = screen.getByRole('banner');
  await within(header).findByRole('heading', { level: 1 });
  expect(within(header).queryAllByRole('link', { name: modules })).toEqual([]);
});

test('the account menu opens what the app does, its author, licence and version', async () => {
  serve(PAGES);
  const { user, settled } = open('/');
  await settled();
  await user.click(screen.getByRole('button', { name: /^Račun / }));
  await user.click(await screen.findByRole('menuitem', { name: 'O aplikaciji' }));
  const about = await screen.findByRole('dialog', { name: 'O aplikaciji' });
  expect(about.textContent).toContain('na vlastiti poslužitelj');
  expect(within(about).getAllByRole('listitem')).toHaveLength(10);
  expect(about.textContent).toContain('Copyright © 2026 Ivo Bošković');
  await waitFor(() => expect(about.textContent).toMatch(/Inačica \S+/));
  expect(within(about).getByRole('link', { name: 'Licenca' }).getAttribute('href')).toBe(
    'https://polyformproject.org/licenses/noncommercial/1.0.0',
  );
  expect(within(about).getByRole('link', { name: 'Izvorni kod' }).getAttribute('href')).toBe(
    'https://github.com/Bacinac/ponistra',
  );
  await user.click(within(about).getByRole('button', { name: 'Zatvori' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'O aplikaciji' })).toBeNull());
});
