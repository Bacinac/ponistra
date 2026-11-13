// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { beforeAll, expect, test, vi } from 'vitest';
import { installPush, type Subscribed } from './push';
import { open, serve } from './testing';

// A browser that can be asked for notifications and has not been yet, with no subscription of
// its own; read once, as the app reads it, when push.ts loads.
vi.hoisted(() => {
  const registration = { pushManager: { getSubscription: async () => null } };
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: {
      ready: Promise.resolve(registration),
      register: async () => registration,
      addEventListener() {},
      removeEventListener() {},
    },
  });
  Object.assign(globalThis, {
    PushManager: class {},
    Notification: { permission: 'default', requestPermission: async () => 'default' },
  });
});

beforeAll(installPush);

const FIREFOX = 'Mozilla/5.0 (X11; Linux x86_64; rv:150.0) Gecko/20100101 Firefox/150.0';

test("a browser not yet asked offers notifications, and the user's other browsers are listed to remove", async () => {
  const subscriptions: Subscribed[] = [
    {
      id: 5,
      agent: FIREFOX,
      language: 'hr',
      created_at: '2026-10-24T08:00:00Z',
      used_at: null,
      current: false,
    },
  ];
  serve({
    'GET /api/push': () => ({ key: 'key', on: true, subscriptions }),
    'DELETE /api/push/subscriptions/:id': (_, { id }) => {
      subscriptions.splice(
        subscriptions.findIndex((each) => each.id === Number(id)),
        1,
      );
    },
  });
  const { user } = open('/settings/notifications');

  await screen.findByRole('heading', { name: 'Ovaj preglednik' });
  await screen.findByText('Obavijesti su isključene.');
  await screen.findByRole('button', { name: 'Uključi obavijesti' });
  const row = await screen.findByRole('row', { name: /Još nijedna/ });
  expect(within(row).queryByText('Ovaj preglednik')).toBeNull();
  await user.click(within(row).getByRole('button', { name: 'Ukloni' }));
  await screen.findByText('Nijedan preglednik ne prima obavijesti.');
});

test('the administrator turns notifications off for the installation and on again', async () => {
  let on = true;
  serve({
    'GET /api/push': () => ({ key: 'key', on, subscriptions: [] }),
    'GET /api/push/setting': () => ({ on, changed_by: null, changed_at: null }),
    'PATCH /api/push/setting': async (request) => {
      on = (await request.json()).on;
      return { on, changed_by: null, changed_at: null };
    },
  });
  const { user } = open('/settings/notifications', { is_admin: true });

  const installation = await screen.findByRole('checkbox', {
    name: 'Instalacija šalje obavijesti preglednicima',
  });
  await waitFor(() => expect(installation).toHaveProperty('checked', true));
  await user.click(installation);
  await screen.findByText('Administrator je isključio obavijesti za ovu instalaciju.');
  expect(installation).toHaveProperty('checked', false);
  expect(screen.queryByRole('button', { name: 'Uključi obavijesti' })).toBeNull();
  await user.click(installation);
  await screen.findByRole('button', { name: 'Uključi obavijesti' });
  expect(installation).toHaveProperty('checked', true);
});
