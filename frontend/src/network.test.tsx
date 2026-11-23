// @vitest-environment jsdom
import { screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

const SEEN = {
  address: '203.0.113.139',
  reached: false,
  ports: { udp: 7882, tcp: 7881 },
  relay: 'turn.example.org',
  names: ['turn.example.org'],
  dns: { hint: '', lost: false, error: '', changed_at: null },
};

test('the network page says the ports are not confirmed and keeps a DNS token by how it ends', async () => {
  const sent: unknown[] = [];
  let network: object = SEEN;
  serve({
    'GET /api/network': () => network,
    'GET /api/network/tunnels': () => ({ tunnels: [] }),
    'GET /api/containers/hosts': () => ({ hosts: [] }),
    'PATCH /api/network': async (request) => {
      sent.push(await request.json());
      network = {
        ...SEEN,
        dns: { hint: 'cdef', lost: false, error: '', changed_at: '2026-11-16T10:00:00Z' },
      };
      return network;
    },
  });
  const { user } = open('/network', { is_admin: true });

  expect(await screen.findByText('Nije potvrđeno')).toBeTruthy();
  expect(screen.getByText('UDP 7882, TCP 7881')).toBeTruthy();
  await user.type(
    screen.getByLabelText('Cloudflare API token (Zone: Read, DNS: Edit)'),
    'token-cdef',
  );
  await user.click(screen.getByRole('button', { name: 'Spremi' }));

  await screen.findByText(/Spremljeni token završava s/);
  expect(sent).toEqual([{ token: 'token-cdef' }]);
  await user.click(screen.getByRole('button', { name: 'Ukloni token' }));
  await expect.poll(() => sent).toEqual([{ token: 'token-cdef' }, { token: '' }]);
});

test('without names pointing straight at it the installation asks for no token', async () => {
  serve({
    'GET /api/network': () => ({ ...SEEN, reached: true, relay: '', names: [] }),
    'GET /api/network/tunnels': () => ({ tunnels: [] }),
    'GET /api/containers/hosts': () => ({ hosts: [] }),
  });
  open('/network', { is_admin: true });
  expect(await screen.findByText('Dostupno')).toBeTruthy();
  expect(screen.queryByLabelText('Cloudflare API token (Zone: Read, DNS: Edit)')).toBeNull();
});

test('a user who is not an administrator does not reach the network page', async () => {
  serve({ 'GET /api/network': () => SEEN });
  open('/network', { is_admin: false });
  expect(screen.queryByText('Javna adresa')).toBeNull();
});
