// @vitest-environment jsdom
import { screen, waitFor } from '@testing-library/react';
import { expect, test } from 'vitest';
import { open, serve } from './testing';

const CONTENTS = {
  sections: [
    {
      id: 'mail',
      title: 'Pošta',
      articles: [{ id: 'mail/reading', title: 'Čitanje pošte', summary: 'Popis i poruka.' }],
    },
  ],
  screens: [{ path: '/mail/:folder?', article: 'mail/reading' }],
};
const ARTICLE = {
  id: 'mail/reading',
  title: 'Čitanje pošte',
  html: '<p>Pritisnite <kbd data-keys="Mod-/">x</kbd> u <a href="/mail">Pošti</a>.</p><p><img data-shot="mail-list" alt="Popis"></p>',
};

function help() {
  serve({
    'GET /api/help': () => CONTENTS,
    'GET /api/help/mail/reading': () => ARTICLE,
  });
}

test('the help lists its sections and opens an article', async () => {
  help();
  const { user, settled } = await open('/help');
  await settled();
  expect(await screen.findByText('Popis i poruka.')).toBeTruthy();
  await user.click(screen.getAllByRole('link', { name: 'Čitanje pošte' })[0]!);
  expect(await screen.findByRole('heading', { name: 'Čitanje pošte' })).toBeTruthy();
  expect(screen.getByAltText('Popis').getAttribute('src')).toMatch(
    /^\/help-shots\/mail-list\.hr\.(light|dark)\.webp$/,
  );
  expect(screen.getByText('Ctrl+/')).toBeTruthy();
});

test('a link in an article stays in the application', async () => {
  help();
  const { user, router } = await open('/help/mail/reading');
  await user.click(await screen.findByRole('link', { name: 'Pošti' }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/mail'));
});

test('from a screen the help opens on the article about it', async () => {
  help();
  const { router } = await open('/help?from=%2Fmail%2Finbox');
  await waitFor(() => expect(router.state.location.pathname).toBe('/help/mail/reading'));
});

test('from a screen without an article the help opens on its contents', async () => {
  help();
  const { router } = await open('/help?from=%2Ftrash');
  await waitFor(() => expect(router.state.location.search).toBe(''));
  expect(router.state.location.pathname).toBe('/help');
});

test('F1 opens the help from any page', async () => {
  help();
  const { user, router } = await open('/help/mail/reading');
  await screen.findByRole('link', { name: 'Pošti' });
  await user.keyboard('{F1}');
  await waitFor(() => expect(router.state.location.pathname).toBe('/help'));
});

test('the header opens the help from any page', async () => {
  help();
  const { user, router } = await open('/help/mail/reading');
  await screen.findByRole('link', { name: 'Pošti' });
  await user.click(screen.getByRole('button', { name: 'Pomoć' }));
  await waitFor(() => expect(router.state.location.pathname).toBe('/help'));
});
