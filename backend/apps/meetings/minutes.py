"""The minutes of a recorded meeting (S2-6): each utterance of those who agreed is read by speech
to text on its own (D28), so the transcript knows who said what and when, and the installation's
model writes from it the summary, the decisions and the tasks, each task given to the member it
names. The minutes are a document in the recording's folder; without the model, the transcript
alone."""

from datetime import date, timedelta
from logging import getLogger

from django.db import transaction
from django.utils import timezone
from pycrdt import Doc

from apps.actions import runs
from apps.actions.models import ActionRun
from apps.ai import installation, model, speech, vocabulary
from apps.ai.installation import Unavailable
from apps.ai.model import Choice, Prompt
from apps.collab.models import Update
from apps.content import operations
from apps.content.sheets import Sheets
from apps.documents.models import Node
from apps.documents.views import created
from apps.help import library
from apps.tasks.models import Task

from . import recorder, recordings
from .models import Recording

log = getLogger(__name__)

ACTION = "meeting.minutes"
MODEL = "claude-opus-5-5"
LANGUAGES = {"hr": "Croatian", "en": "English"}
WORDS = {
    "hr": {
        "title": "Zapisnik",
        "summary": "Sažetak",
        "decisions": "Odluke",
        "tasks": "Zadaci",
        "present": "Prisutni",
        "transcript": "Prijepis",
        "due": "do",
        "date": "%d. %m. %Y.",
    },
    "en": {
        "title": "Minutes",
        "summary": "Summary",
        "decisions": "Decisions",
        "tasks": "Tasks",
        "present": "Present",
        "transcript": "Transcript",
        "due": "by",
        "date": "%Y-%m-%d",
    },
}
INSTRUCTION = """\
Below is the transcript of a meeting: each line the time it was said, who said it and what, \
written by speech to text, so a word may have been misheard. Write its minutes in {language} \
with one call to the tool minutes:

- summary: what was discussed and what came of it, in a few sentences, as minutes state it, \
without retelling who said what in turn.
- decisions: each decision the meeting took, one sentence each; none where it took none.
- tasks: each thing someone undertook or was given to do, as a short imperative or noun phrase. \
owner is the person it falls to, written exactly as in the list of people, where the transcript \
says who; empty where it does not. due is the day it is due, worked out from the meeting's \
date, only where one was said.

Leave out greetings, small talk and anything not said: no decision or task of your own."""


def _minutes_tool(people: list[str]) -> Choice:
    return Choice(
        "Gives the meeting's minutes.",
        {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "minLength": 1, "maxLength": 5000},
                "decisions": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1, "maxLength": 1000},
                    "maxItems": 50,
                },
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "minLength": 1, "maxLength": 500},
                            "owner": {"enum": [*people, ""]},
                            "due": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
                        },
                        "required": ["text", "owner"],
                        "additionalProperties": False,
                    },
                    "maxItems": 50,
                },
            },
            "required": ["summary", "decisions", "tasks"],
            "additionalProperties": False,
        },
    )


def _name(utterance: dict) -> str:
    return utterance.get("name") or recordings.person(utterance["identity"])


def transcript(found: Recording, made: dict, user) -> list[tuple[int, str, str]]:
    """What those who agreed said, in the order they said it: the milliseconds from the start,
    the name and the text."""
    allowed = recordings.agreed(found)
    said = [each for each in made["utterances"] if recordings.person(each["identity"]) in allowed]
    names = sorted({_name(each) for each in made["utterances"]})
    words = " ".join(
        filter(None, [vocabulary.prompt(user), f"People in the meeting: {', '.join(names)}."])
    )
    lines = []
    for each in sorted(said, key=lambda each: each["start"]):
        text = speech.transcribe(recorder.read(str(found.pk), each["file"]), "audio/webm", words)
        if text.strip():
            lines.append((each["start"], _name(each), text.strip()))
    return lines


def _clock(found: Recording, milliseconds: int) -> str:
    return f"{timezone.localtime(found.started_at) + timedelta(milliseconds=milliseconds):%H:%M:%S}"


def _decided(found: Recording, lines: list, people: list[str], user, language: str) -> dict | None:
    """The minutes the installation's model writes, or None where it is off or fails."""
    if not lines or not installation.enabled():
        return None
    started = timezone.localtime(found.started_at)
    written = "\n".join(f"[{_clock(found, at)}] {name}: {text}" for at, name, text in lines)
    prompt = Prompt(
        INSTRUCTION.format(language=LANGUAGES[language]),
        f"The meeting: {found.meeting.title or '-'}, {started:%Y-%m-%d}, a {started:%A}.\n"
        f"People: {'; '.join(people)}\n\n{written}",
        {"minutes": _minutes_tool(people)},
        effort="medium",
        steps=3,
    )
    run = ActionRun.objects.create(
        user=user,
        action=ACTION,
        target={},
        consent=ActionRun.Consented.USER,
        consented_by=user,
    )
    answers: list[dict] = []
    try:
        installation.allowed(user.pk)
        model.converse(MODEL, prompt, answers.append, lambda: False, runs.spending(run))
        if not answers:
            raise model.Failed("no_answer")
    except (model.Failed, Unavailable) as failed:
        log.warning("meetings: the minutes of %s were not written: %s", found.pk, failed.code)
        ActionRun.objects.filter(pk=run.pk).update(
            state=ActionRun.State.FAILED, error=failed.code, finished_at=timezone.now()
        )
        return None
    ActionRun.objects.filter(pk=run.pk).update(
        state=ActionRun.State.DONE, finished_at=timezone.now()
    )
    return answers[-1]


def _block(kind: str, text: str, **attrs) -> dict:
    return {
        "type": kind,
        **({"attrs": attrs} if attrs else {}),
        "content": [{"type": "text", "text": text}] if text else [],
    }


def _due(given: str | None) -> date | None:
    try:
        return date.fromisoformat(given) if given else None
    except ValueError:
        return None


def _content(found: Recording, lines: list, people: list[str], decided: dict | None, words):
    made = []
    if decided is not None:
        made.append(_block("heading", words["summary"], level=2))
        made += [_block("paragraph", each) for each in decided["summary"].split("\n") if each]
        if decided["decisions"]:
            made.append(_block("heading", words["decisions"], level=2))
            made += [_block("paragraph", each, list="bullet") for each in decided["decisions"]]
        if decided["tasks"]:
            made.append(_block("heading", words["tasks"], level=2))
            for task in decided["tasks"]:
                due = _due(task.get("due"))
                told = ", ".join(
                    filter(None, [task["owner"], due and f"{words['due']} {due:{words['date']}}"])
                )
                text = f"{task['text']} ({told})" if told else task["text"]
                made.append(_block("paragraph", text, list="check"))
    made.append(_block("heading", words["present"], level=2))
    made += [_block("paragraph", each, list="bullet") for each in people]
    if lines:
        made.append(_block("heading", words["transcript"], level=2))
        made += [
            _block("paragraph", f"[{_clock(found, at)}] {name}: {text}") for at, name, text in lines
        ]
    return [operations.block_of(each) for each in made]


def _tasks(decided: dict, document: Node, user, members: dict[str, object]) -> None:
    for task in decided["tasks"]:
        Task.objects.create(
            owner=members.get(task["owner"], user),
            text=task["text"][:1000],
            due=_due(task.get("due")),
            source_kind=Task.Source.DOCUMENT,
            source_label=document.title[:300],
            source_link=f"/d/{document.pk}",
        )


def written(found: Recording, made: dict, folder: Node, user) -> Node | None:
    """The recording's minutes in its folder, with the tasks they name; None where speech to
    text is off or nothing was said that may be written."""
    if not speech.enabled():
        return None
    lines = transcript(found, made, user)
    if not lines:
        return None
    language = library.language_of(None, user)
    words = WORDS[language]
    every = made["tracks"] + made["utterances"]
    people = sorted({_name(each) for each in every})
    users = recordings.users_of({recordings.person(each["identity"]) for each in every})
    members = {
        _name(each): users[recordings.person(each["identity"])]
        for each in every
        if recordings.person(each["identity"]) in users
    }
    decided = _decided(found, lines, people, user, language)
    prepared = operations.write(Doc(), Sheets({}), _content(found, lines, people, decided, words))
    with transaction.atomic():
        title = f"{words['title']} – {folder.title}"
        document = created(folder, Node.Kind.DOCUMENT, title, None, user)
        tab = document.tabs.get()
        Update.objects.create(document=document, tab=tab, room=tab.room, data=prepared.update)
        if decided is not None:
            _tasks(decided, document, user, members)
        Recording.objects.filter(pk=found.pk).update(minutes=document)
    found.minutes = document
    return document
