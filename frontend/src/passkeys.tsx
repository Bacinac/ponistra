import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { ApiError, deleteJson, getJson, patchJson, postJson } from './api';
import { ConfirmDialog, NameDialog } from './dialogs';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { ActionsMenu, MenuItem, MenuSeparator } from './menu';
import { field, primaryButton } from './styles';
import { errorMessage } from './tree';

interface Passkey {
  id: number;
  name: string;
  created_at: string;
  used_at: string | null;
}

export const PASSKEYS = ['passkeys'];
const cell = 'px-2 py-2';

export const passkeysWork =
  typeof PublicKeyCredential !== 'undefined' &&
  'parseRequestOptionsFromJSON' in PublicKeyCredential;

/** What the person reads when the browser or the server turned a passkey down. */
export function passkeyMessage(error: Error, t: (key: MessageKey) => string): string {
  if (error.name === 'NotAllowedError') return t('passkeys.cancelled');
  if (error.name === 'InvalidStateError') return t('passkeys.kept');
  return errorMessage(error, t);
}

async function answered(
  path: string,
  request: CredentialRequestOptions = {},
): Promise<PublicKeyCredential> {
  const options = await postJson<PublicKeyCredentialRequestOptionsJSON>(path);
  return (await navigator.credentials.get({
    ...request,
    publicKey: PublicKeyCredential.parseRequestOptionsFromJSON(options),
  })) as PublicKeyCredential;
}

export async function passkeySignIn<T>(): Promise<T> {
  return signedInBy<T>(await answered('/api/auth/passkey/options'));
}

/** Has the browser offer the device's passkeys in the list under the email field, and signs in
 * with the one the person picks; null where the browser offers none or the offer was withdrawn. */
export async function passkeyOffered<T>(withdrawn: AbortSignal): Promise<T | null> {
  if (withdrawn.aborted || !(await PublicKeyCredential.isConditionalMediationAvailable())) {
    return null;
  }
  return signedInBy<T>(
    await answered('/api/auth/passkey/options', { mediation: 'conditional', signal: withdrawn }),
  );
}

async function signedInBy<T>(answer: PublicKeyCredential): Promise<T> {
  try {
    return await postJson<T>('/api/auth/passkey', { credential: answer.toJSON() });
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.code === 'unknown_passkey' &&
      'signalUnknownCredential' in PublicKeyCredential
    ) {
      void PublicKeyCredential.signalUnknownCredential({
        rpId: location.hostname,
        credentialId: answer.id,
      });
    }
    throw error;
  }
}

export async function passkeyConfirm(): Promise<void> {
  const answer = await answered('/api/auth/confirm/options');
  await postJson('/api/auth/confirm', { credential: answer.toJSON() });
}

export async function makePasskey(name: string): Promise<Passkey> {
  const options = await postJson<PublicKeyCredentialCreationOptionsJSON>('/api/passkeys/options');
  const publicKey = PublicKeyCredential.parseCreationOptionsFromJSON(options);
  // Security keys and Windows Hello give a passkey PRF only when it is made; the vault unlocks
  // with it later.
  publicKey.extensions = { ...publicKey.extensions, prf: {} };
  const made = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential;
  return postJson<Passkey>('/api/passkeys', { name, credential: made.toJSON() });
}

/** The user's passkeys, a page of the settings. */
export function Passkeys() {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [dialog, setDialog] = useState<{ type: 'rename' | 'delete'; passkey: Passkey } | null>(
    null,
  );
  const kept = useQuery({
    queryKey: PASSKEYS,
    queryFn: () => getJson<{ passkeys: Passkey[] }>('/api/passkeys'),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: PASSKEYS });
  const close = () => setDialog(null);
  const add = useMutation({
    mutationFn: () => makePasskey(name),
    onSuccess: () => {
      setName('');
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (passkey: Passkey) => deleteJson(`/api/passkeys/${passkey.id}`),
    onSuccess: () => {
      close();
      refresh();
    },
  });
  const failure = kept.error ?? remove.error;

  function submit(event: FormEvent) {
    event.preventDefault();
    add.mutate();
  }

  return (
    <>
      <p className="text-sm text-muted">{t('passkeys.note')}</p>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {kept.data?.passkeys.length === 0 && <p className="text-sm">{t('passkeys.none')}</p>}
      {!!kept.data?.passkeys.length && (
        <table className="w-full border-collapse">
          <thead className="text-left text-sm text-muted">
            <tr className="border-b border-line">
              <th className="w-full px-2 py-2 font-normal">{t('tree.name')}</th>
              <th className="hidden px-2 py-2 font-normal sm:table-cell">
                {t('passkeys.created')}
              </th>
              <th className="px-2 py-2 font-normal whitespace-nowrap">{t('users.lastLogin')}</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {kept.data.passkeys.map((passkey) => (
              <tr key={passkey.id} className="border-b border-line">
                <td className={`${cell} max-w-0`}>
                  <p className="truncate">{passkey.name}</p>
                </td>
                <td className={`${cell} hidden text-sm whitespace-nowrap text-muted sm:table-cell`}>
                  {formatDate(passkey.created_at)}
                </td>
                <td className={`${cell} text-sm whitespace-nowrap text-muted`}>
                  {passkey.used_at ? formatDate(passkey.used_at) : t('users.never')}
                </td>
                <td className="pr-2">
                  <ActionsMenu>
                    <MenuItem
                      icon={Pencil}
                      label={t('tree.rename')}
                      onSelect={() => setDialog({ type: 'rename', passkey })}
                    />
                    <MenuSeparator />
                    <MenuItem
                      icon={Trash2}
                      label={t('passkeys.delete')}
                      onSelect={() => setDialog({ type: 'delete', passkey })}
                    />
                  </ActionsMenu>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {passkeysWork ? (
        <form onSubmit={submit} className="flex flex-col gap-2">
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
          {add.isError && <p className="text-sm text-danger">{passkeyMessage(add.error, t)}</p>}
          <div className="flex justify-end">
            <button type="submit" disabled={add.isPending} className={primaryButton}>
              {t(add.isPending ? 'passkeys.adding' : 'passkeys.add')}
            </button>
          </div>
        </form>
      ) : (
        <p className="text-sm text-danger">{t('passkeys.unsupported')}</p>
      )}
      {dialog?.type === 'rename' && (
        <NameDialog
          heading={t('tree.rename')}
          submitLabel={t('tree.save')}
          initial={dialog.passkey.name}
          onSubmit={(renamed) => patchJson(`/api/passkeys/${dialog.passkey.id}`, { name: renamed })}
          onDone={() => {
            refresh();
            close();
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'delete' && (
        <ConfirmDialog
          heading={t('passkeys.deleteTitle')}
          confirmLabel={t('passkeys.delete')}
          onConfirm={() => remove.mutate(dialog.passkey)}
          onClose={close}
        >
          <strong>{dialog.passkey.name}</strong> {t('passkeys.deleteWarning')}
        </ConfirmDialog>
      )}
    </>
  );
}
