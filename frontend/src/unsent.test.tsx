// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

const ACCOUNT = {
  id: 1,
  address: 'ja@example.com',
  name: 'Ja',
  label: '',
  signature: '',
  own_signature: false,
  username: 'ja@example.com',
  login: 'password',
  protocol: 'imap',
  activesync: { host: '' },
  imap: { host: 'mox', port: 1143, security: 'none' },
  smtp: { host: 'mox', port: 1587, security: 'none' },
  color: 0,
  default: true,
  together: true,
  unseen: 0,
  state: 'ready',
  error: '',
  synced_at: null,
  older: false,
};

/** One account with its Drafts folder, and the server keeping what the composer leaves unsent. */
function mailbox(waiting = new Map<number, Record<string, unknown>>()) {
  const kept = new Map<number, object>();
  serve({
    'GET /api/mail/accounts': () => ({
      mailboxes: [],
      role: null,
      accounts: [ACCOUNT],
      signature: '',
      folders: [
        { id: 7, name: 'drafts', role: 'drafts', parent: null, account: null, unseen: 0, count: 0 },
        { id: 8, name: 'inbox', role: 'inbox', parent: null, account: null, unseen: 0, count: 0 },
      ],
      images: [],
      rules: [],
      plain: [],
      app_passwords: {},
      providers: {},
    }),
    'GET /api/mail/folders/:id/messages': () => ({
      messages: [],
      before: null,
      count: 0,
      unseen: 0,
    }),
    'GET /api/translation': () => ({ languages: null, automatic: false, known: ['hr', 'en'] }),
    'GET /api/mail/sender': () => ({ account: null }),
    'GET /api/mail/drafts': () => ({ drafts: [] }),
    'GET /api/mail/unsent': () => ({ unsent: [...kept.values()].reverse() }),
    'GET /api/mail/later': () => ({ later: [...waiting.values()] }),
    'POST /api/mail/later': async (request) => {
      const given = await request.json();
      const made = {
        ...given,
        id: 90 + waiting.size,
        send_at: given.at,
        sending: false,
        failed: '',
        updated_at: new Date().toISOString(),
      };
      waiting.set(made.id, made);
      return made;
    },
    'PATCH /api/mail/later/:id': async (request, { id }) => {
      const { at } = await request.json();
      const moved = { ...waiting.get(Number(id)), send_at: at, failed: '' };
      if (at) waiting.set(Number(id), moved);
      else waiting.delete(Number(id));
      return moved;
    },
    'POST /api/mail/unsent': async (request) => {
      const made = {
        ...(await request.json()),
        id: kept.size + 1,
        updated_at: new Date().toISOString(),
      };
      kept.set(made.id, made);
      return made;
    },
    'PUT /api/mail/unsent/:id': async (request, { id }) => {
      const changed = {
        ...(await request.json()),
        id: Number(id),
        updated_at: new Date().toISOString(),
      };
      kept.set(Number(id), changed);
      return changed;
    },
    'DELETE /api/mail/unsent/:id': (_, { id }) => {
      kept.delete(Number(id));
    },
  });
  return kept;
}

test('a message begun is kept in the drafts, goes on as it was left and is discarded there', async () => {
  const kept = mailbox();
  const { user, router } = open('/mail?compose');
  const message = await screen.findByRole('dialog', { name: 'Nova poruka' });
  const subject = within(message).getByLabelText('Predmet');
  await user.type(subject, 'Ponuda za Končar');
  await within(message).findByText('Spremljeno u skice');
  await user.type(subject, ', druga');
  await user.click(within(message).getByRole('button', { name: 'Zatvori' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  await waitFor(() =>
    expect([...kept.values()]).toEqual([
      expect.objectContaining({ account: 1, subject: 'Ponuda za Končar, druga' }),
    ]),
  );

  await router.navigate('/mail/7');
  const unsent = await screen.findByRole('region', { name: 'Nedovršene poruke' });
  await user.click(await within(unsent).findByRole('button', { name: /Ponuda za Končar, druga/ }));
  const again = await screen.findByRole('dialog', { name: 'Nova poruka' });
  expect(within(again).getByLabelText('Predmet')).toHaveProperty(
    'value',
    'Ponuda za Končar, druga',
  );
  await user.click(within(again).getByRole('button', { name: 'Odbaci' }));
  const asked = await screen.findByRole('alertdialog', { name: 'Odbaciti poruku?' });
  await user.click(within(asked).getByRole('button', { name: 'Odbaci' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  await waitFor(() =>
    expect(screen.queryByRole('region', { name: 'Nedovršene poruke' })).toBeNull(),
  );
  expect(kept.size).toBe(0);
});

test('a mail link opens a message to its people with its copies, subject and text, kept from the start', async () => {
  const kept = mailbox();
  const link =
    'mailto:ana@example.com?cc=Iva%20Horvat%20%3Civa@example.com%3E&bcc=uprava@example.com' +
    '&subject=Ponuda%207&body=Dobar%20dan%2C%0D%0Ahvala';
  const { router } = open(`/mail?${new URLSearchParams({ mailto: link })}`);
  const message = await screen.findByRole('dialog', { name: 'Nova poruka' });
  within(message).getByTitle('ana@example.com');
  within(message).getByTitle('Iva Horvat <iva@example.com>');
  within(message).getByTitle('uprava@example.com');
  expect(within(message).getByLabelText('Predmet')).toHaveProperty('value', 'Ponuda 7');
  const text = within(message).getByLabelText('Poruka');
  expect([...text.querySelectorAll('p')].map((each) => each.textContent)).toEqual([
    'Dobar dan,',
    'hvala',
  ]);
  await waitFor(() => expect(router.state.location.search).toBe(''));
  await within(message).findByText('Spremljeno u skice');
  expect([...kept.values()]).toEqual([
    expect.objectContaining({
      subject: 'Ponuda 7',
      cc: [expect.objectContaining({ address: 'iva@example.com' })],
      bcc: [expect.objectContaining({ address: 'uprava@example.com' })],
    }),
  ]);
});

test('a message opened and closed untouched is not kept', async () => {
  const kept = mailbox();
  const { user } = open('/mail?compose');
  const message = await screen.findByRole('dialog', { name: 'Nova poruka' });
  await within(message).findByLabelText('Predmet');
  await user.click(within(message).getByRole('button', { name: 'Zatvori' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(kept.size).toBe(0);
});

test('a message set to leave later goes to the server with its moment and waits in its own place', async () => {
  const waiting = new Map<number, Record<string, unknown>>();
  mailbox(waiting);
  const { user, router } = open('/mail/8?compose');
  const message = await screen.findByRole('dialog', { name: 'Nova poruka' });
  await user.type(within(message).getByLabelText('Predmet'), 'Ponuda kasnije');
  await user.type(within(message).getByLabelText('Za'), 'ana@example.com,');
  await user.click(within(message).getByRole('button', { name: 'Pošalji kasnije' }));
  const asked = await screen.findByRole('dialog', { name: 'Kada poslati poruku?' });
  await user.click(within(asked).getByRole('button', { name: /Sutra ujutro/ }));
  await waitFor(() => expect(waiting.size).toBe(1));
  const [made] = [...waiting.values()];
  expect(new Date(String(made.at)).getTime()).toBeGreaterThan(Date.now());
  expect(made).toEqual(expect.objectContaining({ subject: 'Ponuda kasnije', account: 1 }));

  made.failed = 'smtp_unreachable';
  await router.navigate('/mail/later');
  const list = await screen.findByRole('list', { name: 'Za slanje' });
  await within(list).findByText('Ponuda kasnije');
  within(list).getByText(/Odlazni poslužitelj/);
});
