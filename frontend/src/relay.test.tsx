// @vitest-environment jsdom
import { screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

const NONE = { provider: '', addresses: [], name: '', hint: '', lost: false, changed_at: null };

test("an administrator sets Cloudflare's key as the meetings' relay, its token shown only by how it ends", async () => {
  const sent: unknown[] = [];
  let relay: object = NONE;
  serve({
    'GET /api/meetings/relay': () => relay,
    'PATCH /api/meetings/relay': async (request) => {
      sent.push(await request.json());
      relay = {
        ...NONE,
        provider: 'cloudflare',
        name: 'f3a9',
        hint: 'cdef',
        changed_at: '2026-11-12T16:00:00Z',
      };
      return relay;
    },
  });
  const { user } = open('/meetings', { is_admin: true });

  await user.selectOptions(await screen.findByLabelText('Vanjski relej (TURN)'), 'cloudflare');
  expect(screen.queryByLabelText('Adrese, jedna po retku')).toBeNull();
  await user.type(screen.getByLabelText('ID ključa (Key ID)'), 'f3a9');
  await user.type(screen.getByLabelText('API token'), 'token-cdef');
  await user.click(screen.getByRole('button', { name: 'Spremi' }));

  await screen.findByText(/Spremljena vrijednost završava s/);
  expect(sent).toEqual([
    { provider: 'cloudflare', addresses: [], name: 'f3a9', secret: 'token-cdef' },
  ]);
  expect(screen.getByLabelText('API token')).toHaveProperty('value', '');
});

test('another TURN service is its addresses, a user name and a password kept unless replaced', async () => {
  const sent: unknown[] = [];
  const relay = {
    ...NONE,
    provider: 'turn',
    addresses: ['turn:relay.example.com:3478'],
    name: 'ponistra',
    hint: 'ja-9',
  };
  serve({
    'GET /api/meetings/relay': () => relay,
    'PATCH /api/meetings/relay': async (request) => {
      sent.push(await request.json());
      return relay;
    },
  });
  const { user } = open('/meetings', { is_admin: true });

  const addresses = await screen.findByLabelText('Adrese, jedna po retku');
  await user.type(addresses, '\nturns:relay.example.com:443?transport=tcp');
  await user.click(screen.getByRole('button', { name: 'Spremi' }));

  await expect
    .poll(() => sent)
    .toEqual([
      {
        provider: 'turn',
        addresses: ['turn:relay.example.com:3478', 'turns:relay.example.com:443?transport=tcp'],
        name: 'ponistra',
      },
    ]);
});

test('a user who is not an administrator does not reach the setting', async () => {
  serve({ 'GET /api/meetings/relay': () => NONE });
  open('/meetings', { is_admin: false });
  expect(screen.queryByLabelText('Vanjski relej (TURN)')).toBeNull();
});
