import { describe, expect, it } from 'vitest';
import { fitted, placeOf, repeatOf, ruleOf } from './recurrence';

describe('a repeat', () => {
  it('places a day by its weekday, which of them it is and whether it is the last', () => {
    expect(placeOf('2026-10-15')).toEqual({
      month: 10,
      date: 15,
      weekday: 'TH',
      nth: '3',
      last: false,
    });
    expect(placeOf('2026-10-25')).toMatchObject({ weekday: 'SU', nth: '4', last: true });
    expect(placeOf('2026-10-29')).toMatchObject({ weekday: 'TH', nth: null, last: true });
    expect(placeOf('2028-02-29')).toMatchObject({ weekday: 'TU', nth: null, last: true });
  });

  it('offers a fifth weekday as the last and a last one that is not as its number', () => {
    expect(fitted('nth', '2026-10-29')).toBe('last');
    expect(fitted('last', '2026-10-15')).toBe('nth');
    expect(fitted('nth', '2026-10-25')).toBe('nth');
    expect(fitted('last', '2026-10-25')).toBe('last');
  });

  it('writes the rule the start day asks for', () => {
    expect(ruleOf('none', '2026-10-15', 'FREQ=WEEKLY', null)).toBe('');
    expect(ruleOf('nth', '2026-10-15', '', null)).toBe('FREQ=MONTHLY;BYDAY=3TH');
    expect(ruleOf('nth', '2026-10-29', '', null)).toBe('FREQ=MONTHLY;BYDAY=-1TH');
    expect(ruleOf('last', '2026-10-29', '', '2027-06-30')).toBe(
      'FREQ=MONTHLY;BYDAY=-1TH;UNTIL=20270630',
    );
    expect(ruleOf('monthly', '2026-10-15', '', '')).toBe('FREQ=MONTHLY');
  });

  it('keeps the end it had, a count included, until a new one is chosen', () => {
    const kept = 'FREQ=WEEKLY;INTERVAL=2;COUNT=6';
    expect(ruleOf('custom', '2026-10-15', kept, null)).toBe(kept);
    expect(ruleOf('custom', '2026-10-15', kept, '2026-12-31')).toBe(
      'FREQ=WEEKLY;INTERVAL=2;UNTIL=20261231',
    );
    expect(ruleOf('weekly', '2026-10-16', 'FREQ=WEEKLY;BYDAY=TH;UNTIL=20261231', null)).toBe(
      'FREQ=WEEKLY;UNTIL=20261231',
    );
    expect(ruleOf('weekly', '2026-10-16', 'FREQ=WEEKLY;UNTIL=20261231', '')).toBe('FREQ=WEEKLY');
  });

  it('reads a source rule as the choice it amounts to on its start day', () => {
    const day = '2026-10-15';
    expect(repeatOf('', day)).toBe('none');
    expect(repeatOf('FREQ=DAILY;COUNT=10', day)).toBe('daily');
    expect(repeatOf('FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR', day)).toBe('weekdays');
    expect(repeatOf('FREQ=WEEKLY;WKST=MO;BYDAY=TH;INTERVAL=1', day)).toBe('weekly');
    expect(repeatOf('FREQ=MONTHLY;BYMONTHDAY=15', day)).toBe('monthly');
    expect(repeatOf('FREQ=MONTHLY;BYDAY=TH;BYSETPOS=3', day)).toBe('nth');
    expect(repeatOf('FREQ=YEARLY;BYMONTH=10;BYMONTHDAY=15;UNTIL=20301015', day)).toBe('yearly');
    expect(repeatOf('FREQ=MONTHLY;BYDAY=-1TH', '2026-10-29')).toBe('last');
    expect(repeatOf('FREQ=MONTHLY;BYDAY=TH;BYSETPOS=-1', '2026-10-29')).toBe('last');
    expect(repeatOf('FREQ=MONTHLY;BYDAY=5TH', '2026-10-29')).toBe('custom');
    expect(repeatOf('FREQ=WEEKLY;INTERVAL=2', day)).toBe('custom');
    expect(repeatOf('FREQ=WEEKLY;BYDAY=FR', day)).toBe('custom');
    expect(repeatOf('FREQ=MONTHLY;BYMONTHDAY=16', day)).toBe('custom');
  });
});
