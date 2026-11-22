// @vitest-environment jsdom
import { EditorView } from '@codemirror/view';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { I18nProvider } from './i18n';
import { FilesPanel } from './workspaceFiles';

// jsdom lays nothing out, so CodeMirror has nothing to measure.
Range.prototype.getClientRects ??= () => [] as unknown as DOMRectList;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();

const FOLDER = '/work/ponistra';
const HASH = 'a'.repeat(64);
const NEWER = 'b'.repeat(64);

const LISTS: Record<string, unknown> = {
  '': {
    path: '',
    entries: [
      { name: 'backend', kind: 'folder', size: null, modified: '2026-11-16T00:00:00Z' },
      { name: 'away', kind: 'outside', size: null, modified: null },
      { name: 'logo.png', kind: 'file', size: 2400, modified: '2026-11-16T00:00:00Z' },
    ],
  },
  backend: {
    path: 'backend',
    entries: [{ name: 'app.py', kind: 'file', size: 6, modified: '2026-11-16T00:00:00Z' }],
  },
};

const FILES: Record<string, unknown> = {
  'backend/app.py': {
    path: 'backend/app.py',
    size: 6,
    modified: '2026-11-16T00:00:00Z',
    kind: 'text',
    text: 'x = 1\n',
    hash: HASH,
  },
  'logo.png': {
    path: 'logo.png',
    size: 2400,
    modified: '2026-11-16T00:00:00Z',
    kind: 'binary',
    text: null,
    hash: HASH,
  },
};

const HOSTS = {
  hosts: [
    {
      name: 'mlaka',
      address: '192.0.2.11',
      port: 22,
      user: 'root',
      path: '/srv',
      key: 'ponistra_ed25519',
    },
  ],
  keys: [
    {
      name: 'ponistra_ed25519',
      type: 'ssh-ed25519',
      comment: 'ponistra@example.org',
      public: 'ssh-ed25519 AAAAC3Nza ponistra@example.org',
    },
  ],
  made: 'ponistra_ed25519',
};

const sent: { method: string; url: string; body: Record<string, unknown> | null }[] = [];
let written: () => Response;
let onHost: () => Response;

beforeEach(() => {
  sent.length = 0;
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: true,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
  written = () => Response.json({ path: 'backend/app.py', size: 6, modified: '', hash: NEWER });
  onHost = () =>
    Response.json({
      path: '',
      entries: [{ name: 'app.conf', kind: 'file', size: 6, modified: '2026-11-22T00:00:00Z' }],
    });
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      sent.push({ method, url, body });
      const params = new URL(url, 'http://ponistra').searchParams;
      const asked = params.get('path') ?? '';
      if (url.startsWith('/api/workspace/hosts'))
        return Promise.resolve(
          Response.json(
            method === 'POST' && body?.name
              ? { ...HOSTS, hosts: [...HOSTS.hosts, { ...body, was: undefined }] }
              : HOSTS,
          ),
        );
      if (method === 'POST') return Promise.resolve(written());
      if (url.startsWith('/api/workspace/files?') && params.has('host'))
        return Promise.resolve(onHost());
      if (url.startsWith('/api/workspace/files?'))
        return Promise.resolve(Response.json(LISTS[asked]));
      return Promise.resolve(
        Response.json(
          params.has('host')
            ? { path: asked, size: 6, modified: '', kind: 'text', text: 'x = 1\n', hash: HASH }
            : FILES[asked],
        ),
      );
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function shown() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <FilesPanel folder={FOLDER} name="Ponistra" onDirty={() => {}} onClose={() => {}} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

async function opened() {
  shown();
  await userEvent.click(await screen.findByRole('button', { name: 'backend' }));
  await userEvent.click(await screen.findByRole('button', { name: 'app.py' }));
  await waitFor(() => expect(document.querySelector('.cm-editor')).not.toBeNull());
  return EditorView.findFromDOM(document.querySelector<HTMLElement>('.cm-editor')!)!;
}

test('the tree lists folders first and leaves a link out of the project closed', async () => {
  shown();
  const away = await screen.findByRole('button', { name: 'away' }, { timeout: 5000 });
  expect(away).toHaveProperty('disabled', true);
  expect(away.title).toBe('Poveznica vodi izvan projekta.');
  const items = screen.getAllByRole('treeitem').map((item) => item.textContent);
  expect(items).toEqual(['backend', 'away', 'logo.png']);
});

test('a file that is not text is only downloaded', async () => {
  shown();
  await userEvent.click(await screen.findByRole('button', { name: 'logo.png' }));
  const link = await screen.findByRole('link', { name: 'Preuzmi' });
  expect(link.getAttribute('href')).toBe(
    `/api/workspace/file/raw?folder=${encodeURIComponent(FOLDER)}&path=logo.png`,
  );
  expect(screen.getByText('Datoteka nije tekst i može se samo preuzeti.')).toBeTruthy();
});

test('an edited file is saved with the hash of what was read, and the next save with the new one', async () => {
  const editor = await opened();
  const save = screen.getByRole('button', { name: 'Spremi' });
  expect(save).toHaveProperty('disabled', true);
  act(() => editor.dispatch({ changes: { from: 4, to: 5, insert: '2' } }));
  expect(screen.getByText('Nespremljene izmjene')).toBeTruthy();
  await userEvent.click(save);
  await screen.findByText('Spremljeno');
  act(() => editor.dispatch({ changes: { from: 4, to: 5, insert: '3' } }));
  await userEvent.click(save);
  await waitFor(() => expect(sent.filter((each) => each.method === 'POST')).toHaveLength(2));
  expect(sent.filter((each) => each.method === 'POST').map((each) => each.body)).toEqual([
    { folder: FOLDER, path: 'backend/app.py', text: 'x = 2\n', hash: HASH },
    { folder: FOLDER, path: 'backend/app.py', text: 'x = 3\n', hash: NEWER },
  ]);
});

test('a file changed on the disk meanwhile is not written over unless the owner says so', async () => {
  const editor = await opened();
  written = () => Response.json({ error: 'changed' }, { status: 409 });
  act(() => editor.dispatch({ changes: { from: 4, to: 5, insert: '2' } }));
  await userEvent.click(screen.getByRole('button', { name: 'Spremi' }));
  expect((await screen.findByRole('alert')).textContent).toContain(
    'Datoteka se na disku promijenila otkad ste je otvorili.',
  );
  FILES['backend/app.py'] = {
    ...(FILES['backend/app.py'] as object),
    text: 'y = 1\n',
    hash: NEWER,
  };
  await userEvent.click(screen.getByRole('button', { name: 'Učitaj s diska' }));
  await waitFor(() => expect(editor.state.doc.toString()).toBe('y = 1\n'));
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.getByRole('button', { name: 'Spremi' })).toHaveProperty('disabled', true);
});

test('a host chosen in the place menu shows its files, and its file is saved with the host beside the path', async () => {
  shown();
  await screen.findByRole('button', { name: 'backend' });
  await userEvent.click(screen.getByRole('button', { name: 'Mjesto: Ponistra' }));
  await userEvent.click(await screen.findByRole('menuitemradio', { name: 'mlaka' }));
  await userEvent.click(await screen.findByRole('button', { name: 'app.conf' }));
  expect(
    sent.find((each) => each.url.startsWith('/api/workspace/files?') && each.url.includes('host')),
  ).toMatchObject({ url: '/api/workspace/files?host=mlaka&path=' });
  await waitFor(() => expect(document.querySelector('.cm-editor')).not.toBeNull());
  const editor = EditorView.findFromDOM(document.querySelector<HTMLElement>('.cm-editor')!)!;
  act(() => editor.dispatch({ changes: { from: 0, to: 1, insert: 'z' } }));
  await userEvent.click(screen.getByRole('button', { name: 'Spremi' }));
  await waitFor(() =>
    expect(sent.find((each) => each.method === 'POST')?.body).toEqual({
      host: 'mlaka',
      path: 'app.conf',
      text: 'z = 1\n',
      hash: HASH,
    }),
  );
});

test('a host that refuses the key says so where its files would be', async () => {
  onHost = () => Response.json({ error: 'ssh_key_refused' }, { status: 409 });
  shown();
  await userEvent.click(await screen.findByRole('button', { name: 'Mjesto: Ponistra' }));
  await userEvent.click(await screen.findByRole('menuitemradio', { name: 'mlaka' }));
  expect(
    await screen.findByText('Host je odbio ključ: javni ključ nije u authorized_keys na hostu.'),
  ).toBeTruthy();
});

test('a host is added from the hosts, where the public key waits to be copied', async () => {
  shown();
  await userEvent.click(await screen.findByRole('button', { name: 'Mjesto: Ponistra' }));
  await userEvent.click(await screen.findByRole('menuitem', { name: 'Hostovi' }));
  expect((await screen.findByLabelText('Javni ključ ponistra_ed25519')).textContent).toBe(
    'ssh-ed25519 AAAAC3Nza ponistra@example.org',
  );
  expect(screen.queryByRole('textbox')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Dodaj host' }));
  const dialog = await screen.findByRole('dialog');
  await userEvent.type(within(dialog).getByLabelText('Naziv'), 'dev');
  await userEvent.type(within(dialog).getByLabelText('Adresa'), '192.0.2.12');
  await userEvent.type(within(dialog).getByLabelText('Korisnik'), 'bacinac');
  await userEvent.type(within(dialog).getByLabelText('Početna mapa'), '/mnt/docker');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Dodaj host' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(sent.find((each) => each.method === 'POST')?.body).toEqual({
    name: 'dev',
    address: '192.0.2.12',
    port: 22,
    user: 'bacinac',
    path: '/mnt/docker',
    key: 'ponistra_ed25519',
  });
  expect(await screen.findByText('dev')).toBeTruthy();
});
