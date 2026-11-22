import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router';
import { getJson, patchJson } from './api';
import { useSession } from './auth';
import { Loaded } from './frame';
import { Rows, Section, Verdict } from './health';
import { useI18n } from './i18n';
import { AdminFrame } from './settings';
import { TunnelsSection } from './tunnels';
import { button, field, primaryButton } from './styles';
import { errorMessage } from './tree';

/** The installation's public address and what reaches it, as the server sees them now; the DNS
 * token never comes back, only how it ends. */
interface Network {
  address: string | null;
  reached: boolean;
  ports: { udp: number; tcp: number };
  relay: string;
  names: string[];
  dns: { hint: string; lost: boolean; error: string; changed_at: string | null };
}

function TokenForm({ network }: { network: Network }) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const [token, setToken] = useState('');
  const { dns } = network;
  const save = useMutation({
    mutationFn: (given: string) => patchJson<Network>('/api/network', { token: given }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['network'], saved);
      setToken('');
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(token);
  };
  const kept = dns.hint !== '' && !dns.lost;
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        {t('network.token')}
        <input
          type="password"
          autoComplete="new-password"
          spellCheck={false}
          value={token}
          placeholder={kept ? t('network.replace') : undefined}
          onChange={(event) => setToken(event.target.value)}
          className={field}
        />
      </label>
      {kept && (
        <p className="text-sm text-muted">
          {t('network.kept')} …{dns.hint}
        </p>
      )}
      {dns.lost && <p className="text-sm text-danger">{t('network.lost')}</p>}
      {dns.error && (
        <p className="text-sm text-danger">
          {t('network.refused')} {dns.error}
        </p>
      )}
      {dns.changed_at && (
        <p className="text-sm text-muted">
          {t('ai.changed')}: {formatDate(dns.changed_at)}
        </p>
      )}
      {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
      <div className="flex justify-end gap-2">
        {dns.hint !== '' && (
          <button
            type="button"
            disabled={save.isPending}
            onClick={() => save.mutate('')}
            className={button}
          >
            {t('network.forget')}
          </button>
        )}
        <button type="submit" disabled={save.isPending || !token.trim()} className={primaryButton}>
          {t('ai.save')}
        </button>
      </div>
    </form>
  );
}

function NetworkView({ network }: { network: Network }) {
  const { t } = useI18n();
  const { udp, tcp } = network.ports;
  return (
    <div className="flex w-full max-w-2xl flex-col gap-8">
      <Section heading={t('network.meetings')}>
        <Rows
          rows={[
            [t('network.address'), network.address ?? t('network.unknown')],
            [
              `UDP ${udp}, TCP ${tcp}`,
              <Verdict ok={network.reached} good="network.reached" bad="network.unreached" />,
            ],
            [t('network.relay'), network.relay || t('network.noRelay')],
          ]}
        />
      </Section>
      {network.names.length > 0 && (
        <Section heading={t('network.names')}>
          <p className="text-sm">{network.names.join(', ')}</p>
          <TokenForm network={network} />
        </Section>
      )}
      <TunnelsSection />
    </div>
  );
}

export function NetworkPage() {
  const { t } = useI18n();
  const me = useSession().data?.user;
  const network = useQuery({
    queryKey: ['network'],
    queryFn: () => getJson<Network>('/api/network'),
    enabled: !!me?.is_admin,
  });
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return (
    <AdminFrame title={t('network.title')}>
      <Loaded query={network}>{(data) => <NetworkView network={data} />}</Loaded>
    </AdminFrame>
  );
}
