// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

const { get } = vi.hoisted(() => {
  const get = vi.fn();
  vi.stubGlobal('PublicKeyCredential', {
    parseRequestOptionsFromJSON: (options: unknown) => options,
    isConditionalMediationAvailable: () => Promise.resolve(true),
  });
  return { get };
});

import { LoginForm, providerStart, SESSION_KEY, SignInChoice, type Session } from './auth';
import { I18nProvider } from './i18n';

function pending(request: CredentialRequestOptions) {
  return new Promise((_, reject) => {
    request.signal?.addEventListener('abort', () =>
      reject(new DOMException('withdrawn', 'AbortError')),
    );
  });
}

const SIGNED_OUT = {
  user: null,
  due: null,
  setup: false,
  site: '',
  passkeys: true,
  second_factor: null,
  providers: [],
} satisfies Session;

function signIn(chosen: string, session: Partial<Session> = {}) {
  localStorage.setItem('ponistra.signIn', chosen);
  localStorage.setItem('ponistra.language', 'hr');
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
  client.setQueryData(SESSION_KEY, { ...SIGNED_OUT, ...session });
  render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <LoginForm />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  get.mockReset();
  get.mockImplementation(pending);
  vi.stubGlobal('navigator', Object.assign(navigator, { credentials: { get } }));
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(Response.json({ challenge: 'c' }))),
  );
});

afterEach(cleanup);

const passkey = () => screen.getByRole('button', { name: 'Prijavi se pristupnim ključem' });

test('with no choice the page offers both, the passkey also under the email field', async () => {
  signIn('');
  expect(screen.getByLabelText('E-pošta')).toHaveProperty('autocomplete', 'username webauthn');
  expect(screen.getByRole('button', { name: 'Prijavi se' })).toBeTruthy();
  expect(passkey()).toBeTruthy();
  await waitFor(() =>
    expect(get).toHaveBeenCalledWith(expect.objectContaining({ mediation: 'conditional' })),
  );
});

test('a chosen password is all the page offers', async () => {
  signIn('password');
  expect(screen.getByLabelText('E-pošta')).toHaveProperty('autocomplete', 'username');
  expect(screen.queryByRole('button', { name: 'Prijavi se pristupnim ključem' })).toBeNull();
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(get).not.toHaveBeenCalled();
});

test('a chosen passkey leads, without asking until pressed, the password a click away', async () => {
  signIn('passkey');
  expect(screen.queryByLabelText('E-pošta')).toBeNull();
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(get).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Prijavi se lozinkom' }));
  expect(screen.getByLabelText('Lozinka')).toBeTruthy();
});

test('the button withdraws the offer before it asks', async () => {
  signIn('');
  await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  const offered = get.mock.calls[0][0] as CredentialRequestOptions;
  await userEvent.click(passkey());
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  expect(offered.signal?.aborted).toBe(true);
  expect(get.mock.calls[1][0]).not.toHaveProperty('mediation');
});

test('a passkey refused at once, as the platform refuses while it lets go of the offer, is asked once more', async () => {
  const credential = { toJSON: () => ({ id: 'k' }) };
  get
    .mockRejectedValueOnce(new DOMException('busy', 'NotAllowedError'))
    .mockResolvedValueOnce(credential);
  const sent: unknown[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith('/api/auth/passkey')) sent.push(JSON.parse(String(init?.body)));
      return Promise.resolve(Response.json({ challenge: 'c' }));
    }),
  );
  signIn('passkey');
  await userEvent.click(passkey());
  await waitFor(() => expect(sent).toEqual([{ credential: { id: 'k' } }]));
  expect(get).toHaveBeenCalledTimes(2);
});

test('where passkeys are off the page offers only the password', async () => {
  signIn('passkey', { passkeys: false });
  expect(screen.getByLabelText('E-pošta')).toHaveProperty('autocomplete', 'username');
  expect(screen.queryByRole('button', { name: 'Prijavi se pristupnim ključem' })).toBeNull();
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(get).not.toHaveBeenCalled();
});

test('a password the second factor holds asks for the code, and a wrong one says so', async () => {
  const sent: unknown[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((_: RequestInfo | URL, init?: RequestInit) => {
      sent.push(JSON.parse(String(init?.body)));
      return Promise.resolve(Response.json({ error: 'invalid_code' }, { status: 400 }));
    }),
  );
  signIn('', { second_factor: { code: true, passkey: false } });
  expect(screen.queryByLabelText('Lozinka')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Potvrdi pristupnim ključem' })).toBeNull();
  await userEvent.type(screen.getByLabelText('Kôd iz aplikacije za autentifikaciju'), '123456');
  await userEvent.click(screen.getByRole('button', { name: 'Prijavi se' }));
  expect(await screen.findByText('Kôd nije ispravan.')).toBeTruthy();
  expect(sent).toEqual([{ code: '123456' }]);
});

test('a passkey cannot be the choice of an account without one', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(Response.json({ passkeys: [] }))),
  );
  localStorage.setItem('ponistra.language', 'hr');
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } });
  client.setQueryData(SESSION_KEY, SIGNED_OUT);
  render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <SignInChoice />
      </I18nProvider>
    </QueryClientProvider>,
  );
  const option = screen.getByRole('option', { name: 'Pristupni ključ' });
  await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled());
  expect(option).toHaveProperty('disabled', true);
});

test('a sign-in at an outside provider starts there and tells what it came back with', async () => {
  history.replaceState(null, '', '/documents?sign_in=outside_domains');
  signIn('password', { providers: [{ id: 7, name: 'Entra' }] });

  expect(await screen.findByText('Adresa nije u domenama ovog izvora korisnika.')).toBeTruthy();
  expect(window.location.search).toBe('');
  expect(
    await screen.findByRole('button', { name: 'Prijava kod izdavatelja: Entra' }),
  ).toBeTruthy();
  expect(providerStart({ id: 7, name: 'Entra' }, '/documents')).toBe(
    '/api/identity/providers/7/start?next=%2Fdocuments',
  );
  vi.unstubAllGlobals();
});
