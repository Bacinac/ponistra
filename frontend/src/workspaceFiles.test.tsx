// @vitest-environment jsdom
import { EditorView } from '@codemirror/view';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
      { name: 'data.bin', kind: 'file', size: 2400, modified: '2026-11-16T00:00:00Z' },
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
  'data.bin': {
    path: 'data.bin',
    size: 2400,
    modified: '2026-11-16T00:00:00Z',
    kind: 'binary',
    text: null,
    hash: HASH,
  },
};

const sent: { method: string; url: string; body: Record<string, unknown> | null }[] = [];
let written: () => Response;

beforeEach(() => {
  sent.length = 0;
  localStorage.clear();
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
  written = () => Response.json({ path: 'backend/app.py', size: 6, modified: '', hash: NEWER });
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET';
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      sent.push({ method, url, body });
      const asked = new URL(url, 'http://ponistra').searchParams.get('path') ?? '';
      if (url === '/api/workspace/file' && method === 'POST') return Promise.resolve(written());
      if (method === 'POST') return Promise.resolve(Response.json({ path: 'x' }, { status: 201 }));
      if (url.startsWith('/api/workspace/files?'))
        return Promise.resolve(Response.json(LISTS[asked]));
      return Promise.resolve(Response.json(FILES[asked]));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function shown(onClose = () => {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <FilesPanel folder={FOLDER} name="Ponistra" onDirty={() => {}} onClose={onClose} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const row = async (name: string) =>
  (await screen.findByText(name, undefined, { timeout: 5000 })).closest('tr')!;

async function opened() {
  shown();
  await userEvent.click(await row('backend'));
  await userEvent.click(await row('app.py'));
  await waitFor(() => expect(document.querySelector('.cm-editor')).not.toBeNull());
  return EditorView.findFromDOM(document.querySelector<HTMLElement>('.cm-editor')!)!;
}

const q = (path: string) => `folder=${encodeURIComponent(FOLDER)}&path=${encodeURIComponent(path)}`;

test("the project's folder is listed through the workspace in the browser of Documents", async () => {
  shown();
  await row('backend');
  const names = [...document.querySelectorAll('tr[data-name]')].map((each) =>
    each.getAttribute('data-name'),
  );
  expect(names).toEqual(['backend', 'away', 'data.bin', 'logo.png']);
  expect(sent[0].url).toBe(`/api/workspace/files?${q('')}`);
});

test('a picture opens in a tab of its own and a file that is not text is only downloaded', async () => {
  const opening = vi.fn();
  vi.stubGlobal('open', opening);
  shown();
  await userEvent.click(await row('logo.png'));
  expect(opening).toHaveBeenCalledWith(
    `/api/workspace/file/raw?${q('logo.png')}`,
    '_blank',
    'noopener,noreferrer',
  );
  await userEvent.click(await row('data.bin'));
  const link = await screen.findByRole('link', { name: 'Preuzmi' });
  expect(link.getAttribute('href')).toBe(`/api/workspace/file/raw?${q('data.bin')}&download=1`);
  expect(screen.getByText('Datoteka nije tekst i može se samo preuzeti.')).toBeTruthy();
});

test('a folder made, an item renamed and deleted reach the project by its folder', async () => {
  shown();
  await row('backend');
  await userEvent.click(screen.getByRole('button', { name: 'Novo' }));
  await userEvent.click(await screen.findByRole('menuitem', { name: 'Nova mapa' }));
  await userEvent.type(within(await screen.findByRole('dialog')).getByRole('textbox'), 'docs');
  await userEvent.click(screen.getByRole('button', { name: 'Izradi' }));
  await waitFor(() =>
    expect(sent.find((each) => each.url === '/api/workspace/files/folder')?.body).toEqual({
      folder: FOLDER,
      path: '',
      name: 'docs',
    }),
  );

  fireEvent.contextMenu(await row('logo.png'));
  await userEvent.click(await screen.findByRole('menuitem', { name: 'Preimenuj' }));
  const name = within(await screen.findByRole('dialog')).getByRole('textbox');
  await userEvent.clear(name);
  await userEvent.type(name, 'brand.png');
  await userEvent.click(screen.getByRole('button', { name: 'Spremi' }));
  await waitFor(() =>
    expect(sent.find((each) => each.url === '/api/workspace/files/rename')?.body).toEqual({
      folder: FOLDER,
      path: 'logo.png',
      to: 'brand.png',
    }),
  );

  fireEvent.contextMenu(await row('logo.png'));
  await userEvent.click(await screen.findByRole('menuitem', { name: 'Obriši' }));
  await userEvent.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Obriši' }),
  );
  await waitFor(() =>
    expect(sent.find((each) => each.url === '/api/workspace/files/remove')?.body).toEqual({
      folder: FOLDER,
      paths: ['logo.png'],
    }),
  );
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
  const saved = () => sent.filter((each) => each.url === '/api/workspace/file');
  await waitFor(() => expect(saved()).toHaveLength(2));
  expect(saved().map((each) => each.body)).toEqual([
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

test('closing the files with a change unsaved asks first', async () => {
  const closed = vi.fn();
  shown(closed);
  await userEvent.click(await row('backend'));
  await userEvent.click(await row('app.py'));
  await waitFor(() => expect(document.querySelector('.cm-editor')).not.toBeNull());
  const editor = EditorView.findFromDOM(document.querySelector<HTMLElement>('.cm-editor')!)!;
  act(() => editor.dispatch({ changes: { from: 4, to: 5, insert: '2' } }));
  await userEvent.click(screen.getByRole('button', { name: 'Zatvori datoteke' }));
  const asked = await screen.findByRole('alertdialog');
  expect(closed).not.toHaveBeenCalled();
  await userEvent.click(within(asked).getByRole('button', { name: 'Odbaci' }));
  expect(closed).toHaveBeenCalledOnce();
});
