# Recurring events

An event that repeats every day, week, month or year you enter once, and Ponistra also knows what to do with it when it falls on a day off.

## How to use it

### Repeating

1. In the event open {t:calendar.field.repeat}. The choices follow the start day: {t:calendar.repeat.daily}, {t:calendar.repeat.weekdays}, {t:calendar.repeat.weekly}, the same date each month, the same weekday by its place in the month (for example the second Tuesday of each month), {t:calendar.repeat.yearly} or {t:calendar.repeat.none}.
2. In the {t:calendar.field.until} field type the day the series ends, if you wish. An empty field means the event repeats without end.
3. In the {t:calendar.field.dayOff} field choose what happens when a repetition falls on a weekend or a holiday: {t:calendar.dayOff.held}, {t:calendar.dayOff.skip}, or it moves to the {t:calendar.dayOff.before} or the {t:calendar.dayOff.after}.
4. Press {t:tree.save}.

### Changing and deleting

1. Change one occurrence and press {t:tree.save} or {t:calendar.delete}.
2. In the {t:calendar.editRecurring} or {t:calendar.deleteRecurring} window, under {t:calendar.scope}, choose {t:calendar.scope.this}, {t:calendar.scope.following} or {t:calendar.scope.all}.
3. Confirm with the same button in that window.

## How it works

Repeating by the weekday's place in the month is offered from the start day: for the month's fifth such day the last is offered, and for a last one that is also the fourth both are offered. Days off are the weekend and the public holidays of the installation's country, and the days its administrator closes. An occurrence that would move to a day where the series already has one is left out.

{t:calendar.scope.this} changes only that occurrence, and the rest of the series stays as it was. {t:calendar.scope.following} splits the series in two: the one so far ends before that occurrence, and a new one begins with it, carrying your changes. {t:calendar.scope.all} changes the whole series; if you move the time, every occurrence moves.

Calendars on a phone and in other programs know nothing of Ponistra's days off, so they are sent where each occurrence really falls for the next ten years.

## Limits

- A repetition that came from another calendar and is not among those offered shows as {t:calendar.repeat.custom} and is kept as it is; only its end can be changed.
- A move to a working day looks for one within at most 62 days; if there is none, the occurrence is left out.

## Related

- [Events](help:calendar/events)
- [Calendar](help:calendar/overview)
