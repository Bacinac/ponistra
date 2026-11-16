import { useQuery } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { getJson } from './api';
import { actionLabel } from './editor/actions';
import { Loading } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { field } from './styles';
import { Failure } from './tree';

interface Tokens {
  turns: number;
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
  worth: number;
  unpriced: string[];
}

interface Month extends Tokens {
  month: string;
  api: number;
}

interface Day extends Tokens {
  day: string;
  api: number;
}

interface Limit {
  at: string;
  session: number | null;
  week: number | null;
}

/** The tokens the workspace's chats took and what PONISTRA's own model runs cost (PJ3). */
interface Spent {
  months: Month[];
  month: string;
  days: Day[];
  projects: (Tokens & { project: string })[];
  models: (Tokens & { name: string })[];
  rounds: (Tokens & { round: string })[];
  chats: (Tokens & { chat: string; project: string; title: string | null })[];
  actions: { action: string; runs: number; cost: number }[];
  limits: Limit[];
  rate: number | null;
}

const cell = 'px-2 py-2 whitespace-nowrap';
const number = `${cell} text-right tabular-nums`;
const COLUMNS: { key: keyof Tokens & string; label: MessageKey }[] = [
  { key: 'input', label: 'workspace.spend.input' },
  { key: 'output', label: 'workspace.spend.output' },
  { key: 'cache_read', label: 'workspace.spend.cacheRead' },
  { key: 'cache_write', label: 'workspace.spend.cacheWrite' },
];

function useSpent(month: string | null) {
  return useQuery({
    queryKey: ['worked', 'spend', month],
    queryFn: () =>
      getJson<Spent>(`/api/workspace/spend${month ? `?month=${encodeURIComponent(month)}` : ''}`),
    placeholderData: (previous) => previous,
  });
}

function local(day: string): Date {
  const [year, month, date] = day.split('-').map(Number);
  return new Date(year, month - 1, date);
}

function useFormats(rate: number | null) {
  const { t, formatNumber, formatAmount } = useI18n();
  const tokens = (value: number) =>
    value >= 1_000_000
      ? t('workspace.spend.millions').replace(
          '{count}',
          formatNumber(Math.round(value / 100_000) / 10),
        )
      : value >= 1_000
        ? t('workspace.spend.thousands').replace('{count}', formatNumber(Math.round(value / 1_000)))
        : formatNumber(value);
  const dollars = (value: number) =>
    t('workspace.spend.dollars').replace('{amount}', formatAmount(value));
  const worth = (row: Tokens) =>
    row.unpriced.length && !row.worth
      ? '—'
      : `${dollars(row.worth)}${row.unpriced.length ? '*' : ''}`;
  const week = (row: Tokens) =>
    rate === null || !row.worth
      ? '·'
      : t('workspace.spend.ofWeek').replace(
          '{percent}',
          formatNumber(Math.round(row.worth * rate * 10) / 10),
        );
  return { tokens, dollars, worth, week };
}

function Table({
  heading,
  first,
  rows,
  rate,
}: {
  heading: string;
  first: string;
  rows: { key: string; label: ReactNode; tokens: Tokens }[];
  rate: number | null;
}) {
  const { t } = useI18n();
  const shown = useFormats(rate);
  if (!rows.length) return null;
  return (
    <section aria-label={heading} className="flex flex-col gap-2">
      <h2 className="text-base font-semibold">{heading}</h2>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="text-left text-muted">
            <tr className="border-b border-line">
              <th className={`${cell} font-normal`}>{first}</th>
              {COLUMNS.map((column) => (
                <th key={column.key} className={`${number} font-normal`}>
                  {t(column.label)}
                </th>
              ))}
              <th className={`${number} font-normal`}>{t('workspace.spend.worth')}</th>
              <th className={`${number} font-normal`}>{t('workspace.spend.week')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-b border-line">
                <td className={`${cell} max-w-72 truncate`}>{row.label}</td>
                {COLUMNS.map((column) => (
                  <td key={column.key} className={number}>
                    {shown.tokens(row.tokens[column.key] as number)}
                  </td>
                ))}
                <td className={`${number} font-semibold`}>{shown.worth(row.tokens)}</td>
                <td className={`${number} text-muted`}>{shown.week(row.tokens)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** The highest five-hour window and the last weekly one measured on each day. */
function limitsByDay(
  limits: Limit[],
): Map<string, { session: number | null; week: number | null }> {
  const found = new Map<string, { session: number | null; week: number | null }>();
  for (const each of limits) {
    const at = new Date(each.at);
    const day = `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, '0')}-${String(at.getDate()).padStart(2, '0')}`;
    const held = found.get(day) ?? { session: null, week: null };
    if (each.session !== null) held.session = Math.max(held.session ?? 0, each.session);
    if (each.week !== null) held.week = each.week;
    found.set(day, held);
  }
  return found;
}

/** What the workspace's chats took of Anthropic (PJ3): each month, and the chosen month by
    project, model, round, chat and day, beside the plan's limits and PONISTRA's own model runs. */
export function Spend({ named }: { named: (project: string) => string }) {
  const { t, formatMonth, formatShortDay, formatNumber } = useI18n();
  const [month, setMonth] = useState<string | null>(null);
  const spent = useSpent(month);
  const formats = useFormats(spent.data?.rate ?? null);
  if (spent.isPending) return <Loading />;
  if (spent.isError) return <Failure error={spent.error} />;
  const { months, days, rate } = spent.data;
  const shown = months.find((each) => each.month === spent.data.month) ?? null;
  if (!shown) return <p className="text-sm text-muted">{t('workspace.spend.none')}</p>;
  const limits = limitsByDay(spent.data.limits);
  const percent = (value: number | null | undefined) =>
    value === null || value === undefined
      ? '·'
      : t('workspace.limits.percent').replace('{percent}', formatNumber(Math.round(value)));
  const unpriced = [...new Set(spent.data.models.flatMap((each) => each.unpriced))];
  return (
    <div className="flex min-h-0 flex-col gap-6 overflow-y-auto">
      <section aria-label={t('workspace.hours.month')} className="flex flex-col gap-2">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted">{t('workspace.hours.month')}</span>
          <select
            value={shown.month}
            onChange={(event) => setMonth(event.target.value)}
            className={`${field} w-auto`}
          >
            {months.map((each) => (
              <option key={each.month} value={each.month}>
                {formatMonth(each.month)}
              </option>
            ))}
          </select>
        </label>
        <table className="w-full max-w-md border-collapse text-sm">
          <tbody>
            {COLUMNS.map((column) => (
              <tr key={column.key} className="border-b border-line">
                <td className={`${cell} w-full`}>{t(column.label)}</td>
                <td className={number}>{formats.tokens(shown[column.key] as number)}</td>
              </tr>
            ))}
            <tr className="border-b border-line font-semibold">
              <td className={cell}>{t('workspace.spend.worth')}</td>
              <td className={number}>{formats.worth(shown)}</td>
            </tr>
            <tr className="text-muted">
              <td className={cell}>{t('workspace.spend.api')}</td>
              <td className={number}>{formats.dollars(shown.api)}</td>
            </tr>
          </tbody>
        </table>
        {unpriced.length > 0 && (
          <p className="text-xs text-muted">
            {t('workspace.spend.unpriced').replace('{models}', unpriced.join(', '))}
          </p>
        )}
      </section>
      <Table
        heading={t('workspace.spend.projects')}
        first={t('workspace.spend.project')}
        rate={rate}
        rows={spent.data.projects.map((each) => ({
          key: each.project,
          label: named(each.project),
          tokens: each,
        }))}
      />
      <Table
        heading={t('workspace.spend.models')}
        first={t('workspace.spend.model')}
        rate={rate}
        rows={spent.data.models.map((each) => ({ key: each.name, label: each.name, tokens: each }))}
      />
      <Table
        heading={t('workspace.spend.rounds')}
        first={t('workspace.spend.round')}
        rate={rate}
        rows={spent.data.rounds.map((each) => ({
          key: each.round,
          label: each.round,
          tokens: each,
        }))}
      />
      <Table
        heading={t('workspace.spend.chats')}
        first={t('workspace.spend.chat')}
        rate={rate}
        rows={spent.data.chats.map((each) => ({
          key: each.chat,
          label: (
            <span title={each.chat}>
              {each.title ?? each.chat.slice(0, 8)}{' '}
              <span className="text-muted">{named(each.project)}</span>
            </span>
          ),
          tokens: each,
        }))}
      />
      <section aria-label={t('workspace.hours.days')} className="flex flex-col gap-2">
        <h2 className="text-base font-semibold">{t('workspace.hours.days')}</h2>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="text-left text-muted">
              <tr className="border-b border-line">
                <th className={`${cell} font-normal`}>{t('workspace.hours.day')}</th>
                <th className={`${number} font-normal`}>{t('workspace.spend.turns')}</th>
                <th className={`${number} font-normal`}>{t('workspace.spend.worth')}</th>
                <th className={`${number} font-normal`}>{t('workspace.spend.session')}</th>
                <th className={`${number} font-normal`}>{t('workspace.limits.week')}</th>
                <th className={`${number} font-normal`}>{t('workspace.spend.api')}</th>
              </tr>
            </thead>
            <tbody>
              {days.map((day) => (
                <tr key={day.day} className="border-b border-line">
                  <td className={cell}>{formatShortDay(local(day.day))}</td>
                  <td className={number}>{formatNumber(day.turns)}</td>
                  <td className={`${number} font-semibold`}>{formats.worth(day)}</td>
                  <td className={number}>{percent(limits.get(day.day)?.session)}</td>
                  <td className={number}>{percent(limits.get(day.day)?.week)}</td>
                  <td className={`${number} text-muted`}>
                    {day.api ? formats.dollars(day.api) : '·'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {spent.data.actions.length > 0 && (
        <section aria-label={t('workspace.spend.actions')} className="flex flex-col gap-2">
          <h2 className="text-base font-semibold">{t('workspace.spend.actions')}</h2>
          <table className="w-full max-w-md border-collapse text-sm">
            <tbody>
              {spent.data.actions.map((each) => (
                <tr key={each.action} className="border-b border-line">
                  <td className={`${cell} w-full`}>{t(actionLabel(each.action))}</td>
                  <td className={`${number} text-muted`}>{formatNumber(each.runs)}</td>
                  <td className={number}>{formats.dollars(each.cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
