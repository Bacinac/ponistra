"""A PDF file translated into a new document beside it (D35-3): each page of its text, as the
file holds it or OCR read it, an item of the run, which the model writes block by block in the
language chosen; a paragraph a page break cut in two is joined again."""

from apps.ai.model import Choice, Prompt
from apps.content.operations import Refused
from apps.documents.models import Node, Tab
from apps.search.models import BlobPage

from .gathering import readable
from .language import named

ACTION = "file.translate"
# How much of the page before the model reads, to go on with a sentence a page break cut.
TAIL = 300
KINDS = {
    "heading1": ("heading", {"level": 1}),
    "heading2": ("heading", {"level": 2}),
    "heading3": ("heading", {"level": 3}),
    "paragraph": ("paragraph", {}),
    "bullet": ("paragraph", {"list": "bullet"}),
    "number": ("paragraph", {"list": "number"}),
}
JOINED = {"paragraph", "bullet", "number"}

INSTRUCTION = """You translate one page of a PDF file into {language}, for a document in \
PONISTRA, an office suite, that holds the whole file's translation page after page. The user's \
message is the page's text as the file lays it out, from its text or read by OCR: its lines \
may break inside a sentence, and a table's cells may run together.{before}

Give the page with one call to the page tool: its text in {language}, block by block in the \
page's order, each a heading by its level, a paragraph, an item of a bulleted or a numbered \
list, or a table by its rows of cells. Join the lines of one paragraph into one block, and \
leave out what only lays the page out: its running header and footer and its page number. Set \
continues where the page's first block goes on with the paragraph or item the page before it \
ended in. Leave numbers, amounts, dates, codes, addresses and the names of people, companies, \
products and places as they are. Translate faithfully, in the register of the original and in \
the terms a professional translator would choose, and write only the translation."""
BEFORE = """ The page before it ended with: "{tail}\""""
PAGE = Choice(
    "Gives the page in the language asked for, block by block in its order.",
    {
        "type": "object",
        "properties": {
            "continues": {"type": "boolean"},
            "blocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"enum": [*KINDS, "table"]},
                        "text": {"type": "string"},
                        "rows": {
                            "type": "array",
                            "items": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "required": ["kind"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["continues", "blocks"],
        "additionalProperties": False,
    },
)


def title_of(node: Node, language: str) -> str:
    """The new document's title: the file's, then the language's own name."""
    name = named(language)[1]
    room = Tab._meta.get_field("title").max_length - len(name) - 3
    return f"{node.title[:room]} – {name}"


def pages(node: Node) -> list[int]:
    """The numbers of the file's pages that hold text."""
    if not node.is_pdf:
        raise Refused("not_a_pdf")
    return list(
        BlobPage.objects.filter(source_id=node.blob_id)
        .exclude(text__regex=r"^\s*$")
        .order_by("number")
        .values_list("number", flat=True)
    )


def page_in(node: Node, number: int, user) -> tuple[str, str]:
    """The page's text while the user may still read the file, and how the page before it
    ends."""
    readable(node, user)
    found = BlobPage.objects.filter(source_id=node.blob_id, number__lte=number).order_by("-number")
    texts = list(found.values_list("number", "text")[:2])
    if not texts or texts[0][0] != number:
        raise Refused("empty")
    before = texts[1][1].strip()[-TAIL:] if len(texts) > 1 else ""
    return texts[0][1], before


def plan(text: str, before: str, language: str) -> Prompt:
    """What the model is asked of one page."""
    told = BEFORE.format(tail=" ".join(before.split())) if before else ""
    return Prompt(
        INSTRUCTION.format(language=named(language)[0], before=told),
        text,
        {"page": PAGE},
        effort="low",
        steps=3,
    )


def _node(kind: str, text: str) -> dict:
    name, attrs = KINDS[kind]
    return {"type": name, "attrs": attrs, "content": [{"type": "text", "text": text}]}


def written(found: list[dict]) -> list[dict]:
    """The operations that write the pages into the document, in order, a block a page break
    cut in two joined again."""
    blocks: list[dict] = []
    for page in found:
        given = [
            {**block, "text": " ".join(block.get("text", "").split())} for block in page["blocks"]
        ]
        first = given[0] if given else None
        if (
            page["continues"]
            and first
            and blocks
            and first["kind"] == "paragraph"
            and blocks[-1]["kind"] in JOINED
        ):
            blocks[-1]["text"] = f"{blocks[-1]['text']} {first['text']}".strip()
            given = given[1:]
        blocks += given
    operations: list[dict] = []
    text: list[dict] = []
    for block in blocks:
        if block["kind"] != "table":
            if block["text"]:
                text.append(_node(block["kind"], block["text"]))
            continue
        rows = [row for row in block.get("rows", []) if any(cell.strip() for cell in row)]
        if not rows:
            continue
        if text:
            operations.append({"op": "insert", "at": {"end": "body"}, "blocks": text})
            text = []
        width = max(len(row) for row in rows)
        rows = [[cell or None for cell in row] + [None] * (width - len(row)) for row in rows]
        operations.append({"op": "table", "at": {"end": "body"}, "rows": rows})
    if text:
        operations.append({"op": "insert", "at": {"end": "body"}, "blocks": text})
    return operations
