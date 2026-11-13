// @vitest-environment jsdom
import { act, cleanup, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { choosePageTheme, chooseTheme } from './theme';
import { open, serve } from './testing';

function answer(given: object) {
  return {
    user: {
      id: 1,
      email: 'a@b.c',
      name: 'A',
      is_admin: false,
      workspace: null,
      language: '',
      theme: '',
      projects_theme: '',
      meetings_theme: '',
      call: {},
      backdrop: null,
      ...given,
    },
    passkey_due: false,
    setup: false,
    site: '',
  };
}

function account(held?: Promise<void>) {
  const sent: object[] = [];
  serve({
    'PATCH /api/auth/preferences': async (request) => {
      const given = (await request.json()) as object;
      sent.push(given);
      if (held) await held;
      return answer(given);
    },
  });
  return sent;
}

beforeEach(() => {
  localStorage.clear();
  chooseTheme('system');
  choosePageTheme('projects', 'ponistra');
  choosePageTheme('meetings', 'ponistra');
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test('what the account keeps arrives on a browser that chose otherwise, and is not sent back', async () => {
  const sent = account();
  localStorage.setItem('ponistra.language', 'hr');
  const { settled } = open('/documents', { language: 'en', theme: 'dark' });
  await waitFor(() => expect(document.documentElement.lang).toBe('en'));
  await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
  await settled();
  expect(sent).toEqual([]);
});

test('an account that holds nothing takes what this browser chose, and nothing of a default', async () => {
  const sent = account();
  localStorage.setItem('ponistra.language', 'en');
  const { settled } = open('/documents');
  await waitFor(() => expect(sent).toEqual([{ language: 'en' }]));
  await settled();
  expect(sent).toEqual([{ language: 'en' }]);
});

test('a choice made while the one before it is on its way reaches the account, and stays', async () => {
  let release = () => {};
  const sent = account(new Promise<void>((resolve) => (release = resolve)));
  const { settled } = open('/documents', { theme: 'system' });
  act(() => chooseTheme('dark'));
  await waitFor(() => expect(sent).toEqual([{ theme: 'dark' }]));
  act(() => chooseTheme('light'));
  act(() => chooseTheme('system'));
  act(() => release());
  await waitFor(() => expect(sent).toEqual([{ theme: 'dark' }, { theme: 'system' }]));
  await settled();
  expect(document.documentElement.dataset.theme).toBeUndefined();
  expect(sent).toEqual([{ theme: 'dark' }, { theme: 'system' }]);
});

test('a choice is kept even where the account already seems to hold it', async () => {
  const sent: object[] = [];
  serve({
    'PATCH /api/auth/preferences': async (request) => {
      const given = (await request.json()) as object;
      sent.push(given);
      return sent.length === 1 ? new Response(null, { status: 503 }) : answer(given);
    },
  });
  const { settled } = open('/documents', { theme: 'system' });
  act(() => chooseTheme('dark'));
  await waitFor(() => expect(sent).toEqual([{ theme: 'dark' }]));
  await settled();
  act(() => chooseTheme('system'));
  await waitFor(() => expect(sent).toEqual([{ theme: 'dark' }, { theme: 'system' }]));
  await settled();
});

test('the themes of Projects and meetings are kept by the account as the theme is', async () => {
  const sent = account();
  const { settled } = open('/documents', { projects_theme: 'dark' });
  await waitFor(() => expect(localStorage.getItem('ponistra.theme.projects')).toBe('dark'));
  await settled();
  expect(document.documentElement.dataset.theme).toBeUndefined();
  act(() => choosePageTheme('meetings', 'light'));
  await waitFor(() => expect(sent).toEqual([{ meetings_theme: 'light' }]));
  await settled();
  expect(sent).toEqual([{ meetings_theme: 'light' }]);
});
