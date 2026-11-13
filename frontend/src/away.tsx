import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { deleteJson, getJson, putJson } from './api';
import { Labelled } from './dialogs';
import { Loading } from './frame';
import { useI18n } from './i18n';
import { button, field, primaryButton } from './styles';
import { codeText, errorMessage } from './tree';
import { day } from './when';

export interface Away {
  starts_at: string;
  ends_at: string;
  text_hr: string;
  text_en: string;
  failed: string;
}

const AWAY = ['mail', 'away'];

/** The last day of a time away, whose end is the moment after it. */
export function lastDay(ends: string): Date {
  return new Date(new Date(ends).getTime() - 1);
}

function dayStart(given: string, after = 0): Date {
  const [year, month, date] = given.split('-').map(Number);
  return new Date(year, month - 1, date + after);
}

function AwayForm({ away }: { away: Away | null }) {
  const { t, formatDays } = useI18n();
  const queryClient = useQueryClient();
  const [first, setFirst] = useState(away ? day(new Date(away.starts_at)) : '');
  const [last, setLast] = useState(away ? day(lastDay(away.ends_at)) : '');
  const [hr, setHr] = useState(away?.text_hr ?? '');
  const [en, setEn] = useState(away?.text_en ?? '');
  const done = () => queryClient.invalidateQueries({ queryKey: AWAY });
  const save = useMutation({
    mutationFn: () =>
      putJson('/api/mail/away', {
        starts_at: dayStart(first).toISOString(),
        ends_at: dayStart(last, 1).toISOString(),
        text_hr: hr,
        text_en: en,
      }),
    onSuccess: done,
  });
  const off = useMutation({ mutationFn: () => deleteJson('/api/mail/away'), onSuccess: done });
  const ready = first !== '' && last !== '' && first <= last && Boolean(hr.trim() || en.trim());
  const failure = save.error ?? off.error;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <form onSubmit={submit} className="flex max-w-xl flex-col gap-3">
      {away && (
        <p className="text-sm text-muted">
          {t('away.period').replace(
            '{when}',
            formatDays(day(new Date(away.starts_at)), day(lastDay(away.ends_at))),
          )}
        </p>
      )}
      {away?.failed && (
        <p className="text-sm text-danger">
          {t('away.failed')} {codeText(away.failed, t)}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Labelled label={t('away.first')}>
          {(id) => (
            <input
              id={id}
              type="date"
              value={first}
              onChange={(event) => setFirst(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <Labelled label={t('away.last')}>
          {(id) => (
            <input
              id={id}
              type="date"
              value={last}
              min={first || day(new Date())}
              onChange={(event) => setLast(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
      </div>
      <Labelled label={t('away.textHr')}>
        {(id) => (
          <textarea
            id={id}
            rows={5}
            value={hr}
            onChange={(event) => setHr(event.target.value)}
            className={field}
          />
        )}
      </Labelled>
      <Labelled label={t('away.textEn')}>
        {(id) => (
          <textarea
            id={id}
            rows={5}
            value={en}
            onChange={(event) => setEn(event.target.value)}
            className={field}
          />
        )}
      </Labelled>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={!ready || save.isPending} className={primaryButton}>
          {t('away.save')}
        </button>
        {away && (
          <button
            type="button"
            disabled={off.isPending}
            onClick={() => off.mutate()}
            className={button}
          >
            {t('away.off')}
          </button>
        )}
      </div>
    </form>
  );
}

export function AwaySettings() {
  const { t } = useI18n();
  const found = useQuery({
    queryKey: AWAY,
    queryFn: () => getJson<{ away: Away | null }>('/api/mail/away'),
  });
  if (!found.data)
    return found.isError ? (
      <p className="text-sm text-danger">{errorMessage(found.error, t)}</p>
    ) : (
      <Loading />
    );
  return <AwayForm key={found.data.away?.ends_at ?? 'none'} away={found.data.away} />;
}

/** Who of the others in a talk of a few is away now. */
export function AwayNote({ conversation }: { conversation: string }) {
  const { t, formatDay } = useI18n();
  const found = useQuery({
    queryKey: ['away', conversation],
    queryFn: () =>
      getJson<{ away: { name: string; ends_at: string }[] }>(`/api/mail/away/in/${conversation}`),
  });
  if (!found.data?.away.length) return null;
  return (
    <p className="text-sm text-muted">
      {t('away.then')}:{' '}
      {found.data.away
        .map(
          (each) =>
            `${each.name} (${t('away.until').replace('{when}', formatDay(lastDay(each.ends_at)))})`,
        )
        .join(', ')}
    </p>
  );
}
