"""A tab's slides as the editor finds them (frontend editor/slides.ts): each title, heading 1 and
slide break at the text's top level starts one, and what comes before the first is one when it
holds anything or is all there is; and the document's slide template, its own layouts where it
has them, else the built-in ones of `schema/slides.json`, at its slide size."""

import json
from dataclasses import dataclass

from django.conf import settings
from jsonschema import Draft202012Validator
from pycrdt import Doc, Map

from .blocks import TEXTBLOCKS, Block

SLIDES = "slides"
BUILT_IN = json.loads(settings.SCHEMA.with_name("slides.json").read_text())
KINDS = tuple(BUILT_IN["$defs"]["kind"]["enum"])
ROLES = ("title", "subtitle", "body", "second")
SIZE = BUILT_IN["$defs"]["size"]["properties"]["width"]
LAYOUT = Draft202012Validator({"$defs": BUILT_IN["$defs"], "$ref": "#/$defs/layout"})


def starts_slide(block: Block) -> bool:
    return block.type in ("title", "slideBreak") or (
        block.type == "heading" and block.attrs.get("level") == 1
    )


def _holds_anything(run: list[Block]) -> bool:
    return any(block.type not in TEXTBLOCKS or block.runs for block in run)


def slides_of(content: list[Block]) -> list[list[Block]]:
    runs: list[list[Block]] = []
    for block in content:
        if starts_slide(block) or not runs:
            runs.append([])
        runs[-1].append(block)
    return [
        run
        for index, run in enumerate(runs)
        if index > 0 or starts_slide(run[0]) or _holds_anything(run) or len(runs) == 1
    ]


@dataclass(frozen=True)
class Template:
    """A slide's size in cm and the layouts slides are laid out by."""

    width: float
    height: float
    layouts: list[dict]
    built_in: bool


def _sized(length) -> bool:
    return (
        isinstance(length, int | float)
        and not isinstance(length, bool)
        and SIZE["minimum"] <= length <= SIZE["maximum"]
    )


def _scaled(box: dict, across: float, down: float) -> dict:
    return {
        **box,
        "x": box["x"] * across,
        "y": box["y"] * down,
        "w": box["w"] * across,
        "h": box["h"] * down,
    }


def built_in(width: float, height: float) -> list[dict]:
    """The built-in layouts on slides of the size, their boxes and shapes stretched as the
    slide is."""
    across = width / BUILT_IN["size"]["width"]
    down = height / BUILT_IN["size"]["height"]
    if across == down == 1:
        return BUILT_IN["layouts"]
    return [
        {
            **layout,
            "boxes": {role: _scaled(box, across, down) for role, box in layout["boxes"].items()},
            "shapes": [_scaled(shape, across, down) for shape in layout["shapes"]],
        }
        for layout in BUILT_IN["layouts"]
    ]


def template_of(own: Doc) -> Template:
    kept = own.get(SLIDES, type=Map)
    width, height = kept.get("width"), kept.get("height")
    if not (_sized(width) and _sized(height)):
        width, height = BUILT_IN["size"]["width"], BUILT_IN["size"]["height"]
    stored = kept.get("layouts")
    layouts = [each for each in stored if LAYOUT.is_valid(each)] if isinstance(stored, list) else []
    if layouts:
        return Template(width, height, layouts, False)
    return Template(width, height, built_in(width, height), True)


def write(own: Doc, template: dict) -> None:
    """A file's slide template as the document's."""
    with own.transaction():
        own.get(SLIDES, type=Map).update(template)


def join(own: Doc, template: dict) -> None:
    """A file's layouts after the document's own, stretched to its slides as the built-in ones
    are; a document laid out by the built-in layouts keeps them first, so its slides keep
    their look."""
    current = template_of(own)
    across = current.width / template["width"]
    down = current.height / template["height"]
    added = [
        {
            **layout,
            "boxes": {role: _scaled(box, across, down) for role, box in layout["boxes"].items()},
            "shapes": [_scaled(shape, across, down) for shape in layout["shapes"]],
        }
        for layout in template["layouts"]
    ]
    with own.transaction():
        kept = own.get(SLIDES, type=Map)
        kept["layouts"] = [*current.layouts, *added]
        kept.update({"width": current.width, "height": current.height})
