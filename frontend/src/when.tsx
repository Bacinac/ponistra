import { useState, type FormEvent } from 'react';
import { Close, Modal } from './dialogs';
import { useI18n } from './i18n';
import { button, field, primaryButton } from './styles';
import { errorMessage } from './tree';

const MORNING = 8;

function morning(days: number, from: Date): Date {
  return new Date(from.getFullYear(), from.getMonth(), from.getDate() + days, MORNING);
}

function nextMonday(from: Date): number {
  return ((8 - from.getDay()) % 7 || 7) as number;
}

export function day(moment: Date): string {
  const pad = (given: number) => String(given).padStart(2, '0');
  return `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}`;
}

/** Asks for a moment still to come: one of the mornings to come, or a day and time of the user's. */
export function WhenDialog({
  heading,
  confirmLabel,
  pending,
  error,
  onChoose,
  onClose,
}: {
  heading: string;
  confirmLabel: string;
  pending: boolean;
  error: Error | null;
  onChoose: (at: Date) => void;
  onClose: () => void;
}) {
  const { t, formatDate } = useI18n();
  const [now] = useState(() => new Date());
  const tomorrow = morning(1, now);
  const [date, setDate] = useState(day(tomorrow));
  const [time, setTime] = useState('08:00');
  const chosen = new Date(`${date}T${time}`);
  const valid = !Number.isNaN(chosen.getTime()) && chosen > now;
  const offers = [
    { label: t('when.tomorrow'), at: tomorrow },
    { label: t('when.monday'), at: morning(nextMonday(now), now) },
  ];

  function submit(event: FormEvent) {
    event.preventDefault();
    if (valid) onChoose(chosen);
  }

  return (
    <Modal heading={heading} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          {offers.map((offer) => (
            <button
              key={offer.label}
              type="button"
              disabled={pending}
              onClick={() => onChoose(offer.at)}
              className={`${button} justify-between`}
            >
              <span>{offer.label}</span>
              <span className="text-muted">{formatDate(offer.at.toISOString())}</span>
            </button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            {t('when.day')}
            <input
              type="date"
              value={date}
              min={day(now)}
              onChange={(event) => setDate(event.target.value)}
              required
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t('when.time')}
            <input
              type="time"
              value={time}
              onChange={(event) => setTime(event.target.value)}
              required
              className={field}
            />
          </label>
        </div>
        {error && <p className="text-sm text-danger">{errorMessage(error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Close />
          <button type="submit" disabled={pending || !valid} className={primaryButton}>
            {confirmLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}
