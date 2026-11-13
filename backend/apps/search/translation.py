from django.utils import timezone

from apps.actions import runs
from apps.actions.models import ActionRun
from apps.ai import model
from apps.ai.installation import Unavailable
from apps.ai.model import Choice, Prompt
from apps.core.asyncdb import database

ACTION = "search.translate"
MODEL = "claude-haiku-5-5"
DAY = r"^\d{4}-\d{2}-\d{2}$"
INSTRUCTION = """\
You turn a sentence typed into the search box of an office suite into the words the search \
looks for and the filters it narrows them with. The search goes through the user's documents, \
files, links and folders, their mail, their calendar's events, their tasks, the people they \
know and, when asked for them, the earlier versions of their documents. Answer with one call to \
the filters tool.

- text: the words the wanted documents, messages, events, tasks or people's names contain, in \
the language and the form the sentence gives them. Leave out the words that only say what a \
filter says (who, when, which kind, a folder, an attachment) and those with no meaning of their \
own, such as "find", "all" or "please". Empty where the filters alone say what is wanted.
- kind: only where the sentence asks for one kind: document (written in the suite), file \
(uploaded into it, such as a PDF, an image or a spreadsheet from elsewhere), link (a web \
page kept as a bookmark), folder, mail, \
event (a meeting or an appointment in the calendar), task, person (a contact or colleague), or \
version (what a document said earlier: its history, a former or deleted wording).
- from: who a message came from, who made a document or who organised or is invited to an \
event, by the name or the address the sentence gives, in its base form: "od Ane Kovač" is \
"Ana Kovač", "from Mark's" is "Mark".
- account: the mailbox the sentence names, by a word of its address or its name, such as \
"gmail" or "posao".
- folder: a folder by its name, or for a mailbox's own folders one of inbox, drafts, sent, \
archive, junk and trash.
- since and until: the first and the last day of the period the sentence names, both \
included, worked out from today; for an event the period is when it takes place, for a task \
when it is due. Leave one out where the period is open at that end: "since \
March" has no until. On 2026-10-24 "last month" is 2026-09-01 to 2026-09-30, "this year" is \
since 2026-01-01 and "last week" is 2026-10-12 to 2026-10-18, a week running from Monday.
- changed: true only where the period is when a document was last changed rather than when \
it was made or a message came.
- attachment: true only where the sentence asks for mail with an attachment.

Leave out each filter the sentence does not ask for."""
FILTERS = Choice(
    "Gives the words the search looks for and the filters the sentence asks for.",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "kind": {
                "enum": [
                    "document",
                    "file",
                    "link",
                    "folder",
                    "mail",
                    "event",
                    "task",
                    "person",
                    "vault",
                    "version",
                ]
            },
            "from": {"type": "string", "minLength": 1},
            "account": {"type": "string", "minLength": 1},
            "folder": {"type": "string", "minLength": 1},
            "since": {"type": "string", "pattern": DAY},
            "until": {"type": "string", "pattern": DAY},
            "changed": {"type": "boolean"},
            "attachment": {"type": "boolean"},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
)


class Untranslated(Exception):
    """Why the model gave no filters for the sentence: a code the search box names."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def translate(user, sentence: str, consent: ActionRun.Consented) -> dict:
    """The words and filters the model reads in the sentence, its run kept with what it took
    and who let the sentence out to it, the user this once or for all their searches."""
    run = await database(ActionRun.objects.create)(
        user=user, action=ACTION, target={}, consent=consent, consented_by=user
    )
    today = timezone.localdate()
    prompt = Prompt(
        INSTRUCTION,
        f"Today is {today.isoformat()}, a {today.strftime('%A')}.\n\n{sentence}",
        {"filters": FILTERS},
        effort="low",
        steps=3,
    )
    try:
        answer = await runs.decided(run, MODEL, prompt)
    except (model.Failed, Unavailable) as failed:
        raise Untranslated(failed.code) from None
    return {key: value for key, value in answer.items() if key != "op"}
