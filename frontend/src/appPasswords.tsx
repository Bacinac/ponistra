import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import shelved from 'virtual:android';
import { deleteJson, getJson, postJson } from './api';
import { useSession } from './auth';
import { Cancel, Close, ConfirmDialog, Modal } from './dialogs';
import { useI18n } from './i18n';
import { ActionsMenu, MenuItem } from './menu';
import { button, field, primaryButton } from './styles';
import { connectPage, onAndroid, Qr, Steps } from './phoneApp';
import { errorMessage } from './tree';
import { CopyButton } from './vault/parts';

interface AppPassword {
  id: number;
  name: string;
  created_at: string;
  used_at: string | null;
}

interface Made extends AppPassword {
  password: string;
}

interface Pairing extends AppPassword {
  code: string;
}

const APP_PASSWORDS = ['app-passwords'];
const cell = 'px-2 py-2';

/** What an iPhone's own contacts app is given to read the address book over CardDAV. */
function Setup({ email }: { email: string }) {
  const { t } = useI18n();
  const shown = 'min-w-0 font-mono break-words select-all';
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p>{t('appPasswords.iphone')}</p>
      <dl className="grid gap-x-3 sm:grid-cols-[max-content_1fr] sm:gap-y-1">
        <dt className="text-muted">{t('appPasswords.server')}</dt>
        <dd className={shown}>{location.host}</dd>
        <dt className="text-muted">{t('appPasswords.user')}</dt>
        <dd className={shown}>{email}</dd>
      </dl>
    </div>
  );
}

/** A password for an app other than ours, such as an iPhone's contacts over CardDAV, shown once
    and only here. */
function OtherAppDialog({ onMade, onClose }: { onMade: () => void; onClose: () => void }) {
  const { t } = useI18n();
  const email = useSession().data?.user?.email ?? '';
  const [name, setName] = useState('');
  const add = useMutation({
    mutationFn: () => postJson<Made>('/api/app-passwords', { name }),
    onSuccess: onMade,
  });
  const made = add.data;

  function submit(event: FormEvent) {
    event.preventDefault();
    add.mutate();
  }

  return (
    <Modal heading={t('appPasswords.other')} onClose={onClose}>
      {made ? (
        <>
          <section aria-label={made.name} className="flex flex-col gap-3">
            <p className="text-sm">
              <strong>{made.name}</strong> {t('appPasswords.shownOnce')}
            </p>
            <div className="flex items-center gap-2">
              <p
                aria-label={t('appPasswords.password')}
                className="flex-1 rounded border border-line bg-panel p-3 text-center font-mono text-lg tracking-wider break-all select-all"
              >
                {made.password}
              </p>
              <CopyButton text={made.password} label={t('appPasswords.copy')} />
            </div>
            <Setup email={email} />
          </section>
          <div className="flex justify-end">
            <Close />
          </div>
        </>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-1 text-sm">
            {t('appPasswords.newName')}
            <input
              required
              maxLength={150}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('appPasswords.example')}
              className={field}
            />
          </label>
          {add.isError && <p className="text-sm text-danger">{errorMessage(add.error, t)}</p>}
          <div className="flex justify-end gap-2">
            <Cancel />
            <button type="submit" disabled={add.isPending} className={primaryButton}>
              {t(add.isPending ? 'appPasswords.adding' : 'appPasswords.add')}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

/** The code a phone takes to connect its own app (D26): the link that opens the app on the phone
    itself, a QR code for the phone's camera elsewhere. */
function PairingDialog({
  pairing,
  claimed,
  onClose,
}: {
  pairing: Pairing;
  claimed: AppPassword | undefined;
  onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <Modal heading={t('phoneApp.connect')} onClose={onClose}>
      {claimed ? (
        <p className="text-sm">
          {t('phoneApp.connected')} <strong>{claimed.name}</strong>
        </p>
      ) : onAndroid ? (
        <Steps code={pairing.code} />
      ) : (
        <div className="flex flex-col items-center gap-3">
          <Qr text={connectPage(pairing.code)} label={t('phoneApp.qr')} />
          <p className="text-sm text-muted">{t('phoneApp.scan')}</p>
        </div>
      )}
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}

/** The passwords a phone's own apps hold; a page of the settings, and the dialog that Contacts
    and Calendar open where a phone is being set up. */
export function AppPasswords() {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const [other, setOther] = useState(false);
  const [removing, setRemoving] = useState<AppPassword | null>(null);
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const kept = useQuery({
    queryKey: APP_PASSWORDS,
    queryFn: () => getJson<{ app_passwords: AppPassword[] }>('/api/app-passwords'),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: APP_PASSWORDS });
  const remove = useMutation({
    mutationFn: (password: AppPassword) => deleteJson(`/api/app-passwords/${password.id}`),
    onSuccess: () => {
      setRemoving(null);
      refresh();
    },
  });
  const pair = useMutation({
    mutationFn: () => postJson<Pairing>('/api/device/pairing'),
    onSuccess: (given) => {
      setPairing(given);
      refresh();
    },
  });
  const failure = kept.error ?? remove.error ?? pair.error;

  function claimedOf(asked: AppPassword): AppPassword | undefined {
    return kept.data?.app_passwords.find((each) => each.id === asked.id && each.used_at);
  }

  function closePairing(open: Pairing) {
    if (!claimedOf(open)) remove.mutate(open);
    setPairing(null);
  }

  return (
    <>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {shelved && (
        <section className="flex flex-col gap-2 rounded border border-line p-3">
          <h2 className="text-sm font-semibold">{t('phoneApp.title')}</h2>
          <p className="text-sm text-muted">{t('phoneApp.note')}</p>
          <div>
            <button
              type="button"
              onClick={() => pair.mutate()}
              disabled={pair.isPending}
              className={primaryButton}
            >
              {t('phoneApp.connect')}
            </button>
          </div>
        </section>
      )}
      {kept.data?.app_passwords.length === 0 && <p className="text-sm">{t('appPasswords.none')}</p>}
      {!!kept.data?.app_passwords.length && (
        <table className="w-full border-collapse">
          <thead className="text-left text-sm text-muted">
            <tr className="border-b border-line">
              <th className="w-full px-2 py-2 font-normal">{t('appPasswords.device')}</th>
              <th className="hidden px-2 py-2 font-normal sm:table-cell">
                {t('passkeys.created')}
              </th>
              <th className="px-2 py-2 font-normal whitespace-nowrap">{t('appPasswords.used')}</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {kept.data.app_passwords.map((password) => (
              <tr key={password.id} className="border-b border-line">
                <td className={`${cell} max-w-0`}>
                  <p className="truncate">{password.name}</p>
                </td>
                <td className={`${cell} hidden text-sm whitespace-nowrap text-muted sm:table-cell`}>
                  {formatDate(password.created_at)}
                </td>
                <td className={`${cell} text-sm whitespace-nowrap text-muted`}>
                  {password.used_at ? formatDate(password.used_at) : t('users.never')}
                </td>
                <td className="pr-2">
                  <ActionsMenu>
                    <MenuItem
                      icon={Trash2}
                      label={t('appPasswords.delete')}
                      onSelect={() => setRemoving(password)}
                    />
                  </ActionsMenu>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div>
        <button type="button" onClick={() => setOther(true)} className={button}>
          {t('appPasswords.otherOpen')}
        </button>
      </div>
      {other && <OtherAppDialog onMade={refresh} onClose={() => setOther(false)} />}
      {removing && (
        <ConfirmDialog
          heading={t('appPasswords.deleteTitle')}
          confirmLabel={t('appPasswords.delete')}
          onConfirm={() => remove.mutate(removing)}
          onClose={() => setRemoving(null)}
        >
          <strong>{removing.name}</strong> {t('appPasswords.deleteWarning')}
        </ConfirmDialog>
      )}
      {pairing && (
        <PairingDialog
          pairing={pairing}
          claimed={claimedOf(pairing)}
          onClose={() => closePairing(pairing)}
        />
      )}
    </>
  );
}

export function AppPasswordsDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  return (
    <Modal heading={t('appPasswords.title')} wide onClose={onClose}>
      <AppPasswords />
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}
