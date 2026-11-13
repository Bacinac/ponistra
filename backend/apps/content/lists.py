"""A document's list formats: how a list shows its items at each of its levels, kept once in
the document's own state under `lists` and named by its items' `format` (frontend
editor/forms.ts). A list without a format shows the standard levels."""

from pycrdt import Doc, Map

from .numbering import AFFIX_MAX, NUMBERINGS
from .schema import DEEPEST, INDENT_STEP

LISTS = "lists"
LEVELS = 9
NUMBERS = ("1", "a", "i")
BULLETS = ("•", "◦", "▪")
NONE = {"numbering": "", "prefix": "", "suffix": "", "nested": False}


def standard(kind: str, level: int) -> dict:
    if kind == "number":
        return {"numbering": NUMBERS[level % 3], "prefix": "", "suffix": ".", "nested": False}
    return {"numbering": "", "prefix": BULLETS[level % 3], "suffix": "", "nested": False}


def is_standard(format: list[dict]) -> bool:
    return all(
        level == standard("number" if level["numbering"] else "bullet", at)
        for at, level in enumerate(format)
    )


def write(own: Doc, formats: dict[str, list[dict]]) -> None:
    with own.transaction():
        own.get(LISTS, type=Map).update(formats)


def read(own: Doc) -> dict[str, list[dict]]:
    found = own.get(LISTS, type=Map)
    return {id: format for id, format in found.items() if isinstance(format, list)}


def form_of(look: dict) -> dict:
    """A level's or a style's numbering, of the forms the editor knows."""
    numbering = look.get("numbering")
    affix = [look.get(side) for side in ("prefix", "suffix")]
    return {
        "numbering": numbering if numbering in NUMBERINGS else "",
        **{
            side: value[:AFFIX_MAX] if isinstance(value, str) else ""
            for side, value in zip(("prefix", "suffix"), affix, strict=True)
        },
        "nested": look.get("nested") is True,
    }


def level_in(format: list | None, kind: str, level: int) -> dict:
    """A list level as an item of the kind shows it: in the format's form where that is of its
    kind (frontend editor/forms.ts)."""
    own = format[level] if format and level < len(format) else None
    if isinstance(own, dict) and ("number" if own.get("numbering") else "bullet") == kind:
        return form_of(own)
    return standard(kind, level)


def level_of(attrs: dict) -> int:
    """An item's list level, by how far it is indented."""
    indent = attrs.get("indent")
    indent = indent if isinstance(indent, int | float) and not isinstance(indent, bool) else 0
    return min(max(round(indent / INDENT_STEP), 0), DEEPEST)


class Items:
    """Our list numbers, counted as the editor counts them (frontend editor/lists.ts): on
    within a run of items, at their level and of their kind; another block ends the run, but
    an item that continues its list counts on from the last item of its kind."""

    def __init__(self):
        self.counts: list = []
        self.last: dict[str, list] = {}

    def end(self) -> None:
        self.counts = []

    def step(self, attrs: dict) -> tuple[str, int, list]:
        kind = attrs["list"]
        level = level_of(attrs)
        restart = attrs.get("restart") is True
        continued = attrs.get("continued") is True and not restart
        counts = list(self.last.get(kind, []) if continued else self.counts)[: level + 1]
        counts += [None] * (level + 1 - len(counts))
        before = counts[level]
        count = before[1] + 1 if before and before[0] == kind and not restart else 1
        counts[level] = (kind, count)
        self.counts = self.last[kind] = counts
        return kind, level, counts
