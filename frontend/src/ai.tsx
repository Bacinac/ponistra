import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router';
import { deleteJson, getJson, patchJson } from './api';
import { useSession } from './auth';
import { actionLabel } from './editor/actions';
import { Loaded, Loading } from './frame';
import { AdminFrame } from './settings';
import { useI18n } from './i18n';
import { SPEECH } from './voice';
import { button, compactField, primaryButton } from './styles';
import { Headed, inline, inlineField } from './headed';
import { errorMessage, Failure } from './tree';

/** The installation's AI as the server tells an administrator: never its key, only how it
 * ends. */
interface Setting {
  enabled: boolean;
  hint: string;
  lost: boolean;
  changed_at: string | null;
  /** Dollars each user's runs may take in a calendar month, the models' setting alone. */
  monthly?: number | null;
}

/** What the installation's models took in a month for one action. */
interface Spent {
  month: string;
  action: string;
  runs: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  /** Dollars, of the runs whose models have a price. */
  cost: number | null;
  unpriced: number;
}

/** A free request as its users worded it, how often it was asked and when last. */
interface Asked {
  text: string;
  times: number;
  last: string;
}

const cell = 'px-2 py-2 whitespace-nowrap';
const number = `${cell} text-right tabular-nums`;

function Usage() {
  const { t, formatDate, formatMonth, formatNumber } = useI18n();
  const usage = useQuery({
    queryKey: ['ai-usage'],
    queryFn: () => getJson<{ spent: Spent[]; requests: Asked[] }>('/api/runs/usage'),
  });
  if (usage.isPending) return <Loading />;
  if (usage.isError) return <Failure error={usage.error} />;
  const { spent, requests } = usage.data;
  return (
    <>
      <Headed heading={t('ai.usage.heading')}>
        {spent.length === 0 ? (
          <p className="text-sm text-muted">{t('ai.usage.none')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead className="text-left text-muted">
                <tr className="border-b border-line">
                  <th className={`${cell} font-normal`}>{t('ai.usage.month')}</th>
                  <th className={`${cell} w-full font-normal`}>{t('ai.usage.action')}</th>
                  <th className={`${number} font-normal`}>{t('ai.usage.runs')}</th>
                  <th className={`${number} font-normal`}>{t('ai.usage.input')}</th>
                  <th className={`${number} font-normal`}>{t('ai.usage.output')}</th>
                  <th className={`${number} font-normal`}>{t('ai.usage.cost')}</th>
                </tr>
              </thead>
              <tbody>
                {spent.map((row, at) => (
                  <tr key={`${row.month} ${row.action}`} className="border-b border-line">
                    <td className={cell}>
                      {spent[at - 1]?.month !== row.month && formatMonth(row.month)}
                    </td>
                    <td className={cell}>{t(actionLabel(row.action))}</td>
                    <td className={number}>{formatNumber(row.runs)}</td>
                    <td className={number}>
                      {formatNumber(
                        row.input_tokens + row.cache_read_tokens + row.cache_write_tokens,
                      )}
                    </td>
                    <td className={number}>{formatNumber(row.output_tokens)}</td>
                    <td className={number}>
                      {row.cost === null ? '–' : formatNumber(row.cost)}
                      {row.unpriced > 0 && (
                        <span className="block text-xs text-danger">
                          {formatNumber(row.unpriced)} {t('ai.usage.unpriced')}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Headed>
      <Headed heading={t('ai.requests.heading')}>
        {requests.length === 0 ? (
          <p className="text-sm text-muted">{t('ai.requests.none')}</p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="text-left text-muted">
              <tr className="border-b border-line">
                <th className={`${cell} w-full font-normal`}>{t('ai.requests.request')}</th>
                <th className={`${number} font-normal`}>{t('ai.requests.times')}</th>
                <th className={`${cell} hidden font-normal sm:table-cell`}>
                  {t('ai.requests.last')}
                </th>
              </tr>
            </thead>
            <tbody>
              {requests.map((asked) => (
                <tr key={asked.text} className="border-b border-line">
                  <td className="max-w-0 px-2 py-2">
                    <p className="whitespace-pre-line break-words">{asked.text}</p>
                  </td>
                  <td className={number}>{formatNumber(asked.times)}</td>
                  <td className={`${cell} hidden text-muted sm:table-cell`}>
                    {formatDate(asked.last)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Headed>
    </>
  );
}

/** An installation's key for a model and whether it is used: the form is the same for every
 * provider. */
function KeyForm({
  path,
  setting,
  heading,
  enabledLabel,
  keyLabel,
  onSaved,
}: {
  path: string;
  setting: Setting;
  heading: string;
  enabledLabel: string;
  keyLabel: string;
  onSaved: (saved: Setting) => void;
}) {
  const { t, formatDate } = useI18n();
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState('');
  const save = useMutation({
    mutationFn: (change: { enabled?: boolean; key?: string }) => patchJson<Setting>(path, change),
    onSuccess: (saved) => {
      onSaved(saved);
      setKey('');
      setOpen(false);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate({ key: key.trim() });
  };
  const kept = setting.hint !== '' && !setting.lost;
  return (
    <Headed
      heading={heading}
      action={
        !open && (
          <button
            type="button"
            onClick={() => {
              save.reset();
              setOpen(true);
            }}
            className={button}
          >
            {t(kept ? 'ai.keyChange' : 'ai.keyAdd')}
          </button>
        )
      }
    >
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={setting.enabled}
          disabled={save.isPending}
          onChange={(event) => save.mutate({ enabled: event.target.checked })}
        />
        {enabledLabel}
      </label>
      {open && (
        <form onSubmit={submit} className={inline}>
          <label className={inlineField}>
            {keyLabel}
            <input
              type="password"
              required
              autoFocus
              autoComplete="new-password"
              spellCheck={false}
              value={key}
              onChange={(event) => setKey(event.target.value)}
              className={compactField}
            />
          </label>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              setKey('');
            }}
            className={button}
          >
            {t('tree.cancel')}
          </button>
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t('ai.save')}
          </button>
        </form>
      )}
      {kept && (
        <p className="text-sm text-muted">
          {t('ai.keyKept')} …{setting.hint}
          {setting.changed_at && ` · ${t('ai.changed')}: ${formatDate(setting.changed_at)}`}
        </p>
      )}
      {setting.lost && <p className="text-sm text-danger">{t('ai.keyLost')}</p>}
      {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
    </Headed>
  );
}

/** How much each user's runs may take in a month, none for no bound. */
function MonthlyForm({
  setting,
  onSaved,
}: {
  setting: Setting;
  onSaved: (saved: Setting) => void;
}) {
  const { t } = useI18n();
  const shown = setting.monthly == null ? '' : String(setting.monthly);
  const [monthly, setMonthly] = useState(shown);
  const save = useMutation({
    mutationFn: () =>
      patchJson<Setting>('/api/ai', { monthly: monthly.trim() === '' ? null : Number(monthly) }),
    onSuccess: onSaved,
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <Headed
      heading={t('ai.monthly')}
      action={
        <form onSubmit={submit} className="flex items-center gap-2">
          <input
            type="number"
            inputMode="decimal"
            aria-label={t('ai.monthly')}
            min={0}
            step={0.01}
            value={monthly}
            placeholder={t('ai.monthlyNone')}
            onChange={(event) => setMonthly(event.target.value)}
            className={`${compactField} w-32`}
          />
          <button
            type="submit"
            disabled={save.isPending || monthly === shown}
            className={primaryButton}
          >
            {t('ai.save')}
          </button>
        </form>
      }
    >
      {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
    </Headed>
  );
}

function SpeechForm() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const setting = useQuery({
    queryKey: ['ai-speech'],
    queryFn: () => getJson<Setting>('/api/ai/speech'),
  });
  if (setting.isPending) return <Loading />;
  if (setting.isError) return <Failure error={setting.error} />;
  return (
    <KeyForm
      path="/api/ai/speech"
      setting={setting.data}
      heading={t('speech.heading')}
      enabledLabel={t('speech.enabled')}
      keyLabel={t('speech.key')}
      onSaved={(saved) => {
        queryClient.setQueryData(['ai-speech'], saved);
        void queryClient.invalidateQueries({ queryKey: SPEECH });
      }}
    />
  );
}

function Settings({ setting }: { setting: Setting }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  return (
    <AdminFrame title={t('ai.title')}>
      <div className="flex w-full max-w-3xl flex-col gap-8">
        <KeyForm
          path="/api/ai"
          setting={setting}
          heading={t('ai.claude')}
          enabledLabel={t('ai.enabled')}
          keyLabel={t('ai.key')}
          onSaved={(saved) => {
            queryClient.setQueryData(['ai'], saved);
            void queryClient.invalidateQueries({ queryKey: ['actions'] });
          }}
        />
        <MonthlyForm
          setting={setting}
          onSaved={(saved) => queryClient.setQueryData(['ai'], saved)}
        />
        <SpeechForm />
        <Usage />
      </div>
    </AdminFrame>
  );
}

export function AiPage() {
  const me = useSession().data?.user;
  const setting = useQuery({
    queryKey: ['ai'],
    queryFn: () => getJson<Setting>('/api/ai'),
    enabled: !!me?.is_admin,
  });
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return <Loaded query={setting}>{(data) => <Settings setting={data} />}</Loaded>;
}

/** Whether the document's editors run its AI actions without being asked each time, and
 * withdrawing that. */
export function useConsent(document: string, enabled: boolean) {
  const queryClient = useQueryClient();
  const key = ['ai-consent', document];
  const consent = useQuery({
    queryKey: key,
    queryFn: () => getJson<{ consent: { given_at: string } | null }>(`/api/nodes/${document}/ai`),
    enabled,
  });
  const withdraw = useMutation({
    mutationFn: () => deleteJson(`/api/nodes/${document}/ai`),
    onSuccess: () => queryClient.setQueryData(key, { consent: null }),
  });
  return { given: consent.data?.consent ?? null, withdraw };
}
