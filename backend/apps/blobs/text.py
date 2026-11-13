import codecs
from dataclasses import dataclass
from html.parser import HTMLParser

from charset_normalizer import from_bytes

from . import store
from .models import Blob

BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)
# The code page is told from this much; more only makes charset-normalizer slower.
GUESSED = 1024 * 1024


class NotText(Exception):
    pass


@dataclass
class Text:
    text: str
    encoding: str
    truncated: bool


def encoding_of(raw: bytes) -> str:
    """The code page bytes are in: the one their byte order mark names, UTF-8 where they read as
    UTF-8, else the one charset-normalizer finds likeliest."""
    for bom, encoding in BOMS:
        if raw.startswith(bom):
            return encoding
    sample = raw[:GUESSED]
    try:
        codecs.getincrementaldecoder("utf-8")().decode(sample, final=len(raw) <= GUESSED)
        return "utf-8"
    except UnicodeDecodeError:
        pass
    found = from_bytes(sample).best()
    if found is None:
        raise NotText
    return found.encoding


def label(encoding: str) -> str:
    """A code page as people name it: Windows-1250, ISO-8859-2, UTF-16."""
    name = codecs.lookup(encoding).name
    if name.startswith("cp") and name[2:].isdigit():
        return f"Windows-{name[2:]}"
    if name.startswith("iso8859-"):
        return f"ISO-8859-{name.removeprefix('iso8859-')}"
    return {"utf-8-sig": "UTF-8", "latin-1": "ISO-8859-1"}.get(name, name.upper())


def read(blob: Blob, limit: int) -> Text:
    """At most limit bytes of a text file decoded, ending on a whole line where it is cut."""
    with store.path_of(blob.sha256).open("rb") as file:
        raw = file.read(limit + 1)
    truncated = len(raw) > limit
    raw = raw[:limit]
    encoding = encoding_of(raw)
    decoder = codecs.getincrementaldecoder(encoding)(errors="replace")
    text = decoder.decode(raw, final=not truncated)
    if truncated and "\n" in text:
        text = text[: text.rindex("\n") + 1]
    return Text(text.replace("\r\n", "\n").replace("\x00", ""), label(encoding), truncated)


def pages(text: str, size: int) -> list[str]:
    """Text in pieces of about size characters, each ending on a whole line."""
    pieces, start = [], 0
    while start < len(text):
        end = start + size
        if end < len(text):
            cut = text.rfind("\n", start, end)
            end = cut + 1 if cut > start else end
        pieces.append(text[start:end])
        start = end
    return pieces


# What a reader of a page does not see, and where its text breaks into lines.
UNSEEN = {"head", "title", "script", "style", "template", "noscript"}
BLOCKS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "details",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "summary",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}


class _Seen(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag in UNSEEN:
            self.hidden += 1
        elif tag in BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag) -> None:
        if tag in UNSEEN:
            self.hidden = max(self.hidden - 1, 0)
        elif tag in BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data) -> None:
        if not self.hidden:
            self.parts.append(data)


def seen(page: str) -> str:
    """The text a page of HTML shows, line by line; what its script writes is not read."""
    reader = _Seen()
    reader.feed(page)
    reader.close()
    lines = (" ".join(line.split()) for line in "".join(reader.parts).splitlines())
    return "\n".join(line for line in lines if line)
