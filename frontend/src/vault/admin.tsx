import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LifeBuoy, ShieldCheck, UserCheck } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { deleteJson, getJson, postJson, putJson } from '../api';
import type { User } from '../auth';
import { Close, ConfirmDialog, Modal } from '../dialogs';
import { Loading } from '../frame';
import { useI18n } from '../i18n';
import { button, primaryButton } from '../styles';
import { errorMessage } from '../tree';
import {
  fromBase64,
  fromCode,
  newCode,
  newPair,
  openSealed,
  seal,
  sealTo,
  spelledCode,
  toBase64,
  type Pair,
} from './crypto';
import { CodeShown } from './parts';
import { useVault, useVaultData, type Unlocked } from './state';

interface Waiting extends User {
  public_key: string;
}

interface Recovery {
  on: boolean;
  public_key?: string;
  /** The recovery key's private half sealed to this administrator, if they hold it. */
  sealed?: string | null;
  created_by?: User | null;
  created_at?: string;
  holders?: User[];
  /** Administrators with a vault who do not hold the recovery key yet. */
  waiting?: Waiting[];
  escrowed?: number;
  vaults?: number;
}

const RECOVERY = ['vault', 'recovery'];

function useRecovery() {
  return useQuery({ queryKey: RECOVERY, queryFn: () => getJson<Recovery>('/api/vault/recovery') });
}

async function recoveryPair(unlocked: Unlocked, recovery: Recovery): Promise<Pair> {
  const privateKey = await openSealed(unlocked.pair, fromBase64(recovery.sealed!));
  return { publicKey: fromBase64(recovery.public_key!), privateKey };
}

function Unlock() {
  const { t } = useI18n();
  return (
    <p className="text-sm text-muted">
      {t('recovery.unlockFirst')}{' '}
      <Link to="/vault" className="text-accent underline underline-offset-2">
        {t('vault.title')}
      </Link>
    </p>
  );
}

export function RecoverySection() {
  const { t, formatDate, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const vault = useVaultData();
  const { unlocked } = useVault();
  const recovery = useRecovery();
  const [off, setOff] = useState(false);
  const kept = (changed: Recovery) => queryClient.setQueryData(RECOVERY, changed);
  const turnOn = useMutation({
    mutationFn: async () => {
      const pair = await newPair();
      const mine = fromBase64(vault.data!.public_key);
      return putJson<Recovery>('/api/vault/recovery', {
        public_key: toBase64(pair.publicKey),
        sealed: toBase64(await sealTo(mine, pair.privateKey)),
      });
    },
    onSuccess: kept,
  });
  const turnOff = useMutation({
    mutationFn: () => deleteJson('/api/vault/recovery'),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ['vault'] }),
  });
  const confirm = useMutation({
    mutationFn: async (admins: Waiting[]) => {
      const pair = await recoveryPair(unlocked!, recovery.data!);
      const holders = await Promise.all(
        admins.map(async (admin) => ({
          user: admin.id,
          sealed: toBase64(await sealTo(fromBase64(admin.public_key), pair.privateKey)),
        })),
      );
      return postJson<Recovery>('/api/vault/recovery/holders', { holders });
    },
    onSuccess: kept,
  });
  const data = recovery.data;
  const failure = recovery.error ?? vault.error ?? turnOn.error ?? turnOff.error ?? confirm.error;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-semibold">{t('recovery.title')}</h2>
      <p className="text-sm text-muted">{t('recovery.note')}</p>
      {data && !data.on && (
        <div className="flex flex-col gap-2">
          <p className="text-sm">{t('recovery.off')}</p>
          {vault.data ? (
            <button
              type="button"
              disabled={turnOn.isPending}
              onClick={() => turnOn.mutate()}
              className={`${primaryButton} self-start`}
            >
              <ShieldCheck size={16} aria-hidden />
              {t('recovery.turnOn')}
            </button>
          ) : (
            vault.isSuccess && (
              <p className="text-sm text-muted">
                {t('recovery.needVault')}{' '}
                <Link to="/vault" className="text-accent underline underline-offset-2">
                  {t('vault.title')}
                </Link>
              </p>
            )
          )}
        </div>
      )}
      {data?.on && (
        <div className="flex flex-col gap-2">
          <p className="text-sm">
            {t('recovery.on')}: {data.created_by?.name ?? t('log.formerUser')},{' '}
            {formatDate(data.created_at!)} · {t('recovery.escrowed')}:{' '}
            {formatNumber(data.escrowed!)} / {formatNumber(data.vaults!)}
          </p>
          <p className="text-sm">
            {t('recovery.holders')}: {data.holders!.map((holder) => holder.name).join(', ')}
          </p>
          {data.waiting!.length > 0 && (
            <div className="flex flex-col gap-2 rounded border border-line p-2">
              <p className="text-sm font-semibold">{t('recovery.waiting')}</p>
              {!data.sealed ? (
                <p className="text-sm text-muted">{t('recovery.notHolder')}</p>
              ) : (
                !unlocked && <Unlock />
              )}
              <ul className="flex flex-col gap-1">
                {data.waiting!.map((admin) => (
                  <li key={admin.id} className="flex items-center gap-2 text-sm">
                    <span className="min-w-0 flex-1 truncate">{admin.name}</span>
                    <button
                      type="button"
                      disabled={!unlocked || !data.sealed || confirm.isPending}
                      onClick={() => confirm.mutate([admin])}
                      className={button}
                    >
                      <UserCheck size={16} aria-hidden />
                      {t('vault.confirm')}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <button type="button" onClick={() => setOff(true)} className={`${button} self-start`}>
            {t('recovery.turnOff')}
          </button>
        </div>
      )}
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {off && (
        <ConfirmDialog
          heading={t('recovery.turnOffTitle')}
          confirmLabel={t('recovery.turnOff')}
          onConfirm={() => turnOff.mutate()}
          onClose={() => setOff(false)}
        >
          {t('recovery.turnOffWarning')}
        </ConfirmDialog>
      )}
    </section>
  );
}

/** A one-time code an administrator who holds the recovery key prepares for a user who lost
    their vault password, and hands them in person. */
export function RecoverDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const { t } = useI18n();
  const { unlocked } = useVault();
  const recovery = useRecovery();
  const target = useQuery({
    queryKey: ['vault', 'recover', user.id],
    queryFn: () =>
      getJson<{ vault: boolean; escrow: string | null }>(`/api/users/${user.id}/vault`),
  });
  const prepare = useMutation({
    mutationFn: async () => {
      const pair = await recoveryPair(unlocked!, recovery.data!);
      const vaultKey = await openSealed(pair, fromBase64(target.data!.escrow!));
      const code = newCode();
      const handed = await seal(await fromCode(spelledCode(code)!), vaultKey);
      await postJson(`/api/users/${user.id}/vault`, { handed: toBase64(handed) });
      return code;
    },
  });
  const failure = recovery.error ?? target.error ?? prepare.error;
  const blocked = !target.data?.vault
    ? 'recovery.noVault'
    : !recovery.data?.on
      ? 'recovery.off'
      : !target.data.escrow
        ? 'recovery.notEscrowed'
        : !recovery.data.sealed
          ? 'recovery.notHolder'
          : null;

  return (
    <Modal heading={`${t('recovery.recover')}: ${user.name}`} onClose={onClose}>
      {(target.isPending || recovery.isPending) && !failure && <Loading />}
      {target.isSuccess && recovery.isSuccess && (
        <>
          {prepare.data ? (
            <CodeShown code={prepare.data} note={t('recovery.handOver')} />
          ) : blocked ? (
            <p className="text-sm">{t(blocked)}</p>
          ) : !unlocked ? (
            <Unlock />
          ) : (
            <>
              <p className="text-sm">{t('recovery.prepareNote')}</p>
              <button
                type="button"
                disabled={prepare.isPending}
                onClick={() => prepare.mutate()}
                className={`${primaryButton} self-start`}
              >
                <LifeBuoy size={16} aria-hidden />
                {t('recovery.prepare')}
              </button>
            </>
          )}
        </>
      )}
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}
