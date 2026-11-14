import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router';
import { getJson, patchJson } from './api';
import { useSession } from './auth';
import { Loaded } from './frame';
import { useI18n } from './i18n';
import { AdminFrame } from './settings';
import { field, primaryButton } from './styles';
import { errorMessage } from './tree';

type Provider = '' | 'cloudflare' | 'turn';

/** The installation's relay for meetings as the server tells an administrator: never its token
 * or password, only how it ends. */
interface Relay {
  provider: Provider;
  addresses: string[];
  name: string;
  hint: string;
  lost: boolean;
  changed_at: string | null;
}

function RelayForm({ relay }: { relay: Relay }) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const [provider, setProvider] = useState<Provider>(relay.provider);
  const [addresses, setAddresses] = useState(relay.addresses.join('\n'));
  const [name, setName] = useState(relay.name);
  const [secret, setSecret] = useState('');
  const save = useMutation({
    mutationFn: () =>
      patchJson<Relay>('/api/meetings/relay', {
        provider,
        addresses: provider === 'turn' ? addresses.split('\n') : [],
        name,
        secret: secret.trim() || undefined,
      }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['meeting-relay'], saved);
      setSecret('');
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  const kept = provider === relay.provider && relay.hint !== '' && !relay.lost;
  const cloudflare = provider === 'cloudflare';
  return (
    <form onSubmit={submit} className="flex w-full max-w-xl flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm">
        {t('relay.provider')}
        <select
          value={provider}
          onChange={(event) => setProvider(event.target.value as Provider)}
          className={field}
        >
          <option value="">{t('relay.none')}</option>
          <option value="cloudflare">{t('relay.cloudflare')}</option>
          <option value="turn">{t('relay.turn')}</option>
        </select>
      </label>
      {provider === 'turn' && (
        <label className="flex flex-col gap-1 text-sm">
          {t('relay.addresses')}
          <textarea
            rows={3}
            spellCheck={false}
            value={addresses}
            placeholder="turn:turn.example.com:3478"
            onChange={(event) => setAddresses(event.target.value)}
            className={field}
          />
        </label>
      )}
      {provider !== '' && (
        <>
          <label className="flex flex-col gap-1 text-sm">
            {t(cloudflare ? 'relay.keyId' : 'relay.username')}
            <input
              spellCheck={false}
              autoComplete="off"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t(cloudflare ? 'relay.token' : 'relay.password')}
            <input
              type="password"
              autoComplete="new-password"
              spellCheck={false}
              value={secret}
              placeholder={kept ? t('relay.replace') : undefined}
              onChange={(event) => setSecret(event.target.value)}
              className={field}
            />
          </label>
          {kept && (
            <p className="text-sm text-muted">
              {t('relay.kept')} …{relay.hint}
            </p>
          )}
        </>
      )}
      {relay.lost && <p className="text-sm text-danger">{t('relay.lost')}</p>}
      {relay.changed_at && (
        <p className="text-sm text-muted">
          {t('ai.changed')}: {formatDate(relay.changed_at)}
        </p>
      )}
      {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
      <div className="flex justify-end">
        <button type="submit" disabled={save.isPending} className={primaryButton}>
          {t('ai.save')}
        </button>
      </div>
    </form>
  );
}

export function RelayPage() {
  const { t } = useI18n();
  const me = useSession().data?.user;
  const relay = useQuery({
    queryKey: ['meeting-relay'],
    queryFn: () => getJson<Relay>('/api/meetings/relay'),
    enabled: !!me?.is_admin,
  });
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return (
    <AdminFrame title={t('relay.title')}>
      <Loaded query={relay}>
        {(data) => <RelayForm key={data.changed_at ?? ''} relay={data} />}
      </Loaded>
    </AdminFrame>
  );
}
