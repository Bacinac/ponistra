import { useEffect, useState } from 'react';
import { useI18n } from './i18n';

/** A compaction under way: when it began, and the usual length of the last ones once any ended. */
export interface Compaction {
  since: string;
  expected: number | null;
}

/** The share of the bar a compaction that outlasts the usual length stops at until it ends. */
const FURTHEST = 0.95;
const SECOND = 1000;

export function Compacting({ compaction }: { compaction: Compaction }) {
  const { t, formatNumber } = useI18n();
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), SECOND);
    return () => clearInterval(timer);
  }, []);
  const elapsed = Math.max(0, now - Date.parse(compaction.since));
  const { expected } = compaction;
  const share = expected ? Math.min(FURTHEST, elapsed / expected) : null;
  const clock = (ms: number) => {
    const seconds = Math.round(ms / SECOND);
    return `${formatNumber(Math.floor(seconds / 60))}:${String(seconds % 60).padStart(2, '0')}`;
  };
  const told =
    expected === null
      ? clock(elapsed)
      : elapsed < expected
        ? `${clock(elapsed)} / ${clock(expected)}`
        : t('workspace.compacting.over');
  return (
    <span className="mt-1 flex min-w-0 items-center gap-2 text-xs text-muted">
      <span
        role="progressbar"
        aria-label={t('workspace.state.compacting')}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={share === null ? undefined : Math.round(share * 100)}
        className="h-1.5 min-w-0 flex-1 overflow-hidden rounded bg-line"
      >
        {share === null ? (
          <span className="block h-full w-full animate-pulse bg-accent" />
        ) : (
          <span
            className="block h-full bg-accent transition-[width] duration-1000 ease-linear"
            style={{ width: `${share * 100}%` }}
          />
        )}
      </span>
      <span className="shrink-0 tabular-nums">{told}</span>
    </span>
  );
}
