import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { deleteJson, getJson, postJson } from './api';
import { useSession } from './auth';
import { ConfirmDialog } from './dialogs';
import { Loading, Lobby } from './frame';
import { useI18n } from './i18n';
import { ActionsMenu, MenuItem } from './menu';
import { button, primaryButton } from './styles';
import { errorMessage } from './tree';
import { CopyButton } from './vault/parts';

interface Consent {
  client: string;
  redirect: string;
  scopes: string[];
  expires_at: string;
}

interface Agent {
  id: number;
  client: string;
  created_at: string;
  used_at: string | null;
}

const AGENTS = ['agents'];
const cell = 'px-2 py-2';

function placeOf(redirect: string): string {
  try {
    const url = new URL(redirect);
    return url.host || url.protocol.replace(/:$/, '');
  } catch {
    return redirect;
  }
}

/** Where an outside agent's sign-in waits for the user: who asks, as whom it would act and what
 * it can do, and the answer that sends the agent on its way or back without. */
export function ConsentPage() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const request = params.get('request') ?? '';
  const user = useSession().data?.user;
  const asked = useQuery({
    queryKey: ['agents', 'consent', request],
    queryFn: () => getJson<Consent>(`/api/agents/consent?${new URLSearchParams({ request })}`),
    retry: false,
  });
  const answer = useMutation({
    mutationFn: (allow: boolean) =>
      postJson<{ redirect: string }>('/api/agents/consent', { request, allow }),
    onSuccess: ({ redirect }) => location.assign(redirect),
  });
  return (
    <Lobby>
      <section
        aria-labelledby="consent"
        className="flex w-full max-w-md flex-col gap-4 rounded-xl bg-raised p-6"
      >
        <h2 id="consent" className="flex items-center gap-2 text-lg font-semibold">
          <Bot size={20} aria-hidden className="text-muted" />
          {t('agents.consent.title')}
        </h2>
        {asked.isPending ? (
          <Loading />
        ) : asked.isError ? (
          <p className="text-danger">{errorMessage(asked.error, t)}</p>
        ) : (
          <>
            <p>{t('agents.consent.asks').replace('{client}', asked.data.client)}</p>
            <dl className="grid gap-x-3 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
              <dt className="text-muted">{t('agents.consent.as')}</dt>
              <dd>
                {user?.name}
                {user && user.name !== user.email && (
                  <span className="text-muted"> ({user.email})</span>
                )}
              </dd>
              <dt className="text-muted">{t('agents.consent.returns')}</dt>
              <dd className="break-all">{placeOf(asked.data.redirect)}</dd>
            </dl>
            <p className="text-sm font-medium">{t('agents.consent.can')}</p>
            <ul className="list-disc pl-5 text-sm">
              <li>{t('agents.consent.read')}</li>
              <li>{t('agents.consent.write')}</li>
              <li>{t('agents.consent.never')}</li>
            </ul>
            <p className="text-sm text-muted">{t('agents.consent.revocable')}</p>
            {answer.isError && (
              <p className="text-sm text-danger">{errorMessage(answer.error, t)}</p>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                disabled={answer.isPending}
                onClick={() => answer.mutate(false)}
                className={button}
              >
                {t('agents.consent.deny')}
              </button>
              <button
                type="button"
                disabled={answer.isPending}
                onClick={() => answer.mutate(true)}
                className={primaryButton}
              >
                {t('agents.consent.allow')}
              </button>
            </div>
          </>
        )}
      </section>
    </Lobby>
  );
}

/** The agents the user let in, where an agent signs in, and the revoking of one. */
/** The agents let in over MCP, a page of the settings. */
export function Agents() {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const [removing, setRemoving] = useState<Agent | null>(null);
  const kept = useQuery({
    queryKey: AGENTS,
    queryFn: () => getJson<{ url: string; clients: Agent[] }>('/api/agents/clients'),
  });
  const remove = useMutation({
    mutationFn: (agent: Agent) => deleteJson(`/api/agents/clients/${agent.id}`),
    onSuccess: () => {
      setRemoving(null);
      queryClient.invalidateQueries({ queryKey: AGENTS });
    },
  });
  const failure = kept.error ?? remove.error;
  return (
    <>
      <p className="text-sm">{t('agents.intro')}</p>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {kept.data && (
        <div className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t('agents.url')}</span>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 rounded border border-line bg-panel px-3 py-2 font-mono break-all select-all">
              {kept.data.url}
            </code>
            <CopyButton text={kept.data.url} label={t('agents.copy')} />
          </div>
          <span className="text-muted">{t('agents.how')}</span>
        </div>
      )}
      {kept.data?.clients.length === 0 && <p className="text-sm">{t('agents.none')}</p>}
      {!!kept.data?.clients.length && (
        <table className="w-full border-collapse">
          <thead className="text-left text-sm text-muted">
            <tr className="border-b border-line">
              <th className="w-full px-2 py-2 font-normal">{t('agents.client')}</th>
              <th className="hidden px-2 py-2 font-normal sm:table-cell">
                {t('agents.connected')}
              </th>
              <th className="px-2 py-2 font-normal whitespace-nowrap">{t('agents.used')}</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {kept.data.clients.map((agent) => (
              <tr key={agent.id} className="border-b border-line">
                <td className={`${cell} max-w-0`}>
                  <p className="flex items-center gap-2 truncate">
                    <Bot size={16} aria-hidden className="shrink-0 text-muted" />
                    {agent.client}
                  </p>
                </td>
                <td className={`${cell} hidden text-sm whitespace-nowrap text-muted sm:table-cell`}>
                  {formatDate(agent.created_at)}
                </td>
                <td className={`${cell} text-sm whitespace-nowrap text-muted`}>
                  {agent.used_at ? formatDate(agent.used_at) : t('users.never')}
                </td>
                <td className="pr-2">
                  <ActionsMenu>
                    <MenuItem
                      icon={Trash2}
                      label={t('agents.revoke')}
                      onSelect={() => setRemoving(agent)}
                    />
                  </ActionsMenu>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {removing && (
        <ConfirmDialog
          heading={t('agents.revokeTitle')}
          confirmLabel={t('agents.revoke')}
          onConfirm={() => remove.mutate(removing)}
          onClose={() => setRemoving(null)}
        >
          <strong>{removing.client}</strong> {t('agents.revokeWarning')}
        </ConfirmDialog>
      )}
    </>
  );
}
