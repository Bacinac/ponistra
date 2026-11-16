import { useState, type FormEvent } from 'react';
import { Cancel, Labelled, Modal, NumberField, Picker } from './dialogs';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { field, primaryButton } from './styles';
import { errorMessage } from './tree';
import { day } from './when';

export type Condition = 'time' | 'reset' | 'below' | 'round' | 'red';
type Every = 'day' | 'week';

/** What a round or a chat waits on to start (PJ4), and the weekly percent at which what it started
    stops working. */
export interface When {
  on: Condition;
  at?: string;
  every?: Every | null;
  percent?: number;
  round?: string;
  pause?: number | null;
}

export interface OtherRound {
  id: string;
  title: string;
}

const CONDITIONS: Record<Condition, MessageKey> = {
  time: 'workspace.when.time',
  reset: 'workspace.when.reset',
  below: 'workspace.when.below',
  round: 'workspace.when.round',
  red: 'workspace.when.red',
};

const EVERY: Record<'once' | Every, MessageKey> = {
  once: 'workspace.when.once',
  day: 'workspace.when.daily',
  week: 'workspace.when.weekly',
};

const REPEATED: Record<Every, MessageKey> = {
  day: 'workspace.waits.daily',
  week: 'workspace.waits.weekly',
};

const BELOW = 30;
const PAUSE = 90;

/** What a waiting round or chat waits on, in words. */
export function useWhenText() {
  const { t, formatDate, formatNumber } = useI18n();
  return (when: When, rounds: OtherRound[] = []) => {
    const percent = (value: number) => formatNumber(value);
    const said =
      when.on === 'time'
        ? t(when.every ? REPEATED[when.every] : 'workspace.waits.time').replace(
            '{at}',
            formatDate(when.at!),
          )
        : when.on === 'below'
          ? t('workspace.waits.below').replace('{percent}', percent(when.percent!))
          : when.on === 'round'
            ? t('workspace.waits.round').replace(
                '{round}',
                rounds.find((each) => each.id === when.round)?.title ?? when.round!,
              )
            : t(when.on === 'reset' ? 'workspace.waits.reset' : 'workspace.waits.red');
    return when.pause
      ? `${said} · ${t('workspace.waits.pause').replace('{percent}', percent(when.pause))}`
      : said;
  };
}

/** Asks what a round or a new chat waits on to start; only a chat starts again and again. */
export function StartWhen({
  heading,
  repeats,
  rounds,
  pending,
  error,
  onChoose,
  onClose,
}: {
  heading: string;
  repeats: boolean;
  rounds: OtherRound[];
  pending: boolean;
  error: Error | null;
  onChoose: (when: When) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [now] = useState(() => new Date());
  const [on, setOn] = useState<Condition>('time');
  const [date, setDate] = useState(day(new Date(now.getTime() + 24 * 60 * 60 * 1000)));
  const [time, setTime] = useState('03:30');
  const [every, setEvery] = useState<'once' | Every>('once');
  const [percent, setPercent] = useState(BELOW);
  const [round, setRound] = useState(rounds[0]?.id ?? '');
  const [pausing, setPausing] = useState(false);
  const [pause, setPause] = useState(PAUSE);
  const at = new Date(`${date}T${time}`);
  const offered = (Object.keys(CONDITIONS) as Condition[]).filter(
    (each) => each !== 'round' || rounds.length > 0,
  );
  const valid =
    on === 'time'
      ? !Number.isNaN(at.getTime()) && (every !== 'once' || at > now)
      : on !== 'round' || Boolean(round);

  function submit(event: FormEvent) {
    event.preventDefault();
    // The dialog's portal still bubbles React events to the form it was opened from.
    event.stopPropagation();
    if (!valid) return;
    const when: When = { on, pause: pausing ? pause : null };
    if (on === 'time')
      Object.assign(when, { at: at.toISOString(), every: every === 'once' ? null : every });
    if (on === 'below') when.percent = percent;
    if (on === 'round') when.round = round;
    onChoose(when);
  }

  return (
    <Modal heading={heading} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Picker
          label={t('workspace.when.on')}
          value={on}
          options={offered.map((each) => [each, t(CONDITIONS[each])] as const)}
          onChange={setOn}
        />
        {on === 'time' && (
          <>
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
            {repeats && (
              <Picker
                label={t('workspace.when.repeat')}
                value={every}
                options={(Object.keys(EVERY) as ('once' | Every)[]).map(
                  (each) => [each, t(EVERY[each])] as const,
                )}
                onChange={setEvery}
              />
            )}
          </>
        )}
        {on === 'below' && (
          <NumberField
            label={t('workspace.when.percent')}
            value={percent}
            min={5}
            max={100}
            step={5}
            onChange={setPercent}
          />
        )}
        {on === 'round' && (
          <Labelled label={t('workspace.when.which')}>
            {(id) => (
              <select
                id={id}
                value={round}
                onChange={(event) => setRound(event.target.value)}
                className={field}
              >
                {rounds.map((each) => (
                  <option key={each.id} value={each.id}>
                    {each.title}
                  </option>
                ))}
              </select>
            )}
          </Labelled>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={pausing}
            onChange={(event) => setPausing(event.target.checked)}
          />
          {t('workspace.when.pausing')}
        </label>
        {pausing && (
          <NumberField
            label={t('workspace.when.pause')}
            value={pause}
            min={5}
            max={100}
            step={5}
            onChange={setPause}
          />
        )}
        {error && <p className="text-sm text-danger">{errorMessage(error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={pending || !valid} className={primaryButton}>
            {t('workspace.when.set')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
