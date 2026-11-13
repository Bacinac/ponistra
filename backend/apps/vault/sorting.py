"""Folders for a collection's items that a model proposes (D20). It reads only what the browser
lets out of each item, its name and the host of its site, and the names of the folders the
collection has; its proposal goes back to the browser, which seals what the user keeps. The
server keeps none of it, only the run with what it took."""

import json

from apps.actions import runs
from apps.actions.models import ActionRun
from apps.ai import model
from apps.ai.installation import Unavailable
from apps.ai.model import Choice, Prompt
from apps.core.asyncdb import database

from .models import Collection

ACTION = "vault.sort"
MODEL = "claude-sonnet-5-5"
LANGUAGES = {"hr": "Croatian", "en": "English"}
OTHER = {"hr": "Ostalo", "en": "Other"}
INSTRUCTION = """\
You sort the entries of a password manager into folders, so that its user finds a login by what \
it is for. Each entry is a number, the name the user gave it and the host of the site it signs \
in to, either of which may be empty; nothing else of it reaches you. Answer with one call to the \
folders tool.

- Make folders by what the sites are for, such as banking and payments, shopping, travel, \
government and public services, health, telecoms and utilities, social networks, entertainment, \
email, software development and servers, devices and the home network.
- An employer, a client or a school with several entries, which share a domain or a name, gets a \
folder of its own named after it.
- Make at most 20 folders, each with at least 3 entries where the entries allow; join small \
groups into a broader folder.
- Name each folder in {language}, in one to three words, as a person would label it.
- Put every entry into exactly one folder. Entries whose purpose you cannot tell go into a folder \
named "{other}".
- Where the collection has folders already, put entries into those that fit, by their exact \
names, and make new folders only for the rest."""
FOLDERS = Choice(
    "Gives the folders and the numbers of the entries each holds.",
    {
        "type": "object",
        "properties": {
            "folders": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 60},
                        "entries": {"type": "array", "items": {"type": "integer", "minimum": 0}},
                    },
                    "required": ["name", "entries"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["folders"],
        "additionalProperties": False,
    },
)


class Unsorted(Exception):
    """Why the model proposed no folders: a code the vault names."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def propose(
    user, collection: Collection, entries: list[tuple[str, str]], existing: list[str], language: str
) -> list[dict]:
    """The folders the model proposes for the entries, each with the numbers of those it holds,
    its run kept with what it took and the user who let the entries out to it this once."""
    run = await database(ActionRun.objects.create)(
        user=user,
        action=ACTION,
        target={"collection": str(collection.pk)},
        consent=ActionRun.Consented.ONCE,
        consented_by=user,
    )
    prompt = Prompt(
        INSTRUCTION.format(language=LANGUAGES[language], other=OTHER[language]),
        _content(entries, existing),
        {"folders": FOLDERS},
        steps=3,
    )
    try:
        answer = await runs.decided(run, MODEL, prompt)
    except (model.Failed, Unavailable) as failed:
        raise Unsorted(failed.code) from None
    return _proposal(answer, len(entries))


def _content(entries: list[tuple[str, str]], existing: list[str]) -> str:
    listed = ",\n".join(
        json.dumps([number, name, host], ensure_ascii=False)
        for number, (name, host) in enumerate(entries)
    )
    had = json.dumps(existing, ensure_ascii=False) if existing else "none"
    return (
        f"Folders the collection has: {had}\n\nEntries, each [number, name, host]:\n[\n{listed}\n]"
    )


def _proposal(answer: dict, count: int) -> list[dict]:
    """The model's folders as the browser takes them: each entry in the first folder that names
    it, folders of one name as one, and none left empty."""
    folders: dict[str, dict] = {}
    placed: set[int] = set()
    for each in answer["folders"]:
        name = " ".join(each["name"].split())
        taken = []
        for number in each["entries"]:
            if number < count and number not in placed:
                placed.add(number)
                taken.append(number)
        if name and taken:
            folders.setdefault(name.casefold(), {"name": name, "entries": []})["entries"] += taken
    return list(folders.values())
