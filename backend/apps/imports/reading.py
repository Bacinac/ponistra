"""What reading a file for import gives, whatever its kind: a document's tabs and what
goes with them, and what could not be carried, for the import's report."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from apps.content.blocks import Block


class Unreadable(Exception):
    """Not a file of the kind it was taken for, or one too broken to read."""


class TooLarge(Exception):
    pass


class TooManyCells(TooLarge):
    """A workbook with more cells than an import takes on."""


class TooManyFormulas(TooLarge):
    """A workbook holding more different formulas than an import takes on."""


@dataclass
class Remark:
    author: str
    date: datetime | None
    text: str


@dataclass
class Thread:
    """A comment and its replies, and the stretch of text it is on: the block and offset
    of its first character and of its last."""

    remarks: list[Remark]
    resolved: bool
    start: tuple[str, int] | None = None
    end: tuple[str, int] | None = None
    closed: bool = False
    quote: str = ""


@dataclass
class Tab:
    """A tab's title and blocks, its pages where they are its own, and what each section after
    one of its section breaks sets itself, by the break's id: its page setup, None where it
    takes the one before, and the headers and footers it names."""

    title: str
    blocks: list[Block]
    page: dict | None = None
    parts: dict[str, list[Block]] | None = None
    sections: dict[str, tuple[dict | None, dict[str, list[Block]]]] = field(default_factory=dict)


@dataclass
class Imported:
    """A file's tabs and what goes with them, its defined names by id among them; a file that
    sets up no pages, a spreadsheet, has no page and its tabs take the document's, and one with
    slides their template. The rows a large file's tables hold are written by `rest`, given the
    document once it stands, which says the tables it wrote them in; in the reader `rest` sends
    them, given where to."""

    tabs: list[Tab]
    page: dict | None
    parts: dict[str, list[Block]]
    theme: dict[str, str]
    styles: dict[str, dict]
    images: dict[str, bytes]
    threads: list[Thread]
    report: dict
    formats: dict[str, list[dict]]
    template: dict | None = None
    names: dict[str, dict] = field(default_factory=dict)
    saved: dict[str, dict[str, tuple]] = field(default_factory=dict)
    rest: Callable[[object], object] | None = None
