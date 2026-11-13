// @vitest-environment jsdom
import { screen, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import type { Drive } from './drive';
import { open, serve } from './testing';

test('a Google account takes its Drive, shows how far it came and finishes the move', async () => {
  let drive: Drive | null = null;
  const finished: number[] = [];
  serve({
    'GET /api/drive': () => ({
      ready: true,
      accounts: [{ account: 7, address: 'ivo@example.com', drive }],
    }),
    'POST /api/drive': async (request) => {
      expect(await request.json()).toEqual({ account: 7 });
      drive = {
        id: 3,
        state: 'ready',
        error: '',
        finishing: false,
        read_at: '2026-11-11T17:00:00Z',
        spaces: [
          {
            folder: 'f-1',
            title: 'Google Drive',
            shared: false,
            found: {
              files: 12,
              folders: 3,
              bytes: 2048,
              left: [{ id: 'q1', name: 'Anketa', why: 'google_only' }],
              left_count: 1,
            },
            read_at: null,
          },
        ],
      };
      return drive;
    },
    'POST /api/drive/:id/finish': (_, { id }) => {
      finished.push(Number(id));
      drive = { ...drive!, finishing: true };
      return drive;
    },
  });
  const { user } = open('/settings/google');

  await user.click(await screen.findByRole('button', { name: 'Preuzmi Google Drive' }));

  expect(await screen.findByText('Ostaje izvan: 1')).toBeTruthy();
  const links = screen.getAllByRole('link', { name: 'Google Drive' });
  expect(links.map((link) => link.getAttribute('href'))).toContain('/f/f-1');
  await user.click(screen.getByRole('button', { name: 'Završi prelazak…' }));
  const dialog = await screen.findByRole('alertdialog');
  await user.click(within(dialog).getByRole('button', { name: 'Završi' }));

  expect(await screen.findByText('Prelazak se završava…')).toBeTruthy();
  expect(finished).toEqual([3]);
});

test('a Drive Google stopped asks its user to sign in through Google again', async () => {
  serve({
    'GET /api/drive': () => ({
      ready: true,
      accounts: [
        {
          account: 7,
          address: 'ivo@example.com',
          drive: {
            id: 3,
            state: 'copying',
            error: 'drive_scope',
            finishing: false,
            read_at: null,
            spaces: [],
          },
        },
      ],
    }),
  });
  open('/settings/google');

  expect(
    await screen.findByRole('button', { name: 'Ponovno se prijavi preko Googlea' }),
  ).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Pokušaj ponovno' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Završi prelazak…' })).toHaveProperty('disabled', true);
});
