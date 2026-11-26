// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { downloads, open, serve } from '../testing';

const ID = '7d4b0f9e-58a3-4d7b-9a8e-3b1f0c2d9e10';
const ivo = { id: 1, name: 'Ivo Bošković', email: 'ivo@example.com' };
const ana = { id: 2, name: 'Ana Horvat', email: 'ana@example.com' };

const computer = {
  id: ID,
  name: 'recepcija',
  connected: false,
  connected_at: null,
  seen_at: '2026-11-26T14:00:00Z',
  agent: '0.2.31',
  facts: {},
  alerts: [
    {
      key: 'disk',
      severity: 'critical',
      text: 'Disk se puni',
      raised_at: '2026-11-26T13:00:00Z',
      cleared_at: null,
    },
  ],
  enrolled_at: '2026-11-20T10:00:00Z',
  left_at: null,
  recovery_key_at: '2026-11-20T10:01:00Z',
  backup_password_at: null,
};

test('a manager sees the computer, opens its recovery key and adds a manager', async () => {
  const added: unknown[] = [];
  serve({
    'GET /api/computers': () => ({
      computers: [computer],
      orphaned: [],
      codes: [],
      can_add: false,
    }),
    'GET /api/computers/:id': () => ({ ...computer, managers: [ivo], openings: [] }),
    'GET /api/computers/:id/agent/v1/machine': () =>
      Response.json({ error: 'computer_offline' }, { status: 503 }),
    'POST /api/computers/:id/secrets/recovery-key': () => ({
      value: '111111-222222-333333',
      at: computer.recovery_key_at,
    }),
    'GET /api/people': () => ({ users: [ivo, ana], groups: [] }),
    'POST /api/computers/:id/managers': async (request) => {
      added.push(await request.json());
    },
  });
  const { user } = open(`/computers/${ID}/manage`);

  const side = await screen.findByRole('navigation', { name: 'Računala' });
  expect(within(side).getByRole('link', { name: /recepcija/ })).toBeTruthy();
  expect(await screen.findByText('Disk se puni')).toBeTruthy();
  expect(screen.getByText(/Nije povezano · zadnji put/)).toBeTruthy();
  expect(screen.getByText('Računalo ga još nije predalo.')).toBeTruthy();

  await user.click(screen.getByRole('button', { name: 'Prikaži' }));
  expect(await screen.findByText('111111-222222-333333')).toBeTruthy();

  await user.selectOptions(await screen.findByLabelText('Novi upravitelj'), 'Ana Horvat');
  await user.click(screen.getByRole('button', { name: 'Dodaj' }));
  await waitFor(() => expect(added).toEqual([{ user: 2 }]));
  const last = screen.getByRole('button', { name: 'Ukloni upravitelja: Ivo Bošković' });
  expect((last as HTMLButtonElement).disabled).toBe(true);
});

test('an administrator makes a stick: the answers, then the code and install.conf to save', async () => {
  const saved = downloads();
  const sent: unknown[] = [];
  serve({
    'GET /api/computers': () => ({ computers: [], orphaned: [], codes: [], can_add: true }),
    'POST /api/computers/install': async (request) => {
      sent.push(await request.json());
      return {
        id: 3,
        hint: 'WXYZ',
        made_at: '2026-11-26T15:00:00Z',
        expires_at: '2026-12-03T15:00:00Z',
        code: 'ABCD-EFGH-JKMN-WXYZ',
        conf: '# Ponistra OS installation\nlanguage = hr\n',
      };
    },
    'GET /api/computers/sticks': () => ({
      version: '0.2.31',
      network: {
        url: 'https://download.example.com/net.img',
        size: 1048576,
        sha256: 'a'.repeat(64),
      },
      full: { url: 'https://download.example.com/full.img', size: 2097152, sha256: 'b'.repeat(64) },
    }),
  });
  const { user } = open('/computers', { is_admin: true });

  expect(await screen.findByText('Nema računala kojima upravljate.')).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Dodaj računalo' }));
  const dialog = await screen.findByRole('dialog', { name: 'Dodaj računalo' });
  await user.type(within(dialog).getByLabelText('Naziv računala'), 'recepcija');
  await user.type(within(dialog).getByLabelText('Wi-Fi mreža'), 'Ured');
  await user.type(within(dialog).getByLabelText('Lozinka Wi-Fi mreže'), 'lozinka-ureda');
  await user.type(within(dialog).getByLabelText('Lozinka računa admin'), 'admin lozinka');
  await user.type(within(dialog).getByLabelText('Ponovite lozinku'), 'admin lozinka');
  await user.click(within(dialog).getByRole('button', { name: 'Izradi datoteku' }));

  expect(await within(dialog).findByText('ABCD-EFGH-JKMN-WXYZ')).toBeTruthy();
  expect(sent).toEqual([
    {
      language: 'hr',
      keyboard: '',
      role: 'workstation',
      hostname: 'recepcija',
      network: 'dhcp',
      wifi: 'Ured',
      wifi_password: 'lozinka-ureda',
      ssh_key: [],
      password: 'admin lozinka',
      erase: false,
    },
  ]);
  await user.click(within(dialog).getByRole('button', { name: 'Preuzmi install.conf' }));
  expect(saved.map((each) => each.name)).toEqual(['install.conf']);
  expect(await saved[0].file.text()).toContain('language = hr');
  expect(await within(dialog).findByRole('link', { name: 'Puni stick' })).toBeTruthy();
});

test("a machine's tabs lead to its pages from any of them", async () => {
  serve({
    'GET /api/computers': () => ({
      computers: [computer],
      orphaned: [],
      codes: [],
      can_add: false,
    }),
    'GET /api/computers/:id': () => ({ ...computer, managers: [ivo], openings: [] }),
    'GET /api/computers/:id/agent/v1/machine': () =>
      Response.json({ error: 'computer_offline' }, { status: 503 }),
  });
  open(`/computers/${ID}/hardware`);

  const tabs = await screen.findByRole('navigation', { name: 'Stranice računala' });
  const href = (name: string) => within(tabs).getByRole('link', { name }).getAttribute('href');
  expect(href('Pregled')).toBe(`/computers/${ID}`);
  expect(href('Opterećenje')).toBe(`/computers/${ID}/pressure`);
  expect(href('Upravljanje')).toBe(`/computers/${ID}/manage`);
});
