// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { open, serve } from './testing';
import { chooseTheme } from './theme';

/** A microphone that hears nothing, as Chromium's fake device gives a tone; the dialog shows a
 * second passing and sends what it recorded once the user is done. */
class Recorder {
  static isTypeSupported = (kind: string) => kind.startsWith('audio/webm');
  state = 'inactive';
  mimeType = 'audio/webm;codecs=opus';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['tone'], { type: this.mimeType }) });
    this.onstop?.();
  }
}

beforeEach(() => {
  localStorage.clear();
  chooseTheme('system');
  Object.assign(globalThis, {
    MediaRecorder: Recorder,
    AudioContext: class {
      createAnalyser = () => ({ fftSize: 0, getByteTimeDomainData() {}, connect() {} });
      createMediaStreamSource = () => ({ connect() {} });
      close = async () => {};
    },
  });
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) },
  });
});

type Said = { text: string; reading?: object | null };
type Handlers = Parameters<typeof serve>[0];

/** The installation writes speech as `said.text` and the user has agreed to it; what the model
 * reads of it is `said.reading`. Both may change between one thing said and the next. */
function speech(said: Said, handlers: Handlers = {}) {
  serve({
    'GET /api/calendar': () => ({
      calendars: [],
      next_color: 0,
      unfollowed: [],
      failed: [],
      zone: 'Europe/Zagreb',
    }),
    'GET /api/links': () => ({ folder: null, groups: [], links: [] }),
    'GET /api/calendar/resources': () => ({ resources: [] }),
    'GET /api/calendar/days-off': () => ({ days_off: [] }),
    'GET /api/tasks': () => ({ tasks: [] }),
    'GET /api/search': () => ({
      filters: [],
      documents: [],
      mail: [],
      conversations: [],
      events: [],
      tasks: [],
      people: [],
      versions: [],
      help: [],
    }),
    'GET /api/translation': () => ({ languages: null, automatic: false, known: ['hr', 'en'] }),
    'GET /api/speech/consent': () => ({
      enabled: true,
      understands: said.reading !== undefined,
      given_at: '2026-11-01T10:00:00Z',
    }),
    'POST /api/speech': () => Response.json({ text: said.text }),
    'POST /api/speech/understand': () => Response.json(said.reading),
    ...handlers,
  });
}

async function say(user: ReturnType<typeof open>['user']) {
  await user.click(await screen.findByRole('button', { name: 'Izgovorite naredbu ili bilješku' }));
  const recording = await screen.findByRole('dialog', { name: 'Govorite' });
  await within(recording).findByText('Slušam');
  await within(recording).findByText(/^0:(0[1-9]|[1-5]\d)$/);
  await user.click(within(recording).getByRole('button', { name: 'Gotovo' }));
}

test('words of commands are offered beside the note', async () => {
  speech(
    { text: 'tamna' },
    {
      'PATCH /api/auth/preferences': async (request: Request) => ({
        user: { id: 1, email: 'ja@example.com', name: 'Ja', ...(await request.json()) },
      }),
    },
  );
  const { user, settled } = open('/documents');
  await settled();
  await say(user);
  const heard = await screen.findByRole('dialog', { name: 'Izgovoreno' });
  await user.click(
    within(within(heard).getByRole('list', { name: 'Naredbe' })).getByRole('button', {
      name: 'Tema: Tamna',
    }),
  );
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Izgovoreno' })).toBeNull());
  await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
});

test('the microphone says why it is off while the installation writes no speech', async () => {
  serve({
    'GET /api/speech/consent': () => ({ enabled: false, given_at: null }),
  });
  const { settled } = open('/documents');
  await settled();
  const microphone = screen.getByRole('button', { name: 'Izgovorite naredbu ili bilješku' });
  expect(microphone).toHaveProperty('disabled', true);
  expect(microphone.getAttribute('title')).toBe('Govor u tekst nije uključen');
});

const calendar = {
  id: 7,
  name: 'Posao',
  color: 3,
  kind: 'own',
  read_only: false,
  account: null,
};

test('what the model reads as an event opens in the event dialog to be saved', async () => {
  const saved: { summary: string; location: string }[] = [];
  speech(
    {
      text: 'sastanak s Anom sutra u deset u uredu',
      reading: {
        intent: 'event',
        summary: 'Sastanak s Anom',
        day: '2026-11-03',
        time: '10:00',
        location: 'Ured',
      },
    },
    {
      'GET /api/calendar': () => ({
        calendars: [calendar],
        next_color: 4,
        unfollowed: [],
        failed: [],
        zone: 'Europe/Zagreb',
      }),
      'POST /api/calendar/events': async (request) => {
        saved.push(await request.json());
        return { id: 1 };
      },
    },
  );
  const { user, router, settled } = open('/documents');
  await settled();
  await say(user);
  const heard = await screen.findByRole('dialog', { name: 'Izgovoreno' });
  const proposed = await within(heard).findByRole('region', { name: 'Prijedlog' });
  expect(proposed.textContent).toContain('Sastanak s Anom');
  expect(proposed.textContent).toContain('10:00');
  await user.click(within(heard).getByRole('button', { name: 'Dodaj u kalendar…' }));

  const event = await screen.findByRole('dialog', { name: 'Novi događaj' });
  expect(within(event).getByLabelText('Naziv')).toHaveProperty('value', 'Sastanak s Anom');
  expect(within(event).getByLabelText('Mjesto')).toHaveProperty('value', 'Ured');
  await user.click(within(event).getByRole('button', { name: 'Spremi' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Novi događaj' })).toBeNull());
  expect(saved).toEqual([
    expect.objectContaining({ summary: 'Sastanak s Anom', location: 'Ured' }),
  ]);
  expect(router.state.location.pathname).toBe('/documents');
});

test('what the model reads as a task opens in the task dialog', async () => {
  speech({
    text: 'podsjeti me da nazovem servis',
    reading: { intent: 'task', text: 'Nazvati servis', due: '2026-11-06' },
  });
  const { user, settled } = open('/documents');
  await settled();
  await say(user);
  const heard = await screen.findByRole('dialog', { name: 'Izgovoreno' });
  await user.click(await within(heard).findByRole('button', { name: 'Dodaj zadatak…' }));
  const task = await screen.findByRole('dialog', { name: 'Novi zadatak' });
  expect(within(task).getByLabelText('Što')).toHaveProperty('value', 'Nazvati servis');
});

test('a part of the suite is opened by its command, or by what the model reads', async () => {
  const said: Said = { text: 'Otvori kalendar.', reading: null };
  speech(said);
  const { user, router, settled } = open('/documents');
  await settled();
  await say(user);
  await waitFor(() => expect(router.state.location.pathname).toBe('/calendar'));
  await settled();

  Object.assign(said, { text: 'pokaži mi poštu', reading: { intent: 'open', place: 'mail' } });
  await say(user);
  await waitFor(() => expect(router.state.location.pathname).toBe('/mail'));
  await settled();
});

test('what the model reads as a search opens the search with its filters', async () => {
  speech({
    text: 'odgovori Evi na mail',
    reading: { intent: 'search', text: '', kind: 'mail', from: 'Eva' },
  });
  const { user, router, settled } = open('/documents');
  await settled();
  await say(user);
  await waitFor(() => expect(router.state.location.pathname).toBe('/search'));
  expect(new URLSearchParams(router.state.location.search).get('q')).toBe('vrsta:pošta od:Eva');
  await settled();
});

test('a person asked about opens among the contacts, or is chosen among those like them', async () => {
  const said: Said = {
    text: 'kad je rođendan Dino Vrančec',
    reading: {
      intent: 'person',
      name: 'Dino Vrančec',
      people: [{ id: 11, name: 'Dino Vrančić' }],
    },
  };
  const people: Record<string, string> = {
    11: 'Dino Vrančić',
    12: 'Ana Kovač',
    13: 'Ana Horvat',
  };
  const contact = (id: string) => ({
    id: Number(id),
    name: people[id],
    organisation: '',
    title: '',
    email: '',
    phone: '',
    photo: null,
    colleague: false,
    starred: false,
  });
  speech(said, {
    'GET /api/contacts': () => ({
      contacts: Object.keys(people).map((id) => ({ ...contact(id), avatar: null })),
      failed: [],
      directories: [],
    }),
    'GET /api/contacts/:id': (_, { id }) => ({
      ...contact(id),
      fields: { name: people[id] },
      points: [],
      directory: null,
      sources: [],
      changed_at: '2026-11-01T10:00:00Z',
    }),
  });
  const { user, router, settled } = open('/documents');
  await settled();
  await say(user);
  await waitFor(() => expect(router.state.location.pathname).toBe('/contacts/11'));
  await settled();

  Object.assign(said, {
    text: 'kad je rođendan Ani',
    reading: {
      intent: 'person',
      name: 'Ana',
      people: [
        { id: 12, name: 'Ana Kovač' },
        { id: 13, name: 'Ana Horvat' },
      ],
    },
  });
  await router.navigate('/documents');
  await settled();
  await say(user);
  const heard = await screen.findByRole('dialog', { name: 'Izgovoreno' });
  await user.click(await within(heard).findByRole('button', { name: 'Ana Horvat' }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/contacts/13'));
  await settled();

  Object.assign(said, {
    text: 'kad je rođendan Marku',
    reading: { intent: 'person', name: 'Marko', people: [] },
  });
  await router.navigate('/documents');
  await settled();
  await say(user);
  await within(await screen.findByRole('dialog', { name: 'Izgovoreno' })).findByText(
    'Među kontaktima nema osobe Marko.',
  );
});

test('a question about Ponistra offers the articles of its help that answer it', async () => {
  const said: Said = {
    text: 'pretražuješ li pomoć',
    reading: {
      intent: 'help',
      text: 'pomoć',
      articles: [
        { id: 'start/help', title: 'Pomoć' },
        { id: 'start/search', title: 'Pretraga' },
      ],
    },
  };
  speech(said, {
    'GET /api/help': () => ({
      sections: [
        {
          id: 'start',
          title: 'Početak',
          articles: [
            { id: 'start/help', title: 'Pomoć', summary: 'Gdje je pomoć.' },
            { id: 'start/search', title: 'Pretraga', summary: 'Kako tražiti.' },
          ],
        },
      ],
      screens: [],
    }),
    'GET /api/help/start/help': () => ({ id: 'start/help', title: 'Pomoć', html: '<p>Pomoć.</p>' }),
  });
  const { user, router, settled } = open('/documents');
  await settled();
  await say(user);
  const heard = await screen.findByRole('dialog', { name: 'Izgovoreno' });
  await user.click(await within(heard).findByRole('button', { name: 'Pomoć' }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/help/start/help'));
  await settled();

  Object.assign(said, {
    text: 'ima li teleport',
    reading: { intent: 'help', text: 'teleport', articles: [] },
  });
  await router.navigate('/documents');
  await settled();
  await say(user);
  await within(await screen.findByRole('dialog', { name: 'Izgovoreno' })).findByText(
    'U pomoći nema članka o tome.',
  );
});

test('a link said by its name opens its page in a tab, or is chosen among those like it', async () => {
  const link = (id: string, title: string, href: string) => ({ id, kind: 'link', title, href });
  const github = link('a1', 'Github', 'https://github.example/');
  const dcm = link('a2', 'Proxmox DCM', 'https://dcm.example/');
  const backup = link('a3', 'Proxmox Backup Server', 'https://pbs.example/');
  const said: Said = { text: 'Otvori Github.', reading: null };
  speech(said, {
    'GET /api/links': () => ({ folder: null, groups: [], links: [github, dcm, backup] }),
  });
  const tabs: string[] = [];
  vi.spyOn(window, 'open').mockImplementation((url) => {
    tabs.push(String(url));
    return {} as Window;
  });
  const { user, router, settled } = open('/documents');
  await settled();
  await say(user);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(tabs).toEqual(['https://github.example/']);

  Object.assign(said, {
    text: 'otvori Proxmox',
    reading: { intent: 'link', name: 'Proxmox', links: [backup, dcm] },
  });
  await say(user);
  const heard = await screen.findByRole('dialog', { name: 'Izgovoreno' });
  const commands = within(heard).getByRole('list', { name: 'Naredbe' });
  expect(
    within(commands)
      .getAllByRole('button')
      .map((each) => each.textContent),
  ).toEqual(['Otvori: Proxmox Backup Server', 'Otvori: Proxmox DCM']);
  await user.click(within(commands).getByRole('button', { name: 'Otvori: Proxmox DCM' }));
  expect(tabs).toEqual(['https://github.example/', 'https://dcm.example/']);

  Object.assign(said, {
    text: 'otvori Poreznu',
    reading: { intent: 'link', name: 'Porezna', links: [] },
  });
  await say(user);
  await waitFor(() => expect(router.state.location.pathname).toBe('/search'));
  expect(new URLSearchParams(router.state.location.search).get('q')).toBe('Porezna');
  await settled();
});

test('a document said by its name opens to be made under that name', async () => {
  speech({
    text: 'napravi novi dokument Zapisnik',
    reading: { intent: 'document', title: 'Zapisnik sa sastanka' },
  });
  const { user, router, settled } = open('/calendar');
  await settled();
  await say(user);
  const made = await screen.findByRole('dialog', { name: 'Novi dokument' });
  expect(within(made).getByRole('textbox')).toHaveProperty('value', 'Zapisnik sa sastanka');
  expect(router.state.location.pathname).toBe('/documents');
});

test('a message said to someone opens written to them, from the account they are written from', async () => {
  const account = (id: number) => ({
    id,
    address: `ja${id}@example.com`,
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
    default: id === 1,
    together: true,
    unseen: 0,
    state: 'ready',
    error: '',
    synced_at: null,
    older: false,
  });
  speech(
    {
      text: 'napiši Evi da kasnim',
      reading: {
        intent: 'mail',
        to: ['Eva'],
        subject: 'Kašnjenje',
        text: 'Kasnim deset minuta.',
      },
    },
    {
      'GET /api/mail/people': () => ({
        people: [{ name: 'Eva Kovač', address: 'eva@example.com' }],
        unanswered: [],
      }),
      'GET /api/mail/sender': () => ({ account: 2 }),
      'GET /api/mail/accounts': () => ({
        mailboxes: [],
        role: null,
        accounts: [account(1), account(2)],
        signature: '',
        folders: [],
        images: [],
        rules: [],
        plain: [],
        app_passwords: {},
        providers: {},
      }),
    },
  );
  const { user, settled } = open('/documents');
  await settled();
  await say(user);
  const message = await screen.findByRole('dialog', { name: 'Nova poruka' });
  await within(message).findByText('Eva Kovač');
  expect(within(message).getByLabelText('Predmet')).toHaveProperty('value', 'Kašnjenje');
  await waitFor(() => expect(message.textContent).toContain('Kasnim deset minuta.'));
  await waitFor(() => expect(within(message).getByLabelText('Šalje')).toHaveProperty('value', '2'));
});

test('what is dictated beside a field is written into it, and nothing is run', async () => {
  const understood = vi.fn(() => Response.json(null));
  speech(
    { text: 'tablice i pošta' },
    {
      'POST /api/speech/understand': understood,
      'GET /api/workspace/projects': () => ({
        projects: [
          {
            name: 'alpha',
            path: '/work/alpha',
            gate: null,
            plan: null,
            chats: [
              {
                id: 'fresh',
                title: 'Tablice',
                at: new Date().toISOString(),
                open: false,
                state: 'closed',
                waitingFor: null,
                context: null,
                changes: null,
              },
            ],
            rounds: [],
          },
        ],
        restart: null,
      }),
      'GET /api/workspace/commands': () => ({ commands: [] }),
      'GET /api/memory/waiting': () => ({ count: 0 }),
    },
  );
  const { user } = open('/workspace', { workspace: { url: '/code/', here: true } });
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  await user.click(within(alpha).getByRole('button', { name: 'Novi krug' }));
  const form = screen.getByRole('region', { name: 'Novi krug' });
  await user.type(within(form).getByRole('textbox'), 'nastavi s');
  await user.click(within(form).getByRole('button', { name: 'Izgovorite tekst' }));
  const dialog = await screen.findByRole('dialog');
  await user.click(await within(dialog).findByRole('button', { name: 'Gotovo' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(within(form).getByRole('textbox')).toHaveProperty('value', 'nastavi s tablice i pošta');
  expect(understood).not.toHaveBeenCalled();
});
