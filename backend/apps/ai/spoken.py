from datetime import datetime

from apps.actions import runs
from apps.actions.models import ActionRun
from apps.ai import model
from apps.ai.installation import Unavailable
from apps.ai.model import Choice, Prompt
from apps.calendar.recurrence import zone_of
from apps.contacts import search as contacts
from apps.core.asyncdb import database
from apps.documents import launcher
from apps.help import library
from apps.search.translation import FILTERS

ACTION = "speech.understand"
MODEL = "claude-haiku-5-5"
ARTICLES = 5
DAY = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
TIME = {"type": "string", "pattern": r"^([01]\d|2[0-3]):[0-5]\d$"}
PLACES = [
    "today",
    "calendar",
    "mail",
    "contacts",
    "documents",
    "notes",
    "links",
    "tasks",
    "chat",
    "vault",
    "settings",
    "trash",
]
INSTRUCTION = """\
The user of an office suite said something into its microphone, and what they said is written \
below. It named none of the suite's commands word for word. Decide what they want and answer \
with one call to one tool:

- open: going to a part of the suite: today (the day's overview), calendar, mail, contacts, \
documents, notes, links (the page of their links to web pages), tasks, chat (conversations and \
meetings), vault (passwords), settings, trash. Only where they ask to go there or to see it \
("otvori poštu", "pokaži mi kalendar"), with nothing to find or make in it. day only for the \
calendar, where they name one ("kalendar za sutra"), worked out from now.
- link: going to a web page or a service by its name, as one opens a site rather than \
something they wrote or received ("otvori Proxmox", "idi na Grafanu"). name is the name as \
said, in its base form ("Grafanu" is "Grafana").
- search: finding something they have: a document, a file, a message, an event, a task or a \
person ("nađi ponudu za Končar", "gdje je Anin zadnji mail"), and reaching a message to answer \
it ("odgovori Evi na mail" is kind mail from Eva). The fields are those of the search box. \
text holds only the words the wanted thing itself contains, each in its base form ("ponudu za \
Končar" is "ponuda Končar"); leave out words that only say what a filter says, such as "mail", \
"dokument", "zadnji" or a name given in from, so text is often empty. kind, from (a name in \
its base form: "Evi" is "Eva"), account, folder, since and until (days worked out from \
now), changed and attachment, each only where it was said.
- person: something about one person they know, to see in their contact: a birthday, a phone \
number, an address, where they work ("kad je rođendan Bore Vrančića", "Anin broj"). name is \
the person's name in its base form ("Bore Vrančića" is "Boro Vrančić").
- mail: writing a new message to someone ("napiši Evi da kasnim deset minuta"). to are the \
people as said, each a name in its base form or an address; subject a short subject; text only \
the body of the message, written out properly in the language they spoke: no greeting such as \
"Bok Eva" or "Poštovani", no closing and no name, since the user's signature follows it. \
account only where they said which of their mail accounts it goes from ("s Gmaila", "s \
poslovnog"), as its address among those listed with what was said.
- document: making a new document ("napravi novi dokument Ponuda za Končar"). title is its \
name as said, or empty where none was said.
- event: something that takes place at a time, such as a meeting, an appointment, a call \
arranged with someone or a trip. summary is what it is, short, as one names it in a calendar \
("Sastanak s Anom", "Zubar"), in the language the user spoke. day and time are when it starts, \
worked out from now; leave time out and set all_day for a whole day. end_day and end_time only \
where the user said when it ends or how long it lasts. location only where they named a place.
- task: something the user is to do, by a day or by none, without a time it takes place at, \
such as "podsjeti me da nazovem servis", "moram poslati ponudu do petka". text is the thing to \
do, short, as an imperative or a noun phrase, without "remind me"; due the day only where one \
was said or follows from what was said.
- help: a question about Ponistra itself, about what it does or how something is done in it \
("kako dodam potpis", "može li se dokument podijeliti", "pretražuješ li pomoć?"), rather than \
about what the user has. text holds the one to three words its help would hold, each in its \
base form and in the language they spoke ("kako dodam potpis" is "potpis").
- note: anything else: a thought, a list, an observation, something to remember.

When unsure between a task and a note, it is a note; between an event and a task, an event \
only where a time or a meeting with someone is said."""
MAIL = {
    "type": "object",
    "properties": {
        "to": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 200},
            "maxItems": 10,
        },
        "subject": {"type": "string", "maxLength": 200},
        "text": {"type": "string", "maxLength": 5000},
    },
    "required": ["to", "subject", "text"],
    "additionalProperties": False,
}
TOOLS = {
    "open": Choice(
        "Opens a part of the suite.",
        {
            "type": "object",
            "properties": {"place": {"enum": PLACES}, "day": DAY},
            "required": ["place"],
            "additionalProperties": False,
        },
    ),
    "search": Choice("Searches what the user has, as the search box does.", FILTERS.schema),
    "link": Choice(
        "Opens one of the user's links to a web page.",
        {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 200}},
            "required": ["name"],
            "additionalProperties": False,
        },
    ),
    "person": Choice(
        "Opens the contact of a person the user knows.",
        {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 200}},
            "required": ["name"],
            "additionalProperties": False,
        },
    ),
    "mail": Choice("Proposes a new message, which the user checks and sends.", MAIL),
    "document": Choice(
        "Proposes a new document in the user's documents, which they make.",
        {
            "type": "object",
            "properties": {"title": {"type": "string", "maxLength": 200}},
            "required": ["title"],
            "additionalProperties": False,
        },
    ),
    "event": Choice(
        "Proposes an event in the user's calendar, which they check and save.",
        {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "minLength": 1, "maxLength": 200},
                "day": DAY,
                "time": TIME,
                "all_day": {"type": "boolean"},
                "end_day": DAY,
                "end_time": TIME,
                "location": {"type": "string", "maxLength": 200},
            },
            "required": ["summary", "day"],
            "additionalProperties": False,
        },
    ),
    "task": Choice(
        "Proposes a task for the user, which they check and add.",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": 500},
                "due": DAY,
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    ),
    "help": Choice(
        "Opens the articles of the suite's help that answer the question.",
        {
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 200}},
            "required": ["text"],
            "additionalProperties": False,
        },
    ),
    "note": Choice(
        "Keeps what was said as a note.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
}


class Ununderstood(Exception):
    """Why the model gave no reading of what was said: a code the dialog names."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def understand(user, text: str, zone: str) -> dict:
    """What the user wants of what they said: a place or a link to open, a search, a person, a
    message, a document, an event, a task, the help's articles or a note, its run kept with what
    it took under the consent they gave to their speech."""
    run = await database(ActionRun.objects.create)(
        user=user,
        action=ACTION,
        target={},
        consent=ActionRun.Consented.USER,
        consented_by=user,
    )
    now = datetime.now(zone_of(zone))
    accounts = await database(list)(
        user.mail_accounts.order_by("pk").values_list("address", "label", "name")
    )
    tools = dict(TOOLS)
    listed = ""
    if accounts:
        mail = {**MAIL, "properties": {**MAIL["properties"]}}
        mail["properties"]["account"] = {"enum": [address for address, _, _ in accounts]}
        tools["mail"] = Choice(TOOLS["mail"].description, mail)
        listed = "\nTheir mail accounts: " + "; ".join(
            ", ".join(filter(None, each)) for each in accounts
        )
    prompt = Prompt(
        INSTRUCTION,
        f"Now is {now:%Y-%m-%d %H:%M}, a {now:%A}.{listed}\n\n{text}",
        tools,
        effort="low",
        steps=3,
    )
    try:
        answer = await runs.decided(run, MODEL, prompt)
    except (model.Failed, Unavailable) as failed:
        raise Ununderstood(failed.code) from None
    intent = answer.pop("op")
    if intent == "person":
        answer["people"] = await database(contacts.spoken)(user, answer["name"])
    elif intent == "link":
        answer["links"] = await database(launcher.spoken)(user, answer["name"])
    elif intent == "help":
        language = library.language_of(None, user)
        answer["articles"] = await database(library.found)(user, answer["text"], language, ARTICLES)
    return {"intent": intent, **answer}
