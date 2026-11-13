"""Excel's number format codes as Microsoft defines them, the domain the engine is held to Excel
over (D22): the ABNF of [MS-XLS] 2.4.126 (Format), written in each document language as that
section asks after ECMA-376 Part 1, 18.8.31 (the language's decimal mark, group separator, date
separator, letters of a date's parts and name of General, as Application.International tells
them), with the characters 18.8.31 shows without a backslash among its literals and a [$-tag]
naming a language of the suite, the system's long date or time, or a currency sign.

`valid` tells whether a code is in the domain; one outside it is not held to Excel. `drawn`
derives codes from the grammar at random, `covering` draws until each choice the grammar offers
has been made three times and each pair of the choices that make a code's first section has met.
`write` (excel.py's part grammar) writes, for each language, grammar-<language>-codes.xlsx, TEXT
of each code written in the language over VALUES, two values drawn and a text, which excel.py has
Excel compute and save as grammar-<language>.xlsx, and grammar-opened-<nn>-<language>-codes.xlsx,
cells of a few values in each canonical code and Excel's built-in ones, CODES_PER_BOOK to a file,
which Excel opens under the language's regional format, saving what each cell shows as
grammar-opened-<nn>-<language>-shown.csv; a code Excel refuses to open a file in (REFUSED) is left
out, so a new sample's codes are first each opened in a book of its own. What Excel saved is kept
in grammar/ beside this module.

SAMPLES names the samples by their seeds. One drawn after the engine was last changed and
computed by Excel before anyone looked at it tells how much of the domain the engine still
writes otherwise: none of its 3000 codes in any language puts that below 1 in 1000 with 95 %
confidence (3/n)."""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cache, lru_cache
from itertools import combinations
from pathlib import Path
from random import Random

from openpyxl import Workbook

from apps.engine import formats
from apps.engine.tests.saved import BUILT_IN, LANGUAGES

# Where Excel misreads the code it compiled, it writes no rule's result, so those codes are not
# held. The marks of the morning and the afternoon before an elapsed hour with neither an hour nor
# those marks after it turn what follows into other marks, a literal too (en AM/PM[h]s writes 0 as
# AM12/, AM/PM[h]dd as AM120, AM/PM[h].0 as AM1219000.5, A/P[h]\x as A120). Of three sections or
# more with a condition on the first, a number the condition leaves out goes to the second section
# instead of the third where the compiled sections fall in some lengths alone, which no weight of
# ours tells (en [=5]0;"b"0;0.00E+00 writes 6 as b6, [=5]0;"b"0;0E+0 as 6E+0), so no such number
# is held, nor a negative one whose opposite the condition leaves out, which a first section that
# rounds the number to nothing writes as that opposite ([<=480.77]0,,,;0;0.0A/P writes -1234,5678
# as 1235, [<=480.77]0,,,;0;0A/P as 1235P). A cell in a section holding General writes an elapsed
# count of more than 256 digits with what lies past Excel's buffer after them (en [m]General
# shows 4E+252 as 256 digits and 4E+252, 4E+253 as 256 digits, memory and 4E+253).
MISREAD_NOON = re.compile(r"(?i)(?:AM/PM|A/P).*?\[h+\](.*)")
MISREAD_LATER = re.compile(r"(?i)h|AM/PM|A/P")
MISREAD_QUOTED = re.compile(r'"[^"]*"|[\\_*].')
MISREAD_ELAPSED = re.compile(r"(?i)\[(h+|m+|s+)\]")
MISREAD_COUNTED = {"h": 24, "m": 1440, "s": 86400}
MISREAD_DIGITS = 256

LONGEST = 255
# The codes Excel refuses to open a file in, one a line, though it takes each from a cell's format
# setter or in TEXT and MS-OI29500 2.1.712 names the same grammar for a file: measured, a book of
# each code, as no rule of the grammar sets them apart.
REFUSED = Path(__file__).with_name("grammar") / "refused.txt"
SHOWN_LITERALLY = frozenset("$-+/():!^&'~{}<>= ")
COLOURS = ("Black", "Blue", "Cyan", "Green", "Magenta", "Red", "White", "Yellow")
COLOURS_NUMBERED = 56
OPERATORS = ("<", "<=", "<>", "=", ">", ">=")
NOONS = ("AM/PM", "A/P")
# The languages of the suite by their Windows locale ids, and the system's long date and time: a
# [$-tag] naming another locale, whose names and calendars Windows keeps for it, is out of the
# domain.
LOCALE_IDS = ("409", "809", "41A", "407", "40C", "410", "C0A", "F800", "F400")
SIGNS = ("€", "$", "£", "kn", "CHF", "EUR", "USD")
QUOTABLE = "abcxyzABCXYZ 0123456789.,;:/-+$€%#?@()[]\\*_čšž'"
ESCAPABLE = QUOTABLE + '"'
COVERED = 3
COVERING = 20261030
SAMPLES = {
    "development": 1,
    "round 15": 862065051,
    "round 16": 694025528,
    "round 17": 209516276,
    "round 18": 143860694,
    "round 19": 501122178,
    "round 20": 406564178,
    "round 21": 664588671,
    "round 22": 873924334,
    "round 23": 500495772,
}
SAMPLED = 3000
# Each code over these, two values drawn and a text in TEXT; in cells over the first three, one
# drawn and the text.
VALUES = ("0", "1", "-1", "0.5", "-0.5", "1234.5678", "-1234.5678", "0.001234", "123456789.123")
VALUES += ("46000.5432",)
# About the integer widths Excel counts a fraction's parts in.
VALUES += tuple(
    format(2**width + Decimal(offset), "f")
    for width in (15, 16, 31, 32)
    for offset in ("-1.4", "-0.5", "0.6")
)
CELLED = ("1234.5678", "-1234.5678", "0")
DRAWN_VALUES = 2
TEXT = "abc"
# Excel holds between 200 and 250 number formats in a workbook, by its language (Excel
# specifications and limits); 150 kept in each of implied's has never been refused.
CODES_PER_BOOK = 150
LETTERS = {"y": "year", "M": "month", "d": "day", "h": "hour", "m": "minute", "s": "second"}

type Token = tuple
type Code = tuple[tuple[Token, ...], ...]


# Recognising a code: each section's tokens, each a set of the roles the grammar may give it,
# then the section's rule read with every place each rule may end at kept, so that a mark with
# more than one role (French space, Croatian point, the slash) is tried in each at no more cost.


def _bracketed(inner: str, language: str) -> frozenset[str] | None:
    codes = formats.CODES[language]
    number = rf"-?\d+(?:{re.escape(formats.marks(language)[0])}\d+)?(?:E[+-]\d+)?"
    if inner in COLOURS or re.fullmatch(r"Color(?:[1-9]|[1-4]\d|5[0-6])", inner):
        return frozenset({"colour"})
    if re.fullmatch(rf"(?:<[=>]?|=|>=?){number}", inner):
        return frozenset({"condition"})
    if inner.startswith("$") and len(inner) > 1:
        found = re.fullmatch(r".*-0*([0-9A-Fa-f]{3,8})", inner[1:])
        if found and found.group(1).upper() not in LOCALE_IDS:
            return None
        return frozenset({"tag"})
    for letter, role in ((codes.hour, "[h]"), (codes.minute, "[m]"), (codes.second, "[s]")):
        if inner and set(inner) == {letter}:
            return frozenset({role})
    return None


def _letters(language: str) -> dict[str, frozenset[str]]:
    codes = formats.CODES[language]
    found: dict[str, frozenset[str]] = {}
    for role, part in LETTERS.items():
        letter = getattr(codes, part)
        found[letter] = found.get(letter, frozenset()) | {role}
    return found


def _roles(char: str, language: str) -> frozenset[str]:
    decimal, group = formats.marks(language)
    found = {"#": {"#"}, "?": {"?"}, "0": {"0", "digit"}, "%": {"%"}, "@": {"@"}}.get(char, set())
    found = set(found)
    if char.isdigit() and char.isascii():
        found.add("digit")
    for role, mark in ((".", decimal), (",", group), ("date", formats.day_mark(language))):
        if char == mark:
            found.add(role)
    if char == "/":
        found.add("/")
    if char == ":":
        found.add("time")
    if char in SHOWN_LITERALLY:
        found.add("literal")
    return frozenset(found)


def _lexed(code: str, language: str) -> list[list[frozenset[str]]] | None:
    """The code's sections as the roles of their tokens, or None where a character has none."""
    general = formats.CODES[language].general
    letters = _letters(language)
    literal = frozenset({"literal"})
    sections: list[list[frozenset[str]]] = [[]]
    at = 0
    while at < len(code):
        char, tokens = code[at], sections[-1]
        if char == ";":
            sections.append([])
            at += 1
        elif char == '"':
            end = code.find('"', at + 1)
            if end <= at + 1:
                return None
            tokens.append(literal)
            at = end + 1
        elif char in "\\*_":
            if at + 1 == len(code):
                return None
            tokens.append(literal)
            at += 2
        elif char == "[":
            end = code.find("]", at + 1)
            roles = _bracketed(code[at + 1 : end], language) if end > at else None
            if roles is None:
                return None
            tokens.append(roles)
            at = end + 1
        elif char == "E" and code[at + 1 : at + 2] in ("+", "-"):
            tokens.append(frozenset({"E"}))
            at += 2
        elif word := next((w for w in (general, *NOONS) if code.startswith(w, at)), None):
            tokens.append(frozenset({"general" if word == general else "noon"}))
            at += len(word)
        elif char in letters:
            end = at
            while end < len(code) and code[end] == char:
                end += 1
            if letters[char] == {"y"} and (end - at) % 2:
                return None
            tokens.append(letters[char])
            at = end
        elif roles := _roles(char, language):
            tokens.append(roles)
            at += 1
        else:
            return None
    return sections


type Rule = tuple
SKIPPED = frozenset({"literal", "tag"})


def _is(role: str) -> Rule:
    return ("is", role)


def _seq(*rules: Rule) -> Rule:
    return ("seq", rules)


def _alt(*rules: Rule) -> Rule:
    return ("alt", rules)


def _star(rule: Rule) -> Rule:
    return ("star", rule)


_EMPTY: Rule = ("seq", ())


def _opt(rule: Rule) -> Rule:
    return _alt(_EMPTY, rule)


def _plus(rule: Rule) -> Rule:
    return _seq(rule, _star(rule))


class _Machine:
    """A rule as an automaton over the roles of tokens: a state for each token a rule takes,
    where any run of literals and tags may follow, as either may stand between any two of the
    grammar's elements; read a token at a time through the sets of states reached, each step
    kept once taken."""

    def __init__(self, rule: Rule):
        self.moves: list[list[tuple[str, int]]] = []
        self.free: list[list[int]] = []
        self.skips: list[bool] = []
        start = self._state(skips=True)
        self.end = self._built(rule, start)
        self.start = self._closed({start})
        self.steps: dict[tuple[frozenset[int], frozenset[str]], frozenset[int]] = {}

    def _state(self, skips: bool = False) -> int:
        self.moves.append([])
        self.free.append([])
        self.skips.append(skips)
        return len(self.moves) - 1

    def _built(self, rule: Rule, start: int) -> int:
        match rule:
            case ("is", role):
                end = self._state(skips=True)
                self.moves[start].append((role, end))
                return end
            case ("seq", rules):
                for each in rules:
                    start = self._built(each, start)
                return start
            case ("alt", rules):
                end = self._state()
                for each in rules:
                    opening = self._state()
                    self.free[start].append(opening)
                    self.free[self._built(each, opening)].append(end)
                return end
            case ("star", each):
                loop = self._state()
                self.free[start].append(loop)
                self.free[self._built(each, loop)].append(loop)
                return loop
        raise ValueError(rule)

    def _closed(self, states: set[int]) -> frozenset[int]:
        found, fresh = set(states), list(states)
        while fresh:
            for state in self.free[fresh.pop()]:
                if state not in found:
                    found.add(state)
                    fresh.append(state)
        return frozenset(found)

    def holds(self, tokens: list[frozenset[str]]) -> bool:
        states = self.start
        for token in tokens:
            key = (states, token)
            if (after := self.steps.get(key)) is None:
                reached = {state for state in states if self.skips[state] and token & SKIPPED}
                reached.update(
                    end for state in states for role, end in self.moves[state] if role in token
                )
                after = self.steps[key] = self._closed(reached)
            if not after:
                return False
            states = after
        return self.end in states


def _with(token: Rule, also: Rule) -> Rule:
    """1*token *(token / also) / *(token / also) 1*token, as NFPartNum, NFPartFraction and
    NFText are written."""
    either = _alt(token, also)
    return _alt(_seq(_plus(token), _star(either)), _seq(_star(either), _plus(token)))


_TOKEN_1 = _alt(_is("#"), _is("?"), _is("0"))
_TOKEN_2 = _alt(_TOKEN_1, _is("."), _is(","))
_PART_NUM = _with(_TOKEN_2, _is("%"))
_NUMBER = _seq(_PART_NUM, _opt(_seq(_is("E"), _PART_NUM)), _star(_is(",")), _star(_is("noon")))
_PART_FRACTION = _alt(_with(_plus(_is("digit")), _is("%")), _with(_TOKEN_1, _is("%")))
_FRACTION = _seq(_PART_FRACTION, _is("/"), _PART_FRACTION, _opt(_PART_NUM), _star(_is("noon")))
_DATE_TIME_TOKEN = _alt(*(_is(role) for role in (*LETTERS, "[h]", "[m]", "[s]")))
_SUB_SECOND = _seq(_is("."), _is("0"), _opt(_is("0")), _opt(_is("0")))
_DATE_TIME = _seq(
    _star(_is("noon")),
    _plus(_DATE_TIME_TOKEN),
    _star(_alt(_DATE_TIME_TOKEN, _SUB_SECOND, _is("date"), _is("time"), _is("noon"))),
)
_GENERAL = _is("general")
_TIMED = _seq(_opt(_DATE_TIME), _opt(_GENERAL), _opt(_DATE_TIME))
_TEXT = _with(_is("@"), _is("noon"))
_COLOUR, _CONDITION = _opt(_is("colour")), _opt(_is("condition"))
_ANY = _seq(
    _COLOUR,
    _alt(_seq(_CONDITION, _NUMBER), _TEXT, _seq(_CONDITION, _FRACTION), _seq(_CONDITION, _TIMED)),
)
_NO_TEXT = _seq(_COLOUR, _CONDITION, _alt(_NUMBER, _FRACTION, _TIMED))
_NO_CONDITION = _seq(_COLOUR, _alt(_NUMBER, _TEXT, _FRACTION, _TIMED))
_NO_TEXT_NO_CONDITION = _seq(_COLOUR, _alt(_NUMBER, _FRACTION, _TIMED))
_ALL = {
    count: tuple(_Machine(rule) for rule in rules)
    for count, rules in {
        1: (_alt(_seq(_COLOUR, _is("condition"), _GENERAL), _NO_CONDITION),),
        2: (_NO_TEXT, _ANY),
        3: (_NO_TEXT, _NO_TEXT, _NO_CONDITION),
        4: (_NO_TEXT, _NO_TEXT, _NO_TEXT_NO_CONDITION, _opt(_alt(_TEXT, _GENERAL))),
    }.items()
}


def _timed_alone(tokens: list[frozenset[str]]) -> bool:
    """At most one absolute time in each NFDateTime, none beside its unit's own token."""
    sides: list[list[frozenset[str]]] = [[]]
    for token in tokens:
        if "general" in token:
            sides.append([])
        else:
            sides[-1].append(token)
    for side in sides:
        absolute = [token for token in side if token & {"[h]", "[m]", "[s]"}]
        if len(absolute) > 1:
            return False
        for token in absolute:
            unit = next(iter(token))[1]
            if any(each == {unit} for each in side):
                return False
    return True


def _holds(tokens: list[frozenset[str]], machine: _Machine) -> bool:
    if sum("tag" in token for token in tokens) > 1 or not _timed_alone(tokens):
        return False
    return machine.holds(tokens)


def valid(code: str, language: str) -> bool:
    """Whether the code, written in the language as TEXT reads it (canonical in en), is one the
    grammar holds."""
    if not 1 <= len(code) <= LONGEST:
        return False
    sections = _lexed(code, language)
    if sections is None or len(sections) > len(_ALL):
        return False
    return all(map(_holds, sections, _ALL[len(sections)], strict=True))


# Drawing a code: a derivation of the grammar whose every choice is kept, by its point and the
# option taken, for `covering`; a choice of a code's first section is kept as a feature too.


@dataclass
class _Draw:
    random: Random
    made: set = field(default_factory=set)
    features: set = field(default_factory=set)

    def pick(self, point: str, options: dict, feature: bool = False):
        option = self.random.choices(tuple(options), weights=tuple(options.values()))[0]
        self.made.add((point, option))
        if feature:
            self.features.add((point, option))
        return option

    def chance(self, point: str, probability: float, feature: bool = False) -> bool:
        return self.pick(point, {True: probability, False: 1 - probability}, feature)

    def count(self, point: str, least: int, most: int) -> int:
        found = self.random.randint(least, most)
        self.made.add((point, min(found, least + 2)))
        return found


def _digits(draw: _Draw, most: int) -> str:
    return "".join(draw.random.choice("0123456789") for _ in range(draw.random.randint(1, most)))


def _with_also(draw: _Draw, point: str, tokens: list[Token], also: Token) -> list[Token]:
    """The tokens with `also` put among them, never both before the first and after the last."""
    if not draw.chance(f"{point} {also[0]}", 0.2):
        return tokens
    found = list(tokens)
    for _ in range(draw.count(f"{point} {also[0]}s", 1, 2)):
        found.insert(draw.random.randint(0, len(found)), also)
    if found[0] == also and found[-1] == also:
        found.pop()
    return found


def _part_num(draw: _Draw) -> list[Token]:
    weights = {"0": 35, "#": 25, "?": 10, ".": 15, ",": 15}
    count = draw.count("places", 1, 6)
    return _with_also(
        draw, "places", [(draw.pick("place", weights),) for _ in range(count)], ("%",)
    )


def _number(draw: _Draw) -> list[Token]:
    found = _part_num(draw)
    if draw.chance("exponent", 0.15):
        found += [("E", draw.pick("exponent sign", {"+": 3, "-": 1})), *_part_num(draw)]
    found += [(",",)] * (draw.count("scaled", 1, 3) if draw.chance("scaled", 0.1) else 0)
    if draw.chance("number noon", 0.03):
        found.append(("noon", draw.pick("noon", dict.fromkeys(NOONS, 1))))
    return found


def _part_fraction(draw: _Draw, point: str) -> tuple[list[Token], str]:
    kind = draw.pick(f"{point} kind", {"placeholders": 4, "digits": 1})
    if kind == "digits":
        tokens = [("digit", _digits(draw, 6)) for _ in range(draw.count(f"{point} numbers", 1, 2))]
    else:
        weights = {"?": 3, "#": 2, "0": 2}
        tokens = [(draw.pick(f"{point} place", weights),) for _ in range(draw.count(point, 1, 4))]
    return _with_also(draw, point, tokens, ("%",)), kind


def _fraction(draw: _Draw) -> list[Token]:
    found, kind = _part_fraction(draw, "numerator")
    # A whole part is placeholders the numerator's own part goes on after a space.
    if kind == "placeholders" and draw.chance("whole", 0.5):
        whole = [(draw.pick("whole place", {"#": 3, "0": 2, "?": 1}),)]
        whole *= draw.count("whole places", 1, 3)
        found = [*whole, ("ecma", " "), *found]
    found += [("/",), *_part_fraction(draw, "denominator")[0]]
    if draw.chance("after fraction", 0.05):
        found += _part_num(draw)
    if draw.chance("fraction noon", 0.03):
        found.append(("noon", draw.pick("noon", dict.fromkeys(NOONS, 1))))
    return found


def _date_time(draw: _Draw) -> list[Token]:
    found: list[Token] = []
    if draw.chance("leading noon", 0.05):
        found.append(("noon", draw.pick("noon", dict.fromkeys(NOONS, 1))))
    absolute, units = False, set()
    lengths = {"y": (2, 4), "M": (1, 2, 3, 4, 5), "d": (1, 2, 3, 4), "h": (1, 2), "m": (1, 2)}
    lengths["s"] = (1, 2)
    for at in range(draw.count("date parts", 1, 6)):
        kinds = {"part": 6, "absolute": 0 if absolute else 1}
        if at:
            kinds |= {"date": 2, "time": 2, "sub second": 1, "noon": 1}
        kind = draw.pick("date token", kinds)
        if kind == "part":
            options = {part: 1 for part in LETTERS if f"[{part}]" not in units}
            part = draw.pick("date part", options)
            units.add(part)
            found.append((part, draw.pick(f"{part} length", dict.fromkeys(lengths[part], 1))))
        elif kind == "absolute":
            options = {unit: 1 for unit in "hms" if unit not in units}
            if not options:
                continue
            unit = draw.pick("absolute unit", options)
            absolute = True
            units.add(f"[{unit}]")
            found.append((f"[{unit}]", draw.count("absolute length", 1, 3)))
        elif kind == "sub second":
            found += [(".",), *[("0",)] * draw.count("sub second", 1, 3)]
        elif kind == "noon":
            found.append(("noon", draw.pick("noon", dict.fromkeys(NOONS, 1))))
        else:
            found.append((kind,))
    return found


def _timed(draw: _Draw) -> list[Token]:
    shape = draw.pick(
        "timed", {"date": 8, "general": 3, "date general": 1, "general date": 1, "empty": 1}
    )
    found: list[Token] = []
    for part in shape.split():
        found += [("general",)] if part == "general" else _date_time(draw) if part == "date" else []
    return found


def _text(draw: _Draw) -> list[Token]:
    found = [("@",)] * draw.count("ats", 1, 2)
    if draw.chance("text noon", 0.05):
        noon = ("noon", draw.pick("noon", dict.fromkeys(NOONS, 1)))
        found = [noon, *found] if draw.chance("noon first", 0.5) else [*found, noon]
    return found


BODIES = {"number": _number, "fraction": _fraction, "timed": _timed, "text": _text}


def _condition(draw: _Draw) -> Token:
    number = ("-" if draw.chance("condition minus", 0.25) else "") + _digits(draw, 5)
    if draw.chance("condition places", 0.3):
        number += "." + _digits(draw, 3)
    if draw.chance("condition exponent", 0.1):
        number += "E" + draw.pick("condition exponent sign", {"+": 1, "-": 1}) + _digits(draw, 2)
    return ("condition", (draw.pick("operator", dict.fromkeys(OPERATORS, 1), True), number))


def _colour(draw: _Draw) -> Token:
    if draw.pick("colour kind", {"named": 3, "numbered": 1}, True) == "named":
        return ("colour", draw.pick("colour", dict.fromkeys(COLOURS, 1)))
    return ("colour", f"Color{draw.random.randint(1, COLOURS_NUMBERED)}")


def _literal(draw: _Draw) -> Token:
    kind = draw.pick("literal", {"quoted": 3, "escaped": 2, "fill": 1, "space": 2, "ecma": 3})
    if kind == "quoted":
        return ("quoted", "".join(draw.random.choices(QUOTABLE, k=draw.random.randint(1, 4))))
    if kind == "ecma":
        return ("ecma", draw.random.choice(sorted(SHOWN_LITERALLY)))
    return (kind, draw.random.choice(ESCAPABLE))


def _tag(draw: _Draw) -> Token:
    kind = draw.pick("tag", {"language": 3, "sign": 1, "sign and language": 2}, True)
    sign = draw.random.choice(SIGNS) if "sign" in kind else ""
    language = "-" + draw.random.choice(LOCALE_IDS) if "language" in kind else ""
    return ("tag", sign + language)


def _section(draw: _Draw, slot: str, bodies: tuple[str, ...], condition: bool) -> list[Token]:
    first = slot == "1"
    weights = {"number": 5, "fraction": 2, "timed": 3, "text": 2}
    body = draw.pick(f"body {slot}", {kind: weights[kind] for kind in bodies}, first)
    found: list[Token] = []
    if draw.chance(f"colour {slot}", 0.15, first):
        found.append(_colour(draw))
    if condition and body != "text" and draw.chance(f"condition {slot}", 0.2, first):
        found.append(_condition(draw))
    found += BODIES[body](draw)
    for _ in range(draw.count("literals", 1, 3) if draw.chance(f"literals {slot}", 0.4) else 0):
        found.insert(draw.random.randint(0, len(found)), _literal(draw))
    if draw.chance(f"tag {slot}", 0.1, first):
        found.insert(draw.random.randint(0, len(found)), _tag(draw))
    return found


ALL = ("number", "fraction", "timed", "text")
NO_TEXT = ("number", "fraction", "timed")


def _code(draw: _Draw) -> Code:
    form = draw.pick("sections", {"general": 1, "1": 6, "2": 3, "3": 2, "4": 2}, True)
    if form == "general":
        colour = [_colour(draw)] if draw.chance("colour 1", 0.3) else []
        return ((*colour, _condition(draw), ("general",)),)
    if form == "1":
        return (tuple(_section(draw, "1", ALL, False)),)
    if form == "2":
        return (tuple(_section(draw, "1", NO_TEXT, True)), tuple(_section(draw, "2", ALL, True)))
    rest = [_section(draw, "2", NO_TEXT, True)]
    if form == "3":
        rest.append(_section(draw, "3", ALL, False))
    else:
        rest.append(_section(draw, "3", NO_TEXT, False))
        last = draw.pick("last", {"none": 1, "text": 3, "general": 1})
        rest.append(_text(draw) if last == "text" else [("general",)] if last == "general" else [])
    return tuple(map(tuple, (_section(draw, "1", NO_TEXT, True), *rest)))


def _written_token(token: Token, language: str) -> str:
    kind, *rest = token
    codes = formats.CODES[language]
    decimal, group = formats.marks(language)
    match kind:
        case "#" | "?" | "0" | "%" | "@" | "/":
            return kind
        case ".":
            return decimal
        case ",":
            return group
        case "date":
            return formats.day_mark(language)
        case "time":
            return ":"
        case "digit" | "ecma" | "noon":
            return rest[0]
        case "E":
            return "E" + rest[0]
        case "general":
            return codes.general
        case "y" | "M" | "d" | "h" | "m" | "s":
            return getattr(codes, LETTERS[kind]) * rest[0]
        case "[h]" | "[m]" | "[s]":
            return "[" + getattr(codes, LETTERS[kind[1]]) * rest[0] + "]"
        case "colour":
            return f"[{rest[0]}]"
        case "condition":
            operator, number = rest[0]
            return f"[{operator}{number.replace('.', decimal)}]"
        case "tag":
            return f"[${rest[0]}]"
        case "quoted":
            return f'"{rest[0]}"'
        case "escaped":
            return "\\" + rest[0]
        case "fill":
            return "*" + rest[0]
        case "space":
            return "_" + rest[0]
    raise ValueError(kind)


def written(code: Code, language: str) -> str:
    """The code as TEXT reads it in the language; in en, the canonical code a cell keeps."""
    return ";".join("".join(_written_token(token, language) for token in each) for each in code)


def _drawn(draw: _Draw) -> Code:
    while True:
        code = _code(draw)
        if written(code, "en"):
            for language in LANGUAGES:
                text = written(code, language)
                if not valid(text, language):
                    raise AssertionError(f"drawn outside the grammar in {language}: {text!r}")
            return code


@cache
def drawn(seed: int, count: int) -> list[Code]:
    draw = _Draw(Random(seed))
    return [_drawn(draw) for _ in range(count)]


@cache
def covering(seed: int = COVERING) -> list[Code]:
    """Codes drawn until each choice made in any has been made COVERED times and each pair of
    the features of a first section has met, the draws adding to neither left out."""
    random, made, met, found, idle = Random(seed), {}, set(), [], 0
    while idle < 2000:
        draw = _Draw(random)
        code = _drawn(draw)
        pairs = set(combinations(sorted(draw.features, key=repr), 2))
        fresh = {each for each in draw.made if made.get(each, 0) < COVERED} | (pairs - met)
        if fresh:
            found.append(code)
            for each in draw.made:
                made[each] = made.get(each, 0) + 1
            met |= pairs
            idle = 0
        else:
            idle += 1
    return found


def _value(random: Random) -> str:
    """A number as a formula writes it, its 15 significant digits at most read alike by Excel
    and Python: a whole number, a fraction, one ending in a half, a date with its time, or one
    of a large or small exponent."""
    sign = "-" if random.random() < 0.3 else ""
    shape = random.random()
    digits = str(random.randrange(1, 10 ** random.randint(1, 15)))
    if shape < 0.2:
        return sign + digits
    if shape < 0.6:
        if shape >= 0.45:
            digits = digits[:-1] + "5" if len(digits) > 1 else "5"
        return sign + format(Decimal(digits).scaleb(-random.randint(1, len(digits) + 3)), "f")
    if shape < 0.85:
        day = str(random.randrange(2_958_466))
        return f"{sign}{day}.{random.randrange(10 ** (15 - len(day))):0{15 - len(day)}d}"
    exponent = random.randint(-300, 300)
    return f"{sign}{digits[0]}.{digits[1:] or '0'}E{exponent:+d}"


def _codes() -> list[Code]:
    return [*covering(), *(code for seed in SAMPLES.values() for code in drawn(seed, SAMPLED))]


def rows(language: str) -> list[tuple[str, str | None]]:
    """TEXT's code in the language and its value, None for the text, a row each, in order: the
    covering codes, then each sample's."""
    random = Random(COVERING)
    return [
        (written(code, language), value)
        for code in _codes()
        for value in (*VALUES, *(_value(random) for _ in range(DRAWN_VALUES)), None)
    ]


def workbook(language: str) -> Workbook:
    book = Workbook()
    sheet = book.active
    sheet.title = "TEXT"
    for y, (code, value) in enumerate(rows(language), start=1):
        given = f'"{TEXT}"' if value is None else value
        sheet.cell(y, 1, f'=TEXT({given},"{code.replace('"', '""')}")')
    return book


def built_in(language: str) -> list[str]:
    """Excel's built-in codes, each as a cell keeps it, the amounts' in the language."""
    money = (formats.built_in_money(id, None, language) for id in formats.MONEY_IDS)
    return [code or formats.CODES["en"].general for code in (*BUILT_IN.values(), *money)]


def opened(language: str) -> list[tuple[str, tuple[float | str, ...]]]:
    """Each canonical code Excel opens a file in, its built-in ones first, with the values of the
    cells of its row: the numbers, then the text."""
    random = Random(COVERING)
    refused = set(REFUSED.read_text(encoding="utf-8").splitlines())
    return [
        (code, (*(float(value) for value in values), TEXT))
        for code in (*built_in(language), *(written(each, "en") for each in _codes()))
        for values in ((*CELLED, _value(random)),)
        if code not in refused
    ]


def books(language: str) -> dict[str, list[tuple[str, tuple[float | str, ...]]]]:
    """The rows of cells, CODES_PER_BOOK to a workbook, by the workbook's name."""
    rows = opened(language)
    return {
        f"grammar-opened-{n // CODES_PER_BOOK + 1:02d}": rows[n : n + CODES_PER_BOOK]
        for n in range(0, len(rows), CODES_PER_BOOK)
    }


def book(rows: list[tuple[str, tuple[float | str, ...]]]) -> Workbook:
    """A row of cells in each code, as a file brings them to Excel."""
    book = Workbook()
    sheet = book.active
    for y, (code, values) in enumerate(rows, start=1):
        for x, value in enumerate(values, start=1):
            sheet.cell(y, x, value).number_format = code
    return book


def write(folder: Path) -> None:
    for language in LANGUAGES:
        workbook(language).save(folder / f"grammar-{language}-codes.xlsx")
        for name, rows in books(language).items():
            book(rows).save(folder / f"{name}-{language}-codes.xlsx")


def misread(code: str, language: str, value=None, celled: bool = False) -> bool:
    """Whether Excel misreads the code, for the value where one is given, in a cell where celled."""
    noon, counted, condition = _misreading(code, language)
    if noon:
        return True
    numeric = isinstance(value, int | float) and not isinstance(value, bool)
    if celled and numeric and any(abs(value) * each >= 10**MISREAD_DIGITS for each in counted):
        return True
    if condition is None:
        return False
    if value is None:
        return True
    if not numeric:
        return False
    operator, bound = condition
    taken = {
        "<": lambda number: number < bound,
        "<=": lambda number: number <= bound,
        "<>": lambda number: number != bound,
        "=": lambda number: number == bound,
        ">": lambda number: number > bound,
        ">=": lambda number: number >= bound,
    }[operator]
    return not taken(value) or value < 0 and not taken(-value)


@lru_cache(maxsize=1024)
def _misreading(code: str, language: str) -> tuple[bool, tuple[int, ...], tuple[str, float] | None]:
    """What of the code misread looks at whatever the value, read once for the rows of a code:
    whether a section's hours after its AM/PM are misread, the count in a day of the elapsed
    unit of each section that also shows General, and the first section's condition where the
    code has three sections or more."""
    sections = MISREAD_QUOTED.sub("x", code).split(";")
    noon = False
    counted = []
    for section in sections:
        found = MISREAD_NOON.search(section)
        noon = noon or bool(found and found[1] and not MISREAD_LATER.search(found[1]))
        elapsed = MISREAD_ELAPSED.search(section)
        if elapsed and "general" in section.lower():
            counted.append(MISREAD_COUNTED[elapsed[1][0].lower()])
    point = formats.marks(language)[0]
    number = rf"-?\d+(?:{re.escape(point)}\d+)?(?:E[+-]\d+)?"
    found = re.search(rf"\[(<[=>]?|=|>=?)({number})\]", sections[0])
    if len(sections) < 3 or not found:
        return noon, tuple(counted), None
    return noon, tuple(counted), (found[1], float(found[2].replace(point, ".")))
