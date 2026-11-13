// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

test('an administrator keeps the rooms and resources from the settings', async () => {
  const kept: {
    id: number;
    name: string;
    kind: string;
    capacity: number | null;
    place: string;
    active: boolean;
  }[] = [];
  let next = 1;
  serve({
    'GET /api/nodes/recent': () => ({ items: [] }),
    'GET /api/mail/waiting': () => ({ messages: [] }),
    'GET /api/calendar': () => ({
      calendars: [],
      next_color: 0,
      unfollowed: [],
      failed: [],
      zone: 'Europe/Zagreb',
    }),
    'GET /api/calendar/days-off': () => ({ days_off: [] }),
    'GET /api/tasks': () => ({ tasks: [] }),
    'GET /api/passkeys': () => ({ passkeys: [] }),
    'GET /api/calendar/resources': () => ({ resources: kept }),
    'POST /api/calendar/resources': async (request) => {
      const made = { id: next++, ...(await request.json()) };
      kept.push(made);
      return made;
    },
    'PATCH /api/calendar/resources/:id': async (request, { id }) => {
      const at = kept.findIndex((each) => each.id === Number(id));
      kept[at] = { ...kept[at], ...(await request.json()) };
      return kept[at];
    },
    'DELETE /api/calendar/resources/:id': (_, { id }) => {
      kept.splice(
        kept.findIndex((each) => each.id === Number(id)),
        1,
      );
    },
  });
  const { user, router, settled } = open('/', { is_admin: true });
  await settled();
  await user.click(screen.getByRole('button', { name: /^Račun / }));
  await user.click(await screen.findByRole('menuitem', { name: 'Postavke' }));
  await user.click(
    within(await screen.findByRole('navigation', { name: 'Postavke' })).getByRole('link', {
      name: 'Sobe i resursi',
    }),
  );
  await waitFor(() => expect(router.state.location.pathname).toMatch(/\/resources$/));
  await screen.findByText('Još nema nijedne sobe ni resursa.');

  await user.click(screen.getByRole('button', { name: 'Novi resurs' }));
  const dialog = screen.getByRole('dialog', { name: 'Novi resurs' });
  await user.type(within(dialog).getByLabelText('Naziv'), 'Mala soba');
  await user.selectOptions(within(dialog).getByLabelText('Vrsta'), 'Soba');
  await user.type(within(dialog).getByLabelText('Kapacitet'), '4');
  await user.type(within(dialog).getByLabelText('Gdje'), '1. kat');
  await user.click(within(dialog).getByRole('button', { name: 'Izradi' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Novi resurs' })).toBeNull());
  const row = () => screen.getByRole('row', { name: /Mala soba/ });
  await screen.findByRole('row', { name: /Mala soba/ });
  expect(row().textContent).toContain('Soba');
  expect(row().textContent).toContain('1. kat');

  await user.click(screen.getByRole('button', { name: 'Uredi resurs: Mala soba' }));
  const edit = screen.getByRole('dialog', { name: 'Uredi resurs' });
  await user.click(within(edit).getByLabelText('U uporabi'));
  await user.click(within(edit).getByRole('button', { name: 'Spremi' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Uredi resurs' })).toBeNull());
  await waitFor(() => expect(row().textContent).toContain('izvan uporabe'));

  await user.click(screen.getByRole('button', { name: 'Obriši: Mala soba' }));
  await user.click(
    within(await screen.findByRole('alertdialog', { name: 'Obrisati resurs?' })).getByRole(
      'button',
      { name: 'Obriši' },
    ),
  );
  await screen.findByText('Još nema nijedne sobe ni resursa.');
});
