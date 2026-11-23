// @vitest-environment jsdom
import { screen, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';
import type { Tunnel } from './tunnels';

const NETWORK = {
  address: '203.0.113.139',
  reached: true,
  ports: { udp: 7882, tcp: 7881 },
  relay: '',
  names: [],
  dns: { hint: '', lost: false, error: '', changed_at: null },
};

const CONF = `[Interface]
PrivateKey = yAnz5TF+lXXJte14tji3zlMNq+hd2rYUIgJBgB3fBmk=
Address = 10.9.0.2/32

[Peer]
PublicKey = xTIBA5rboUvnH4htodjb6e697QjLERt1NAB4mZqp8Dg=
Endpoint = vpn.example.org:51820
AllowedIPs = 10.9.0.0/24
`;

const OFFICE: Tunnel = {
  id: 4,
  name: 'Office',
  kind: 'softether',
  enabled: true,
  shown: { server: 'vpn.example.org', port: 443, hub: 'OFFICE', username: 'ponistra' },
  state: 'connecting',
  error: 'refused',
  detail: 'User authentication failed.',
  address: '',
  since: '2026-11-22T10:00:00Z',
};

test('a WireGuard tunnel is added from its configuration and shows the state the service tells', async () => {
  const sent: unknown[] = [];
  let tunnels: Tunnel[] = [];
  serve({
    'GET /api/network': () => NETWORK,
    'GET /api/network/tunnels': () => ({ tunnels }),
    'GET /api/containers/hosts': () => ({ hosts: [] }),
    'POST /api/network/tunnels': async (request) => {
      sent.push(await request.json());
      tunnels = [
        {
          id: 5,
          name: 'Lab',
          kind: 'wireguard',
          enabled: true,
          shown: { address: '10.9.0.2', endpoint: 'vpn.example.org:51820' },
          state: 'up',
          error: '',
          detail: '',
          address: '10.9.0.2',
          since: '2026-11-22T10:00:00Z',
        },
      ];
      return tunnels[0];
    },
  });
  const { user } = open('/network', { is_admin: true });

  expect(await screen.findByText('Nema tunela.')).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Novi tunel' }));
  const dialog = await screen.findByRole('dialog');
  await user.type(within(dialog).getByLabelText('Naziv'), 'Lab');
  await user.click(within(dialog).getByLabelText('Konfiguracija (.conf)'));
  await user.paste(CONF);
  await user.click(within(dialog).getByRole('button', { name: 'Izradi' }));

  expect(await screen.findByText('Spojen')).toBeTruthy();
  expect(screen.getByText('WireGuard · vpn.example.org:51820 · 10.9.0.2')).toBeTruthy();
  expect(sent).toEqual([{ configuration: CONF, kind: 'wireguard', name: 'Lab', enabled: true }]);
});

test('a refused SoftEther tunnel says why, keeps its password when edited and is switched off', async () => {
  const sent: unknown[] = [];
  let tunnels = [OFFICE];
  serve({
    'GET /api/network': () => NETWORK,
    'GET /api/network/tunnels': () => ({ tunnels }),
    'GET /api/containers/hosts': () => ({ hosts: [] }),
    'PATCH /api/network/tunnels/:id': async (request) => {
      const given = await request.json();
      sent.push(given);
      tunnels = [{ ...OFFICE, ...given, state: given.enabled === false ? 'off' : OFFICE.state }];
      return tunnels[0];
    },
  });
  const { user } = open('/network', { is_admin: true });

  expect(
    await screen.findByText('Poslužitelj je odbio prijavu: User authentication failed.'),
  ).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Radnje' }));
  await user.click(await screen.findByRole('menuitem', { name: 'Uredi tunel' }));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).queryByLabelText('Vrsta')).toBeNull();
  await user.clear(within(dialog).getByLabelText('Virtualni hub'));
  await user.type(within(dialog).getByLabelText('Virtualni hub'), 'VPN');
  await user.click(within(dialog).getByRole('button', { name: 'Spremi' }));
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0]).toEqual({
    server: 'vpn.example.org',
    port: 443,
    hub: 'VPN',
    username: 'ponistra',
    password: '',
    kind: 'softether',
    name: 'Office',
    enabled: true,
  });

  await user.click(screen.getByRole('button', { name: 'Radnje' }));
  await user.click(await screen.findByRole('menuitem', { name: 'Isključi' }));
  expect(await screen.findByText('Isključen')).toBeTruthy();
  expect(sent[1]).toEqual({ enabled: false });
});
