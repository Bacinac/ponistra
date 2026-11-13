"""A message in a language its owner does not read, written in theirs (D35): code knows its
language on the server and cuts what PONISTRA shows of it into blocks, the model writes each
block, and code puts them back, so its layout, images and links stay."""

import hashlib
import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from django.db import IntegrityError

from apps.actions import runs
from apps.actions.models import ActionRun
from apps.ai import model
from apps.ai.detection import LETTER, language_in, name_of
from apps.ai.installation import Unavailable
from apps.ai.model import Choice, Prompt
from apps.core.asyncdb import database

from . import sending
from .models import Message, Translation

ACTION = "mail.translate"
REPLY = "mail.translateReply"
MODEL = "claude-sonnet-5-5"
LONGEST = 60_000
CONTEXT = 4000
QUOTED = re.compile(r"^\s*>", re.M)
# What HTML lays out as one space outside <pre>, which keeps each line as it is.
SPACE = re.compile(r"[ \t\r\n\f]+")

BLOCK_TAGS = {
    *("address", "article", "aside", "blockquote", "body", "caption", "center", "dd", "div"),
    *("dl", "dt", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6"),
    *("header", "hr", "html", "li", "main", "nav", "ol", "p", "pre", "section", "table"),
    *("tbody", "td", "tfoot", "th", "thead", "title", "tr", "ul"),
}
VOID_TAGS = {"area", "br", "col", "embed", "hr", "img", "input", "source", "track", "wbr"}
MARK = re.compile(r"<(/?)(\d+)(/?)>|<br/>")
PARAGRAPHS = re.compile(r"(\n[^\S\n]*\n\s*)")
BREAK = re.compile(r"[^\S\n]*\n[^\S\n]*")

# How a block keeps its tags and what stays as it is, in either direction.
KEEPING = """Keep the tags a block has: put <1>…</1> around the words that translate the words so \
tagged, so they keep their link or formatting, each <2/>, an image, once where it belongs, and \
<br/> where the line breaks. A block already in {language}, or with nothing to translate, comes \
back as it is. Leave numbers, amounts, dates, codes, addresses and the names of people, \
companies, products and places as they are."""
INSTRUCTION = f"""You translate an e-mail into {{language}} for the person who received it, in \
PONISTRA, an office suite. The user's message is the e-mail: its subject on the first line after \
[subject], then each block of its text on a line of its own after the block's id in brackets.

Answer with one call to the translation tool: the subject and every block in {{language}}, each \
block by its id. {KEEPING} Translate faithfully, in the register of the original and in the terms \
a professional translator would choose for such a message, and write only the translation, with \
no remark about it."""
REPLY_INSTRUCTION = f"""You translate into {{language}} the reply a PONISTRA user wrote to an \
e-mail in {{language}}, a language they do not write, so it goes in the language of the e-mail \
it answers. The user's message gives that e-mail after [answered], to be read and not \
translated, then the reply: its subject on the line after [subject], then each block of its text \
on a line of its own after the block's id in brackets.

Answer with one call to the translation tool: the subject and every block of the reply in \
{{language}}, each block by its id. {KEEPING} Address the people as the e-mail answered addresses \
them, formally or familiarly, call things by its terms, and write as a professional writes such a \
reply in {{language}}, with no remark about the translation."""

TRANSLATION = Choice(
    "Gives the subject and every block of the e-mail in the language asked for.",
    {
        "type": "object",
        "properties": {
            "subject": {"type": "string"},
            "blocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                    "required": ["id", "text"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["subject", "blocks"],
        "additionalProperties": False,
    },
)


def _own(message: Message) -> str:
    """The message's text without the lines it quotes."""
    return "\n".join(line for line in message.text.splitlines() if not QUOTED.match(line))


def language_of(message: Message) -> str | None:
    """The language the message is written in, as code reads its subject and the start of its
    own text, or None where too little of it or too mixed to tell."""
    return language_in(f"{message.subject}\n{_own(message)}")


@dataclass
class _Block:
    """A run of text and inline tags between two block boundaries: what the model reads, the
    tags its marks stand for, its line breaks and the HTML it was."""

    tags: dict[int, tuple[str, str]] = field(default_factory=dict)
    breaks: list[str] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)
    raw: list[str] = field(default_factory=list)

    def text(self) -> str:
        return "".join(self.parts)


class _Parser(HTMLParser):
    """The HTML as tokens and blocks: what stands between blocks as it is, each block apart. A
    closing tag whose opening stood in an earlier block ends a block too, so it stays where it
    was."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str | _Block] = []
        self.block: _Block | None = None
        self.opened: list[tuple[str, int]] = []
        self.styled = False
        self.kept = 0

    def _between(self, raw: str) -> None:
        self._close()
        self.out.append(raw)

    def _close(self) -> None:
        if self.block is not None:
            self.out.append(self.block)
            self.block, self.opened = None, []

    def _inline(self) -> _Block:
        if self.block is None:
            self.block = _Block()
        return self.block

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or f"<{tag}>"
        if tag == "style":
            self.styled = True
            self._between(raw)
        elif tag in BLOCK_TAGS:
            self.kept += tag == "pre"
            self._between(raw)
        elif tag == "br":
            block = self._inline()
            block.breaks.append(raw)
            block.parts.append("<br/>")
            block.raw.append(raw)
        elif tag in VOID_TAGS:
            block = self._inline()
            number = len(block.tags) + 1
            block.tags[number] = (raw, "")
            block.parts.append(f"<{number}/>")
            block.raw.append(raw)
        else:
            block = self._inline()
            number = len(block.tags) + 1
            block.tags[number] = (raw, f"</{tag}>")
            self.opened.append((tag, number))
            block.parts.append(f"<{number}>")
            block.raw.append(raw)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "style":
            self.styled = False
            self._between(f"</{tag}>")
        elif tag in BLOCK_TAGS or self.block is None:
            self.kept = max(self.kept - (tag == "pre"), 0)
            self._between(f"</{tag}>")
        elif tag in VOID_TAGS:
            return
        else:
            number = next((n for name, n in reversed(self.opened) if name == tag), None)
            if number is None:
                self._between(f"</{tag}>")
                return
            self.opened.remove((tag, number))
            self.block.parts.append(f"</{number}>")
            self.block.raw.append(f"</{tag}>")

    def handle_data(self, data):
        if self.styled:
            self.out.append(data)
            return
        block = self._inline()
        block.raw.append(html.escape(data, quote=False))
        read = data.replace("<", "‹").replace(">", "›") if MARK.search(data) else data
        if not self.kept:
            block.parts.append(SPACE.sub(" ", read))
            return
        lines = read.split("\n")
        block.breaks.extend("\n" for _ in lines[1:])
        block.parts.append("<br/>".join(lines))

    def close(self):
        super().close()
        self._close()


def _key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def _worded(text: str) -> bool:
    return bool(LETTER.search(MARK.sub("", text)))


@dataclass(frozen=True)
class Body:
    """What PONISTRA shows of a message, as the model reads it and as it is put back: its
    pieces, each a piece kept as it is or a block, and the blocks with words by their keys."""

    pieces: list[str | tuple[str, str, str, _Block | None, str]]
    blocks: dict[str, str]
    html: bool


def body(markup: str | None, text: str | None) -> Body:
    """The HTML the message shows, or else its text, cut into blocks."""
    pieces: list = []
    blocks: dict[str, str] = {}

    def add(whole: str, block: _Block | None, raw: str) -> None:
        stripped = whole.strip()
        if not _worded(stripped):
            pieces.append(raw)
            return
        lead = whole[: len(whole) - len(whole.lstrip())]
        trail = whole[len(whole.rstrip()) :]
        key = _key(stripped)
        blocks[key] = stripped
        pieces.append((key, lead, trail, block, raw))

    if markup is not None:
        parser = _Parser()
        parser.feed(markup)
        parser.close()
        for each in parser.out:
            if isinstance(each, str):
                pieces.append(each)
            else:
                add(each.text(), each, "".join(each.raw))
        return Body(pieces, blocks, True)
    for paragraph in PARAGRAPHS.split(text or ""):
        if PARAGRAPHS.fullmatch(paragraph):
            pieces.append(paragraph)
        else:
            inner = paragraph.strip()
            start = paragraph.index(inner[:1]) if inner else 0
            whole = paragraph[:start] + BREAK.sub("<br/>", inner) + paragraph[start + len(inner) :]
            add(whole, None, paragraph)
    return Body(pieces, blocks, False)


def _marks(text: str) -> list[str]:
    return [found[0] for found in MARK.finditer(text) if found[0] != "<br/>"]


def _plain(text: str) -> str:
    """The translation's text with its marks taken out and its line breaks as such."""
    return MARK.sub(lambda found: "\n" if found[0] == "<br/>" else "", text)


def _rebuilt(block: _Block | None, translated: str, original: str) -> str:
    """The translated block with its tags back in place; where the model lost or doubled a
    mark, its text alone, the block's images after it."""
    escaped = (lambda text: html.escape(text, quote=False)) if block else str
    if sorted(_marks(translated)) != sorted(_marks(original)):
        images = [raw for raw, end in block.tags.values() if not end] if block else []
        return escaped(_plain(translated).replace("\n", " ")) + "".join(images)
    out, last = [], 0
    breaks = iter(block.breaks if block else [])
    for found in MARK.finditer(translated):
        out.append(escaped(translated[last : found.start()]))
        last = found.end()
        if found[0] == "<br/>":
            out.append(next(breaks, "<br>") if block else "\n")
        elif block:
            start, end = block.tags[int(found[2])]
            out.append(end if found[1] else start)
    out.append(escaped(translated[last:]))
    return "".join(out)


def put_back(shown: Body, translated: dict[str, str]) -> str:
    """The message as it shows with each block the translation holds written in its place."""
    out = []
    for piece in shown.pieces:
        if isinstance(piece, str):
            out.append(piece)
            continue
        key, lead, trail, block, raw = piece
        if key not in translated:
            out.append(raw)
            continue
        written = _rebuilt(block, translated[key], shown.blocks[key])
        out.append(lead + written + trail)
    return "".join(out)


class Untranslated(Exception):
    """Why the model gave no translation: a code the reader is shown."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def kept(message: Message, into: str) -> Translation | None:
    return Translation.objects.filter(message=message, language=into).first()


def _saved(
    message: Message, into: str, run: ActionRun, answer: dict, keys: list[str]
) -> Translation:
    blocks = {
        keys[each["id"] - 1]: each["text"]
        for each in answer["blocks"]
        if 0 < each["id"] <= len(keys)
    }
    text = "\n".join(_plain(each) for each in blocks.values())
    try:
        return Translation.objects.create(
            message=message,
            language=into,
            subject=answer["subject"],
            blocks=blocks,
            text=text,
            run=run,
        )
    except IntegrityError:
        return Translation.objects.get(message=message, language=into)


async def translate(user, message: Message, shown: Body, into: str, consent) -> Translation:
    """The message translated into the language by the model, its run kept with what it took and
    who let the message out to it, the user this once or for all of their mail."""
    keys = list(shown.blocks)
    if sum(len(each) for each in shown.blocks.values()) + len(message.subject) > LONGEST:
        raise Untranslated("message_too_long")
    run = await database(ActionRun.objects.create)(
        user=user,
        action=ACTION,
        target={"message": message.pk},
        parameters={"language": into},
        consent=consent,
        consented_by=user,
    )
    lines = [f"[subject] {message.subject}"]
    lines += [f"[{number}] {shown.blocks[key]}" for number, key in enumerate(keys, 1)]
    prompt = Prompt(
        INSTRUCTION.format(language=name_of(into)),
        "\n".join(lines),
        {"translation": TRANSLATION},
        effort="low",
        steps=3,
    )
    try:
        answer = await runs.decided(run, MODEL, prompt)
    except (model.Failed, Unavailable) as failed:
        raise Untranslated(failed.code) from None
    return await database(_saved)(message, into, run, answer, keys)


def _pairs(written: Body, translated: Body) -> dict[str, str]:
    """What the user wrote by the blocks of its translation, block for block as both are cut."""
    blocks = [
        [piece[0] for piece in each.pieces if not isinstance(piece, str)]
        for each in (written, translated)
    ]
    if len(blocks[0]) != len(blocks[1]):
        return {}
    return {after: written.blocks[before] for before, after in zip(*blocks, strict=True)}


async def reply(
    user,
    answered: Message,
    written: str,
    subject: str,
    heading: list[str],
    mine: str,
    into: str,
    consent,
) -> dict:
    """The reply the user wrote, by the model in the language of the message it answers: its
    subject, HTML and heading, and what the user wrote by the blocks of the translation, which the
    message keeps once sent."""
    own = body(written, None)
    cited = body(sending.heading_html(heading), None)
    together = {**own.blocks, **cited.blocks}
    if sum(len(each) for each in together.values()) + len(subject) > LONGEST:
        raise Untranslated("message_too_long")
    run = await database(ActionRun.objects.create)(
        user=user,
        action=REPLY,
        target={"message": answered.pk},
        parameters={"language": into},
        consent=consent,
        consented_by=user,
    )
    keys = list(together)
    context = SPACE.sub(" ", _own(answered)).strip()[:CONTEXT]
    lines = [f"[answered] {context}", f"[subject] {subject}"]
    lines += [f"[{number}] {together[key]}" for number, key in enumerate(keys, 1)]
    prompt = Prompt(
        REPLY_INSTRUCTION.format(language=name_of(into)),
        "\n".join(lines),
        {"translation": TRANSLATION},
        effort="low",
        steps=3,
    )
    try:
        answer = await runs.decided(run, MODEL, prompt)
    except (model.Failed, Unavailable) as failed:
        raise Untranslated(failed.code) from None
    got = {
        keys[each["id"] - 1]: each["text"]
        for each in answer["blocks"]
        if 0 < each["id"] <= len(keys)
    }
    translated = put_back(own, got)
    lines = [_plain(got[key]).split("\n") for key in cited.blocks if key in got]
    said = lines[0] if lines else heading
    pairs = _pairs(own, body(translated, None))
    pairs |= _pairs(cited, body(sending.heading_html(said), None))
    language = language_in("\n".join(_plain(each) for each in own.blocks.values())) or mine
    return {
        "language": into,
        "subject": answer["subject"],
        "html": translated,
        "heading": said,
        "source": {"language": language, "subject": subject, "blocks": pairs, "run": str(run.pk)},
    }


def keep_written(message: Message, answered: Message, source: dict) -> None:
    """Keeps what the user wrote in their language as the translation of the message they sent
    in another, with the message it answers as they read it translated, where they did."""
    read = kept(answered, source["language"])
    Translation.objects.update_or_create(
        message=message,
        language=source["language"],
        defaults={
            "subject": source["subject"],
            "blocks": (read.blocks if read else {}) | source["blocks"],
            "text": "\n".join(_plain(each) for each in source["blocks"].values()),
            "run_id": source["run"],
        },
    )
