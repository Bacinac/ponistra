// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { open, serve } from './testing';

function account(id: number, first_name: string, email: string, is_admin = false) {
  return {
    id,
    email,
    first_name,
    last_name: 'Horvat',
    name: `${first_name} Horvat`,
    is_admin,
    is_active: true,
    groups: [],
    last_login: null,
    kept_by: null,
    providers: [],
  };
}

const me = account(1, 'Ja', 'ja@example.com', true);
const ana = account(3, 'Ana', 'ana@example.com');
const marko = account(4, 'Marko', 'marko@example.com');

function company() {
  return {
    'GET /api/company': () => ({ folders: [] }),
    'GET /api/vault/company': () => ({ collections: [] }),
    'GET /api/vault/recovery': () => ({ on: false }),
    'GET /api/policy': () => ({ passkeys: 'nobody', outside: 'everyone' }),
    'GET /api/identity/providers': () => ({ providers: [] }),
  };
}

async function actions(user: ReturnType<typeof open>['user'], name: RegExp, item: string) {
  await user.click(
    within(await screen.findByRole('row', { name })).getByRole('button', { name: 'Radnje' }),
  );
  await user.click(await screen.findByRole('menuitem', { name: item }));
}

test('an administrator erases a user and names who takes over their documents', async () => {
  let users = [me, ana, marko];
  let erased = '';
  serve({
    ...company(),
    'GET /api/users': () => ({ users, groups: [] }),
    'DELETE /api/users/:id': (request, { id }) => {
      erased = `${id}${new URL(request.url).search}`;
      users = users.filter((each) => String(each.id) !== id);
    },
  });
  const { user } = open('/users', { id: 1, is_admin: true });
  await user.click(
    within(await screen.findByRole('row', { name: /Ja Horvat/ })).getByRole('button', {
      name: 'Radnje',
    }),
  );
  expect(await screen.findByRole('menuitem', { name: 'Obriši korisnika' })).toHaveProperty(
    'ariaDisabled',
    'true',
  );
  await user.keyboard('{Escape}');

  await actions(user, /Ana Horvat/, 'Obriši korisnika');
  const dialog = await screen.findByRole('dialog', { name: 'Obrisati korisnika?' });
  const heir = within(dialog).getByLabelText('Dokumente i sandučiće preuzima');
  expect(
    within(heir)
      .getAllByRole('option')
      .map((option) => option.textContent),
  ).toEqual(['Ja Horvat', 'Marko Horvat']);
  expect(heir).toHaveProperty('value', '1');
  await user.selectOptions(heir, 'Marko Horvat');
  await user.click(within(dialog).getByRole('button', { name: 'Obriši korisnika' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(erased).toBe('3?heir=4');
  await waitFor(() => expect(screen.queryByRole('row', { name: /Ana Horvat/ })).toBeNull());
});

test("an administrator saves a user's data as one file", async () => {
  let asked: unknown;
  serve({
    ...company(),
    'GET /api/users': () => ({ users: [me, ana], groups: [] }),
    'POST /api/jobs': async (request) => {
      asked = await request.json();
      return {
        id: 'b1',
        kind: 'personal',
        state: 'done',
        status: null,
        error: null,
        answer: null,
        file: true,
        cancellable: false,
      };
    },
  });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  const { user } = open('/users', { id: 1, is_admin: true });
  await actions(user, /Ana Horvat/, 'Izvezi podatke');
  await waitFor(() => expect(click).toHaveBeenCalled());
  expect(asked).toEqual({ kind: 'personal', user: 3 });
  const saved = click.mock.contexts[0] as HTMLAnchorElement;
  expect([saved.getAttribute('href'), saved.download]).toEqual([
    '/api/jobs/b1/file?download=1',
    'ana@example.com.zip',
  ]);
  click.mockRestore();
});
