import { useMutation } from '@tanstack/react-query';
import { KeyRound } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useI18n } from '../i18n';
import { passkeyMessage, passkeysWork } from '../passkeys';
import { button, field, primaryButton } from '../styles';
import {
  NoPrf,
  withCode,
  withPasskey,
  withPassword,
  Wrong,
  type Unlocked,
  type VaultData,
} from './state';

type How = 'password' | 'code' | 'passkey';

/** The vault opened by its password, the code it was handed with, or a passkey. */
export function UnlockForm({
  vault,
  mode,
  onOpened,
}: {
  vault: VaultData;
  mode: 'password' | 'code';
  onOpened: (unlocked: Unlocked, how: How) => void;
}) {
  const { t } = useI18n();
  const [typed, setTyped] = useState('');
  const opening = useMutation({
    mutationFn: (how: How) =>
      how === 'password'
        ? withPassword(vault, typed)
        : how === 'code'
          ? withCode(vault, typed)
          : withPasskey(vault),
    onSuccess: onOpened,
  });
  const failure = (error: Error) => {
    if (error instanceof Wrong)
      return t(mode === 'code' ? 'vault.wrongCode' : 'vault.wrongPassword');
    if (error instanceof NoPrf) return t('vault.noPrf');
    return passkeyMessage(error, t);
  };

  function submit(event: FormEvent) {
    event.preventDefault();
    event.stopPropagation();
    opening.mutate(mode);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        {t(mode === 'code' ? 'vault.code' : 'vault.password.vault')}
        <input
          type={mode === 'code' ? 'text' : 'password'}
          autoComplete={mode === 'code' ? 'off' : 'current-password'}
          spellCheck={false}
          autoFocus
          required
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          className={`${field} ${mode === 'code' ? 'font-mono uppercase' : ''}`}
        />
      </label>
      {opening.isError && (
        <p role="alert" className="text-sm text-danger">
          {failure(opening.error)}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" disabled={opening.isPending} className={primaryButton}>
          {t('vault.unlock')}
        </button>
        {mode === 'password' && passkeysWork && vault.unlocks.length > 0 && (
          <button
            type="button"
            disabled={opening.isPending}
            onClick={() => opening.mutate('passkey')}
            className={button}
          >
            <KeyRound size={16} aria-hidden />
            {t('vault.withPasskey')}
          </button>
        )}
      </div>
    </form>
  );
}
