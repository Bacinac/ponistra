import { useMutation, useQuery } from '@tanstack/react-query';
import { Fingerprint, LogIn } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ApiError, getJson, onConfirm, postJson } from './api';
import { providerStart, refusalText, type Provider } from './auth';
import { Cancel, Modal } from './dialogs';
import { useI18n } from './i18n';
import { passkeyConfirm, passkeyMessage, passkeysWork } from './passkeys';
import { button, field, primaryButton } from './styles';
import { errorMessage } from './tree';

interface Ways {
  passkey: boolean;
  password: boolean;
  providers: Provider[];
}

const CONFIRMED = '/api/identity/confirmed';
const CLOSED = 'closed';
const BLOCKED = 'blocked';

/** The user shows who they are at the provider in a window of its own, so that what waits on
 * the confirmation here is still there to be sent again. */
function confirmAt(provider: Provider): Promise<void> {
  return new Promise((resolve, reject) => {
    const opened = window.open(
      providerStart(provider, CONFIRMED, true),
      'ponistra-confirm',
      'popup,width=520,height=720',
    );
    if (!opened) {
      reject(new Error(BLOCKED));
      return;
    }
    const watching = setInterval(() => {
      if (opened.closed) {
        clearInterval(watching);
        reject(new Error(CLOSED));
        return;
      }
      let back: URL;
      try {
        back = new URL(opened.location.href);
      } catch {
        return;
      }
      if (back.origin !== location.origin || back.pathname.startsWith('/api/identity/providers/'))
        return;
      clearInterval(watching);
      opened.close();
      const refused = back.searchParams.get('sign_in');
      if (refused) reject(new Error(refused));
      else resolve();
    }, 250);
  });
}

/** Where the user shows again who they are when the backend asks it before what it was asked
 * (D33): each request waiting on it is sent again once they have, and refused if they close it. */
export function Confirmation() {
  const waiting = useRef<((confirmed: boolean) => void)[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(
    () =>
      onConfirm(
        () =>
          new Promise<boolean>((resolve) => {
            waiting.current.push(resolve);
            setOpen(true);
          }),
      ),
    [],
  );

  function settle(confirmed: boolean) {
    setOpen(false);
    for (const resolve of waiting.current.splice(0)) resolve(confirmed);
  }

  return open && <Asking onDone={() => settle(true)} onClose={() => settle(false)} />;
}

function Asking({ onDone, onClose }: { onDone: () => void; onClose: () => void }) {
  const { t } = useI18n();
  const [password, setPassword] = useState('');
  const ways = useQuery({
    queryKey: ['confirm'],
    queryFn: () => getJson<Ways>('/api/auth/confirm'),
  });
  const byPasskey = useMutation({ mutationFn: passkeyConfirm, onSuccess: onDone });
  const byProvider = useMutation({ mutationFn: confirmAt, onSuccess: onDone });
  const providers = ways.data?.providers ?? [];
  const providerFailure = byProvider.error?.message;
  const byPassword = useMutation({
    mutationFn: () => postJson('/api/auth/confirm', { password }),
    onSuccess: onDone,
  });
  const passkey = !!ways.data?.passkey && passkeysWork;

  function submit(event: FormEvent) {
    event.preventDefault();
    byPassword.mutate();
  }

  return (
    <Modal heading={t('confirm.title')} onClose={onClose}>
      {ways.isError && <p className="text-sm text-danger">{errorMessage(ways.error, t)}</p>}
      {passkey && (
        <button
          type="button"
          disabled={byPasskey.isPending}
          onClick={() => byPasskey.mutate()}
          className={`${primaryButton} justify-center py-2`}
        >
          <Fingerprint size={18} aria-hidden />
          {t('confirm.passkey')}
        </button>
      )}
      {byPasskey.isError && (
        <p className="text-sm text-danger">{passkeyMessage(byPasskey.error, t)}</p>
      )}
      {providers.map((provider) => (
        <button
          key={provider.id}
          type="button"
          disabled={byProvider.isPending}
          aria-label={`${t('confirm.provider')}: ${provider.name}`}
          onClick={() => byProvider.mutate(provider)}
          className={`${passkey ? button : primaryButton} justify-center py-2`}
        >
          <LogIn size={18} aria-hidden />
          {provider.name}
        </button>
      ))}
      {providerFailure && providerFailure !== CLOSED && (
        <p className="text-sm text-danger">
          {providerFailure === BLOCKED ? t('confirm.blocked') : refusalText(providerFailure, t)}
        </p>
      )}
      {ways.data?.password ? (
        <form onSubmit={submit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            {t('auth.password')}
            <input
              type="password"
              autoComplete="current-password"
              required
              autoFocus={!passkey}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={field}
            />
          </label>
          {byPassword.isError && (
            <p className="text-sm text-danger">
              {byPassword.error instanceof ApiError && byPassword.error.code === 'locked_out'
                ? t('auth.locked')
                : errorMessage(byPassword.error, t)}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Cancel />
            <button type="submit" disabled={byPassword.isPending} className={primaryButton}>
              {t('confirm.submit')}
            </button>
          </div>
        </form>
      ) : (
        ways.isSuccess && (
          <>
            {!passkey && providers.length === 0 && (
              <p className="text-sm text-danger">{t('confirm.none')}</p>
            )}
            <div className="flex justify-end">
              <Cancel />
            </div>
          </>
        )
      )}
    </Modal>
  );
}
