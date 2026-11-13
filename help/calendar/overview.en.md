# Calendar

The calendar shows in one place the events of all your calendars, tasks with a due date, holidays, your contacts' birthdays and the bookings of the rooms you follow.

![The calendar showing a month](shot:calendar-month)

## How to use it

### Views and moving around

1. Open the [calendar](/calendar) on the rail on the left.
2. Above the calendar, in the {t:calendar.view} group, you choose the view: {t:calendar.view.month}, {t:calendar.view.week}, {t:calendar.view.day} or {t:calendar.view.agenda}.
3. The arrows {t:calendar.previous} and {t:calendar.next} move a whole view back or ahead, and the {t:calendar.today} button returns to today.
4. In the left column the small month leads to any day; its arrows {t:calendar.previousMonth} and {t:calendar.nextMonth} turn the months.

### What each view shows

- {t:calendar.view.month}: each day holds up to three events, and "+" with the number of the rest opens that day. The day's number opens the day view, and a double click on a day opens a new event on it.
- {t:calendar.view.week} and {t:calendar.view.day}: events stand by the hour, and a line marks the current time. A click on an hour opens a new event at that hour, and {t:calendar.addAllDay} at the top of a day opens an event for the whole day.
- {t:calendar.view.agenda}: the events of the next 30 days one below the other.
- A click on an event opens it; an event of a calendar that is only read opens under the heading {t:calendar.event}.

### What is shown

1. In the left column beside {t:calendar.calendars} press {t:calendar.settings}. The list of your calendars opens.
2. The tick beside a calendar hides or brings back its events, and the ticks {t:calendar.holidays} and {t:calendar.birthdays} choose whether holidays and your contacts' birthdays show.
3. Under {t:calendar.resources} the tick beside a room or resource adds its bookings to the calendar.
4. Under {t:mail.mailboxes} you open the calendars of a [shared mailbox](help:mail/mailboxes) shared with you, and {t:calendar.mailboxOwn} brings back your own.

## How it works

The view and the day are written in the page's address, so a link to the calendar opens on exactly that view. On a wide screen the calendar opens on the month, on a phone as a list. The week and day views open at 7 in the morning.

Tentative events show faded, cancelled ones struck through, and recurring ones carry a repeat sign. Days off are shaded. Tasks with a due date stand on their due day and open in the task's window. A birthday leads to the contact. In someone else's room booking that is private, the event's title is not shown.

What you hid with the ticks is remembered by this browser, not by the account. The calendar refreshes itself as soon as any of its events changes, here, on a phone or at the organisation's server.

## Limits

- Hidden calendars and chosen rooms hold only in the browser where you chose them.
- In the month view a day holds at most three events; the rest are in the day view.

## Related

- [Events](help:calendar/events)
- [Calendars](help:calendar/calendars)
- [Rooms and resources](help:calendar/rooms)
- [Tasks](help:tasks/overview)
- [Shared mailboxes](help:mail/mailboxes)
