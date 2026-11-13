# Attendees and answers

You add the people you invite to an event, who receive an invitation by email, and you answer others' invitations from the calendar.

## How to use it

### Inviting

1. In the event, in the {t:calendar.field.attendees} field, type the people as you would a message's recipients.
2. If one of your colleagues is busy at that time, {t:calendar.busyThen} with their names shows below the field. Choose one of the free times, change the time yourself or invite them anyway.
3. Press {t:tree.save}. The invitation goes to those invited.

### Free times

1. When someone invited is busy or away at the chosen time, or a room you ticked is taken, {t:calendar.offers} appears below the rooms: the first times of the same length at which you, everyone invited from the installation and every ticked room are free.
2. Press a time. The event's start and end move to it, and the offer disappears.
3. Below the times, beside {t:calendar.unknownThen}, stand those invited from outside the installation.

### Who has answered

1. Open the event. Under {t:calendar.attendees} stand the {t:calendar.organizer} and each person invited with their answer: {t:calendar.status.accepted}, {t:calendar.status.tentative}, {t:calendar.status.declined} or {t:calendar.status.needsAction}.

### Answering an invitation

1. Open the event you are invited to.
2. Under {t:calendar.yourAnswer} press {t:calendar.respond.accepted}, {t:calendar.respond.tentative} or {t:calendar.respond.declined}.

You can also answer an invitation in the message itself, as [reading a message](help:mail/reading) describes.

## How it works

The invitation goes by email from your account: the one with the organiser's address or, if there is none, the default one. If you change the time, the place or anything else that matters, everyone invited gets a new invitation; people you only added get the invitation alone, and those removed, and everyone when you delete the event, are told of the cancellation.

An invitation that reaches you by mail goes into your calendar and awaits your answer. Your answer goes to the organiser by email, and for an event of an organisation calendar through the organisation's server. The answers of those invited arrive by mail and are written beside their names, and the organiser's change or cancellation changes the event in your calendar.

The busy check knows only the users of this installation, and only that their time is taken, not what for. Events not marked as busy, cancelled events and invitations the person declined do not count.

Free times are looked for from the day chosen in the event, or from now if that day has begun. They are offered on the hour and half hour from the start of the working hours, only on the installation's working days and within its working hours, which the administrator sets, and do not overlap one another. Besides the events in the calendars, a period of time away counts too. When you edit an existing event, the event itself takes no one's time. Those invited from outside the installation do not affect the offer, as their busy times are not known.

## Limits

- Sending invitations needs a mail account that sends directly; an account connected over ActiveSync does not send invitations.
- Only the organiser changes who is invited.
- The busy times of people outside the installation are not known.
- Free times are not offered for an all-day event and are looked for at most two months ahead; if there is none, it says: {t:calendar.noOffers}
- A time longer than the installation's working hours cannot be offered.

## Related

- [Events](help:calendar/events)
- [Reading a message](help:mail/reading)
- [Writing a message](help:mail/composing)
