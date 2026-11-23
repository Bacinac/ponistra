// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { FileBrowser, type FileEntry, type FileSource } from './files';
import { I18nProvider } from './i18n';

const HASH = 'a'.repeat(64);

let kept: Record<string, FileEntry[]>;
let calls: unknown[][];

/** The live socket held connecting, so the browser counts the server as reachable. */
class Connecting extends EventTarget {
  readonly readyState = 0;
  close(): void {}
  send(): void {}
}

function source(writable = true): FileSource {
  const noted =
    (name: string) =>
    (...given: unknown[]) => {
      calls.push([name, ...given]);
      return Promise.resolve();
    };
  return {
    key: 'fake',
    name: 'Arhiva',
    writable,
    list: (path) => Promise.resolve({ path, entries: kept[path] ?? [] }),
    rawHref: (path, download) => `/raw/${path}${download ? '?download=1' : ''}`,
    read: (path) =>
      Promise.resolve({ path, size: 3, modified: '', kind: 'binary', text: null, hash: HASH }),
    write: (path) => Promise.resolve({ path, size: 3, modified: '', hash: HASH }),
    folder: noted('folder'),
    rename: noted('rename'),
    remove: noted('remove'),
    put: noted('put'),
  };
}

function Shown({ from }: { from: FileSource }) {
  const [at, setAt] = useState<{ path: string; file: string | null }>({ path: '', file: null });
  return (
    <FileBrowser
      source={from}
      path={at.path}
      file={at.file}
      onGo={(path, file) => setAt({ path, file: file ?? null })}
      frame={({ title, actions, primary, panel, children }) => (
        <div>
          <h1>{title}</h1>
          {actions}
          {primary}
          {children}
          {panel}
        </div>
      )}
    />
  );
}

function shown(from: FileSource) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <MemoryRouter>
          <Shown from={from} />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const row = async (name: string) =>
  (await screen.findByText(name, undefined, { timeout: 5000 })).closest('tr')!;

beforeEach(() => {
  calls = [];
  kept = {
    '': [
      { name: 'zapis.bin', kind: 'file', size: 2400, modified: '2026-11-16T00:00:00Z' },
      { name: 'Ponude', kind: 'folder', size: null, modified: '2026-11-16T00:00:00Z' },
    ],
    Ponude: [{ name: 'ponuda.bin', kind: 'file', size: 6, modified: '2026-11-16T00:00:00Z' }],
  };
  localStorage.clear();
  vi.stubGlobal('WebSocket', Connecting);
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test('a source is listed folders first, a folder opens on a click and a file in the place of the list', async () => {
  shown(source());
  await row('Ponude');
  const names = [...document.querySelectorAll('tr[data-name]')].map((each) =>
    each.getAttribute('data-name'),
  );
  expect(names).toEqual(['Ponude', 'zapis.bin']);
  await userEvent.click(await row('Ponude'));
  await userEvent.click(await row('ponuda.bin'));
  const link = await screen.findByRole('link', { name: 'Preuzmi' });
  expect(link.getAttribute('href')).toBe('/raw/Ponude/ponuda.bin?download=1');
});

test('a rename and a delete go to the source with the paths of the folder shown', async () => {
  shown(source());
  await userEvent.click(await row('Ponude'));
  fireEvent.contextMenu(await row('ponuda.bin'));
  await userEvent.click(await screen.findByRole('menuitem', { name: 'Preimenuj' }));
  const name = within(await screen.findByRole('dialog')).getByRole('textbox');
  await userEvent.clear(name);
  await userEvent.type(name, 'stara.bin');
  await userEvent.click(screen.getByRole('button', { name: 'Spremi' }));
  await waitFor(() =>
    expect(calls).toContainEqual(['rename', 'Ponude/ponuda.bin', 'Ponude/stara.bin']),
  );

  fireEvent.contextMenu(await row('ponuda.bin'));
  await userEvent.click(await screen.findByRole('menuitem', { name: 'Obriši' }));
  await userEvent.click(
    within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Obriši' }),
  );
  await waitFor(() => expect(calls).toContainEqual(['remove', ['Ponude/ponuda.bin']]));
});

test('a source that is only read has what changes it disabled', async () => {
  shown(source(false));
  fireEvent.contextMenu(await row('zapis.bin'));
  await screen.findByRole('menuitem', { name: 'Preuzmi' });
  for (const name of ['Preimenuj', 'Obriši'])
    expect(screen.getByRole('menuitem', { name }).getAttribute('aria-disabled')).toBe('true');
  expect(screen.getByRole('button', { name: 'Novo' })).toHaveProperty('disabled', true);
});

test('a folder or the rows chosen are saved as one zip, what a file holds is shown', async () => {
  const saved: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push(this.getAttribute('href')!);
  });
  const asked: string[] = [];
  vi.stubGlobal('fetch', (url: string) => {
    asked.push(url);
    return Promise.resolve(
      new Response(
        JSON.stringify({
          kind: 'archive',
          count: 1,
          entries: [{ n: 0, path: 'ugovor.pdf', size: 3, modified: null, folder: false }],
        }),
        { headers: { 'Content-Type': 'application/json' } },
      ),
    );
  });
  kept[''].push({ name: 'paket.zip', kind: 'file', size: 9, modified: null });
  shown({
    ...source(),
    heldBase: (path) => `/held/${path}`,
    zipHref: (paths) => `/zip?${paths.join('&')}`,
  });
  fireEvent.contextMenu(await row('Ponude'));
  await userEvent.click(await screen.findByRole('menuitem', { name: 'Preuzmi kao ZIP' }));
  expect(saved).toEqual(['/zip?Ponude']);

  fireEvent.contextMenu(document.querySelector('nav')!);
  await userEvent.click(await screen.findByRole('menuitem', { name: 'Preuzmi mapu kao ZIP' }));
  expect(saved).toEqual(['/zip?Ponude', '/zip?']);

  await userEvent.dblClick(await row('paket.zip'));
  expect(await screen.findByText('ugovor.pdf')).toBeTruthy();
  expect(asked).toContain('/held/paket.zip/shown');
});
