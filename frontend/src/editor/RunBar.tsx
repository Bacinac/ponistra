import { LoaderCircle, X } from 'lucide-react';
import { useState } from 'react';
import { isMessageKey, useI18n } from '../i18n';
import { iconButton } from '../styles';
import { actionLabel } from './actions';
import type { Missed, Run, Running } from './runs';

/** The runs of actions under way in the tab, whoever started them, a model's with Stop where the
 * user may edit, and the user's last one done or stopped, which they can take back where it
 * changed anything, with the documents it missed and what its model said. Inline, it stands
 * where it is put instead of over the page. */
export function RunBar({
  running,
  done,
  inline = false,
  onStop,
  onUndo,
  onClose,
  onOpen,
}: {
  running: readonly Running[];
  done: Run | null;
  inline?: boolean;
  onStop: ((run: string) => void) | null;
  onUndo: () => void;
  onClose: () => void;
  /** Opens what the run made. */
  onOpen?: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const [stopped, setStopped] = useState<ReadonlySet<string>>(new Set());
  if (running.length === 0 && !done) return null;
  return (
    <div
      role="status"
      className={`${inline ? 'self-center' : 'fixed bottom-4 left-1/2 z-40 -translate-x-1/2'} flex max-w-[calc(100vw-2rem)] flex-col gap-1 rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink shadow-lg`}
    >
      {running.map((each) => (
        <p key={each.run} className="flex items-center gap-2">
          <LoaderCircle aria-hidden className="size-4 shrink-0 animate-spin text-muted" />
          <span className="truncate">
            {t(actionLabel(each.action))}
            {each.model && <span className="text-muted"> · {t('run.writing')}</span>}
            {each.of !== undefined && (
              <span className="text-muted">
                {' '}
                · {t('run.through')}: {formatNumber(each.through ?? 0)} / {formatNumber(each.of)}
              </span>
            )}
            {each.user && (
              <span className="text-muted">
                {' '}
                · {each.via ? `${each.via} ${t('run.via')} ${each.user.name}` : each.user.name}
              </span>
            )}
          </span>
          {each.model && onStop && (
            <button
              type="button"
              disabled={stopped.has(each.run)}
              onClick={() => {
                setStopped((kept) => new Set(kept).add(each.run));
                onStop(each.run);
              }}
              className="shrink-0 rounded px-2 py-1 font-medium text-link hover:bg-hover disabled:text-muted"
            >
              {t(stopped.has(each.run) ? 'run.stopping' : 'run.stop')}
            </button>
          )}
        </p>
      ))}
      {done && (
        <p className="flex items-center gap-3">
          <span className="truncate">
            {t(done.state === 'stopped' ? 'run.stopped' : 'run.done')}:{' '}
            {t(actionLabel(done.action))}
            {done.items && done.items.missed.length > 0 && (
              <span className="text-muted">
                {' '}
                · {t('run.missed')}: {formatNumber(done.items.missed.length)}
              </span>
            )}
          </span>
          {onOpen && (
            <button
              type="button"
              onClick={onOpen}
              className="shrink-0 rounded px-2 py-1 font-medium text-link hover:bg-hover"
            >
              {t('run.open')}
            </button>
          )}
          {done.changed && (
            <button
              type="button"
              onClick={onUndo}
              className="shrink-0 rounded px-2 py-1 font-medium text-link hover:bg-hover"
            >
              {t('run.undo')}
            </button>
          )}
          <button
            type="button"
            aria-label={t('frame.close')}
            onClick={onClose}
            className={iconButton}
          >
            <X aria-hidden className="size-4" />
          </button>
        </p>
      )}
      {done?.items && done.items.missed.length > 0 && (
        <ul className="max-w-prose text-muted">
          {done.items.missed.map((missed, at) => (
            <li key={at}>
              {done.action === 'file.translate'
                ? `${t('pdf.page')} ${formatNumber(Number(missed.title))}`
                : missed.title}
              : <Why missed={missed} />
            </li>
          ))}
        </ul>
      )}
      {done?.reply && <p className="max-w-prose whitespace-pre-line">{done.reply}</p>}
    </div>
  );
}

function Why({ missed }: { missed: Missed }) {
  const { t } = useI18n();
  const key = `error.${missed.error}`;
  return isMessageKey(key) ? t(key) : missed.error;
}
