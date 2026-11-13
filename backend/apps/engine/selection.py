"""SUMIF, SUMIFS, COUNTIF and COUNTIFS compiled (D22). A criterion known when compiling is a test
SQL puts to each cell. Where one is computed for each cell compiled, the cells the function reads
are read once and each set of criteria the cells compiled compute is totalled in one sweep over
them in their order, a cell's number added to every set selecting it in one array operation: each
set takes its numbers in the order SUM adds them, so its total is Excel's to the last bit, for
the cells times the sets, which a query for each set would pay many times over."""

import itertools
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, replace

import numpy as np

from . import criteria, formats
from .collation import collation
from .formats import Language
from .sql import (
    NUMBER,
    UNKNOWN,
    VALUE,
    Range,
    Scope,
    Typed,
    Unsupported,
    known_key,
    matching,
    text_literal,
    value,
)
from .values import BLANK, CANCELS, Error

# A total that cancels is below CANCELS of the larger of the term and the total before it, which
# is at most the term and the total together: under twice CANCELS of the term.
NEAR = 2 * CANCELS
SPANS = {
    ">": np.less,
    ">=": np.less_equal,
    "<": np.greater,
    "<=": np.greater_equal,
    "<>": lambda codes, found: ~np.isin(codes, found),
}
# The key of no value: a comparison with nothing selects nothing.
NOTHING = "-"


def selected(scope: Scope, target: Range, pairs: list[tuple[Range, Typed]], counting: bool):
    """The total of the numbers of the target's cells the criteria of the pairs select
    (statistical.selected_numbers), or with `counting` their count; NULL where SQL cannot tell
    whether a cell that would change it is selected, or an error is."""
    for area, _ in pairs:
        if (area.height, area.width) != (target.height, target.width):
            raise Unsupported("#VALUE!")
    beyond = target.height * target.width - target.extent[0] * target.extent[1] if counting else 0
    if beyond and any(
        area.extent[0] > target.extent[0] or area.extent[1] > target.extent[1] for area, _ in pairs
    ):
        raise Unsupported("criteria reaching past the cells counted")
    if beyond and not all(
        criteria.criterion(given.known, scope.language)(BLANK)
        for _, given in pairs
        if given.known is not UNKNOWN
    ):
        beyond = 0
    joins = []
    tests = []
    read = []
    computed = []
    for at, (area, given) in enumerate(pairs):
        v = f"coalesce(c{at}.v, 'null'::jsonb)"
        joins.append(f"LEFT JOIN {area.source} AS c{at} ON c{at}.y = t.y AND c{at}.x = t.x")
        if given.known is not UNKNOWN:
            tests.append(f"({matching(given, scope.language)(v)})")
            continue
        if area.moves or target.moves:
            raise Unsupported("a criterion computed over an area moving")
        read.append(v)
        computed.append(given)
    matched = " AND ".join(tests) or "true"
    source = f"{target.source} AS t {' '.join(joins)}"
    if computed:
        return _swept(scope, source, matched, read, computed, counting, beyond)
    if counting:
        return Typed(
            f"(SELECT CASE WHEN bool_or(({matched}) IS NULL) THEN NULL "
            f"ELSE count(*) FILTER (WHERE {matched})::float8 + {beyond} END FROM {source})",
            NUMBER,
        )
    total = (
        f"engine_total(CASE WHEN ({matched}) AND jsonb_typeof(t.v) = 'number' "
        "THEN (t.v)::float8 END ORDER BY t.y, t.x)"
    )
    error = (
        "(array_agg(t.v ORDER BY t.y, t.x) "
        f"FILTER (WHERE ({matched}) AND jsonb_typeof(t.v) = 'object'))[1]"
    )
    unknown = f"bool_or(({matched}) IS NULL AND jsonb_typeof(t.v) IN ('number', 'object'))"
    return Typed(
        f"(SELECT CASE WHEN {unknown} THEN NULL ELSE coalesce({error}, to_jsonb({total})) END "
        f"FROM {source})",
        VALUE,
    )


def _swept(
    scope: Scope,
    source: str,
    matched: str,
    read: list[str],
    computed: list[Typed],
    counting: bool,
    beyond: int,
) -> Typed:
    parts = [value(given) for given in computed]
    origins = [value(replace(given, sql=scope.origin(given.sql))) for given in computed]
    sets = [
        text
        for (text,) in scope.read(
            f"SELECT DISTINCT to_jsonb(q.v)::text FROM ({scope.each(_array(origins))}) AS q "
            "WHERE array_position(q.v, NULL) IS NULL"
        )
    ]
    if counting:
        target, relevant = "NULL, NULL", "true"
    else:
        target, relevant = _typed("t.v"), "jsonb_typeof(t.v) IN ('number', 'object')"
    rows = scope.read(
        f"SELECT {target}, {matched}, {', '.join(_typed(v) for v in read)} FROM {source} "
        f"WHERE ({matched}) IS DISTINCT FROM false AND {relevant} ORDER BY t.y, t.x"
    )
    cells = [
        (_value(row[0], row[1]), row[2], *map(_value, row[3::2], row[4::2], strict=True))
        for row in rows
    ]
    found = sweep(cells, sets, counting, scope.language, beyond)
    totals = f"{text_literal(json.dumps(found, ensure_ascii=False))}::jsonb"
    if counting:
        return scope.bound(
            parts, lambda names: Typed(f"({totals} -> {_set(names)})::float8", NUMBER)
        )
    return scope.bound(parts, lambda names: Typed(f"({totals} -> {_set(names)})", VALUE))


def _array(parts: list[Typed]) -> str:
    return f"ARRAY[{', '.join(each.sql for each in parts)}]"


def _set(parts: list[Typed]) -> str:
    """The text of the jsonb array of the criteria of a cell, NULL where one is."""
    held = " AND ".join(f"{each.sql} IS NOT NULL" for each in parts)
    return f"CASE WHEN {held} THEN to_jsonb({_array(parts)})::text END"


def _typed(v: str) -> str:
    """A jsonb value as columns Python reads without decoding JSON: the number, or else the
    letter of its kind and its text."""
    return (
        f"CASE WHEN jsonb_typeof({v}) = 'number' THEN ({v})::float8 END, "
        f"CASE jsonb_typeof({v}) WHEN 'string' THEN 's' || ({v} #>> '{{}}') "
        f"WHEN 'boolean' THEN 'b' || ({v})::text WHEN 'object' THEN 'r' || ({v} ->> 'error') END"
    )


def _value(number: float | None, text: str | None):
    if number is not None or text is None:
        return number
    if text[0] == "s":
        return text[1:]
    if text[0] == "b":
        return text == "btrue"
    return Error(text[1:])


@dataclass
class _Frame:
    """Sets alike but for the values their comparisons are with, at `start` to `stop` of the
    totals, in the order of the values of the first comparison (`ranks` of each one's place)."""

    start: int
    stop: int
    tests: tuple[tuple[str, str], ...]
    compared: list[int]
    ranks: dict[int, np.ndarray]


def sweep(cells: list[tuple], sets: list[str], counting: bool, language: Language, beyond: int = 0):
    """The total of each set of criteria, as the text of a jsonb array of them, over cells in
    their order, each the target's value, whether the criteria known select it (None where SQL
    could not tell) and the values the computed criteria test, and counting, `beyond` empty
    places the criteria known select after them; the first error a set selects where it selects
    one, and nothing for a set that selects a cell SQL could not tell it selects, nor one the
    sweep cannot test."""
    tested = _tested(sets, language)
    rows, errors_met = _terms(cells, counting, tested, beyond)
    terms = [term for term, _ in rows if isinstance(term, float)]
    if any(0 < abs(term) < sys.float_info.min for term in terms):
        return {}
    read = _Reader(language)
    texted_at = {
        at for found in tested.values() for at, (_, kind, _) in enumerate(found) if kind == "s"
    }
    texts = {operand for found in tested.values() for _, kind, operand in found if kind == "s"}
    texts.update(given[at] for _, given in rows for at in texted_at if isinstance(given[at], str))
    if not read.ordered(texts):
        return {}
    codes: dict[str, int] = {}
    for found in tested.values():
        for op, _, operand in found:
            if op == "<>":
                codes.setdefault(operand, len(codes))
    order, frames, keyed_at = _framed(tested, codes, read)
    cancelling = any(term < 0 for term in terms) and any(term > 0 for term in terms)
    totals = np.zeros(len(order))
    errors = np.zeros(len(order), np.int64)
    with np.errstate(all="ignore"):
        for term, given in rows:
            keys = dict.fromkeys(range(len(given)), ())
            for at in keyed_at:
                keys[at] = read.keys(given[at])
            for frame in _met(frames, keys):
                for span in _reach(frame, given, keys, codes, read):
                    if isinstance(term, int):
                        _changed(errors, span, _first, term)
                    else:
                        _changed(totals, span, _add, term, cancelling)
    out = {}
    for text, total, error in zip(order, totals.tolist(), errors.tolist(), strict=True):
        if math.isnan(total):
            continue
        if error:
            out[text] = {"error": errors_met[-1 - error]}
        elif math.isfinite(total):
            out[text] = total
    return {} if read.odd else out


def _tested(sets: list[str], language: Language) -> dict[str, list]:
    """The tests of each set of criteria the sweep can test, each criterion read once."""
    tested = {}
    tests: dict = {}
    for text in sets:
        found = []
        for each in json.loads(text):
            held = (type(each), json.dumps(each)) if isinstance(each, dict) else (type(each), each)
            if held not in tests:
                tests[held] = _test(each, language)
            found.append(tests[held])
        if None not in found:
            tested[text] = found
    return tested


def _terms(
    cells: list[tuple], counting: bool, tested: dict[str, list], beyond: int
) -> tuple[list[tuple], list[str]]:
    """Each cell's term and the values the computed criteria test: NaN where SQL could not tell
    whether the criteria known select it, 1 counting, an error by -1 less its place among the
    errors met, else the target's value; and those errors."""
    errors_met: list[str] = []
    rows = []
    for target, known, *given in cells:
        if known is None:
            term = math.nan
        elif counting:
            term = 1.0
        elif isinstance(target, Error):
            if target.value not in errors_met:
                errors_met.append(target.value)
            term = -1 - errors_met.index(target.value)
        else:
            term = target
        rows.append((term, given))
    if beyond and tested:
        rows.append((float(beyond), [None] * len(next(iter(tested.values())))))
    return rows, errors_met


def _framed(
    tested: dict[str, list], codes: dict[str, int], read: _Reader
) -> tuple[list[str], dict, set[int]]:
    """The sets in the order of their totals, their frames by the places of their equalities and
    those equalities' keys, and the places whose values are keyed."""

    def ranked(test: tuple[str, str, object]):
        op, kind, operand = test
        if op == "<>":
            return codes[operand]
        return read.texts[operand] if kind == "s" else operand

    alike = defaultdict(list)
    for text, found in tested.items():
        alike[
            tuple((op, kind) for op, kind, _ in found),
            tuple(operand if op == "=" else None for op, _, operand in found),
        ].append(text)
    order: list[str] = []
    frames: dict[tuple[int, ...], dict[tuple[str, ...], list[_Frame]]] = defaultdict(dict)
    keyed_at = set()
    for (kinds, keys), held in alike.items():
        compared = [at for at, (op, _) in enumerate(kinds) if op != "="]
        if compared:
            held.sort(key=lambda text: ranked(tested[text][compared[0]]))
        start = len(order)
        order.extend(held)
        ranks = {at: np.array([ranked(tested[text][at]) for text in held]) for at in compared}
        equal = tuple(at for at, (op, _) in enumerate(kinds) if op == "=")
        keyed_at.update(at for at, (op, _) in enumerate(kinds) if op in ("=", "<>"))
        frames[equal].setdefault(tuple(keys[at] for at in equal), []).append(
            _Frame(start, len(order), kinds, compared, ranks)
        )
    return order, frames, keyed_at


def _met(frames: dict, keys: dict[int, tuple]):
    """The frames whose equalities a cell's keys meet."""
    for equal, keyed in frames.items():
        for combination in itertools.product(*(keys[at] for at in equal)):
            yield from keyed.get(combination, ())


def _test(given, language: Language) -> tuple[str, str, object] | None:
    """A criterion as the sweep tests it: "=" or "<>", "k" and the key of the values it matches
    or all but matches; or a comparison, the kind of value it compares with ("n" a number, "s"
    a text, "b" a logical) and that value, a number by its rank; None for any other."""
    match given:
        case None:
            return "=", "k", known_key(0.0)
        case bool():
            return "=", "k", known_key(given)
        case int() | float():
            return "=", "k", known_key(float(given))
        case str():
            op, written = criteria.split(given)
            if op in ("", "=", "<>"):
                return _equality(op or "=", written, language) if op or written else None
            if written == "":
                return "=", "k", NOTHING
            match criteria.operand(written, language):
                case bool() as found:
                    return op, "b", float(found)
                case float() as found:
                    return None if rank(found) is None else (op, "n", rank(found))
                case str() as found:
                    return op, "s", found
    return None


def _equality(op: str, written: str, language: Language) -> tuple[str, str, str] | None:
    """A criterion that matches the cells equal to one value, or all but them
    (criteria.criterion), as _test gives it."""
    if written == "":
        return op, "k", "e"
    found = criteria.operand(written, language)
    if isinstance(found, Error):
        return None
    if isinstance(found, str):
        found = criteria.literal(found)
    key = None if found is None else _key(found, language)
    return None if key is None else (op, "k", key)


def _reach(
    frame: _Frame, given: list, keys: dict, codes: dict[str, int], read
) -> list[tuple[int, int, np.ndarray | None]]:
    """The totals of the frame a cell's values select: spans of them from start to stop, each
    only where its mask holds where it has one."""
    size = frame.stop - frame.start
    spans = [(0, size)]
    tests = []
    for n, at in enumerate(frame.compared):
        op, kind = frame.tests[at]
        ranks = frame.ranks[at]
        if op == "<>":
            found = sorted(codes[key] for key in keys[at][:1] if key in codes)
        else:
            found = read.ranked(kind, given[at])
            if found is None:
                return []
        if n:
            tests.append((SPANS[op], ranks, found))
            continue
        match op:
            case ">":
                spans = [(0, int(np.searchsorted(ranks, found, "left")))]
            case ">=":
                spans = [(0, int(np.searchsorted(ranks, found, "right")))]
            case "<":
                spans = [(int(np.searchsorted(ranks, found, "right")), size)]
            case "<=":
                spans = [(int(np.searchsorted(ranks, found, "left")), size)]
            case "<>":
                spans, start = [], 0
                for code in found:
                    spans.append((start, int(np.searchsorted(ranks, code, "left"))))
                    start = int(np.searchsorted(ranks, code, "right"))
                spans.append((start, size))
    out = []
    for start, stop in spans:
        if start >= stop:
            continue
        mask = None
        for holds, ranks, found in tests:
            held = holds(ranks[start:stop], found)
            mask = held if mask is None else mask & held
        out.append((frame.start + start, frame.start + stop, mask))
    return out


def _changed(array: np.ndarray, span: tuple[int, int, np.ndarray | None], change, *given):
    """The change made in place to the places of the array a span holds."""
    start, stop, mask = span
    change(array[start:stop], *given, True if mask is None else mask)


def _first(errors: np.ndarray, code: int, where) -> None:
    np.copyto(errors, code, where=(errors == 0) & where)


def _add(totals: np.ndarray, term: float, cancelling: bool, where) -> None:
    """The term added in place to each of the totals where `where` holds, as values.total adds
    it."""
    np.add(totals, term, out=totals, where=where)
    if not cancelling:
        return
    near = np.abs(totals) < abs(term) * NEAR
    if where is not True:
        near &= where
    near = np.flatnonzero(near)
    if near.size:
        found = totals[near]
        # A total that near 0 came of a term and a total before it within a factor of two of each
        # other, whose sum is exact: subtracting the term gives that total back exactly.
        before = found - term
        cancels = ((before < 0) != (term < 0)) & (
            np.abs(found) < np.maximum(np.abs(before), abs(term)) * CANCELS
        )
        totals[near[cancels]] = 0.0


def rank(number: float) -> float | None:
    """A number ordered and held equal as Excel compares numbers, by its fifteen significant
    digits; None for one too small for those to tell numbers apart (formats.significant)."""
    if 0 < abs(number) < sys.float_info.min:
        return None
    return float(f"{number:.15g}")


class _Reader:
    """The values of cells as the sweep tests them, each read once; `odd` once one was a number
    it cannot rank."""

    def __init__(self, language: Language):
        self.language = language
        self.odd = False
        self._keys: dict = {}
        self._ranks: dict[float, float | None] = {}
        self.texts: dict[str, float] = {}

    def keys(self, given) -> list[str]:
        if isinstance(given, Error):
            return []
        found = self._keys.get((type(given), given))
        if found is None:
            found = self._keys[type(given), given] = self._keyed(given)
        return found

    def _keyed(self, given) -> list[str]:
        match given:
            case None:
                return ["e"]
            case bool() | float():
                return [known_key(given)]
        found = cell_keys(given, self.language)
        self.odd |= found is None
        return found or []

    def ranked(self, kind: str, given) -> float | None:
        """The rank of a cell's value among those a comparison of its kind compares with; None
        for a value of another kind, which it never selects."""
        match kind:
            case "n":
                if not isinstance(given, float):
                    return None
                if given not in self._ranks:
                    self._ranks[given] = rank(given)
                    self.odd |= self._ranks[given] is None
                return self._ranks[given]
            case "b":
                return float(given) if isinstance(given, bool) else None
        return self.texts.get(given) if isinstance(given, str) else None

    def ordered(self, texts) -> bool:
        """Ranks the texts as values.compare orders them, False where no ranks can
        (Collation.ranks)."""
        found = collation(self.language.code).ranks(texts)
        if found is None:
            return False
        self.texts = found
        return True


def cell_keys(given: str, language: Language) -> list[str] | None:
    """The keys of the criteria a text in a cell matches: its own and that of the number it
    reads as; None for a text no key holds (Collation.equality)."""
    own = _key(given, language)
    if own is None:
        return None
    keys = [own]
    found = formats.read(given, language)
    if found is not None:
        keys.append(known_key(found))
    return keys


def _key(given, language: Language) -> str | None:
    if not isinstance(given, str):
        return known_key(given)
    found = collation(language.code).equality(given)
    return None if found is None else "s" + found.hex()
