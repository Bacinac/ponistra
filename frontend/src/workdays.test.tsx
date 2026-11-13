// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

type Closure = { id: number; first: string; last: string; name: string };

test('an administrator chooses the country and keeps the company days off', async () => {
  const state = {
    country: 'HR',
    subdivision: '',
    opens: '08:00',
    closes: '16:00',
    countries: {
      HR: [],
      DE: [
        ['BY', 'Bayern'],
        ['SN', 'Sachsen'],
      ],
    },
    holidays: [{ date: '2027-05-27', hr: 'Tijelovo', en: 'Corpus Christi' }],
    closures: [] as Closure[],
  };
  const chosen: unknown[] = [];
  let next = 1;
  let read = '';
  serve({
    'GET /api/calendar/workdays': () => state,
    'PATCH /api/calendar/workdays': async (request) => {
      const body = await request.json();
      chosen.push(body);
      Object.assign(state, body);
      return state;
    },
    'POST /api/calendar/closures': async (request) => {
      const { closures } = await request.json();
      const made = closures.map((each: Omit<Closure, 'id'>) => ({ id: next++, ...each }));
      state.closures.push(...made);
      return { closures: made };
    },
    'POST /api/calendar/closures/read': async (request) => {
      read = (await request.json()).ics;
      return {
        closures: [
          { first: '2027-08-02', last: '2027-08-13', name: 'Kolektivni godišnji' },
          { first: '2027-02-14', last: '2027-02-14', name: 'Valentinovo' },
        ],
      };
    },
    'DELETE /api/calendar/closures/:id': (_, { id }) => {
      state.closures.splice(
        state.closures.findIndex((each) => each.id === Number(id)),
        1,
      );
    },
  });
  const { user } = open('/workdays', { is_admin: true });

  const country = await screen.findByLabelText('Država');
  expect(country).toHaveProperty('value', 'HR');
  expect(screen.queryByLabelText('Regija')).toBeNull();
  await screen.findByText('Tijelovo');
  screen.getByText('Još nema nijednog neradnog dana tvrtke.');

  await user.selectOptions(country, 'Njemačka');
  const region = await screen.findByLabelText('Regija');
  expect(region).toHaveProperty('value', '');
  await user.selectOptions(region, 'Bayern');
  await waitFor(() => expect(region).toHaveProperty('value', 'BY'));
  expect(chosen).toEqual([
    { country: 'DE', subdivision: '' },
    { country: 'DE', subdivision: 'BY' },
  ]);

  const hours = screen.getByRole('heading', { name: 'Radno vrijeme' }).parentElement!;
  const opens = within(hours).getByLabelText('Od');
  expect(opens).toHaveProperty('value', '08:00');
  await user.clear(opens);
  await user.type(opens, '07:30');
  await user.tab();
  await waitFor(() => expect(chosen).toContainEqual({ opens: '07:30', closes: '16:00' }));
  expect(chosen).toHaveLength(3);

  await user.click(screen.getByRole('button', { name: 'Novi neradni dan' }));
  const dialog = screen.getByRole('dialog', { name: 'Novi neradni dan' });
  await user.type(within(dialog).getByLabelText('Naziv'), 'Dan između');
  await user.type(within(dialog).getByLabelText('Od'), '2027-05-28');
  expect(within(dialog).getByLabelText('Do')).toHaveProperty('value', '2027-05-28');
  await user.click(within(dialog).getByRole('button', { name: 'Izradi' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect((await screen.findByRole('row', { name: /Dan između/ })).textContent).toContain('2027');

  await user.click(screen.getByRole('button', { name: 'Radnje' }));
  await user.click(await screen.findByRole('menuitem', { name: 'Uvezi iz kalendara (.ics)…' }));
  const picker = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  await user.upload(
    picker,
    new File(['BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n'], 'neradni.ics', { type: 'text/calendar' }),
  );
  const reading = await screen.findByRole('dialog', { name: 'Uvezi iz kalendara (.ics)…' });
  await user.click(within(reading).getByRole('checkbox', { name: /Valentinovo/ }));
  await user.click(within(reading).getByRole('button', { name: 'Dodaj odabrane (1)' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(read).toContain('BEGIN:VCALENDAR');
  await screen.findByRole('row', { name: /Kolektivni godišnji/ });
  expect(screen.queryByRole('row', { name: /Valentinovo/ })).toBeNull();

  await user.click(screen.getByRole('button', { name: 'Obriši: Dan između' }));
  const asked = await screen.findByRole('alertdialog', { name: 'Obrisati neradni dan?' });
  await user.click(within(asked).getByRole('button', { name: 'Obriši' }));
  await waitFor(() => expect(screen.queryByRole('row', { name: /Dan između/ })).toBeNull());
});
