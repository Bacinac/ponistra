"""The numbers a document's styles show before its blocks, as the editor shows them: each
heading level and each other style counts on through the tabs in reading order, from the
tallies the tabs' editors keep under `numbers` in the document's own state."""

from pycrdt import Doc, Map

from . import blocks
from .schema import LEVELS, LISTS
from .styles import STYLES

NUMBERS = "numbers"
NUMBERINGS = ("1", "a", "A", "i", "I")
AFFIX_MAX = 40
ROMAN = (
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
)


def letters(count: int) -> str:
    found = ""
    while count > 0:
        count, rest = divmod(count - 1, 26)
        found = chr(ord("a") + rest) + found
    return found


def roman(count: int) -> str:
    found = ""
    for value, digits in ROMAN:
        while count >= value:
            found += digits
            count -= value
    return found


def numeral(count: int, numbering: str) -> str:
    if count < 1 or numbering == "1":
        return str(count)
    if numbering in ("a", "A"):
        found = letters(count)
    elif numbering in ("i", "I"):
        found = roman(count)
    else:
        return ""
    return found.upper() if numbering.isupper() else found


def _affix(value) -> str:
    return value[:AFFIX_MAX] if isinstance(value, str) else ""


def styles_of(own: Doc) -> dict[str, dict]:
    """Each style's kind and how it numbers, which is all of a style its numbers follow."""
    found = {}
    for id, style in own.get(STYLES, type=Map).items():
        if not isinstance(style, Map) or not isinstance(style.get("kind"), str):
            continue
        numbering = style.get("numbering")
        found[id] = {
            "kind": style["kind"],
            "numbering": numbering if numbering in NUMBERINGS else "",
            "prefix": _affix(style.get("prefix")),
            "suffix": _affix(style.get("suffix")),
            "nested": style.get("nested") is True,
        }
    return found


def _counted(value) -> bool:
    return type(value) in (int, float) and value >= 0 and value == int(value)


def start_of(own: Doc, order: list, tab) -> dict[str, int]:
    """Where the tab's counters start: on from the tabs before it, as their editors tallied
    them."""
    tallies = own.get(NUMBERS, type=Map)
    counters: dict[str, int] = {}
    for id in map(str, order):
        if id == str(tab):
            break
        tally = tallies.get(id)
        for key, step in (tally if isinstance(tally, dict) else {}).items():
            if not isinstance(step, dict) or not _counted(step.get("count")):
                continue
            count = int(step["count"])
            counters[key] = count if step.get("reset") is True else counters.get(key, 0) + count
    return counters


def numbering_of(own: Doc, order: list, tab) -> dict:
    """What the tab's numbers follow: the document's styles and, of the counters the tabs
    before it leave, those a style numbers by."""
    styles = styles_of(own)
    numbered = {id for id, style in styles.items() if style["numbering"]}
    if any(styles[id]["kind"].startswith("h") for id in numbered):
        numbered |= {f"#{level}" for level in LEVELS}
    start = {key: count for key, count in start_of(own, order, tab).items() if key in numbered}
    return {"styles": styles, "start": start}


def kind_of(block: blocks.Block) -> str | None:
    if block.type == "paragraph":
        return "text"
    if block.type in ("title", "subtitle"):
        return block.type
    if block.type == "heading" and block.attrs.get("level") in LEVELS:
        return f"h{block.attrs['level']}"
    return None


def numbered(
    content: list[blocks.Block], numbering: dict
) -> tuple[dict[int, str], dict[str, dict]]:
    """Each numbered block's number, by its index in the order the tab is read, and the tab's
    tally as its editors keep it under `numbers`. A heading numbers on at its level and starts
    the levels below it again; it shows the numbers of the headings above it when its style
    nests them, each in the form of that heading's style."""
    styles, start = numbering["styles"], numbering["start"]
    labels: dict[int, str] = {}
    tally: dict[str, tuple[bool, int]] = {}
    above: dict[int, dict | None] = {}

    def value(key: str) -> int:
        reset, count = tally.get(key, (False, 0))
        return count if reset else start.get(key, 0) + count

    def step(key: str, restart: bool) -> None:
        reset, count = tally.get(key, (False, 0))
        tally[key] = (True, 1) if restart else (reset, count + 1)

    for index, block in enumerate(content):
        kind = kind_of(block)
        if kind is None or block.attrs.get("list") in LISTS:
            continue
        own = block.attrs.get("style")
        id = own if own in styles and styles[own]["kind"] == kind else kind
        style = styles.get(id)
        restart = block.attrs.get("restart") is True
        if block.type != "heading":
            step(id, restart)
            if style and style["numbering"]:
                number = numeral(value(id), style["numbering"])
                labels[index] = f"{style['prefix']}{number}{style['suffix']}"
            continue
        level = block.attrs["level"]
        step(f"#{level}", restart)
        above[level] = style
        for below in LEVELS:
            if below > level:
                tally[f"#{below}"] = (True, 0)
                above.pop(below, None)
        if not style or not style["numbering"]:
            continue
        numerals = []
        if style["nested"]:
            for higher in LEVELS:
                if higher >= level:
                    break
                by = above.get(higher) or styles.get(f"h{higher}")
                if by and by["numbering"]:
                    numerals.append(numeral(value(f"#{higher}"), by["numbering"]))
        numerals.append(numeral(value(f"#{level}"), style["numbering"]))
        labels[index] = f"{style['prefix']}{'.'.join(numerals)}{style['suffix']}"
    counted = {key: {"reset": reset, "count": count} for key, (reset, count) in tally.items()}
    return labels, counted
