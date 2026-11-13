import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CalendarClock, Clock, Pencil, RotateCw, Send, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { deleteJson, getJson, patchJson } from './api';
import { UNSENT, type Unsent } from './compose';
import { ConfirmDialog } from './dialogs';
import { useI18n } from './i18n';
import { dequeue, queue, queued, type Queued, subscribeKeeping, subscribeQueue } from './kept';
import { useReachable } from './live';
import { inBox, type Person, person, useBox } from './mailData';
import { ContextMenuArea, MenuItem } from './menu';
import { useMenuPress } from './press';
import { sideRow } from './styles';
import { codeText, errorMessage } from './tree';
import { WhenDialog } from './when';
import { sendQueued } from './offline';

const LATER = ['mail', 'later'];

function useLater() {
  const box = useBox();
  return useQuery({
    queryKey: [...LATER, box],
    queryFn: () => getJson<{ later: Unsent[] }>(inBox('/api/mail/later', box)),
    select: (data) => data.later,
  });
}

/** What this device wrote without the network and holds until the server is reached (D45); the
 * user's own mailbox alone. */
function useQueued(): Queued[] {
  const box = useBox();
  const [entries, setEntries] = useState<Queued[]>([]);
  useEffect(() => {
    if (box !== null) return;
    let shown = true;
    const read = () =>
      queued().then(
        (found) => shown && setEntries(found),
        (error: unknown) =>
          console.error('reading the mail written without the network failed', error),
      );
    void read();
    const leaving = [subscribeQueue(read), subscribeKeeping(read)];
    return () => {
      shown = false;
      for (const leave of leaving) leave();
    };
  }, [box]);
  return box === null ? entries : [];
}

/** The place of the messages waiting to be sent, once there are any; those that failed show. */
export function LaterLink({ here }: { here: boolean }) {
  const { t, formatNumber } = useI18n();
  const later = useLater();
  const waiting = useQueued();
  const box = useBox();
  const all = [...(later.data ?? []), ...waiting];
  if (all.length === 0) return null;
  const failed = all.filter((each) => each.failed).length;
  return (
    <Link
      to={inBox('/mail/later', box)}
      aria-current={here ? 'page' : undefined}
      className={sideRow}
    >
      <Clock size={16} aria-hidden className="shrink-0 text-muted" />
      <span className="min-w-0 flex-1 truncate">{t('mail.laterTitle')}</span>
      <span className={`text-xs ${failed ? 'font-semibold text-danger' : 'text-muted'}`}>
        {formatNumber(failed || all.length)}
      </span>
    </Link>
  );
}

function recipients(people: { to?: unknown; cc?: unknown }): Person[] {
  return [people.to, people.cc].flatMap((each) => (Array.isArray(each) ? (each as Person[]) : []));
}

/** A message written without the network: it leaves, or is kept unsent on the server, once the
 * server is reached; one the server refused says why. */
function QueuedRow({ entry }: { entry: Queued }) {
  const { t, formatDate } = useI18n();
  const reachable = useReachable();
  const press = useMenuPress();
  const [discarding, setDiscarding] = useState(false);
  const again = useMutation({
    mutationFn: async () => {
      await queue({ ...entry, failed: undefined });
      await sendQueued();
    },
  });
  const status = entry.failed
    ? null
    : entry.send
      ? entry.at
        ? `${t('mail.queuedWaiting')} · ${formatDate(entry.at)}`
        : t('mail.queuedWaiting')
      : t('mail.queuedUnsent');
  return (
    <li className="rounded-md border-b border-line hover:bg-hover">
      <ContextMenuArea
        items={
          <>
            {entry.failed && (
              <MenuItem
                icon={RotateCw}
                label={t('mail.queuedAgain')}
                disabled={!reachable || again.isPending}
                onSelect={() => again.mutate()}
              />
            )}
            <MenuItem
              icon={Trash2}
              label={t('mail.discard')}
              onSelect={() => setDiscarding(true)}
            />
          </>
        }
      >
        <div {...press} className="flex w-full min-w-0 flex-col gap-0.5 px-2 py-2 text-left">
          <span className="flex min-w-0 items-center gap-2">
            <span className="min-w-0 flex-1 truncate">
              {recipients(entry.message).map(person).join(', ') || t('mail.noRecipients')}
            </span>
            {status && <span className="shrink-0 text-xs text-muted">{status}</span>}
          </span>
          <span className="truncate text-sm">{entry.message.subject || t('mail.noSubject')}</span>
          {entry.failed && <span className="text-sm text-danger">{codeText(entry.failed, t)}</span>}
          {again.error && (
            <span className="text-sm text-danger">{errorMessage(again.error, t)}</span>
          )}
        </div>
      </ContextMenuArea>
      {discarding && (
        <ConfirmDialog
          heading={t('mail.discardTitle')}
          confirmLabel={t('mail.discard')}
          onConfirm={() => void dequeue(entry.key)}
          onClose={() => setDiscarding(false)}
        >
          {t('mail.discardWarning')}
        </ConfirmDialog>
      )}
    </li>
  );
}

function LaterRow({ unsent, onEdit }: { unsent: Unsent; onEdit: (unsent: Unsent) => void }) {
  const { t, formatDate } = useI18n();
  const reachable = useReachable();
  const queryClient = useQueryClient();
  const press = useMenuPress();
  const [asking, setAsking] = useState<'when' | 'discard' | null>(null);
  const settled = () => {
    void queryClient.invalidateQueries({ queryKey: LATER });
    void queryClient.invalidateQueries({ queryKey: UNSENT });
  };
  const moved = useMutation({
    mutationFn: (at: Date | null) =>
      patchJson<Unsent>(`/api/mail/later/${unsent.id}`, { at: at && at.toISOString() }),
    onSuccess: (changed) => {
      setAsking(null);
      settled();
      if (changed.send_at === null) onEdit(changed);
    },
  });
  const discarded = useMutation({
    mutationFn: () => deleteJson(`/api/mail/unsent/${unsent.id}`),
    onSuccess: settled,
  });
  const failure = moved.error ?? discarded.error;
  return (
    <li className="rounded-md border-b border-line hover:bg-hover">
      <ContextMenuArea
        items={
          <>
            <MenuItem
              icon={Pencil}
              label={t('mail.laterEdit')}
              disabled={!reachable}
              onSelect={() => moved.mutate(null)}
            />
            <MenuItem
              icon={Send}
              label={t('mail.laterNow')}
              disabled={!reachable}
              onSelect={() => moved.mutate(new Date())}
            />
            <MenuItem
              icon={CalendarClock}
              label={t('mail.laterMove')}
              disabled={!reachable}
              onSelect={() => setAsking('when')}
            />
            <MenuItem
              icon={Trash2}
              label={t('mail.discard')}
              disabled={!reachable}
              onSelect={() => setAsking('discard')}
            />
          </>
        }
      >
        <button
          type="button"
          disabled={unsent.sending || !reachable}
          {...press}
          onClick={() => moved.mutate(null)}
          className="flex w-full min-w-0 flex-col gap-0.5 px-2 py-2 text-left"
        >
          <span className="flex min-w-0 items-center gap-2">
            <span className="min-w-0 flex-1 truncate">
              {[...unsent.to, ...unsent.cc].map(person).join(', ') || t('mail.noRecipients')}
            </span>
            <span className="shrink-0 text-xs text-muted">
              {unsent.sending ? t('mail.sending') : unsent.send_at && formatDate(unsent.send_at)}
            </span>
          </span>
          <span className="truncate text-sm">{unsent.subject || t('mail.noSubject')}</span>
          {unsent.failed && (
            <span className="text-sm text-danger">{codeText(unsent.failed, t)}</span>
          )}
          {failure && <span className="text-sm text-danger">{errorMessage(failure, t)}</span>}
        </button>
      </ContextMenuArea>
      {asking === 'when' && (
        <WhenDialog
          heading={t('mail.laterMove')}
          confirmLabel={t('mail.later')}
          pending={moved.isPending}
          error={moved.error}
          onChoose={(at) => moved.mutate(at)}
          onClose={() => setAsking(null)}
        />
      )}
      {asking === 'discard' && (
        <ConfirmDialog
          heading={t('mail.discardTitle')}
          confirmLabel={t('mail.discard')}
          onConfirm={() => discarded.mutate()}
          onClose={() => setAsking(null)}
        >
          {t('mail.discardWarning')}
        </ConfirmDialog>
      )}
    </li>
  );
}

/** The messages waiting for their moment to leave, the soonest first; opening one takes it off
 * its moment, so that it does not leave while the user is changing it. */
export function LaterList({ onEdit }: { onEdit: (unsent: Unsent) => void }) {
  const { t } = useI18n();
  const later = useLater();
  const waiting = useQueued();
  if (later.data?.length === 0 && waiting.length === 0)
    return <p className="p-4 text-sm text-muted">{t('mail.laterNone')}</p>;
  return (
    <ul aria-label={t('mail.laterTitle')} className="flex flex-col">
      {waiting.map((each) => (
        <QueuedRow key={each.key} entry={each} />
      ))}
      {later.data?.map((each) => (
        <LaterRow key={each.id} unsent={each} onEdit={onEdit} />
      ))}
    </ul>
  );
}
