// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

let made = 0;

/** A node of the user's own as the tree lists it. */
function node(title: string, given: object = {}) {
  made += 1;
  return {
    id: `6f1c2a3b-4d5e-4f60-8a7b-${String(made).padStart(12, '0')}`,
    parent: null as string | null,
    kind: 'document',
    title,
    locale: 'hr',
    updated_at: '2026-11-10T08:00:00Z',
    updated_by: null,
    size: null,
    holds: null,
    media_type: null,
    picture: null,
    extension: null,
    href: null,
    description: '',
    trashed_at: null as string | null,
    original: null,
    origin: null,
    macros: null,
    imported: null,
    company: false,
    confined: false,
    notes: false,
    links: false,
    boards: false,
    role: 'own',
    audience: [],
    wider: false,
    kept: null,
    ...given,
  };
}

type Node = ReturnType<typeof node>;

/** The item of the list that says the text; none once the list itself is gone. */
function item(list: string, text: string) {
  return [...(screen.queryByRole('list', { name: list })?.children ?? [])].find((each) =>
    each.textContent?.includes(text),
  ) as HTMLElement | undefined;
}

/** The user's tree as the server keeps it: what is listed in a folder, in the trash, gone. */
function tree(nodes: Node[]) {
  const ids = async (request: Request) => (await request.json()).nodes as string[];
  const listing = (parent: string | null) => ({
    path: nodes.filter((each) => each.id === parent),
    root: 'mine',
    role: 'own',
    confined: false,
    folder: nodes.find((each) => each.id === parent) ?? null,
    children: nodes.filter((each) => each.parent === parent && !each.trashed_at),
  });
  return {
    'GET /api/nodes': (request: Request) =>
      listing(new URL(request.url).searchParams.get('parent')),
    'GET /api/nodes/:id': (_: Request, { id }: Record<string, string>) => ({
      ...nodes.find((each) => each.id === id),
      ...listing(id),
    }),
    'GET /api/trash': () => ({ items: nodes.filter((each) => each.trashed_at) }),
    'POST /api/nodes/trash': async (request: Request) => {
      for (const id of await ids(request))
        nodes.find((each) => each.id === id)!.trashed_at = '2026-11-11T09:00:00Z';
    },
    'POST /api/trash/restore': async (request: Request) => {
      for (const id of await ids(request)) nodes.find((each) => each.id === id)!.trashed_at = null;
    },
    'POST /api/trash/purge': async (request: Request) => {
      const gone = await ids(request);
      nodes.splice(0, nodes.length, ...nodes.filter((each) => !gone.includes(each.id)));
    },
  };
}

test('trashed documents are chosen by a long press and restored or purged together', async () => {
  const titles = ['Prvi', 'Drugi', 'Treći'];
  const nodes = titles.map((title) => node(title, { trashed_at: '2026-11-11T09:00:00Z' }));
  serve(tree(nodes));
  const { user, router, settled } = open('/trash');
  await settled();
  const row = (title: string) => item('Smeće', title);
  within(row(titles[0])!).getByRole('button', { name: 'Vrati' });
  await user.pointer({
    keys: '[MouseLeft>]',
    target: within(row(titles[0])!).getByRole('button', { name: new RegExp(titles[0]) }),
  });
  await screen.findByText('Odabrano: 1');
  await user.pointer({ keys: '[/MouseLeft]' });
  await user.click(within(row(titles[1])!).getByRole('button', { name: new RegExp(titles[1]) }));
  await screen.findByText('Odabrano: 2');
  expect(within(row(titles[0])!).queryByRole('button', { name: 'Vrati' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Vrati' }));
  await waitFor(() => expect(row(titles[0])).toBeUndefined());
  expect(row(titles[1])).toBeUndefined();

  await user.keyboard('{Control>}');
  await user.click(within(row(titles[2])!).getByRole('button', { name: new RegExp(titles[2]) }));
  await user.keyboard('{/Control}');
  await user.click(screen.getByRole('button', { name: 'Trajno obriši' }));
  await user.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Trajno obriši' }),
  );
  await waitFor(() => expect(row(titles[2])).toBeUndefined());

  await router.navigate('/documents');
  await settled();
  for (const title of titles.slice(0, 2)) {
    await screen.findByRole('row', { name: new RegExp(title) });
  }
});

test('rows chosen in a folder carry their actions in the header and Escape lets them go', async () => {
  const folder = node('Odabir', { kind: 'folder' });
  const nodes = [folder, ...['Jedan', 'Dva'].map((title) => node(title, { parent: folder.id }))];
  serve(tree(nodes));
  const { user, settled } = open('/documents');
  await settled();
  await user.dblClick(await screen.findByRole('row', { name: /Odabir/ }));
  await screen.findByRole('row', { name: /Jedan/ });
  await settled();
  const table = screen.getByRole('table');
  const chosen = async (name: RegExp) => {
    await user.keyboard('{Control>}');
    await user.click(within(table).getByRole('row', { name }));
    await user.keyboard('{/Control}');
  };
  expect(within(table).queryByRole('checkbox', { name: 'Odaberi sve' })).toBeNull();
  await chosen(/Jedan/);
  await chosen(/Dva/);
  await screen.findByText('Odabrano: 2');
  expect(screen.getByRole('button', { name: 'Premjesti u smeće' })).toHaveProperty(
    'disabled',
    false,
  );
  expect(screen.getByRole('checkbox', { name: 'Odaberi sve' })).toHaveProperty('checked', true);
  await user.click(screen.getByRole('button', { name: 'Odabir' }));
  await user.click(await screen.findByRole('menuitem', { name: 'Poništi odabir' }));
  await chosen(/Jedan/);
  await user.click(screen.getByRole('button', { name: 'Odabir' }));
  await user.click(await screen.findByRole('menuitem', { name: 'Obrni odabir' }));
  await waitFor(() =>
    expect(within(table).getByRole('row', { name: /Dva/ }).getAttribute('aria-selected')).toBe(
      'true',
    ),
  );
  expect(within(table).getByRole('row', { name: /Jedan/ }).getAttribute('aria-selected')).toBe(
    'false',
  );
  await user.click(screen.getByRole('checkbox', { name: 'Odaberi sve' }));
  await screen.findByText('Odabrano: 2');
  await user.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByText('Odabrano: 2')).toBeNull());
  expect(within(table).queryByRole('checkbox', { name: 'Odaberi sve' })).toBeNull();
});

test('notes are chosen together and go to the trash in one move', async () => {
  const notes = ['Mlijeko', 'Kruh'].map((title) => node(title, { kind: 'document', excerpt: '' }));
  serve({
    ...tree(notes),
    'GET /api/notes': () => ({
      folder: null,
      notes: notes.filter((each) => !each.trashed_at),
    }),
  });
  const { user, router, settled } = open('/notes');
  await settled();
  const card = (name: string) => item('Bilješke', name);
  await user.keyboard('{Control>}');
  await user.click(within(card('Mlijeko')!).getByRole('link'));
  await user.keyboard('{/Control}');
  expect(router.state.location.pathname).toBe('/notes');
  await user.click(within(card('Kruh')!).getByRole('link'));
  await screen.findByText('Odabrano: 2');
  await user.click(screen.getByRole('button', { name: 'Premjesti u smeće' }));
  await waitFor(() => expect(card('Mlijeko')).toBeUndefined());
  expect(card('Kruh')).toBeUndefined();
});

test('contacts chosen together are written to or deleted at once', async () => {
  const people = [
    { id: 1, name: 'Vesna Horvat', email: 'vesna@example.com' },
    { id: 2, name: 'Zoran Horvat', email: 'zoran@example.com' },
  ].map((each) => ({
    ...each,
    organisation: '',
    title: '',
    phone: '',
    photo: null,
    colleague: false,
    starred: false,
    avatar: null,
  }));
  serve({
    'GET /api/contacts': () => ({ contacts: people, failed: [], directories: [] }),
    'POST /api/contacts/delete': async (request) => {
      const gone = (await request.json()).contacts as number[];
      people.splice(0, people.length, ...people.filter((each) => !gone.includes(each.id)));
    },
  });
  const { user, settled } = open('/contacts?q=Horvat');
  await settled();
  const row = (name: string) =>
    screen.queryAllByRole('listitem').find((each) => each.textContent?.includes(name));
  await user.keyboard('{Control>}');
  await user.click(within(row('Vesna')!).getByRole('link'));
  await user.keyboard('{/Control}');
  await user.click(within(row('Zoran')!).getByRole('link'));
  await screen.findByText('Odabrano: 2');
  expect(screen.getByRole('link', { name: 'Napiši poruku' }).getAttribute('href')).toMatch(
    /to=vesna%40example.com.*to=zoran%40example.com/,
  );
  await user.click(screen.getByRole('button', { name: 'Izbriši odabrane' }));
  await user.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', {
      name: 'Izbriši odabrane',
    }),
  );
  await waitFor(() => expect(row('Vesna')).toBeUndefined());
  expect(row('Zoran')).toBeUndefined();
});
