// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import type { Collection } from './collections';
import { open, serve } from './testing';

test('a collection is made with consent to recognise bills, and its month is sent on request', async () => {
  const kept: Collection[] = [];
  const asked: string[] = [];
  serve({
    'GET /api/mail/accounts': () => ({ accounts: [] }),
    'GET /api/actions': () => ({ ai: true }),
    'GET /api/search/ai': () => ({ translate: false }),
    'GET /api/collections': () => ({ collections: kept }),
    'POST /api/collections': async (request) => {
      const given = await request.json();
      if (given.recognise && given.consent !== 'once')
        return Response.json({ error: 'consent_needed' }, { status: 428 });
      const made: Collection = {
        ...given,
        id: 7,
        folder: { id: 'f1', title: given.name },
        error: '',
        months: [
          {
            id: 3,
            month: '2026-10',
            folder: { id: 'f2', title: '2026-10' },
            table: null,
            past: true,
            asked_at: null,
            delivered_at: null,
            failed: '',
            kept: 2,
            waiting: 0,
            passed: 1,
            missed: 0,
            due_at: '2026-11-01T08:00:00Z',
          },
        ],
      };
      kept.push(made);
      return made;
    },
    'POST /api/collections/:id/months/:month/send': (_, params) => {
      asked.push(`${params.id}/${params.month}`);
      return {};
    },
  });
  const page = open('/settings/collections');
  await page.settled();
  await page.user.click(screen.getByRole('button', { name: 'Nova zbirka' }));
  await page.user.type(screen.getByLabelText('Naziv'), 'Troškovi');
  await page.user.type(screen.getByLabelText('Pošiljatelji ili domene'), 'anthropic.com');
  await page.user.click(screen.getByLabelText('Prepoznaj račune umjetnom inteligencijom'));
  await page.user.click(screen.getByRole('button', { name: 'Spremi' }));
  const consent = await screen.findByRole('dialog');
  await page.user.click(within(consent).getByRole('button', { name: 'Dopusti' }));

  await screen.findByRole('heading', { name: 'Troškovi' });
  expect(kept[0]).toMatchObject({ senders: ['anthropic.com'], recognise: true, sends: 'draft' });
  expect(screen.getByText('Uzeto: 2 · Nije račun: 1')).toBeTruthy();
  expect(screen.getByText('Nije poslano')).toBeTruthy();
  await page.user.click(screen.getByRole('button', { name: 'Pošalji sada' }));
  await waitFor(() => expect(asked).toEqual(['7/3']));
});
