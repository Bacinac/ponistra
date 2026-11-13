# Events

An event has a title, a time, the calendar it belongs to and, if you wish, a place, a description, a reminder and an online meeting.

## How to use it

### A new event

1. Press {t:calendar.newEvent}, click an hour in the week or day view, or double-click a day in the month view.
2. Type the {t:calendar.field.summary}. The rest is already filled in: a new event starts at 9 o'clock and lasts an hour, and a clicked hour sets its own start.
3. Change {t:calendar.field.startDay}, {t:calendar.field.startTime}, {t:calendar.field.endDay} and {t:calendar.field.endTime} if needed, or tick {t:calendar.allDay}.
4. In the {t:calendar.field.calendar} field choose the calendar, and type the {t:calendar.field.location} and {t:calendar.field.description} if you want them.
5. Press {t:tree.save}.

### The event's other settings

- {t:calendar.field.busy}: the event's time counts as taken when someone in the installation checks whether you are free. Turn it off for an event that does not take your time.
- People invited who are away at that time are listed beside the field of those invited, with the day they are back ([Away](help:mail/away)), and below the rooms times at which everyone is free are offered ([Attendees and answers](help:calendar/invitations)).
- {t:calendar.field.private}: others do not see the event's title in a room booking, and calendars that receive it get it marked as private.
- {t:calendar.field.reminder}: {t:calendar.reminder.none} or a time from the moment of the event to one day before.
- {t:calendar.field.repeat}: an event that repeats, described in the article [Recurring events](help:calendar/recurring).

### An online meeting

1. In the {t:calendar.field.conference} part press {t:meeting.add}. Ponistra opens a meeting for the event, and the field shows {t:meeting.ours}.
2. {t:meeting.join} opens the meeting, and {t:meeting.copyLink} keeps the link for sending; while the link is copied, the button says {t:meeting.copied}
3. The cross {t:meeting.remove} removes the meeting from the event.

### An existing event

1. Click the event in the calendar, change what is needed, then press {t:tree.save}. The window's heading is {t:calendar.editEvent}.
2. {t:calendar.delete} deletes the event at once.
3. {t:tasks.fromEvent} opens a new task with the event's title and the event's day as its due date, linked to that day in the calendar.
4. {t:tree.cancel} closes the window without changes.

## How it works

The event is saved in the chosen calendar and shows at once on all your devices, and calendars connected to Ponistra, such as the one on your phone, receive it with their next sync. The reminder is saved with the event and passed to the calendars on your phone and in programs connected to Ponistra, which remind you of it.

A Ponistra meeting opens beside your work in a window of its own, another service's meeting in a new tab. Only the event's organiser can add or remove a meeting, and only while its link is not written into the place or the description.

An event of an organisation calendar is only read: the window's heading is {t:calendar.event}, the fields are disabled, and you can still open a new task from it.

## Limits

- An event's title has at most 200 characters.
- Ponistra does not show a reminder itself; the calendars of the devices and programs connected to it do the reminding.
- Deleting asks for no confirmation.

## Related

- [Calendar](help:calendar/overview)
- [Attendees and answers](help:calendar/invitations)
- [Recurring events](help:calendar/recurring)
- [Meetings](help:meetings/overview)
