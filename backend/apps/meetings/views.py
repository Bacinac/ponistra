import json
import secrets
import uuid
from datetime import timedelta
from logging import getLogger

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.calendar.invitations import sender_of
from apps.calendar.models import Event
from apps.chat import conversations
from apps.chat.models import Conversation, Member
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database, waited
from apps.journal import entries
from apps.journal.entries import Kind
from apps.mail import sending
from apps.mail.imap import Failed
from apps.users.accounts import administrator
from apps.users.models import User

from . import livekit, lobby, recordings, relay, rings
from .models import Guest, Meeting, Recording, Relay, Ring

log = getLogger(__name__)

TITLE = 1000
# What the people asked into a meeting from outside the installation read, in the language the
# user reads PONISTRA in.
ASKED = {
    "hr": (
        "{name} vas zove u sastanak",
        "{name} vas zove u sastanak u Ponistri:\n\n{link}\n\nZa ulaz vam ne treba račun.\n",
    ),
    "en": (
        "{name} asks you into a meeting",
        "{name} asks you into a meeting in Ponistra:\n\n{link}\n\nYou need no account to join.\n",
    ),
}
NAME = 200
# How many may wait at a meeting's door having come by its link, within the last minutes: its
# link is all it takes, and every one of them stands in the lobby of everyone in the meeting.
DOOR = 20
DOOR_WITHIN = timedelta(minutes=10)


def describe(meeting: Meeting, title: str) -> dict:
    return {
        "id": str(meeting.id),
        "title": title,
        "link": meeting.link,
        "conversation": str(meeting.conversation_id),
    }


def _found(pk: uuid.UUID) -> Meeting:
    found = Meeting.objects.filter(pk=pk).first()
    if found is None:
        raise Refused(404, "no_meeting")
    return found


def _titled(user, meeting: Meeting) -> str:
    """The meeting as the user's own calendar names it, where an event of theirs leads to it."""
    event = (
        Event.objects.filter(calendar__owner=user, conference=meeting.link, master__isnull=True)
        .order_by("-starts")
        .first()
    )
    return event.summary if event and event.summary else meeting.title


@api("POST")
def meetings(request):
    """A meeting under the title given; one made now has none, its people naming it. One made in
    a conversation of the user's takes its title and rings everyone else in it."""
    data = body(request)
    user = request.user
    if (within := data.get("conversation")) is not None:
        try:
            found = Member.objects.filter(conversation_id=uuid.UUID(str(within)), user=user)
            member = found.select_related("conversation", "user").get()
        except ValueError, Member.DoesNotExist:
            raise Refused(404, "no_conversation") from None
        conversation = member.conversation
        made = Meeting.objects.made(conversation.title, user, conversation)
        if conversation.kind == Conversation.Kind.CHANNEL:
            conversations.meeting_opened(member, made)
            return JsonResponse(describe(made, made.title), status=201)
        others = User.objects.filter(memberships__conversation=conversation).exclude(pk=user.pk)
        rings.ring(user, made, list(others))
        return JsonResponse(describe(made, made.title), status=201)
    title = " ".join(str(data.get("title") or "").split())[:TITLE]
    made = Meeting.objects.made(title, user)
    return JsonResponse(describe(made, made.title), status=201)


def _shown(user, pk: uuid.UUID) -> dict:
    found = _found(pk)
    planned = Event.objects.filter(conference=found.link).exists()
    return {**describe(found, _titled(user, found)), "planned": planned}


@api("GET")
async def meeting(request, pk):
    shown = await database(_shown)(request.user, pk)
    try:
        shown["present"] = await livekit.present(shown["id"])
    except livekit.Unavailable as unavailable:
        log.warning("meetings: %s", unavailable)
        raise Refused(503, "meetings_unavailable") from unavailable
    return JsonResponse(shown)


@api("POST")
def join(request, pk):
    """The key the browser enters the room with: each joining is a participant of its own, so the
    same person may be in from the laptop and the phone at once."""
    found = _found(pk)
    user = request.user
    rings.answered(user, found, Ring.Answer.JOINED)
    conversations.added(found.conversation, [user])
    identity = f"{user.pk}.{secrets.token_hex(4)}"
    name = user.get_full_name() or user.email
    return JsonResponse({"token": livekit.joining(str(found.id), identity, name), "ice": _ice()})


def _ice() -> list[dict] | None:
    try:
        return relay.servers()
    except relay.Unavailable as unavailable:
        log.warning("meetings: the relay is unavailable: %s", unavailable.code)
        raise Refused(503, unavailable.code) from None


@api("GET", "PATCH")
def relay_setting(request):
    administrator(request)
    if request.method == "PATCH":
        provider, addresses, name, secret = _relay(body(request))
        try:
            found = relay.change(request.user, provider, addresses, name, secret)
        except relay.Unavailable as unavailable:
            raise Refused(422, unavailable.code) from None
        entries.wrote(
            Kind.SETTING_CHANGED,
            request=request,
            setting="meetings_relay",
            provider=provider,
            secret=secret is not None,
        )
        return JsonResponse(relay.describe(found))
    return JsonResponse(relay.describe(relay.setting()))


def _relay(data: dict) -> tuple[str, list[str], str, str | None]:
    provider, addresses = data.get("provider"), data.get("addresses", [])
    name, secret = data.get("name", ""), data.get("secret")
    if provider not in Relay.Provider.values:
        raise Refused(400, "invalid_provider")
    if not isinstance(addresses, list) or not all(isinstance(each, str) for each in addresses):
        raise Refused(400, "invalid_relay_address")
    if not isinstance(name, str) or (secret is not None and not isinstance(secret, str)):
        raise Refused(400, "invalid_relay")
    given = [each.strip() for each in addresses if each.strip()]
    return provider, given, name.strip(), (secret and secret.strip()) or None


@api("POST")
def decline(request, pk):
    rings.answered(request.user, _found(pk), Ring.Answer.DECLINED)
    return HttpResponse(status=204)


def _people(given) -> list:
    if not isinstance(given, list) or not given:
        raise Refused(400, "invalid_recipient")
    found = []
    for each in given:
        named, address = (
            (each.get("name", ""), each.get("address")) if isinstance(each, dict) else ("", None)
        )
        if not isinstance(named, str) or not isinstance(address, str) or len(named) > 998:
            raise Refused(400, "invalid_recipient")
        try:
            found.append(sending.address(named, address))
        except sending.Invalid:
            raise Refused(400, "invalid_recipient") from None
    return found


def _asked(user, pk: uuid.UUID, people: list) -> tuple[Meeting, dict, list, object]:
    """The meeting, the colleagues among the people by the address they asked, those outside
    the installation each with the link that lets them in, and the account they are written to
    from."""
    found = _found(pk)
    colleagues, outside = {}, []
    for each in people:
        address = each.addr_spec.lower()
        colleague = (
            User.objects.filter(is_active=True)
            .filter(Q(email__iexact=address) | Q(mail_accounts__address__iexact=address))
            .first()
        )
        if colleague is None:
            outside.append(each)
        elif colleague.pk != user.pk:
            colleagues[address] = colleague
    account = sender_of(user) if outside else None
    return found, colleagues, [(each, _let_in(found, user, each).link) for each in outside], account


def _let_in(meeting: Meeting, user, address) -> Guest:
    """The guest asked at the address, by a link of their own that an earlier one stays."""
    asked = meeting.guests.filter(address__iexact=address.addr_spec).first()
    if asked is None:
        return Guest.objects.create(
            meeting=meeting,
            name=address.display_name[:NAME],
            address=address.addr_spec.lower(),
            state=Guest.State.ADMITTED,
            by=user,
        )
    if asked.state != Guest.State.ADMITTED:
        lobby.answered(asked, user, Guest.State.ADMITTED)
    return asked


@transaction.atomic
def _rung(user, meeting: Meeting, colleagues: list) -> None:
    """The colleagues rung are in the meeting's conversation, whether they answer or not."""
    conversations.added(meeting.conversation, colleagues)
    rings.ring(user, meeting, colleagues)


@api("POST")
async def invite(request, pk):
    """Rings the colleagues among the people asked in every PONISTRA they have open, and writes
    each of the others a link of their own that lets them in, from the user's account, before
    anyone is rung."""
    data = body(request)
    user = request.user
    people = _people(data.get("people"))
    found, colleagues, outside, account = await database(_asked)(user, pk, people)
    if outside:
        language = data.get("language") if data.get("language") in ASKED else "en"
        title, text = ASKED[language]
        name = user.get_full_name() or account.name or account.address
        for address, link in outside:
            message = sending.composed(
                account,
                [address],
                [],
                [],
                title.format(name=name),
                text.format(name=name, link=link),
                None,
                [],
            )
            try:
                await sending.delivered(account, message)
            except Failed as failed:
                raise Refused(502, failed.code) from None
            await database(sending.recorded)(account, message, None)
    await database(_rung)(user, found, list(colleagues.values()))
    return JsonResponse(
        {
            "rung": sorted(each.get_full_name() or each.email for each in colleagues.values()),
            "written": [address.addr_spec for address, _ in outside],
        }
    )


def _guest_of(pk: uuid.UUID, key) -> Guest:
    found = isinstance(key, str) and Guest.objects.filter(meeting_id=pk, key=key).first()
    if not found:
        raise Refused(404, "no_guest")
    return found


@api("GET", signed_in=False)
def door(request, pk):
    """What someone outside the installation sees of the meeting before they are in: its title,
    and how they were asked where their link has a key."""
    found = _found(pk)
    key = request.GET.get("guest")
    guest = found.guests.filter(key=key).first() if key else None
    return JsonResponse(
        {
            "id": str(found.id),
            "title": found.title,
            "guest": guest and {"name": guest.name, "state": guest.state},
        }
    )


@api("POST", signed_in=False)
def guests(request, pk):
    """A guest at the meeting's door under the name given: the one the key given was asked or
    came as before, or one come now, who waits until someone in the meeting lets them in."""
    data = body(request)
    name = " ".join(str(data.get("name") or "").split())[:NAME]
    if (key := data.get("key")) is None:
        if not name:
            raise Refused(400, "no_name")
        with transaction.atomic():
            meeting = Meeting.objects.select_for_update().filter(pk=pk).first()
            if meeting is None:
                raise Refused(404, "no_meeting")
            waiting = meeting.guests.filter(
                by=None,
                state=Guest.State.WAITING,
                came_at__gt=timezone.now() - DOOR_WITHIN,
            )
            if waiting.count() >= DOOR:
                raise Refused(429, "door_full")
            made = Guest.objects.create(meeting=meeting, name=name, state=Guest.State.WAITING)
        return JsonResponse({"key": made.key, "state": made.state}, status=201)
    found = _guest_of(pk, key)
    if name and name != found.name:
        found.name = name
        found.save(update_fields=["name"])
        if found.at_door:
            lobby.told(found.meeting)
    if not found.name:
        raise Refused(400, "no_name")
    return JsonResponse({"key": found.key, "state": found.state})


@api("POST", signed_in=False)
def guest_join(request, pk):
    """The key a guest let in enters the room with, each joining a participant of its own."""
    found = _guest_of(pk, body(request).get("key"))
    if found.state == Guest.State.REFUSED:
        raise Refused(403, "entry_refused")
    if found.state != Guest.State.ADMITTED:
        raise Refused(403, "not_admitted")
    identity = f"{livekit.guest_identity(found.pk)}.{secrets.token_hex(4)}"
    token = livekit.joining(str(found.meeting_id), identity, found.name, guest=True)
    return JsonResponse({"token": token, "ice": _ice()})


@api("PATCH")
def guest(request, pk, guest):
    """Lets a guest at the door in or turns them away, as anyone in the meeting's conversation
    may."""
    state = body(request).get("state")
    if state not in (Guest.State.ADMITTED, Guest.State.REFUSED):
        raise Refused(400, "invalid_state")
    found = (
        Guest.objects.select_related("meeting")
        .filter(pk=guest, meeting_id=pk, meeting__conversation__members__user=request.user)
        .first()
    )
    if found is None:
        raise Refused(404, "no_guest")
    lobby.answered(found, request.user, state)
    return HttpResponse(status=204)


def _member(user, pk: uuid.UUID) -> Meeting:
    found = Meeting.objects.filter(pk=pk, conversation__members__user=user).first()
    if found is None:
        raise Refused(404, "no_meeting")
    return found


async def _inside(pk: uuid.UUID, who: str) -> None:
    """Refuses whoever is not in the call now."""
    try:
        identities = await livekit.inside(str(pk))
    except livekit.Unavailable as unavailable:
        log.warning("meetings: %s", unavailable)
        raise Refused(503, "meetings_unavailable") from unavailable
    if who not in {recordings.person(each) for each in identities}:
        raise Refused(403, "not_in_call")


def _recording_shown(user, pk: uuid.UUID) -> dict:
    found = recordings.running(_member(user, pk))
    return {
        "recording": found and recordings.describe(found),
        "asks": recordings.asks(found, str(user.pk), user),
    }


def _started(user, pk: uuid.UUID) -> dict:
    return recordings.describe(recordings.start(user, _member(user, pk)))


def _stopped(user, pk: uuid.UUID) -> dict:
    return recordings.describe(recordings.stop(_member(user, pk)))


@api("GET", "POST", "DELETE")
async def recording(request, pk):
    """Whether the meeting is being recorded, and for a member in the call, starting and
    stopping it."""
    user = request.user
    if request.method == "GET":
        return JsonResponse(await database(_recording_shown)(user, pk))
    await _inside(pk, str(user.pk))
    if request.method == "POST":
        return JsonResponse(await waited(lambda: _started(user, pk)), status=201)
    return JsonResponse(await waited(lambda: _stopped(user, pk)))


def _agreed(found: Recording | None, who: str, data: dict) -> HttpResponse:
    if found is None:
        raise Refused(409, "not_recording")
    if not isinstance(agreed := data.get("agreed"), bool):
        raise Refused(400, "invalid_consent")
    recordings.consented(found, who, agreed)
    return HttpResponse(status=204)


@api("POST")
def recording_consent(request, pk):
    """A member's answer, in the call, to their speech going to speech to text for the minutes."""
    found = recordings.running(_member(request.user, pk))
    return _agreed(found, str(request.user.pk), body(request))


def _admitted(pk: uuid.UUID, key) -> Guest:
    found = _guest_of(pk, key)
    if found.state != Guest.State.ADMITTED:
        raise Refused(403, "not_admitted")
    return found


@api("GET", "POST", signed_in=False)
def guest_recording(request, pk, key):
    """For a guest let in: whether the meeting is being recorded and whether they are asked
    about their speech, or their answer."""
    found = _admitted(pk, key)
    who = livekit.guest_identity(found.pk)
    running = recordings.running(found.meeting)
    if request.method == "POST":
        return _agreed(running, who, body(request))
    return JsonResponse({"recording": running is not None, "asks": recordings.asks(running, who)})


@api("GET")
def meeting_recordings(request, pk):
    """The meeting's recordings, each with its tracks on the recording's time for playing them
    together; none for whoever came by its link and is not yet among its members."""
    found = Recording.objects.filter(
        meeting=pk, meeting__conversation__members__user=request.user
    ).order_by("-started_at")
    return JsonResponse(
        {"recordings": [{**recordings.describe(each), "tracks": each.tracks} for each in found]}
    )


@api("POST")
def recording_again(request, pk):
    """Saves again a recording whose saving failed, for whoever started it."""
    return JsonResponse(recordings.describe(recordings.again(request.user, pk)), status=202)


@csrf_exempt
@require_POST
def recorded(request):
    """The recorder telling a recording ended by itself, with the key it was given."""
    try:
        data = json.loads(request.body)
        pk, key = uuid.UUID(str(data["id"])), str(data["key"])
    except ValueError, KeyError, TypeError:
        return JsonResponse({"error": "invalid"}, status=400)
    if not recordings.ended(pk, key):
        return JsonResponse({"error": "no_recording"}, status=404)
    return HttpResponse(status=204)
