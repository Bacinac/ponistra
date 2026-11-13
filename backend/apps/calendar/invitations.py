"""Invitations in the mail (D15, S4-3): the calendar part a message carries, read as the message
is taken. A meeting the user is asked to goes into a calendar of their own awaiting their
answer, a change or a cancellation reaches the meeting it names, an attendee's answer the
meeting the user called; and the user's answer goes back, by mail to the organizer, or through
the organisation's server for a meeting of its calendar."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from logging import getLogger

from django.db import transaction
from django.utils import timezone

from apps.core.api import Refused
from apps.core.asyncdb import database, waited
from apps.mail import sending, signin
from apps.mail.activesync import sync as activesync_sync
from apps.mail.imap import Failed
from apps.mail.models import Account, Message

from . import activesync, events, ical, notes, recurrence, taking
from .ical import Found
from .models import Calendar, Event, Feed, Invitation

log = getLogger(__name__)

CALENDAR = "text/calendar"
RESPONSES = ("accepted", "tentative", "declined")
NEEDS_ACTION = "needs-action"
OWN = Calendar.Kind.OWN
# The subject and the text of an answer, in the language the user reads PONISTRA in.
WORDED = {
    "hr": {
        "accepted": ("Prihvaćeno", "{name} prihvaća poziv."),
        "tentative": ("Možda", "{name} možda dolazi."),
        "declined": ("Odbijeno", "{name} odbija poziv."),
    },
    "en": {
        "accepted": ("Accepted", "{name} accepted the invitation."),
        "tentative": ("Tentative", "{name} may come."),
        "declined": ("Declined", "{name} declined the invitation."),
    },
}


def _addresses(owner_id: int) -> set[str]:
    listed = Account.objects.filter(owner_id=owner_id).values_list("address", flat=True)
    return {each.lower() for each in listed}


def _event_of(owner_id: int, uid: str) -> Event | None:
    return (
        Event.objects.filter(calendar__owner_id=owner_id, uid=uid, master__isnull=True)
        .select_related("calendar")
        .order_by("pk")
        .first()
    )


def _status_of(found: ical.Found, ours: set[str]) -> str:
    """How the organizer has the user down, where the invitation names them."""
    for each in found.attendees:
        if each.get("email", "").lower() in ours:
            return each.get("status") or NEEDS_ACTION
    return NEEDS_ACTION


def noted(message: Message, files: list[tuple[dict, bytes]]) -> None:
    """Reads the calendar part the message carries, if one, and does what it asks."""
    for each, data in files:
        if each["type"] != CALENDAR:
            continue
        try:
            method, found = ical.imip(data.decode("utf-8", "replace"))
        except ical.Malformed:
            continue
        if method not in Invitation.Method.values or not found[0].uid:
            continue
        try:
            with transaction.atomic():
                _noted(message, method, found)
        except Exception:
            log.exception("calendar: the invitation in message %s was not applied", message.pk)
        return


def _noted(message: Message, method: str, found: list[ical.Found]) -> Invitation:
    first = found[0]
    ours = _addresses(message.owner_id)
    called = (first.organizer.get("email") or "").lower() in ours
    if method == Invitation.Method.REQUEST and not called:
        _requested(message, found, ours)
    elif method == Invitation.Method.CANCEL and not called:
        _cancelled(message.owner_id, found)
    elif method == Invitation.Method.REPLY and called:
        _replied(message.owner_id, found)
    answering = method in (Invitation.Method.REPLY, Invitation.Method.COUNTER)
    return Invitation.objects.create(
        owner_id=message.owner_id,
        message=message,
        method=method,
        uid=first.uid,
        recurrence_id=first.recurrence_id,
        sequence=first.sequence,
        event=ical.described(first),
        attendee=first.attendees[0] if answering and first.attendees else {},
    )


def _calendar_of(account: Account) -> Calendar:
    own = Calendar.objects.filter(owner_id=account.owner_id, kind=OWN).order_by("pk").first()
    return own or taking.own(account.owner_id, account.address)


def _override(master: Event, found: ical.Found) -> Event:
    override = master.overrides.filter(recurrence_id=found.recurrence_id).first()
    if override is None:
        return events.made(master.calendar, found, master=master)
    return events.saved(override, found)


def _requested(message: Message, found: list[ical.Found], ours: set[str]) -> None:
    if message.account.protocol == Account.Protocol.ACTIVESYNC:
        # The organisation's server puts the meeting into its calendar itself.
        return
    for each in found:
        each.response = _status_of(each, ours)
    existing = _event_of(message.owner_id, found[0].uid)
    master = found[0] if found[0].recurrence_id is None else None
    if existing is None:
        if master is None:
            # One occurrence of a series never held stands on its own.
            found[0].recurrence_id = None
            master = found[0]
        made = events.made(_calendar_of(message.account), master)
        for each in found[1:]:
            events.made(made.calendar, each, master=made)
        return
    if existing.calendar.kind != OWN or found[0].sequence < existing.sequence:
        return
    if found[0].sequence == existing.sequence:
        # The same invitation again (a copy, a resend) does not take back what the user answered.
        held = {None: existing, **{each.recurrence_id: each for each in existing.overrides.all()}}
        for each in found:
            kept = held.get(each.recurrence_id)
            if kept is not None and kept.response != NEEDS_ACTION:
                each.response = kept.response
    if master is not None:
        events.replaced(existing, found)
        return
    for each in found:
        _override(existing, each)


def _cancelled(owner_id: int, found: list[ical.Found]) -> None:
    existing = _event_of(owner_id, found[0].uid)
    if existing is None or existing.calendar.kind != OWN:
        return
    if found[0].recurrence_id is None:
        rows = [existing, *existing.overrides.all()]
        Event.objects.filter(pk__in=[each.pk for each in rows]).update(
            status=Event.Status.CANCELLED
        )
        events.revise(*rows)
        return
    for each in found:
        override = existing.overrides.filter(recurrence_id=each.recurrence_id).first()
        gone = events.found_of(override or events.stand_in(existing, each.recurrence_id))
        gone.recurrence_id = each.recurrence_id
        gone.status = Event.Status.CANCELLED
        _override(existing, gone)


def _answered(attendees: list[dict], who: dict) -> list[dict]:
    email = who.get("email", "").lower()
    listed = [
        dict(each, status=who["status"]) if each.get("email", "").lower() == email else each
        for each in attendees
    ]
    if all(each.get("email", "").lower() != email for each in attendees):
        listed.append(who)
    return listed


def _replied(owner_id: int, found: list[ical.Found]) -> None:
    existing = _event_of(owner_id, found[0].uid)
    if existing is None or existing.calendar.kind != OWN or not found[0].attendees:
        return
    answer = found[0]
    target = existing
    if answer.recurrence_id is not None:
        target = existing.overrides.filter(recurrence_id=answer.recurrence_id).first()
        if target is None:
            stood = events.found_of(events.stand_in(existing, answer.recurrence_id))
            stood.recurrence_id = answer.recurrence_id
            target = _override(existing, stood)
    Event.objects.filter(pk=target.pk).update(
        attendees=_answered(target.attendees, answer.attendees[0])
    )
    events.revise(target, existing)


def described(message: Message, zone: str) -> dict | None:
    """What the message says of a meeting, and where the meeting stands in the user's
    calendars."""
    invitation = Invitation.objects.filter(message=message).exclude(event={}).first()
    if invitation is None:
        return None
    given = invitation.event
    all_day = given.get("all_day", False)
    held = _event_of(message.owner_id, invitation.uid)
    if held is not None:
        day = (
            recurrence.as_day(held.starts)
            if held.all_day
            else held.starts.astimezone(recurrence.zone_of(zone)).date()
        )
    return {
        "method": invitation.method,
        "event": {
            **given,
            "start": recurrence.shown(datetime.fromisoformat(given["start"]), all_day, zone),
            "end": recurrence.shown(datetime.fromisoformat(given["end"]), all_day, zone, end=True),
        },
        "attendee": invitation.attendee,
        "held": None
        if held is None
        else {
            "id": held.pk,
            "calendar": held.calendar_id,
            "response": held.response,
            "status": held.status,
            "day": day.isoformat(),
            "outdated": held.sequence > invitation.sequence,
        },
    }


def _server_of(event: Event) -> tuple[Account, str, str, str]:
    """The account whose server holds the meeting, its password, and the folder and item the
    server answers: the meeting in its calendar, or the notice of an invitation not answered."""
    account = event.calendar.account
    login, _ = signin.login(account)
    if notes.standing(event):
        collection, request = notes.notice_of(event)
    else:
        feed = Feed.objects.get(account=account, calendar=event.calendar)
        collection, request = feed.server_id, activesync.server_id_of(event.href)
    return account, login.password, collection, request


def _told_server(
    account: Account, password: str, collection: str, request: str, event: Event, response: str
):
    with activesync_sync.session(account, password) as client:
        activesync.responded(client, collection, request, response, event.recurrence_id)


async def _told_organizer(user, event: Event, response: str, language: str) -> None:
    organizer = (event.organizer.get("email") or "").lower()
    if not organizer:
        raise Refused(400, "no_organizer")
    accounts = await database(
        lambda: list(
            user.mail_accounts.exclude(protocol=Account.Protocol.ACTIVESYNC).order_by(
                "-default", "pk"
            )
        )
    )()
    if not accounts:
        raise Refused(400, "no_account")
    if organizer in await database(_addresses)(event.calendar.owner_id):
        raise Refused(400, "not_invited")
    invited = {each.get("email", "").lower() for each in event.attendees}
    account = next((each for each in accounts if each.address.lower() in invited), accounts[0])
    name = user.get_full_name() or account.name or account.address
    attendee = {"email": account.address, "name": name, "role": "required", "status": response}
    try:
        to = sending.address(event.organizer.get("name", ""), organizer)
    except sending.Invalid:
        raise Refused(400, "no_organizer") from None
    word, text = WORDED.get(language, WORDED["en"])[response]
    message = sending.imip(
        account,
        [to],
        f"{word}: {event.summary}",
        text.format(name=name),
        ical.replied(event, attendee, timezone.now()),
        "REPLY",
    )
    try:
        await sending.delivered(account, message)
    except Failed as failed:
        raise Refused(502, failed.code) from None
    await database(sending.recorded)(account, message, None)


def _kept(event: Event, response: str) -> None:
    ours = _addresses(event.calendar.owner_id)
    attendees = [
        dict(each, status=response) if each.get("email", "").lower() in ours else each
        for each in event.attendees
    ]
    Event.objects.filter(pk=event.pk).update(response=response, attendees=attendees)
    events.revise(event, event.master or event)


async def answered(user, event: Event, response: str, language: str) -> None:
    """The user's answer to the meeting, given to whoever asked: the organisation's server for
    a meeting of its calendar, else the organizer by mail from the account they were asked at;
    then kept on the event."""
    if event.response == "organizer":
        raise Refused(400, "not_invited")
    if event.response == response:
        return
    if event.calendar.kind == Calendar.Kind.ORGANISATION:
        account, password, collection, request = await database(_server_of)(event)
        try:
            await waited(
                partial(_told_server, account, password, collection, request, event, response)
            )
        except Failed as failed:
            raise Refused(502, failed.code) from None
    else:
        await _told_organizer(user, event, response, language)
    await database(_kept)(event, response)


# The subject and the text of what the organizer sends, in the language they read PONISTRA in.
INVITING = {
    "hr": {
        "request": ("Poziv", "{name} vas poziva na sastanak."),
        "updated": ("Ažurirano", "{name} je promijenio sastanak."),
        "cancel": ("Otkazano", "{name} je otkazao sastanak."),
    },
    "en": {
        "request": ("Invitation", "{name} invites you to a meeting."),
        "updated": ("Updated", "{name} changed the meeting."),
        "cancel": ("Cancelled", "{name} cancelled the meeting."),
    },
}
ORGANIZER = "organizer"
MOST_ATTENDEES = 100
# A change of these reaches every attendee; of anything else (a reminder, busy) nobody.
TOLD_OF = (
    "summary",
    "location",
    "conference",
    "description",
    "all_day",
    "starts",
    "ends",
    "rrule",
    "day_off",
    "status",
)


@dataclass
class Notice:
    """What the organizer's save or delete has to tell the attendees, once the row is written."""

    account: Account
    kind: str
    to: list[dict]
    event: Event
    ics: str


def given(data: dict) -> list[dict] | None:
    """The attendees as the interface sent them, or None where it sent nothing of them."""
    if "attendees" not in data:
        return None
    listed = data["attendees"]
    if not isinstance(listed, list) or len(listed) > MOST_ATTENDEES:
        raise Refused(400, "invalid_attendee")
    found: dict[str, dict] = {}
    for each in listed:
        person = each if isinstance(each, dict) else {}
        name, email = person.get("name", ""), person.get("email")
        if not isinstance(name, str) or not isinstance(email, str) or len(name) > 998:
            raise Refused(400, "invalid_attendee")
        try:
            address = sending.address(name, email)
        except sending.Invalid:
            raise Refused(400, "invalid_attendee") from None
        email = address.addr_spec.lower()
        found.setdefault(email, {"email": email, "name": name.strip()})
    return list(found.values())


def sender_of(user, email: str = "") -> Account:
    """The account the organizer's mail goes out from: the one with the address, else the
    default; Refused where the user has none that sends."""
    accounts = user.mail_accounts.exclude(protocol=Account.Protocol.ACTIVESYNC).order_by(
        "-default", "pk"
    )
    found = next((each for each in accounts if each.address.lower() == email.lower()), None)
    if found is None:
        found = accounts.first()
    if found is None:
        raise Refused(400, "no_account")
    return found


def arranged(user, found: Found, before: Event | None, attendees: list[dict] | None) -> None:
    """Puts the attendees the user asked onto the event, the user as its organizer, keeping how
    each attendee already stood; with none left, the meeting is a plain event again."""
    if attendees is None:
        return
    ours = _addresses(user.pk)
    held = {each.get("email", "").lower(): each for each in (before.attendees if before else [])}
    listed = []
    for each in attendees:
        if each["email"] in ours:
            continue
        old = held.get(each["email"], {})
        listed.append(
            {
                "email": each["email"],
                "name": each["name"] or old.get("name", ""),
                "role": old.get("role", "required"),
                "status": old.get("status", NEEDS_ACTION),
            }
        )
    found.attendees = listed
    if listed:
        account = sender_of(user, found.organizer.get("email", ""))
        found.organizer = {
            "email": account.address,
            "name": user.get_full_name() or account.name or account.address,
        }
        found.response = ORGANIZER
    elif before is None or before.response == ORGANIZER:
        found.organizer = {}
        found.response = ""


def _organized(event: Event) -> bool:
    return event.response == ORGANIZER and bool(event.attendees)


def _emails(attendees: list[dict]) -> set[str]:
    return {each.get("email", "").lower() for each in attendees}


def changes(user, before: Event | None, after: Event, parts: list[Event]) -> list[Notice]:
    """What the attendees are told of the event as it stands against how it stood: the meeting
    to everyone when what matters changed, to the newly asked otherwise, and taken back from
    whoever was dropped."""
    notices = []
    now = timezone.now()
    master = after.master or after
    dropped = []
    if before is not None and before.response == ORGANIZER:
        kept = _emails(after.attendees) if after.response == ORGANIZER else set()
        dropped = [each for each in before.attendees if each.get("email", "").lower() not in kept]
    if _organized(after):
        account = sender_of(user, after.organizer.get("email", ""))
        if before is None or before.response != ORGANIZER:
            to, kind = after.attendees, "request"
        elif any(getattr(before, name) != getattr(after, name) for name in TOLD_OF):
            to, kind = after.attendees, "updated"
        else:
            held = _emails(before.attendees)
            to = [each for each in after.attendees if each.get("email", "").lower() not in held]
            kind = "request"
        if to:
            notices.append(Notice(account, kind, to, after, ical.requested(master, parts, now)))
    if dropped:
        account = sender_of(user, before.organizer.get("email", ""))
        notices.append(
            Notice(account, "cancel", dropped, after, ical.cancelled(after, master, dropped, now))
        )
    return notices


def withdrawn(user, event: Event) -> list[Notice]:
    """The meeting, or its one occurrence, taken back from everyone asked, as its organizer
    deletes it."""
    if not _organized(event):
        return []
    account = sender_of(user, event.organizer.get("email", ""))
    master = event.master or event
    return [
        Notice(
            account,
            "cancel",
            event.attendees,
            event,
            ical.cancelled(event, master, event.attendees, timezone.now()),
        )
    ]


def _when(event: Event, language: str) -> str:
    zone = recurrence.zone_of(event.zone or "UTC")
    if event.all_day:
        first = recurrence.as_day(event.starts)
        last = recurrence.as_day(event.ends) - timedelta(days=1)
        shape = "%d.%m.%Y." if language == "hr" else "%d %b %Y"
        return first.strftime(shape) if last <= first else f"{first:{shape}} – {last:{shape}}"
    starts, ends = event.starts.astimezone(zone), event.ends.astimezone(zone)
    shape = "%d.%m.%Y. %H:%M" if language == "hr" else "%d %b %Y %H:%M"
    tail = ends.strftime("%H:%M" if ends.date() == starts.date() else shape)
    return f"{starts:{shape}} – {tail} ({event.zone or 'UTC'})"


async def told(language: str, notices: list[Notice]) -> None:
    """Sends each notice through the organizer's account and keeps a copy in their Sent folder;
    Refused where the server would not take it."""
    words = INVITING.get(language, INVITING["en"])
    for notice in notices:
        word, text = words[notice.kind]
        lines = [
            text.format(name=notice.event.organizer.get("name") or notice.account.address),
            "",
            notice.event.summary,
            _when(notice.event, language),
        ]
        if notice.event.location:
            lines.append(notice.event.location)
        if notice.event.conference and notice.kind != "cancel":
            lines.append(notice.event.conference)
        if notice.event.description and notice.kind != "cancel":
            lines += ["", notice.event.description]
        to = [sending.address(each.get("name", ""), each["email"]) for each in notice.to]
        message = sending.imip(
            notice.account,
            to,
            f"{word}: {notice.event.summary}",
            "\n".join(lines),
            notice.ics,
            "CANCEL" if notice.kind == "cancel" else "REQUEST",
        )
        try:
            await sending.delivered(notice.account, message)
        except Failed as failed:
            raise Refused(502, failed.code) from None
        await database(sending.recorded)(notice.account, message, None)
