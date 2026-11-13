"""The actions a model carries out on a tab's text (A4), each planned as what the model is
asked, what it reads and the operations it may call."""

from django.utils import timezone
from django.utils.translation import get_language_info

from apps.ai.model import STEPS, Among, Prompt
from apps.ai.reading import changes_of, tagged_of, text_of
from apps.collab import server
from apps.content import blocks
from apps.content.blocks import UNLOOKED_MARKS, Block, Run
from apps.content.operations import TEXTBLOCKS, copy_of
from apps.content.sheets import Refused
from apps.documents.models import Tab
from apps.versions import history
from apps.versions.models import Version

LEADING = {"title", "subtitle"}
NODES = """Each block is a ProseMirror JSON node:
- a paragraph: {"type": "paragraph", "content": [{"type": "text", "text": "..."}]}
- a bulleted item: {"type": "paragraph", "attrs": {"list": "bullet"}, "content": [...]}
- a numbered item: {"type": "paragraph", "attrs": {"list": "number"}, "content": [...]}
- bold or italic text: {"type": "text", "text": "...", "marks": [{"type": "strong"}]}, \
"em" for italic"""
SUMMARY = f"""You summarise part of a document in PONISTRA, an office suite. The user's \
message is that part: each block on a line of its own after its id in brackets and its kind, \
a table's rows after it.

Write the summary with one call to the insert tool. It goes into the document as a proposal \
the user accepts or rejects, so write only the summary: no heading, preface or remark about \
the text or the task. Keep to what the text says, in the language it is written in, in a few \
short paragraphs or a bulleted list, whichever fits it better, at most a fifth of its length.

{NODES}"""
WAYS = {
    "formal": "in a more formal register, as for official correspondence or a contract",
    "simple": "in plain words and short sentences that anyone understands at first reading",
    "short": "shorter, saying the same in fewer words, without repetition or filler",
    "correct": "with its spelling, grammar and punctuation corrected and nothing else changed: "
    "the same words, order and style wherever they are right",
}
REWRITE = """You rewrite part of a document in PONISTRA, an office suite. The user's message is \
that part: each block on a line of its own after its id in brackets and its kind.

Rewrite it {way}. Call the rewrite tool once for each block whose text changes, with the \
block's whole new text; leave a block that needs no change alone. Each block stays one block \
of its kind, its text on one line, in the language it is written in. Keep every fact, name, \
number and date as it is. Write plain text: the editor keeps the formatting of the words that \
stay, and what you write goes into the document as proposals the user accepts or rejects, so \
write only the text, with no remark about it or the task."""


EXTRACT = """You pull the data of part of a document in PONISTRA, an office suite, into a \
table. The user's message is that part: each block on a line of its own after its id in \
brackets and its kind, a table's rows after it.

Make the table with one call to the table tool. Choose its shape from the text: where it \
describes one thing, such as a contract with its parties, dates, amounts and terms, a row for \
each datum with its name and its value; where it lists several things of one kind, such as \
items, payments or deadlines, a row for each with a column for each property they share. The \
first row is the header. Take only what the text says, in the language it is written in, and \
leave a cell empty where it says nothing. Write numbers, amounts and dates as the document's \
language ({locale}) types them, so the table computes with them; a currency or a unit goes \
into the header where a whole column holds such values. The table goes into the document as \
a proposal the user accepts or rejects, so write only the table."""
TRANSLATE = """You translate a tab of a document in PONISTRA, an office suite, into {language}. \
The user's message is the tab, already copied into a new tab beside it whose words you write: \
each block on a line of its own after its id in brackets and its kind, a footnote after the \
block it belongs to, and a table's cells after the table, each after the table's id, its row's \
and its column's.

Translate every line:
- a block or a footnote with the replace tool: its whole text in {language} on one line, with \
the tags it has. Put <1>…</1> around the words that translate the words so tagged, so they keep \
their formatting, each <2/>, a footnote or a field, once where it belongs, in the order given, \
and <br/> where the line breaks.
- a table's cells with the cells tool, a call for each table, each cell's value its text in \
{language}.
- a chart's title or an image's description with the set tool, as its attribute title or alt.

Leave numbers, amounts, dates, codes, and the names of people, companies and places as they \
are, and a cell that holds only such a value alone. Translate faithfully, in the register of \
the original and in the terms a professional translator would choose for such a text. Make many \
calls at once, at most fifty in a turn. The translation goes into the new tab as it is, so \
write only the translation, with no remark about it or the task."""

COMPARE = """You describe what changed in a tab of a document in PONISTRA, an office suite, \
since its {version}. The user's message is what changed, as code found it: each change on a \
line of its own after the id of what changed in brackets, what it is, how it changed (added, \
removed, moved or changed) and its text. In a changed text [-…-] holds the words taken out and \
{{+…+}} those written in; a table's rows show their cells between bars.

Write the description with one call to the insert tool. It goes into the document as a proposal \
the user accepts or rejects, so write only the description: one short paragraph that names the \
version, then a bulleted list of the changes a reader would want to know, the most important \
first, each saying what changed and, where something was replaced, from what to what. Join the \
small changes of one kind into one item and leave out those of spacing or punctuation alone. \
Write in the language the tab is written in, and say nothing of the ids or the marks around the \
words.

"""


def _chosen(tab: Tab, target: dict) -> list[Block]:
    found = server.read_grids(tab.room, lambda doc, held: blocks.read(doc, held.grids()))
    if not (ids := target.get("blocks")):
        return found
    chosen = [block for block in found if block.id in ids]
    if missing := set(ids) - {block.id for block in chosen}:
        raise Refused("not_found", ", ".join(sorted(missing)))
    return chosen


def summarise(tab: Tab, target: dict, parameters: dict) -> Prompt:
    """A summary of the blocks chosen, after the last of them, or of the whole tab, at its
    start after its title."""
    content, at = _read(tab, target)
    return Prompt(SUMMARY, content, {"insert": {"at": at}})


def extract(tab: Tab, target: dict, parameters: dict) -> Prompt:
    """A table of the data of the blocks chosen, or of the whole tab, where a summary goes."""
    content, at = _read(tab, target)
    instruction = EXTRACT.format(locale=tab.document.locale)
    return Prompt(instruction, content, {"table": {"at": at}})


def _read(tab: Tab, target: dict) -> tuple[str, dict]:
    """What the model reads of the blocks chosen, and where what it writes goes: after the last
    of them or, of the whole tab, after its title."""
    chosen = _chosen(tab, target)
    content = text_of(chosen)
    if not content:
        raise Refused("empty")
    if target.get("blocks"):
        return content, {"after": chosen[-1].id}
    return content, _titled(chosen)


def compare(tab: Tab, target: dict, parameters: dict) -> Prompt:
    """What the tab changed since the version chosen, as code finds it, described where a
    summary of the whole tab goes."""
    version = Version.objects.filter(pk=parameters["version"], document=tab.document_id).first()
    if version is None:
        raise Refused("not_found", parameters["version"])
    current = _chosen(tab, {})
    if not (found := changes_of(history.blocks_of(version, tab), current)):
        raise Refused("same", str(version.pk))
    saved = timezone.localtime(version.created_at).strftime("%Y-%m-%d %H:%M")
    named = f'"{version.title}"' if version.title else ""
    shown = " ".join(filter(None, ["version", str(version.number), named, f"of {saved}"]))
    return Prompt(
        COMPARE.format(version=shown) + NODES,
        "\n".join(found),
        {"insert": {"at": _titled(current)}},
    )


def rewrite(tab: Tab, target: dict, parameters: dict) -> Prompt:
    """The text of the blocks chosen, or of the whole tab, rewritten the way chosen, each block
    word by word in its place."""
    chosen = [
        block for block in _chosen(tab, target) if block.type in TEXTBLOCKS and block.text.strip()
    ]
    if not chosen:
        raise Refused("empty")
    if proposed := [block.id for block in chosen if _proposed(block)]:
        raise Refused("proposed", ", ".join(proposed))
    return Prompt(
        REWRITE.format(way=WAYS[parameters["way"]]),
        text_of(chosen),
        {"rewrite": {"block": Among(tuple(block.id for block in chosen))}},
        effort="low" if parameters["way"] == "correct" else "medium",
    )


def _proposed(block: Block) -> bool:
    return (
        any(block.attrs.get(name) for name in (*UNLOOKED_MARKS, "proposedRows"))
        or any(
            name in (run.marks if isinstance(run, Run) else run.proposed)
            for run in [*block.runs, *(run for note in block.notes for run in note.runs)]
            for name in UNLOOKED_MARKS
        )
        or any(_proposed(each) for cell in block.cells for each in cell.blocks)
    )


AMERICAN = {"name": "American English", "name_local": "American English"}


def named(language: str) -> tuple[str, str]:
    """The document language's English name, which the model is told, and its own name as a
    title carries it."""
    info = AMERICAN if language == "en" else get_language_info(language.lower())
    return info["name"], info["name_local"][:1].upper() + info["name_local"][1:]


def translate(tab: Tab, target: dict, parameters: dict) -> Prompt:
    """The tab copied into a new tab beside it, named after it in the language chosen, whose
    text, cells of text, charts' titles and images' descriptions the model writes in that
    language."""
    english, name = named(parameters["language"])
    room = Tab._meta.get_field("title").max_length - len(name) - 3
    copy = copy_of(tab, " – ".join(filter(None, [tab.title[:room], name])))
    if proposed := [block.id for block in copy.blocks if _proposed(block)]:
        raise Refused("proposed", ", ".join(proposed))
    reading = tagged_of(copy.blocks)
    tools = {
        tool: {field: Among(tuple(ids))}
        for tool, field, ids in [
            ("replace", "block", reading.texts),
            ("cells", "table", reading.tables),
            ("set", "block", reading.described),
        ]
        if ids
    }
    if not tools:
        raise Refused("empty")
    return Prompt(
        TRANSLATE.format(language=english),
        "\n".join(reading.lines),
        tools,
        steps=STEPS + len(reading.lines) // 25,
        opens=copy,
    )


def _titled(found: list[Block]) -> dict:
    """After the tab's title and subtitle, or at its start without them."""
    last = None
    for block in found:
        if block.type not in LEADING:
            break
        last = block
    return {"after": last.id} if last else {"start": "body"}
