// @vitest-environment jsdom
import { screen, waitFor, within } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

const NAS = '5d2f0c4e-1a7b-4c3d-9e8f-0a1b2c3d4e5f';
const FAR = '7e6d5c4b-3a29-4180-9f7e-6d5c4b3a2918';
const OWNER = { id: 1, name: 'Ivo Ivić' };

const location = (id: string, name: string, kind: string, address: string) => ({
  id,
  name,
  kind,
  address,
  role: 'own',
  owner: OWNER,
  tunnel: null,
});

const FOLDERS: Record<string, { name: string; kind: string }[]> = {
  '': [
    { name: 'Ponude', kind: 'folder' },
    { name: 'popis.txt', kind: 'file' },
  ],
  Ponude: [{ name: '2026', kind: 'folder' }],
  'Ponude/2026': [],
};

test('Network opens in the tree as a folder: locations below it, their folders read as a branch opens', async () => {
  const asked: string[] = [];
  serve({
    'GET /api/locations': () => ({
      locations: [
        location(NAS, 'Arhiva', 'smb', '\\\\nas\\arhiva'),
        location(FAR, 'Poslužitelj', 'sftp', 'far:files'),
      ],
      adds: true,
      tunnels: [],
    }),
    'GET /api/locations/:id/files': (request, { id }) => {
      const path = new URL(request.url).searchParams.get('path') ?? '';
      asked.push(`${id === NAS ? 'nas' : 'far'}:${path}`);
      if (id === FAR) return Response.json({ error: 'location_unreachable' }, { status: 409 });
      const entries = (FOLDERS[path] ?? []).map((entry) => ({
        ...entry,
        size: entry.kind === 'file' ? 3 : null,
        modified: null,
      }));
      return { path, entries };
    },
  });
  const { user, router, settled } = open('/locations');
  await settled();
  let tree = screen.getByRole('navigation', { name: 'Mape' });
  expect(within(tree).getByRole('link', { name: 'Mreža' }).getAttribute('aria-current')).toBe(
    'page',
  );
  await within(tree).findByRole('link', { name: 'Arhiva' });
  expect(within(tree).getByRole('link', { name: 'Poslužitelj' })).toBeTruthy();
  expect(asked).toEqual([]);

  const row = (name: string) => within(tree).getByRole('link', { name }).parentElement!;
  await user.click(within(row('Arhiva')).getByRole('button', { name: 'Proširi' }));
  await user.click(await within(tree).findByRole('link', { name: 'Ponude' }));
  await waitFor(() =>
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe(
      `/locations/${NAS}?path=Ponude`,
    ),
  );
  await settled();
  tree = screen.getByRole('navigation', { name: 'Mape' });
  expect(within(tree).getByRole('link', { name: 'Ponude' }).getAttribute('aria-current')).toBe(
    'page',
  );
  expect(within(tree).getByRole('link', { name: 'Mreža' }).getAttribute('aria-current')).toBeNull();
  expect(within(tree).getByRole('link', { name: '2026' })).toBeTruthy();
  expect(within(tree).queryByRole('link', { name: 'popis.txt' })).toBeNull();
  expect(within(row('2026')).queryByRole('button', { name: 'Proširi' })).toBeTruthy();
  await user.click(within(row('2026')).getByRole('button', { name: 'Proširi' }));
  await settled();
  expect(within(row('2026')).queryByRole('button')).toBeNull();

  await user.click(within(row('Poslužitelj')).getByRole('button', { name: 'Proširi' }));
  expect(await within(tree).findByText('Poslužitelj nije dostupan.')).toBeTruthy();
  expect(within(tree).getByRole('link', { name: 'Ponude' })).toBeTruthy();

  await user.click(within(row('Mreža')).getByRole('button', { name: 'Sažmi' }));
  expect(within(tree).queryByRole('link', { name: 'Arhiva' })).toBeNull();
});
