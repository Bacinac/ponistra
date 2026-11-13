import { ArrowDownUp, Cpu, HardDrive, MemoryStick, type LucideIcon } from 'lucide-react';
import { Fragment, useId } from 'react';
import { formatSize } from './explorer';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';

export interface Limit {
  kind: 'session' | 'week' | 'model';
  name: string | null;
  percent: number;
  resets: string;
}

/** The plan's limits as the workspace last measured them, or why it could not (KR21). */
export interface Usage {
  at: string | null;
  windows: Limit[];
  credits: { used: number; currency: string; using: boolean } | null;
  error: string | null;
}

/** The machine the workspace runs on, as the workspace measured it when it was last read (KR29). */
export interface Host {
  at: string;
  load: number | null;
  cpus: number | null;
  memory: { total: number; available: number } | null;
  swap: { total: number; free: number } | null;
  disk: { total: number; free: number } | null;
  error: string | null;
}

const NAMED: Record<'session' | 'week', MessageKey> = {
  session: 'workspace.limits.session',
  week: 'workspace.limits.week',
};
// As the owner's push says the weekly limit runs out (`notices.LIMITED`).
const NEAR = 80;

const HEADING = 'text-[11px] font-semibold uppercase tracking-wide text-muted';

function useWhen() {
  const { formatTime, formatDay } = useI18n();
  const today = formatDay(new Date());
  return (iso: string) => {
    const at = new Date(iso);
    const day = formatDay(at);
    return day === today ? formatTime(at) : `${day} ${formatTime(at)}`;
  };
}

export function Limits({
  usage,
  onMeasure,
  measuring = false,
}: {
  usage: Usage | null;
  onMeasure?: () => void;
  measuring?: boolean;
}) {
  const { t, formatNumber } = useI18n();
  const when = useWhen();
  const heading = useId();
  if (!usage) return null;
  const percent = (value: number) =>
    t('workspace.limits.percent').replace('{percent}', formatNumber(Math.round(value)));
  const measure = () => {
    if (!measuring) onMeasure?.();
  };
  return (
    <section aria-labelledby={heading} className="flex flex-col gap-1.5 text-xs">
      <div className="flex items-baseline justify-between gap-2">
        <h3 id={heading} className={HEADING}>
          {t('workspace.limits')}
        </h3>
        <button
          type="button"
          onClick={measure}
          disabled={!onMeasure || measuring}
          title={t('workspace.limits.measure')}
          aria-busy={measuring}
          className={`rounded text-[11px] text-muted tabular-nums hover:text-accent disabled:hover:text-muted ${measuring ? 'animate-pulse' : ''}`}
        >
          {t('workspace.limits.measured')} {usage.at ? when(usage.at) : '–'}
        </button>
      </div>
      <div
        onClick={measure}
        title={t('workspace.limits.measure')}
        className={`grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2 gap-y-1 ${onMeasure ? 'cursor-pointer' : ''}`}
      >
        {usage.windows.map((limit) => {
          const label = limit.kind === 'model' ? (limit.name ?? '') : t(NAMED[limit.kind]);
          const near = limit.percent >= NEAR;
          const resets = t('workspace.limits.resets').replace('{when}', when(limit.resets));
          return (
            <Fragment key={`${limit.kind} ${limit.name ?? ''}`}>
              <span className="w-14 truncate leading-4 text-muted" title={resets}>
                {label}
              </span>
              <span
                role="meter"
                aria-label={label}
                aria-valuenow={limit.percent}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuetext={`${percent(limit.percent)}, ${resets}`}
                title={resets}
                className="h-1.5 min-w-0 rounded bg-line"
              >
                <span
                  className={`block h-1.5 rounded ${near ? 'bg-danger' : 'bg-accent'}`}
                  style={{ width: `${Math.min(100, limit.percent)}%` }}
                />
              </span>
              <span
                className={`w-10 text-right leading-4 tabular-nums ${near ? 'font-semibold text-danger' : ''}`}
              >
                {percent(limit.percent)}
              </span>
            </Fragment>
          );
        })}
      </div>
      {usage.credits && (
        <p className={usage.credits.using ? 'font-semibold text-danger' : 'text-muted'}>
          {t(usage.credits.using ? 'workspace.limits.spending' : 'workspace.limits.credits')}{' '}
          <span className="tabular-nums">
            {formatNumber(usage.credits.used)} {usage.credits.currency}
          </span>
        </p>
      )}
      {usage.error && (
        <p className="text-danger" title={usage.error}>
          {t('workspace.limits.unread')}
        </p>
      )}
    </section>
  );
}

const FULL = 90;

interface Measure {
  key: string;
  icon: LucideIcon;
  label: MessageKey;
  percent: number;
  detail: string;
}

export function Machine({
  host,
  onMeasure,
  measuring = false,
}: {
  host: Host | null;
  onMeasure?: () => void;
  measuring?: boolean;
}) {
  const { t, formatNumber } = useI18n();
  const when = useWhen();
  const heading = useId();
  if (!host) return null;
  const size = (bytes: number) => formatSize(bytes, formatNumber);
  const shown: Measure[] = [];
  if (host.load !== null && host.cpus)
    shown.push({
      key: 'cpu',
      icon: Cpu,
      label: 'workspace.host.cpu',
      percent: (host.load / host.cpus) * 100,
      detail: t('workspace.host.load')
        .replace('{load}', formatNumber(Math.round(host.load * 100) / 100))
        .replace('{cpus}', formatNumber(host.cpus)),
    });
  const used = (key: string, icon: LucideIcon, label: MessageKey, total: number, free: number) =>
    shown.push({
      key,
      icon,
      label,
      percent: ((total - free) / total) * 100,
      detail: t('workspace.host.used')
        .replace('{used}', size(total - free))
        .replace('{total}', size(total)),
    });
  if (host.memory)
    used('memory', MemoryStick, 'workspace.host.memory', host.memory.total, host.memory.available);
  if (host.swap) used('swap', ArrowDownUp, 'workspace.host.swap', host.swap.total, host.swap.free);
  if (host.disk) used('disk', HardDrive, 'workspace.host.disk', host.disk.total, host.disk.free);
  return (
    <section aria-labelledby={heading} className="flex flex-col gap-1.5 text-xs">
      <h3 id={heading} className={HEADING}>
        {t('workspace.host')}
      </h3>
      {host.error ? (
        <p className="text-danger" title={host.error}>
          {t('workspace.host.unread')}
        </p>
      ) : (
        <button
          type="button"
          onClick={() => {
            if (!measuring) onMeasure?.();
          }}
          disabled={!onMeasure}
          aria-busy={measuring}
          title={`${t('workspace.host.measure')} (${t('workspace.limits.measured')} ${when(host.at)})`}
          className={`flex w-full flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded text-left text-muted hover:text-ink disabled:hover:text-muted ${measuring ? 'animate-pulse' : ''}`}
        >
          {shown.map(({ key, icon: Icon, label, percent, detail }) => (
            <span
              key={key}
              title={`${t(label)}: ${detail}`}
              className={`inline-flex items-center gap-1 tabular-nums ${percent >= FULL ? 'font-semibold text-danger' : ''}`}
            >
              <Icon size={14} aria-hidden />
              <span className="sr-only">{t(label)}</span>
              {t('workspace.limits.percent').replace(
                '{percent}',
                formatNumber(Math.round(percent)),
              )}
            </span>
          ))}
        </button>
      )}
    </section>
  );
}
