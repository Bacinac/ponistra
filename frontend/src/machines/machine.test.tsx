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

test('a full battery is not an alarm, a nearly empty one and a nearly full disk are', async () => {
  stub({
    ...signedIn('desktop'),
    'GET /api/v1/hardware': {
      body: {
        temperatures: [],
        disks: [],
        batteries: [
          { name: 'BAT0', status: 'Full', capacity: 100, health: 100, cycles: 476 },
          { name: 'BAT1', status: 'Discharging', capacity: 8 },
        ],
        errors: [],
      },
    },
    'GET /api/v1/resources': {
      body: {
        load: [0.5, 0.4, 0.3],
        memory: { total: 32e9, available: 16e9, swap_total: 0, swap_free: 0 },
        pressure: {},
        filesystems: [{ path: '/var', size: 100e9, free: 5e9, avail: 5e9 }],
        interfaces: [],
      },
    },
  });
  const alarmed = (label: string) =>
    screen.getByRole('meter', { name: label }).firstElementChild!.classList.contains('bg-danger');
  const router = open('/');
  await screen.findByRole('meter', { name: '/var' });
  expect(alarmed('/var')).toBe(true);
  await router.navigate('/hardware');
  await screen.findByRole('meter', { name: 'BAT0' });
  expect(alarmed('BAT0')).toBe(false);
  expect(alarmed('BAT1')).toBe(true);
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

const image = (extra: object = {}) => ({
  follows: 'ghcr.io/bacinac/ponistra-os:stable',
  channel: 'stable',
  role: 'server',
  booted: null,
  staged: null,
  rollback: null,
  rollback_queued: false,
  available: null,
  job: null,
  ...extra,
});

test('a workspace takes an owner and names what its firewall opens; a staged workstation takes no guest', async () => {
  const user = userEvent.setup();
  stub({
    ...signedIn('base'),
    'GET /api/v1/guests': { body: [] },
    'GET /api/v1/image': { body: image() },
    'GET /api/v1/isos': { body: [] },
    'GET /api/v1/guest-networks': { body: [] },
    'GET /api/v1/network': {
      body: {
        config: { uplink: 'aa', bridge: true, address: { mode: 'dhcp' }, guest_ports: ['bb'] },
        links: [
          { name: 'eno1', kind: 'port', mac: 'aa', carrier: true, addresses: [] },
          { name: 'eno2', kind: 'port', mac: 'bb', carrier: true, addresses: [] },
        ],
      },
    },
    'GET /api/v1/recipes': {
      body: [
        {
          id: 'desk',
          title: 'Desk',
          description: '',
          group: 'workspaces',
          kind: 'lxc',
          class: 'work',
          memory: '4GiB',
          cpus: 2,
          disk: '20GiB',
          open: 'tcp/443 udp/51820',
          inputs: [
            { name: 'wan', title: 'WAN', type: 'port' },
            { name: 'domain', title: 'Domain', type: 'text', pattern: '[a-z.]+', default: '' },
          ],
        },
      ],
    },
    'POST /api/v1/guests': { status: 202, body: {} },
  });
  open('/guests');
  await user.click(await screen.findByRole('button', { name: 'New guest' }));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByText('tcp/443 udp/51820')).toBeTruthy();
  await user.click(within(dialog).getByRole('button', { name: /Desk/ }));
  await user.type(within(dialog).getByLabelText('Name'), 'desk-1');
  await user.type(within(dialog).getByLabelText('Domain'), 'Bad Domain');
  const create = within(dialog).getByRole('button', { name: 'Create' });
  await user.selectOptions(await within(dialog).findByLabelText('WAN'), 'eno2');
  expect(create).toHaveProperty('disabled', true);
  await user.clear(within(dialog).getByLabelText('Domain'));
  await user.type(within(dialog).getByLabelText('Owner'), 'ana@example.com');
  await user.click(create);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(
    calls.find((call) => call.method === 'POST' && call.path === '/api/v1/guests')?.body,
  ).toEqual({ name: 'desk-1', recipe: 'desk', inputs: { wan: 'eno2' }, owner: 'ana@example.com' });

  stub({
    ...signedIn('base'),
    'GET /api/v1/guests': { body: [] },
    'GET /api/v1/image': { body: image({ staged_role: 'workstation' }) },
  });
  cleanup();
  open('/guests');
  expect(await screen.findByText(/takes no new guests until it restarts/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'New guest' })).toHaveProperty('disabled', true);
  expect(screen.getByRole('button', { name: 'Import from Proxmox' })).toHaveProperty(
    'disabled',
    true,
  );
});

test('a network change goes on trial, counts down and is confirmed', async () => {
  const user = userEvent.setup();
  const config = {
    uplink: 'aa',
    bridge: false,
    address: { mode: 'dhcp' },
    vlans: [],
    guest_ports: [],
  };
  const links = [
    { name: 'eno1', kind: 'port', mac: 'aa', carrier: true, addresses: ['10.0.0.5/24'] },
  ];
  let pending: object | undefined;
  stub({
    ...signedIn('base'),
    'GET /api/v1/network': () => ({ body: { config, links, pending } }),
    'PUT /api/v1/network': () => {
      pending = { deadline: new Date(Date.now() + 120_000).toISOString(), previous: config };
      return { status: 202, body: { config, links, pending } };
    },
    'POST /api/v1/network/confirm': () => {
      pending = undefined;
      return { body: { config, links } };
    },
  });
  open('/network');
  await user.click(await screen.findByRole('button', { name: 'Change the network' }));
  const dialog = await screen.findByRole('dialog');
  await user.selectOptions(within(dialog).getByLabelText('Address'), 'static');
  await user.type(within(dialog).getByLabelText('Address with prefix'), '10.0.0.9/24');
  await user.type(within(dialog).getByLabelText('Gateway'), '10.0.0.1');
  await user.click(within(dialog).getByRole('checkbox', { name: /bridge br0/ }));
  await user.click(within(dialog).getByRole('button', { name: 'Add a VLAN' }));
  await user.type(within(dialog).getByLabelText('VLAN'), '20');
  await user.click(within(dialog).getByRole('button', { name: 'Apply on trial' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(calls.find((call) => call.method === 'PUT')?.body).toEqual({
    uplink: 'aa',
    bridge: true,
    address: { mode: 'static', address: '10.0.0.9/24', gateway: '10.0.0.1' },
    vlans: [{ id: 20, bridge: true, address: { mode: 'none' } }],
    guest_ports: [],
  });
  expect(await screen.findByText(/undoes itself in [12]:\d\d unless you confirm/)).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Confirm' }));
  await waitFor(() => expect(screen.queryByText(/undoes itself/)).toBeNull());
});

test("a guest's firewall shows its rules and replaces them", async () => {
  const user = userEvent.setup();
  const firewall = {
    ingress_default: 'drop',
    egress_default: 'allow',
    ingress: [{ action: 'allow', protocol: 'tcp', port: '443', description: 'web' }],
    egress: [],
    nics: [
      { name: 'eth0', network: 'br0', attached: true },
      { name: 'eth1', network: 'eno2', attached: false, reason: 'a macvlan carries no firewall' },
    ],
  };
  stub({
    ...signedIn('base'),
    'GET /api/v1/guests/web-1': {
      body: {
        name: 'web-1',
        kind: 'lxc',
        recipe: '',
        status: 'Stopped',
        description: '',
        profiles: [],
        autostart: false,
        created_at: '2026-11-25T08:00:00Z',
        last_used_at: '2026-11-25T08:00:00Z',
        memory_limit: '',
        cpu_limit: '',
        memory: 0,
        memory_peak: 0,
        cpu_time: 0,
        disk: null,
        addresses: null,
        processes: 0,
        snapshots: 0,
        snapshot_policy: '',
      },
    },
    'GET /api/v1/guests/web-1/snapshots': { body: [] },
    'GET /api/v1/guests/web-1/firewall': { body: firewall },
    'PUT /api/v1/guests/web-1/firewall': { body: firewall },
    'GET /api/v1/tasks': { body: [] },
  });
  open('/guests/web-1');
  const part = await screen.findByRole('region', { name: 'Firewall' });
  expect(await within(part).findByText('a macvlan carries no firewall')).toBeTruthy();
  expect(within(part).getByText('web')).toBeTruthy();
  await user.click(within(part).getByRole('button', { name: 'Edit the rules' }));
  const dialog = await screen.findByRole('dialog');
  const outgoing = within(dialog).getByRole('group', { name: 'Outgoing' });
  await user.click(within(outgoing).getByRole('button', { name: 'Add a rule' }));
  await user.type(within(outgoing).getByLabelText('Destination'), '10.0.0.0/8');
  await user.selectOptions(within(outgoing).getByLabelText('Protocol'), '');
  await user.click(within(dialog).getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(calls.find((call) => call.method === 'PUT')?.body).toEqual({
    ingress_default: 'drop',
    egress_default: 'allow',
    ingress: [{ action: 'allow', protocol: 'tcp', port: '443', description: 'web' }],
    egress: [{ action: 'drop', destination: '10.0.0.0/8' }],
  });
});

test('the machine enrolls in a Ponistra with its code, warns of a key left behind and switches channel', async () => {
  const user = userEvent.setup();
  stub({
    ...signedIn('desktop'),
    'GET /api/v1/ponistra': { body: { state: 'not-enrolled', url: 'https://office.example' } },
    'POST /api/v1/ponistra/enroll': {
      body: { state: 'connecting', url: 'https://office.example', recovery_key: 'machine' },
    },
  });
  open('/ponistra');
  await user.click(await screen.findByRole('button', { name: 'Enroll in Ponistra' }));
  const dialog = await screen.findByRole('dialog');
  await user.type(within(dialog).getByLabelText('Code from Ponistra'), 'abc-123');
  expect(within(dialog).getByLabelText('Machine name')).toHaveProperty('value', 'office-pc');
  await user.click(within(dialog).getByRole('button', { name: 'Enroll in Ponistra' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(calls.find((call) => call.path === '/api/v1/ponistra/enroll')?.body).toEqual({
    code: 'abc-123',
    url: 'https://office.example',
    name: 'office-pc',
  });

  cleanup();
  stub({
    ...signedIn('desktop'),
    'GET /api/v1/ponistra': {
      body: { state: 'connected', url: 'https://office.example', recovery_key: 'machine' },
    },
    'GET /api/v1/image': { body: image() },
    'POST /api/v1/image/channel': { status: 202, body: {} },
  });
  const router = open('/ponistra');
  expect((await screen.findByRole('alert')).textContent).toContain('still on the machine');
  expect(screen.getByRole('button', { name: 'Leave Ponistra' })).toBeTruthy();
  await router.navigate('/image');
  await user.click(await screen.findByRole('button', { name: 'Switch to test' }));
  await waitFor(() =>
    expect(calls.find((call) => call.path === '/api/v1/image/channel')?.body).toEqual({
      channel: 'test',
    }),
  );
});

test("another account's guest says so instead of opening its files", async () => {
  stub({
    ...signedIn('base'),
    'GET /api/v1/guests/desk-1/snapshots/daily/files': {
      status: 403,
      body: { error: 'forbidden' },
    },
  });
  open('/guests/desk-1/snapshots/daily');
  expect(
    await screen.findByText(/belongs to another account: only its owner opens its files/),
  ).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Restore' })).toBeNull();
});
