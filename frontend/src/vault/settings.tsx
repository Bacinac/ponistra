import { useMutation, useQueryClient } from '@tanstack/react-query';
import { KeyRound, RotateCcw, X } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { deleteJson } from '../api';
import { Close, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import { passkeyMessage, passkeysWork } from '../passkeys';
import { button, field, iconButton } from '../styles';
import { errorMessage } from '../tree';
import { CodeShown, NewPassword } from './parts';
import {
  addPasskey,
  IDLE_MINUTES,
  idleMinutes,
  keepIdle,
  MINE,
  NoPrf,
  renewCode,
  setPassword,
  shownCode,
  type Idle,
  type Unlocked,
  type VaultData,
} from './state';

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-t border-line pt-3">
      <h3 className="font-semibold">{title}</h3>
      {children}
    </section>
  );
}

export function SettingsDialog({
  vault,
  unlocked,
  onClose,
}: {
  vault: VaultData;
  unlocked: Unlocked;
  onClose: () => void;
}) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const kept = (changed: VaultData) => queryClient.setQueryData(MINE, changed);
  const [idle, setIdle] = useState<Idle>(idleMinutes);
  const [code, setCode] = useState<string | null>(null);
  const [passwordSet, setPasswordSet] = useState(false);
  const password = useMutation({
    mutationFn: (typed: string) => setPassword(unlocked, typed),
    onSuccess: (changed) => {
      kept(changed);
      setPasswordSet(true);
    },
  });
  const shown = useMutation({ mutationFn: () => shownCode(unlocked, vault), onSuccess: setCode });
  const renewed = useMutation({
    mutationFn: () => renewCode(unlocked),
    onSuccess: ({ vault: changed, code: made }) => {
      kept(changed);
      setCode(made);
    },
  });
  const passkey = useMutation({ mutationFn: () => addPasskey(unlocked), onSuccess: kept });
  const unhooked = useMutation({
    mutationFn: (id: number) => deleteJson(`/api/vault/unlocks/${id}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: MINE }),
  });
  const codeFailure = shown.error ?? renewed.error;
  const passkeyFailure = passkey.error ?? unhooked.error;

  return (
    <Modal heading={t('vault.settings')} wide onClose={onClose}>
      <Section title={t('vault.password.change')}>
        {passwordSet ? (
          <p className="text-sm">{t('vault.password.changed')}</p>
        ) : (
          <NewPassword
            submitLabel={t('vault.password.change')}
            pending={password.isPending}
            error={
              password.isError && (
                <p className="text-sm text-danger">{errorMessage(password.error, t)}</p>
              )
            }
            onSubmit={(typed) => password.mutate(typed)}
          />
        )}
      </Section>
      <Section title={t('vault.code')}>
        {code ? (
          <CodeShown code={code} note={t('vault.codeNote')} />
        ) : (
          <p className="text-sm text-muted">{t('vault.codeAbout')}</p>
        )}
        <div className="flex flex-wrap gap-2">
          {!code && (
            <button
              type="button"
              disabled={shown.isPending}
              onClick={() => shown.mutate()}
              className={button}
            >
              {t('vault.codeShow')}
            </button>
          )}
          <button
            type="button"
            disabled={renewed.isPending}
            onClick={() => renewed.mutate()}
            className={button}
          >
            <RotateCcw size={16} aria-hidden />
            {t('vault.codeRenew')}
          </button>
        </div>
        {codeFailure && <p className="text-sm text-danger">{errorMessage(codeFailure, t)}</p>}
      </Section>
      <Section title={t('vault.passkeys')}>
        <p className="text-sm text-muted">{t('vault.passkeysNote')}</p>
        {vault.unlocks.length > 0 && (
          <ul className="flex flex-col gap-1">
            {vault.unlocks.map((unlock) => (
              <li key={unlock.passkey} className="flex items-center gap-2 text-sm">
                <KeyRound size={16} aria-hidden className="shrink-0 text-muted" />
                <span className="min-w-0 flex-1 truncate">{unlock.name}</span>
                <button
                  type="button"
                  aria-label={t('vault.passkeyRemove')}
                  title={t('vault.passkeyRemove')}
                  onClick={() => unhooked.mutate(unlock.passkey)}
                  className={iconButton}
                >
                  <X size={16} aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        {passkeysWork ? (
          <button
            type="button"
            disabled={passkey.isPending}
            onClick={() => passkey.mutate()}
            className={`${button} self-start`}
          >
            <KeyRound size={16} aria-hidden />
            {t('vault.passkeyAdd')}
          </button>
        ) : (
          <p className="text-sm text-muted">{t('passkeys.unsupported')}</p>
        )}
        {passkeyFailure && (
          <p className="text-sm text-danger">
            {passkeyFailure instanceof NoPrf ? t('vault.noPrf') : passkeyMessage(passkeyFailure, t)}
          </p>
        )}
      </Section>
      <Section title={t('vault.idle')}>
        <select
          value={idle}
          aria-label={t('vault.idle')}
          onChange={(event) => {
            const minutes = Number(event.target.value) as Idle;
            keepIdle(minutes);
            setIdle(minutes);
          }}
          className={`${field} self-start`}
        >
          {IDLE_MINUTES.map((minutes) => (
            <option key={minutes} value={minutes}>
              {t(`vault.idle.${minutes}`)}
            </option>
          ))}
        </select>
      </Section>
      <Section title={t('vault.recovery')}>
        <p className="text-sm">
          {t(
            !vault.recovery
              ? 'vault.unrecoverable'
              : vault.escrowed
                ? 'vault.recoverable'
                : 'vault.enrolling',
          )}
        </p>
        {vault.recovered && (
          <p className="text-sm text-muted">
            {t('vault.recoveredBy')}: {vault.recovered.by?.name ?? t('log.formerUser')},{' '}
            {formatDate(vault.recovered.at)}
          </p>
        )}
      </Section>
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}
