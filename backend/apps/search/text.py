import re

from django.contrib.postgres.search import SearchVectorField
from django.db.models import Func, TextField

CONFIG = "hr"
TYPING = re.compile(r"(?:^|\s)(\w+)$")
OPERATORS = re.compile(r'"|(?:^|\s)-|(?:^|\s)or(?:\s|$)', re.IGNORECASE)
# pg_trgm's default of 0.6 misses one typo in a short word: "ugvor" scores 0.44
# against "ugovor".
LIKENESS = 0.4
HEADLINE = "StartSel=, StopSel=, MaxWords=30, MinWords=15, ShortWord=2, MaxFragments=1"
# Postgres never ends a fragment on a number, so the snippet of "Ukupno 1250" would end at
# "Ukupno": a word after the text lets the fragment reach the number, and is cut away again.
TAIL = "ponistratail"
WHOLE = "StartSel=, StopSel=, HighlightAll=true"


class Words(Func):
    """The text's lexemes under the hr configuration: accents folded, then stemmed."""

    arity = 1
    template = f"to_tsvector('{CONFIG}'::regconfig, %(expressions)s)"
    output_field = SearchVectorField()


class Folded(Func):
    """The text in lower case without accents, for trigram matching."""

    arity = 1
    function = "search_fold"
    output_field = TextField()


class MailWords(Func):
    """A message's lexemes under the hr configuration: its subject weighed above its people,
    and both above its text."""

    arity = 5
    function = "mail_words"
    output_field = SearchVectorField()


class TranslationWords(Func):
    """A message's translation's lexemes under the hr configuration: its subject weighed above
    its text, as the message's own are."""

    arity = 2
    function = "mail_translation_words"
    output_field = SearchVectorField()


class EventWords(Func):
    """An event's lexemes under the hr configuration: its summary weighed above its place and
    people, and both above its description."""

    arity = 5
    function = "calendar_words"
    output_field = SearchVectorField()


class TaskWords(Func):
    """A task's lexemes under the hr configuration: its text weighed above where it came from."""

    arity = 2
    function = "tasks_words"
    output_field = SearchVectorField()


PEOPLE = "strpos(search_fold(concat_ws(' ', {name}, {address})), search_fold(%s)) > 0"
UNDER = """{column} IN (
    WITH RECURSIVE under AS (
        {first}
        UNION
        SELECT child.id FROM {table} child JOIN under ON child.parent_id = under.id
    )
    SELECT id FROM under
)"""
NAMED = "strpos(search_fold({name}), search_fold(%s)) > 0"
INSIDE = (
    "SELECT child.id FROM documents_node child"
    " JOIN documents_node folder ON folder.id = child.parent_id"
    f" WHERE folder.kind = 'folder' AND {NAMED.format(name='folder.title')}"
)


def matching(text: str) -> tuple[str, list[str]]:
    """The tsquery for web-search syntax; the last word, likely still being typed,
    also matches as a prefix."""
    typing = TYPING.search(text)
    head = text[: typing.start(1)] if typing else text
    words = head.split()
    if typing is None or head.count('"') % 2 or (words and words[-1].lower() == "or"):
        return f"websearch_to_tsquery('{CONFIG}', %s)", [text]
    return (
        f"websearch_to_tsquery('{CONFIG}', %s) && to_tsquery('{CONFIG}', %s)",
        [head, f"'{typing[1]}':*"],
    )


def period_of(column: str, wanted, params: list) -> list[str]:
    """The conditions a period filter puts on the column, their values appended to params."""
    conditions = []
    if wanted.period.start:
        conditions.append(f"{column} >= %s")
        params.append(wanted.period.start)
    if wanted.period.end:
        conditions.append(f"{column} < %s")
        params.append(wanted.period.end)
    return conditions
