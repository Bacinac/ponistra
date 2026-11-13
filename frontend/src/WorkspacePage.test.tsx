// @vitest-environment jsdom
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { expect, onTestFinished, test, vi } from 'vitest';
import { open, serve } from './testing';

const MEMBER = {
  name: null,
  hosted: false,
  waitingFor: null,
  at: null,
  task: null,
  context: null,
  changes: null,
  heard: null,
};

const ROUND = {
  id: 'alpha-20261111-1428',
  created: '2026-11-11T13:28:00Z',
  started: null,
  auto: true,
  asked: null,
  coordinator: {
    ...MEMBER,
    id: 'lead',
    name: 'alpha-45',
    title: 'Plan kruga',
    state: 'idle',
    at: '2026-11-11T13:30:00Z',
  },
  chats: [
    {
      ...MEMBER,
      id: 'one',
      name: 'alpha-de',
      title: 'Kod → Krugovi',
      state: 'working',
      context: 312_400,
      changes: { files: 3, added: 309, removed: 12 },
    },
    {
      ...MEMBER,
      id: 'two',
      name: 'alpha-fd',
      title: 'Grupe u panelu',
      state: 'waiting',
      waitingFor: 'input needed',
    },
    {
      ...MEMBER,
      id: null,
      title: '**Pomoćnici e2e.** Krug alpha-20261111-1428.',
      task: '**Pomoćnici e2e.** Krug alpha-20261111-1428.\nPodručje: e2e/tests/helpers.',
      state: 'new',
    },
  ],
};

const CHAT = {
  context: null,
  changes: null,
  state: 'idle',
  hosted: false,
  waitingFor: null,
  coordinator: null,
};

const GATE = {
  checked: { tree: 'b'.repeat(40), at: '2026-11-11T15:25:00Z' },
  pushed: { commit: 'c'.repeat(40), tree: 'b'.repeat(40), at: '2026-11-11T15:29:00Z' },
  browser: { tree: 'b'.repeat(40), outcome: 'failed', at: '2026-11-11T15:39:00Z', pushed: true },
  night: {
    tree: 'a'.repeat(40),
    outcome: 'passed',
    at: '2026-11-11T02:56:00Z',
    pushed: false,
    failed: null,
  },
  running: [],
};

const IDLE = { sessions: 4, working: [], scripts: [] };

const PROJECTS = {
  projects: [
    { name: null, path: '/work', gate: null, plan: null, chats: [], rounds: [] },
    {
      name: 'alpha',
      path: '/work/alpha',
      gate: GATE,
      plan: { title: 'Plan Alpha', path: '/p/plan' },
      chats: [
        {
          ...CHAT,
          id: 'free',
          title: 'Popravak izvoza',
          at: '2026-11-08T10:00:00Z',
          open: false,
          state: 'closed',
          context: 81_000,
        },
        { ...CHAT, id: 'busy', title: 'Nova tablica', at: '2026-11-08T09:00:00Z', open: true },
      ],
      rounds: [ROUND],
    },
  ],
  restart: IDLE,
};

const OWNER = { workspace: { url: '/code/', here: true } };

const AT = '2026-11-11T13:31:00Z';

const SAID = [
  { role: 'user', text: 'nastavi: tablice', at: AT },
  { role: 'assistant', text: 'Dijelim krug na dva chata.', at: AT },
  { role: 'tool', text: 'Bash git status', at: AT },
  { role: 'tool', text: 'Read docs/SCOPE.md', at: AT },
  { role: 'assistant', text: 'Krug je otvoren.', at: AT },
];

const COMMAND = {
  folder: null,
  round: null,
  session: null,
  text: null,
  images: 0,
  auto: false,
  error: null,
  created_at: AT,
  changed_at: AT,
};

type Asked = Record<string, unknown>;

function served(more: Parameters<typeof serve>[0] = {}) {
  serve({
    'GET /api/workspace/projects': () => PROJECTS,
    'POST /api/workspace/opened': () => ({ ok: true }),
    'GET /api/workspace/commands': () => ({ commands: [] }),
    'GET /api/memory/waiting': () => ({ count: 0 }),
    'POST /api/workspace/commands': async (request) => ({
      ...COMMAND,
      ...((await request.json()) as Asked),
      id: 1,
      state: 'done',
    }),
    'GET /api/workspace/chats/:session': (_request, { session }) => ({
      id: session,
      title: null,
      state: 'idle',
      waitingFor: null,
      said: session === 'lead' ? SAID : [],
    }),
    ...more,
  });
  const opened = vi.fn((): Window | null => ({}) as Window);
  vi.stubGlobal('open', opened);
  return opened;
}

test('a new chat starts in its project with its first message, the editor left closed', async () => {
  const asked: Asked[] = [];
  const opened = served({
    'POST /api/workspace/commands': async (request) => {
      const given = (await request.json()) as Asked;
      asked.push(given);
      return { ...COMMAND, ...given, id: 1, session: 'busy', state: 'done' };
    },
  });
  const { user } = open('/workspace', OWNER);
  const general = await screen.findByRole('region', { name: 'Općenito' });
  const [waiting, first] = screen.getAllByRole('region');
  expect(waiting.getAttribute('aria-label')).toBe('Čeka vas');
  expect(first).toBe(general);
  const alpha = screen.getByRole('region', { name: 'Alpha' });
  await user.click(within(alpha).getByRole('button', { name: 'Novi chat' }));
  const form = screen.getByRole('region', { name: 'Novi chat' });
  within(form).getByRole('heading', { name: 'Novi chat Alpha' });
  const start = within(form).getByRole('button', { name: 'Započni chat' });
  expect(start).toHaveProperty('disabled', true);
  expect(document.activeElement).toBe(
    within(form).getByRole('textbox', { name: 'Prva poruka chatu' }),
  );
  await user.keyboard('catchup');
  await user.click(start);
  await waitFor(() =>
    expect(asked).toEqual([{ kind: 'chat', folder: '/work/alpha', text: 'catchup' }]),
  );
  const chat = screen.getByRole('region', { name: 'Razgovor' });
  await within(chat).findByRole('heading', { name: /Nova tablica/ });
  expect(screen.queryByRole('region', { name: 'Novi chat' })).toBeNull();
  expect(opened).not.toHaveBeenCalled();
});

test('a project shows its chats in use, and the others once it is opened', async () => {
  served();
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  within(alpha).getByRole('button', { name: /Nova tablica/ });
  expect(within(alpha).queryByRole('button', { name: /Popravak izvoza/ })).toBeNull();
  await user.click(within(alpha).getByRole('button', { name: /Alpha/, expanded: false }));
  within(alpha).getByRole('button', { name: /Popravak izvoza/ });
  await user.click(within(alpha).getByRole('button', { name: /Alpha/, expanded: true }));
  expect(within(alpha).queryByRole('button', { name: /Popravak izvoza/ })).toBeNull();
  const general = screen.getByRole('region', { name: 'Općenito' });
  expect(within(general).queryByRole('button', { name: /Općenito/ })).toBeNull();
});

test("a closed round's chats stand under their coordinator", async () => {
  const lead = { ...CHAT, id: 'lead-old', title: 'Koordinator kruga', at: AT, open: true };
  const member = {
    ...CHAT,
    id: 'member-old',
    title: 'Grupe pod koordinatorom',
    at: AT,
    open: false,
    state: 'closed',
    coordinator: 'lead-old',
  };
  const [general, alpha] = PROJECTS.projects;
  served({
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [general, { ...alpha, rounds: [], chats: [member, lead] }],
    }),
  });
  const { user } = open('/workspace', OWNER);
  const project = await screen.findByRole('region', { name: 'Alpha' });
  await user.click(within(project).getByRole('button', { name: /Alpha/, expanded: false }));
  const led = within(project)
    .getByRole('button', { name: /Koordinator kruga/ })
    .closest('li') as HTMLElement;
  within(led).getByRole('button', { name: /Grupe pod koordinatorom/ });
});

test('a project bears the name of its plan, else its folder capitalised', async () => {
  served({
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [
        ...PROJECTS.projects,
        { name: 'dida', path: '/work/dida', gate: null, plan: null, chats: [], rounds: [] },
        {
          name: 'opus-library',
          path: '/work/opus-library',
          gate: null,
          plan: { title: 'Plan OPUS', path: '/p/opus' },
          chats: [],
          rounds: [],
        },
      ],
    }),
  });
  open('/workspace', OWNER);
  await screen.findByRole('region', { name: 'Alpha' });
  screen.getByRole('region', { name: 'Dida' });
  screen.getByRole('region', { name: 'Opus-library' });
});

test("a project's plan opens from its menu and stands nowhere else on the page", async () => {
  served();
  const { user, router } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  expect(within(alpha).queryByText(/Plan Alpha/)).toBeNull();
  fireEvent.contextMenu(within(alpha).getByRole('heading', { name: /Alpha/ }));
  await user.click(await screen.findByRole('menuitem', { name: 'Otvori plan' }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/p/plan'));
});

test('a project the owner put under Others waits folded at the bottom and is moved back from its menu', async () => {
  const asked: Asked[] = [];
  const dida = { name: 'dida', path: '/work/dida', gate: null, plan: null, chats: [], rounds: [] };
  served({
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [...PROJECTS.projects, { ...dida, aside: true }],
    }),
    'POST /api/workspace/projects': async (request) => {
      asked.push((await request.json()) as Asked);
      return new Response(null, { status: 204 });
    },
  });
  const { user } = open('/workspace', OWNER);
  await screen.findByRole('region', { name: 'Alpha' });
  expect(screen.queryByRole('region', { name: 'Dida' })).toBeNull();
  await user.click(screen.getByRole('button', { name: /Ostali\s*1/, expanded: false }));
  const others = screen.getByRole('region', { name: 'Dida' });
  fireEvent.contextMenu(within(others).getByRole('heading', { name: 'Dida' }));
  await user.click(await screen.findByRole('menuitem', { name: 'Vrati u glavne' }));
  await waitFor(() => expect(asked).toEqual([{ name: 'dida', aside: false }]));
});

test('a project in the main list is put under Others from its menu, the general one never', async () => {
  const asked: Asked[] = [];
  served({
    'POST /api/workspace/projects': async (request) => {
      asked.push((await request.json()) as Asked);
      return new Response(null, { status: 204 });
    },
  });
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  fireEvent.contextMenu(within(alpha).getByRole('heading', { name: /Alpha/ }));
  await user.click(await screen.findByRole('menuitem', { name: 'Premjesti u Ostale' }));
  await waitFor(() => expect(asked).toEqual([{ name: 'alpha', aside: true }]));
  const general = screen.getByRole('region', { name: 'Općenito' });
  fireEvent.contextMenu(within(general).getByRole('heading', { name: 'Općenito' }));
  expect(screen.queryByRole('menuitem', { name: 'Premjesti u Ostale' })).toBeNull();
});

test('an earlier chat is read here and comes back in the editor once the workspace lets it go', async () => {
  const asked: Asked[] = [];
  const opened = served({
    'POST /api/workspace/commands': async (request) => {
      const given = (await request.json()) as Asked;
      asked.push(given);
      return { ...COMMAND, ...given, id: 1, state: 'done' };
    },
  });
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  await user.click(within(alpha).getByRole('button', { name: /Alpha/, expanded: false }));
  const free = screen.getByRole('button', { name: /Popravak izvoza/ });
  await user.click(free);
  expect(free.getAttribute('aria-current')).toBe('true');
  const chat = screen.getByRole('region', { name: 'Razgovor' });
  await within(chat).findByRole('heading', { name: /Popravak izvoza/ });
  expect(opened).not.toHaveBeenCalled();
  await user.click(within(chat).getByRole('button', { name: 'Otvori chat' }));
  await waitFor(() => expect(asked).toEqual([{ kind: 'open', session: 'free' }]));
  await waitFor(() =>
    expect(opened).toHaveBeenCalledWith(
      '/code/?folder=%2Fwork%2Falpha&chat=free',
      'ponistra-code-alpha',
    ),
  );
  const busy = screen.getByRole('button', { name: /Nova tablica/ });
  within(busy).getByText('U radu');
  await user.click(busy);
  await within(chat).findByRole('heading', { name: /Nova tablica/ });
  expect(opened).toHaveBeenCalledTimes(1);
});

function commanded(asked: Asked[]) {
  return {
    'POST /api/workspace/commands': async (request: Request) => {
      const given = (await request.json()) as Asked;
      asked.push(given);
      return { ...COMMAND, ...given, id: asked.length, state: 'sent' };
    },
  };
}

test('a round shows what each of its chats is doing and is started from here', async () => {
  const asked: Asked[] = [];
  served(commanded(asked));
  const { user } = open('/workspace', OWNER);
  const round = await screen.findByRole('region', { name: /^Krug / });
  const row = (name: RegExp) => within(round).getByRole('button', { name });
  within(row(/Plan kruga/)).getByText('Koordinator');
  within(row(/Plan kruga/)).getByText('Gotov');
  within(row(/Kod → Krugovi/)).getByText('Radi');
  expect(within(row(/Grupe u panelu/)).getByText('Čeka vas').title).toBe('input needed');
  expect(within(round).queryByRole('button', { name: /Pomoćnici e2e/ })).toBeNull();
  const unsent = within(round).getByText(/Pomoćnici e2e/, { selector: 'summary span' });
  await user.click(unsent);
  expect(unsent.closest('details')?.open).toBe(true);
  within(round).getByText(/Područje: e2e\/tests\/helpers/);
  expect(within(round).queryByRole('button', { name: 'Objedini' })).toBeNull();
  expect(within(round).queryByRole('button', { name: 'Pushaj' })).toBeNull();
  await user.click(within(round).getByRole('button', { name: 'Pokreni krug' }));
  expect(within(round).queryByRole('checkbox')).toBeNull();
  fireEvent.contextMenu(row(/Plan kruga/));
  const auto = await screen.findByRole('menuitemcheckbox', { name: 'Objedini sam' });
  expect(auto.getAttribute('aria-checked')).toBe('true');
  await user.click(auto);
  const id = ROUND.id;
  await waitFor(() =>
    expect(asked).toEqual([
      { kind: 'start', round: id },
      { kind: 'auto', round: id, text: 'off' },
    ]),
  );
});

const OTHER_ROUND = {
  ...ROUND,
  id: 'alpha-20261111-1500',
  coordinator: { ...ROUND.coordinator, id: 'other', name: 'alpha-77', title: 'Uvoz tablica' },
  chats: [],
};

test('a chat is moved under a coordinator of its project from its menu', async () => {
  const asked: Asked[] = [];
  served({
    ...commanded(asked),
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [{ ...PROJECTS.projects[1], rounds: [ROUND, OTHER_ROUND] }],
    }),
  });
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  fireEvent.contextMenu(within(alpha).getByRole('button', { name: /Nova tablica/ }));
  (await screen.findByRole('menuitem', { name: 'Premjesti pod' })).focus();
  await user.keyboard('{ArrowRight}');
  (await screen.findByRole('menuitem', { name: 'Uvoz tablica' })).focus();
  await user.keyboard('{Enter}');
  await waitFor(() =>
    expect(asked).toEqual([{ kind: 'move', session: 'busy', round: OTHER_ROUND.id }]),
  );
  const lead = screen.getByRole('region', { name: 'Krug Plan kruga' });
  fireEvent.contextMenu(within(lead).getByRole('button', { name: /Kod → Krugovi/ }));
  (await screen.findByRole('menuitem', { name: 'Premjesti pod' })).focus();
  await user.keyboard('{ArrowRight}');
  await screen.findByRole('menuitem', { name: 'Uvoz tablica' });
  expect(screen.queryByRole('menuitem', { name: 'Plan kruga' })).toBeNull();
});

test('a coordinator dropped on another brings its round along, a chat of another project is not taken', async () => {
  const asked: Asked[] = [];
  const beta = {
    ...PROJECTS.projects[1],
    name: 'beta',
    path: '/work/beta',
    plan: null,
    chats: [{ ...CHAT, id: 'far', title: 'Drugi projekt', at: '2026-11-08T09:00:00Z', open: true }],
    rounds: [],
  };
  served({
    ...commanded(asked),
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [{ ...PROJECTS.projects[1], rounds: [ROUND, OTHER_ROUND] }, beta],
    }),
  });
  open('/workspace', OWNER);
  const target = await screen.findByRole('region', { name: 'Krug Uvoz tablica' });
  const source = screen.getByRole('region', { name: 'Krug Plan kruga' });
  const lead = within(source).getByRole('button', { name: /Plan kruga/ }).parentElement!;
  const dataTransfer = {
    types: ['text/plain'],
    setData: () => undefined,
    effectAllowed: '',
    dropEffect: '',
  };
  fireEvent.dragStart(lead, { dataTransfer });
  expect(fireEvent.dragOver(source, { dataTransfer })).toBe(true);
  expect(fireEvent.dragOver(target, { dataTransfer })).toBe(false);
  fireEvent.drop(target, { dataTransfer });
  await waitFor(() =>
    expect(asked).toEqual([{ kind: 'move', session: 'lead', round: OTHER_ROUND.id }]),
  );
  const far = screen.getByRole('button', { name: /Drugi projekt/ }).parentElement!;
  fireEvent.dragStart(far, { dataTransfer });
  expect(fireEvent.dragOver(target, { dataTransfer })).toBe(true);
  fireEvent.dragEnd(far);
});

test('a move the workspace refuses says why under the round it was dropped on', async () => {
  const asked: Asked[] = [];
  served({
    ...commanded(asked),
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [{ ...PROJECTS.projects[1], rounds: [ROUND, OTHER_ROUND] }],
    }),
    'GET /api/workspace/commands': () => ({
      commands: asked.map((given, at) => ({
        ...COMMAND,
        ...given,
        id: at + 1,
        state: 'failed',
        error: 'asked',
      })),
    }),
  });
  open('/workspace', OWNER);
  const target = await screen.findByRole('region', { name: 'Krug Uvoz tablica' });
  const chat = screen.getByRole('button', { name: /Nova tablica/ }).parentElement!;
  const dataTransfer = { types: ['text/plain'], setData: () => undefined, effectAllowed: '' };
  fireEvent.dragStart(chat, { dataTransfer });
  fireEvent.dragOver(target, { dataTransfer });
  fireEvent.drop(target, { dataTransfer });
  await within(target).findByText('Koordinatoru je naredba već poslana.');
});

const FINISHED_ROUND = {
  ...ROUND,
  started: '2026-11-11T13:29:00Z',
  chats: [
    { ...ROUND.chats[0], state: 'idle', at: '2026-11-11T14:00:00Z' },
    { ...ROUND.chats[1], state: 'closed', waitingFor: null, at: '2026-11-11T14:10:00Z' },
  ],
};

test('a session named as its title is not named twice beneath it', async () => {
  const named = {
    ...ROUND,
    coordinator: {
      ...ROUND.coordinator,
      name: 'Kod: limiti i memorija',
      title: 'Kod: limiti i memorija',
    },
  };
  served({
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [{ ...PROJECTS.projects[1], chats: [], rounds: [named] }],
    }),
  });
  open('/workspace', OWNER);
  const round = await screen.findByRole('region', { name: /^Krug / });
  const lead = within(round).getByRole('button', { name: /Kod: limiti i memorija/ });
  expect(within(lead).getAllByText('Kod: limiti i memorija')).toHaveLength(1);
  within(lead).getByText('Koordinator');
});

const UNPUSHED = { ...GATE, checked: { tree: 'd'.repeat(40), at: '2026-11-11T16:00:00Z' } };

test('a round is offered Objedini in its coordinator’s row once every chat finished', async () => {
  const asked: Asked[] = [];
  served({
    ...commanded(asked),
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [{ ...PROJECTS.projects[1], chats: [], rounds: [FINISHED_ROUND] }],
    }),
  });
  const { user } = open('/workspace', OWNER);
  const round = await screen.findByRole('region', { name: /^Krug / });
  expect(within(round).queryByRole('button', { name: 'Pushaj' })).toBeNull();
  const lead = within(round)
    .getByRole('button', { name: /Plan kruga/ })
    .closest('li');
  await user.click(within(lead as HTMLElement).getByRole('button', { name: 'Objedini' }));
  await waitFor(() => expect(asked).toEqual([{ kind: 'consolidate', round: ROUND.id }]));
});

test('a consolidated round with a green tree not yet pushed is offered Pushaj instead', async () => {
  const asked: Asked[] = [];
  const consolidated = {
    ...FINISHED_ROUND,
    coordinator: { ...FINISHED_ROUND.coordinator, at: '2026-11-11T16:05:00Z' },
  };
  served({
    ...commanded(asked),
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [{ ...PROJECTS.projects[1], gate: UNPUSHED, chats: [], rounds: [consolidated] }],
    }),
    'GET /api/workspace/commands': () => ({
      commands: [
        {
          ...COMMAND,
          id: 3,
          kind: 'consolidate',
          round: ROUND.id,
          state: 'done',
          changed_at: '2026-11-11T15:00:00Z',
        },
      ],
    }),
  });
  const { user } = open('/workspace', OWNER);
  const round = await screen.findByRole('region', { name: /^Krug / });
  await user.click(await within(round).findByRole('button', { name: 'Pushaj' }));
  expect(within(round).queryByRole('button', { name: 'Objedini' })).toBeNull();
  await waitFor(() => expect(asked).toEqual([{ kind: 'push', round: ROUND.id }]));
});

test('the coordinator of a closed round is told to push while its green tree waits', async () => {
  const asked: Asked[] = [];
  const project = (gate: typeof GATE) => ({
    ...PROJECTS.projects[1],
    gate,
    rounds: [],
    chats: [
      { ...CHAT, id: 'lead', title: 'Plan kruga', at: AT, open: false, state: 'closed' },
      {
        ...CHAT,
        id: 'member',
        title: 'Kod → Krugovi',
        at: AT,
        open: false,
        state: 'closed',
        coordinator: 'lead',
      },
    ],
  });
  served({
    ...commanded(asked),
    'GET /api/workspace/projects': () => ({ ...PROJECTS, projects: [project(UNPUSHED)] }),
  });
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  await user.click(within(alpha).getByRole('button', { name: 'Pushaj' }));
  await waitFor(() => expect(asked).toEqual([{ kind: 'push', session: 'lead' }]));
});

test('a word sent to the coordinator holds the others back until it is taken', async () => {
  served({
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [{ ...PROJECTS.projects[1], rounds: [{ ...ROUND, asked: 'pushaj' }] }],
    }),
  });
  open('/workspace', OWNER);
  const round = await screen.findByRole('region', { name: /^Krug / });
  within(round).getByText('Koordinatoru je poslano „pushaj”.');
  expect(within(round).queryByRole('button', { name: 'Objedini' })).toBeNull();
  expect(within(round).queryByRole('button', { name: 'Pushaj' })).toBeNull();
});

test('a new round starts a coordinator told what to divide, the editor left closed', async () => {
  const asked: Asked[] = [];
  const opened = served(commanded(asked));
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  await user.click(within(alpha).getByRole('button', { name: 'Novi krug' }));
  const form = screen.getByRole('region', { name: 'Novi krug' });
  await user.type(
    within(form).getByRole('textbox', { name: 'Što krug treba napraviti' }),
    'tablice i pošta',
  );
  await user.click(within(form).getByRole('button', { name: 'Otvori koordinatora' }));
  await waitFor(() =>
    expect(asked).toEqual([
      { kind: 'chat', folder: '/work/alpha', text: 'nastavi: tablice i pošta' },
    ]),
  );
  expect(opened).not.toHaveBeenCalled();
});

test('a project shows its gate folded under its first check, and what each chat holds and changed', async () => {
  served();
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  const status = within(alpha)
    .getByText(/^Push /)
    .closest('ul') as HTMLElement;
  const lines = () =>
    within(status)
      .getAllByRole('listitem')
      .map((line) => line.textContent);
  expect(lines()).toEqual([expect.stringMatching(/^Push .*2$/)]);
  const checks = within(status).getByRole('button', { name: 'Provjere', expanded: false });
  expect(checks.className).toContain('text-danger');
  await user.click(checks);
  expect(lines()).toEqual([
    expect.stringMatching(/^Push /),
    expect.stringMatching(/^Preglednik /),
    expect.stringMatching(/^Noćni run /),
  ]);
  expect(
    within(alpha)
      .getByText(/Preglednik/)
      .closest('li')?.className,
  ).toContain('text-danger');
  within(alpha).getByText(/Noćni run prošao .* nije zadnji push/);
  await user.click(within(alpha).getByRole('button', { name: /Alpha/, expanded: false }));
  within(within(alpha).getByRole('button', { name: /Popravak izvoza/ })).getByText('81k');
  const large = within(within(alpha).getByRole('button', { name: /Kod → Krugovi/ })).getByText(
    '312k',
  );
  expect(large.className).toContain('text-danger');
  within(within(alpha).getByRole('button', { name: /Kod → Krugovi/ })).getByText('+309');
});

test('the workspace restarts only when nothing runs in it, and after it is confirmed', async () => {
  const asked: Asked[] = [];
  const restarted = vi.fn(commanded(asked)['POST /api/workspace/commands']);
  served({ 'POST /api/workspace/commands': restarted });
  const { user } = open('/workspace', OWNER);
  await user.click(await screen.findByRole('button', { name: 'Restartaj radni prostor' }));
  const dialog = await screen.findByRole('alertdialog');
  within(dialog).getByText(/svi chatovi \(4\)/);
  await user.click(within(dialog).getByRole('button', { name: 'Restartaj radni prostor' }));
  await waitFor(() => expect(asked).toEqual([{ kind: 'restart' }]));
  await screen.findByRole('button', { name: 'Radni prostor se restarta' });
});

test('a workspace at work is not offered a restart', async () => {
  served({
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      restart: {
        sessions: 4,
        working: [{ id: 'one', name: 'alpha-de', state: 'working', title: 'Kod → Krugovi' }],
        scripts: [{ script: 'check-full', kind: 'browser', project: 'alpha' }],
      },
    }),
  });
  open('/workspace', OWNER);
  const restart = await screen.findByRole('button', { name: 'Restartaj radni prostor' });
  expect(restart).toHaveProperty('disabled', true);
  expect(restart.title).toBe('Radi: Kod → Krugovi\nProvjera (alpha)');
});

test('a chat at work is not offered to the editor until its turn ends', async () => {
  served({
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [
        {
          ...PROJECTS.projects[1],
          chats: [{ ...PROJECTS.projects[1].chats[1], state: 'working' }],
          rounds: [],
        },
      ],
    }),
  });
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  await user.click(within(alpha).getByRole('button', { name: /Nova tablica/ }));
  const chat = screen.getByRole('region', { name: 'Razgovor' });
  await within(chat).findByRole('heading', { name: /Nova tablica/ });
  expect(within(chat).getByRole('button', { name: 'Otvori chat' })).toHaveProperty(
    'disabled',
    true,
  );
  fireEvent.contextMenu(within(alpha).getByRole('button', { name: /Nova tablica/ }));
  const item = await screen.findByRole('menuitem', { name: 'Otvori chat' });
  expect(item.getAttribute('aria-disabled')).toBe('true');
});

test('a chat at work here is stopped beside Send, one at work in the editor is stopped there', async () => {
  const asked: Asked[] = [];
  served({
    ...commanded(asked),
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [
        {
          ...PROJECTS.projects[1],
          chats: [{ ...PROJECTS.projects[1].chats[1], state: 'working' }],
          rounds: [
            { ...ROUND, coordinator: { ...ROUND.coordinator, state: 'working', hosted: true } },
          ],
        },
      ],
    }),
  });
  const { user } = open('/workspace', OWNER);
  const chat = await screen.findByRole('region', { name: 'Razgovor' });
  await within(chat).findByRole('heading', { name: /Plan kruga/ });
  await user.click(within(chat).getByRole('button', { name: 'Zaustavi' }));
  await waitFor(() => expect(asked).toEqual([{ kind: 'stop', session: 'lead' }]));
  const alpha = screen.getByRole('region', { name: 'Alpha' });
  await user.click(within(alpha).getByRole('button', { name: /Nova tablica/ }));
  await within(chat).findByRole('heading', { name: /Nova tablica/ });
  expect(within(chat).getByRole('button', { name: 'Zaustavi' })).toHaveProperty('disabled', true);
});

test('an idle chat offers no Stop', async () => {
  served();
  open('/workspace', OWNER);
  const chat = await screen.findByRole('region', { name: 'Razgovor' });
  await within(chat).findByRole('heading', { name: /Plan kruga/ });
  expect(within(chat).queryByRole('button', { name: 'Zaustavi' })).toBeNull();
});

test('a chat that set to work meanwhile stays out of the editor and says why', async () => {
  const opened = served({
    'POST /api/workspace/commands': async (request) => ({
      ...COMMAND,
      ...((await request.json()) as Asked),
      id: 1,
      state: 'failed',
      error: 'chat_working',
    }),
  });
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  fireEvent.contextMenu(within(alpha).getByRole('button', { name: /Nova tablica/ }));
  await user.click(await screen.findByRole('menuitem', { name: 'Otvori chat' }));
  await screen.findByText('Chat upravo radi ili čeka vaš odgovor; otvorite ga kad završi.');
  expect(opened).not.toHaveBeenCalled();
});

test('an image pasted into the message shows small, can be taken off and goes with the words', async () => {
  const asked: Asked[] = [];
  const stored = 'f'.repeat(64);
  served({
    ...commanded(asked),
    'POST /api/uploads': async (request) => {
      const { size } = (await request.json()) as { size: number };
      const blob = { sha256: stored, size, media_type: 'image/png' };
      return { id: 'u', size, received: size, chunk: size, blob };
    },
  });
  vi.stubGlobal('createImageBitmap', async () => ({ width: 40, height: 30, close: () => {} }));
  URL.createObjectURL = () => 'blob:picture';
  URL.revokeObjectURL = () => {};
  const { user } = open('/workspace', OWNER);
  const chat = await screen.findByRole('region', { name: 'Razgovor' });
  const field = await within(chat).findByRole('textbox', { name: 'Poruka chatu' });
  const png = () => new File([new Uint8Array(8)], 'snimka.png', { type: 'image/png' });
  const pasted = (files: File[]) =>
    fireEvent.paste(field, { clipboardData: { files, getData: () => '' } });
  pasted([png()]);
  const images = await within(chat).findByRole('list', { name: 'Slike uz poruku' });
  await user.click(within(images).getByRole('button', { name: 'Ukloni sliku' }));
  expect(within(chat).queryByRole('list', { name: 'Slike uz poruku' })).toBeNull();
  pasted([png()]);
  await within(chat).findByRole('list', { name: 'Slike uz poruku' });
  await user.type(field, 'Što je ovo?');
  const send = within(chat).getByRole('button', { name: 'Pošalji' });
  await waitFor(() => expect(send).toHaveProperty('disabled', false));
  await user.click(send);
  await waitFor(() =>
    expect(asked).toEqual([
      { kind: 'say', session: 'lead', text: 'Što je ovo?', images: [stored] },
    ]),
  );
  await waitFor(() =>
    expect(within(chat).queryByRole('list', { name: 'Slike uz poruku' })).toBeNull(),
  );
  pasted([png(), png(), png(), png(), png()]);
  await within(chat).findByText('Uz poruku idu najviše četiri slike.');
});

test('a right click pastes into the message where the caret stands, and says when the browser refuses', async () => {
  served(commanded([]));
  open('/workspace', OWNER);
  const chat = await screen.findByRole('region', { name: 'Razgovor' });
  const field = await within(chat).findByRole('textbox', { name: 'Poruka chatu' });
  const read = vi.fn(async () => [
    {
      types: ['text/plain'],
      getType: async () => new Blob(['lijepim ']),
    },
  ]);
  const held = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { read } });
  onTestFinished(() => {
    if (held) Object.defineProperty(navigator, 'clipboard', held);
    else Reflect.deleteProperty(navigator, 'clipboard');
  });
  fireEvent.change(field, { target: { value: 'Ovdje tekst' } });
  (field as HTMLTextAreaElement).setSelectionRange(6, 6);
  fireEvent.contextMenu(field);
  await waitFor(() => expect(field).toHaveProperty('value', 'Ovdje lijepim tekst'));
  read.mockRejectedValueOnce(new Error('NotAllowedError'));
  fireEvent.contextMenu(field);
  await within(chat).findByText(/Preglednik ne dopušta Ponistri čitanje međuspremnika/);
});

test('the chat shows its model, and a click on it chooses another for its next answer', async () => {
  const asked: Asked[] = [];
  const models = [
    { value: 'opus', name: 'Opus 5.5', resolved: 'claude-opus-5-5' },
    { value: 'sonnet', name: 'Sonnet 5.5', resolved: 'claude-sonnet-5-5' },
  ];
  const lead = { ...ROUND.coordinator, model: 'claude-opus-5-5' };
  served({
    ...commanded(asked),
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      models,
      projects: [{ ...PROJECTS.projects[1], rounds: [{ ...ROUND, coordinator: lead }] }],
    }),
  });
  const { user } = open('/workspace', OWNER);
  const chat = await screen.findByRole('region', { name: 'Razgovor' });
  await user.click(await within(chat).findByRole('button', { name: 'Model: Opus 5.5' }));
  expect(screen.getByRole('menuitemradio', { name: 'Opus 5.5' })).toHaveProperty(
    'ariaChecked',
    'true',
  );
  await user.click(screen.getByRole('menuitemradio', { name: 'Sonnet 5.5' }));
  await waitFor(() => expect(asked).toEqual([{ kind: 'model', session: 'lead', text: 'sonnet' }]));
});

test('a started round is offered neither to start again nor to consolidate while it works', async () => {
  const started = { ...ROUND, started: '2026-11-11T13:29:00Z' };
  served({
    'GET /api/workspace/projects': () => ({
      ...PROJECTS,
      projects: [{ ...PROJECTS.projects[1], chats: [], rounds: [started] }],
    }),
  });
  open('/workspace', OWNER);
  const round = await screen.findByRole('region', { name: /^Krug / });
  within(round).getByRole('button', { name: /Kod → Krugovi/ });
  expect(within(round).queryByRole('button', { name: 'Objedini' })).toBeNull();
  expect(within(round).queryByRole('button', { name: 'Pokreni krug' })).toBeNull();
});

test('a code block and a whole answer are copied from the conversation', async () => {
  const command = 'cd /mnt/docker/workspace && docker compose up -d';
  served({
    'GET /api/workspace/chats/:session': (_request, { session }) => ({
      id: session,
      title: null,
      state: 'idle',
      waitingFor: null,
      said: [{ role: 'assistant', text: `Zalijepi:\n\n\`\`\`sh\n${command}\n\`\`\``, at: AT }],
    }),
  });
  const { user } = open('/workspace', OWNER);
  const chat = await screen.findByRole('region', { name: 'Razgovor' });
  const block = (await within(chat).findByText(command)).closest('div') as HTMLElement;
  await user.click(within(block).getByRole('button', { name: 'Kopiraj' }));
  expect(await navigator.clipboard.readText()).toBe(command);
  within(block).getByRole('button', { name: 'Kopirano' });
  const answer = within(chat).getAllByRole('button', { name: 'Kopiraj' });
  await user.click(answer[answer.length - 1]);
  expect(await navigator.clipboard.readText()).toBe(`Zalijepi:\n\n\`\`\`sh\n${command}\n\`\`\``);
});

test("a chat's earlier turns are read on from where its page begins, its latest question pinned atop", async () => {
  const read: string[] = [];
  served({
    'GET /api/workspace/chats/:session': (request, { session }) => {
      const asked = new URL(request.url).search;
      read.push(asked);
      const said =
        asked === '?before=700'
          ? [
              { role: 'user', text: 'prvo pitanje', at: AT },
              { role: 'assistant', text: 'Prvi odgovor.', at: AT },
            ]
          : session === 'lead'
            ? SAID
            : [];
      return {
        id: session,
        title: null,
        state: 'idle',
        waitingFor: null,
        said,
        earlier: asked === '?before=700' ? null : 700,
      };
    },
  });
  const { user } = open('/workspace', OWNER);
  const chat = await screen.findByRole('region', { name: 'Razgovor' });
  const latest = await within(chat).findByText('nastavi: tablice');
  expect(latest.closest('li')?.className).toContain('sticky');
  await user.click(within(chat).getByRole('button', { name: 'Ranije' }));
  const first = await within(chat).findByText('prvo pitanje');
  expect(first.closest('li')?.className).not.toContain('sticky');
  within(chat).getByText('Prvi odgovor.');
  within(chat).getByText('Krug je otvoren.');
  await waitFor(() => expect(read).toContain('?from=700'));
  expect(within(chat).queryByRole('button', { name: 'Ranije' })).toBeNull();
});

test('the latest coordinator is read here, a message going to its panel by Enter', async () => {
  const touch = globalThis.matchMedia;
  onTestFinished(() => void (globalThis.matchMedia = touch));
  vi.spyOn(globalThis, 'matchMedia').mockImplementation((query) =>
    query === '(pointer: fine)'
      ? ({ ...touch(query), matches: true } as MediaQueryList)
      : touch(query),
  );
  const asked: Asked[] = [];
  served(commanded(asked));
  const { user } = open('/workspace', OWNER);
  const chat = await screen.findByRole('region', { name: 'Razgovor' });
  await within(chat).findByText('Dijelim krug na dva chata.');
  within(chat).getByText('nastavi: tablice');
  within(chat).getByText('Krug je otvoren.');
  within(chat).getByText('Alati: 2');
  const field = within(chat).getByRole('textbox', { name: 'Poruka chatu' });
  await user.type(field, 'objedini kad budu gotovi');
  await user.keyboard('{Shift>}{Enter}{/Shift}');
  expect(field).toHaveProperty('value', 'objedini kad budu gotovi\n');
  await user.keyboard('{Enter}');
  await user.click(within(chat).getByRole('button', { name: 'Gdje smo' }));
  await waitFor(() =>
    expect(asked).toEqual([
      { kind: 'say', session: 'lead', text: 'objedini kad budu gotovi' },
      { kind: 'say', session: 'lead', text: 'catchup' },
    ]),
  );
  await waitFor(() => expect(field).toHaveProperty('value', ''));
});

test("the agent's words read as Markdown and what the harness told it as a line of its own", async () => {
  served({
    'GET /api/workspace/chats/:session': (_request, { session }) => ({
      id: session,
      title: null,
      state: 'idle',
      waitingFor: null,
      said: [
        { role: 'harness', kind: 'peer', text: 'alpha-de', at: AT },
        { role: 'harness', kind: 'task', text: 'Background command "gate" completed', at: AT },
        {
          role: 'assistant',
          text: 'Krug je **zelen**.\n\n- `check.sh` prošao\n- <b>bez</b> HTML-a\n\n| a | b |\n|---|---|\n| 1 | 2 |',
          at: AT,
        },
      ],
    }),
  });
  open('/workspace', OWNER);
  const chat = await screen.findByRole('region', { name: 'Razgovor' });
  await within(chat).findByText('Poruka od sesije alpha-de');
  within(chat).getByText('Pozadinski zadatak: Background command "gate" completed');
  expect(within(chat).getByText('zelen').tagName).toBe('STRONG');
  expect(within(chat).getByText('check.sh').tagName).toBe('CODE');
  expect(
    within(chat)
      .getAllByRole('listitem')
      .some((item) => item.closest('ul')),
  ).toBe(true);
  within(chat).getByRole('table');
  expect(chat.querySelector('b')).toBeNull();
});

test('a chat waiting on its owner is answered Yes or No atop the list', async () => {
  const asked: Asked[] = [];
  served(commanded(asked));
  const { user } = open('/workspace', OWNER);
  const waiting = await screen.findByRole('region', { name: 'Čeka vas' });
  within(waiting).getByText('input needed');
  await user.click(within(waiting).getByRole('button', { name: 'Da' }));
  await user.click(within(waiting).getByRole('button', { name: 'Ne' }));
  await waitFor(() =>
    expect(asked).toEqual([
      { kind: 'answer', session: 'two', text: 'yes' },
      { kind: 'answer', session: 'two', text: 'no' },
    ]),
  );
});

test('what was asked of a chat stands at its foot until it is carried out', async () => {
  served({
    'GET /api/workspace/commands': () => ({
      commands: [
        {
          ...COMMAND,
          id: 2,
          kind: 'consolidate',
          round: ROUND.id,
          session: 'lead',
          text: 'objedini sam od sebe',
          auto: true,
          state: 'taken',
        },
        { ...COMMAND, id: 1, kind: 'say', session: 'lead', text: 'hej', state: 'sent' },
      ],
    }),
  });
  open('/workspace', OWNER);
  const chat = await screen.findByRole('region', { name: 'Razgovor' });
  within(await within(chat).findByText(/^hej/)).getByText('Poslano');
  within(within(chat).getByText(/^objedini sam od sebe/)).getByText('Preuzeto');
});

test('an archive that fails says why under its chat', async () => {
  const asked: Asked[] = [];
  served({
    ...commanded(asked),
    'GET /api/workspace/commands': () => ({
      commands: asked.map((given, at) => ({
        ...COMMAND,
        ...given,
        id: at + 1,
        state: 'failed',
        error: 'not_ended',
      })),
    }),
  });
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  fireEvent.contextMenu(within(alpha).getByRole('button', { name: /Nova tablica/ }));
  await user.click(await screen.findByRole('menuitem', { name: 'Arhiviraj' }));
  await within(alpha).findByText('Radni prostor nije zaustavio chat.');
});

test('a chat in use is archived from its menu', async () => {
  const asked: Asked[] = [];
  served(commanded(asked));
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  fireEvent.contextMenu(within(alpha).getByRole('button', { name: /Nova tablica/ }));
  await user.click(await screen.findByRole('menuitem', { name: 'Arhiviraj' }));
  await waitFor(() => expect(asked).toEqual([{ kind: 'archive', session: 'busy' }]));
});

test('a closed chat is archived from its menu too', async () => {
  const asked: Asked[] = [];
  served(commanded(asked));
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  await user.click(within(alpha).getByRole('button', { name: /Alpha/, expanded: false }));
  fireEvent.contextMenu(within(alpha).getByRole('button', { name: /Popravak izvoza/ }));
  await user.click(await screen.findByRole('menuitem', { name: 'Arhiviraj' }));
  await waitFor(() => expect(asked).toEqual([{ kind: 'archive', session: 'free' }]));
});

test('a chat in use is closed from its menu and stays on the list', async () => {
  const asked: Asked[] = [];
  served(commanded(asked));
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  fireEvent.contextMenu(within(alpha).getByRole('button', { name: /Nova tablica/ }));
  await user.click(await screen.findByRole('menuitem', { name: 'Zatvori' }));
  await waitFor(() => expect(asked).toEqual([{ kind: 'close', session: 'busy' }]));
});

test('a closed chat opens in the editor from its menu, which has nothing to close', async () => {
  const opened = served();
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  await user.click(within(alpha).getByRole('button', { name: /Alpha/, expanded: false }));
  fireEvent.contextMenu(within(alpha).getByRole('button', { name: /Popravak izvoza/ }));
  await screen.findByRole('menuitem', { name: 'Arhiviraj' });
  expect(screen.queryByRole('menuitem', { name: 'Zatvori' })).toBeNull();
  await user.click(screen.getByRole('menuitem', { name: 'Otvori chat' }));
  await waitFor(() =>
    expect(opened).toHaveBeenCalledWith(
      '/code/?folder=%2Fwork%2Falpha&chat=free',
      'ponistra-code-alpha',
    ),
  );
});

test('a chat is renamed from its menu', async () => {
  const asked: Asked[] = [];
  served(commanded(asked));
  const { user } = open('/workspace', OWNER);
  const alpha = await screen.findByRole('region', { name: 'Alpha' });
  fireEvent.contextMenu(within(alpha).getByRole('button', { name: /Nova tablica/ }));
  await user.click(await screen.findByRole('menuitem', { name: 'Preimenuj' }));
  const dialog = await screen.findByRole('dialog', { name: 'Preimenuj' });
  const name = within(dialog).getByRole('textbox');
  await user.clear(name);
  await user.type(name, 'Tablice za izvoz');
  await user.click(within(dialog).getByRole('button', { name: 'Spremi' }));
  await waitFor(() =>
    expect(asked).toEqual([{ kind: 'rename', session: 'busy', text: 'Tablice za izvoz' }]),
  );
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});

const MEMORY_PROPOSAL = {
  id: 7,
  store: '-work-alpha',
  file: 'project_a.md',
  source: 'mechanical',
  kind: 'state',
  reason: null,
  session: null,
  state: 'open',
  removes: false,
  creates: false,
  created_at: '2026-11-12T12:00:00+00:00',
  decided_at: null,
  diff: [
    { op: '-', text: 'S1 na devu necommitano' },
    { op: '+', text: 'S1 commitano `abc1234`' },
  ],
};

function memory(
  proposals: (typeof MEMORY_PROPOSAL)[],
  history: unknown[] = [],
  advice: unknown[] = [],
) {
  return {
    root: '/work',
    stores: [
      {
        store: '-work-alpha',
        folder: '/work/alpha',
        files: 12,
        bytes: 9000,
        index: { lines: 210, bytes: 8000, tokens: 2000, cut: 10 },
        findings: [{ file: 'project_b.md', kind: 'orphan', detail: '' }],
        proposals: proposals.length,
        unanalysed: 3,
      },
    ],
    advice,
    proposals,
    history,
    nightly: false,
  };
}

test('proposals for the memory wait atop the list and are accepted on the Memory tab', async () => {
  const asked: string[] = [];
  let pending = [MEMORY_PROPOSAL];
  served({
    'GET /api/memory/waiting': () => ({ count: pending.length }),
    'GET /api/memory': () =>
      memory(
        pending,
        pending.length
          ? []
          : [{ ...MEMORY_PROPOSAL, state: 'applied', decided_at: MEMORY_PROPOSAL.created_at }],
      ),
    'POST /api/memory/proposals/:id': async (request, { id }) => {
      asked.push(`${id} ${((await request.json()) as Asked).text}`);
      pending = [];
      return { ...MEMORY_PROPOSAL, state: 'applied' };
    },
    'POST /api/memory/proposals/:id/revert': (_request, { id }) => {
      asked.push(`${id} revert`);
      return { ...MEMORY_PROPOSAL, state: 'reverted' };
    },
  });
  const { user } = open('/workspace', OWNER);
  await user.click(await screen.findByRole('button', { name: /^Memorija\s*1$/ }));
  const proposals = await screen.findByRole('region', { name: 'Prijedlozi za memoriju' });
  within(proposals).getByText('S1 commitano `abc1234`');
  const stores = screen.getByRole('region', { name: 'Spremišta' });
  within(stores).getByText('Alpha');
  await user.click(within(proposals).getByRole('button', { name: 'Prihvati' }));
  await waitFor(() => expect(asked).toEqual(['7 yes']));
  await within(proposals).findByText('Nema prijedloga.');
  const history = screen.getByRole('region', { name: 'Povijest' });
  await user.click(within(history).getByRole('button', { name: 'Vrati' }));
  await waitFor(() => expect(asked).toEqual(['7 yes', '7 revert']));
  await screen.findByRole('button', { name: 'Memorija' });
});

test('a review groups the proposals, and a group is accepted at once', async () => {
  const asked: string[] = [];
  const other = { ...MEMORY_PROPOSAL, id: 8, file: 'project_b.md', kind: 'link' };
  let pending = [MEMORY_PROPOSAL, other];
  const group = {
    id: 3,
    title: 'Poveznice na preimenovane memorije',
    reason: 'Svaka vodi na memoriju koja postoji.',
    action: 'accept',
    proposals: [8],
  };
  served({
    'GET /api/memory/waiting': () => ({ count: pending.length }),
    'GET /api/memory': () => memory(pending, [], pending.includes(other) ? [group] : []),
    'POST /api/memory/review': () => {
      asked.push('review');
      return { state: 'taken', error: null };
    },
    'POST /api/memory/advice/:id': async (request, { id }) => {
      asked.push(`${id} ${((await request.json()) as Asked).text}`);
      pending = [MEMORY_PROPOSAL];
      return { applied: 1, rejected: 0, stale: 0 };
    },
  });
  const { user } = open('/workspace?view=memory', OWNER);
  await user.click(await screen.findByRole('button', { name: 'Analiziraj prijedloge' }));
  await waitFor(() => expect(asked).toEqual(['review']));
  const proposals = screen.getByRole('region', { name: 'Prijedlozi za memoriju' });
  within(proposals).getByText('Preporuka: prihvatiti');
  within(proposals).getByText('Bez preporuke');
  await user.click(within(proposals).getByRole('button', { name: 'Prihvati sve (1)' }));
  await waitFor(() => expect(asked).toEqual(['review', '3 yes']));
  await waitFor(() => expect(within(proposals).queryByText('Bez preporuke')).toBeNull());
  within(proposals).getByText('S1 commitano `abc1234`');
});

test('a notification of a proposal opens the Memory tab', async () => {
  served({
    'GET /api/memory/waiting': () => ({ count: 1 }),
    'GET /api/memory': () => memory([MEMORY_PROPOSAL]),
  });
  open('/workspace?view=memory', OWNER);
  const proposals = await screen.findByRole('region', { name: 'Prijedlozi za memoriju' });
  within(proposals).getByRole('button', { name: 'Odbij' });
});
