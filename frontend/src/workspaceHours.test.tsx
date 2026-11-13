// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { I18nProvider } from './i18n';
import { TimeSettings } from './workspaceHours';

const CLOCKIFY = {
  kind: 'clockify',
  address: '',
  person: '',
  offered: [
    { id: 'p2', name: 'Dida' },
    { id: 'p1', name: 'Ponistra' },
  ],
  projects: { ponistra: 'p1' },
  excluded: ['porat'],
  label: 'Razvoj aplikacija',
  since: '2026-11-01',
  nightly: false,
  error: null,
  written_at: null,
  due: 3,
};

let sheets: Record<string, unknown>;
const sent: { method: string; url: string; body: unknown }[] = [];

beforeEach(() => {
  sent.length = 0;
  sheets = {
    projects: ['', 'dida', 'ponistra', 'porat'],
    removal: null,
    sheets: { clockify: CLOCKIFY },
  };
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      sent.push({ method, url, body });
      if (url === '/api/workspace/sheets' && method === 'PATCH')
        sheets = { ...sheets, removal: body.after };
      if (url.endsWith('/compare?month=2026-11'))
        return Promise.resolve(
          Response.json({
            month: '2026-11',
            days: [
              {
                day: '2026-11-12',
                state: 'differs',
                projects: [{ project: 'p1', measured: 3600, own: 1200, others: 0 }],
              },
            ],
          }),
        );
      if (url === '/api/workspace/sheets/clockify' && method === 'POST')
        return Promise.resolve(Response.json({ written: 3, left: 0, error: null }));
      if (method === 'PUT') return Promise.resolve(Response.json(CLOCKIFY));
      return Promise.resolve(Response.json(sheets));
    }),
  );
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime('2026-11-14T09:00:00.000Z');
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function shown() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider>
        <TimeSettings />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

test('a sheet set up shows how it writes and writes when asked, the other waits to be set up', async () => {
  shown();
  const clockify = await screen.findByRole('region', { name: 'Clockify' });
  expect(within(clockify).getByText('Na „Upiši”')).toBeTruthy();
  expect(within(clockify).getByText('3')).toBeTruthy();
  const taskstreamer = screen.getByRole('region', { name: 'TaskStreamer' });
  expect(within(taskstreamer).queryByRole('button', { name: 'Upiši' })).toBeNull();
  expect(within(taskstreamer).getByRole('button', { name: 'Postavi…' })).toBeTruthy();
  await userEvent.click(within(clockify).getByRole('button', { name: 'Upiši' }));
  expect(await within(clockify).findByText('Upisano dana: 3')).toBeTruthy();
  await userEvent.click(within(clockify).getByRole('button', { name: 'Usporedi' }));
  expect(await within(clockify).findByText('Razlikuje se')).toBeTruthy();
  expect(within(clockify).getByText('Ponistra')).toBeTruthy();
});

test('the form maps our projects to the sheet’s and leaves the key as it was unless one is typed', async () => {
  shown();
  const clockify = await screen.findByRole('region', { name: 'Clockify' });
  await userEvent.click(within(clockify).getByRole('button', { name: 'Uredi…' }));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByRole('combobox', { name: 'Porat' })).toHaveProperty('disabled', true);
  await userEvent.selectOptions(within(dialog).getByRole('combobox', { name: 'Dida' }), 'p2');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Spremi' }));
  await waitFor(() => expect(sent.some(({ method }) => method === 'PUT')).toBe(true));
  const put = sent.find(({ method }) => method === 'PUT');
  expect(put?.body).toEqual({
    address: '',
    person: '',
    label: 'Razvoj aplikacija',
    since: '2026-11-01',
    nightly: false,
    projects: { ponistra: 'p1', dida: 'p2' },
    excluded: ['porat'],
    refresh: false,
  });
});

test('the transcripts of archived chats are removed after the days chosen', async () => {
  shown();
  const removal = await screen.findByRole('combobox', { name: 'Brisanje' });
  expect(screen.queryByLabelText('Dana nakon arhiviranja')).toBeNull();
  await userEvent.selectOptions(removal, 'after');
  await waitFor(() =>
    expect(sent.find(({ method }) => method === 'PATCH')?.body).toEqual({ after: 30 }),
  );
  expect(await screen.findByLabelText('Dana nakon arhiviranja')).toHaveProperty('value', '30');
});
