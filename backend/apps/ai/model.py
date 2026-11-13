"""A model's run (A4): the model reads what an action gives it and changes the document only
through the operations the action lets it call, each call carried out on its own."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from logging import getLogger

import anthropic

from apps.content import schema
from apps.content.operations import OPERATIONS, OWN_OPERATIONS, Copy, Refused

from .installation import client

log = getLogger(__name__)

STEPS = 40
MAX_TOKENS = 64000
FALLBACK = "server-side-fallback-2026-07-01"
WITHOUT_FALLBACK = {"claude-haiku-5-5"}
DESCRIPTIONS = {
    "insert": "Puts blocks into the tab, each a ProseMirror JSON node of the document's schema.",
    "rewrite": "Writes a block's whole text anew, as plain text on one line. Only the words that "
    "differ change, and the rest keeps its formatting.",
    "table": "Puts a table into the tab: its rows, the first its header, each cell what one types "
    "into it or, for a computed one, a formula.",
    "replace": "Writes a block's or a footnote's whole text anew, on one line, with the tags its "
    "text has: <1>…</1> around the words that keep the formatting of the part so tagged, each "
    "<2/>, a footnote or a field, once where it stands, <br/> a line break.",
    "cells": "Writes cells of a table, each by its row and column, its value what one types into "
    "it, or a formula, blocks or a number format.",
    "set": "Sets a block's type, one of the text's, or its attributes; null takes one off.",
    "mark": "Gives a block's or a footnote's text, the whole of it or the words given, a mark "
    "with its attributes, or takes it off.",
    "text": "Writes pieces of text, each with its marks, in place of a block's or a footnote's "
    "text, the whole of it or the words given.",
    "lines": "Puts rows or columns into a table under the ids given, before the one named or at "
    "its end, or takes out those from one to the other.",
    "fill": "Fills a table from a range of its cells to the slot given, as a sheet's fill handle "
    "does: a series goes on and formulas move.",
    "order": "Sorts a table's rows by their values in a column, as Excel sorts: those from one "
    "to the other, or all of them below a header but the totals.",
    "grid": "Sets a table's name, its columns' widths and rows' heights, and the last row that "
    "stays at the top.",
    "looks": "Gives whole rows or columns of a table, from one to the other, a look: the marks of "
    "their text, their paragraphs' attributes and their fill.",
    "copy": "Copies a table right after it under a name of its own, with its formulas or the "
    "values they show.",
    "move": "Moves the blocks from the first to the last given, side by side, to the place given.",
    "delete": "Takes out the blocks from the first to the last given, side by side.",
    "accept": "Accepts the proposals given by id, or all of the tab's without ids.",
    "reject": "Rejects the proposals given by id, or all of the tab's without ids.",
    "substitute": "Replaces a text found in the tab, its case counting or not and as a whole "
    "word or not: everywhere, in its text and its tables' cells but those a formula calculates, "
    "or where it starts in a block or a footnote, or in one cell.",
    "style": "Sets the font or the size in points of one of the document's styles, which every "
    "block of that style shows.",
}


@dataclass(frozen=True)
class Price:
    """What a model charges, in dollars for a million tokens, for those it reads anew, those it
    writes and those it reads from the cache; with `long`, what it charges instead for a prompt
    of more than LONG tokens."""

    input: Decimal
    output: Decimal
    cached: Decimal
    long: Price | None = None


LONG = 100_000
CACHE_WRITE = Decimal("1.25")
PRICES = {
    "claude-opus-5-5": Price(Decimal(4), Decimal(20), Decimal("0.20")),
    "claude-sonnet-5-5": Price(Decimal(2), Decimal(10), Decimal("0.20")),
    "claude-haiku-5-5": Price(
        Decimal("0.10"),
        Decimal("0.50"),
        Decimal("0.01"),
        Price(Decimal("0.50"), Decimal("2.50"), Decimal("0.05")),
    ),
    "claude-opus-5": Price(Decimal(5), Decimal(25), Decimal("0.50")),
    "claude-opus-4-8": Price(Decimal(5), Decimal(25), Decimal("0.50")),
}


@dataclass(frozen=True)
class Spent:
    """What one of the model's answers took: the model that gave it, the tokens it read anew,
    wrote, read from the cache and wrote to it, and what those cost in dollars, None where a
    model that took part has no price."""

    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost: Decimal | None


def _cost(model: str, read: int, wrote: int, cached: int, cache_written: int) -> Decimal | None:
    price = PRICES.get(model)
    if price is None:
        log.error("no price for the model %s", model)
        return None
    if price.long is not None and read + cached + cache_written > LONG:
        price = price.long
    return (
        read * price.input
        + wrote * price.output
        + cached * price.cached
        + cache_written * price.input * CACHE_WRITE
    ) / 1_000_000


def spent(asked: str, response: anthropic.types.beta.BetaMessage) -> Spent:
    """What the answer took, summed over its attempts where a fallback took over from the model
    asked, each at its own model's price."""
    usage = response.usage
    attempts = (
        [(each.model or asked, each) for each in usage.iterations if each.type != "compaction"]
        if usage.iterations
        else [(response.model, usage)]
    )
    counts = [
        (
            each.input_tokens,
            each.output_tokens,
            each.cache_read_input_tokens or 0,
            each.cache_creation_input_tokens or 0,
        )
        for _, each in attempts
    ]
    costs = [_cost(model, *count) for (model, _), count in zip(attempts, counts, strict=True)]
    return Spent(
        response.model,
        *map(sum, zip(*counts, strict=True)),
        None if None in costs else sum(costs, Decimal(0)),
    )


class Failed(Exception):
    """Why a model's run stopped short: a code the editor names, and what the API said."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Among:
    """A field the model fills, with one of the values the action gives."""

    values: tuple[str, ...]


@dataclass(frozen=True)
class Choice:
    """A tool through which the model only decides: what it is for and the JSON Schema of its
    answer, which ends the conversation once given."""

    description: str
    schema: dict


@dataclass(frozen=True)
class Reading:
    """A tool through which the model reads what code finds for it: what it is for, the JSON
    Schema of what it asks and what reads the answer, which goes back to the model as JSON."""

    description: str
    schema: dict
    read: Callable[[dict], object]


@dataclass(frozen=True)
class Prompt:
    """What an action asks of a model: the instruction it works under, the content it reads,
    for each operation it may call the fields the action fixes or bounds, the rest the model's,
    how many turns it may take, the copy of the tab it writes in, where it opens one, whether
    what it says at the end is kept for the user, and the operations code carries out on the tab
    before the model begins, taken back with the run."""

    instruction: str
    content: str
    tools: dict[str, dict | Choice | Reading]
    effort: str = "medium"
    steps: int | None = None
    opens: Copy | None = None
    replies: bool = False
    before: list[dict] | None = None


def tool(name: str, fixed: dict | Choice | Reading) -> dict:
    """The operation as a tool, its fields as the operation's schema checks them, less those
    the action fixes and of those it bounds only the values it gives; a choice or a reading as
    it is."""
    if isinstance(fixed, Choice | Reading):
        return {"name": name, "description": fixed.description, "input_schema": fixed.schema}
    spec = schema.validator({**OPERATIONS, **OWN_OPERATIONS}[name]).schema
    left = {
        key: {"enum": list(fixed[key].values)} if isinstance(fixed.get(key), Among) else value
        for key, value in spec["properties"].items()
        if key != "op" and (key not in fixed or isinstance(fixed[key], Among))
    }
    return {
        "name": name,
        "description": DESCRIPTIONS[name],
        "input_schema": {
            "type": "object",
            "properties": left,
            "required": [key for key in spec["required"] if key in left],
            "additionalProperties": False,
        },
    }


def answer(request: dict) -> anthropic.types.beta.BetaMessage:
    try:
        with client().beta.messages.stream(**request) as stream:
            return stream.get_final_message()
    except anthropic.AuthenticationError:
        raise Failed("key_refused") from None
    except anthropic.RateLimitError:
        raise Failed("rate_limited") from None
    except anthropic.APIStatusError as error:
        raise Failed("api", f"{error.status_code} {error.message}") from None
    except anthropic.APIConnectionError:
        raise Failed("ai_unreachable") from None


def _result(use, call: Callable[[dict], list[dict]], prompt: Prompt) -> dict:
    found = {"type": "tool_result", "tool_use_id": use.id}
    if use.name not in prompt.tools:
        return {**found, "is_error": True, "content": f"unknown tool {use.name}"}
    fixed = prompt.tools[use.name]
    if isinstance(fixed, Choice | Reading):
        if wrong := next(schema.validator(fixed.schema).iter_errors(use.input), None):
            return {**found, "is_error": True, "content": wrong.message}
        if isinstance(fixed, Choice):
            call({**use.input, "op": use.name})
            return {**found, "content": "done"}
        try:
            return {**found, "content": json.dumps(fixed.read(use.input), ensure_ascii=False)}
        except Refused as refused:
            return {**found, "is_error": True, "content": str(refused)}
    for key, value in fixed.items():
        if isinstance(value, Among) and use.input.get(key) not in value.values:
            return {
                **found,
                "is_error": True,
                "content": f"{key} is one of {', '.join(value.values)}",
            }
    try:
        made = call(
            {
                **use.input,
                **{key: value for key, value in fixed.items() if not isinstance(value, Among)},
                "op": use.name,
            }
        )
    except Refused as refused:
        return {**found, "is_error": True, "content": str(refused)}
    return {**found, "content": json.dumps(made) if made else "done"}


def converse(
    model: str,
    prompt: Prompt,
    call: Callable[[dict], list[dict]],
    stopped: Callable[[], bool],
    spend: Callable[[Spent], None],
) -> str:
    """Lets the model work until it is done or stopped, each of its tool calls carried out as
    the operation it names, one the document refuses going back to it to put right, and what
    each answer took given to `spend`; and returns what it says at the end."""
    request = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": [
            {"type": "text", "text": prompt.instruction, "cache_control": {"type": "ephemeral"}}
        ],
        "tools": [tool(name, fixed) for name, fixed in prompt.tools.items()],
        "output_config": {"effort": prompt.effort},
        "cache_control": {"type": "ephemeral"},
    }
    if model not in WITHOUT_FALLBACK:
        request |= {"betas": [FALLBACK], "fallbacks": "default"}
    messages: list[dict] = [{"role": "user", "content": prompt.content}]
    for _ in range(prompt.steps or STEPS):
        if stopped():
            return ""
        response = answer({**request, "messages": messages})
        spend(spent(model, response))
        if response.stop_reason == "refusal":
            category = response.stop_details and response.stop_details.category
            raise Failed("refused", category or "")
        if response.stop_reason == "max_tokens":
            raise Failed("too_long")
        uses = [block for block in response.content if block.type == "tool_use"]
        if not uses:
            return "".join(block.text for block in response.content if block.type == "text").strip()
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for use in uses:
            if stopped():
                return ""
            results.append(_result(use, call, prompt))
        if all(
            isinstance(prompt.tools.get(use.name), Choice) and not result.get("is_error")
            for use, result in zip(uses, results, strict=True)
        ):
            return ""
        messages.append({"role": "user", "content": results})
    raise Failed("too_many_steps")
