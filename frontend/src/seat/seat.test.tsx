// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test } from 'vitest';
import { I18nProvider } from '../i18n';
import { serve } from '../testing';
import { Seat } from './Seat';

const NETWORK = {
  cause: 'no-link',
  ponistra: 'https://ponistra.example.org',
  interfaces: [
    { name: 'enp1s0', wireless: false, carrier: false, addresses: null },
    { name: 'wlan0', wireless: true, carrier: true, addresses: ['fe80::1', '192.0.2.7'] },
  ],
  checked_at: '2026-11-25T17:00:00Z',
};

const WIFI = [
  {
    name: 'wlan0',
    powered: true,
    state: 'disconnected',
    scanning: false,
    networks: [
      { id: 'n1', name: 'Office', security: 'psk', signal: -50, connected: false, known: false },
      { id: 'n2', name: 'Home', security: 'psk', signal: -70, connected: false, known: true },
      { id: 'n3', name: 'Corp', security: '8021x', signal: -60, connected: false, known: false },
    ],
  },
];

const BLUETOOTH = {
  adapters: [{ id: 'hci0', address: '00:11:22:33:44:55', powered: true, discovering: false }],
  devices: [
    {
      id: 'd1',
      address: 'AA:BB:CC:DD:EE:01',
      name: 'Headset',
      icon: 'audio-headset',
      paired: false,
      trusted: false,
      connected: false,
      rssi: -58,
    },
  ],
};

function show() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider unchosen="en">
        <Seat />
      </I18nProvider>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

test('the seat says why Ponistra is missing and joins a Wi-Fi network with its password', async () => {
  localStorage.clear();
  const sent: unknown[] = [];
  serve({
    'GET /v1/seat/network': () => NETWORK,
    'GET /v1/seat/wifi': () => WIFI,
    'GET /v1/seat/bluetooth': () => BLUETOOTH,
    'POST /v1/seat/wifi/connect': async (request) => {
      const body = await request.json();
      sent.push(body);
      return body.passphrase === 'right one'
        ? undefined
        : Response.json({ error: 'wrong passphrase' }, { status: 400 });
    },
  });
  const user = show();

  expect(await screen.findByRole('heading', { name: 'No network' })).toBeTruthy();
  expect(screen.getByText('not connected')).toBeTruthy();
  expect(screen.getByText('192.0.2.7')).toBeTruthy();
  expect(screen.getByText('ponistra.example.org')).toBeTruthy();

  await user.click(await screen.findByRole('button', { name: /Office/ }));
  await user.type(screen.getByLabelText('Password'), 'wrong one');
  await user.click(screen.getByRole('button', { name: 'Connect' }));
  expect(await screen.findByText('Wrong password')).toBeTruthy();
  await user.clear(screen.getByLabelText('Password'));
  await user.type(screen.getByLabelText('Password'), 'right one');
  await user.click(screen.getByRole('button', { name: 'Connect' }));
  await expect
    .poll(() => sent)
    .toEqual([
      { network: 'n1', passphrase: 'wrong one' },
      { network: 'n1', passphrase: 'right one' },
    ]);

  await user.click(screen.getByRole('button', { name: /Home/ }));
  expect(screen.queryByLabelText('Password')).toBeNull();
  await user.click(screen.getByRole('button', { name: /Corp/ }));
  expect(screen.getByText(/needs an enterprise sign-in/)).toBeTruthy();
});

test('a device that asks for a PIN is refused with the reason', async () => {
  localStorage.clear();
  serve({
    'GET /v1/seat/network': () => ({
      ...NETWORK,
      cause: 'portal',
      portal_url: 'http://portal.example/',
    }),
    'GET /v1/seat/wifi': () => [],
    'GET /v1/seat/bluetooth': () => BLUETOOTH,
    'POST /v1/seat/bluetooth/pair': () =>
      Response.json({ error: 'pairing refused' }, { status: 400 }),
  });
  const user = show();

  const portal = await screen.findByRole('link', { name: 'Sign in to the network' });
  expect(portal.getAttribute('href')).toBe('http://portal.example/');
  expect(screen.queryByRole('heading', { name: 'Wi-Fi' })).toBeNull();
  const bluetooth = await screen.findByRole('region', { name: 'Bluetooth' });
  await user.click(within(bluetooth).getByRole('button', { name: /Headset/ }));
  await user.click(within(bluetooth).getByRole('button', { name: 'Pair' }));
  expect(await screen.findByText(/asks for a PIN/)).toBeTruthy();
});

test('a screen without the session cookie says it has no access', async () => {
  localStorage.clear();
  const refused = () => Response.json({ error: 'unauthorized' }, { status: 401 });
  serve({
    'GET /v1/seat/network': refused,
    'GET /v1/seat/wifi': refused,
    'GET /v1/seat/bluetooth': refused,
  });
  show();
  expect(
    await screen.findByRole('heading', {
      name: "This screen has no access to the machine's settings",
    }),
  ).toBeTruthy();
});
