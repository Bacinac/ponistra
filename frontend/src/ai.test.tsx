// @vitest-environment jsdom
import { screen, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

test('an administrator sees what the models took and the free requests asked, but not who asked them', async () => {
  const tokens = { cache_read_tokens: 1000, cache_write_tokens: 0 };
  serve({
    'GET /api/ai': () => ({ enabled: true, hint: 'abcd', lost: false, changed_at: null }),
    'GET /api/ai/speech': () => ({ enabled: false, hint: '', lost: false, changed_at: null }),
    'GET /api/runs/usage': () => ({
      spent: [
        {
          month: '2026-10',
          action: 'text.ask',
          runs: 1234,
          input_tokens: 2500,
          output_tokens: 700,
          cost: 0.0123,
          unpriced: 1,
          ...tokens,
        },
        {
          month: '2026-10',
          action: 'text.summarise',
          runs: 2,
          input_tokens: 10,
          output_tokens: 20,
          cost: null,
          unpriced: 2,
          ...tokens,
        },
      ],
      requests: [{ text: 'Skrati tekst.', times: 3, last: '2026-10-22T08:00:00Z' }],
    }),
  });
  open('/ai', { is_admin: true });

  await screen.findByText('Skrati tekst.');
  const [spent, requests] = screen.getAllByRole('table');
  const [, asked, summarised] = within(spent).getAllByRole('row');
  for (const shown of [
    'listopad 2026',
    'Slobodna uputa',
    '1.234',
    '3.500',
    '0,012',
    '1 bez cijene',
  ])
    expect(asked.textContent).toContain(shown);
  expect(summarised.textContent).not.toContain('listopad');
  expect(summarised.textContent).toContain('–');
  const [, request] = within(requests).getAllByRole('row');
  expect(request.textContent).toContain('Skrati tekst.');
  expect(request.textContent).toContain('3');
});

test('an administrator bounds what each user may spend in a month, or lifts the bound', async () => {
  const sent: unknown[] = [];
  let monthly: number | null = 25;
  serve({
    'GET /api/ai': () => ({ enabled: true, hint: 'abcd', lost: false, changed_at: null, monthly }),
    'PATCH /api/ai': async (request) => {
      const given = (await request.json()) as { monthly: number | null };
      sent.push(given);
      monthly = given.monthly;
      return { enabled: true, hint: 'abcd', lost: false, changed_at: null, monthly };
    },
    'GET /api/ai/speech': () => ({ enabled: false, hint: '', lost: false, changed_at: null }),
    'GET /api/runs/usage': () => ({ spent: [], requests: [] }),
  });
  const { user } = open('/ai', { is_admin: true });

  const field = await screen.findByLabelText('Mjesečni strop po korisniku (USD)');
  expect(field).toHaveProperty('value', '25');
  const form = field.closest('form')!;
  await user.clear(field);
  await user.type(field, '12.5');
  await user.click(within(form).getByRole('button', { name: 'Spremi' }));
  await user.clear(field);
  await user.click(within(form).getByRole('button', { name: 'Spremi' }));

  await expect.poll(() => sent).toEqual([{ monthly: 12.5 }, { monthly: null }]);
});
