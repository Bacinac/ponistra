// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { downloads, open, serve } from './testing';

const health = {
  version: '0.1.99',
  services: { database: true, converter: true, printer: true, ocr: true },
  snapshots: { count: 3, newest: '2026-10-24T01:00:00Z', due: '2026-10-25T01:00:00Z', late: false },
  disks: [{ holds: ['files', 'snapshots'], free: 2e10, total: 5e10 }],
  stored: { database: 1e7, files: 2e7, dead: 3e6 },
  archive: { at: '2026-11-10T16:00:00Z', error: '', late: false },
  queues: { jobs: 0, ocr: 0, text: 0, unread: 0, batches: 0 },
  problems: [],
};

const setting = {
  endpoint: 'https://abc.eu.r2.cloudflarestorage.com',
  bucket: 'ponistra-backup',
  access_key: 'a'.repeat(32),
  hint: 'wxyz',
  lost: false,
  generation: '2026-10-24',
  mirrored_at: '2026-10-24T14:16:13Z',
  protected: false,
  error: '',
  late: false,
};

test('an administrator sets the off-site copy, is told its bucket allows deleting and takes the kit once', async () => {
  let saved = false;
  const sent: unknown[] = [];
  serve({
    'GET /api/health': () => ({
      ...health,
      offsite: { locked: 30, setting: saved ? setting : null },
    }),
    'PATCH /api/backups/offsite': async (request) => {
      sent.push(await request.json());
      if (sent.length === 1)
        return Response.json({ error: 'offsite_unreachable' }, { status: 422 });
      saved = true;
      return {
        kit: { ...setting, secret: 'secret-wxyz', emergency: 'ABCD-EFGH-JKMN-PQRS-TUVW-XYZ2' },
      };
    },
  });
  const files = downloads();
  const { user } = open('/health', { is_admin: true });

  await screen.findByText(/Kopija izvan poslužitelja nije postavljena/);
  await user.click(screen.getByRole('button', { name: 'Postavi…' }));
  const form = screen.getByRole('dialog', { name: 'Kopija izvan poslužitelja' });
  expect(form.textContent).toContain('najmanje 30 dana.');
  await user.type(within(form).getByLabelText('Adresa (S3 API)'), setting.endpoint);
  await user.type(within(form).getByLabelText('Spremnik (bucket)'), setting.bucket);
  await user.type(
    within(form).getByLabelText('Ključ za pristup (Access Key ID)'),
    setting.access_key,
  );
  await user.type(within(form).getByLabelText('Tajni ključ (Secret Access Key)'), 'secret-wxyz');
  await user.click(within(form).getByRole('button', { name: 'Provjeri i spremi' }));
  await within(form).findByText(/Adresa spremnika ne odgovara/);
  await user.click(within(form).getByRole('button', { name: 'Provjeri i spremi' }));

  const kit = await screen.findByRole('dialog', { name: 'Paket za oporavak' });
  expect(kit.textContent).toContain('PONISTRA_EMERGENCY_KEY=ABCD-EFGH-JKMN-PQRS-TUVW-XYZ2');
  await user.click(within(kit).getByRole('button', { name: 'Preuzmi' }));
  expect(files.map(({ name }) => name)).toEqual([expect.stringMatching(/^ponistra-.+-kit\.txt$/)]);
  const text = await files[0].file.text();
  expect(text).toContain(`PONISTRA_OFFSITE_BUCKET=${setting.bucket}\n`);
  expect(text).toContain('PONISTRA_OFFSITE_SECRET=secret-wxyz\n');
  await user.click(within(kit).getByRole('button', { name: 'Zatvori' }));

  await screen.findByText('Spremnik dopušta brisanje', { exact: true });
  screen.getByText(/Spremnik dopušta brisanje, pa kopiju.*najmanje 30 dana\./);
  await waitFor(() => screen.getByRole('button', { name: 'Promijeni…' }));
  expect(sent[1]).toEqual({
    endpoint: setting.endpoint,
    bucket: setting.bucket,
    access_key: setting.access_key,
    secret: 'secret-wxyz',
  });
});

test('the problems the watch raised stand first, each with when it began', async () => {
  serve({
    'GET /api/health': () => ({
      ...health,
      offsite: { locked: 30, setting: null },
      problems: [
        { key: 'queue:text', since: '2026-11-10T08:00:00Z' },
        { key: 'disk:files+snapshots', since: '2026-11-10T09:00:00Z' },
        { key: 'service:converter', since: '2026-11-10T10:00:00Z' },
      ],
    }),
  });
  open('/health', { is_admin: true });

  const problems = (await screen.findByRole('heading', { name: 'Problemi' })).parentElement!;
  expect(
    within(problems)
      .getAllByRole('row')
      .map((row) => row.textContent),
  ).toEqual([
    expect.stringMatching(/^Čitanje teksta datoteka: stoji više od sat vremena/),
    expect.stringMatching(/^Disk s datotekama i sigurnosnim kopijama: manje od 10 % slobodno/),
    expect.stringMatching(/^Pretvaranje datoteka: Ne odgovara/),
  ]);
});
