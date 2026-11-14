import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router';
import { deleteJson, getJson, patchJson } from './api';
import { useSession } from './auth';
import { ConfirmDialog, Labelled } from './dialogs';
import { Loaded } from './frame';
import { AdminFrame } from './settings';
import { useI18n } from './i18n';
import { button, field, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';
import { ACCOUNTS, type Provider } from './mailData';

/** The installation's client at a provider as the server tells an administrator: never its
    secret, only its last four characters. */
interface Client {
  provider: Provider;
  /** Where the provider sends users back, registered with the provider exactly so. */
  redirect: string;
  client_id: string;
  hint: string;
  lost: boolean;
  /** When a Microsoft secret ends, as YYYY-MM-DD. */
  expires: string | null;
  changed_at: string | null;
}

/** The installation's mail as the server tells an administrator. */
interface MailSetting {
  /** Whether the sender of a message sees which colleagues opened it, and when. */
  opened: boolean;
  changed_at: string | null;
}

const CLIENTS = ['mail', 'clients'];
const SETTING = ['mail', 'setting'];
const WARNED_DAYS = 30;

function endsSoon(expires: string | null): boolean {
  if (!expires) return false;
  return new Date(expires).getTime() - Date.now() < WARNED_DAYS * 24 * 60 * 60 * 1000;
}

function ClientForm({ client }: { client: Client }) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const [clientId, setClientId] = useState(client.client_id);
  const [secret, setSecret] = useState('');
  const [expires, setExpires] = useState(client.expires ?? '');
  const [removing, setRemoving] = useState(false);
  const changed = () => {
    void queryClient.invalidateQueries({ queryKey: CLIENTS });
    void queryClient.invalidateQueries({ queryKey: ACCOUNTS });
  };
  const save = useMutation({
    mutationFn: () =>
      patchJson<Client>(`/api/mail/clients/${client.provider}`, {
        client_id: clientId.trim(),
        secret: secret.trim() || undefined,
        expires: expires || null,
      }),
    onSuccess: () => {
      setSecret('');
      changed();
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteJson(`/api/mail/clients/${client.provider}`),
    onSuccess: () => {
      setRemoving(false);
      setClientId('');
      setExpires('');
      changed();
    },
  });
  const kept = client.hint !== '' && !client.lost;
  const failure = save.error ?? remove.error;

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <>
      <form onSubmit={submit} className="flex flex-col gap-3 rounded-lg border border-line p-4">
        <h2 className="text-base font-semibold">{t(`providers.${client.provider}`)}</h2>
        <p className="text-sm text-muted">{t(`providers.${client.provider}.note`)}</p>
        <Labelled label={t('providers.redirect')}>
          {(id) => (
            <div className="flex items-center gap-1">
              <input
                id={id}
                readOnly
                value={client.redirect}
                onFocus={(event) => event.target.select()}
                className={field}
              />
              <button
                type="button"
                aria-label={t('providers.copy')}
                title={t('providers.copy')}
                onClick={() => void navigator.clipboard.writeText(client.redirect)}
                className={iconButton}
              >
                <Copy size={16} aria-hidden />
              </button>
            </div>
          )}
        </Labelled>
        <Labelled label={t('providers.clientId')}>
          {(id) => (
            <input
              id={id}
              required
              maxLength={255}
              spellCheck={false}
              value={clientId}
              onChange={(event) => setClientId(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <Labelled label={t('providers.secret')}>
          {(id) => (
            <input
              id={id}
              type="password"
              required={!kept}
              autoComplete="new-password"
              spellCheck={false}
              value={secret}
              placeholder={kept ? t('providers.secretReplace') : undefined}
              onChange={(event) => setSecret(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        {kept && (
          <p className="-mt-2 text-xs text-muted">
            {t('providers.secretKept')} …{client.hint}
          </p>
        )}
        {client.lost && <p className="text-sm text-danger">{t('providers.secretLost')}</p>}
        {client.provider === 'microsoft' && (
          <Labelled label={t('providers.expires')}>
            {(id) => (
              <input
                id={id}
                type="date"
                value={expires}
                onChange={(event) => setExpires(event.target.value)}
                className={field}
              />
            )}
          </Labelled>
        )}
        {endsSoon(client.expires) && (
          <p className="text-sm text-danger">{t('providers.endsSoon')}</p>
        )}
        {client.changed_at && (
          <p className="text-sm text-muted">
            {t('providers.changed')}: {formatDate(client.changed_at)}
          </p>
        )}
        {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
        <div className="flex justify-end gap-2">
          {client.client_id && (
            <button type="button" onClick={() => setRemoving(true)} className={button}>
              {t('providers.remove')}
            </button>
          )}
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t(save.isPending ? 'mail.checking' : 'providers.save')}
          </button>
        </div>
      </form>
      {removing && (
        <ConfirmDialog
          heading={t('providers.removeTitle')}
          confirmLabel={t('providers.remove')}
          onConfirm={() => remove.mutate()}
          onClose={() => setRemoving(false)}
        >
          {t('providers.removeWarning')}
        </ConfirmDialog>
      )}
    </>
  );
}

/** Where an administrator enters the installation's own clients at Google and Microsoft, through
    which its users' accounts sign in instead of with a password. */
function OpenedForm({ setting }: { setting: MailSetting }) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const [opened, setOpened] = useState(setting.opened);
  const save = useMutation({
    mutationFn: () => patchJson<MailSetting>('/api/mail/setting', { opened }),
    onSuccess: (saved) => queryClient.setQueryData(SETTING, saved),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <h2 className="text-base font-semibold">{t('mail.openedSetting')}</h2>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={opened}
          onChange={(event) => setOpened(event.target.checked)}
        />
        {t('mail.openedEnabled')}
      </label>
      <p className="text-sm text-muted">{t('mail.openedNote')}</p>
      {setting.changed_at && (
        <p className="text-sm text-muted">
          {t('providers.changed')}: {formatDate(setting.changed_at)}
        </p>
      )}
      {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
      <div className="flex justify-end">
        <button type="submit" disabled={save.isPending} className={primaryButton}>
          {t('providers.save')}
        </button>
      </div>
    </form>
  );
}

export function ProvidersPage() {
  const { t } = useI18n();
  const me = useSession().data?.user;
  const clients = useQuery({
    queryKey: CLIENTS,
    queryFn: () => getJson<{ clients: Client[] }>('/api/mail/clients'),
    enabled: !!me?.is_admin,
  });
  const setting = useQuery({
    queryKey: SETTING,
    queryFn: () => getJson<MailSetting>('/api/mail/setting'),
    enabled: !!me?.is_admin,
  });
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return (
    <Loaded query={clients}>
      {(data) => (
        <AdminFrame title={t('providers.title')}>
          <div className="flex w-full max-w-xl flex-col gap-8">
            <Loaded query={setting}>{(found) => <OpenedForm setting={found} />}</Loaded>
            <section className="flex flex-col gap-4">
              <h2 className="text-base font-semibold">{t('providers.signIn')}</h2>
              <p className="text-sm text-muted">{t('providers.intro')}</p>
              {data.clients.map((client) => (
                <ClientForm key={client.provider} client={client} />
              ))}
            </section>
          </div>
        </AdminFrame>
      )}
    </Loaded>
  );
}
