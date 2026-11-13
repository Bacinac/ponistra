// @vitest-environment jsdom
import { cleanup, screen, waitFor } from '@testing-library/react';
import { expect, test } from 'vitest';
import type { Away } from './away';
import { open, serve } from './testing';

test('time away is set, kept and turned off in the settings', async () => {
  let kept: Away | null = null;
  serve({
    'GET /api/mail/away': () => ({ away: kept }),
    'PUT /api/mail/away': async (request) => {
      kept = { ...(await request.json()), failed: '' };
    },
    'DELETE /api/mail/away': () => {
      kept = null;
    },
  });
  const day = (ahead: number) => {
    const moment = new Date(Date.now() + ahead * 86_400_000);
    const pad = (given: number) => String(given).padStart(2, '0');
    return `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}`;
  };
  const first = open('/settings/away');
  await first.settled();
  const save = screen.getByRole('button', { name: 'Spremi' });
  expect(save).toHaveProperty('disabled', true);
  await first.user.type(screen.getByLabelText('Prvi dan'), day(0));
  await first.user.type(screen.getByLabelText('Zadnji dan'), day(5));
  await first.user.type(
    screen.getByLabelText('Tekst na hrvatskom'),
    'Odsutan sam do kraja tjedna.',
  );
  await first.user.click(save);
  await screen.findByText(/^Odsutnost traje /);

  cleanup();
  const again = open('/settings/away');
  await again.settled();
  await waitFor(() => expect(screen.getByLabelText('Zadnji dan')).toHaveProperty('value', day(5)));
  expect(screen.getByLabelText('Tekst na hrvatskom')).toHaveProperty(
    'value',
    'Odsutan sam do kraja tjedna.',
  );
  await again.user.click(screen.getByRole('button', { name: 'Isključi odsutnost' }));
  await waitFor(() => expect(screen.queryByText(/^Odsutnost traje /)).toBeNull());
});
