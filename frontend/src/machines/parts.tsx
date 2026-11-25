import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { formatSize } from '../explorer';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';

export function useFormats() {
  const { formatNumber, formatDate } = useI18n();
  return {
    bytes: (value: number) => formatSize(value, formatNumber),
    rate: (value: number) => `${formatSize(value, formatNumber)}/s`,
    percent: (value: number) => `${formatNumber(Math.round(value * 10) / 10)} %`,
    number: (value: number) => formatNumber(Math.round(value * 100) / 100),
    date: (iso: string | null | undefined) => (iso ? formatDate(iso) : '—'),
  };
}

/** What a request to the machine answered instead of its data, said where the data would be. */
export function Failure({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-danger">
      {error.message}
    </p>
  );
}

export function Loaded<T>({
  query,
  children,
}: {
  query: UseQueryResult<T, Error>;
  children: (data: T) => ReactNode;
}) {
  const { t } = useI18n();
  if (query.data !== undefined) return children(query.data);
  if (query.error) return <Failure error={query.error} />;
  return <p className="text-sm text-muted">{t('machine.loading')}</p>;
}

export type Tone = 'ok' | 'bad' | 'quiet';

const TONES: Record<Tone, string> = {
  ok: 'border-accent text-accent',
  bad: 'border-danger text-danger',
  quiet: 'border-line text-muted',
};

export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

export function Facts({ children }: { children: ReactNode }) {
  return (
    <dl className="grid grid-cols-[minmax(8rem,max-content)_1fr] gap-x-6 gap-y-1.5 text-sm">
      {children}
    </dl>
  );
}

export function Fact({ label, children }: { label: MessageKey; children: ReactNode }) {
  const { t } = useI18n();
  return (
    <>
      <dt className="text-muted">{t(label)}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </>
  );
}

/** A share filled, as a bar with its percent beside it. */
export function Meter({ share, label }: { share: number; label: string }) {
  const { percent } = useFormats();
  const clamped = Math.max(0, Math.min(100, share));
  return (
    <div className="flex items-center gap-2">
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(clamped)}
        className="h-2 min-w-24 flex-1 overflow-hidden rounded-full bg-panel"
      >
        <div
          className={`h-full rounded-full ${clamped >= 90 ? 'bg-danger' : 'bg-accent'}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="w-14 shrink-0 text-right text-xs text-muted tabular-nums">
        {percent(clamped)}
      </span>
    </div>
  );
}

export const card = 'flex flex-col gap-3 rounded-lg border border-line bg-raised p-4';

export const table =
  'w-full border-collapse text-sm [&_td]:py-1.5 [&_td]:pr-4 [&_th]:pb-1.5 [&_th]:pr-4 [&_th]:text-left [&_th]:font-medium [&_th]:text-muted [&_tbody_tr]:border-t [&_tbody_tr]:border-line';
