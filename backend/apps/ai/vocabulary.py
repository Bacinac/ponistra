"""The names the user's speech is likely to hold, given to the speech to text so that it writes
them as the user does: the people they write to and the names in their folders and documents."""

import re
from collections import Counter

from django.db.models.expressions import RawSQL

from apps.access import rights
from apps.documents.models import Node
from apps.mail.correspondents import UNANSWERED

TITLES = 300
PEOPLE = 20
# OpenAI reads only the end of a longer prompt.
LONGEST = 800
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
# Longer words in capitals are a title shouted, not an abbreviation.
ABBREVIATION = 5


def named(title: str) -> list[str]:
    """The words of a title that are names: those with a capital inside them (TaskStreamer, MRO)
    and capitalised words after the first, which a title in most languages writes small unless
    they are names. A title written all in capitals names nothing."""
    if not any(letter.islower() for letter in title):
        return []
    found = []
    for place, word in enumerate(WORD.findall(title)):
        if len(word) < 2 or (word.isupper() and len(word) > ABBREVIATION):
            continue
        inner = any(letter.isupper() for letter in word[1:])
        if inner or (place and word[0].isupper()):
            found.append(word)
    return found


def words(user) -> list[str]:
    readable, params = rights.readable(user)
    titles = (
        Node.objects.filter(pk__in=RawSQL(readable, params))
        .exclude(kind=Node.Kind.FILE)
        .order_by("-updated_at")
        .values_list("title", flat=True)[:TITLES]
    )
    people = (
        user.mail_correspondents.filter(written__gt=0)
        .exclude(name="")
        .exclude(address__regex=UNANSWERED)
        .order_by("-written", "-last")
        .values_list("name", flat=True)[:PEOPLE]
    )
    counted = Counter(
        word for title in dict.fromkeys(titles) for word in dict.fromkeys(named(title))
    )
    named_words = sorted(counted, key=counted.get, reverse=True)
    found, known = [], set()
    for word in [name for name in people if "@" not in name] + named_words:
        if word.casefold() not in known:
            known.add(word.casefold())
            found.append(word)
    return found


def prompt(user) -> str:
    """The words as a sentence the model reads before the speech, or nothing."""
    listed = ""
    for word in words(user):
        longer = f"{listed}, {word}" if listed else word
        if len(longer) > LONGEST:
            break
        listed = longer
    return f"Names and words the user uses: {listed}." if listed else ""
