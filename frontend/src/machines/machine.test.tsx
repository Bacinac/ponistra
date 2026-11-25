// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { I18nProvider } from '../i18n';
import { MachinePage } from './MachinePage';
import { MACHINE_ROUTES } from './routes';

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
globalThis.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  addEventListener() {},
  removeEventListener() {},
})) as unknown as typeof matchMedia;

type Answer = { status?: number; body?: unknown; headers?: Record<string, string> };
type Route = (init: RequestInit) => Answer;

const machine = (variant: 'base' | 'desktop') => ({
  hostname: 'office-pc',
  machine_id: 'm',
  boot_id: 'b',
  booted_at: '2026-11-25T08:00:00Z',
  os: {
    name: 'Ponistra OS',
    image: 'ghcr.io/bacinac/ponistra-os',
    version: '45.3',
    variant,
    kernel: '7.0',
  },
  hardware: {
    vendor: 'Lenovo',
    product: 'ThinkCentre',
    version: '',
    serial: '',
    chassis: 'desktop',
    cpu: 'Ryzen 7',
    cpus: 16,
    memory: 32e9,
  },
  security: { secure_boot: true, tpm: '2.0' },
});

let routes: Record<string, Route>;
let calls: { method: string; path: string; body?: unknown }[];

function stub(given: Record<string, Route | Answer>) {
  routes = Object.fromEntries(
    Object.entries(given).map(([key, route]) => [
      key,
      typeof route === 'function' ? route : () => route,
    ]),
  );
}

beforeEach(() => {
  localStorage.clear();
  calls = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET';
    const path = url.split('?')[0];
    calls.push({ method, path, body: init.body ? JSON.parse(String(init.body)) : undefined });
    const route = routes[`${method} ${path}`];
    const answer = route ? route(init) : { status: 404, body: { error: `no ${method} ${path}` } };
    const status = answer.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(answer.body ?? {}), {
      status,
      headers: answer.headers,
    });
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function open(path = '/') {
  const router = createMemoryRouter(
    [{ path: '/', element: <MachinePage />, children: MACHINE_ROUTES }],
    { initialEntries: [path] },
  );
  render(
    <I18nProvider unchosen="en">
      <RouterProvider router={router} />
    </I18nProvider>,
  );
  return router;
}

const signedIn = (variant: 'base' | 'desktop') => ({
  'GET /api/session': { body: { name: 'admin' } },
  'GET /api/v1/machine': { body: machine(variant) },
  'GET /api/v1/machine/health': {
    body: { state: 'red', failed_units: ['incus.service'], faults: [] },
  },
  'GET /api/v1/health': { body: { status: 'ok', version: '0.9.1' } },
  'GET /api/v1/alerts': {
    body: [
      {
        id: 'disk:sda',
        kind: 'disk',
        subject: 'sda',
        severity: 'critical',
        text: 'sda fails SMART',
        raised_at: '2026-11-25T09:00:00Z',
      },
    ],
  },
  'GET /api/v1/resources': {
    body: {
      load: [0.5, 0.4, 0.3],
      memory: { total: 32e9, available: 16e9, swap_total: 0, swap_free: 0 },
      pressure: {},
      filesystems: [{ path: '/var', size: 100e9, free: 40e9, avail: 40e9 }],
      interfaces: [],
    },
  },
});

test('the sign-in names a wrong password and counts down after too many attempts', async () => {
  const user = userEvent.setup();
  let attempts = 0;
  stub({
    ...signedIn('base'),
    'GET /api/session': { status: 401, body: { error: 'not signed in' } },
    'POST /api/session': () => {
      attempts += 1;
      if (attempts === 1) return { status: 401, body: { error: 'wrong' } };
      if (attempts === 2)
        return { status: 429, body: { error: 'wait' }, headers: { 'Retry-After': '30' } };
      return { body: { name: 'admin' } };
    },
  });
  open('/');
  await user.type(await screen.findByLabelText('Account'), 'admin');
  await user.type(screen.getByLabelText('Password'), 'nope');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  expect((await screen.findByRole('alert')).textContent).toContain('Wrong account or password.');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(await screen.findByText('Too many attempts. Try again in 30 s.')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Sign in' })).toHaveProperty('disabled', true);
  expect(
    calls.filter((call) => call.path === '/api/session' && call.method === 'POST')[0].body,
  ).toEqual({
    name: 'admin',
    password: 'nope',
  });
});

test('a machine without an account says how to make one', async () => {
  const user = userEvent.setup();
  stub({
    'GET /api/session': { status: 401, body: { error: 'not signed in' } },
    'POST /api/session': { status: 503, body: { error: 'no account' } },
  });
  open('/');
  await user.type(await screen.findByLabelText('Account'), 'admin');
  await user.type(screen.getByLabelText('Password'), 'x');
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
  expect((await screen.findByRole('alert')).textContent).toContain('ponistra-agent account set');
});

test('the overview shows the state, the alerts and the machine; the desktop has no guests', async () => {
  stub(signedIn('desktop'));
  open('/');
  expect(await screen.findByText('sda fails SMART')).toBeTruthy();
  expect(await screen.findByText('incus.service')).toBeTruthy();
  expect(screen.getByText('Fault')).toBeTruthy();
  expect(await screen.findByText(/Ponistra OS 45\.3 · desktop/)).toBeTruthy();
  const pages = screen.getByRole('navigation', { name: 'Machine pages' });
  expect(within(pages).queryByRole('link', { name: 'Guests' })).toBeNull();
  expect(within(pages).getByRole('link', { name: 'Overview' }).getAttribute('aria-current')).toBe(
    'page',
  );
});

test('a session that ends brings the sign-in back in place of the page', async () => {
  let expired = false;
  stub({
    ...signedIn('base'),
    'GET /api/v1/tasks': () =>
      expired ? { status: 401, body: { error: 'expired' } } : { body: [] },
  });
  const router = open('/');
  await screen.findByText('office-pc', { selector: 'span' });
  expired = true;
  await router.navigate('/tasks');
  expect(await screen.findByRole('button', { name: 'Sign in' })).toBeTruthy();
  expect(router.state.location.pathname).toBe('/tasks');
});

test('a guest from a recipe sends only what differs from the recipe', async () => {
  const user = userEvent.setup();
  stub({
    ...signedIn('base'),
    'GET /api/v1/guests': { body: [] },
    'GET /api/v1/isos': {
      body: [{ name: 'win11.iso', size: 6e9, created_at: '2026-11-25T09:00:00Z' }],
    },
    'GET /api/v1/guest-networks': { body: [{ name: 'br0', type: 'bridge', managed: false }] },
    'GET /api/v1/recipes': {
      body: [
        {
          id: 'windows-11',
          title: 'Windows 11',
          description: '',
          group: 'workspaces',
          kind: 'vm',
          class: 'work',
          memory: '8GiB',
          cpus: 4,
          disk: '80GiB',
          inputs: [{ name: 'install', title: 'Windows ISO', type: 'iso' }],
        },
      ],
    },
    'POST /api/v1/guests': { status: 202, body: {} },
  });
  open('/guests');
  await user.click(await screen.findByRole('button', { name: 'New guest' }));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByRole('region', { name: 'Workspaces' })).toBeTruthy();
  await user.click(within(dialog).getByRole('button', { name: /Windows 11/ }));
  const create = within(dialog).getByRole('button', { name: 'Create' });
  await user.type(within(dialog).getByLabelText('Name'), 'win-1');
  expect(create).toHaveProperty('disabled', true);
  await user.selectOptions(within(dialog).getByLabelText('Windows ISO'), 'win11.iso');
  await user.selectOptions(within(dialog).getByLabelText('Network'), 'br0');
  await user.click(create);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(
    calls.find((call) => call.method === 'POST' && call.path === '/api/v1/guests')?.body,
  ).toEqual({
    name: 'win-1',
    recipe: 'windows-11',
    inputs: { install: 'win11.iso' },
    network: 'br0',
  });
});
