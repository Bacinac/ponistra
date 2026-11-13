"""What a collection that recognises bills asks the model of each message: whether it is one,
and if so who issued it, when, how much and in what currency, read from the message and the
text of the files it carries."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from apps.ai import installation, model
from apps.ai.model import Choice, Prompt
from apps.mail.models import Attachment, Message
from apps.search.models import BlobText

from .models import Item

ACTION = "mail.gather"
MODEL = "claude-sonnet-5-5"
# What the model reads of a message's own text and of all it is, files with it.
TEXT = 20_000
LONGEST = 200_000
CURRENCY = re.compile(r"^[A-Z]{3}$")
AMOUNT = re.compile(r"^-?\d{1,12}(\.\d{1,2})?$")
READ = """You read one e-mail message for a collection of bills in PONISTRA, an office suite: \
invoices, receipts and other confirmations of a payment owed or made. The user's message is the \
e-mail: who sent it, when, its subject and its text, then the text of each file it carries, page \
by page.

Answer with one call to the bill tool. {asked} Give who issued it (the company as it names \
itself, not a payment service that sent it on their behalf), the date it was issued as \
YYYY-MM-DD, the total paid or to pay as a number with a point before its decimals and without \
the currency, and the currency as its ISO 4217 code. Leave out what the message does not say."""
ASK = "Say whether it is such a bill; if it is not, give nothing else."
CHOSEN = "The user chose it as a bill: say it is one."
BILL = Choice(
    "Gives whether the message is a bill and what it says of it.",
    {
        "type": "object",
        "properties": {
            "bill": {"type": "boolean"},
            "supplier": {"type": "string", "maxLength": 200},
            "date": {"type": "string"},
            "amount": {"type": "string"},
            "currency": {"type": "string"},
        },
        "required": ["bill"],
        "additionalProperties": False,
    },
)


def content(message: Message, files: list[Attachment]) -> str:
    sender = message.sender or {}
    lines = [
        f"From: {sender.get('name', '')} <{sender.get('address', '')}>",
        f"Date: {message.date.isoformat()}",
        f"Subject: {message.subject}",
        "",
        message.text[:TEXT],
    ]
    texts = {
        found.blob_id: found
        for found in BlobText.objects.filter(blob_id__in=[each.blob_id for each in files])
    }
    for each in files:
        found = texts.get(each.blob_id)
        pages = found.pages.order_by("number") if found else []
        read = "\n\n".join(f"[page {page.number}]\n{page.text}" for page in pages if page.text)
        if read:
            lines += ["", f"[file {each.name or each.part}]", read]
    return "\n".join(lines)[:LONGEST]


def prompt(message: Message, files: list[Attachment], chosen: bool) -> Prompt:
    return Prompt(
        READ.format(asked=CHOSEN if chosen else ASK),
        content(message, files),
        {"bill": BILL},
        effort="low",
        steps=2,
    )


def _date(given) -> date | None:
    try:
        return date.fromisoformat(given) if isinstance(given, str) else None
    except ValueError:
        return None


def _amount(given) -> Decimal | None:
    if not isinstance(given, str) or not AMOUNT.match(given.strip()):
        return None
    try:
        return Decimal(given.strip())
    except InvalidOperation:
        return None


def read(item: Item, message: Message, files: list[Attachment], spend) -> dict | None:
    """What the model found of the message, or None where it says it is no bill. A model the
    installation does not let the owner reach raises `installation.Unavailable`, and one that
    fails `model.Failed`."""
    installation.allowed(item.collection.owner_id)
    answers: list[dict] = []
    model.converse(MODEL, prompt(message, files, item.chosen), answers.append, lambda: False, spend)
    if not answers:
        raise model.Failed("no_answer")
    answer = answers[-1]
    if not answer.get("bill") and not item.chosen:
        return None
    currency = str(answer.get("currency", "")).strip().upper()
    return {
        "supplier": str(answer.get("supplier", "")).strip()[:200],
        "date": _date(answer.get("date")),
        "amount": _amount(answer.get("amount")),
        "currency": currency if CURRENCY.match(currency) else "",
    }
