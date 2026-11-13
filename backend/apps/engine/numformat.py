"""Excel's number format codes (D22): a value as a code writes it, as the TEXT function and a
cell's format show it. A code is read with the decimal mark and group separator it was written
with: TEXT reads it with the document's language's, as Excel does in that language, a cell's
format is kept with the canonical ones. What it writes is in the document's language."""

import itertools
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from functools import cache

import icu

from . import formats
from .dates import calendar_day, day_of, hijri
from .values import VALUE, Error

CANONICAL = (".", ",")
ELAPSED_CODES = re.compile(r"\[(h+|m+|s+)\]", re.IGNORECASE)
NOON = re.compile(r"am/pm|a/p", re.IGNORECASE)
NOONS = ("am/pm", "a/p")
NOON_TOKENS = (("date", "am/pm"), ("date", "a/p"))
CONDITION = re.compile(r"\[(<=|>=|<>|<|>|=)(-?\d+)(?:([.,])(\d+))?(?:[eE]([+-]\d+))?\]")
COLOURS = re.compile(r"\[(?:black|blue|cyan|green|magenta|red|white|yellow|color(\d+))\]", re.I)
COLOURS_NUMBERED = 56
# Numerals of another script, which a language with none of its own writes as its digits.
NUMERALS = re.compile(r"\[DBNum[1-4]\]", re.IGNORECASE)
WEEKDAY_LEAST = 3
BUDDHIST = 543
# The calendars B1 and B2 write a date in, and the language of their names where no [$-tag]
# names one: the Gregorian in English and the tabular Hijri in Arabic, whatever the document's.
# One after a [$-tag] is none ([$-409]B2 writes the Gregorian date), and one after @ #VALUE!; a
# cell shows its date as though neither stood in its format.
ESCAPES = {"_": ("lit", " "), "*": ("lit", "")}
CALENDARS = {"1": ("gregorian", "en"), "2": ("hijri", "ar")}
LITERAL = set("$-+/():!^&'~{}<>= ")
SYSTEM_NAMES = {"x-sysdate": "date", "x-systime": "time"}
SYSTEM_IDS = {0xF800: "date", 0xF400: "time"}
ELAPSED = {"h": (24,), "m": (60, 24), "s": (60, 60, 24)}
TIMES = {"h": 0, "[h": 0, "n": 1, "[m": 1, "s": 2, "[s": 2}
# The number from which Excel writes no fraction without a whole part, 2147483646,5 being
# 2147483647/1 and 429496729,6 2147483648/5 but 2147483647 #VALUE!, and the largest count it
# writes over a denominator the code gives, 9877/8 but not 9876543/8.
FREE_MOST = 2**31 - 1
FIXED_MOST = 2**15 - 1
# Over such a denominator Excel rounds the count half up, a product under the half by at most TIED
# of it counting as the half (# ?/25 writes 1,38 as 1 10/25, its product 2,8e-16 of the half under
# it, # ?/10 7,55 as 7 5/10, 3,2e-16 under; closed.py's ties).
TIED = 3e-16
# A denominator the code gives is read in 16 bits: up to 32768 it is the denominator, 70000 being
# 4464, and any other takes the best fraction over as many places as it lacks of 2**16, seven at
# most (?/65535 writes 0,123 as 1/6    as ?/? would, ?/65534 as 8/65   , ?/40000 and ?/65536 π as
# 5419351/1725033, not the next convergent of eight). Either writes as many of the code's digits
# as the denominator has, spaces for the rest after a ? in the numerator (?/08 writes 0,5 as 4/0 ,
# #/65535 as 1/6). Six digits make the whole code #VALUE!. A run of placeholders too gives a
# denominator of seven places at most, writing it as the run's (√2 in 0/00000000 is
# 13250218/09369319, 1/2147483647 in ?/?????????? 0/1).
GIVEN_BITS = 2**16
PLACES_MOST = 7
GIVEN_LONGEST = 5
# The placeholders after a code's decimal mark, however they run and whatever stands between them,
# but for the exponent's: 127 at most, the whole code #VALUE! past them (0. and 128 of 0 is,
# 0. and 127 of 0 before E+000 is not).
DECIMALS_MOST = 127
# Where group marks follow a fraction Excel writes the number 10**256 times larger, a thousand times
# smaller for each mark (0,0001 in # ?/?, is 1 and 249 zeros, in # ?/?,, 1 and 246), and #VALUE!
# where the sign and the whole part outrun 255 characters with the code from the whole part to the
# end of the denominator's run; where the numerator opens at a decimal mark, with what parts it
# from the whole part but its first mark, the slash and the run's first place alone: 0 #/0, writes
# 1 and 250 zeros, 0 ./0, and 0 ./00, 1 and 252, 0 "x"./0, 1 and 251, a minus sign a digit less.
SCALED_UP = 256
SCALED_WIDTH = 255
# A fraction is laid out on a picture of its section, a character a token (_pictured): its
# placeholders, the digits a code gives, and each other literal as a character of the private use
# area, GROUPED standing for the group marks its whole part is written with.
HOLDERS = "0#?"
COUNTING = HOLDERS + "123456789"
EMPTY = {"0": "0", "?": " ", "#": ""}
PICTURED = 0xE000
GROUPED = "\uf8ff"
# The longest a number is written as, #VALUE! past it in TEXT and FIXED and a cell of #, and the
# longest text TEXT writes, where a cell shows any (TEXT(0,001;"# ??/??,") would be 257 long,
# TEXT(REPT("a";256);"@") 256).
SHOWN_LONGEST = 255
# What Excel keeps of a code, measured over x runs (closed.py, budgets and probes): a literal takes
# 3, a quoted text 2 and 2 a character, a run of one placeholder 2, a decimal mark 1, the sign of
# the currency of the language 1, quoted or bare in TEXT (en $, hr €; a cell's bare $ is a literal),
# and the last part only what it needs to begin, 3 or, after a literal, 4 less than its whole; a
# code past CODE_BUDGET is #VALUE!, as is one of more than CODE_LONGEST characters. No code of up to
# 81 characters reaches the budget, and past them the weights miss Excel by a few for codes of
# several sections.
CODE_BUDGET = 250
CODE_LONGEST = 255
CODE_START = 3
CODE_MERGED = 4
WEIGHTS = {"literal": 3, "digit": 2, "point": 1, "dollar": 1, "date": 1, "text": 1, "general": 1}
WEIGHTS |= {"exp": 4, "slash": 2, "condition": 6, "tag": 15, "symbol": 17, "noon": 11, "letter": 7}
# The digits a double rounds to: the 309 of its largest integer part and the places of the longest
# code.
EXACT = 309 + 255


@dataclass
class Section:
    tokens: list = field(default_factory=list)
    condition: tuple[str, float] | None = None
    language: str | None = None
    system: str | None = None
    calendar: tuple[str, str] | None = None

    def has(self, kind: str) -> bool:
        return any(token[0] == kind for token in self.tokens)

    def dated(self) -> bool:
        return self.has("date") or self.has("places")

    def general(self) -> bool:
        """Whether the section writes General and nothing beside it (""General does)."""
        return self.has("general") and all(
            token in (("general",), ("lit", "")) for token in self.tokens
        )


def shown(value, code: str, locale: str, written: str | None = None) -> str | Error:
    """The value as the code writes it: a number, a date as its serial number, or text; a code
    written in a language (TEXT's) with its letters, marks and name of General, else canonical,
    as a cell's is."""
    sections = _sections(code, written, locale)
    if sections is None:
        return VALUE
    if isinstance(value, str):
        if len(sections) < 4 and not sections[-1].has("text"):
            return value
        section = sections[3] if len(sections) >= 4 else sections[-1]
        if any(token[2:] == ("noon",) for token in section.tokens):
            section = _noon(section, 0, locale)
        if section.system:
            # The system date or time the first section names ends the text section at its tag,
            # writing what stands before it and the tag's currency; a cell writes the text alone
            # where no literal stands before the tag (en [$-F800]0;"x"[$£]@ and @[$£]@ write abc
            # as x£ and abc£, a cell shows them as x£ and abc).
            at = next(at for at, token in enumerate(section.tokens) if token[2:] == ("tagged",))
            if written is None and not any(
                token[0] in ("lit", "fixed") for token in section.tokens[:at]
            ):
                return value
            section = Section(section.tokens[: at + 1])
        return _text(section, value, locale)
    chosen = _chosen(sections, value)
    if chosen is None:
        return VALUE
    first, second = sections[0], sections[1] if len(sections) > 1 else None
    if not first.tokens and first.condition is None and second and second.condition:
        # An empty first section leaves no section the number a later condition takes (;[<5]0
        # writes -1 and 0 as #VALUE!, 1 as nothing).
        if value <= 0 and _meets(value, second.condition):
            return VALUE
    if (
        value < 0
        and chosen[0]
        and (chosen[3] or chosen[0].system)
        and (chosen[0].system or chosen[0].dated())
    ):
        # A date or a time of day is never negative, whichever section takes the number (0;mm
        # and 0;ss write -1 as #VALUE!), the system's even taking it as its opposite (a cell in
        # 0%%?/[$-F800]00?;[<>9412]#?/000;[Green].00##% shows -7E-179 as ####); time elapsed
        # alone is, with its sign before all else where the section writes it, but for its
        # decimal places ("x"[h] writes -1 as -x24, [h];[m] as 1440, 0;[h].0 as #VALUE!).
        if chosen[0].system or any(
            token[0] == "places" or (token[0] == "date" and not token[1].startswith("["))
            for token in chosen[0].tokens
        ):
            return VALUE
    # A number written as its opposite would be is that opposite to the marks of the morning and
    # the afternoon too (en [<=480.77]0,,,;0;0A/P writes -1234,5678 as 1235P).
    given = value if chosen[3] else -value
    section, value, signed, _ = chosen
    if section is not None and section.system:
        # Excel takes the number by the section before the system's date or time stands for it,
        # so what the section cannot take is #VALUE! (en [$-F800]0/4 writes 5000 as the long date
        # and 10000 as #VALUE!, as 0/4 writes 10000), what it cannot lay out is not (en
        # [$-F800]? ./0 writes 0,5 as the long date, ? ./0 being #VALUE!).
        bare = replace(section, system=None)
        if isinstance(_placed(bare, value, signed, given, locale, laying=False), Error):
            return VALUE
        return _date(_sections(_systems(locale)[section.system], None, locale)[0], value, locale)
    found = _placed(section, value, signed, given, locale)
    if isinstance(found, str) and len(found) > SHOWN_LONGEST:
        # A cell writes a section holding General whole, TEXT not ([h]"y"General writes 4E+250 in
        # a cell as 252 digits, y and 4E+250, in TEXT as #VALUE!).
        if written is not None or section is None or not section.has("general"):
            return VALUE
    return found


def _placed(
    section: Section | None,
    value: float,
    signed: bool,
    given: float,
    locale: str,
    laying: bool = True,
) -> str | Error:
    """The number as the section _chosen gives writes it, in General where none does."""
    if section is None:
        return formats.numeral(value, _marks(locale)[0], formats.GENERAL)
    if section.dated():
        shown = _date(section, abs(value), locale)
        return "-" + shown if value < 0 and isinstance(shown, str) else shown
    if section.has("text") and not section.has("digit"):
        # A number is written in General alone, whatever stands about the text (@"B1" writes 5
        # as 5, "abc" as abcB1).
        return formats.numeral(value, _marks(locale)[0], formats.GENERAL)
    if section.has("general"):
        # The sign stands before all else, as a number's does (en (General writes -1 as -(1).
        return ("-" if signed and value < 0 else "") + _text(
            section, formats.numeral(abs(value), _marks(locale)[0], formats.GENERAL), locale
        )
    if not _counted(section):
        if any(token[2:] == ("noon",) for token in section.tokens):
            section = _noon(section, value, locale)
            if section is None or given < 0:
                return VALUE
        return ("-" if signed and value < 0 else "") + _text(section, "", locale)
    if any(token[2:] == ("noon",) for token in section.tokens):
        section = _noon(section, value, locale)
        if (
            section is None
            or given < 0
            and not signed
            or _number(section, given, True, locale) != _number(section, abs(given), False, locale)
        ):
            return VALUE
    return _number(section, value, signed, locale, laying)


def _counted(section: Section) -> bool:
    """Whether a number is placed in the section: by its placeholders, or as a fraction over a
    denominator given, whose count no placeholder writes (81/7 writes 81/7, -1 as -81/7, -0,04 as
    81/7 and 12345,6 is #VALUE!), or by an exponent alone (.E+. writes 0,5 as .E+1.)."""
    return (
        section.has("digit")
        or section.has("exp")
        or (section.has("slash") and section.has("fixed"))
    )


def _noon(section: Section, value: float, locale: str) -> Section | None:
    """The number section with the marks of the morning and the afternoon its value's time of day
    writes, the number's sign aside and before a percent or a group mark scales it (en 0??00,A/P
    writes -0,5 as 0  00P, 32767,5 as 0  33P); None past a date's last day, and #VALUE! too for
    a negative number a section writes without its sign or with its sign showing (2147483646,6
    in 0??00,A/P, -0,5 in 0%AM/PM, -1 in 0;0#A/P and in 0;00,A/P are #VALUE!)."""
    days, ticks = divmod(_ticks(abs(value), 1), 86_400)
    if day_of(days) is None:
        return None
    afternoon = ticks >= 43_200
    marks = _names(section.language or locale, None, section.language is not None)["ampm"]
    return replace(
        section,
        tokens=[
            (
                (
                    "lit",
                    marks[afternoon]
                    if token[1].lower() == "am/pm" or section.language
                    else token[1][2 * afternoon],
                )
                if token[2:] == ("noon",)
                else token
            )
            for token in section.tokens
        ],
    )


@cache
def celled(code: str, locale: str) -> str:
    """The code a cell shows its value in: the built-in short date (id 14) and date with time
    (id 22) are the language's short date (hr d.m.yyyy, en m/d/yyyy), the built-in dates with a
    month's name (ids 15 to 17) parted by the language's marks for them, their day and the hour of
    the built-in times (ids 20 to 22) with a leading zero where Windows writes one (en-GB
    01-Feb, 09:05), as Excel shows them; TEXT keeps those codes as written."""
    hour = "hh" if formats.LONG_TIMES[locale].lower().startswith("hh") else "h"
    if code in (formats.DAY_MONTH_YEAR, formats.DAY_MONTH, formats.MONTH_YEAR):
        day = "dd" if "dd" in formats.short_day(locale) else "d"
        after_day, before_year = formats.NAMED_MARKS[locale]
        return re.sub(r"^d-", day + after_day, code).replace("-", before_year)
    if code in (formats.CLOCK, formats.CLOCK_SECONDS):
        return hour + code[1:]
    if code not in (formats.SHORT_DATE, formats.MOMENT):
        return code
    day = _windows(formats.short_day(locale))
    return day if code == formats.SHORT_DATE else f"{day} {hour}:mm"


def _windows(pattern: str) -> str:
    """A date or a time as Windows writes its pattern, in Excel's code: M for the month, H for
    the hour of a whole day, tt for the morning's and the afternoon's marks and text quoted."""
    return pattern.replace("M", "m").replace("H", "h").replace("tt", "AM/PM").replace("'", '"')


@cache
def _systems(locale: str) -> dict[str, str]:
    return {
        "date": _windows(formats.LONG_DAYS[locale]),
        "time": _windows(formats.LONG_TIMES[locale]),
    }


def _tagged(tag: str) -> tuple[str | None, str | None]:
    """The language a [$-tag] names its months and days in, by the lower half of the Windows
    LCID it writes in hexadecimal, and the system date or time it stands for: F800 and
    x-sysdate the long date, F400 and x-systime the long time."""
    if found := SYSTEM_NAMES.get(tag.lower()):
        return None, found
    try:
        number = int(tag, 16) & 0xFFFF
    except ValueError:
        return None, None
    return _lcids().get(number), SYSTEM_IDS.get(number)


@cache
def _lcids() -> dict[int, str]:
    return {
        each.getLCID(): each.getLanguage()
        for each in icu.Locale.getAvailableLocales().values()
        if each.getLCID()
    }


def category(code: str) -> str:
    """The kind of a format, by its first section, as Excel sorts its formats: general, text,
    date (a day, a month or a year in it), time, scientific, fraction, percent, currency (a
    currency sign in its text) or number."""
    sections = _sections(code, None, None) if code else None
    if sections is None:
        return "general"
    section = sections[0]
    dates = [token[1] for token in section.tokens if token[0] == "date"]
    if dates:
        return "date" if any(each[:1] in "ymdegb" for each in dates) else "time"
    if not section.has("digit"):
        return "text" if section.has("text") else "general"
    if section.has("exp"):
        return "scientific"
    if section.has("slash"):
        return "fraction"
    literals = [token for token in section.tokens if token[0] == "lit"]
    if any(token[2:] == ("percent",) for token in literals):
        return "percent"
    if any(unicodedata.category(each) == "Sc" for token in literals for each in token[1]):
        return "currency"
    return "number"


def _marks(locale: str) -> tuple[str, str]:
    return formats.marks(locale)


@cache
def _letters(written: str | None) -> dict[str, str]:
    """The canonical letter of each letter a code written in the language names a part of a date
    by, in either case: n for the minute where its letter is the month's in the other case (German
    M and m), and e in small letters alone, as an E with no sign after it is no code."""
    codes = formats.CODES[written or "en"]
    found = {"e": "e"}
    for canonical, letter in (
        ("y", codes.year),
        ("m", codes.month),
        ("d", codes.day),
        ("h", codes.hour),
        ("s", codes.second),
        ("a", codes.weekday),
        ("g", codes.era),
        ("b", "b"),
    ):
        found[letter.lower()] = found[letter.upper()] = canonical
    if codes.minute != codes.month:
        found[codes.month], found[codes.minute] = "m", "n"
    return found


def _spent(weights: list[tuple[int, str | None]]) -> int:
    if not weights:
        return 0
    *before, (weight, kind) = weights
    if kind == "section":
        need = 0
    elif kind == "merged":
        need = CODE_START
    else:
        merged = before and before[-1][1] == "literal"
        need = max(CODE_START, weight - CODE_MERGED if merged else weight)
    return 1 + sum(each for each, _ in before) + need


class _Refused(Exception):
    """A code Excel takes for none."""


class _Lexer:
    """A code read into the tokens of its sections, with each token's weight against
    CODE_BUDGET, the sections a colour or a condition marks and the place after the last of
    those marks."""

    def __init__(self, code: str, written: str | None, locale: str | None):
        self.code = code
        self.written = written
        self.point, self.group = formats.marks(written) if written else CANONICAL
        self.sign = formats.currency_sign(locale) if locale else None
        self.letters = _letters(written)
        self.general = formats.CODES[written or "en"].general.lower()
        self.sections = [Section()]
        self.weights: list[tuple[int, str | None]] = []
        self.marked: set[int] = set()
        self.fence: tuple[int, int] | None = None

    @property
    def tokens(self) -> list:
        return self.sections[-1].tokens

    def read(self) -> list[Section]:
        at = 0
        while at < len(self.code):
            at = self._next(at)
        return self.sections

    def _next(self, at: int) -> int:
        code, each = self.code, self.code[at]
        if each == ";":
            self.sections.append(Section())
            self.weights.append((0, "section"))
            return at + 1
        if each == '"':
            end = code.find('"', at + 1)
            end = len(code) if end < 0 else end
            quoted = code[at + 1 : end]
            self.tokens.append(("lit", quoted))
            self.weights.append(
                (WEIGHTS["dollar"], None)
                if quoted == self.sign
                else (2 + 2 * len(quoted), "literal")
            )
            return end + 1
        if each in "\\_*" and at + 1 < len(code):
            self.tokens.append(ESCAPES[each] if each != "\\" else ("lit", code[at + 1], "escaped"))
            self.weights.append((WEIGHTS["literal"], "literal"))
            return at + 2
        if each == "[":
            end = code.find("]", at)
            end = len(code) - 1 if end < 0 else end
            self._bracket(code[at : end + 1])
            return end + 1
        if code[at : at + len(self.general)].lower() == self.general:
            self.tokens.append(("general",))
            self.weights.append((WEIGHTS["general"], None))
            return at + len(self.general)
        if self._placed(each):
            return at + 1
        if (end := self._worded(at)) is not None:
            return end
        self._other(each)
        return at + 1

    def _bracket(self, inside: str) -> None:
        sections, tokens = self.sections, self.tokens
        if found := CONDITION.fullmatch(inside):
            if len(sections) > 2:
                raise _Refused
            # A bound's places count after the language's decimal mark alone (hr [<0.5] is
            # [<0], [<=-0.5] [<=0]).
            places = f".{found[4]}" if found[3] == self.point else ""
            power = f"e{found[5]}" if found[5] else ""
            sections[-1].condition = (found[1], float(found[2] + places + power))
            self.weights.append((WEIGHTS["condition"], None))
            self._mark()
        elif ELAPSED_CODES.fullmatch(inside):
            tokens.append(("date", inside.lower()))
        elif NUMERALS.fullmatch(inside):
            pass
        elif inside.startswith("[$"):
            symbol, _, tag = inside[2:-1].partition("-")
            tokens.append(("lit", symbol, "tagged"))
            self.weights.append((WEIGHTS["symbol" if symbol else "tag"], None))
            sections[-1].language, sections[-1].system = _tagged(tag)
        elif not (found := COLOURS.fullmatch(inside)) or not (
            found[1] is None or 1 <= int(found[1]) <= COLOURS_NUMBERED
        ):
            raise _Refused
        else:
            self._mark()

    def _mark(self) -> None:
        self.marked.add(len(self.sections) - 1)
        self.fence = (len(self.sections), len(self.tokens))

    def _placed(self, each: str) -> bool:
        """A placeholder, a decimal or group mark, a percent or the text's place."""
        tokens, weights = self.tokens, self.weights
        before = tokens[-1] if tokens else None
        if each in "0#?":
            tokens.append(("digit", each))
            weights.append((0, "merged") if before == ("digit", each) else (WEIGHTS["digit"], None))
        elif each == self.point:
            tokens.append(("point", each))
            weights.append((WEIGHTS["point"], None))
        elif each == self.group:
            parted = self.fence == (len(self.sections), len(tokens)) and before
            parted = parted and before[0] == "group"
            tokens.append(("group", each, "parted") if parted else ("group", each))
            numeric = before and before[0] in ("digit", "point", "group")
            weights.append((0, "merged") if numeric else (WEIGHTS["literal"], None))
        elif each == "%":
            tokens.append(("lit", "%", "percent"))
            weights.append((WEIGHTS["literal"], "literal"))
        elif each == "@":
            tokens.append(("text",))
            weights.append((WEIGHTS["text"], None))
        else:
            return False
        return True

    def _worded(self, at: int) -> int | None:
        """An exponent, a calendar, the marks of the morning and the afternoon or a run of a
        date's letters, and the place after it; None for none of them."""
        code, each = self.code, self.code[at]
        tokens, weights = self.tokens, self.weights
        if each in "eE" and at + 1 < len(code) and code[at + 1] in "+-":
            tokens.append(("exp", code[at + 1]))
            weights.append((WEIGHTS["exp"], None))
            return at + 2
        if each in "nNE":
            raise _Refused
        if each in "Bb" and code[at + 1 : at + 2] in CALENDARS:
            if any(token[0] == "text" for token in tokens):
                raise _Refused
            if self.sections[-1].language is None and self.written is not None:
                self.sections[-1].calendar = CALENDARS[code[at + 1]]
            tokens.append(("calendar",))
            weights.append((WEIGHTS["literal"], None))
            return at + 2
        if found := NOON.match(code, at):
            tokens.append(("date", found[0].lower(), found[0]))
            weights.append((WEIGHTS["noon" if len(found[0]) > len("A/P") else "letter"], None))
            return found.end()
        if letter := self.letters.get(each):
            return self._lettered(at, letter)
        return None

    def _lettered(self, at: int, letter: str) -> int:
        code, tokens, weights = self.code, self.tokens, self.weights
        end = at + 1
        # The name of General ends a run of its first letter (de sStandard is s and General),
        # the marks of the morning and the afternoon a run of the year's (fr aaaaA/P is aaaa
        # and A/P).
        while (
            end < len(code)
            and self.letters.get(code[end]) == letter
            and code[end : end + len(self.general)].lower() != self.general
            and not NOON.match(code, end)
        ):
            end += 1
        run = code[at:end]
        if run == "B":
            raise _Refused
        if letter != "a":
            tokens.append(("date", letter * len(run)))
            weights.append((WEIGHTS["date"], None))
        elif len(run) < WEEKDAY_LEAST:
            tokens.extend(("lit", each) for each in run)
            weights.extend((WEIGHTS["literal"], "literal") for each in run)
        else:
            tokens.append(("date", "dddd" if len(run) > WEEKDAY_LEAST else "ddd"))
            weights.append((WEIGHTS["date"], None))
        return end

    def _other(self, each: str) -> None:
        tokens, weights = self.tokens, self.weights
        if each == "/":
            tokens.append(("slash", each))
            weights.append((WEIGHTS["slash"], None))
        elif each.isdigit():
            tokens.append(("fixed", each))
            weights.append((WEIGHTS["literal"], "literal"))
        elif self.written and each == self.sign:
            tokens.append(("lit", each))
            weights.append((WEIGHTS["dollar"], None))
        elif each != ":":
            tokens.append(("lit", each))
            weights.append((WEIGHTS["literal"], "literal"))
        elif not tokens or tokens[-1][2:] != ("colon",):
            tokens.append(("lit", each, "colon"))
            weights.append((WEIGHTS["literal"], "literal"))
        else:
            weights.append((0, "merged"))


@cache
def _sections(code: str, written: str | None, locale: str | None) -> tuple[Section, ...] | None:
    """The sections of a code, None where Excel takes it for no code (TEXT gives #VALUE!): an n,
    an E with no sign after it, a B alone, a bracket but for a condition, an elapsed time, a
    [$-tag], [DBNum1] to [DBNum4] and a colour, and a date or a fraction its marks or digits do
    not fit. A run of colons stands for one (en 0::x writes 1 as 1:x, #:: as 1:, h::hh 0:00,
    h":"::hh 0::00, 0\\:\\: 1::)."""
    if len(code) > CODE_LONGEST:
        return None
    lexer = _Lexer(code, written, locale)
    try:
        sections = lexer.read()
    except _Refused:
        return None
    if _spent(lexer.weights) > CODE_BUDGET:
        return None
    # A section of a colour or a condition alone writes General, one of nothing or of a [$-tag]
    # nothing (en [Red] writes -5 as -5, [>3];0 writes 5 as 5, ;0 and [$-409] as nothing).
    for each in lexer.marked:
        if not sections[each].tokens:
            sections[each].tokens.append(("general",))
    _languaged(sections)
    day = formats.day_mark(locale) if locale else "/"
    for at, section in enumerate(sections):
        if _refused(section, at == len(sections) - 1):
            return None
        if written is None and section.language == "ar":
            # A cell names in English what an Arabic [$-tag] names ([$-401]mmmm shows May,
            # [$-40C]B2mmmm mai).
            section.language = "en"
        timed = _timed(section.tokens)
        _nooned(section, timed)
        if section.has("date") or timed:
            section.tokens = _dated(section.tokens, written is not None)
        else:
            section.tokens = _numbered(section.tokens, lexer.group, written, day)
        if section.tokens is None:
            return None
    return tuple(sections)


def _languaged(sections: list[Section]) -> None:
    """The first section's [$-tag] names the language of the whole code, and there writes A/P
    as the marks of the morning and the afternoon in full, and a later section's system date or
    time counts only where the first names one, which a later section of any tag then writes,
    but a first section of text names neither (en mm/A/Phh[$-410] writes 0 as 01/AM12,
    General;0;mmm[$-41A] writes 0 as Jan, 0;[$-F800]#0 writes -1 as 1, [$-F400][>3]0;[$-F400]0
    0,5 as 12:00:00 PM, [$-F800]0;0;0[$£] and [$-F800][=5]0;[$-F400]0 0 as the long date,
    "x"A/P[$-409]@ writes abc as xAabc, [$-F400]@ 1 as 1)."""
    language, system = (
        (None, None) if sections[0].has("text") else (sections[0].language, sections[0].system)
    )
    for section in sections:
        section.language = language
        if system is None:
            section.system = None
        elif any(token[2:] == ("tagged",) for token in section.tokens):
            section.system = system


def _refused(section: Section, last: bool) -> bool:
    """Whether a section makes the whole code #VALUE!."""
    tokens = section.tokens
    if tokens[:1] == [("slash", "/")]:
        # A slash opening a section makes the whole code #VALUE!, text's too (0;/0.0 and
        # /AM/PM@ are, [ss]/;0 is not).
        return True
    slash = next((place for place, token in enumerate(tokens) if token[0] == "slash"), None)
    runs = _runs(tokens[slash + 1 :]) if slash is not None else []
    if runs and _given(runs[0]) and len(runs[0]) > GIVEN_LONGEST:
        return True
    point = next((place for place, token in enumerate(tokens) if token[0] == "point"), None)
    if point is not None:
        exponent = next(
            (place for place, token in enumerate(tokens) if token[0] == "exp"), len(tokens)
        )
        if sum(token[0] == "digit" for token in tokens[point + 1 : exponent]) > DECIMALS_MOST:
            return True
    clocked = next(
        (
            place
            for place, token in enumerate(tokens)
            if token[2:] == ("colon",) or token[:2] in NOON_TOKENS
        ),
        len(tokens),
    )
    # Text stands in the last section, with neither a digit nor a placeholder about it nor a
    # slash a colon or a noon has not made a literal nor a calendar but at its very start (@;@,
    # 1@, @0, @/, \B1@ and "x"B1@ are #VALUE!, B1@ and @:/ write the text).
    return section.has("text") and (
        not last
        or any(token[0] in ("fixed", "digit") for token in tokens)
        or any(token[0] == "slash" for token in tokens[:clocked])
        or (
            section.has("calendar")
            and next(token for token in tokens if token[:2] != ("lit", ""))[0] != "calendar"
        )
    )


def _nooned(section: Section, timed: bool) -> None:
    """The marks of the morning and the afternoon among placeholders, before a decimal mark or
    after digits write the value's time of day after its number, a run of them one in full (en
    0%AM/PM writes 0,5 as 50%PM, .A/P as 1.P, 0A/PA/P as 1PM, 75/589A/P as 75/589P, 1A/P1 is
    #VALUE!), about text the morning's (@A/P writes abc as abcA)."""
    dated = [token for token in section.tokens if token[0] == "date"]
    noon = next((at for at, token in enumerate(section.tokens) if token[0] == "date"), 0)
    fixed = section.has("fixed") and not any(token[0] == "fixed" for token in section.tokens[noon:])
    if not (
        (
            section.has("text")
            or (section.has("digit") or section.has("point") or fixed)
            and not timed
        )
        and all(token[1] in NOONS for token in dated)
    ):
        return
    noons = []
    for token in section.tokens:
        if token[0] != "date":
            noons.append(token)
        elif noons and noons[-1][2:] == ("noon",):
            noons[-1] = ("lit", "AM/PM", "noon")
        else:
            noons.append(("lit", token[2], "noon"))
    section.tokens = noons


def _timed(tokens: list) -> bool:
    """Whether a colon stands before the first decimal mark with nothing of a number before it,
    which makes that mark a time's (en :.0 writes 1,2345678 as :.7, :. and :.AM/PM 1 as :. and
    :.AM)."""
    point = next((at for at, token in enumerate(tokens) if token[0] == "point"), None)
    return (
        point is not None
        and any(token[2:] == ("colon",) for token in tokens[:point])
        and not any(token[0] in ("digit", "fixed", "text", "general") for token in tokens[:point])
    )


def _numbered(tokens: list, group: str, written: str | None, day: str) -> list | None:
    """The tokens of a number section: a digit written as it is (fr yyyy 2026 writes yyyy
    24632326), a decimal mark where no placeholder is as though a # stood before it, or before
    the group marks right after such a digit (en "x"."y" writes 5 as x5.y, 0 as x.y, 1,.A/P 1 as
    1.A), and an exponent after such a digit (1E+0 writes 1 as 1E+1), one group mark for a run
    of them where no placeholder is, none right after such a digit (fr B2dd dddd writes dd dddd,
    en ,, writes ,, 1,x 1x) and ahead of the first (,0 writes ,1235), and after the
    placeholders one apart from them by anything but decimal marks (fr 0, , writes 1234567 as
    1235,,), or one that is also a plain literal, French's space, right before the language's
    currency sign written plainly or quoted (fr 0 € writes 1235 €, 0 "K" 1K, 0 \\€ 1€). A group
    mark after the placeholders that a decimal mark follows apart by anything but group marks is
    dropped (hr 0. , and 0.x, write 1234567,891 as 1234568 , and 1234568x,); past the integer
    places one after a literal is a literal, among the decimal places too (en 0.x,0 writes
    1234567.x,9), and one right after a decimal mark scales the number wherever that mark stands
    (en 0.x., writes 1235.x.). After a colon or the marks of the morning and the afternoon a
    decimal mark and a slash are literals, the slash in a canonical code the language's date mark
    (en 0:/ writes 0,6 as 1:/, 0AM/PM/ as 1PM/, 0:., 1234 as 1234:.,; hr 0:/. in a cell writes 1
    as 1:.., fr as 1:/.); a fraction's tokens stand as they are, for _fraction to lay out. None
    for a fraction _framed takes for none or with an exponent (0E+0/0), for a calendar's B1 or B2
    among placeholders or after a slash (B10, 0 B2 and fr :/B1yy are #VALUE!),
    for a colon or the marks of the morning and the afternoon written plainly before a
    placeholder or a digit (#00:,0, :?0/?, ##0,.:0E+0, A/P0 and 1A/P.0 are #VALUE!, ?,#:,, and
    1A/P. are not), and for a slash with no placeholder or digit after it, a second
    slash or an exponent with no placeholder or decimal mark (00###/, General"c"/, ?/#/?,
    0/0#/#AM/PM and 0?E-, are #VALUE!, 0E+.%% is not); text's section takes a slash."""
    tokens = _readable(tokens, written, day)
    if tokens is None:
        return None
    if any(token[0] == "slash" for token in tokens) and not any(
        token[0] in ("text", "general") for token in tokens
    ):
        if any(token[0] == "exp" for token in tokens) or _framed(_pictured(tokens)[0]) is None:
            return None
        return tokens
    out = []
    for token in _point_held(tokens):
        if token[2:] == ("parted",):
            out += [("part",), token[:2]]
        else:
            out.append(("lit", token[1], "fixed") if token[0] == "fixed" else token)
    exp_at = next((at for at, token in enumerate(out) if token[0] == "exp"), len(out))
    if _exponent_grouped(out, exp_at):
        return None
    held = [at for at, token in enumerate(out[:exp_at]) if token[0] == "digit"]
    if not held:
        return _unplaced(out, exp_at)
    return _group_marks(out, exp_at, held[0], held[-1], group, written)


def _readable(tokens: list, written: str | None, day: str) -> list | None:
    """The tokens of a number section with what follows a colon or the marks of the morning and
    the afternoon made literals and its calendar taken out; None where they make no code."""
    ending = max(
        (at for at, token in enumerate(tokens) if token[0] in ("digit", "fixed")), default=0
    )
    if any(token[2:] in (("colon",), ("noon",)) for token in tokens[:ending]):
        return None
    calendar = next((at for at, token in enumerate(tokens) if token[0] == "calendar"), 0)
    if any(token[0] == "slash" for token in tokens[:calendar]):
        return None
    clock = next(
        (at for at, token in enumerate(tokens) if token[2:] in (("colon",), ("noon",))), None
    )
    if clock is not None:
        tokens = [
            *tokens[:clock],
            *(
                ("lit", day if token[0] == "slash" and written is None else token[1])
                if token[0] in ("slash", "point")
                else token
                for token in tokens[clock:]
            ),
        ]
    texted = any(token[0] == "text" for token in tokens)
    if not texted and sum(token[0] == "slash" for token in tokens) > 1:
        return None
    wanted = {"slash": () if texted else ("digit", "fixed"), "exp": ("digit", "point")}
    for at, token in enumerate(tokens):
        if wanted.get(token[0]) and not any(each[0] in wanted[token[0]] for each in tokens[at:]):
            return None
    if any(token[0] == "calendar" for token in tokens):
        if any(token[0] == "digit" for token in tokens):
            return None
        tokens = [token for token in tokens if token[0] != "calendar"]
    return tokens


def _point_held(tokens: list) -> list:
    """A decimal mark where no placeholder is held as though a # stood before it, or before the
    group marks right after a digit written as itself."""
    point = next((at for at, token in enumerate(tokens) if token[0] == "point"), None)
    if point is None or any(
        token[0] in ("digit", "text", "general", "slash", "exp") for token in tokens
    ):
        return tokens
    held = point
    while held and tokens[held - 1][0] == "group":
        held -= 1
    held = held if held and tokens[held - 1][0] == "fixed" else point
    return [*tokens[:held], ("digit", "#"), *tokens[held:]]


def _exponent_grouped(out: list, exp_at: int) -> bool:
    """Whether a group mark stands between placeholders after the exponent, with no decimal mark
    before it."""
    for at in range(exp_at + 1, len(out)):
        if out[at][0] != "group" or any(token[0] == "point" for token in out[:at]):
            continue
        prior = next(
            (
                token[0]
                for token in reversed(out[exp_at + 1 : at])
                if token[0] not in ("group", "part")
            ),
            None,
        )
        following = next(
            (token[0] for token in out[at + 1 :] if token[0] not in ("group", "part")), None
        )
        if prior == following == "digit":
            return True
    return False


def _unplaced(out: list, exp_at: int) -> list | None:
    """The tokens of a number section with no placeholder."""
    if exp_at < len(out) and not any(
        token[0] == "point" or token[2:] == ("fixed",) for token in out[:exp_at]
    ):
        return None
    return [
        ("lit", token[1]) if token[0] == "group" and at < exp_at else token
        for at, token in enumerate(out)
        if token[0] != "part"
        and not (token[0] == "group" and 0 < at < exp_at and out[at - 1][0] == "group")
        and not (token[0] == "group" and _pointed(out[:at]))
        and not (token[0] == "group" and at < exp_at and _figured(out[:at]))
    ]


def _group_marks(
    out: list, exp_at: int, first: int, last: int, group: str, written: str | None
) -> list:
    """The tokens of a number section with each group mark among its first and last
    placeholders, before and after them, grouping, scaling, written or dropped."""
    sign = formats.currency_sign(written) if written else None
    for at, token in enumerate(out[:exp_at]):
        if token[0] != "group":
            continue
        prior = next(
            (each[0] for each in reversed(out[:at]) if each and each[0] not in ("group", "part")),
            None,
        )
        following = next((each[0] for each in out[at + 1 : exp_at] if each[0] != "group"), None)
        # One mark stands for a run of them ahead of the placeholders or after a literal (en ,,0
        # writes ,1, 0.x,, 1234568.x,), a fill or a [$-tag] parting runs (\#,,*?,0 writes #,,1).
        run = next((each for each in reversed(out[:at]) if each), ())[2:] == ("grouped",)
        if 0 < at < first and _pointed(out[:at]):
            out[at] = (*token, "scale") if following == "point" and _scaling(out, at) else None
        elif at < first:
            out[at] = None if run else ("lit", token[1], "grouped")
        elif at > last and group in LITERAL and out[at + 1 : at + 2] == [("lit", sign)]:
            out[at] = ("lit", token[1])
        elif prior == "lit":
            out[at] = None if run else ("lit", token[1], "grouped")
        elif at < last and prior == "digit" and following == "part":
            # A colour or a condition between two runs of them ends the first, which scales the
            # number (en 0,[Red],0 writes 1234567,891 as 1,235, 0,,[Red]0 and 0,[Red]0 group).
            out[at] = (*token, "scale")
        elif at < last and following == "point":
            # Right before a decimal mark a placeholder or another mark follows they scale the
            # number (en #0,.0 writes 1 as 0.0, 0.,..# as 0...), else they are dropped (?,.%0
            # writes 1 as 1.%00).
            out[at] = (*token, "scale") if _scaling(out, at) else None
        elif at < last and (prior == "point" or following == "lit"):
            out[at] = None
        elif at > last and following == "point" and not _scaling(out, at):
            out[at] = None
        elif at > last and _apart(out[at + 1 : exp_at]):
            out[at] = None
    return [token for token in out if token is not None and token[0] != "part"]


def _scaling(out: list, at: int) -> bool:
    """Whether the group marks at a decimal mark scale the number: no placeholder or other mark
    follows anything else after that mark, group marks aside (en .,.? writes 1234567,891 as
    1234..6, ?,.,? as 1234.6, 0,.0.0 as 1234.5.7, .,."a" as 1234..a, .,."a"? as 1234567..a9,
    ?,."a". as 1234568.a., 0,.0"a"0 as 1234567.8a9, 0,.0 0 as 1234567.8 9)."""
    mark = next(each for each in range(at + 1, len(out)) if out[each] and out[each][0] != "group")
    after = [each[0] for each in out[mark + 1 :] if each and each[0] != "group"]
    rest = itertools.dropwhile(lambda kind: kind in ("digit", "point"), after)
    return not {"digit", "point"} & set(rest)


def _pointed(before: list) -> bool:
    """Whether a decimal mark stands right before, group marks aside."""
    last = next((each for each in reversed(before) if each and each[0] != "group"), None)
    return last is not None and last[0] == "point"


def _figured(before: list) -> bool:
    """Whether a digit written as itself stands right before, group marks aside."""
    last = next((each for each in reversed(before) if each and each[0] != "group"), None)
    return last is not None and last[2:] == ("fixed",)


def _apart(after: list) -> bool:
    point = next((at for at, token in enumerate(after) if token and token[0] == "point"), None)
    return point is not None and any(token and token[0] != "group" for token in after[:point])


def _counting(code: str) -> int:
    """The places an elapsed time writes at least: a clock's code taken for one at most two (en
    [m]hhh writes 0 as 012)."""
    return len(code.strip("[]")) if code.startswith("[") else min(len(code), 2)


def _dated(tokens: list, written: bool) -> list | None:
    """The tokens of a date section: marks written as they are, but for decimal places, which
    write the parts of a second wherever they stand, each to its own places of the most any of
    them has (en mmm.000 writes 1234,5678 as May.920, s.0.000 as 37.9.920), and a slash, which a
    code written in a language (TEXT's) writes as itself and a canonical one as the language's
    date mark, a run of group marks, which writes one (hr ss... writes 0 as 00.), a run
    of the marks of the morning and the afternoon, which writes one in full (en yyA/PA/P writes
    0,5 as 00PM), and
    the first m standing for minutes after an hour, again after each later hour, or a second no
    minute of the language's own letter came before, with no such minute between, or right
    before a second or decimal places, the marks of the morning and the afternoon and the
    language's own minutes aside, but never before an elapsed second (en mmhdddmm writes
    1234,5678 as 0513Mon37, A/Pmmd\\1mmAM/PMs as P0518137PM38, de MMmss as 373738, MmMs as
    5373738, m.00 as 37.92, m>s$mm as 37>38$05, mm:[ss] as 05:3319488, de [sss]m:MM as
    3855324:05, hmssMM as 13373805, MshsM as 3738133837), an elapsed minute, or one of the
    language's own letter after an elapsed second, leaving only the one after a later hour (en
    AM/PM[m]hm writes 0 as AM0120, AM/PM[m]ms as AM72010, s:[m]:m as 0:720:1, de [s]mM,0 as
    37139685,9). Of the hours,
    minutes and seconds about an elapsed time the largest counts the time elapsed and the
    others the clock's (en [ss]h writes 1234,5678 as 38922, [sss]m:mm as 3855324:05). None
    where a decimal mark or a slash comes before the first of its codes, a calendar's B1 or B2
    among them, but for a slash after a colon before any but a calendar (en x:/yy writes 1 as
    x:/00, :/B1yy is #VALUE!), a percent beside any but the marks of the morning and the
    afternoon (yy% and %:hh are #VALUE!, %:/A/P is not), a digit stands anywhere but in decimal
    places, a clock's hour, minute or second before an elapsed time of no larger a unit or the
    marks of the morning and the afternoon after one (en TT.MM.JJJJ, fr dd/mm/aaaa, ss,00, d 1
    m, h[s], hh:[mm], mm:.0dddd[s] and [h]AM/PM are #VALUE!, [mm]hh, mm.000[h] and AM/PM[h] are
    not, fr B1dd/mm/yyyy writes dd/10/yyyy)."""
    if any(token[2:] == ("percent",) for token in tokens) and any(
        token[0] == "date" and token[1] not in NOONS for token in tokens
    ):
        return None
    first = next((at for at, token in enumerate(tokens) if token[0] in ("date", "calendar")), None)
    clock = next((at for at, token in enumerate(tokens) if token[2:] == ("colon",)), len(tokens))
    calendar = next((at for at, token in enumerate(tokens) if token[0] == "calendar"), -1)
    if (
        first is not None
        and not _timed(tokens)
        and any(
            token[0] == "point" or token[0] == "slash" and (at < clock or at < calendar)
            for at, token in enumerate(tokens[:first])
        )
    ):
        return None
    out = []
    for at, token in enumerate(tokens):
        if token[0] == "calendar":
            continue
        if token[0] == "point":
            places = 0
            while at + 1 + places < len(tokens) and tokens[at + 1 + places] == ("digit", "0"):
                places += 1
            if places:
                out.append(("places", places))
                continue
        if token[0] == "digit":
            if not (out and out[-1][0] == "places"):
                return None
            continue
        if token[0] == "fixed":
            return None
        if token[0] == "slash":
            out.append(("lit", "/") if written else ("mark",))
            continue
        if token[0] == "group" and at and tokens[at - 1][0] == "group":
            continue
        if token[0] in ("point", "group"):
            out.append(("lit", token[1]))
            continue
        if token[0] == "date" and token[1] in NOONS and out and out[-1][:2] in NOON_TOKENS:
            out[-1] = ("date", "am/pm", "AM/PM")
            continue
        out.append(token)
    timing = [
        at
        for at, token in enumerate(out)
        if token[0] == "places" or token[0] == "date" and token[1] not in NOONS
    ]
    minute = timed = own = counted = second = False
    for place, at in enumerate(timing):
        if out[at][0] == "places":
            timed = timed or not counted | own
            continue
        code = out[at][1]
        if code in ("m", "mm"):
            ahead = next(
                (
                    out[each]
                    for each in timing[place + 1 :]
                    if out[each][0] == "places" or out[each][1][0] != "n"
                ),
                ("date", ""),
            )
            ahead = not counted and (ahead[0] == "places" or ahead[1].startswith("s"))
            prior = out[timing[place - 1]] if place else ("",)
            after = prior[0] == "date" and prior[1].startswith(("h", "[h"))
            if ahead or after or not minute and timed:
                out[at] = ("date", "n" * len(code))
                minute = True
        elif code.startswith("[m"):
            counted, timed = True, False
        elif code[0] == "n":
            timed, own, counted = False, True, counted or second
        elif code.startswith(("h", "[h")):
            timed, minute = True, False
        elif code.startswith(("s", "[s")):
            timed = timed or not own | counted
            second = second or code.startswith("[s")
    elapsed = next(
        (at for at, token in enumerate(out) if token[0] == "date" and token[1][0] == "["), None
    )
    if elapsed is None:
        return out
    if any(
        token[0] == "date"
        and (
            TIMES.get(token[1][0], 3) <= TIMES[out[elapsed][1][:2]]
            if at < elapsed
            else token[1] in NOONS
        )
        for at, token in enumerate(out)
    ):
        return None
    timed = [
        TIMES.get(token[1][:2], TIMES.get(token[1][0])) if token[0] == "date" else None
        for token in out
    ]
    largest = min(unit for unit in timed if unit is not None)
    return [
        token
        if unit is None
        else ("date", "[" + "hms"[unit] * _counting(token[1]) + "]")
        if unit == largest
        else ("date", "hns"[unit] * len(token[1].strip("[]")))
        for unit, token in zip(timed, out, strict=True)
    ]


def _chosen(sections: tuple[Section, ...], value: float):
    """The section a number is written by, the number as it writes it, and whether its sign
    is still to be shown. A section whose condition takes negative numbers alone writes the number
    without its sign (hr TEXT(-1234,5;"[<-100]0") is 1235, [<0]0 too, [<=0]0 -1235), and so does
    the section after the first where the first's condition compares to a bound of 0 or below by
    anything but = ([>0]0;0 and [<>-100]0;0 write -5 as 5, [=-100]0;0 and [>100]0;0 as -5).
    Where the first alone has a condition and two sections follow it, the second takes the
    negative numbers the first leaves, without their sign, and the third the rest ([>0]0;"x"0;"z"0
    writes -5 as x5 and 0 as z0, [<0]0;"x"0;"z"0 0,5 as z1). A negative number a section would
    round to nothing without its sign is written as its opposite would be (-0,4 in [<1]0 is 0, in
    [<=0]0 0,4 and in [<=0]0;"x"0;"z"0 z0, -0,5 in [<=0]0 -1). No section where a lone section's
    condition leaves the number out, which Excel writes in General as that second section would
    (-0,5 in [>100]0 is -0,5, -50 in [<-100]0 is 50), and None for #VALUE! where none of several
    sections takes it ([>100]0;[<-100]0 for 50); last, whether the number is still the one given,
    which a date writes where it rounds to nothing elsewhere (mmm;[<5]"x"0 writes -0,4 as Jan). A
    first section with no condition before one
    that has takes the positive numbers alone, the rest going on to the sections after it with
    their sign (0;[<5]"x"0 writes -1 as -x1, 0;[=5]0 0 as #VALUE!, 0;[=5]0;"z"0 -1 as -z1). A
    text section closing two or three takes no
    number: the sections before it take them all, and General none of them (0;@ writes -1 as -1,
    0;0;@ 0 as 0, [>59]General;@@ and [=5]0;@ write 1 as #VALUE!)."""
    found = _section(sections, value)
    if found and found[2] and value < 0 and _vanishes(found[0], value):
        condition = found[0].condition
        if len(sections) == 2 and condition and _negative(condition):
            return None
        opposite = _section(sections, -value)
        return opposite and (*opposite, False)
    return found and (*found, True)


def _section(sections: tuple[Section, ...], value: float):
    numbers = sections[:-1] if 1 < len(sections) < 4 and sections[-1].has("text") else sections[:3]
    first = numbers[0].condition
    texted = len(numbers) == 1 < len(sections)
    if any(section.condition for section in numbers):
        split = len(numbers) == 3 and numbers[1].condition is None is numbers[2].condition
        for at, section in enumerate(numbers):
            if at == 0 and first is None and value > 0:
                return section, value, True
            if section.condition is None:
                if at == 0:
                    continue
                if at == 1 and split and value >= 0:
                    continue
                bare = at == 1 and (split or _opposed(first))
                return section, abs(value) if bare else value, not bare
            if _meets(value, section.condition):
                negative = (
                    _negative(section.condition)
                    and not texted
                    and (len(numbers) > 1 or not section.general())
                )
                return section, abs(value) if negative else value, not negative
        if len(sections) > 1 or numbers[0].general():
            return None
        return None, abs(value) if _opposed(first) else value, True
    if value < 0 and len(numbers) >= 2:
        return numbers[1], -value, False
    if value == 0 and len(numbers) >= 3:
        return numbers[2], value, False
    return numbers[0], value, True


def _vanishes(section: Section | None, value: float) -> bool:
    if section is None or section.system or not _counted(section):
        return False
    if section.has("date") or section.has("general"):
        return False
    shown = _number(section, value, True, "en")
    return shown != VALUE and shown == _number(section, -value, True, "en")


def _negative(condition: tuple[str, float]) -> bool:
    op, limit = condition
    return (op == "<" and limit <= 0) or (op in ("<=", "=") and limit < 0)


def _opposed(condition: tuple[str, float] | None) -> bool:
    return condition is not None and condition[0] != "=" and condition[1] <= 0


def _meets(value: float, condition: tuple[str, float]) -> bool:
    op, limit = condition
    return {
        "<": value < limit,
        ">": value > limit,
        "=": value == limit,
        "<=": value <= limit,
        ">=": value >= limit,
        "<>": value != limit,
    }[op]


def _text(section: Section, text: str, locale: str) -> str:
    out = []
    for token in section.tokens:
        if token[0] == "lit":
            out.append(token[1])
        elif token[0] == "mark":
            out.append(formats.day_mark(locale))
        elif token[0] in ("text", "general"):
            out.append(text)
        elif token[0] == "fixed":
            out.append(token[1])
    return "".join(out)


def _number(section: Section, value: float, signed: bool, locale: str, laying: bool = True) -> str:
    point, group = _marks(locale)
    tokens = section.tokens
    exp_at = next((at for at, token in enumerate(tokens) if token[0] == "exp"), len(tokens))
    exponent = exp_at < len(tokens)
    if section.has("slash"):
        text = _fraction(tokens, value, signed, point, group, laying)
        return VALUE if text is None else text
    percents = 0 if exponent else sum(1 for token in tokens if token[2:] == ("percent",))
    value *= 100**percents
    point_at = next((at for at, token in enumerate(tokens[:exp_at]) if token[0] == "point"), None)
    whole = tokens[: point_at if point_at is not None else exp_at]
    places = tokens[point_at + 1 : exp_at] if point_at is not None else []
    digits = [at for at, token in enumerate(whole) if token[0] == "digit"]
    grouped = (
        any(token[0] == "group" for token in whole[digits[0] : digits[-1]]) if digits else False
    )
    held = [at for at, token in enumerate(tokens[:exp_at]) if token[0] == "digit"]
    scale = (
        0
        if exponent
        else sum(
            1
            for at, token in enumerate(tokens[:exp_at])
            if token[0] == "group" and (at > held[-1] or token[2:] == ("scale",))
        )
    )
    # Exactly, as a run of group marks scales past what a double holds, by a power of ten Excel
    # keeps in a signed byte (fr 0 and 253 spaces writes 1 as 1000000000, 254 as 1000000).
    value = float(Fraction(value) * Fraction(10) ** ((128 - 3 * scale) % 256 - 128))
    count = sum(1 for token in places if token[0] == "digit")
    if count + 2 * percents > DECIMALS_MOST:
        # Each percent takes two of the places Excel writes past the decimal mark: 0. and 126 of 0
        # before % writes 1 as 0.000…%, 125 of them as 100.000…%.
        value = 0.0
    negative = value < 0
    number = abs(value)
    power = None
    if exponent:
        # A group mark among the integer places steps the exponent by four places at least: hr
        # 0.00E+00 writes 0.000012345 as 1.235E-08, 0.0E+00 -0.004 as -40E-04 and 0.0000E+00
        # steps by five; without integer places the number is written below 1 (.00E+0 writes
        # 1234 as .12E+4), and without any places one that rounds to nothing as E+1 (,.E+0
        # writes 1234 as ,.E+1 but 65534.6 as ,.E+6).
        step = max(4 if grouped else 1, len(digits))
        if number == 0:
            power = 0
        elif digits:
            power = math.floor(math.log10(number) / step) * step
        else:
            power = math.floor(math.log10(number)) + 1
        top = Decimal(10) ** step if digits else 1
        mantissa = _rounded(number / 10.0**power, count)
        if mantissa >= top:
            power += step
            mantissa = _rounded(number / 10.0**power, count)
        elif number and not mantissa:
            power = 1
        number = mantissa
    else:
        number = _rounded(number, count)
    if not number and not (exponent and value):
        # Excel writes a negative number rounded to nothing without its sign: -0.4 in 0 is 0, in
        # # nothing, -0.5 in #,##0, 0 and in 0," K" 0 K; but for its exponent (-1234 in ,.E+0 is
        # -,.E+1).
        negative = False
    integer, _, fraction = f"{number:f}".partition(".")
    fraction = (fraction + "0" * count)[:count]
    integer = "" if integer == "0" or (exponent and not digits) else integer
    if power is not None and digits and not number:
        # Excel writes 0 by as many integer places as a step of the exponent takes (##0.0E+00
        # writes it 000.0E+00, #.##0E+00 0.0E+00 and hr #,##0E+00 0.000E+00).
        integer = "0" * step
    text = _whole(whole, integer, grouped, group)
    if point_at is not None:
        text += point + _places(places, fraction, point)
    if power is not None:
        text += _exponent(tokens[exp_at:], power, grouped, point, group)
    return ("-" if signed and negative else "") + text


def _rounded(number: float, places: int) -> Decimal:
    with localcontext(prec=EXACT):
        return Decimal(f"{number:.15g}").quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)


def _whole(tokens: list, integer: str, grouped: bool, group: str) -> str:
    """The integer part placed into its placeholders from the right, the leftmost taking the
    digits beyond them, literals between them staying where they are written; grouped, with a
    group mark before every third digit from the right (en # ##0,00 writes  1,235), a space where
    a ? keeps the place of the digit before it (en ??,??? writes 5 as five spaces and 5), a # that
    writes nothing counting as a place (en ?,?#0 writes 5 as three spaces and 5)."""
    holders = sum(1 for token in tokens if token[0] == "digit")
    pieces = []
    remaining = integer
    seen = 0
    for token in reversed(tokens):
        if token[0] == "lit":
            pieces.append((token[1], False))
            continue
        if token[0] != "digit":
            continue
        seen += 1
        if remaining and seen == holders:
            pieces.append((remaining, True))
            remaining = ""
        elif remaining:
            pieces.append((remaining[-1], True))
            remaining = remaining[:-1]
        else:
            pieces.append(({"0": "0", "?": " ", "#": ""}[token[1]], True))
    if not holders and remaining:
        pieces.insert(0, (remaining, True))
    out = []
    counted = 0
    for text, digits in pieces:
        if not (grouped and digits):
            out.append(text)
            continue
        if not text:
            counted += 1
        for each in reversed(text):
            if counted and counted % 3 == 0:
                out.append(" " if each == " " else group)
            out.append(each)
            counted += 1
    return "".join(reversed(out))


def _places(tokens: list, fraction: str, point: str) -> str:
    """The decimal places: a 0 always shows its digit, a # or ? only as far as the digits
    that are not trailing zeros, a ? keeping its place with a space, a second decimal mark
    written as the language's (en #.##0. writes 1234.568., 0.0.0 in a cell 1234,5,7 in hr)."""
    significant = len(fraction.rstrip("0"))
    out = []
    at = 0
    for token in tokens:
        if token[0] == "lit":
            out.append(token[1])
        elif token[0] == "point":
            out.append(point)
        elif token[0] == "digit":
            digit = fraction[at]
            if token[1] == "0" or at < significant:
                out.append(digit)
            elif token[1] == "?":
                out.append(" ")
            at += 1
    return "".join(out)


def _exponent(tokens: list, power: int, grouped: bool, point: str, group: str) -> str:
    """The exponent from its E: what stands before its first placeholder or decimal mark, then
    its sign, then the power placed into its integer placeholders as the integer part is, its
    units place writing a digit whatever it is (en 0E+# writes 0 as 0E+0, 0E+%0# 1234 as 1E%+03),
    grouped where the integer part is (#,#?E+00#%%,# writes 0,0%%,0), and written before a decimal
    mark where it has none (0E+.#"x" writes 1E+3.x). A decimal mark's places write 0 for a 0, a
    space for a ? and nothing for a #, a second mark itself (0E+..0 writes 1E+3..0); a group mark
    after a literal or before the first placeholder is written once however many stand together
    (0E+%,,0 writes 1 as 1E%,+0, 0E+,,0 as 1E,+0), any other dropped."""
    out = []
    for at, token in enumerate(tokens[1:], start=1):
        if token[0] != "group":
            out.append(token)
        elif tokens[at - 1][0] != "group" and (not out or out[-1][0] == "lit"):
            out.append(("lit", token[1]))
    first = next((at for at, token in enumerate(out) if token[0] in ("digit", "point")), len(out))
    point_at = next((at for at, token in enumerate(out) if token[0] == "point"), len(out))
    sign = "-" if power < 0 else ("+" if tokens[0][1] == "+" else "")
    text = "E" + "".join(token[1] for token in out[:first]) + sign
    text += _whole(out[first:point_at], str(abs(power)), grouped, group)
    if point_at < len(out):
        places = sum(1 for token in out[point_at + 1 :] if token[0] == "digit")
        text += point + _places(out[point_at + 1 :], "0" * places, point)
    return text


def _pictured(tokens: list) -> tuple[str, dict[str, str]]:
    """A fraction section as a character a token: its placeholders, digits, decimal and group
    marks, percent signs and slash as the canonical code writes them, any other literal as a
    character of the private use area, with the text each of those stands for."""
    picture, texts = [], {}
    for token in tokens:
        if token[0] in ("digit", "fixed"):
            picture.append(token[1])
        elif token[0] in ("point", "group", "slash"):
            picture.append({"point": ".", "group": ",", "slash": "/"}[token[0]])
        elif token[2:] == ("percent",):
            picture.append("%")
        else:
            mark = chr(PICTURED + len(texts))
            texts[mark] = token[1]
            picture.append(mark)
    return "".join(picture), texts


def _uncomma(picture: str) -> tuple[str, list[int]]:
    """The picture with the group marks a fraction writes: one after a literal or at the start,
    none after a placeholder, a digit, a decimal mark or another group mark (#\\ ,?/? writes 1234
    ,1/2, #,\\ ?/? 1234 1/2); and the place each character kept stood at."""
    out, kept = [], []
    for at, each in enumerate(picture):
        if each == "," and out and (out[-1] in COUNTING or out[-1] in ",."):
            continue
        out.append(each)
        kept.append(at)
    return "".join(out), kept


def _framed(picture: str) -> tuple | None:
    """A fraction's picture in its parts: the part before the slash with group marks as a fraction
    writes them, where the numerator begins in it, the denominator's lead, its run of placeholders
    and digits and what follows the run, whether group marks between the whole part's placeholders
    group it (#,##0 ?/? writes 1234,5 as 1,234 1/2) and how many group marks end the code after a
    placeholder, a digit or a decimal mark, decimal marks right after them past the slash still
    ending it (0?/%#%?,.0 writes 1 as 10/%1% .0, 0/#,%. as 100/1%.), a second such end counting
    as well (0?/%#%?,., writes 0 as 00/%1% ., 1 as #VALUE!, 0 ??#%%/?%%#00,., 1 as 100 and a
    blank). The
    numerator begins at the first decimal mark where that mark stands before the part's last run
    holding a placeholder or the part has no run, else at the first decimal mark after that run
    where something but decimal marks stands between them, else at the run, a digit next to
    placeholders standing in it. None where Excel takes the code for none: a part before the slash
    with neither a placeholder, a digit nor a decimal mark (x/0) or with a decimal mark before a
    placeholder (.?/?, #.?/?), a decimal mark before the denominator's run or right after it (?/.0,
    ?/0., ?/0,.), group marks between placeholders of the numerator (#,?/?) or, without a decimal
    mark before the slash, of the denominator (?/#,#), a numerator opening at a decimal mark whose
    placeholders a literal parts from a later placeholder or decimal mark (.x0x0/0, .x0x./0) and a
    denominator mixing digits with # or ? (?/4#)."""
    left, right = picture.split("/")
    if not set(left) & set(COUNTING + ".") or not set(right) & set(COUNTING):
        return None
    if re.search(r"\.,*[0#?]", left):
        return None
    lead, run, after = re.fullmatch(r"([^0-9#?]*)([0-9#?,]*[0-9#?])(.*)", right).groups()
    if "." in lead or after.lstrip(",").startswith("."):
        return None
    decimal = "." in left
    if not decimal and re.search(r"[0-9#?],+[0-9#?]", run):
        return None
    slash = picture.index("/")
    scaling = [
        found
        for found in re.finditer(r"(?<=[0-9#?.])(,+)(?=\.|[^0-9#?.]*$)", picture)
        if found.start() > slash or picture[found.end() :][:1] != "."
    ]
    written = left
    plain, kept = _uncomma(picture)
    left, right = plain.split("/")
    lead, run, after = re.fullmatch(r"([^0-9#?]*)([0-9#?]+)(.*)", right).groups()
    if re.search("[1-9]", run) and re.search("[#?]", run):
        return None
    point = left.find(".")
    runs = list(re.finditer(r"[0-9#?]*[0#?][0-9#?]*|[1-9]+", left))
    if not runs:
        start = point
    else:
        found = runs[-1]
        later = left.find(".", found.end())
        if decimal and point < found.start() and set(found[0]) & set(HOLDERS):
            start = point
        elif later < 0 or not left[found.end() : left.rfind(".") + 1].strip("."):
            start = found.start()
        else:
            start = later
    if re.search(r"[0-9#?],+[0-9#?]", written[kept[start] :]):
        return None
    parted = r"[0#?][^0-9#?.]+[0#?.]|\.[^0-9#?.]+[0#?].*\.[^0-9#?.]+[0#?.]"
    if start == point and re.search(parted, left[start:]):
        return None
    grouped = bool(re.search(r"[0-9#?],+[0-9#?]", written[: kept[start]]))
    commas = sum(len(found[1]) for found in scaling)
    return left, start, lead, run, after, grouped, commas


def _fraction(
    tokens: list, value: float, signed: bool, point: str, group: str, laying: bool = True
) -> str | None:
    """The number as a fraction, held to Excel over every code of up to six tokens of
    placeholders, digits, marks and literals (closed.py). Each percent sign scales the number a
    hundred times up and each group mark ending the code after a placeholder, a digit or a decimal
    mark a thousand times down, all at once, on a power of ten Excel keeps in a byte, one below
    nothing taking 256 more (0,0001 in # ?/?, is 1 and 249 zeros, in # ?/?,, 1 and 246), #VALUE!
    past SCALED_WIDTH. The whole part is written from its placeholders as Excel holds a number, to
    fifteen digits, down, or up once the count reaches the denominator, the count taken from the
    double past its floor (# ?/4 writes 123456789012344,75 as 123456789012345 3/4, # ?/2 as
    123456789012345, 0 0/1 writes 123456789012344,5 as 123456789012344 0/1). The denominator is the
    best fraction over as many places as its run has placeholders, PLACES_MOST at most (_nearest),
    or the run's digits, or the digits of the last stretch after the run opening with a digit and
    going on through digits, # and ? (?/2"x"9#0
    writes 0,5 as 45/2x9000 over 90), read in 16 bits: up to 32768 they are the denominator
    (70000 being 4464), any other giving the best fraction over as many places as they lack of
    2**16, PLACES_MOST at most, and the run's digits where placeholders or a decimal mark follow
    it with no such stretch, or follow the stretch past anything but a decimal mark, over
    PLACES_MOST (?/65535 writes 0,123 as 1/6, ?/65535"x"? as 123/6553 x0, ?/2"x"9"x"# 0,5 as
    1/2x9x0). Of a denominator the code gives the code's digits are written as far as the
    denominator has digits, spaces for the rest where a ? stands in the numerator or last in the
    whole part (?/08 writes 0,5 as 4/0 , ?0 #/092 as  0 46/09), the denominator's further digits
    after them or among the placeholders after the run. A numerator of digits alone writes
    no count but its digits (75529/? writes 0,5 as 75529/2), one opening at a decimal mark its
    count before the mark and its placeholders as for no digit (#.\\ ?/? writes 1234,5 as
    12341.  /2). Placeholders no digit reaches write as _filled, _denominated, _opened and _tail
    tell; a whole part of nothing writes the marks after it as spaces where the numerator opens
    with a ? or the whole part's last placeholder is a ?, else not at all, and a fraction of
    nothing writes the whole part alone, with spaces for the fraction where a ? stands about it (0
    in # ?/? is 0 and four spaces) or for what _ahead leaves of it. None without a whole part from
    FREE_MOST or for a count above FIXED_MOST over a denominator the code gives, before a whole
    part takes it (0,999999 in # ?/32768), and for a whole part of nothing before a numerator
    opening at a decimal mark without placeholders, but where the whole part's last placeholder
    is a 0, or a ? and the count nothing (#.\\ ?/? is #VALUE! for 0,5). Without a whole part a
    count of nothing is written without its sign (-0,004 in ?/ ? is 0/ 1). Not laying it out, the
    fraction is nothing once its count is taken, None past the width ahead of the system's tag."""
    picture, texts = _pictured(tokens)
    left, start, lead, run, after, grouped, commas = _framed(picture)
    written = next((token[1] for token in tokens if token[0] == "group"), ",")
    table = str.maketrans({".": point, ",": written, GROUPED: group, **texts})
    number = _scaled(value, picture.count("%"), commas)
    sign = "-" if signed and value < 0 else ""
    wpart, npart = left[:start], left[start:]
    lastw = max((at for at, each in enumerate(wpart) if each in HOLDERS), default=None)
    holders, parting = (None, wpart) if lastw is None else (wpart[: lastw + 1], wpart[lastw + 1 :])
    if commas and not holders and number >= FREE_MOST:
        return None
    held = Decimal(f"{number:.15g}")
    whole = math.floor(held) if holders else 0
    part = number - math.floor(number) if holders else number
    given, tailed = _denominator_given(run, after)
    fixed = given if given and not tailed and given <= FIXED_MOST + 1 else 0
    if not holders and not fixed and part >= FREE_MOST:
        return None
    rest = held - math.floor(held) if holders else held
    found = _fraction_count(part, rest, run, given, tailed, fixed)
    if found is None:
        return None
    count, denominator = found
    if holders and count == denominator:
        whole, count = math.ceil(held), 0
    npoint = npart.find(".")
    nint = npart if npoint < 0 else npart[:npoint]
    counted = _numerator(npart, count)
    under, owed, paid, leftover, tail = _denominator(
        left, npart, holders, run, after, given, denominator
    )
    text, shortened = "", False
    if holders:
        last = [each for each in holders if each in HOLDERS][-1]
        first = next((each for each in npart if each in HOLDERS), "")
        forced = count == 0 and whole == 0 and (first != "0" or last == "?")
        text = _aligned(holders, str(whole) if whole else "", forced, grouped).translate(table)
        shortened = (
            count == 0 and "0" not in npart and "?" not in (last, run[0]) and "?" not in npart
        )
    if not laying:
        # Before the system's date or time stands for the number, Excel holds to the width what the
        # section writes ahead of its tag: the whole part from its first placeholder, its parting
        # and the numerator once the numerator ends, to its last placeholder where the tag stands
        # before the denominator's, the slash and the denominator from its first placeholder but
        # where it opens with a ?, a blank Excel shortens as it counts (1 is #VALUE! in
        # 0 ??[$-F800]/##, and 0 ??/##,[$-F800], 0,0001 the date, 0,001 #VALUE! in
        # 0 ??/#[$-F800]#,; 1 the date in 0"x" [$-F800]?/?, and 0 ?[$-F800]?/##,, 0,01 #VALUE!
        # in 00 #/#[$-F800]0, and the date in 00 #/#0,[$-F800]; 0,01 the date, 0,1 #VALUE! in
        # # 0%,%/[$-F800]#,,).
        tag = picture[max(at for at, token in enumerate(tokens) if token[2:] == ("tagged",))]
        spot = left.find(tag)
        opening = next((at for at, each in enumerate(wpart) if each in HOLDERS), len(left))
        width = len(sign + text) if not 0 <= spot < opening else 0
        if not 0 <= spot < max((at for at, each in enumerate(left) if each in COUNTING), default=0):
            if tag in after and shortened:
                spent = _shortened(counted, lead, run, given, tailed, "." in left)
                width += len((parting + spent).translate(table))
            else:
                lastn = max((at for at, each in enumerate(npart) if each in HOLDERS), default=None)
                if tag not in after and lastn is not None:
                    counted = counted[: len(counted) - len(npart) + lastn + 1]
                width += len((parting + counted).translate(table))
                if tag in after and run[0] != "?":
                    width += len(("/" + lead + under).translate(table))
        return None if commas and width > SCALED_WIDTH else ""
    if tail is None:
        tail = _tail(after, owed, leftover, paid)
    if grouped:
        tail = _grouped(after, tail, owed, paid, leftover)
        if tail is None:
            return None
    rest = counted + "/" + lead + under
    if not holders:
        return (sign if count else "") + (parting + rest + tail).translate(table)
    if (
        whole == 0
        and not set(nint) & set(HOLDERS)
        and npoint >= 0
        and last != "0"
        and not (count == 0 and last == "?")
    ):
        return None
    if whole == 0 and not forced and last != "0":
        opening = next((each for each in nint if each in HOLDERS), "")
        parting = " " * len(parting.translate(table)) if "?" in (opening, last) else ""
    if count == 0 and "0" not in npart:
        cut = after.find(".")
        spared = cut >= 0 and bool(_owing(after[:cut], owed, paid, leftover)[2])
        held = tail if spared or set(after) & set(HOLDERS) else ""
        if not shortened:
            blank = len((parting + rest + held).translate(table))
        else:
            opened = given is None and "." in left
            spent = _shortened(counted, lead, run, given, tailed, opened)
            if len(sign + text + (parting + spent).translate(table)) > SHOWN_LONGEST:
                return None
            ahead = _ahead(run, after, under, held, opened, owed, grouped)
            blank = len((under + held).translate(table)) - len(ahead.translate(table))
        if held:
            end = max(after.rfind(each) for each in HOLDERS)
            closing = len(after) - 1 - (max(end, cut - 1) if spared else end)
            closing = held[len(held) - closing :].translate(table)
            return sign + text + " " * max(blank - len(closing), 0) + closing
        return sign + text + " " * blank + tail.translate(table)
    return sign + text + (parting + rest + tail).translate(table)


def _scaled(value: float, percents: int, commas: int) -> float:
    """Excel scales the double once, by the power of ten all its percent signs and group marks
    make (?/???%%0, writes 0,0003 as 2/667, ten times 0,0003 being a double under 0,003), and a
    number past the largest double is nothing."""
    power = 2 * percents
    if commas:
        power += (SCALED_UP if 2 * percents < 3 * commas else 0) - 3 * commas
    number = abs(value) * 10.0**power if power <= sys.float_info.max_10_exp else math.inf
    return 0.0 if math.isinf(number) else number


def _denominator_given(run: str, after: str) -> tuple[int | None, bool]:
    """The denominator the code's digits give, if they give one, and whether placeholders or a
    decimal mark follow it past its stretch. Digits before a percent sign that placeholders or a
    decimal mark follow give no denominator (0/2 6%0 writes 0,001 as 1/20 6%0, 0/2 6%0 writes 1
    as 100/2 6%0)."""
    if not re.search("[1-9]", run):
        return None, False
    past = after[after.rfind("%") + 1 :]
    reading = past if set(past) & set(HOLDERS + ".") else after
    later = list(re.finditer("[1-9][0-9#?]*", reading))
    if later:
        beyond = re.sub(r"^[0-9#?.]*", "", reading[later[-1].end() :])
        tailed = bool(set(beyond) & set(HOLDERS + "."))
    else:
        tailed = bool(set(after) & set(HOLDERS + "."))
    return int(re.sub("[#?]", "", later[-1][0]) if later else run) % GIVEN_BITS, tailed


def _fraction_count(
    part: float, rest: Decimal, run: str, given: int | None, tailed: bool, fixed: int
) -> tuple[int, int] | None:
    """The count and the denominator of the fraction of `part`, its fifteen digits `rest`, over
    the denominator the code fixes, if it fixes one; None for a count above FIXED_MOST over it."""
    if fixed == 1:
        # Over a denominator of one Excel rounds the number as 0 does, at fifteen digits (# ?/1%
        # writes 10000000000,005 as 1000000000001, a hundred times its double 1000000000000,49988).
        count, denominator = int(rest.to_integral_value(ROUND_HALF_UP)), 1
    elif fixed:
        count, denominator = math.floor(part * fixed + 0.5), fixed
        if -math.fma(part, fixed, -count - 0.5) <= TIED * (count + 0.5):
            count += 1
    elif given is None:
        return _nearest(part, min(len(run), PLACES_MOST))
    else:
        return _nearest(part, PLACES_MOST if tailed else min(GIVEN_BITS - given, PLACES_MOST))
    return None if count > FIXED_MOST else (count, denominator)


def _numerator(npart: str, count: int) -> str:
    npoint = npart.find(".")
    nint, ndec = (npart, "") if npoint < 0 else (npart[:npoint], npart[npoint:])
    if set(nint) & set(HOLDERS):
        counted = _aligned(nint, str(count) if count else "", True, False)
    elif npoint >= 0:
        counted = nint + str(count)
    else:
        counted = nint
    return counted + _substituted(ndec, _opened("".join(each for each in ndec if each in HOLDERS)))


def _denominator(
    left: str,
    npart: str,
    holders: str | None,
    run: str,
    after: str,
    given: int | None,
    denominator: int,
) -> tuple[str, int, int, str, str | None]:
    """The denominator as its run writes it, the spaces it owes, the places it paid, the digits
    left over of a given one and the tail after it where a decimal mark lays it out."""
    owed, paid, leftover, tail = 0, 0, "", None
    if given is not None:
        digits = str(denominator)
        if "?" in left and len(digits) > len(run):
            under, leftover = run, digits[len(run) :]
        else:
            under = run[: len(digits)] + digits[len(run) :]
        closed = holders and [each for each in holders if each in HOLDERS][-1] == "?"
        if ("?" in npart or closed) and len(under) < len(run):
            owed = len(run) - len(under)
            under += " " * owed
    elif "." in left:
        digits = str(denominator)
        fill = run[len(digits) :]
        outs = _opened(fill + after)
        under = digits + "".join(outs[: len(fill)])
        tail = _substituted(after, outs[len(fill) :])
    else:
        under, owed, paid = _denominated(list(run), denominator)
    return under, owed, paid, leftover, tail


def _shortened(
    counted: str, lead: str, run: str, given: int | None, tailed: bool, opened: bool
) -> str:
    """What a blank Excel shortens counts toward the 255 characters past its parting: the numerator
    as written, the slash, the denominator's lead and the run's leading zeros, a run of # alone as
    one place, a given denominator its number's digits or, placeholders after it, one place; after
    a decimal mark the slash alone (0 #/00 writes 1 and 249 zeros, 0 #/#0 1 and 251, 0 #/# 1 and
    250, 0 #/100 1 and 248, 0 #/010 1 and 249, 0 #/100"x"0 1 and 250, 0 #./00 1 and 252; closed.py's
    wide and blanks; 0,000001 is #VALUE! in 0 89/"Ačb4"#[$-F800]#,.#0)."""
    if opened:
        return "/"
    if given is not None:
        places = 1 if tailed else len(str(given))
    else:
        places = len(run) - len(run.lstrip("0")) or int(set(run) == {"#"})
    return counted + "/" + lead + "0" * places


def _ahead(
    run: str, after: str, under: str, held: str, opened: bool, owed: int, grouped: bool
) -> str:
    """What the denominator and the placeholders after it write ahead of the spaces of a fraction
    of nothing where no ? stands in its numerator, first in its run or last in its whole part: up
    to the last 0, # or digit before their first ?, the rest written as spaces, and all of it
    without a ? (#x#/0?0 writes 0 as 0 and two spaces, #x./#?# 0 and two, #x#/#?# 0 and one,
    #x#/0x? 0 and two, 0 #/1"x"0? 0 and one, #x#/0x0 0 alone), its zeros grouped as the tail's
    are (#,##0 ?0%#/%#%0? writes 0 as 0  0 and one space, #,##0 ?0%#/%#?%0 as 0  0 and four).
    The denominator is 1 or the code's."""
    marks = run + after
    first = marks.find("?")
    if first < 0:
        return under + held
    cut = max(at for at in range(first) if at < len(run) or marks[at] in "0#") + 1
    if cut < len(run):
        if opened:
            return "1" + "".join(_opened(run[1:cut]))
        return "".join(EMPTY[mark] for mark in run[:cut])
    own = after[: cut - len(run)]
    if opened:
        written = _substituted(own, _opened(run[1:] + own)[len(run) - 1 :])
    else:
        written = _tail(own, owed, "")
    return under + (_grouped(own, written, owed) if grouped else written)


def _tail(after: str, owed: int, leftover: str, paid: int = 0) -> str:
    """What follows the denominator's run without a decimal mark before the slash. Up to a
    decimal mark the placeholders write as _owing tells. Past the mark they write as _filled
    tells, a 0 counted before them where any placeholder or a ? left a space stands before the
    mark (0.? writes 0.0, ??x.# 1 x.0). The denominator's digits beyond the code's that no ?
    takes stand before the mark, or nowhere without one (?/2"x"?"x". writes 1234,5678 as
    6172839/2x0x00.)."""
    cut = after.find(".") if "." in after else len(after)
    own, past = after[:cut], after[cut:]
    outs, held, spare = _owing(own, owed, paid, leftover)
    return _substituted(own, outs) + (spare if past else "") + _substituted(past, _past(past, held))


def _grouped(after: str, tail: str, owed: int, paid: int = 0, leftover: str = "") -> str | None:
    """The tail of a fraction whose whole part is grouped: its zeros up to a decimal mark take a
    group mark after the first and every third since, and from a placeholder a ? paid a zero to
    after its first and every third since (#,##0 ?/?"x"0000 writes 1234,5 as 1,234 1/2x0,000,
    "x"0?00 x0,00,00, ?/???"x"00??0 1234,5678 as 1,234 67/118x0,0000,00), but never after a zero
    a ? writes (#,##0
    ?/??"x"000? writes 1234,5678 as 1,234 46/81x0,000). The ?s opening the placeholders pay the
    spaces the denominator's run left with zeros that count no place (#,##0 ?/??"x"?0 writes 0,5
    as 0 1/2 x00,). None where the placeholders past those are not a run of ? alone, a run of
    one kind and ?s, or a run of one kind, as many ?s, a run of one kind and ?s, a literal parting
    only ?s from them (0#, 0"y"0, 00?0, 0??0 and 0?0# are #VALUE!, 00?, 0?00, 0?0??, 00??0 and
    #"y"? not) or a space the run left is
    still owed before them (0,5 in #,##0 ??/??"x"0 and #,##0 ?/??"x"??0), but for ?s alone, which
    take no mark (#,##0 ?/??"x"? writes 0,5 as 0 1/2 x0), measured over closed.py's grouped,
    runs, mixed, zeros, owed and paid."""
    cut = after.find(".") if "." in after else len(after)
    own = after[:cut]
    places = [at for at, each in enumerate(own) if each in HOLDERS]
    if not places:
        return tail
    marks = "".join(own[at] for at in places)
    if owed and set(marks) == {"?"}:
        return tail
    opening = len(marks) - len(marks.lstrip("?"))
    paying = min(owed, opening)
    kept = marks[paying:]
    stretch = own[places[paying] : places[-1] + 1]
    parted = re.search(r"[^0#?][0#?]*[0#]", stretch)
    shape = re.fullmatch(r"\?+|(?:0+|#+)\?*|(0+|#+)(\?+)(?:0+|#+)\?*", kept)
    if owed > paying or parted or not shape or shape[1] and len(shape[1]) != len(shape[2]):
        return None
    point = tail.find(".") if "." in tail else len(tail)
    if leftover:
        written = [(each, "0", False) for each in tail[:point]]
    else:
        outs = iter(_owing(own, owed, paid)[0])
        written = []
        for at, mark in enumerate(own):
            out = next(outs) if mark in HOLDERS else mark
            spent = at in places[:paying]
            doubled = mark in "0#" and len(out) > 1
            written += [
                (each, "" if spent else mark, doubled and not n) for n, each in enumerate(out)
            ]
    out, count, anchor = [], 0, 1
    for each, mark, opening in written:
        out.append(each)
        if each.isdigit() and mark:
            count += 1
            if opening:
                anchor = count
            if mark != "?" and (count == 1 or (count - anchor) % 3 == 0):
                out.append(GROUPED)
    return "".join(out) + tail[point:]


def _owing(own: str, owed: int, paid: int = 0, leftover: str = "") -> tuple[list, int, str]:
    """What the placeholders after the run write up to a decimal mark (_tail), the zeros still
    owed past it and the denominator's digits beyond the code's left over. Each 0 or # writes 0
    and owes one more, each ? that left a space one more after it. The first placeholders pay the
    spaces the run left, one each, a # then writing nothing (?/33871"x"0## writes 0,01 as 1/338
    x00, "x"?## as x00, "x"### as x0); past those a ? writes 0 for one the tail owes, else a
    space, and the next 0 or # after a ? paying it writes 00, through spaces and literals between
    (##?? writes 0000, #??# 00 00, #?x# 00x00, ?x?# x000, but ??x?0 1 x00, ?/33871"x"0?0 0/3
    x000). The denominator's digits beyond the
    code's go one to each ? before the first 0 or #, each such ? then counting as one that paid,
    and the rest before that 0 or # (?/2"x"?"x"# writes 1234,5678 as 6172839/2x0x0000, "x"#?#
    as x0000000)."""
    outs, pending, lead, prior, doubled = [], 0, 0, None, 0
    for mark in own:
        if mark not in HOLDERS:
            lead, pending = lead + pending, 0
        elif mark == "?" and leftover and prior in (None, "?"):
            outs.append(leftover[0])
            leftover, doubled = leftover[1:], doubled + 1
        elif mark == "?":
            if lead or owed:
                if owed:
                    owed -= 1
                else:
                    lead, doubled = lead - 1, doubled + 1
                outs.append("0")
            else:
                pending += 1
                outs.append(" ")
        else:
            first = prior is None and paid
            out = "" if (first or owed) and mark == "#" else "0" * (1 + doubled)
            outs.append(leftover + out)
            leftover = ""
            if owed:
                owed -= 1
            lead, pending, doubled = lead + pending + 1 + doubled, 0, 0
        if mark in HOLDERS:
            prior = mark
    return outs, owed + lead + pending, leftover


POOL_KIND = {"0": "A", "#": "H", "?": "Q"}
POOL_PAYS = {"A": "#?", "H": "0?", "Q": "0#", "B": "0#?"}


def _past(past: str, owed: int) -> list:
    """What the placeholders past a fraction tail's decimal mark write, owed zeros standing at the
    mark. Obligations are kept as one pool: a 0 writes 0 and, with none owed or the pool a 0's,
    owes one more, paid by a # or a ?; a # that wrote nothing, or a ? that wrote a space, owes one
    paid by a 0 or the other of the two. The first payment out of a pool of several makes what is
    left payable by any placeholder, as does a literal or the mark for the owed zeros (0.0# writes
    0.0 and 00.0# 00.00, but #0#.0 and ##0# .00), measured over every tail up to three marks
    before and five after the decimal mark (closed.py, tails)."""
    kind, count, outs = ("B" if owed else None), owed, []
    for mark in past:
        if mark not in HOLDERS:
            kind = "B" if count else kind
            continue
        if count and mark in POOL_PAYS[kind]:
            outs.append("0")
            count -= 1
            kind = "B" if count else None
            continue
        outs.append(EMPTY[mark])
        if not count or kind == POOL_KIND[mark]:
            kind, count = POOL_KIND[mark], count + 1
    return outs


def _opened(marks: str) -> list:
    """What the placeholders after a denominator's digits write where the numerator opens at a
    decimal mark, through what follows the run: a ? writes a space and a # nothing till one of
    the other kind or a 0 answers one of them with a 0, the rest then turning to zeros, as does
    each 0 answering none; a zero makes the next ? or # write 0. Anything but a placeholder turns
    the unanswered to zeros, and a 0 right after it takes one (?##0# writes 1 as 100, #x0## 1x00,
    00x0# 10x0, #x#x# 1xx0)."""
    spaces = blanks = zeros = 0
    outs, prior, answered = [], None, False
    for mark in marks:
        answers = True
        if mark not in HOLDERS:
            zeros, spaces, blanks = zeros + spaces + blanks, 0, 0
            answers = False
        elif mark != "?" and spaces:
            zeros, spaces = zeros + spaces - 1, 0
            outs.append("0")
        elif mark != "#" and blanks:
            zeros, blanks = zeros + blanks - 1, 0
            outs.append("0")
        elif mark != "0" and zeros:
            zeros -= 1
            outs.append("0")
        elif mark == "0":
            zeros += -1 if zeros and (answered or prior not in (None, *HOLDERS)) else 1
            outs.append("0")
            answers = False
        else:
            spaces, blanks = spaces + (mark == "?"), blanks + (mark == "#")
            outs.append(EMPTY[mark])
            answers = False
        prior, answered = mark, answers
    return outs


def _aligned(picture: str, digits: str, forced: bool, grouped: bool) -> str:
    """The digits in a picture's placeholders as _whole places them, its last placeholder writing
    0 where `forced`, though no digit comes to it; grouped by GROUPED."""
    last = max(at for at, each in enumerate(picture) if each in HOLDERS)
    if forced:
        picture = picture[:last] + "0" + picture[last + 1 :]
    held = [("digit", each) if each in HOLDERS else ("lit", each) for each in picture]
    return _whole(held, digits, grouped, GROUPED)


def _substituted(picture: str, outs: list) -> str:
    out, each = [], iter(outs)
    for mark in picture:
        out.append(next(each) if mark in HOLDERS else mark)
    return "".join(out)


def _filled(kinds: list) -> list:
    """What placeholders with no digit write: a 0 writes 0, as does the first of another kind
    after a run of one kind opening them; any other as for no digit (?#0 writes a space, 0 and
    0, #?? nothing, 0 and a space)."""
    out = []
    for at, kind in enumerate(kinds):
        breaks = at > 0 and kind != kinds[0] and all(each == kinds[0] for each in kinds[:at])
        out.append("0" if kind == "0" or breaks else EMPTY[kind])
    return out


def _denominated(kinds: list, denominator: int) -> tuple[str, int, int]:
    """The denominator of a fraction with no decimal mark before its slash, and how many ? it left a
    space with no 0 after: right-aligned, or from its first ? on where it has one, its first digit
    in that ? and the others in the ? after it, then from the right, each placeholder left where it
    stands (?0? writes 81 as 801); digits beyond those placeholders take the places before them,
    which write nothing. A 0 writes 0, a # nothing, and a ? a space, but 0 for each ? that left a
    space before the last 0 or # before it and no 0 since (?0?0? writes 1 as 10 00, ??0?? as
    1 00 )."""
    digits = str(denominator)
    region = kinds[kinds.index("?") :] if "?" in kinds else kinds[-1:]
    if len(digits) >= len(region):
        return (
            "".join(EMPTY[kind] for kind in kinds[: max(len(kinds) - len(digits), 0)]) + digits,
            0,
            0,
        )
    taken, extra = {0}, len(digits) - 1
    marked = [at for at in range(1, len(region)) if region[at] == "?"]
    for at in marked + list(range(len(region) - 1, 0, -1)):
        if extra and at not in taken:
            taken.add(at)
            extra -= 1
    placed, written, owed, pending, paid = iter(digits), [], 0, 0, 0
    for at, kind in enumerate(region):
        if at in taken:
            written.append(next(placed))
        elif kind != "?":
            owed, pending = owed + pending, 0
            written.append(EMPTY[kind])
        elif owed:
            owed, paid = owed - 1, paid + 1
            written.append("0")
        else:
            pending += 1
            written.append(" ")
    prefix = "".join(EMPTY[kind] for kind in kinds[: len(kinds) - len(region)])
    return prefix + "".join(written), owed + pending, paid


def _runs(tokens: list) -> list[list]:
    """The tokens' runs of placeholders and digits, each unbroken by anything else."""
    runs = [[]]
    for token in tokens:
        if token[0] in ("digit", "fixed"):
            runs[-1].append(token)
        elif runs[-1]:
            runs.append([])
    return [run for run in runs if run]


def _given(run: list) -> bool:
    return any(token[0] == "fixed" for token in run)


def _nearest(part: float, places: int) -> tuple[int, int]:
    """The fraction Excel writes for a part of one with no denominator longer than its places: the
    last convergent of the part's continued fraction that fits, its terms taken in doubles, none
    between them however near (0,118 is 1/8 in # ?/?, not the nearer 1/9; 0,1 is 0, its
    reciprocal being 10 as a double). A term whose product with the last numerator passes 32 bits
    ends it too, the sum after that product going unchecked, and the whole number it then leaves
    alone is rounded (in ?/? 2147483646,6 is 4294967293/2, 2147483646,5 2147483647/1, 429496729,6
    2147483648/5; in ?/??? 123456789,123 987654313/8)."""
    before, last = (0, 1), (1, 0)
    rest = part
    while not math.isinf(rest):
        whole = math.floor(rest)
        if whole * last[0] > FREE_MOST:
            return (int(_rounded(part, 0)), 1) if last[1] == 1 else last
        following = (whole * last[0] + before[0], whole * last[1] + before[1])
        if len(str(following[1])) > places:
            break
        before, last = last, following
        if rest == whole:
            break
        rest = 1 / (rest - whole)
    return last


def _clock(serial: float, unit: int) -> tuple[int, float, float, float]:
    """The serial's days, and its hours, minutes and seconds each of the one before's rest, as
    Excel reads a time of day: half a tick of 1/unit second added to the day."""
    moment = serial + 0.5 / (86_400 * unit)
    days = math.floor(moment)
    hours = (moment - days) * 24
    minutes = (hours - math.floor(hours)) * 60
    return days, hours, minutes, (minutes - math.floor(minutes)) * 60


def _ticks(serial: float, unit: int) -> int:
    """The serial's ticks of 1/unit second as Excel shows a time of day: the parts of its clock
    with the rest cut off, its places read from the rest's fifteen digits."""
    days, hours, minutes, seconds = _clock(serial, unit)
    part = math.floor(Decimal(f"{seconds - math.floor(seconds):.15g}") * unit)
    whole = (days * 24 + math.floor(hours)) * 60 + math.floor(minutes)
    return (whole * 60 + math.floor(seconds)) * unit + part


def _elapsed(moment: float, letter: str) -> int:
    """The hours, minutes or seconds an elapsed [h], [m] or [s] counts of a moment in days, half
    a tick added to it already: multiplied out by sixties first and the day's 24 hours last,
    which is how Excel tells which way a half second goes (59.5 seconds show as [mm]:ss 01:59).
    A count past fifteen digits keeps fifteen as Excel holds a number, one past the doubles none
    ([s] of 1E+100 days is 864 and 98 zeros, of 9.99999999999999E+307 0)."""
    for factor in ELAPSED[letter]:
        moment *= factor
    if math.isinf(moment):
        return 0
    return int(Decimal(f"{moment:.15g}")) if moment >= 10**15 else math.floor(moment)


@dataclass(frozen=True)
class _Moment:
    """What a date section writes its codes of a day and a time from."""

    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int
    weekday: int
    weekly: bool
    names: dict
    language: str | None


def _date(section: Section, serial: float, locale: str) -> str | Error:
    if serial < 0:
        return VALUE
    places = max((token[1] for token in section.tokens if token[0] == "places"), default=0)
    unit = 10**places
    days, ticks = divmod(_ticks(serial, unit), 86_400 * unit)
    clocked = any(token[0] == "date" and token[1][0] != "[" for token in section.tokens)
    # Time elapsed alone counts past the calendar's last day, but for its decimal places ([hh]
    # writes 123456789,123 as 2962962938, [hh].0 #VALUE!).
    found = day_of(days) if clocked or places else (0, 0, 0)
    if found is None:
        return VALUE
    calendar, named = section.calendar or (None, locale)
    if calendar == "hijri" and clocked and (found := hijri(days)) is None:
        return VALUE
    year, month, day = found
    seconds, part = divmod(ticks, unit)
    hour, rest = divmod(seconds, 3600)
    minute, second = divmod(rest, 60)
    twelve = _twelve(section.tokens)
    left = _left(serial, unit, clocked)
    names = _names(section.language or named, calendar, section.language is not None)
    weekday = (days - 1) % 7
    first = next((token[1] for token in section.tokens if token[0] == "date"), "")
    weekly = calendar == "hijri" and section.language is None and first in ("ddd", "dddd")
    if weekly:
        # B2 with no [$-tag] after it counts the weekdays of a code that begins with one by the
        # true calendar of 1900, without the 29 February Excel adds (0 and 1 are Monday), and
        # writes the weekday for a month's long name there (B2dddd mmmm, not mmm); else as Excel
        # counts them (0 is Saturday in B2dd dddd and B2[$-409]dddd).
        weekday = (calendar_day(days or 1).weekday() + 1) % 7
    moment = _Moment(
        year, month, day, hour, minute, second, weekday, weekly, names, section.language
    )
    out = []
    read = False
    for place, token in enumerate(section.tokens):
        kind = token[0]
        if kind == "lit":
            out.append(token[1])
        elif kind == "places":
            out.append(
                _marks(locale)[0] + str(part // 10 ** (places - token[1])).rjust(token[1], "0")
            )
        elif kind == "mark":
            out.append(formats.day_mark(locale))
        elif kind == "general":
            out.append(formats.numeral(left, _marks(locale)[0], formats.GENERAL))
        elif kind == "date" and token[1].startswith("["):
            inner = token[1][1:-1]
            moment_at = (left if read else serial) + 0.5 / (86_400 * unit)
            out.append(str(_elapsed(moment_at, inner[0])).rjust(len(inner), "0"))
        elif kind == "date":
            out.append(_date_code(token, place in twelve, moment))
            read = True
    return "".join(out)


def _twelve(tokens: list) -> set[int | None]:
    """The marks of the morning and the afternoon count on a clock of twelve the last hour before
    each of them and the last of all (en h:hAM/PM writes 0 as 0:12AM, AM/PMh:h as AM0:12,
    hAM/PMh as 12AM12)."""
    twelve, hour_at = set(), None
    for at, token in enumerate(tokens):
        if token[0] == "date" and token[1][0] == "h":
            hour_at = at
        elif token[0] == "date" and token[1] in NOONS and hour_at is not None:
            twelve.add(hour_at)
    if twelve or any(token[0] == "date" and token[1] in NOONS for token in tokens):
        twelve.add(hour_at)
    return twelve


def _left(serial: float, unit: int, clocked: bool) -> float:
    """What the clock leaves past its minutes, or past its seconds in ticks of the decimal places,
    is what General writes among a date's codes and what an elapsed time after any of its other
    codes counts as days (en sGeneral writes 1234,5678 as 3838.42, ss.000General as
    37.920920.5000096, yyyy[mm] as 190355324, General[hh] as 38.4229629); with neither a clock
    nor decimal places about it General writes the number ([h]General writes 1234,5678 as
    296291234.5678, [s].000General as 106666657.920920.5000096)."""
    left = _clock(serial, unit)[3]
    if unit > 1:
        return (left - math.floor(left)) * unit
    return left if clocked else serial


def _date_code(token: tuple, twelve: bool, moment: _Moment) -> str:
    """A code of a day or a time written of the moment, an hour on a clock of twelve where
    `twelve`."""
    code = token[1]
    letter, size, names = code[0], len(code), moment.names
    if code == "am/pm":
        return names["ampm"][moment.hour >= 12]
    if code == "a/p":
        return (
            names["ampm"][moment.hour >= 12]
            if moment.language
            else token[2][2 * (moment.hour >= 12)]
        )
    if letter == "e":
        return str(moment.year)
    if letter in "yb":
        year = moment.year + BUDDHIST * (letter == "b")
        return f"{year % 100:02d}" if size <= 2 else str(year)
    if letter == "m":
        if size <= 2:
            return str(moment.month).rjust(size, "0")
        if moment.weekly and size > 3:
            return names["days"][moment.weekday]
        key = {3: "months_short", 5: "months_initial"}.get(size, "months")
        return names[key][moment.month - 1]
    if letter == "d":
        if size <= 2:
            return str(moment.day).rjust(size, "0")
        return names["days_short" if size == 3 else "days"][moment.weekday]
    if letter == "h":
        hour = (moment.hour % 12 or 12) if twelve else moment.hour
        return str(hour).rjust(min(size, 2), "0")
    if letter == "n":
        return str(moment.minute).rjust(min(size, 2), "0")
    if letter == "s":
        return str(moment.second).rjust(min(size, 2), "0")
    return ""


@cache
def _names(locale: str, calendar: str | None, tagged: bool) -> dict:
    """Month and day names as they stand alone, Sunday first, Windows' where they differ from
    ICU's, the short ones of a language no [$-tag] names without the period ending them (fr
    janv, [$-40C] janv.), and the marks of the morning and the afternoon, which Excel writes AM
    and PM where ICU writes am and pm (en-GB). B1's Gregorian months write their whole name for
    the initial unless a [$-tag] names their language. B2's Hijri months are named in Arabic,
    French or, for any other language, English, their short names in Arabic whatever the
    language, the days of the English names beside them and of the others their language's."""
    alone, wide = icu.DateFormatSymbols.STANDALONE, icu.DateFormatSymbols.WIDE
    if calendar == "hijri":
        language = locale if locale in formats.HIJRI_MONTHS else "en"
        months = formats.HIJRI_MONTHS[language]
        days = formats.HIJRI_DAYS.get(language)
        own = _names(language, None, tagged)
        return {
            "months": months,
            "months_short": formats.HIJRI_MONTHS["ar"],
            "months_initial": [each[0] for each in months],
            "days": days or own["days"],
            "days_short": days or own["days_short"],
            "ampm": own["ampm"],
        }
    symbols = icu.DateFormatSymbols(icu.Locale(locale))
    months = list(symbols.getMonths(alone, wide))[: formats.MONTHS_A_YEAR]
    days = formats.DAYS.get(locale) or list(symbols.getWeekdays(alone, wide))[1:]
    return {
        "months": months,
        "months_short": list(formats.short_months(locale, tagged)),
        "months_initial": (
            months if calendar == "gregorian" and not tagged else [each[0] for each in months]
        ),
        "days": list(days),
        "days_short": list(formats.short_days(locale, tagged)),
        "ampm": ["AM", "PM"],
    }
