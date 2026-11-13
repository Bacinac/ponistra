// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

const ivo = { id: 1, name: 'Ivo Bošković', email: 'ivo@example.com' };
const ana = { id: 2, name: 'Ana Horvat', email: 'ana@example.com' };

test('an administrator sets a rule of retention, places a person on hold and releases them', async () => {
  const sent: { method: string; path: string; body: unknown }[] = [];
  const rules = [
    {
      id: 1,
      what: 'documents',
      folder: { id: 'f1', title: 'Ugovori' },
      keep_days: 3650,
      remove_days: null,
    },
  ];
  const holds = [
    {
      id: 4,
      name: 'Spor 14/2026',
      person: ana,
      folder: null,
      created_by: ivo,
      created_at: '2026-11-10T16:00:00Z',
    },
  ];
  const removals = [{ at: '2026-11-10T03:00:00Z', documents: 2, files: 0, mail: 1250, chat: 4 }];
  serve({
    'GET /api/users': () => ({ users: [ivo, ana], groups: [] }),
    'GET /api/retention/rules': () => ({ rules, removals }),
    'GET /api/retention/holds': () => ({ holds }),
    'POST /api/retention/rules': async (request) => {
      const body = await request.json();
      sent.push({ method: 'POST', path: 'rules', body });
      return { id: 2, folder: null, ...body };
    },
    'POST /api/retention/holds': async (request) => {
      const body = await request.json();
      sent.push({ method: 'POST', path: 'holds', body });
      return { id: 5, ...body };
    },
    'DELETE /api/retention/holds/4': () => {
      sent.push({ method: 'DELETE', path: 'holds/4', body: null });
      return null;
    },
  });
  const { user } = open('/retention', { is_admin: true });

  const [ruled, held, removed] = await screen.findAllByRole('table');
  expect(
    within(ruled)
      .getAllByRole('cell')
      .map((cell) => cell.textContent),
  ).toEqual(['Dokumenti', 'Ugovori', '3.650', '–', '']);
  expect(within(held).getByText('Ana Horvat')).toBeTruthy();
  expect(within(removed).getByText('1.250')).toBeTruthy();

  await user.click(screen.getByRole('button', { name: 'Novo pravilo' }));
  const dialog = await screen.findByRole('dialog');
  await user.selectOptions(within(dialog).getByLabelText('Vrsta'), 'mail');
  await user.type(within(dialog).getByLabelText('Čuva se najmanje (dana)'), '30');
  await user.type(within(dialog).getByLabelText('Briše se nakon (dana)'), '3650');
  await user.click(within(dialog).getByRole('button', { name: 'Izradi' }));
  await waitFor(() => expect(sent).toHaveLength(1));
  expect(sent[0].body).toEqual({ what: 'mail', folder: null, keep_days: 30, remove_days: 3650 });

  await user.click(screen.getByRole('button', { name: 'Novo zakonsko čuvanje' }));
  const holding = await screen.findByRole('dialog');
  const placing = within(holding).getByRole('button', { name: 'Stavi pod čuvanje' });
  await user.type(within(holding).getByLabelText('Predmet'), 'Revizija');
  expect((placing as HTMLButtonElement).disabled).toBe(true);
  await user.selectOptions(within(holding).getByLabelText('Osoba'), String(ivo.id));
  await user.click(placing);
  await waitFor(() => expect(sent).toHaveLength(2));
  expect(sent[1].body).toEqual({ name: 'Revizija', person: ivo.id });

  await user.click(screen.getByRole('button', { name: 'Otpusti: Spor 14/2026' }));
  await user.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Otpusti' }),
  );
  await waitFor(() => expect(sent).toHaveLength(3));
});
