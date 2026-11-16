import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { ApiError, deleteJson, getJson, postJson } from './api';
import { ConfirmDialog } from './dialogs';
import { useI18n } from './i18n';
import { Qr } from './phoneApp';
import { button, field, primaryButton } from './styles';
import { errorMessage } from './tree';

interface Kept {
  authenticator: boolean;
  confirmed_at: string | null;
}

interface Made {
  secret: string;
  uri: string;
}

const AUTHENTICATOR = ['authenticator'];

/** The secret as an app asks it typed: in groups of four. */
function grouped(secret: string): string {
  return secret.match(/.{1,4}/g)?.join(' ') ?? secret;
}

/** The user's authenticator app, the second factor of their sign-in with a password: added by
 * scanning its secret and typing its first code, and removed. */
export function Authenticator({ onAdded }: { onAdded?: () => void }) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const [made, setMade] = useState<Made | null>(null);
  const [code, setCode] = useState('');
  const [removing, setRemoving] = useState(false);
  const kept = useQuery({
    queryKey: AUTHENTICATOR,
    queryFn: () => getJson<Kept>('/api/authenticator'),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: AUTHENTICATOR });
  const begin = useMutation({
    mutationFn: () => postJson<Made>('/api/authenticator'),
    onSuccess: setMade,
  });
  const confirm = useMutation({
    mutationFn: () => postJson<Kept>('/api/authenticator/confirm', { code }),
    onSuccess: (confirmed) => {
      queryClient.setQueryData(AUTHENTICATOR, confirmed);
      setMade(null);
      setCode('');
      onAdded?.();
    },
    onError: () => setCode(''),
  });
  const remove = useMutation({
    mutationFn: () => deleteJson('/api/authenticator'),
    onSuccess: () => {
      setRemoving(false);
      refresh();
    },
  });
  const failure = kept.error ?? begin.error ?? remove.error;

  function submit(event: FormEvent) {
    event.preventDefault();
    confirm.mutate();
  }

  if (kept.data?.authenticator) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm">
          {t('authenticator.since')} {formatDate(kept.data.confirmed_at!)}
        </p>
        {failure && (
          <p className="text-sm text-danger">
            {failure instanceof ApiError && failure.code === 'last_factor'
              ? t('authenticator.last')
              : errorMessage(failure, t)}
          </p>
        )}
        <div className="flex justify-end">
          <button type="button" onClick={() => setRemoving(true)} className={button}>
            {t('authenticator.remove')}
          </button>
        </div>
        {removing && (
          <ConfirmDialog
            heading={t('authenticator.removeTitle')}
            confirmLabel={t('authenticator.remove')}
            onConfirm={() => remove.mutate()}
            onClose={() => setRemoving(false)}
          >
            {t('authenticator.removeWarning')}
          </ConfirmDialog>
        )}
      </div>
    );
  }

  if (made) {
    return (
      <form onSubmit={submit} className="flex flex-col gap-3">
        <p className="text-sm">{t('authenticator.scan')}</p>
        <Qr text={made.uri} label={t('authenticator.qr')} />
        <p className="font-mono text-sm break-all select-all">{grouped(made.secret)}</p>
        <label className="flex flex-col gap-1 text-sm sm:max-w-xs">
          {t('authenticator.code')}
          <input
            required
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9 ]{6,7}"
            maxLength={7}
            value={code}
            onChange={(event) => setCode(event.target.value)}
            className={field}
          />
        </label>
        {confirm.isError && (
          <p className="text-sm text-danger">
            {confirm.error instanceof ApiError && confirm.error.code === 'invalid_code'
              ? t('authenticator.invalid')
              : errorMessage(confirm.error, t)}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={() => setMade(null)} className={button}>
            {t('tree.cancel')}
          </button>
          <button type="submit" disabled={confirm.isPending} className={primaryButton}>
            {t('authenticator.confirm')}
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {kept.isSuccess && (
        <div className="flex justify-end">
          <button
            type="button"
            disabled={begin.isPending}
            onClick={() => begin.mutate()}
            className={primaryButton}
          >
            {t('authenticator.add')}
          </button>
        </div>
      )}
    </div>
  );
}
