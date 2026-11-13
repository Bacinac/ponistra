"""Recording a meeting (S2-5): started and stopped by a member in the call, the room told so that
everyone in it, guests too, sees it; once it ends, by a member or as the room stays empty, a job
takes each participant's files into a folder of the starter's, which those who took part may
read, and writes its minutes (S2-6, `minutes.py`)."""

import hmac
from logging import getLogger

from django.db import IntegrityError, transaction
from django.db.models.functions import Coalesce, Now
from django.utils import timezone

from apps.access.models import Grant, Role
from apps.ai import speech
from apps.ai.installation import Unavailable
from apps.ai.models import SpeechConsent
from apps.blobs import previews, store
from apps.core.api import Refused
from apps.core.asyncdb import notify, released
from apps.documents.models import Node
from apps.documents.views import created
from apps.help import library
from apps.jobs.models import Job
from apps.search import extraction
from apps.users.models import User

from . import livekit, recorder
from .models import Meeting, Recording

log = getLogger(__name__)

KIND = "recording"
SOURCES = {
    "hr": {
        "microphone": "mikrofon",
        "camera": "kamera",
        "screen_share": "zaslon",
        "screen_share_audio": "zvuk zaslona",
    },
    "en": {
        "microphone": "microphone",
        "camera": "camera",
        "screen_share": "screen",
        "screen_share_audio": "screen sound",
    },
}
# A recording that ended so: nothing was recorded that could be saved again.
UNSAVED = {"not_started", "no_owner"}
MEETING = {"hr": "Sastanak", "en": "Meeting"}
WHEN = {"hr": "%d. %m. %Y. %H:%M", "en": "%Y-%m-%d %H:%M"}


def person(identity: str) -> str:
    """Whom a participant's identity names: a user's id or a guest's, the mark of the device
    after the dot left out."""
    return identity.split(".", 1)[0]


def running(meeting: Meeting) -> Recording | None:
    return meeting.recordings.filter(state=Recording.State.RECORDING).first()


def describe(found: Recording) -> dict:
    return {
        "id": str(found.pk),
        "state": found.state,
        "started_by": found.started_by_id,
        "started_at": found.started_at,
        "ended_at": found.ended_at,
        "folder": found.folder_id and str(found.folder_id),
        "minutes": found.minutes_id and str(found.minutes_id),
        "error": found.error,
        "saves_again": found.state == Recording.State.FAILED and found.error not in UNSAVED,
    }


def start(user, meeting: Meeting) -> Recording:
    try:
        with transaction.atomic():
            made = Recording.objects.create(meeting=meeting, started_by=user)
    except IntegrityError:
        raise Refused(409, "already_recording") from None
    room = str(meeting.pk)
    released()
    try:
        recorder.start(str(made.pk), livekit.address(), livekit.recording(room), made.key)
    except recorder.Unavailable as unavailable:
        log.warning("meetings: %s", unavailable)
        _failed(made, "not_started")
        raise Refused(503, "recording_unavailable") from unavailable
    try:
        livekit.recorded(room, True)
    except livekit.Unavailable as unavailable:
        log.warning("meetings: %s", unavailable)
        _stopped(made)
        raise Refused(503, "recording_unavailable") from unavailable
    return made


def stop(meeting: Meeting) -> Recording:
    found = running(meeting)
    if found is None:
        raise Refused(409, "not_recording")
    released()
    try:
        recorder.stop(str(found.pk))
    except recorder.Unavailable as unavailable:
        log.warning("meetings: %s", unavailable)
        raise Refused(503, "recording_unavailable") from unavailable
    return _ended(found)


def ended(pk, key: str) -> bool:
    """The recorder telling the recording ended by itself; False where it names none."""
    found = Recording.objects.filter(pk=pk).first()
    if found is None or not hmac.compare_digest(found.key, key):
        return False
    if found.state == Recording.State.RECORDING:
        _ended(found)
    return True


def _stopped(found: Recording) -> None:
    try:
        recorder.stop(str(found.pk))
        recorder.forget(str(found.pk))
    except recorder.Unavailable as unavailable:
        log.warning("meetings: %s", unavailable)
    _failed(found, "not_started")


def _failed(found: Recording, error: str) -> None:
    Recording.objects.filter(pk=found.pk).update(
        state=Recording.State.FAILED, error=error, ended_at=Coalesce("ended_at", Now())
    )


def _ended(found: Recording) -> Recording:
    with transaction.atomic():
        changed = Recording.objects.filter(pk=found.pk, state=Recording.State.RECORDING).update(
            state=Recording.State.SAVING, ended_at=timezone.now()
        )
        if changed and found.started_by_id is not None:
            _job(found, found.started_by_id)
        elif changed:
            _failed(found, "no_owner")
    try:
        livekit.recorded(str(found.meeting_id), False)
    except livekit.Unavailable as unavailable:
        log.warning("meetings: %s", unavailable)
    found.refresh_from_db()
    return found


def consented(found: Recording, identity: str, agreed: bool) -> None:
    with transaction.atomic():
        locked = Recording.objects.select_for_update().get(pk=found.pk)
        locked.consents[person(identity)] = agreed
        locked.save(update_fields=["consents"])


def asks(found: Recording | None, who: str, user=None) -> bool:
    """Whether the participant is still to say whether their speech goes to speech to text."""
    if found is None or not speech.enabled() or who in found.consents:
        return False
    return user is None or not SpeechConsent.objects.filter(user=user).exists()


def agreed(found: Recording) -> set[str]:
    """Those whose speech goes to speech to text: who agreed in the call, and the members who
    agreed to their speech going to it and did not refuse in the call."""
    said = {who for who, yes in found.consents.items() if yes}
    refused = {who for who, yes in found.consents.items() if not yes}
    standing = SpeechConsent.objects.values_list("user_id", flat=True)
    return said | ({str(pk) for pk in standing} - refused)


def users_of(identities: set[str]) -> dict[str, User]:
    pks = [int(each) for each in identities if each.isdigit()]
    return {str(user.pk): user for user in User.objects.filter(pk__in=pks)}


def _title(found: Recording, user) -> tuple[str, str]:
    language = library.language_of(None, user)
    started = timezone.localtime(found.started_at)
    title = found.meeting.title or MEETING[language]
    return language, f"{title} {started.strftime(WHEN[language])}"


class _Streamed:
    """A file the recorder sends, read as the store reads a file."""

    def __init__(self, answer) -> None:
        self.chunks = answer.iter_bytes(store.CHUNK)

    def read(self, _size: int = -1) -> bytes:
        return next(self.chunks, b"")


def _saved(found: Recording, made: dict, user) -> Node:
    """The recording's folder, each track a file of it, shared with the members who took
    part; once made, the same folder again. The files are taken before the folder is made, so
    that a run cut off leaves no half folder, only files nothing holds, which are collected."""
    if found.folder is not None:
        return found.folder
    blobs = []
    for track in made["tracks"]:
        with recorder.opened(str(found.pk), track["file"]) as answer:
            blobs.append(store.put(_Streamed(answer)))
    language, title = _title(found, user)
    people = users_of({person(each["identity"]) for each in made["tracks"] + made["utterances"]})
    named: dict[str, int] = {}
    tracks = []
    with transaction.atomic():
        folder = created(None, Node.Kind.FOLDER, title, None, user)
        for track, blob in zip(made["tracks"], blobs, strict=True):
            source = SOURCES[language].get(track.get("source", ""), track.get("source", ""))
            label = f"{track.get('name') or person(track['identity'])} – {source}"
            named[label] = named.get(label, 0) + 1
            if named[label] > 1:
                label = f"{label} ({named[label]})"
            node = created(folder, Node.Kind.FILE, label, blob, user, "webm")
            tracks.append({**track, "node": str(node.pk)})
        for each in people.values():
            if each.pk != user.pk:
                Grant.objects.create(node=folder, user=each, role=Role.READ, created_by=user)
        Recording.objects.filter(pk=found.pk).update(folder=folder, tracks=tracks)
    extraction.wake()
    previews.wake()
    found.folder, found.tracks = folder, tracks
    return folder


def _job(found: Recording, user_id: int) -> None:
    Job.objects.create(user_id=user_id, kind=KIND, parameters={"recording": str(found.pk)})
    transaction.on_commit(lambda: notify("jobs"))


def again(user, pk) -> Recording:
    """A recording whose saving failed, handed over to be saved again by whoever started it."""
    with transaction.atomic():
        found = Recording.objects.select_for_update().filter(pk=pk, started_by=user).first()
        if found is None:
            raise Refused(404, "no_recording")
        if found.state != Recording.State.FAILED or found.error in UNSAVED:
            raise Refused(409, "recording_not_failed")
        found.state, found.error = Recording.State.SAVING, ""
        found.save(update_fields=["state", "error"])
        _job(found, user.pk)
    return found


def saved(user, parameters: dict) -> dict:
    """The job: the recording into the tree, then its minutes; the recorder lets its files go
    once both are made, and keeps them while either failed, to be saved again."""
    from . import minutes

    found = Recording.objects.select_related("meeting").get(pk=parameters["recording"])
    if found.state != Recording.State.SAVING:
        return describe(found)
    try:
        made = recorder.made(str(found.pk))
        if made is None:
            raise recorder.Unavailable("the recorder holds no such recording")
        folder = _saved(found, made, user)
        if found.minutes is None:
            minutes.written(found, made, folder, user)
        recorder.forget(str(found.pk))
    except recorder.Unavailable as unavailable:
        log.warning("meetings: %s", unavailable)
        _failed(found, "recorder_unavailable")
        raise Refused(503, "recording_unavailable") from unavailable
    except Unavailable as unavailable:
        _failed(found, unavailable.code)
        raise Refused(503, unavailable.code) from unavailable
    except Exception:
        _failed(found, "unsaved")
        raise
    Recording.objects.filter(pk=found.pk).update(state=Recording.State.DONE)
    found.state = Recording.State.DONE
    return describe(found)
