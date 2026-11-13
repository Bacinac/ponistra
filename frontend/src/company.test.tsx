// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

const FIREFOX = 'Mozilla/5.0 (X11; Linux x86_64; rv:150.0) Gecko/20100101 Firefox/150.0';
const CHROME =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0 Safari/537.36';

const ana = {
  id: 3,
  email: 'ana@example.com',
  first_name: 'Ana',
  last_name: 'Anić',
  name: 'Ana Anić',
  is_admin: false,
  is_active: true,
  groups: [7],
  last_login: '2026-10-24T08:00:00Z',
  kept_by: null,
  providers: [],
};

function device(id: string, agent: string, current: boolean) {
  return {
    id,
    agent,
    address: '203.0.113.7',
    signed_in_at: '2026-10-24T07:00:00Z',
    seen_at: '2026-10-24T09:00:00Z',
    current,
  };
}

test('an administrator lays out a company folder for a group and asks administrators for passkeys', async () => {
  const folders: object[] = [];
  let posted: unknown;
  const collections: object[] = [];
  let collected: unknown;
  let passkeys = 'nobody';
  let ended = false;
  serve({
    'GET /api/users': () => ({ users: [ana], groups: [{ id: 7, name: 'Financije' }] }),
    'GET /api/identity/providers': () => ({ providers: [] }),
    'GET /api/company': () => ({ folders }),
    'POST /api/company': async (request) => {
      posted = await request.json();
      folders.push({
        id: '0b7e5c1d-2a3f-4e60-9d8c-7b6a5f4e3d2c',
        title: 'Računovodstvo',
        confined: true,
        grants: [
          { group: null, role: 'read' },
          { group: { id: 7, name: 'Financije' }, role: 'own' },
        ],
      });
      return folders[0];
    },
    'GET /api/vault/company': () => ({ collections }),
    'POST /api/vault/company': async (request) => {
      collected = await request.json();
      collections.push({
        id: '5d1f0c2e-7a4b-4c39-8e21-3f6b9a0d7c45',
        name: 'Lozinke financija',
        grants: [{ group: { id: 7, name: 'Financije' }, role: 'own' }],
      });
      return collections[0];
    },
    'GET /api/vault/recovery': () => ({ on: false }),
    'GET /api/policy': () => ({ passkeys }),
    'PATCH /api/policy': async (request) => {
      passkeys = (await request.json()).passkeys;
      return { passkeys };
    },
    'GET /api/users/:id/sessions': () => ({
      sessions: ended ? [] : [device('a1', FIREFOX, false)],
    }),
    'DELETE /api/users/:id/sessions': () => {
      ended = true;
    },
  });
  const { user } = open('/users', { is_admin: true });

  await screen.findByText('Još nema mapa tvrtke.');
  await user.click(screen.getByRole('button', { name: 'Nova mapa tvrtke' }));
  const dialog = screen.getByRole('dialog', { name: 'Nova mapa tvrtke' });
  await user.type(within(dialog).getByLabelText('Naziv'), 'Računovodstvo');
  const create = within(dialog).getByRole('button', { name: 'Izradi' });
  await user.selectOptions(within(dialog).getByLabelText('Svi'), 'Čitanje');
  expect(create).toHaveProperty('disabled', true);
  await user.selectOptions(within(dialog).getByLabelText('Financije'), 'Vlasnik');
  await user.click(within(dialog).getByLabelText(/Bez preuzimanja/));
  await user.click(create);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(posted).toEqual({
    title: 'Računovodstvo',
    confined: true,
    grants: [
      { group: null, role: 'read' },
      { group: 7, role: 'own' },
    ],
  });
  await screen.findByText('Svi: Čitanje · Financije: Vlasnik');
  screen.getByRole('img', { name: 'Bez preuzimanja' });

  screen.getByText('Još nema zbirki sefa tvrtke.');
  await user.click(screen.getByRole('button', { name: 'Nova zbirka sefa' }));
  const vault = screen.getByRole('dialog', { name: 'Nova zbirka sefa' });
  await user.type(within(vault).getByLabelText('Naziv'), 'Lozinke financija');
  expect(within(vault).queryByLabelText(/Bez preuzimanja/)).toBeNull();
  await user.selectOptions(within(vault).getByLabelText('Financije'), 'Vlasnik');
  await user.click(within(vault).getByRole('button', { name: 'Izradi' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(collected).toEqual({ name: 'Lozinke financija', grants: [{ group: 7, role: 'own' }] });
  await screen.findByText('Financije: Vlasnik');
  screen.getByText('Oporavak sefova nije uključen.');

  const policy = screen.getByLabelText('Obavezan pristupni ključ');
  expect(policy).toHaveProperty('value', 'nobody');
  await user.selectOptions(policy, 'Za administratore');
  await waitFor(() => expect(policy).toHaveProperty('value', 'administrators'));
  expect(passkeys).toBe('administrators');

  await user.click(
    within(screen.getByRole('row', { name: /Ana Anić/ })).getByRole('button', { name: 'Radnje' }),
  );
  await user.click(await screen.findByRole('menuitem', { name: 'Uređaji' }));
  const devices = await screen.findByRole('dialog', { name: 'Uređaji: Ana Anić' });
  await within(devices).findByText('Firefox · Linux');
  await user.click(within(devices).getByRole('button', { name: 'Odjavi sa svih uređaja' }));
  await within(devices).findByText('Nema prijavljenih uređaja.');
});

test('a member works in a company folder but leaves the folder itself where it was laid out', async () => {
  serve({
    'GET /api/nodes/company': () => ({
      children: [
        {
          id: '6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b',
          parent: null,
          kind: 'folder',
          title: 'Računovodstvo',
          locale: 'hr',
          updated_at: '2026-10-24T08:00:00Z',
          updated_by: null,
          size: null,
          trashed_at: null,
          original: null,
          macros: null,
          imported: null,
          company: true,
          confined: false,
          role: 'own',
          audience: [{ kind: 'group', id: 7, name: 'Financije', role: 'own' }],
          wider: false,
        },
      ],
    }),
  });
  const { user, router, settled } = open('/documents');
  await settled();
  await user.click(screen.getByRole('link', { name: 'Tvrtka' }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/company'));
  await user.click(
    within(await screen.findByRole('row', { name: /Računovodstvo/ })).getByRole('button', {
      name: 'Radnje',
    }),
  );
  for (const name of ['Preimenuj', 'Premjesti', 'Premjesti u smeće'])
    expect(await screen.findByRole('menuitem', { name })).toHaveProperty('ariaDisabled', 'true');
  expect(screen.getByRole('menuitem', { name: 'Otvori' }).ariaDisabled).toBeNull();
});

test('a user signs another browser out from the list of their devices', async () => {
  let ended = false;
  serve({
    'GET /api/sessions': () => ({
      sessions: [device('b1', CHROME, true), ...(ended ? [] : [device('b2', FIREFOX, false)])],
    }),
    'DELETE /api/sessions/:id': (_, { id }) => {
      ended = id === 'b2';
    },
  });
  const { user } = open('/settings/devices');
  const main = await screen.findByRole('main');
  expect(
    (await within(main).findByRole('row', { name: /Chrome · Windows/ })).textContent,
  ).toContain('Ovaj uređaj');
  await user.click(
    within(within(main).getByRole('row', { name: /Firefox · Linux/ })).getByRole('button', {
      name: 'Odjavi',
    }),
  );
  await waitFor(() => expect(within(main).queryByText('Firefox · Linux')).toBeNull());
  expect(ended).toBe(true);
});

test('an administrator copies a folder of the file server into a company folder and moves it in', async () => {
  const address = '\\\\fs01\\Podaci\\Arhiva';
  const folder = {
    id: '2c4e6a8b-0d1f-4a3c-9e5b-7d9f1b3d5f70',
    title: 'Arhiva',
    confined: false,
    grants: [{ group: { id: 7, name: 'Financije' }, role: 'own' }],
    share: null as object | null,
  };
  const left = [{ path: 'Uprava/Place', why: 'narrower' }];
  const read = {
    address,
    mode: 'copy',
    username: 'FIRMA\\ponistra',
    state: 'read',
    error: '',
    found: { files: 3, folders: 2, bytes: 48_000, free: 9e10, left, left_count: 1 },
    moving: false,
    read_at: '2026-11-05T09:00:00Z',
  };
  const sent: unknown[] = [];
  serve({
    'GET /api/users': () => ({ users: [ana], groups: [{ id: 7, name: 'Financije' }] }),
    'GET /api/identity/providers': () => ({ providers: [] }),
    'GET /api/company': () => ({ folders: [folder] }),
    'POST /api/company/:id/share': async (request) => {
      sent.push(await request.json());
      folder.share = read;
      return { ...read, state: 'reading', found: {} };
    },
    'PATCH /api/company/:id/share': async (request) => {
      sent.push(await request.json());
      folder.share = {
        ...read,
        state: 'ready',
        found: {
          ...read.found,
          copied: 3,
          kept: [{ path: 'Prodaja/Stari.docx', kept: 'unreadable' }],
        },
      };
      return folder.share;
    },
    'POST /api/company/:id/share/move': () => {
      folder.share = null;
      return { ...read, state: 'ready', moving: true };
    },
    'GET /api/vault/company': () => ({ collections: [] }),
    'GET /api/vault/recovery': () => ({ on: false }),
    'GET /api/policy': () => ({ passkeys: 'nobody' }),
  });
  const { user } = open('/users', { is_admin: true });
  const row = () => within(screen.getByText('Arhiva').closest('li')!);
  const choose = async (name: string) => {
    await user.click(row().getByRole('button', { name: 'Radnje' }));
    await user.click(await screen.findByRole('menuitem', { name }));
  };

  await screen.findByText('Arhiva');
  await choose('Spoji s mapom na poslužitelju…');
  const dialog = screen.getByRole('dialog', { name: 'Mapa na poslužitelju: Arhiva' });
  await user.type(within(dialog).getByLabelText('Adresa mape'), address);
  await user.type(within(dialog).getByLabelText('Korisničko ime'), 'FIRMA\\ponistra');
  await user.type(within(dialog).getByLabelText('Lozinka'), 'tajna');
  expect(within(dialog).getByLabelText(/Kopija dok se ne preseli/)).toHaveProperty('checked', true);
  await user.click(within(dialog).getByRole('button', { name: 'Spoji' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(sent).toEqual([{ address, username: 'FIRMA\\ponistra', password: 'tajna', mode: 'copy' }]);
  await row().findByText(/Popis pročitan, čeka kopiranje · Ostaje izvan: 1/);

  await choose('Popis s poslužitelja…');
  const inventory = screen.getByRole('dialog', { name: 'Popis s poslužitelja: Arhiva' });
  within(inventory).getByText('Uprava/Place');
  within(inventory).getByText('uža prava nego mapa iznad');
  await user.click(within(inventory).getByRole('button', { name: 'Kopiraj' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(sent[1]).toEqual({ copy: true });
  await row().findByText(/Osvježeno/);

  await choose('Preseli u Ponistru…');
  await user.click(screen.getByRole('button', { name: 'Preseli' }));
  await waitFor(() => expect(row().queryByText(/fs01/)).toBeNull());
  await choose('Spoji s mapom na poslužitelju…');
  await user.keyboard('{Escape}');
});

test('the shared page switches between what others share with me and what I share', async () => {
  const folder = {
    id: '6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4c',
    parent: null,
    kind: 'folder',
    title: 'Ponude',
    locale: 'hr',
    updated_at: '2026-11-10T08:00:00Z',
    updated_by: null,
    size: null,
    trashed_at: null,
    original: null,
    macros: null,
    imported: null,
    company: false,
    confined: false,
    role: 'own',
    audience: [{ kind: 'everyone', id: null, name: '', role: 'read' }],
    wider: false,
  };
  serve({
    'GET /api/nodes/shared': (request) => ({
      children: new URL(request.url).searchParams.get('by') === 'me' ? [folder] : [],
    }),
  });
  const { user, router, settled } = open('/documents');
  await settled();
  await user.click(screen.getByRole('link', { name: 'Dijeljeno' }));
  await settled();
  const views = await screen.findByRole('group', { name: 'Dijeljeno' });
  expect(within(views).getByRole('button', { name: 'Sa mnom' }).getAttribute('aria-pressed')).toBe(
    'true',
  );
  expect(screen.queryByRole('row', { name: /Ponude/ })).toBeNull();
  await user.click(within(views).getByRole('button', { name: 'Ja dijelim' }));
  await waitFor(() =>
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe(
      '/shared?by=me',
    ),
  );
  await screen.findByRole('row', { name: /Ponude/ });
  expect(screen.queryByRole('row', { name: /Unutra/ })).toBeNull();
});
