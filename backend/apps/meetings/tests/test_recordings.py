import json
from contextlib import contextmanager
from datetime import date

import pytest
from django.test import Client
from pycrdt import Doc

from apps.access.models import Grant, Role
from apps.ai import installation, model, speech
from apps.ai.models import SpeechConsent
from apps.chat import conversations
from apps.content.blocks import body_of
from apps.documents.models import Node
from apps.jobs.models import Job
from apps.meetings import livekit, recorder, recordings
from apps.meetings.models import Guest, Meeting, Recording
from apps.tasks.models import Task
from apps.users.models import User
from apps.versions import history


@pytest.fixture
def owner():
    return User.objects.create_user(
        "ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo", last_name="Bošković"
    )


@pytest.fixture
def ana():
    return User.objects.create_user(
        "ana@example.com", "Kamen-Most-Rijeka-72", first_name="Ana", last_name="Horvat"
    )


@pytest.fixture
def meeting(owner, ana):
    made = Meeting.objects.made("Kolegij", owner)
    conversations.added(made.conversation, [ana])
    return made


def signed(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def sent(client, method, path, **data):
    return getattr(client, method)(path, json.dumps(data), content_type="application/json")


class Recorder:
    def __init__(self):
        self.started: list[tuple] = []
        self.stopped: list[str] = []
        self.forgotten: list[str] = []
        self.manifest: dict | None = None
        self.down = False

    def start(self, pk, url, token, key):
        if self.down:
            raise recorder.Unavailable("down")
        self.started.append((pk, url, token, key))

    def stop(self, pk):
        self.stopped.append(pk)
        return {}

    def made(self, pk):
        if self.down:
            raise recorder.Unavailable("down")
        return self.manifest

    @contextmanager
    def opened(self, pk, name):
        class Answer:
            def iter_bytes(self, _size):
                yield f"webm {name}".encode()

        yield Answer()

    def read(self, pk, name):
        return f"webm {name}".encode()

    def forget(self, pk):
        self.forgotten.append(pk)


@pytest.fixture
def faked(monkeypatch):
    fake = Recorder()
    for name in ("start", "stop", "made", "opened", "read", "forget"):
        monkeypatch.setattr(recorder, name, getattr(fake, name))
    told: list[tuple[str, bool]] = []
    monkeypatch.setattr(livekit, "recorded", lambda room, on: told.append((room, on)))
    fake.told = told
    return fake


@pytest.fixture
def present(monkeypatch):
    there: list[str] = []

    async def inside(room):
        return there

    monkeypatch.setattr(livekit, "inside", inside)
    return there


@pytest.mark.django_db(transaction=True)
def test_a_member_in_the_call_starts_and_stops_the_recording_which_is_then_saved(
    owner, ana, meeting, faked, present
):
    at = f"/api/meetings/{meeting.id}/recording"
    away = signed(ana).post(at)
    assert (away.status_code, away.json()) == (403, {"error": "not_in_call"})
    present[:] = [f"{owner.pk}.a1", f"{ana.pk}.b2"]
    started = signed(owner).post(at)
    assert started.status_code == 201, started.json()
    assert started.json()["state"] == "recording"
    found = Recording.objects.get()
    [(pk, url, token, key)] = faked.started
    assert (pk, key) == (str(found.pk), found.key)
    assert url.startswith("ws://") and token
    assert faked.told == [(str(meeting.id), True)]
    shown = signed(ana).get(at).json()
    assert (shown["recording"]["id"], shown["asks"]) == (str(found.pk), False)
    twice = signed(ana).post(at)
    assert (twice.status_code, twice.json()) == (409, {"error": "already_recording"})

    stopped = signed(ana).delete(at)
    assert (stopped.status_code, stopped.json()["state"]) == (200, "saving")
    assert faked.stopped == [str(found.pk)]
    assert faked.told[-1] == (str(meeting.id), False)
    job = Job.objects.get()
    assert (job.kind, job.user, job.parameters) == (
        "recording",
        owner,
        {"recording": str(found.pk)},
    )
    again = signed(ana).delete(at)
    assert (again.status_code, again.json()) == (409, {"error": "not_recording"})
    assert signed(ana).get(at).json() == {"recording": None, "asks": False}


@pytest.mark.django_db(transaction=True)
def test_a_recording_the_recorder_did_not_take_fails_and_another_may_start(
    owner, meeting, faked, present
):
    present[:] = [f"{owner.pk}.a1"]
    faked.down = True
    at = f"/api/meetings/{meeting.id}/recording"
    refused = signed(owner).post(at)
    assert (refused.status_code, refused.json()) == (503, {"error": "recording_unavailable"})
    failed = Recording.objects.get()
    assert (failed.state, failed.error, failed.ended_at is not None) == (
        "failed",
        "not_started",
        True,
    )
    assert recordings.describe(failed)["saves_again"] is False
    faked.down = False
    assert signed(owner).post(at).status_code == 201


@pytest.mark.django_db
def test_the_recordings_are_listed_to_the_members_and_to_no_one_else(owner, meeting):
    Recording.objects.create(meeting=meeting, started_by=owner)
    at = f"/api/meetings/{meeting.id}/recordings"
    [shown] = signed(owner).get(at).json()["recordings"]
    assert (shown["state"], shown["tracks"]) == ("recording", [])
    stranger = User.objects.create_user("vid@example.com", "Kamen-Most-Rijeka-73")
    assert signed(stranger).get(at).json() == {"recordings": []}


@pytest.mark.django_db
def test_the_recorder_ends_a_recording_with_its_key_once(owner, meeting, faked):
    found = Recording.objects.create(meeting=meeting, started_by=owner)
    outside = Client()
    wrong = sent(outside, "post", "/api/meetings/recorded", id=str(found.pk), key="x")
    assert (wrong.status_code, wrong.json()) == (404, {"error": "no_recording"})
    unread = outside.post("/api/meetings/recorded", "{", content_type="application/json")
    assert unread.status_code == 400
    for _ in range(2):
        told = sent(outside, "post", "/api/meetings/recorded", id=str(found.pk), key=found.key)
        assert told.status_code == 204
    found.refresh_from_db()
    assert (found.state, found.ended_at is not None) == ("saving", True)
    assert Job.objects.count() == 1


@pytest.mark.django_db
def test_each_is_asked_once_about_their_speech_and_a_refusal_overrides_the_standing_consent(
    owner, ana, meeting, faked, monkeypatch
):
    monkeypatch.setattr(speech, "enabled", lambda: True)
    found = Recording.objects.create(meeting=meeting, started_by=owner)
    SpeechConsent.objects.create(user=owner)
    SpeechConsent.objects.create(user=ana)
    guest = Guest.objects.create(meeting=meeting, name="Eva", state=Guest.State.ADMITTED)
    at = f"/api/meetings/{meeting.id}"
    assert signed(owner).get(f"{at}/recording").json()["asks"] is False
    assert recordings.asks(found, str(ana.pk), User.objects.create_user("x@example.com", "p"))
    refused = sent(signed(ana), "post", f"{at}/recording/consent", agreed=False)
    assert refused.status_code == 204
    door = f"{at}/guests/{guest.key}/recording"
    assert Client().get(door).json() == {"recording": True, "asks": True}
    assert sent(Client(), "post", door, agreed=True).status_code == 204
    assert Client().get(door).json() == {"recording": True, "asks": False}
    wrong = sent(Client(), "post", door, agreed="yes")
    assert (wrong.status_code, wrong.json()) == (400, {"error": "invalid_consent"})
    found.refresh_from_db()
    assert recordings.agreed(found) == {str(owner.pk), f"guest{guest.pk}"}
    Guest.objects.filter(pk=guest.pk).update(state=Guest.State.WAITING)
    assert Client().get(door).status_code == 403


def manifest(owner, ana, guest) -> dict:
    def track(identity, name, source, file, start=0):
        kind = "video" if source == "camera" else "audio"
        return {
            "kind": kind,
            "file": file,
            "identity": identity,
            "name": name,
            "source": source,
            "start": start,
        }

    def said(identity, name, file, start):
        return {"kind": "utterance", "file": file, "identity": identity, "name": name,
                "start": start, "end": start + 900}  # fmt: skip

    return {
        "tracks": [
            track(f"{owner.pk}.a1", "Ivo Bošković", "microphone", "t1.webm"),
            track(f"{ana.pk}.b2", "Ana Horvat", "camera", "t2.webm", 500),
            track(f"{ana.pk}.b2", "Ana Horvat", "camera", "t3.webm", 9000),
            track(f"guest{guest.pk}.c3", "Eva", "microphone", "t4.webm", 1200),
        ],
        "utterances": [
            said(f"guest{guest.pk}.c3", "Eva", "s3.webm", 3000),
            said(f"{owner.pk}.a1", "Ivo Bošković", "s1.webm", 1000),
            said(f"{ana.pk}.b2", "Ana Horvat", "s2.webm", 2000),
        ],
    }


def text_of(document: Node) -> str:
    doc = Doc()
    doc.apply_update(history.state_of(document.tabs.get().room))
    return str(body_of(doc))


@pytest.mark.django_db
def test_the_saved_recording_is_a_folder_its_people_read_with_minutes_and_tasks(
    owner, ana, meeting, faked, monkeypatch
):
    guest = Guest.objects.create(meeting=meeting, name="Eva", state=Guest.State.ADMITTED)
    found = Recording.objects.create(
        meeting=meeting,
        started_by=owner,
        state=Recording.State.SAVING,
        consents={str(ana.pk): False, f"guest{guest.pk}": True},
    )
    SpeechConsent.objects.create(user=owner)
    faked.manifest = manifest(owner, ana, guest)
    monkeypatch.setattr(speech, "enabled", lambda: True)
    monkeypatch.setattr(installation, "enabled", lambda: True)
    heard: list[str] = []

    def transcribe(audio, media_type, words):
        assert media_type == "audio/webm" and "Ana Horvat" in words
        heard.append(audio.decode())
        return {"webm s1.webm": "Ana šalje ponudu do petka.", "webm s3.webm": "Dogovoreno."}[
            audio.decode()
        ]

    monkeypatch.setattr(speech, "transcribe", transcribe)
    asked: list = []

    def converse(name, prompt, call, stopped, spend):
        asked.append(prompt)
        call(
            {
                "op": "minutes",
                "summary": "Dogovorena ponuda.",
                "decisions": ["Ponuda ide u petak."],
                "tasks": [
                    {"text": "Poslati ponudu", "owner": "Ana Horvat", "due": "2026-11-13"},
                    {"text": "Javiti se dobavljaču", "owner": ""},
                ],
            }
        )
        return ""

    monkeypatch.setattr(model, "converse", converse)

    described = recordings.saved(owner, {"recording": str(found.pk)})
    assert described["state"] == "done"
    assert heard == ["webm s1.webm", "webm s3.webm"]
    assert "Ana šalje ponudu" in asked[0].content and "Eva: Dogovoreno." in asked[0].content
    found.refresh_from_db()
    folder = found.folder
    assert folder.parent is None and folder.title.startswith("Kolegij ")
    files = Node.objects.filter(parent=folder, kind=Node.Kind.FILE).order_by("title")
    assert [(each.title, each.extension) for each in files] == [
        ("Ana Horvat – kamera", "webm"),
        ("Ana Horvat – kamera (2)", "webm"),
        ("Eva – mikrofon", "webm"),
        ("Ivo Bošković – mikrofon", "webm"),
    ]
    assert [each["node"] for each in found.tracks] and all(t["node"] for t in found.tracks)
    assert sorted(Grant.objects.filter(node=folder).values_list("user", "role")) == [
        (owner.pk, Role.OWN),
        (ana.pk, Role.READ),
    ]
    assert found.minutes.parent == folder and found.minutes.title.startswith("Zapisnik – Kolegij")
    written = text_of(found.minutes)
    assert "Ponuda ide u petak." in written and "Javiti se dobavljaču" in written
    assert "Ana šalje ponudu do petka." in written and "Horvat:" not in written
    tasks = Task.objects.order_by("text")
    assert [(t.text, t.owner, t.due, t.source_link) for t in tasks] == [
        ("Javiti se dobavljaču", owner, None, f"/d/{found.minutes.pk}"),
        ("Poslati ponudu", ana, date(2026, 11, 13), f"/d/{found.minutes.pk}"),
    ]
    assert faked.forgotten == [str(found.pk)]
    recordings.saved(owner, {"recording": str(found.pk)})
    assert Node.objects.filter(parent=folder).count() == 5 and Task.objects.count() == 2


@pytest.mark.django_db
def test_a_saving_that_failed_keeps_the_files_and_its_starter_saves_it_again(
    owner, ana, meeting, faked, monkeypatch
):
    guest = Guest.objects.create(meeting=meeting, name="Eva", state=Guest.State.ADMITTED)
    found = Recording.objects.create(
        meeting=meeting, started_by=owner, state=Recording.State.SAVING, consents={}
    )
    SpeechConsent.objects.create(user=owner)
    faked.manifest = manifest(owner, ana, guest)
    monkeypatch.setattr(speech, "enabled", lambda: True)
    monkeypatch.setattr(installation, "enabled", lambda: False)

    def refused(audio, media_type, words):
        raise installation.Unavailable("speech_key_refused")

    monkeypatch.setattr(speech, "transcribe", refused)
    with pytest.raises(Exception) as raised:
        recordings.saved(owner, {"recording": str(found.pk)})
    assert raised.value.error == "speech_key_refused"
    found.refresh_from_db()
    assert (found.state, found.error, found.minutes) == ("failed", "speech_key_refused", None)
    assert found.folder is not None and faked.forgotten == []

    at = f"/api/meetings/recordings/{found.pk}/again"
    assert signed(ana).post(at).status_code == 404
    again = signed(owner).post(at)
    assert (again.status_code, again.json()["state"]) == (202, "saving")
    assert signed(owner).post(at).status_code == 409
    monkeypatch.setattr(speech, "transcribe", lambda audio, media_type, words: "Dobar dan.")
    recordings.saved(owner, Job.objects.get().parameters)
    found.refresh_from_db()
    assert (found.state, found.error) == ("done", "")
    assert Node.objects.filter(kind=Node.Kind.FOLDER, title=found.folder.title).count() == 1
    written = text_of(found.minutes)
    assert "Dobar dan." in written and "Sažetak" not in written
    assert faked.forgotten == [str(found.pk)]
    listed = signed(ana).get(f"/api/meetings/{meeting.id}/recordings").json()["recordings"]
    assert [(each["id"], each["minutes"]) for each in listed] == [
        (str(found.pk), str(found.minutes_id))
    ]
