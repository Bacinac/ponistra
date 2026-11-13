// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

const ivo = { id: 1, name: 'Ivo Bošković', email: 'ivo@example.com' };
const ana = { id: 2, name: 'Ana Horvat', email: 'ana@example.com' };

function entry(id: number, kind: string, fields: object = {}) {
  return {
    id,
    at: '2026-11-10T16:00:00Z',
    kind,
    actor: null,
    subject: null,
    address: null,
    detail: {},
    ...fields,
  };
}

test('an administrator reads the journal newest first, older pages on asking, narrowed by kind and person', async () => {
  const asked: string[] = [];
  serve({
    'GET /api/users': () => ({ users: [ivo, ana], groups: [] }),
    'GET /api/journal': (request) => {
      const query = new URL(request.url).searchParams;
      asked.push(query.toString());
      if (query.get('before') === '5')
        return { entries: [entry(4, 'installed', { actor: ivo, subject: ivo })], next: null };
      return {
        entries: [
          entry(9, 'signed_in', {
            actor: ana,
            address: '198.51.100.7',
            detail: { way: 'passkey', agent: 'Firefox' },
          }),
          entry(8, 'sign_in_failed', {
            subject: ana,
            address: '203.0.113.4',
            detail: { email: 'ana@example.com' },
          }),
          entry(7, 'user_changed', {
            actor: ivo,
            subject: ana,
            detail: { changed: ['name', 'admin'], admin: true, active: true },
          }),
          entry(6, 'setting_changed', {
            actor: ivo,
            detail: { setting: 'resource', change: 'added', name: 'Dvorana' },
          }),
          entry(5, 'problem', { detail: { problem: 'queue:text' } }),
        ],
        next: 5,
      };
    },
  });
  const { user } = open('/journal', { is_admin: true });

  await screen.findByText('198.51.100.7');
  const table = screen.getByRole('table');
  const rows = () =>
    within(table)
      .getAllByRole('row')
      .slice(1)
      .map((row) =>
        within(row)
          .getAllByRole('cell')
          .slice(1)
          .map((cell) => cell.textContent),
      );
  expect(rows()).toEqual([
    ['Ana Horvat', 'Prijava: pristupnim ključem', '198.51.100.7'],
    ['–', 'Neuspjela prijava: ana@example.com', '203.0.113.4'],
    ['Ivo Bošković', 'Promijenjen korisnik: Ana Horvat: ime, administrator: da', ''],
    ['Ivo Bošković', 'Promijenjena postavka: prostorije i resursi, dodano, Dvorana', ''],
    ['Ponistra', 'Problem: Čitanje teksta datoteka: stoji više od sat vremena', ''],
  ]);
  await user.click(screen.getByRole('button', { name: 'Starije' }));
  await waitFor(() => expect(rows()).toHaveLength(6));
  expect(rows()[5]).toEqual(['Ivo Bošković', 'Instalacija postavljena', '']);
  expect(screen.queryByRole('button', { name: 'Starije' })).toBeNull();

  await user.selectOptions(screen.getByLabelText('Vrsta'), 'Prijave');
  await user.selectOptions(screen.getByLabelText('Osoba'), 'Ana Horvat');
  await waitFor(() => expect(asked).toContain('group=sign_ins&user=2'));
});
