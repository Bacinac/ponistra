"""Numbers and dates as text in a document's language, and text read back as them, as Excel does
in that language (D22): how a number is written in a formula or turned into text, what a typed
or given text reads as. Logicals are TRUE and FALSE in every language, as function names are
English in every language."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from functools import cache, partial
from typing import NamedTuple

import icu

from .dates import dated

SMALLEST = 2.2250738585072014e-308
PLACES_MOST = 308
POWER_MOST = 10**9
SECONDS_A_DAY = 86_400
CENTURY_TURN = 30
FRACTION_MOST = 32767
WRAPPED = 2**16
CLOCK_DIGITS = 4
MONTHS_A_YEAR = 12
NAMED_LEAST = 3
WRITTEN = 21
SHOWN = 20
GENERAL = 11
COUNTED_MOST = 9

GROUPED = "#,##0"
GROUPED_PLACES = "#,##0.00"
PERCENT = "0%"
PERCENT_PLACES = "0.00%"
SCIENTIFIC = "0.00E+00"
FRACTION = "# ?/?"
FRACTION_TWO = "# ??/??"
SHORT_DATE = "mm-dd-yy"
DAY_MONTH_YEAR = "d-mmm-yy"
DAY_MONTH = "d-mmm"
MONTH_YEAR = "mmm-yy"
CLOCK = "h:mm"
CLOCK_SECONDS = "h:mm:ss"
HALVES = "h:mm AM/PM"
HALVES_SECONDS = "h:mm:ss AM/PM"
TENTHS = "mm:ss.0"
DURATION = "[h]:mm:ss"
MOMENT = "m/d/yy h:mm"
# The languages a document is written in, each computed as Excel computes under the Windows
# regional format of its culture.
CULTURES = {
    "hr": "hr-HR",
    "en": "en-US",
    "en-GB": "en-GB",
    "de": "de-DE",
    "fr": "fr-FR",
    "it": "it-IT",
    "es": "es-ES",
}
# Windows writes a negative amount in brackets in US English alone of the document languages
# (LOCALE_INEGCURR 0), as the format Excel gives a typed amount then does; ICU writes a minus.
BRACKETED = frozenset({"en"})
# French groups by a plain space, which Excel shows and reads, where ICU writes U+202F.
MARKS = {
    "hr": (",", "."),
    "en": (".", ","),
    "en-GB": (".", ","),
    "de": (",", "."),
    "fr": (",", " "),
    "it": (",", "."),
    "es": (",", "."),
}


class Codes(NamedTuple):
    year: str
    month: str
    day: str
    hour: str
    minute: str
    second: str
    weekday: str
    era: str
    general: str


# The letters TEXT reads a code's parts of a date by and its name of General in the language, as
# Application.International tells them (international-<code>.tsv), with a weekday's aaa written
# ooo and the era's g written x where the year or the day takes the letter (cases-<code>.xlsx).
CODES = {
    "hr": Codes("y", "m", "d", "h", "m", "s", "a", "g", "General"),
    "en": Codes("y", "m", "d", "h", "m", "s", "a", "g", "General"),
    "en-GB": Codes("y", "m", "d", "h", "m", "s", "a", "g", "General"),
    "de": Codes("J", "M", "T", "h", "m", "s", "a", "g", "Standard"),
    "fr": Codes("a", "m", "j", "h", "m", "s", "o", "g", "Standard"),
    "it": Codes("a", "m", "g", "h", "m", "s", "o", "x", "Standard"),
    "es": Codes("a", "m", "d", "h", "m", "s", "o", "g", "Est\u00e1ndar"),
}
# Excel takes a language's short date and its months' and days' short names from Windows, whose
# Croatian writes d.M.yyyy and vlj, not ICU's dd. MM. y. and velj, whose British English and
# Spanish Sep, not Sept, whose German Mrz, not Mär, whose French janv and jeu without ICU's point
# and whose Spanish two letters of a day; it shows its built-in dates with a month's name (d-mmm-yy,
# d-mmm, mmm-yy) with the marks Windows parts a day, a month's name and a year by (NAMED_MARKS).
SHORT_DAYS = {
    "hr": "d.M.yyyy",
    "en": "M/d/yyyy",
    "en-GB": "dd/MM/yyyy",
    "de": "dd.MM.yyyy",
    "fr": "dd/MM/yyyy",
    "it": "dd/MM/yyyy",
    "es": "dd/MM/yyyy",
}
# Windows' long date and long time, which Excel shows for a code tagged [$-F800] or [$-F400]
# whatever the code writes after the tag.
LONG_DAYS = {
    "hr": "d. MMMM yyyy.",
    "en": "dddd, MMMM d, yyyy",
    "en-GB": "dd MMMM yyyy",
    "de": "dddd, d. MMMM yyyy",
    "fr": "dddd d MMMM yyyy",
    "it": "dddd d MMMM yyyy",
    "es": "dddd, d' de 'MMMM' de 'yyyy",
}
LONG_TIMES = {
    "hr": "H:mm:ss",
    "en": "h:mm:ss tt",
    "en-GB": "HH:mm:ss",
    "de": "HH:mm:ss",
    "fr": "HH:mm:ss",
    "it": "HH:mm:ss",
    "es": "H:mm:ss",
}
MONTHS_SHORT = {
    "hr": ("sij", "vlj", "ožu", "tra", "svi", "lip", "srp", "kol", "ruj", "lis", "stu", "pro"),
    "en-GB": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "de": ("Jan", "Feb", "Mrz", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"),
    "es": (
        *("ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep.", "oct.", "nov."),
        "dic.",
    ),
}
DAYS_SHORT = {
    "es": ("do.", "lu.", "ma.", "mi.", "ju.", "vi.", "sá."),
}
# Windows' days where they differ from ICU's, Arabic's short ones its whole names.
DAYS = {
    "ar": ("الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"),
}
# The Hijri months Windows names (B2) in Arabic, French and English, which every other language
# writes, its days beside them.
HIJRI_MONTHS = {
    "ar": (
        "محرم",
        "صفر",
        "ربيع\xa0الأول",
        "ربيع\xa0الثاني",
        "جمادى\xa0الأولى",
        "جمادى\xa0الثانية",
        "رجب",
        "شعبان",
        "رمضان",
        "شوال",
        "ذو\xa0القعدة",
        "ذو\xa0الحجة",
    ),
    "fr": (
        "Mouharam",
        "Safar",
        "Rabi' Aoual",
        "Rabi' Thani",
        "Jamada El Oula",
        "Jamada El Thaniah",
        "Rajab",
        "Chaaban",
        "Ramadan",
        "Chaoual",
        "Zoul Ki'dah",
        "Zoul Hijjah",
    ),
    "en": (
        "Muharram",
        "Safar",
        "Rabi' Awwal",
        "Rabi' Thani",
        "Jamada El Oula",
        "Jamada El Thaniah",
        "Rajab",
        "Sha'ban",
        "Ramadan",
        "Shawwal",
        "Thoul Ki'dah",
        "Thoul Hijjah",
    ),
}
HIJRI_DAYS = {
    "en": ("AlAhad", "AlEthnien", "AthThulatha", "AlArbia'a", "AlKhamis", "AlJumaa", "AsSabt"),
}
# Words Excel reads as a month though they do not start its name: German's short Mrz, not
# Croatian's vlj, which Excel shows and does not read (cases-<code>.xlsx, Read short names).
MONTH_WORDS = {"de": {"mrz": 3}, "fr": {"jun": 6, "jul": 7}}
# After the day and before the year.
NAMED_MARKS = {
    "hr": (".", "."),
    "en": ("-", "-"),
    "en-GB": ("-", "-"),
    "de": (". ", " "),
    "fr": ("-", "-"),
    "it": ("-", "-"),
    "es": ("-", "-"),
}


@dataclass(frozen=True)
class Language:
    """The language a computation reads and writes text in; the year of the computation, in
    which a date written without its year falls, as Excel reads it when it recalculates; and
    the code page CHAR and CODE count characters by, which Excel takes from Windows, not from
    the language (cp1250 on a Croatian Windows, whatever the regional format)."""

    code: str
    year: int
    code_page: str


class Typed(NamedTuple):
    """The number a typed text reads as, and the number format Excel gives the cell it is typed
    in as the text writes it: "1.250,5" #,##0.00 in Croatian, "12 €" its currency, "1.2.2026"
    the short date; "" for none, the General format."""

    value: float
    format: str = ""


class _Number(NamedTuple):
    value: float
    format: str
    places: bool


def marks(locale: str) -> tuple[str, str]:
    """The decimal mark and the group separator of the language."""
    return MARKS[locale]


def entered(digits: str, power: int = 0) -> float | None:
    """A typed number as Excel takes it, times ten to the power given (two less for a percent):
    the digits past the fifteenth significant one turn to zeros, not rounded; None where its
    first digit stands more than PLACES_MOST places before or after the decimal mark, a zero
    where its exponent is past them, however long the exponent (VALUE("1E308"), VALUE("1E-310")
    and VALUE("0E-309") are #VALUE!, VALUE("1E-309") and VALUE("0E308") 0); 0 below the
    smallest normal double, which Excel does not keep."""
    if (
        not power
        and len(digits) <= 15
        and digits.isascii()
        and digits.replace(".", "", 1).isdigit()
    ):
        return float(digits)
    mantissa, _, written = digits.upper().partition("E")
    exponent = max(-POWER_MOST, min(int(written or 0) + power, POWER_MOST))
    exact = Decimal(f"{mantissa}E{exponent}")
    if not -PLACES_MOST <= exact.adjusted() + bool(exact) <= PLACES_MOST:
        return None
    if exact:
        exact = exact.quantize(Decimal(1).scaleb(exact.adjusted() - 14), rounding=ROUND_DOWN)
    value = float(exact)
    return value if abs(value) >= SMALLEST else 0.0


def numeral(value: float, mark: str = ".", width: int = WRITTEN) -> str:
    """A number in its fifteen significant digits as the General format writes it within a
    width, which counts the digits and the decimal mark but not the sign (ECMA-376 Part 1,
    §18.8.30): plain while the digits fit, else plain rounded to the width, else with an
    exponent where the whole part does not fit or a fraction below 1E-04 would show fewer
    digits plain."""
    digits = Decimal(f"{abs(value):.15g}").normalize()
    if not digits:
        return "0"
    sign = "-" if value < 0 else ""
    power = digits.adjusted()
    if power < width:
        decimals = max(-digits.as_tuple().exponent, 0)
        whole = max(power + 1, 1)
        if whole + (decimals and decimals + 1) <= width:
            return sign + _plain(digits, mark)
        if power >= -4:
            rounded = digits.quantize(Decimal(1).scaleb(-max(width - whole - 1, 0)), ROUND_HALF_UP)
            if rounded.adjusted() < width:
                return sign + _plain(rounded.normalize(), mark)
    return sign + _exponent(digits, mark, width)


def _plain(digits: Decimal, mark: str) -> str:
    return format(digits, "f").replace(".", mark)


def _exponent(digits: Decimal, mark: str, width: int) -> str:
    power = digits.adjusted()
    # Excel gives an exponent of 99, of either sign, the room of three digits (General writes
    # 1,23456789E-99 as 1,2346E-99, 9,99999E-99 as 1E-98, 1,23456789E-98 as 1,23457E-98).
    room = width - len(f"E+{abs(power):02d}") - (abs(power) == 99)
    mantissa = digits.scaleb(-power).quantize(Decimal(1).scaleb(-max(room - 2, 0)), ROUND_HALF_UP)
    if mantissa >= 10:
        mantissa, power = mantissa / 10, power + 1
    return f"{_plain(mantissa.normalize(), mark)}E{'+' if power >= 0 else '-'}{abs(power):02d}"


def _whole(locale: str) -> str:
    """A whole number as the language writes it, its groups marked by the language's own mark,
    each of three digits or more after a first that is no zero: "1.2345" and "01.2345" are 12345
    in Croatian, "1.23" and "0.123" no number but a date or nothing."""
    return rf"0*[1-9]\d*(?:{re.escape(marks(locale)[1])}\d{{3,}})+|\d+"


def _number_pattern(locale: str) -> re.Pattern:
    return re.compile(
        rf"(?P<int>{_whole(locale)})?"
        rf"(?:{re.escape(marks(locale)[0])}(?P<frac>\d*))?(?:[eE](?P<exp>[+-]?\d+))?"
    )


_number = cache(_number_pattern)


@cache
def _fraction(locale: str, alone: bool) -> re.Pattern:
    """A whole number, one space, and a fraction, its numbers of up to five digits and up to
    FRACTION_MOST; with `alone`, the fraction without the whole number too."""
    whole = rf"(?P<whole>{_whole(locale)}) "
    return re.compile(
        rf"{f'(?:{whole})?' if alone else whole}(?P<above>\d{{1,5}})/(?P<below>\d{{1,5}})"
    )


EURO = "€"


class _Own(NamedTuple):
    sign: str
    before: bool
    spaced: bool


@cache
def _own(locale: str) -> _Own:
    """The sign of the currency of the language's country, whether the language writes it
    before the number, and whether a space parts them."""
    country = icu.Locale(locale)
    country.addLikelySubtags()
    symbols = icu.DecimalFormatSymbols(country)
    sign = symbols.getSymbol(icu.DecimalFormatSymbols.kCurrencySymbol)
    written = icu.NumberFormat.createCurrencyInstance(country).toPattern()
    before = written.index("¤") < written.index("#")
    return _Own(sign, before, bool(re.search(r"[#0]\s¤|¤\s[#0]", written)))


def currency_sign(locale: str) -> str:
    """The sign of the currency of the language's country (hr €, en $)."""
    return _own(locale).sign


@cache
def _currency(locale: str, criterion: bool) -> re.Pattern:
    """A number with a currency sign before or after it, as Excel takes it: the euro on either
    side in every language, the sign of the language's country where the language writes it
    ("$12" in English, not "12$"; no "$12" in Croatian), a number's sign and spaces before
    either, and spaces between a sign before and the number's own sign ("€  - 386" is -386); a
    criterion takes the language's own alone ("12 €" in Croatian, no "€12")."""
    own = _own(locale)
    before, after = (set(), set()) if criterion else ({EURO}, {EURO})
    (before if own.before else after).add(own.sign)
    before = "|".join(map(re.escape, sorted(before))) or "(?!)"
    after = "|".join(map(re.escape, sorted(after))) or "(?!)"
    return re.compile(
        rf"(?P<sign>[+-]?) *(?P<before>{before}) *(?P<ahead>.+)|(?P<behind>.+?) *(?P<after>{after})"
    )


@cache
def money(locale: str, places: bool = False, red: bool = True) -> str:
    """An amount in the currency of the language's country as Windows formats it, Excel's
    built-in currency formats 5 to 8 as the language shows them: with places or without, a
    negative amount in red or not."""
    own = _own(locale)
    quoted, gap = f'"{own.sign}"', "\\ " if own.spaced else ""
    number = GROUPED_PLACES if places else GROUPED
    positive = quoted + number if own.before else number + gap + quoted
    negative = "[Red]" if red else ""
    if locale in BRACKETED:
        return rf"{positive}_);{negative}\({positive}\)"
    return rf"{positive};{negative}\-{positive}"


# Excel's built-in currency formats by their ids: with places or without, a negative amount in
# red or not.
MONEY_IDS = {5: (False, False), 6: (False, True), 7: (True, False), 8: (True, True)}


def built_in_money(id: int, code: str | None, locale: str) -> str:
    """Excel's built-in currency format `id` as a file gives it, which Excel shows in the
    regional format it runs in whatever the file's code says: as `money` where the code names
    no currency or the language's own, else as the code writes it, keeping its currency."""
    if code is None or _own(locale).sign in code:
        return money(locale, *MONEY_IDS[id])
    return code


def _signed(
    text: str, locale: str, bare: Callable[..., _Number | None], criterion: bool = False
) -> Typed | None:
    """A number with its sign, spaces after it, or in brackets for a negative one, never both,
    and a currency (_currency) or a percent before or after it, never both ("€1%" is no
    number), within the brackets or around them ("(€1)" and "€(1)" are -1), the number itself
    read by `bare` two powers of ten less for the percent; its format the currency's or the
    percent's, with places where it has them, an exponent's over either; an amount in the
    language's own currency where the language writes it takes the currency's format, any other
    the General format, as Excel gives them ("€12" in Croatian, "12 €" in English)."""
    negative = _bracketed(text)
    if negative:
        text = text[1:-1].strip(" ")
    percent, own = False, None
    if found := _currency(locale, criterion).fullmatch(text):
        ahead = bool(found["ahead"])
        currency = _own(locale)
        own = (found["before"] if ahead else found["after"]) == currency.sign
        own = own and ahead == currency.before
        text = found["sign"] + found["ahead"] if ahead else found["behind"]
    elif ahead := re.fullmatch(r"([+-]?) *% *(.+)", text):
        text, percent = ahead[1] + ahead[2], True
    elif percent := text.endswith("%"):
        text = text.removesuffix("%").rstrip(" ")
    if not negative and (negative := _bracketed(text)):
        text = text[1:-1].strip(" ")
    sign = text[0] if text[:1] in ("+", "-") else ""
    number = bare(text[len(sign) :].lstrip(" "), power=-2 * percent)
    if number is None:
        return None
    value = -number.value if sign == "-" else number.value
    if negative:
        if sign:
            return None
        value = -value
    format = number.format
    if format != SCIENTIFIC and percent:
        format = PERCENT_PLACES if number.places else PERCENT
    elif format != SCIENTIFIC and own is not None:
        format = money(locale, bool(number.places)) if own else ""
    return Typed(value, format)


def _bracketed(text: str) -> bool:
    return text.startswith("(") and text.endswith(")")


@cache
def _month_first(locale: str) -> bool:
    """Whether the language writes the month before the day (en Oct 27, not hr 27. lis)."""
    pattern = icu.DateFormat.createDateInstance(icu.DateFormat.MEDIUM, icu.Locale(locale))
    pattern = pattern.toPattern()
    return pattern.index("M") < pattern.index("d")


_PART = re.compile(r"\d+|[^\W\d_]+")
_COMMA = re.compile(r" *, +")


class _Written(NamedTuple):
    numbers: re.Pattern
    order: str
    marks: str
    spaced: re.Pattern


def short_day(locale: str) -> str:
    """The pattern of a date as Windows writes it short in the language (hr d.M.yyyy, en
    M/d/yyyy)."""
    return SHORT_DAYS[locale]


def day_mark(locale: str) -> str:
    """The mark between the numbers of the language's short date: hr the point, en the slash."""
    return next(each for each in short_day(locale) if each not in "dMy '")


@cache
def _day(locale: str) -> _Written:
    """The pattern of a date as the language writes it short, its year optional, its numbers
    parted by one of the language's own mark, a slash or a dash in any mix, spaces around it;
    the order of its day, month and year, as ICU knows it with the language's own mark (hr
    d.M.y and the point, en M/d/y and the slash); those marks as a pattern's class; and what
    parts a named month from its numbers: nothing, or spaces around at most one of the marks."""
    pattern = short_day(locale)
    order = "".join(dict.fromkeys(each for each in pattern if each in "dMy"))
    own = day_mark(locale)
    marks = "[" + re.escape("".join(dict.fromkeys(own + "/-"))) + "]"
    mark = rf" *{marks} *"
    numbers = re.compile(rf"(\d{{1,4}}){mark}(\d{{1,4}})(?:{mark}(\d{{1,4}}))?", re.ASCII)
    return _Written(numbers, order, marks, re.compile(rf" *(?:{marks} *)?"))


@cache
def short_months(locale: str, tagged: bool = False) -> tuple[str, ...]:
    """Each month's short name as Windows writes it where it differs from ICU's, without the point
    that closes it but as a [$-tag] names it (fr janv, [$-40C] janv.)."""
    names = MONTHS_SHORT.get(locale)
    if names is None:
        symbols = icu.DateFormatSymbols(icu.Locale(locale))
        alone = icu.DateFormatSymbols.STANDALONE
        names = symbols.getMonths(alone, icu.DateFormatSymbols.ABBREVIATED)[:MONTHS_A_YEAR]
    return tuple(name if tagged else name.removesuffix(".") for name in names)


def short_days(locale: str, tagged: bool = False) -> tuple[str, ...]:
    """Each weekday's short name from Sunday, as short_months names the months."""
    names = DAYS_SHORT.get(locale) or DAYS.get(locale)
    if names is None:
        symbols = icu.DateFormatSymbols(icu.Locale(locale))
        alone = icu.DateFormatSymbols.STANDALONE
        names = symbols.getWeekdays(alone, icu.DateFormatSymbols.ABBREVIATED)[1:]
    return tuple(name if tagged else name.removesuffix(".") for name in names)


@cache
def _months(locale: str) -> tuple[tuple[str, frozenset[str]], ...]:
    """Each month's full name standing alone (hr listopad, not the listopada of a written date)
    and the words Excel reads as it besides, in lower case."""
    symbols = icu.DateFormatSymbols(icu.Locale(locale))
    alone = icu.DateFormatSymbols.STANDALONE
    full = symbols.getMonths(alone, icu.DateFormatSymbols.WIDE)[:MONTHS_A_YEAR]
    also = MONTH_WORDS.get(locale, {})
    return tuple(
        (name.lower(), frozenset(word for word, at in also.items() if at == month))
        for month, name in enumerate(full, 1)
    )


def _month(name: str, locale: str) -> int | None:
    """The first month whose full name a name of NAMED_LEAST letters at least starts (Oct and
    Octo are October, hr vel veljača, fr jui juin) or which Excel reads it as besides (de Mrz)."""
    name = name.lower()
    if len(name) < NAMED_LEAST:
        return None
    return next(
        (
            month
            for month, (full, also) in enumerate(_months(locale), 1)
            if full.startswith(name) or name in also
        ),
        None,
    )


def read(text: str, language: Language, criterion: bool = False) -> float | None:
    """The number a text reads as in the language (typed), as Excel reads a typed or given one
    or, with `criterion`, a criterion's; None for text that is none."""
    found = typed(text, language, criterion)
    return None if found is None else found.value


def typed(
    text: str, language: Language, criterion: bool = False, numeric: bool = False
) -> Typed | None:
    """The number a text reads as in the language and the format it implies: a number with its
    signs, groups, percent or currency, a whole number and a fraction (5 6/2026 is 5 and
    6/2026, where no space parts a date), a date, a time, or a date and a time; typed in a cell
    holding a number's format (`numeric`), a fraction alone too (1/2 is a half there, a date in
    General)."""
    given = text.lstrip(" ")
    if not given.rstrip(" "):
        return None
    found = _read_number(given.rstrip(" "), language.code, criterion, numeric)
    if found is not None:
        return found
    return _moment(given, language)


def moment(text: str, language: Language) -> float | None:
    """The serial of the date, the time or the date and time a text names (_moment)."""
    found = _moment(text, language)
    return None if found is None else found.value


def _moment(text: str, language: Language) -> Typed | None:
    """The date, the time or the date and time a text names, the day and the time added as
    Excel adds them, at any space between them where the date comes first, as the time reads
    them where it does; None for any other text, a number among them, and for ten numbers or
    words or more (5 lipanj 2026 1:45 5 5 5 5 is nine). Spaces after it count: "6 A, " is 6 AM
    in English, "6 A," no time. A day with a time takes its format by _timed."""
    given = text.lstrip(" ")
    if len(_PART.findall(given)) > COUNTED_MOST:
        return None
    if (found := _read_day(given.rstrip(" "), language)) is not None:
        return found
    if (found := _read_time(given, language)) is not None:
        return found
    for gap in re.finditer(r" +", given):
        day = _read_day(given[: gap.start()], language)
        if day is not None and (time := _read_time(given[gap.end() :], language, True)) is not None:
            return Typed(day.value + time.value, _timed(time.format))
    return None


def read_marked(text: str, decimal: str, group: str, language: Language) -> float | None:
    """A number as NUMBERVALUE reads it with the marks given: its spaces, tabs and line breaks
    dropped and its groups before the decimal mark, in its exponent too (NUMBERVALUE("1,5e3,5") is
    1.5E+36 in English), each percent sign after it a hundredth (NUMBERVALUE("1,5%%";",") is
    0.00015, NUMBERVALUE("% %.";",";".") 0), taken once the number is read and 0 below the smallest
    normal double (NUMBERVALUE("5E-308%") is 0, VALUE("5E-308%") #VALUE!), then brackets, a sign, a
    currency or a percent as VALUE takes them, no group after the decimal mark nor a decimal mark
    after the exponent; else as VALUE reads it with the decimal mark given turned into the
    language's own and a group after it left as it is (NUMBERVALUE("1:45.5,5 lis 2026";".") is
    #VALUE! in Croatian): NUMBERVALUE("5-6%") is 5 June in hundredths, NUMBERVALUE("15:21.6";",")
    15:216 and NUMBERVALUE("1.5";",";";") 1 May in Croatian, NUMBERVALUE("18:19,04.") 18:19,04 there
    with its closing mark, NUMBERVALUE("1 PM") #VALUE! as "1PM" is no time."""
    text = re.sub("[ \t\n\r]", "", text)
    whole, point, places = text.partition(decimal)
    text = whole.replace(group, "") + point + places
    bare = text.rstrip("%")
    hundredths = len(text) - len(bare)
    if not bare:
        return 0.0
    grouped = partial(_grouped, decimal=decimal, group=group)
    if found := _signed(bare, language.code, grouped):
        value = found.value
    else:
        whole, point, places = bare.partition(decimal)
        own = marks(language.code)[0]
        places = places.replace(decimal, own)
        if (value := read(whole + (own if point else "") + places, language)) is None:
            return None
    value /= 100**hundredths
    return value if abs(value) >= SMALLEST else 0.0


def _grouped(text: str, decimal: str, group: str, power: int) -> _Number | None:
    whole, point, places = text.partition(decimal)
    if group in places or "." in whole + places:
        return None
    written = (whole + ("." if point else "") + places).lower()
    if not re.fullmatch(r"(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?", written):
        return None
    mantissa, _, exponent = written.partition("e")
    value = entered(f"{mantissa}e{exponent or 0}", power)
    return None if value is None else _Number(value, "", False)


def _read_number(
    text: str, locale: str, criterion: bool = False, alone: bool = False
) -> Typed | None:
    return _signed(text, locale, partial(_bare, locale=locale, alone=alone), criterion)


def _bare(text: str, locale: str, power: int, alone: bool = False) -> _Number | None:
    """A number without its signs, and the format it implies: a whole number and a fraction
    the fraction's of as many places as the fraction is over (# ?/? for 1 1/2, # ??/?? for
    1 1/12), an exponent the scientific, groups the grouped number's with places where they
    follow the decimal mark; with `alone`, a fraction without the whole number too."""
    if fraction := _fraction(locale, alone).fullmatch(text):
        whole = entered(re.sub(r"\D", "", fraction["whole"] or "0"), power)
        above, below = int(fraction["above"]), int(fraction["below"])
        if whole is None or not below or max(above, below) > FRACTION_MOST:
            return None
        # Where the space groups, three digits after it are read as a group of a whole that is
        # not naught: fr 1 999/2 is no number, 0 999/2 is (cases-fr.xlsx).
        if whole and marks(locale)[1] == " " and len(fraction["above"]) > 2:
            return None
        format = FRACTION if below < 10 else FRACTION_TWO
        return _Number(whole + above / below / 10**-power, format, False)
    found = _number(locale).fullmatch(text)
    if not found or not (found["int"] or found["frac"]):
        return None
    whole = re.sub(r"\D", "", found["int"] or "0")
    places = f".{found['frac']}" if found["frac"] else ""
    value = entered(f"{whole}{places}e{found['exp'] or 0}", power)
    if value is None:
        return None
    format = ""
    if found["exp"] is not None:
        format = SCIENTIFIC
    elif whole != (found["int"] or "0"):
        format = GROUPED_PLACES if found["frac"] else GROUPED
    return _Number(value, format, bool(found["frac"]))


def _read_day(text: str, language: Language) -> Typed | None:
    """A date as the language writes it short, or year first where the first of three numbers
    has four digits, or with the month named. Of two numbers the first reads as the day and
    month in this year, else as the month and year on its first day, as "10/27" is 1 October
    2027, where a language writing the day first takes the second as a year only where it is no
    month ("5/0" is 1 May 2000 in English, no date in Croatian); a year of one or two digits
    falls in the hundred years from 1930."""
    written = _day(language.code)
    order = written.order
    if not (found := written.numbers.fullmatch(text)):
        return _read_named(text, language)
    first, second, third = found.groups()
    if third is not None:
        order = "yMd" if len(first) == 4 else order
        parts = dict(zip(order, (first, second, third), strict=True))
        return _dated(parts["y"], parts["M"], parts["d"], SHORT_DATE)
    parts = dict(zip(order.replace("y", ""), (first, second), strict=True))
    if (day := _dated(str(language.year), parts["M"], parts["d"], DAY_MONTH)) is not None:
        return day
    parts = dict(zip(order.replace("d", ""), (first, second), strict=True))
    if order.startswith("d") and int(parts["y"]) <= MONTHS_A_YEAR:
        return None
    return _dated(parts["y"], parts["M"], "1", MONTH_YEAR)


def _read_named(text: str, language: Language) -> Typed | None:
    """A date with its month named: after its day, its year optional, or before its year; before its
    day too where the language writes the month first, its year then after a comma. Of the three a
    comma before a space may follow the month, the day before the year where the month comes first,
    the day before the month where one or a date mark follows the month too, but not the day-first
    order of a language writing the month first: hr 27 lis, 2026, 27, lis-2026, de 1, Feb, 1904 and
    en Oct, 27, 2026 are dates, en 27 Oct, 2026, hr 27, lis 2026 and lis, 2026 are not. One number
    before the month is its day in this year; one after it the day in this year where the language
    writes the month first, else the year on the month's first."""
    parts = _PART.findall(text)
    gaps = _PART.split(text)
    if gaps[0] or gaps[-1]:
        return None
    named = [at for at, part in enumerate(parts) if not part.isdigit()]
    if named not in ([0], [1]) or len(parts) not in (2, 3):
        return None
    month = _month(parts[named[0]], language.code)
    if month is None:
        return None
    first = _month_first(language.code)
    ahead = named == [0]
    written = _day(language.code)
    spaced = written.spaced
    commas = [bool(_COMMA.fullmatch(gap)) for gap in gaps[1:-1]]
    if not all(_COMMA.fullmatch(gap) or spaced.fullmatch(gap) for gap in gaps[1:-1]):
        return None
    if len(parts) == 2 or first and not ahead:
        allowed = set()
    elif ahead:
        allowed = {named[0], 1}
    else:
        allowed = {0, 1} if commas[1] or re.search(written.marks, gaps[2]) else {1}
    if any(comma and at not in allowed for at, comma in enumerate(commas)):
        return None
    numbers = [part for part in parts if part.isdigit()]
    if ahead and not first:
        return _dated(numbers[0], str(month), "1", MONTH_YEAR) if len(numbers) == 1 else None
    if len(numbers) == 2:
        if ahead and not commas[1]:
            return None
        return _dated(numbers[1], str(month), numbers[0], DAY_MONTH_YEAR)
    this_year = _dated(str(language.year), str(month), numbers[0], DAY_MONTH)
    if this_year is not None or not ahead:
        return this_year
    return _dated(numbers[0], str(month), "1", MONTH_YEAR)


def _dated(year: str, month: str, day: str, format: str) -> Typed | None:
    if len(year) not in (1, 2, 4) or len(month) > 2 or len(day) > 2:
        return None
    whole = int(year) + ((2000 if int(year) < CENTURY_TURN else 1900) if len(year) < 4 else 0)
    found = dated(whole, int(month), int(day))
    return None if found is None else Typed(float(found), format)


_FIRST = re.compile(r"[0-9]+")
_NEXT = re.compile(r" *: *([0-9]+)")
_HALF = re.compile(r" +([AaPp][Mm]?)(?![^\W\d_])")
_BEYOND = (24, 60, 60)


class _Ends(NamedTuple):
    fraction: re.Pattern
    closing: re.Pattern
    point: re.Pattern
    lead: re.Pattern
    halved: re.Pattern
    overflow: re.Pattern
    dropped: re.Pattern


@cache
def _ends(locale: str) -> _Ends:
    """What may follow a time's numbers in the language: the fraction of a second after its
    decimal mark, spaces around it; spaces around one closing mark, a colon, a date mark or a
    comma before a space, or the decimal mark alone; spaces or one date mark or comma before a
    space ahead of a date, nothing ahead of a month's name, after AM or PM or seconds read twice
    also the decimal mark or nothing; the decimal mark or a colon before digits after AM or PM,
    which Excel overflows on; numbers of up to four digits parted by spaces, a date mark or a
    comma before a space, after a date, which are dropped."""
    decimal = re.escape(marks(locale)[0])
    dates = _day(locale).marks
    joint = rf" *(?:{dates}|,(?= ))? *"
    return _Ends(
        re.compile(rf" *{decimal} *([0-9]+)"),
        re.compile(rf" *(?::|{dates}|,(?= ))? *"),
        re.compile(rf" *{decimal} *"),
        re.compile(rf" *(?:{dates}|,(?= )) *| +|(?=[^\W\d_])"),
        re.compile(rf" *(?:{dates}|,(?= )|{decimal})? *"),
        re.compile(rf" *(?:{decimal}|:) *[0-9]"),
        re.compile(rf"(?:{joint}[0-9]{{1,4}}(?![0-9]))+{joint}"),
    )


def _read_time(text: str, language: Language, dated: bool = False) -> Typed | None:
    """A time of day as Excel reads it in the language, read as far as it goes: hours, minutes and
    seconds of up to four digits each, none of three or four below 100 ("0100" is a hundred, "001"
    nothing), spaces around their colons, the seconds to the millisecond after the language's
    decimal mark, spaces around it, minutes and seconds where two numbers have one (1:45,5 in
    Croatian), hours and minutes where a colon and a number follow the fraction, its digits then the
    seconds too and the number dropped (1:45,52:5 is 1:45:52,52); past 23, 59 and 59 one of them at
    most, carried over, none with AM or PM (A, P), which spaces part from it. One mark may close it,
    a colon making one number a time, the decimal mark where a fraction does not end it; a date may
    follow (1:45/5/6/2026 and 1:45. 5/6/2026 are 5 June at 1:45 in Croatian, 1:45, 5/6/2026 and
    1:45:5/6/2026 1 June at 1:45,5 and 1:45:05), after AM or PM at once, or after the decimal mark
    where a fraction precedes (1:45 PM5/6 and 1:45,5 PM,5/6). Where a date comes first, numbers of
    up to four digits after it are dropped (5.6.2026 1:45 5/5 is 5 June at 1:45), but no colon nor
    AM or PM after them, nor a decimal mark ending one, and of three or four digits none below 100.
    A decimal mark ahead of the date wants a number after it (23:30, lipanj 2026 is nothing in
    Croatian) unless a fraction, AM or PM or seconds read twice precede (de 13:27,58, Dez-2575 is
    December at 0:13:27,58). After those or the dropped number, a decimal mark and digits keep the
    fraction's number but give it their count of digits, the digits read by their value as the first
    number of a date that follows (1:45,05 A,5/6 is 5 June at 1:45,5, 1:45,0 A,0005/6 5 June,
    5.6.2026 1:45,5 PM,2026 12:01:45,0005, rounded to ,001); a fraction so given keeps 16 bits of
    its number with their sign, nothing where they are negative (1:45,65541 A,5/6 is 5 June at
    1:45,5 as 1:45,05 A,5/6 is, 1:45,32768 A,5/6 nothing). Its format (_clock) is the date and
    time's where a date follows."""
    ends = _ends(language.code)
    if not (found := _FIRST.match(text)):
        return None
    parts, fraction, twice, at = [found[0]], None, False, found.end()
    while True:
        if len(parts) < 3 and (found := _NEXT.match(text, at)):
            twice = fraction is not None
            parts.append(found[1])
        elif fraction is None and len(parts) > 1 and (found := ends.fraction.match(text, at)):
            fraction = found[1]
        else:
            break
        at = found.end()
    half, scale, rescaled = None, len(fraction or ""), False
    if found := _HALF.match(text, at):
        half, at = found[1][0].upper(), found.end()
        if fraction is None and ends.overflow.match(text, at):
            return None
        if fraction and dated and (found := ends.fraction.match(text, at)):
            scale, at, rescaled = len(found[1]), found.end(), True
    rest, day = text[at:], None
    closed = ends.closing.fullmatch(rest) or (
        (fraction is None or half or twice) and ends.point.fullmatch(rest)
    )
    if not (half or len(parts) > 1 or (closed and ":" in rest)):
        return None
    if not closed and dated:
        if not ends.dropped.fullmatch(rest):
            return None
        if not all(_clock_part(number) for number in re.findall("[0-9]+", rest)):
            return None
    if not closed and not dated:
        lead = (ends.halved if half or twice else ends.lead).match(rest)
        if lead is None:
            return None
        written = rest[lead.end() :].rstrip(" ")
        if marks(language.code)[0] in lead[0]:
            first = _FIRST.match(written)
            if not (half or twice):
                if first is None and fraction is None:
                    return None
            elif fraction is None:
                return None
            elif first:
                scale, written = len(first[0]), str(int(first[0])) + written[first.end() :]
                rescaled = True
        if (day := _read_day(written, language)) is None:
            return None
    if not all(_clock_part(part) for part in parts):
        return None
    numbers = [int(part) for part in parts]
    if twice:
        numbers[2] = int(fraction)
    elif fraction and len(numbers) == 2:
        numbers.insert(0, 0)
    hours, minutes, seconds = [*numbers, 0, 0][:3]
    beyond = tuple(map(int.__ge__, (hours, minutes, seconds), _BEYOND, strict=True))
    if half:
        if hours > 12 or minutes > 59 or seconds > 59:
            return None
        hours = hours % 12 + (12 if half == "P" else 0)
    elif sum(beyond) > 1:
        return None
    given = int(fraction or 0)
    if rescaled and (given := given % WRAPPED) > FRACTION_MOST:
        return None
    exact = (seconds + Decimal(given).scaleb(-scale)).quantize(Decimal("0.001"), ROUND_HALF_UP)
    time = (hours * 3600 + minutes * 60 + float(exact)) / SECONDS_A_DAY
    format = _clock(beyond, bool(half), len(parts) == 3, fraction is not None)
    if day is None:
        return Typed(time, format)
    return Typed(day.value + time, _timed(format))


def _timed(format: str) -> str:
    """The format of a date typed with a time: none where the time's hours, minutes or seconds
    carry, the time's own where it has a fraction of a second, else the date with the time."""
    return {"": "", DURATION: "", TENTHS: TENTHS}.get(format, MOMENT)


def _clock(beyond: tuple[bool, bool, bool], half: bool, seconds: bool, fraction: bool) -> str:
    """The format of a typed time: none where its minutes or seconds carry, the hours past a
    day's where its hours do, with its seconds where they are written, to a tenth where a
    fraction of a second is."""
    if beyond[1] or beyond[2]:
        return ""
    if beyond[0]:
        return DURATION
    if fraction:
        return TENTHS
    if half:
        return HALVES_SECONDS if seconds else HALVES
    return CLOCK_SECONDS if seconds else CLOCK


def _clock_part(part: str) -> bool:
    return len(part) <= CLOCK_DIGITS and (len(part) < 3 or int(part) >= 100)
