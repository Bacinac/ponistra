"""The agent beside a document (A6-3, A6-4): a conversation over a tab in turns, each a run of
its own the user takes back, and the analysis of a table into a new tab. A long table is read
as code profiles it and by stretches of rows, never whole, and every number the model states
stands in a cell as a formula our engine computes."""

import json
import re
from collections import Counter

from pycrdt import Doc

from apps.ai.model import Choice, Prompt, Reading
from apps.ai.reading import whole_of
from apps.collab import server
from apps.content import blocks, styles
from apps.content.blocks import Block
from apps.content.models import Grid
from apps.content.operations import OPERATIONS, OWN_OPERATIONS, Copy, write
from apps.content.sheets import Places, Refused, Sheets
from apps.documents.models import Tab

from . import profiles
from .language import NODES
from .models import ActionRun
from .tables import table_in

# The rows of a table the model reads with the tab; the rest it reads through its tools.
ROWS = 100
# The earlier turns of a conversation the model reads.
TURNS = 20
TABLES = """A table shown only in part says so: read its other rows with the read tool and the \
whole of it, column by column, with the profile tool, which gives the address a formula reads \
each column's data by. Never read a long table row by row to work something out from it: \
write formulas over those addresses, and read what they compute with the read tool before \
writing about it.

A chart is a block placed after the table it shows: {"type": "chart", "attrs": {"range": \
{"table": id, "from": {"row": id, "col": id}, "to": {"row": id, "col": id}}, "kind": \
"column" | "bar" | "line" | "area" | "pie" | "doughnut" | "scatter", "by": "cols" | "rows", \
"title": "..."}}, its range the cells of its names and values, its series running down the \
columns ("cols") or along the rows.

A formula is written as xlsx stores it, whatever the document's language: English function \
names, a comma between arguments, a point before decimals, another table's cells after its \
name, as 'Sales 2025'!B2:B500. Besides the common functions there are CORREL, PEARSON, RSQ, \
SLOPE and INTERCEPT, MEDIAN, MODE.SNGL, STDEV.S, VAR.S, PERCENTILE.INC, QUARTILE.INC, \
COUNTIFS, SUMIFS, AVERAGEIFS, MINIFS and MAXIFS."""
ASK = """You carry out a user's request on a tab of a document in PONISTRA, an office suite, \
talking with them in turns beside it. The user's message is the turns before this one, if \
any, the tab, the blocks they chose if they chose any, and their request.

Each earlier turn says what was asked, the operations called, what was said to the user and \
whether the user took it back. A request often builds on them ("now as a pie", "leave out \
2023", "shorter"): change what an earlier turn made rather than making it again.

The tab has each block on a line of its own after its id in brackets, its type and its \
attributes as JSON, then its text: <1>…</1> around a formatted part, <2/> a footnote or a \
field, <br/> a line break, and the line after it saying what each tag holds and which \
proposals the text carries. A footnote follows its block. A table lists its rows and columns, \
each id with the number or letter a formula addresses it by, then its cells, each after the \
table's id, its row's and its column's, a formula with what it computes. The document's styles \
come last.

Carry out the request with the tools, which are the document's operations, addressing blocks, \
rows, columns and proposals by their ids and a part of a text by the words it holds. Where the \
user chose blocks, the request concerns them unless it says otherwise. Make many calls at \
once where they do not depend on each other. Text you write goes into the document as \
proposals the user accepts or rejects; formatting, structure and tables apply at once, and the \
user can undo the whole turn. Never compute a number yourself: write a formula and the table \
computes it. Write in the document's language ({locale}) unless asked otherwise, its numbers \
and dates as that language types them. A block of another type or with other attributes is \
written as the tab shows such blocks.

Where the request can be read in ways that lead to different results, do not guess: call the \
offer tool with a short question and two to four answers, each one the user can choose as it \
stands, and do nothing else in that turn.

{tables}

When you are done, end your turn without text. Write to the user only of an assumption you \
made or a part of the request left undone. Where the request cannot be carried out with these \
tools, or asks a question rather than a change, change nothing and only answer it. Write one or \
two sentences, not of what was done, in the language the request is written in, impersonally: \
never of yourself.

"""
ANALYSE = """You analyse a table of a document in PONISTRA, an office suite, in a new tab of \
its own. The user's message is the table as code profiled it: each column's header, the kinds \
of value it holds and how many of each, the distinct values and the commonest, the least and \
the greatest number and the address a formula reads its data by, then a sample of its rows.

Write into the new tab, which is empty: a heading, then for what the data shows a table of \
formulas over the source's addresses (counts, sums, averages, spread, shares by category, \
the correlation of numeric columns that may move together) with a name in its first column, \
a chart where one shows it better than numbers, and a short text of what they say. Every \
number the text states stands in a cell as a formula: read what the formulas compute with the \
read tool before writing the text, and never compute or estimate a number yourself. Choose \
what to compute from the profile; skip what the data cannot answer.

{tables}

Write in the document's language ({locale}), its numbers and dates as that language types \
them. When you are done, end your turn without text.

"""
OFFER = Choice(
    "Asks the user to choose how the request is meant before anything is changed.",
    {
        "type": "object",
        "properties": {
            "question": {"type": "string", "minLength": 1, "maxLength": 300},
            "options": {
                "type": "array",
                "minItems": 2,
                "maxItems": 4,
                "items": {"type": "string", "minLength": 1, "maxLength": 200},
            },
        },
        "required": ["question", "options"],
        "additionalProperties": False,
    },
)
TABLE = {"type": "string", "minLength": 1, "maxLength": 100}


def readings(tab: Tab) -> dict[str, Reading]:
    """The tools through which the model reads the document's long tables: a table of the tab
    profiled, and the rows of any of the document's tables."""
    return {
        "profile": Reading(
            "Profiles a table of the tab whole: each column's header, kinds of value, distinct "
            "values, least and greatest number and the address its data is read by, and a "
            "sample of its rows.",
            {
                "type": "object",
                "properties": {"table": TABLE},
                "required": ["table"],
                "additionalProperties": False,
            },
            lambda asked: profiles.profile(tab, asked["table"]),
        ),
        "read": Reading(
            f"Reads at most {profiles.STRETCH} rows of a table from the one numbered first, "
            "each cell as it shows, a formula's as it computes.",
            {
                "type": "object",
                "properties": {
                    "table": TABLE,
                    "first": {"type": "integer", "minimum": 1},
                    "count": {"type": "integer", "minimum": 1, "maximum": profiles.STRETCH},
                },
                "required": ["table", "first", "count"],
                "additionalProperties": False,
            },
            lambda asked: profiles.stretch(tab, asked["table"], asked["first"], asked["count"]),
        ),
    }


def _calls(names: list[str]) -> str:
    return ", ".join(
        name if times == 1 else f"{name} ×{times}" for name, times in Counter(names).items()
    )


def turns_of(tab: Tab, user, thread: str | None) -> list[str]:
    """The earlier turns of the conversation, as the model reads them."""
    if thread is None:
        return []
    found = ActionRun.objects.filter(
        document=tab.document_id, user=user, action="text.ask", parameters__thread=thread
    ).order_by("-started_at")[:TURNS]
    lines = []
    for run in reversed(found):
        lines.append("turn: " + run.parameters["request"])
        if run.calls:
            lines.append("    called: " + _calls(run.calls))
        if run.reply:
            lines.append("    said: " + run.reply)
        if run.offers:
            lines.append("    offered: " + " | ".join(run.offers))
        if run.state != ActionRun.State.DONE:
            lines.append(f"    {run.state}")
    return [*lines, ""] if lines else []


def _read(tab: Tab) -> tuple[list[Block], dict[str, dict[str, str]], dict[str, int]]:
    def reading(doc: Doc, held: Sheets):
        found = blocks.read(doc, held.grids(cut=True))
        places = Places(held)
        formulas, sizes = {}, {}
        for block in found:
            if block.type != "table" or block.grid is None:
                continue
            shown = set(block.grid.rows[:ROWS])
            formulas[block.id] = {
                key: places.text(pieces, block.id, row, col)
                for key, pieces in block.grid.formulas.items()
                for row, col in [key.split(":")]
                if row in shown
            }
            if (laid := held.peek(block.id)) is not None:
                sizes[block.id] = laid.size
        return found, formulas, sizes

    return server.read_grids(tab.room, reading, settled=True)


def ask(tab: Tab, target: dict, parameters: dict, user) -> Prompt:
    """The user's request carried out on the tab by the model with every operation, as a turn of
    a conversation whose earlier turns it reads, the blocks chosen named; what it says at the
    end, or the answers it offers to choose from, kept for the user."""
    found, formulas, sizes = _read(tab)
    chosen = target.get("blocks") or []
    if missing := set(chosen) - {block.id for block in found}:
        raise Refused("not_found", ", ".join(sorted(missing)))
    theme, looks = server.read(tab.document.room, styles.read)
    lines = whole_of(found, formulas, theme, looks, ROWS, sizes)
    asked = [
        *(["chosen: " + ", ".join(chosen)] if chosen else []),
        "request: " + parameters["request"],
    ]
    return Prompt(
        ASK.format(locale=tab.document.locale, tables=TABLES) + NODES,
        "\n".join([*turns_of(tab, user, parameters.get("thread")), *lines, "", *asked]),
        {
            **{name: {} for name in (*OPERATIONS, *OWN_OPERATIONS)},
            **readings(tab),
            "offer": OFFER,
        },
        effort="high",
        replies=True,
    )


def _named(tab: Tab, laid) -> str | None:
    """A name for the table formulas read it by, where it has none: the tab's title, numbered
    apart from the document's other tables."""
    if laid.name:
        return None
    title = tab.title or tab.document.title
    base = re.sub(r"[\\\[\]:*?/]", " ", title).strip(" '")[:27].strip(" '") or "Data"
    taken = {
        name.casefold()
        for name in Grid.objects.filter(document=tab.document_id).values_list("name", flat=True)
    }
    name, at = base, 1
    while name.casefold() in taken:
        at += 1
        name = f"{base} {at}"
    return name


def analyse(tab: Tab, target: dict, parameters: dict) -> Prompt:
    """The table analysed by the model into a new tab beside the tab: tables of formulas over
    its data, charts and text, from the profile code makes of it. A table without a name is
    given one first, which formulas read it by."""
    table = target["table"]
    laid = server.read_grids(tab.room, lambda doc, held: table_in(doc, held, table)[0])
    name = _named(tab, laid)
    profiled = profiles.profile(tab, table, name)
    room = Tab._meta.get_field("title").max_length - len(parameters["title"]) - 3
    doc = Doc()
    doc.apply_update(write(doc, Sheets({}), []).update)
    opens = Copy(
        tab,
        " – ".join(filter(None, [parameters["title"], tab.title[:room]])),
        doc.get_update(),
        [],
        [],
    )
    return Prompt(
        ANALYSE.format(locale=tab.document.locale, tables=TABLES) + NODES,
        json.dumps(profiled, ensure_ascii=False, indent=1),
        {**{name: {} for name in OPERATIONS}, **readings(tab)},
        effort="high",
        opens=opens,
        before=[{"op": "grid", "table": table, "name": name}] if name else None,
    )
