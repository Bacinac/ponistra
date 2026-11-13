import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Language } from './i18n';
import type { CallChoices } from './camera';
import type { PageTheme, Theme } from './theme';
import { Fingerprint, KeyRound, LogIn } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, getJson, patchJson, postJson, unavailable } from './api';
import { useI18n } from './i18n';
import {
  makePasskey,
  PASSKEYS,
  passkeyMessage,
  passkeyOffered,
  passkeySignIn,
  passkeysWork,
} from './passkeys';
import { button, field, primaryButton } from './styles';
import type { MessageKey } from './i18n/hr';
import { errorMessage } from './tree';

export interface User {
  id: number;
  email: string;
  name: string;
}

export interface Me extends User {
  is_admin: boolean;
  /** Someone outside the installation, in by a link of their own and reaching only what was
      shared with them (D39). */
  visitor: boolean;
  /** The installation's code workspace (D34) when the user holds it: here, behind PONISTRA's own
      door, or elsewhere at an address with a door of its own. */
  workspace: { url: string; here: boolean } | null;
  language: Language | '';
  theme: Theme | '';
  projects_theme: PageTheme | '';
  meetings_theme: PageTheme | '';
  sign_in: SignIn | '';
  /** What a call does with the camera and the microphone, what was never chosen left out. */
  call: Partial<CallChoices>;
  /** The user's own picture behind them in a call, by its bytes' SHA-256. */
  backdrop: string | null;
}

export interface Session {
  user: Me | null;
  /** Signed in with a password while the passkey policy holds the user, who has none yet. */
  passkey_due: boolean;
  setup: boolean;
  /** Where the installation is reached from outside, as its own links carry it. */
  site: string;
  /** The outside providers one may sign in at, offered while nobody is signed in (U1). */
  providers: Provider[];
}

export interface Provider {
  id: number;
  name: string;
}

const ANSWERED = 'sign_in';
const REFUSALS = [
  'no_account',
  'no_email',
  'outside_domains',
  'unverified_email',
  'inactive',
  'visitor',
  'unknown_attempt',
  'expired_attempt',
  'provider_refused',
  'provider_unreachable',
  'someone_else',
] as const;

/** Where a provider is asked who the user is, the browser coming back to `next`. */
export function providerStart(provider: Provider, next: string, confirm = false): string {
  const asked = new URLSearchParams({ next });
  if (confirm) asked.set('confirm', '1');
  return `/api/identity/providers/${provider.id}/start?${asked}`;
}

/** The refusal a provider's sign-in came back with. */
function answerOf(): string | null {
  return new URL(location.href).searchParams.get(ANSWERED);
}

function dropAnswer(): void {
  const address = new URL(location.href);
  if (!address.searchParams.has(ANSWERED)) return;
  address.searchParams.delete(ANSWERED);
  history.replaceState(history.state, '', address);
}

export function refusalText(code: string, t: (key: MessageKey) => string): string {
  const known = REFUSALS.find((each) => each === code);
  return t(known ? `auth.refused.${known}` : 'auth.refused');
}

export const SESSION_KEY = ['session'];
const AWAITED = 5000;

export type SignIn = 'password' | 'passkey';

const SIGN_IN_KEY = 'ponistra.signIn';

/** What the account chose to sign in with, which the browser holds for the sign-in page. */
export function keepSignIn(chosen: SignIn | ''): void {
  try {
    localStorage.setItem(SIGN_IN_KEY, chosen);
  } catch {
    return;
  }
}

function keptSignIn(): SignIn | '' {
  try {
    const kept = localStorage.getItem(SIGN_IN_KEY);
    return kept === 'password' || kept === 'passkey' ? kept : '';
  } catch {
    return '';
  }
}

/** Whether the one signed in came from outside, by a link (D39). */
export function useVisitor(): boolean {
  return Boolean(useSession().data?.user?.visitor);
}

export function useSession() {
  return useQuery({
    queryKey: SESSION_KEY,
    queryFn: () => getJson<Session>('/api/auth/session'),
    refetchInterval: (query) =>
      query.state.status === 'error' && unavailable(query.state.error) ? AWAITED : false,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postJson<Session>('/api/auth/logout'),
    onSuccess: (session) => {
      // clear() would take the session's query from under App, whose observer would stay on the
      // removed query and go on showing the page of the user who just left.
      queryClient.setQueryData(SESSION_KEY, session);
      queryClient.removeQueries({ predicate: ({ queryKey }) => queryKey[0] !== SESSION_KEY[0] });
      if ('clearAppBadge' in navigator) void navigator.clearAppBadge();
    },
  });
}

export function LoginForm() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [leading, setLeading] = useState(keptSignIn);
  const [refused, setRefused] = useState<Error | null>(null);
  const [offers, setOffers] = useState(0);
  const [answered] = useState(answerOf);
  const providers = useSession().data?.providers ?? [];
  const offer = useRef<AbortController | null>(null);
  // The server keeps one challenge a session, so the options of an offer being withdrawn must land
  // before those of what follows it.
  const offerOver = useRef<Promise<void>>(Promise.resolve());
  const login = useMutation({
    mutationFn: () => postJson<Session>('/api/auth/login', { email, password }),
    onSuccess: (session) => queryClient.setQueryData(SESSION_KEY, session),
  });
  const passkey = useMutation({
    mutationFn: async () => {
      offer.current?.abort();
      await offerOver.current;
      return passkeySignIn<Session>();
    },
    onSuccess: (session) => queryClient.setQueryData(SESSION_KEY, session),
    onError: (error) => {
      setRefused(error);
      setOffers((count) => count + 1);
    },
  });
  const failure = login.error instanceof ApiError ? login.error.code : undefined;
  const passkeyFirst = passkeysWork && leading === 'passkey';
  const offered = passkeysWork && !leading;

  useEffect(() => {
    if (!offered) return;
    const withdrawn = new AbortController();
    const began = Date.now();
    offer.current = withdrawn;
    offerOver.current = offerOver.current
      .then(() => passkeyOffered<Session>(withdrawn.signal))
      .then((session) => {
        if (session) queryClient.setQueryData(SESSION_KEY, session);
      })
      .catch((error: Error) => {
        if (withdrawn.signal.aborted) return;
        setRefused(error);
        // An offer that failed at once would only fail again, as fast as it could ask.
        if (Date.now() - began > 1000) setOffers((count) => count + 1);
      });
    return () => withdrawn.abort();
  }, [offered, offers, queryClient]);

  useEffect(dropAnswer, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    setRefused(null);
    login.mutate();
  }

  return (
    <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3">
      <h2 className="text-lg font-semibold">{t('auth.title')}</h2>
      {!passkeyFirst && (
        <>
          <label className="flex flex-col gap-1 text-sm">
            {t('auth.email')}
            <input
              type="email"
              autoComplete={offered ? 'username webauthn' : 'username'}
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t('auth.password')}
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={field}
            />
          </label>
          {login.isError && (
            <p className="text-sm text-danger">
              {failure === 'invalid_credentials'
                ? t('auth.invalid')
                : failure === 'locked_out'
                  ? t('auth.locked')
                  : errorMessage(login.error, t)}
            </p>
          )}
          <button
            type="submit"
            disabled={login.isPending}
            className={`${primaryButton} justify-center py-2 text-base`}
          >
            {login.isPending ? t('auth.signingIn') : t('auth.signIn')}
          </button>
        </>
      )}
      {passkeysWork && (
        <button
          type="button"
          disabled={passkey.isPending}
          onClick={() => {
            login.reset();
            setRefused(null);
            passkey.mutate();
          }}
          className={
            passkeyFirst
              ? `${primaryButton} justify-center py-2 text-base`
              : `${button} justify-center py-2 text-base`
          }
        >
          <Fingerprint size={18} aria-hidden />
          {t('auth.passkey')}
        </button>
      )}
      {passkeyFirst && (
        <button
          type="button"
          onClick={() => {
            setRefused(null);
            setLeading('');
          }}
          className={`${button} justify-center py-2 text-base`}
        >
          <KeyRound size={18} aria-hidden />
          {t('auth.withPassword')}
        </button>
      )}
      {providers.map((provider) => (
        <button
          key={provider.id}
          type="button"
          aria-label={`${t('auth.signInAt')}: ${provider.name}`}
          onClick={() =>
            location.assign(providerStart(provider, location.pathname + location.search))
          }
          className={`${button} justify-center py-2 text-base`}
        >
          <LogIn size={18} aria-hidden />
          {provider.name}
        </button>
      ))}
      {refused && <p className="text-sm text-danger">{passkeyMessage(refused, t)}</p>}
      {answered && <p className="text-sm text-danger">{refusalText(answered, t)}</p>}
    </form>
  );
}

/** The way of signing in the sign-in page leads with on the user's devices: a page of the
 * settings. */
export function SignInChoice() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const chosen = useSession().data?.user?.sign_in ?? '';
  const kept = useQuery({
    queryKey: PASSKEYS,
    queryFn: () => getJson<{ passkeys: unknown[] }>('/api/passkeys'),
  });
  const choose = useMutation({
    mutationFn: (sign_in: SignIn | '') => patchJson<Session>('/api/auth/preferences', { sign_in }),
    onSuccess: (session) => queryClient.setQueryData(SESSION_KEY, session),
  });
  return (
    <>
      <label className="flex flex-col gap-1 text-sm sm:max-w-xs">
        {t('signIn.choice')}
        <select
          value={chosen}
          disabled={choose.isPending}
          onChange={(event) => choose.mutate(event.target.value as SignIn | '')}
          className={field}
        >
          <option value="">{t('signIn.none')}</option>
          <option value="password">{t('password.title')}</option>
          <option value="passkey" disabled={!kept.data?.passkeys.length}>
            {t('signIn.passkey')}
          </option>
        </select>
      </label>
      {choose.isError && <p className="text-sm text-danger">{errorMessage(choose.error, t)}</p>}
    </>
  );
}

/** The one thing a user the passkey policy holds can do until they have a passkey. */
export function PasskeyDue() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const logout = useLogout();
  const [name, setName] = useState('');
  const add = useMutation({
    mutationFn: () => makePasskey(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SESSION_KEY }),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    add.mutate();
  }

  return (
    <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3">
      <h2 className="text-lg font-semibold">{t('passkeys.dueTitle')}</h2>
      <p className="text-sm">{t('passkeys.due')}</p>
      {passkeysWork ? (
        <label className="flex flex-col gap-1 text-sm">
          {t('passkeys.newName')}
          <input
            required
            maxLength={150}
            value={name}
            onChange={(event) => setName(event.target.value)}
            className={field}
          />
        </label>
      ) : (
        <p className="text-sm text-danger">{t('passkeys.unsupported')}</p>
      )}
      {add.isError && <p className="text-sm text-danger">{passkeyMessage(add.error, t)}</p>}
      {logout.isError && <p className="text-sm text-danger">{errorMessage(logout.error, t)}</p>}
      {passkeysWork && (
        <button
          type="submit"
          disabled={add.isPending}
          className={`${primaryButton} justify-center py-2 text-base`}
        >
          <Fingerprint size={18} aria-hidden />
          {t(add.isPending ? 'passkeys.adding' : 'passkeys.add')}
        </button>
      )}
      <button
        type="button"
        disabled={logout.isPending}
        onClick={() => logout.mutate()}
        className={`${button} justify-center py-2 text-base`}
      >
        {t('auth.signOut')}
      </button>
    </form>
  );
}

export function SetupForm() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    code: '',
    first_name: '',
    last_name: '',
    email: '',
    password: '',
  });
  const setup = useMutation({
    mutationFn: () => postJson<Session>('/api/setup', form),
    onSuccess: (session) => queryClient.setQueryData(SESSION_KEY, session),
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'already_set_up') {
        void queryClient.invalidateQueries({ queryKey: SESSION_KEY });
      }
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setup.mutate();
  }

  const text = (name: keyof typeof form, label: string, type: string, autoComplete?: string) => (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      <input
        type={type}
        autoComplete={autoComplete}
        required={name !== 'first_name' && name !== 'last_name'}
        maxLength={name === 'email' ? 254 : 150}
        value={form[name]}
        onChange={(event) => setForm({ ...form, [name]: event.target.value })}
        className={field}
      />
    </label>
  );

  return (
    <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3">
      <h2 className="text-lg font-semibold">{t('setup.title')}</h2>
      <p className="text-sm text-muted">{t('setup.intro')}</p>
      {text('code', t('setup.code'), 'text', 'one-time-code')}
      <div className="grid grid-cols-2 gap-3">
        {text('first_name', t('users.firstName'), 'text', 'given-name')}
        {text('last_name', t('users.lastName'), 'text', 'family-name')}
      </div>
      {text('email', t('auth.email'), 'email', 'username')}
      {text('password', t('auth.password'), 'password', 'new-password')}
      {setup.isError && <p className="text-sm text-danger">{errorMessage(setup.error, t)}</p>}
      <button
        type="submit"
        disabled={setup.isPending}
        className={`${primaryButton} justify-center py-2 text-base`}
      >
        {t('setup.submit')}
      </button>
    </form>
  );
}

/** The change of the user's password, a page of the settings. */
export function PasswordForm() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [password, setPassword] = useState('');
  const change = useMutation({
    mutationFn: () => postJson<Session>('/api/auth/password', { password }),
    onSuccess: (session) => {
      queryClient.setQueryData(SESSION_KEY, session);
      setPassword('');
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    change.mutate();
  }

  return (
    <form onSubmit={submit} className="flex w-full max-w-md flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm">
        {t('password.new')}
        <input
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={field}
        />
      </label>
      {change.isError && <p className="text-sm text-danger">{errorMessage(change.error, t)}</p>}
      {change.isSuccess && <p className="text-sm text-muted">{t('password.changed')}</p>}
      <div className="flex justify-end">
        <button type="submit" disabled={change.isPending} className={primaryButton}>
          {t('password.change')}
        </button>
      </div>
    </form>
  );
}
