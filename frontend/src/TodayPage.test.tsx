// @vitest-environment jsdom
import { screen, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

/** What Today shows beside the mail, as an account with none of it answers. */
const TODAY = {
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
};

const MESSAGE = {
  folder: 3,
  account: null,
  to: [],
  date: new Date().toISOString(),
};

test('the mail waiting stands on Today and opens there, before the recent documents', async () => {
  const waiting = {
    messages: [
      {
        ...MESSAGE,
        id: 11,
        subject: 'Ponuda za Končar',
        sender: { name: 'Ana Kovač', address: 'ana@example.test' },
        seen: false,
        flagged: false,
      },
      {
        ...MESSAGE,
        id: 12,
        subject: 'Ugovor',
        sender: { name: '', address: 'iva@example.test' },
        seen: true,
        flagged: true,
      },
    ],
    count: 7,
  };
  serve({ ...TODAY, 'GET /api/mail/waiting': () => waiting });
  open('/');
  const mail = await screen.findByRole('region', { name: 'Pošta koja čeka' });
  expect(await within(mail).findByRole('link', { name: 'Pošta (7)' })).toHaveProperty(
    'pathname',
    '/mail',
  );
  expect(within(mail).getByRole('link', { name: /Ugovor/ }).textContent).toContain(
    'iva@example.test',
  );
  expect(within(mail).getAllByRole('img', { name: 'Omiljeno' })).toHaveLength(1);
  expect(within(mail).getByRole('link', { name: /Ponuda za Končar/ })).toHaveProperty(
    'pathname',
    '/mail/3/11',
  );
  const recent = screen.getByRole('region', { name: 'Nedavni dokumenti' });
  expect(mail.compareDocumentPosition(recent) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test('Today says so while no mail waits', async () => {
  serve({ ...TODAY, 'GET /api/mail/waiting': () => ({ messages: [], count: 0 }) });
  open('/');
  const mail = await screen.findByRole('region', { name: 'Pošta koja čeka' });
  await within(mail).findByText('Nijedna poruka ne čeka.');
});
