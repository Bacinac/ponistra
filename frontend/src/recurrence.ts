export const PRESETS = ['daily', 'weekdays', 'weekly', 'monthly', 'nth', 'last', 'yearly'] as const;
export type Preset = (typeof PRESETS)[number];
export const REPEATS = ['none', ...PRESETS, 'custom'] as const;
export type Repeat = (typeof REPEATS)[number];
export const DAYS_OFF = ['', 'skip', 'before', 'after'] as const;
export type DayOff = (typeof DAYS_OFF)[number];
const WEEKDAYS = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'] as const;
const ORDINALS = ['1', '2', '3', '4'] as const;
const ENDS = /^(UNTIL|COUNT)=/;

export function placeOf(day: string) {
  const [year, month, date] = day.split('-').map(Number);
  const nth = Math.ceil(date / 7);
  return {
    month,
    date,
    weekday: WEEKDAYS[new Date(Date.UTC(year, month - 1, date)).getUTCDay()],
    nth: nth <= 4 ? ORDINALS[nth - 1] : null,
    last: date + 7 > new Date(Date.UTC(year, month, 0)).getUTCDate(),
  };
}

/** The month's fifth weekday is offered only as its last, and a last one only as its number
 * when it is not the month's last. */
export function fitted(repeat: Repeat, day: string): Repeat {
  const { nth, last } = placeOf(day);
  if (repeat === 'nth' && !nth) return 'last';
  if (repeat === 'last' && !last) return 'nth';
  return repeat;
}

function ruleFor(repeat: Preset, day: string): string {
  const { weekday, nth } = placeOf(day);
  switch (repeat) {
    case 'daily':
      return 'FREQ=DAILY';
    case 'weekdays':
      return 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR';
    case 'weekly':
      return 'FREQ=WEEKLY';
    case 'monthly':
      return 'FREQ=MONTHLY';
    case 'nth':
      return `FREQ=MONTHLY;BYDAY=${nth}${weekday}`;
    case 'last':
      return `FREQ=MONTHLY;BYDAY=-1${weekday}`;
    case 'yearly':
      return 'FREQ=YEARLY';
  }
}

/** A rule with what its start implies spelled out, so that a source's FREQ=WEEKLY;BYDAY=TH or
 * BYDAY=TH;BYSETPOS=3 reads as the same choice as ours. */
function spelled(rule: string, day: string): string {
  const { month, date, weekday } = placeOf(day);
  const parts = new Map(
    rule
      .split(';')
      .filter((part) => part && !ENDS.test(part) && !part.startsWith('WKST='))
      .map((part) => part.split('=') as [string, string]),
  );
  if (parts.get('INTERVAL') === '1') parts.delete('INTERVAL');
  const position = parts.get('BYSETPOS');
  const days = parts.get('BYDAY');
  if (position && days && /^[A-Z]{2}$/.test(days)) {
    parts.set('BYDAY', `${position}${days}`);
    parts.delete('BYSETPOS');
  }
  const frequency = parts.get('FREQ');
  if (frequency === 'WEEKLY' && !parts.has('BYDAY')) parts.set('BYDAY', weekday);
  if (frequency === 'MONTHLY' || frequency === 'YEARLY') {
    if (!parts.has('BYDAY') && !parts.has('BYMONTHDAY')) parts.set('BYMONTHDAY', String(date));
  }
  if (frequency === 'YEARLY' && !parts.has('BYMONTH')) parts.set('BYMONTH', String(month));
  return [...parts]
    .map((part) => part.join('='))
    .sort()
    .join(';');
}

export function repeatOf(rule: string, day: string): Repeat {
  if (!rule) return 'none';
  const shape = spelled(rule, day);
  return (
    PRESETS.find(
      (each) => fitted(each, day) === each && spelled(ruleFor(each, day), day) === shape,
    ) ?? 'custom'
  );
}

export function untilOf(rule: string): string {
  const match = /UNTIL=(\d{4})(\d{2})(\d{2})/.exec(rule);
  return match ? `${match[1]}-${match[2]}-${match[3]}` : '';
}

/** The rule a repeat asks for from the day, over the rule kept so far. Its end stays the kept
 * one's, a COUNT included, unless a new date to end on is given. */
export function ruleOf(repeat: Repeat, day: string, kept: string, until: string | null): string {
  if (repeat === 'none') return '';
  const base =
    repeat === 'custom'
      ? kept
          .split(';')
          .filter((part) => !ENDS.test(part))
          .join(';')
      : ruleFor(fitted(repeat, day) as Preset, day);
  const end =
    until === null
      ? (kept.split(';').find((part) => ENDS.test(part)) ?? '')
      : until && `UNTIL=${until.replaceAll('-', '')}`;
  return end ? `${base};${end}` : base;
}
