import { QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { NavLink, Outlet } from 'react-router';
import { Brand } from '../Brand';
import { LANGUAGES, useI18n } from '../i18n';
import { button, field, primaryButton } from '../styles';
import { MachineContext, MachineError, machineApi, newMachineQueryClient, useMachine } from './api';
import { Failure } from './parts';
import { MACHINE_PAGES } from './routes';

/** The machine's own page: its sign-in, then its pages under one header. The session is the
 * agent's (`/api/session`), and every 401 brings the sign-in back in place of the page, which
 * returns once signed in. */
export function MachinePage() {
  const [client] = useState(newMachineQueryClient);
  return (
    <QueryClientProvider client={client}>
      <Session />
    </QueryClientProvider>
  );
}

type Signed = { name: string } | 'out' | 'unknown';

function Session() {
  const { t } = useI18n();
  const client = useQueryClient();
  const [signed, setSigned] = useState<Signed>('unknown');
  const [failed, setFailed] = useState<Error | null>(null);
  const api = useMemo(
    () =>
      machineApi('/api', () => {
        client.clear();
        setSigned('out');
      }),
    [client],
  );

  useEffect(() => {
    api
      .get<{ name: string }>('/session')
      .then(setSigned)
      .catch((error: Error) => {
        if (!(error instanceof MachineError && error.status === 401)) setFailed(error);
      });
  }, [api]);

  if (failed) {
    return (
      <main className="mx-auto max-w-md p-8">
        <Failure error={failed} />
      </main>
    );
  }
  if (signed === 'unknown') return <p className="p-8 text-sm text-muted">{t('machine.loading')}</p>;
  if (signed === 'out') return <SignIn signedIn={setSigned} />;
  return (
    <MachineContext value={api}>
      <Shell
        name={signed.name}
        signOut={() =>
          api.send('DELETE', '/session').finally(() => {
            client.clear();
            setSigned('out');
          })
        }
      />
    </MachineContext>
  );
}

function SignIn({ signedIn }: { signedIn: (session: { name: string }) => void }) {
  const { t } = useI18n();
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [until, setUntil] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const waiting = Math.max(0, Math.ceil((until - now) / 1000));

  useEffect(() => {
    if (until <= Date.now()) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [until]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setRefusal(null);
    try {
      const response = await fetch('/api/session', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, password }),
      });
      if (response.ok) {
        signedIn(await response.json());
        return;
      }
      if (response.status === 429) {
        const seconds = Number(response.headers.get('Retry-After')) || 60;
        setNow(Date.now());
        setUntil(Date.now() + seconds * 1000);
      } else if (response.status === 401) {
        setRefusal(t('machine.signIn.wrong'));
      } else if (response.status === 503) {
        setRefusal(t('machine.signIn.noAccount'));
      } else {
        const answer = await response.json().catch(() => null);
        setRefusal(answer?.error ?? response.statusText);
      }
    } catch (error) {
      setRefusal((error as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-4">
        <div className="mb-4 flex justify-center">
          <Brand />
        </div>
        <h1 className="text-lg font-semibold">{t('machine.signIn')}</h1>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t('machine.signIn.name')}</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="username"
            autoFocus
            required
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t('machine.signIn.password')}</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
            className={field}
          />
        </label>
        {refusal && (
          <p role="alert" className="text-sm text-danger">
            {refusal}
          </p>
        )}
        {waiting > 0 && (
          <p role="status" className="text-sm text-danger">
            {t('machine.signIn.wait').replace('{seconds}', String(waiting))}
          </p>
        )}
        <button type="submit" className={primaryButton} disabled={busy || waiting > 0}>
          {t('machine.signIn.submit')}
        </button>
        <Languages />
      </form>
    </main>
  );
}

function Languages() {
  const { t, language, setLanguage } = useI18n();
  return (
    <div role="group" aria-label={t('frame.language')} className="flex justify-center gap-1">
      {LANGUAGES.map((each) => (
        <button
          key={each}
          type="button"
          aria-pressed={language === each}
          onClick={() => setLanguage(each)}
          className="rounded px-2 py-1 text-xs text-muted uppercase hover:bg-hover aria-pressed:font-semibold aria-pressed:text-accent"
        >
          {each}
        </button>
      ))}
    </div>
  );
}

function Shell({ name, signOut }: { name: string; signOut: () => void }) {
  const { t } = useI18n();
  const machine = useMachine();
  const base = machine.data?.os.variant === 'base';
  const hostname = machine.data?.hostname;

  useEffect(() => {
    document.title = hostname ? `${hostname} – Ponistra` : 'Ponistra';
  }, [hostname]);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-line bg-panel px-4 py-2">
        <div className="flex items-center gap-3">
          <Brand compact />
          {hostname && <span className="text-sm font-semibold">{hostname}</span>}
        </div>
        <nav aria-label={t('machine.pages')} className="flex flex-1 flex-wrap gap-1">
          {MACHINE_PAGES.filter((page) => !page.base || base).map((page) => (
            <NavLink
              key={page.path}
              to={`/${page.path}`}
              end={page.path === ''}
              className="rounded px-3 py-1.5 text-sm hover:bg-hover aria-[current=page]:bg-selected aria-[current=page]:font-semibold aria-[current=page]:text-accent"
            >
              {t(page.label)}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <Languages />
          <span className="text-sm text-muted">{name}</span>
          <button type="button" className={button} onClick={signOut}>
            {t('machine.signOut')}
          </button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 p-4 md:p-6">
        <Failure error={machine.error} />
        <Outlet />
      </main>
    </div>
  );
}
