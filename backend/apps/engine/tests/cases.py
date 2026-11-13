"""The workbook of cases Excel computes for us (D22): a sheet of data and a sheet of formulas for
each category of functions, one formula a row in column A. `python -m apps.engine.tests.cases
<file>` writes it without values; saved by Excel, which writes the value of each formula beside it,
under the regional format of each document language, it comes here as cases-<language>.xlsx, the
references the engine is held to. The sheet Locale holds what depends on the language Excel ran in;
its first cell tells which. The Read sheets hold every text a number, a fraction, a date or a time
can be written as, made of each part's values on both sides of every bound a rule draws (a digit
more, 12 and 13, 59 and 60, 32767 and 32768) and of every mark that can stand between them, so that
what Excel reads is taken as a whole, not case by case. The Read sample sheets hold texts drawn at
random from all those forms, as written, changed by a character or three, or numbers, marks and
words in any order: the engine is made to read those it was built on as Excel did, and a sample
drawn after them, counted before it is looked at, tells how much of what Excel reads it still
misses. Read bounds holds every power of ten around the limits a number's exponent meets and the
fractions around the 16 bits a fraction read as a number keeps, Read words each word a date or a
time is read with in each place a part of a time takes, Read arithmetic the mixed fractions the
orders they may be computed in tell apart, Read short names each month's short name in every
language and others a reading may hold, and a named month among commas, Read joined names a date
with its month named right after a time or after a comma ending its fraction of a second, and as
NUMBERVALUE reads them with marks given, Read codes what TEXT makes of each letter, name and mark a
format may be written with in the language, of fractions built of every kind of part and every place
a mark takes in them and after them, of fractions without a whole part about the counts 16 and 32
bits hold, of denominators written with zeros, about 16 bits or mixed of placeholders and digits,
of fractions of nothing a group mark after them or after their whole part scales, of a space before
each sign, group marks apart from the placeholders, after decimal marks or after literals, ? and #
placeholders between group marks and marks where no placeholder is, of every condition on each side
of its bound alone and among others and of bounds however written, of text in each section, of
negatives that round to nothing in a section of a condition
and in the ones after it, of exponents with group marks and of 0 in every exponent, of the days of
the Hijri calendar and the first days Excel counts in both calendars, of the weekday each writes
alone and among a date's other codes and where it begins the code, of calendars and digits beside
text, of the names of every month and weekday each calendar writes in each language of the suite
and Arabic, its [$-tag] alone, before or after the calendar's letter, and under the tags of other
languages, and the longest texts TEXT writes."""

import itertools
import string
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from random import Random

import icu
from openpyxl import Workbook

from apps.engine import formats
from apps.engine.parse import parse, written
from apps.engine.tests.saved import LANGUAGES, TOLD

PATHS = {code: Path(__file__).with_name(f"cases-{code}.xlsx") for code in LANGUAGES}
HIDDEN_ROW = 12

DATA = {
    "A": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    "B": [1, "2", True, None, 5.5, -3, "abc", 0, False, '=""'],
    "C": ["=1/0", "=NA()", 3, None, '=""', 7, "=SQRT(-1)", "x", 4, None],
    "D": [
        "apple",
        "Banana",
        "cherry",
        "date",
        "Elderberry",
        "fig",
        "grape",
        "apple pie",
        "  two  spaces ",
        "a*b",
    ],
    "E": ["North", "South", "North", "East", "South", "North", "West", "East", "North", "South"],
    "F": [100, 250, 75, 300, 125, 50, 400, 225, 175, 90],
    "G": [
        date(2024, 2, 29),
        date(2026, 1, 31),
        date(2026, 10, 27),
        date(1900, 3, 1),
        date(2025, 12, 31),
        date(2026, 3, 29),
        date(2000, 1, 1),
        datetime(2026, 10, 27, 13, 45, 30),
        date(2026, 12, 25),
        date(2027, 1, 1),
    ],
    "H": ["Code", 10, 20, 30, 40, 50],
    "I": ["Name", "Bread", "Milk", "Eggs", "Cheese", "Apples"],
    "J": ["Price", 1.2, 0.99, 2.5, 4.75, 1.8],
    "K": [date(2026, 12, 25), date(2026, 12, 26), date(2027, 1, 1)],
    "L": [2, 4, 4, 4, 5, 5, 7, 9],
    "M": [2.5, -2.5, 1.005, 2.675, 0.5, -0.5, 1234.5678, -1234.5678, 1e-10, 123456789012345],
    "N": [None] * 9 + [1, 2, 4, 8, "=SUBTOTAL(9,N10:N13)"],
    "O": [-1000, 300, 400, 500, 200],
}

GAPS = (
    *("", " ", "  ", "-", "/", ".", ",", ", ", " ,", ". ", " - ", ".-", " /", " .", "  -  ", " , "),
)
SIGNS = (
    "",
    "+",
    "-",
    "(",
    "€",
    "€ ",
    "-€",
    "€-",
    "+€",
    "%",
    "-%",
    "% ",
    "$",
    "-$",
    "$-",
    "£",
    "-£",
)
ENDS = ("", "%", " %", "%%", ")", "%)", "€", " €", "$", " $", "£", " £", "-", "+", "e")
SHAPES = (
    *("1", "0", "00012", "1,5", "1.5", ",5", ".5", "5,", "5.", "1.234", "1,234", "1.234,5"),
    *("1,234.5", "1.23", "1,23", "1.2345", "1,2345", "1 234", "1\u00a0234", "12.345.678"),
    *("12,345,678", "1.234.5", "1,234,5", "1e3", "1E3", "1,5e3", "1.5e3", "1e+3", "1e-3", "1e"),
    *("e3", "1,5e3,5", "1.2.3", "1,2,3"),
)
PARTS = ("0", "1", "2", "01", "000001", "9999", "10000", "32767", "32768")
WHOLES = ("0", "1", "01", "-1", "+1", "12345", "1.234", "1,234", "1,5", "1.5", "123456789012345678")
SQUARE = (
    *("0", "00", "1", "01", "001", "2", "5", "12", "13", "29", "30", "31", "32", "59", "99"),
    *("100", "999", "1900", "2026", "9999", "10000", "02026"),
)
CUBE = ("0", "00", "1", "01", "001", "12", "13", "31", "32", "99", "100", "2026", "10000")
CALENDAR = [
    text
    for day in ("28", "29", "30", "31")
    for month in ("2", "4")
    for year in ("1900", "2024", "2026", "24", "0", "00")
    for text in (f"{day}/{month}/{year}", f"{month}/{day}/{year}", f"{year}/{month}/{day}")
] + [
    f"{a}/{b}"
    for day in ("28", "29", "30", "31")
    for month in ("2", "4")
    for a, b in ((day, month), (month, day))
]
MONTHS = {
    "hr": (
        *("siječanj", "veljača", "ožujak", "travanj", "svibanj", "lipanj", "srpanj", "kolovoz"),
        *("rujan", "listopad", "studeni", "prosinac", "sij", "velj", "ožu", "tra", "svi", "lip"),
        *("srp", "kol", "ruj", "lis", "stu", "pro", "siječnja", "veljače", "ožujka", "travnja"),
        *("svibnja", "lipnja", "srpnja", "kolovoza", "rujna", "listopada", "studenoga", "studenog"),
        *("prosinca", "ozujak", "ozu", "sijecanj", "sij.", "LIS", "Lis", "lIs", "listop"),
    ),
    "en": (
        *("January", "February", "March", "April", "May", "June", "July", "August", "September"),
        *("October", "November", "December", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug"),
        *("Sep", "Oct", "Nov", "Dec", "Sept", "Febr", "OCT", "oct", "oCt", "Octo", "Oct."),
    ),
}


def _named(code: str, *also: str) -> tuple[str, ...]:
    """The months' names ICU writes in the language, full and short, in a date and alone, with
    others Windows or a writer may use."""
    symbols = icu.DateFormatSymbols(icu.Locale(code))
    return tuple(
        dict.fromkeys(
            (
                *(
                    name
                    for context in (icu.DateFormatSymbols.FORMAT, icu.DateFormatSymbols.STANDALONE)
                    for width in (icu.DateFormatSymbols.WIDE, icu.DateFormatSymbols.ABBREVIATED)
                    for name in symbols.getMonths(context, width)[:12]
                ),
                *also,
            )
        )
    )


def _days(code: str) -> tuple[str, ...]:
    """The days' names ICU writes in the language, full and short."""
    symbols = icu.DateFormatSymbols(icu.Locale(code))
    return tuple(
        dict.fromkeys(
            name
            for width in (icu.DateFormatSymbols.WIDE, icu.DateFormatSymbols.ABBREVIATED)
            for name in symbols.getWeekdays(icu.DateFormatSymbols.FORMAT, width)
            if name
        )
    )


MONTHS |= {
    "de": _named("de", "Mrz", "MÄRZ", "Dezemb", "Sept"),
    "fr": _named("fr", "fevrier", "FÉVR.", "décem", "aout"),
    "it": _named("it", "GEN", "dicem", "sett"),
    "es": _named("es", "setiembre", "SEPT.", "diciem", "sept"),
}
NAMES = tuple(name for names in MONTHS.values() for name in names)
NAMED = (
    *("0", "00", "1", "01", "001", "6", "12", "13", "29", "31", "32", "99", "100", "2026"),
    *("02026", "10000"),
)
CLOCK = (
    *("0", "00", "1", "01", "001", "9", "12", "13", "23", "24", "59", "60", "99", "100", "9999"),
    *("10000",),
)
SECONDS = ("0", "00", "59", "60", "99", "9999", "10000", "5,5", "5.5", "5,55555", "05,5")
NOON = (
    *("AM", "am", "Am", "aM", "A", "a", "PM", "pm", "P", "p", "A.M.", "P.M.", "AM.", "prijepodne"),
    *("popodne", "dop", "pop"),
)
DAYS = (
    *("5/6/2026", "5.6.2026", "5. 6. 2026", "6 lis 2026", "6 Oct 2026", "Oct 6, 2026"),
    *("2026/6/5", "5/6"),
)
TIMES = ("1:45", "13:45:30", "1:45 PM", "1 PM", "1:45:30,5", "1:45:30.5")
LEADING = (
    *("000", "0000", "0001", "001", "0100", "01", "099", "0099", "0999", "010", "0010", "100"),
    *("999", "1000", "9999"),
)
MILLISECONDS = (
    *("0,0005", "0,0015", "0,0025", "0,00049", "0,00051", "0,1234", "0,12345", "59,9994"),
    *("59,9995",),
)
CLOSINGS = (":", " :", ": ", "::")
NOONS = ("A.", "P.", "PM.", "p.", "PM..", "a.m.", "AM.M", "AMM")
TAILS = (
    *(".5", "/5", "-5", ".", ".55555", ".5.5", ",5.5", ".5,5", ".55", ".555", ".5555", "/55"),
    *("/5555", "/55555", "-5555", "-55555", ".5.5.5", "/5/5", "-5-5", "/5.5", ".5/5", "-5/5"),
    *(",", ",5,", ".5.", "./5", ",.5", ",5/5", ",/5", ".5:", "/5:", " .5", " /5", ":.5", ":/5"),
)
HALVES = ("A", "P", "a", "p", "AM", "PM")
ENDING = (" ", ",", ".", "/", "5", ":", "A")
AHEAD = ("-", " ", "€", "(", "%")
BEHIND = (")", " ", "%", "€")
JOINS = (" ", ",", ".", "/", "-", ":")
PIECES = (" ", ",", ", ", ".", "/", "-", ":", "5", "2026", "55555", "A", " PM", "5/6", "5/6/2026")
JOINED = (
    *("1:45", "1:45:30", "1:45,5", "1:45.5", "1:45 PM", "6 PM"),
    *("5/6/2026 1:45", "5/6/2026 1:45 PM", "5/6/2026 1:45,5", "5/6/2026 1:45.5"),
)
SECONDS_TWICE = ("0", "05", "5", "50", "052", "5205", "1234567")
DROPPED = ("0", "05", "099", "100", "5555", "05555")
SCALED = ("0", "05", "5", "50", "500", "5000", "0005", "55555", "123456")
HALVED = ("", ",", ".", ", ", ". ", " ,", "-", "/")
LATER = ("5/6", "5/6/2026", "27.10.2026", "2026-10-27", "27 lis 2026", "Oct 27, 2026")
COUNTED = ("5 lipanj 2026", "5 June 2026", "June 5, 2026", "2026-6-5", "5/6/2026")
SCALED_LARGE = (
    *("9999", "65535", "65536", "86399", "86400", "99999", "100000", "131071", "131072"),
    *("327679", "327680", "655359", "655360", "863999", "864000", "999999", "1000000"),
    *("0000001", "0000100", "1234567", "12345678"),
)


def _spelled(alphabet: tuple[str, ...], longest: int, shortest: int = 1) -> list[str]:
    """Every string of `shortest` to `longest` letters of the alphabet."""
    return [
        "".join(letters)
        for length in range(shortest, longest + 1)
        for letters in itertools.product(alphabet, repeat=length)
    ]


BLANKS = ("\t", "\u00a0", "\u202f")
BEFORE = ("-", "€", "%", "(", "$", "£")
AFTER = ("%", "€", ")", "$", "£")
DECORATIONS = [
    (ahead, behind)
    for ahead in ("", *BEFORE, *(a + b for a in BEFORE for b in BEFORE))
    for behind in ("", *AFTER, *(a + b for a in AFTER for b in AFTER))
]
SAMPLED = 40_000
SAMPLES = 12
MANTISSAS = ("1", "5", "0001", "4287", "100000", "999999999999999", "0")
WRAPPING = ("32766", "32767", "32768", "32769", "65535", "65536", "98303", "98304", "98305")
BOUNDS = (
    *("0", "1", "2", "5", "6", "9", "10", "11", "12", "13", "23", "24", "25", "28", "29", "30"),
    *("31", "32", "59", "60", "61", "99", "100", "999", "1000", "1899", "1900", "1904", "1929"),
    *("1930", "1999", "2000", "2026", "2029", "2030", "9999", "10000", "32767", "32768", "65535"),
    *("65536", "86399", "86400", "99999", "100000", "999999", "1000000", "1234567"),
)
WEEKDAYS = (
    *("ponedjeljak", "utorak", "srijeda", "četvrtak", "petak", "subota", "nedjelja", "pon", "uto"),
    *("sri", "čet", "pet", "sub", "ned", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"),
    *("Saturday", "Sunday", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    *(name for code in ("de", "fr", "it", "es") for name in _days(code)),
)
PLACED = (
    *("W:13", "W :13", "W: 13", "W:13:14", "W:13:14,5", "W:13:14.5", "W:13,5", "W:13.5"),
    *("W:13 PM", "W:13 5/6/2026", "5/6/2026 W:13", "W:", "W :", "W::13"),
    *("1:W", "1: W", "1 :W", "1:W:14", "1:W,5", "1:W.5", "1:W PM", "1:W 5/6/2026"),
    *("5/6/2026 1:W", "1:13:W", "1:13: W", "1:13:W,5", "1:13:W.5", "1:13:W PM"),
    *("5/6/2026 1:13:W", "6 W,5", "6 W.5", "6 W:5", "1:13 W,5", "1:13 W.5", "1:13 W:5"),
)
SOUP = (
    *(" ", " ", "  ", ":", ",", ".", "/", "-", "+", "%", "€", "$", "(", ")", "e", "E", "T", "x"),
    *("\t", " ", ", ", ". ", " - ", "£", "\u202f"),
)
MUTANTS = (*"0123456789 :,./-+%€$£()eETAPMapmx", "\t", " ", "\u202f")


# A named month among commas, as February's first three letters in each language write it.
COMMAED = (
    *("1, {}, 1904", "1, {} 1904", "1 {}, 1904", "1, {}, 1904 12:42", "{}, 1, 1904", "{}, 1 1904"),
    *("1,{},1904", "1 ,{} ,1904", "1, {},1904", "1 , {} , 1904", "1, {}", "{}, 1904", "1, {}, 04"),
)
# Short names of months other than Windows' own, which a language's own reading may hold.
OTHER_SHORT = (
    *("velj", "velj.", "vlj.", "vel.", "ožuj", "Mär", "Mär.", "Mrz.", "Maer", "Mae", "Okt."),
    *("Dez.", "févr", "févr.", "janv", "janv.", "juil", "juil.", "sept.", "mag.", "giu."),
    *("ene.", "abr.", "set", "sep", "Sept", "Sep.", "Febr", "Febr.", "Jän", "Jänner"),
)
# Tuesday 27 October 2026 at 13:45:56,789, each of its parts told apart from the others.
MOMENT = "DATE(2026,10,27)+TIME(13,45,56)+0.789/86400"
# The General format's name in the document languages and others.
GENERAL_NAMES = (
    *("General", "general", "GENERAL", "Standard", "standard", "Estándar", "Estandar"),
    *("Generale", "Général", "Allgemein", "Općenito", "Opći", "G/Standard", "Standaard"),
)
TIMED_CODES = (
    *("dddd, mmmm dd, yyyy", "dddd. mmmm", "d, m", "m, y", "mmmm, yyyy", "dddd, mmmm"),
    *("mmmm d, yyyy", "TTTT, MMMM JJJJ", "TT.MM.JJJJ", "jjjj, mmmm aaaa", "jj/mm/aaaa"),
    *("gggg, mmmm aaaa", "gg/mm/aaaa", "dddd, mmmm aaaa", "dd/mm/aaaa", "hh:mm:ss.000"),
    *("hh:mm:ss,000", "ss.00", "ss,00", "[h]:mm", "[hh]:mm:ss", "h AM/PM", "h am/pm", "h A/P"),
    *("h a/p", "hh:mm AM/PM", "d.m.yyyy h:mm", "dd/mm/yyyy hh:mm", "HH:MM", "hh:MM", "HH:mm"),
    *("mm:ss", "MM:SS", "m:s", "M:S", "h:m", "h:M", "d.M", "d.m", "T.M", "T.m", "MM.JJ", "M/T"),
    *("B1dd/mm/yyyy", "B2dd/mm/yyyy", "B1", "B2", "a/P", "A/p", "h a/P", "yyyy0", "d1", "0 d"),
    *("dd0", "h0", "ss0", "0:mm", "mm:ss0", "d 1 m", "yyyy 2026"),
    *("[DBNum1]yyyy", "[DBNum2]yyyy", "[NatNum1]yyyy", "[DBNum1]dd/mm/yyyy hh:mm"),
)
NUMBER_CODES = (
    *("0.0", "0,0", "#,##0", "#.##0", "# ##0", "#,##0.00", "#.##0,00", "# ##0,00", "0 0"),
    *("# ?/?", "#?/?", "0 ?/?", "# ??/??", "?/?", "#\\ ?/?", "0.00E+00", "0,00E+00", "0%"),
    *("0.0%", "0,0%", "€0", "0 €", "@", '"x"0', "0_)", "0*-", "[Red]0", "[Rot]0", "[Rouge]0"),
    *("[Rosso]0", "[Rojo]0", "[Crvena]0", "[Color3]0", "[Farbe3]0", "[>100]0", '0;-0;"z"'),
    *("0;;;@", "#,##0,", "#.##0.", "0.0,", "00000", "#", "0", "0.", "0,", ".0", ",0", "x0", "0x"),
    *("00,000", "0,000", "00.000", "0.000", "00 000", "0 000", '0,"K"', "0,€", "0,x", '0.0,"K"'),
    *('0 "K"', "0 \\K", "0 ", "0  ", "0.0 ", "0,0 ", "#,?/?", "#.?/?", "# #?/?", "0.0.0", "0,0,0"),
    *(".0.0", ",0,0", "[DBNum1]0", "[Color0]0", "[Color56]0", "[Color57]0", "[color9]0"),
    *("[DBNum2]0", "[DBNum3]0", "[DBNum4]0", "[NatNum1]0", "[dbnum1]0", "[DBNum1][Red]0"),
    *("B10", "B20.00", "B1#,##0", "b10", "0B1", "0 B2"),
)
# Parts of one in the formats of fractions, every thousandth and every tenth of a prime
# denominator's, so that Excel tells which fraction it writes where the nearest is not the
# last convergent of the part's continued fraction, nor any before 0/1's next.
FRACTION_CODES = ("# ?/?", "# ??/??", "?/?")
FRACTION_PARTS = (
    *(f"{part}/1000" for part in range(1, 1000)),
    *(f"{part}/9973" for part in range(1, 9973, 10)),
)
# Fractions of every kind of part beside every other, so that Excel tells how each is written:
# the whole part, the marks between it and the numerator, the numerator and the denominator, and
# spaces about the slash.
FRACTION_SHAPES = (
    *dict.fromkeys(
        f"{whole}{parting}{numerator}/{denominator}"
        for whole in ("", "#", "0", "?", "##", "#0")
        for parting in ("", " ", "\\ ", ".", "-", '"x"')
        for numerator in ("?", "#", "0", "#?", "??", "?#", "0?")
        for denominator in ("?", "??", "8")
    ),
    *("# ? /?", "# ?/ ?", "# ? / ?", "? /?", "?/ ?", '# ?/?"x"', "# ?/? "),
)
FRACTION_VALUES = ("0.5", "1.5", "-0.5", "0", "12.25", "0.01", "1234.5678")
# A space after a number's last placeholder before each kind of sign and literal: French
# groups by it, and scales by it but before its currency's sign.
SPACED_CODES = (
    *("0 €", "0 $", "0 £", "0 %", "0 -", "0 (", "0 _)", "0 *x", '0 "€"', "0 \\€", "0 [$€]"),
    *("0 [$€-40C]", "0 [$$-409]", "0 € ", "0  €", "0,0 €", "0.0 €", "# ##0 €", "0 x", "0 ;"),
    *("0 €;-0 €", "0 e", "0 \\ ", '0 " "', "0 _€"),
)
SPACED_VALUES = ("1234.5678", "-1234.5678", "0.5")
# The days the Hijri calendar of B2 writes: one in every 997 from 1900 to 9999, every day of 2020
# to 2029, where the tabular calendars and Umm al-Qura part, and the days about 29 February 1900.
HIJRI_DAYS = (*range(0, 2_958_466, 997), *range(43_831, 47_484), 59, 60, 61)
# A calendar before each code of a date in each language's letters, and the calendars with no
# code after them or lowercase.
CALENDAR_CODES = tuple(
    f"{calendar}{code}"
    for calendar in ("B2", "b2", "B1", "b1")
    for code in (
        *("yyyy", "yy", "e", "mmmm", "mmm", "mmmmm", "dddd", "ddd", "d", "m", "JJJJ", "MMMM"),
        *("TTTT", "aaaa", "jjjj", "gggg", "[$-409]mmmm", " dd/mm/yyyy"),
    )
)
# Conditions some value meets none of, and what a section without one takes.
CONDITION_CODES = (
    *("[>100]0", "[<0]0;[>100]0", "[>100]0;[<-100]0", "[>100]0;[<-100]0;0.0", "[>100]0;0.0"),
    *("[<-100]0", "[=50]0", "[>100]0;[<-100]0;0.0;@", '[>100]"big";"small"', "[>=50]0.0;0"),
)
CONDITION_VALUES = ("50", "-50", "1234.5678", "-1234.5678", "0")
# Negative numbers that round to nothing, in each kind of section.
ZERO_CODES = (
    *("0", "0.00", "0,00", "#", "#,##0", "0%", "0.0E+00", "0,0E+00", "# ?/?", '0"x"', "0;0"),
    *("0;(0)", '0;"neg"0', "0.0,", "#,##0,"),
)
ZERO_VALUES = ("-0.4", "-0.004", "-0.00004", "-0.6")
TAGGED_CODES = (
    *("[$-F800]", "[$-F800]0", "[$-F800]dddd", "[$-F400]", "[$-F400]0", "[$-409]mmmm"),
    *("[$-407]mmmm", "[$-40C]mmmm", "[$-41A]mmmm", "[$-409]dddd, mmmm dd, yyyy"),
)

# A day in each month of both calendars, the fifteenth of 2026's and about the fifteenth of
# 1448's in the Hijri one, and a week from Sunday, written with every language's letters.
GREGORIAN_MONTHS = tuple(f"DATE(2026,{month},15)" for month in range(1, 13))
HIJRI_MONTHS = tuple(str(46_203 + round(29.53 * month)) for month in range(12))
WEEK = tuple(f"DATE(2026,10,{day})" for day in range(25, 32))
MONTH_NAMES = ("mmmm", "mmm", "mmmmm", "MMMM", "MMM", "MMMMM")
DAY_NAMES = ("dddd", "ddd", "TTTT", "TTT", "jjjj", "jjj", "gggg", "ggg", "aaaa", "aaa")
# Every language of the suite and Arabic, by the tag naming it, alone, before and after each
# calendar's letter.
NAMED_TAGS = ("409", "809", "41A", "407", "40C", "410", "C0A", "401")
NAMED_CALENDARS = {
    "B2": (
        "B2",
        "b2",
        *(f"B2[$-{tag}]" for tag in NAMED_TAGS),
        *(f"[$-{tag}]B2" for tag in NAMED_TAGS),
    ),
    "B1": ("B1", *(f"B1[$-{tag}]" for tag in NAMED_TAGS), *(f"[$-{tag}]B1" for tag in NAMED_TAGS)),
    "": tuple(f"[$-{tag}]" for tag in NAMED_TAGS),
}
# The first days Excel counts, about its 29 February 1900, in each calendar.
FIRST_DAYS = range(62)
FIRST_CODES = tuple(
    f"{calendar}{code}"
    for calendar in ("B2", "B1")
    for code in (
        "dd/mm/yyyy",
        "TT.MM.JJJJ",
        "jj/mm/aaaa",
        "dd/mm/aaaa",
        "gg/mm/aaaa",
        "dddd",
        "TTTT",
    )
)
# The weekday each calendar writes alone and among a date's other codes, in every language's
# letters for the day, the month and the year, about Excel's 29 February 1900; and the date a tag
# before or after a calendar's letter writes.
WEEKDAY_CODES = tuple(
    dict.fromkeys(
        code
        for day, month, year in (
            ("d", "m", "y"),
            ("T", "M", "J"),
            ("j", "m", "a"),
            ("g", "m", "a"),
            ("d", "m", "a"),
        )
        for code in (
            f"B2{day * 4}",
            f"B2{day * 3}",
            f"B2{day * 2} {day * 4}",
            f"B2{day * 4} {day * 2}",
            f"B2{month * 2} {day * 4}",
            f"B2{year * 4} {day * 4}",
            f'B2{day * 4}"x"',
            f'B2"x"{day * 4}',
            f"B2{day * 4} {month * 4}",
            f"B2{day * 4} hh:mm",
            f"B2[$-409]{day * 4}",
            f"B1{day * 4}",
            f"B1{day * 2} {day * 4}",
            *(
                f"{prefix}{day * 2}/{month * 2}/{year * 4}"
                for tag in ("409", "401", "41A")
                for prefix in (f"[$-{tag}]B2", f"B2[$-{tag}]", f"[$-{tag}]B1")
            ),
        )
    )
)
WEEKDAY_VALUES = ("0", "1", "2", "7", "59", "60", "61", "100", "46203")
# A calendar beside text, or alone among other codes.
CALENDAR_TEXTS = (
    *("B1@", "B2@", "@B1", 'B1"x"', "b1@", "B2;B1", "B1;;;@", '"x"B1@', '@"x"B1', "@ B1"),
    *("@B2", "@b1", "B1@B1", "0;0;0;@B1", "0;0;0;B1@", '"x"@B1', "@B12", "@\\B1", '@"B1"'),
)
CALENDAR_TEXT_VALUES = ("5", "-5", '"abc"')
# Each condition on each side of its bound, alone, before a section without one, after another
# condition and between them, and before a section of text alone.
CONDITIONED = tuple(
    form.format(f"[{op}{bound}]")
    for op in ("<", "<=", ">", ">=", "=", "<>")
    for bound in ("-100", "0", "100")
    for form in ("{}0", "{}0;0", "[>1000]0;{}0", "{}0;[>1000]0;0", '{}"x"', "{}0.0")
)
CONDITIONED_VALUES = ("-150", "-100", "-50", "-0.5", "0", "50", "100", "150", "1500")
# Each condition on 0, bounds near it and between 0 and 100, alone, before a section without one
# and before sections that tell themselves apart, where negatives round to nothing or do not.
NEAR_CONDITIONED = tuple(
    form.format(f"[{op}{bound}]")
    for op in ("<", "<=", ">", ">=", "=", "<>")
    for bound in ("0", "-1", "1", "-50", "50")
    for form in ("{}0", "{}0;0", '{}0;"x"0', '{}0.0;"x"0', '{}0;"x"0;"z"0', '{}?/?;"x"0')
)
NEAR_CONDITIONED_VALUES = (
    *("-75", "-50", "-25", "-1", "-0.5", "0", "0.5", "1", "25", "50", "75"),
    *("-0.4", "-0.004", "-0.04", "-0.49", "-0.51", "-1.4", "0.4"),
)
# Exponents with group marks among the integer places, in either language's marks.
GROUPED_EXPONENTS = (
    *("#,##0E+00", "0,0E+00", "0,00E+00", "00,0E+00", "0,000E+00", "0,0,0E+00", "#,##0.0E+00"),
    *("#.##0E+00", "0.0E+00", "0.00E+00", "00.0E+00", "0.000E+00", "0.0.0E+00", "#.##0,0E+00"),
    *("##0,0E+00", "##0.0E+00", "0,0000E+00", "0.0000E+00"),
    *("000,000E+00", "0,00000E+00", "00,0000E+00", "0,0,0,0E+00", "00000,0E+00", "0,000000E+00"),
    *("000.000E+00", "0.00000E+00", "00.0000E+00", "0.0.0.0E+00", "00000.0E+00", "0.000000E+00"),
    *("#,##0,000E+00", "##,##0.0E+00", "#.##0.000E+00", "##.##0,0E+00", "0,0E+000", "0.0E+000"),
    *("000000E+00", "#####0E+00", "0000000E+00"),
)
GROUPED_EXPONENT_VALUES = (
    "0",
    "0.4",
    "5",
    "1234.5678",
    "12345678",
    "0.000123",
    "-0.004",
    "123456789012",
    "98765.4321",
    "1E-10",
    "-123456.789",
)
# Group marks after the placeholders apart from them by a literal, a sign or another mark.
APART_CODES = (
    *("0,x,", '0,"K",', "0,€,", "0, ,", "0,%,", "0%,", "0,%", "0,,x", "0,x", "0,$,", "0,\\,"),
    *("0 x ", "0 € €", "0 \€ ", '0 "€" ', "0 € x", '0 "€x"', '0 "x€"', "0 $ ", "0 _€ ", "0  x"),
    *("0.x.", "0.€.", "0. .", "0.%.", "0..x"),
    *("0.,", "0.,,", "0.0,", "0.00,", "#.##,", "0. ,", "0.x,", "0.%,", "0,.", "0,..", "0,0."),
    *("0,00.", "0, ", "0,  ", "0,0 ", "0.0.,", "0,0,."),
)
APART_VALUES = ("1234567.891", "-1234567.891", "0.5", "999.5", "1234")
# Fractions with whole parts of two placeholders, and a mark in each place about the slash.
WIDE_FRACTIONS = tuple(
    f"{whole}{parting}{numerator}/{denominator}"
    for whole in ("??", "00", "?0", "0?", "#?")
    for parting in (" ", "-")
    for numerator in ("?", "#", "0", "??")
    for denominator in ("?", "8")
)
WIDE_FRACTION_VALUES = ("0.5", "0", "12.25", "-0.004", "-0.5", "1.5")
MARKED_FRACTIONS = (
    *("?,/?", "?/,?", "?/?,", "? /?", "?/ ?", "?/? ", "#,?/?", "# ? /?", "?.?/?", "?/.?"),
    *("?/?.", ".?/?", ",?/?", " ?/?", "# ?,/?", "# ?/,?", "# ?./?", "# ?/.?", "?/? ?"),
)
MARKED_FRACTION_VALUES = ("0.5", "1.5", "0")
# Fractions with a group or a decimal mark after their last placeholder.
TRAILED_FRACTIONS = (
    *("?/?,", "# ?/?,", "#/8,", "?/?,,", "??/??,", "?/?.", "?/? ", "# ?/?.", "# ?/? ", "?/8 "),
    "?/8.",
)
TRAILED_FRACTION_VALUES = (
    *("0", "0.5", "1.5", "1000", "500", "2000", "0.0001", "0.000000001", "-0.5", "3"),
    *("1234567", "-0.0001", "-1000"),
)
# Fractions without a whole part about the counts 32 bits hold, and of negatives rounding to none.
BOUND_FRACTIONS = (
    *("?/?", "?/ ?", "0/8", "#/100", "??/??", "?/???", "0/?", "#?/?", '"x"?/?', "?/?;-?/?"),
    *("?/?;(?/?)", "# ?/?", "0 0/8"),
)
BOUND_FRACTION_VALUES = (
    *("-0.004", "-0.04", "-0.4", "0.004", "999999999", "1000000000", "2147483647", "2147483648"),
    *("2147483647.4", "-2147483648", "-2147483649", "4294967296", "12345678901", "-12345678901"),
    *("268435455", "268435456", "268435456.4", "21474836", "21474837", "1234567.891"),
)
SWAPPED = str.maketrans(",.", ".,")
# The weekday B2 writes where one begins the code, beside each kind of other code, after a literal
# and after a tag, in every language's letters.
WEEKLY_CODES = tuple(
    dict.fromkeys(
        code
        for day, month, year in (
            ("d", "m", "y"),
            ("T", "M", "J"),
            ("j", "m", "a"),
            ("g", "m", "a"),
            ("d", "m", "a"),
        )
        for code in (
            f"B2{day * 4} {month * 3}",
            f"B2{day * 4} {month * 5}",
            f"B2{day * 4} {month}",
            f"B2{day * 4} {month * 2}",
            f"B2{day * 3} {month * 4}",
            f"B2{day * 4} {year * 4}",
            f"B2{day * 4}/{month * 2}/{year * 4}",
            f"B2{day * 4} {day * 4}",
            f"B2{day * 3} {day * 3}",
            f"B2{day} {day * 4}",
            f"B2h {day * 4}",
            f"b2{day * 4} {month * 4}",
            f'B2" "{day * 4} {month * 4}',
            f"B1{day * 4} {month * 4}",
            *(
                f"B2[$-{tag}]{day * 4}{after}"
                for tag in ("401", "40C", "409", "41A")
                for after in ("", f" {month * 4}")
            ),
            *(f"[$-{tag}]B2{day * 4} {month * 4}" for tag in ("401", "409")),
        )
    )
)
# Text beside digits, escaped calendars, literals and calendars, with numbers and text.
TEXT_CODES = (
    *("@1", "1@", "@\\1", '@"1"', "\\1@", "@0", "0@", "@#", "@?", "@\\B", "@\\B2", "\\B1@"),
    *('@"x"', '"x"@', '"x"@"y"', '@ "x"', "[$-409]B1@", 'B1"x"@', "B2@;0", "@;@", "B1 @", "B1@ "),
)
TEXT_VALUES = ("5", "-5", "0.5", '"abc"')
# Each condition on 0 and bounds about it, before sections that tell themselves apart, a second
# of a condition, text, a group mark scaling a number to nothing, a percent and a fraction, about
# the negatives that round to nothing in each.
OPPOSED_CONDITIONED = tuple(
    form.format(f"[{op}{bound}]")
    for op in ("<", "<=", ">", ">=", "=", "<>")
    for bound in ("0", "-0.5", "0.5", "-100", "100")
    for form in (
        *('{}0;"x"0;"z"0', '{}0.0;"x"0;"z"0', '{}0;"x"0;"z"0;@', '{}0;[<-5]"x"0;"z"0'),
        *('{}0,;"x"0', '{}0%;"x"0', '{}#;"x"0', '{}?/?;"x"0;"z"0', '{}0;0;"z"0'),
    )
)
OPPOSED_VALUES = (
    *("-0.4", "-0.04", "-0.5", "-0.49", "-0.51", "-1.4", "-400", "-499", "-500", "0", "0.4"),
    *("1", "-1", "-50", "50", "-100", "100", "150", "-150", "-0.004"),
)
# Denominators given with zeros in them, or among placeholders.
DENOMINATED = (
    *("?/10", "?/100", "?/1000", "#/20", "?/101", "?/08", "?/80", "?/10?", "?/1?0", "?/0", "?/00"),
    *("# ?/10", "# ?/100", "?/100 ", "0/100", "??/100"),
)
DENOMINATED_VALUES = ("0", "0.5", "0.123", "1.5", "-0.04", "12.345", "0.004")
# Counts over denominators given about the bounds of 16, 24 and 32 bits, and of free ones about 32.
FIXED_BOUNDS = (
    *("?/2", "?/8", "?/100", "#/8", "0/8", "?/8;-?/8", "?/32767", "?/32768", "?/99999"),
    "?/2;(?/2)",
)
FIXED_BOUND_VALUES = tuple(
    dict.fromkeys(
        f"{count / denominator:.15g}"
        for denominator in (2, 8, 100, 32767, 32768, 99999)
        for count in (9999, 32767, 32768, 65535, 65536, 99999, 1000000, 8388607, 8388608)
    )
) + ("-4096", "-4095.875", "1.5")
FREE_BOUNDS = ("?/?", "??/??", "?/???", "# ?/?", "0/?", "?/?;-?/?")
FREE_BOUND_VALUES = (
    *("1073741823", "1073741824", "2147483646", "2147483646.5", "1500000000.5", "1000000000.5"),
    *("2147483645.5", "1073741823.5", "715827882.333333", "-2147483646", "-2147483646.5"),
    *("2147483646.4", "429496729.6", "2147483646.9", "1000000000.3333333", "1000000000.25"),
    *("1500000000.25", "715827882.5", "1073741824.5", "2147483646.6", "1431655765.5"),
)
# Fractions with a whole part a group mark follows, in either language's marks, about numbers
# their fraction writes as nothing.
SCALED_FRACTIONS = tuple(
    dict.fromkeys(
        code
        for each in (
            *("# ?/?,", "# ?/8,", "0 ?/?,", "# ?/?,,", "# #/?,", "# 0/?,", "?? ?/?,", "# ??/??,"),
            *("# ?/?, ", "0 0/8,"),
        )
        for code in (each, each.translate(SWAPPED))
    )
)
SCALED_FRACTION_VALUES = (
    *("0.04", "0.05", "0.06", "0.001", "0.01", "0.0001", "0.00015", "1E-300", "1E-250"),
    *("1E-253", "1E-254", "1E-200", "0.0123456789", "-0.000000001", "0.9999", "1.0001", "0.5"),
    *("1", "123456.0001"),
)
# Exponents of every kind of integer and decimal places, for 0 and numbers about it.
ZERO_EXPONENTS = (
    *("#E+0", "#.#E+0", "##0E+0", "###E+00", "#0.0E+00", "0.0E+00", "00E+00", "?E+00", "??0E+00"),
    *("##E+00", "#.##E-00", "####E+00", "#####E+00", "0.##E+00", "#,##0E+00", "#.##0E+00"),
    *("?.?E+00", "#?E+00"),
)
ZERO_EXPONENT_VALUES = ("0", "1E-300", "-0.0000001", "5")
# A group mark after the placeholders that a decimal mark follows apart from it, and ? and #
# placeholders about group marks, in either language's marks.
PARTED_GROUPS = tuple(
    dict.fromkeys(
        code
        for each in (
            *("0, .", "0,x.", "0,%.", '0,"x".', "0, ,.", "#,##0 .", "0,0x.", "0, .0", "0,x.0"),
            *("0,x.00", "0,,x.", "0, x.", "0,x .", "0,x,.", "#, .", "?, .", "0,x.,", "0,x.."),
            *("?,?#0", "?,##0", "#,?#0", "?,#?0", "??,?#0", "?,???,?#0", "#?,?#0", "?#,##0"),
            *("?,#00", "?,##?"),
        )
        for code in (each, each.translate(SWAPPED))
    )
)
PARTED_VALUES = (
    *("1234567.891", "-1234567.891", "0.5", "999.5", "1234", "0", "5", "12", "123", "12345"),
    *("123456", "-5", "0.4"),
)
# Marks where no placeholder is, in either language's marks.
MARKS_ALONE = tuple(
    dict.fromkeys(
        code
        for each in (",", '","', '"x","y"', ",,", '" ",', "\\,", ".", '"a".', '"x"."y"', " ")
        for code in (each, each.translate(SWAPPED))
    )
)
MARKS_ALONE_VALUES = ("5", "-5", "0", "0.5")
# Placeholders of ? that a number of nothing leaves empty.
BLANK_CODES = ("?", "??", "?.?", "#?", "?#", "?0", "?,?", "?.??", "??,???", "? ?")
BLANK_VALUES = ("0", "-0.4", "0.4", "5", "-5")
# Placeholders of ? between group marks, in either language's marks.
PADDED_GROUPS = (
    *("??,???", "?,??0", "??,??0.00", "0?,??0", "?,???,???", "#,??0", "?,?#0"),
    *("??.???", "?.??0", "??.??0,00", "0?.??0", "?.???.???", "#.??0", "?.?#0"),
)
PADDED_GROUP_VALUES = ("0", "5", "12", "123", "1234", "12345", "123456", "-5", "0.4", "1234567")
# A condition's bound written with either language's marks, signs, spaces, exponents and letters.
WRITTEN_BOUNDS = tuple(
    f'[<{bound}]0;"x"0'
    for bound in (
        *("0.5", "0,5", "1.5", "1,5", "1.234", "1,234", "1,2,3", "1.2.3", "1 5", "5x", ".5", ",5"),
        *("-.5", "-,5", "5.", "5,", "+5", " 5", "1e2", "1E2", "1.5.5", "1,5,5", "-0.5", "-0,5"),
        *("05", "0.50", "1.5 ", "1.,5", "1,.5", "-1.5", "-1,5", "1.05", "1,05"),
    )
)
WRITTEN_BOUND_VALUES = (
    *("0", "0.4", "0.5", "0.6", "1", "1.04", "1.2", "1.4", "1.5", "1.6", "4", "5", "6", "-0.4"),
    *("-0.5", "-0.6", "-1.5", "100", "101", "1.234", "1.233", "1.235", "123", "1234", "1235"),
)
# Group marks after a literal, alone, in runs and among decimal places, in either language's marks.
LITERAL_GROUPS = tuple(
    dict.fromkeys(
        code
        for each in (
            *("0.x,,,", "0x,,", "0 ,,", "0.x, ,", '0"x",,', "0.0x,0", "0.x,,0", "0.0,x0", "0.x0,0"),
            *("0.,x.", "0x,0", "0x,00", "#x,##0", "0.x,", "0x,", "0x,,x", "0.0x,,", "0x,.0"),
            *("0 ,0", "0.0 ,", "0,x,", "0,x,,", "0x,,0", "0.x,x,", '0"x",0'),
        )
        for code in (each, each.translate(SWAPPED))
    )
)
LITERAL_GROUP_VALUES = (
    *("1234567.891", "-1234567.891", "0.5", "999.5", "1234", "0", "12345678", "1234567890"),
    "0.04",
)
# Text in each section of codes of two to five, and number sections a text meets.
TEXT_SECTIONS = (
    *("0;@", "0;0;@", "@;0;0", "0;@;0", "0;0;@;0", "@;", "0;@;", "0;;@", ";;;@", "@;;", ";@"),
    *("0;0;0;@;0", "0;0;0;0", "0;0;0;", '0;"x"@', '0;0;0;"x"', "#;#;#;@@"),
)
TEXT_SECTION_VALUES = ("5", "-5", "0.5", "0", '"abc"', '""')
# Fractions with a group mark after the whole part or among its placeholders, in either
# language's marks, about numbers that write as nothing once scaled and about the bounds of the
# scaling.
WHOLE_GROUPED = tuple(
    dict.fromkeys(
        code
        for each in (
            *("#,\\ ?/?", "#,,\\ ?/?", "0,\\ ?/?", '#,"x"?/?', "#\\ ,?/?", "#, ,?/?"),
            *("#,\\ ?/?,", "#,-?/?", "#,\\ 0/8", "##,\\ ?/?", "#,#\\ ?/?", "#,##0\\ ?/?"),
            *("#,##0 ?/?", "#,,,\\ ?/?"),
            *("?,\\ ?/?", "#,\\ ?/?;-#,\\ ?/?", "#,##0 ??/??", "#,##0.0 ?/?", "# ?/?,,,", "?/?,"),
        )
        for code in (each, each.translate(SWAPPED))
    )
)
WHOLE_GROUPED_VALUES = (
    *("0", "0.0001", "0.000001", "0.005", "1E-251", "1E-252", "1E-250", "0.5", "1234.5"),
    *("1234567.25", "-0.0001", "12", "-1234.5"),
)
# Denominators given about 16 bits and above, and free ones mixed of placeholders and digits.
GIVEN_DENOMINATORS = (
    *("?/65535", "?/65536", "?/65534", "?/40000", "?/98765", "?/123456", "?/70000", "#/65535"),
    *("# ?/65536", "# ?/40000", "?/0?", "?/?0", "?/#0", "?/0#", "?/000", "# ?/00", "?/?8", "?/8?"),
    *("?/#8", "?/0??", "# ?/0?", "?/?00", "??/0?"),
)
GIVEN_DENOMINATOR_VALUES = (
    *("0", "0.5", "0.123", "1.5", "0.99999", "12.345", "-0.04", "0.00001", "0.333333333333333"),
    *("0.0001234", "1.2345678"),
)
# A decimal mark between the whole part and the numerator over numerators of each placeholder
# and of several digits, whole parts mixed of placeholders, and marks among literals there.
POINTED_FRACTIONS = tuple(
    dict.fromkeys(
        code
        for each in (
            *(
                "#.\\ ??/??",
                "#.\\ #/?",
                "#.\\ 0/?",
                "#.\\ #?/?",
                "#.\\ 0?/?",
                "0.\\ ?/8",
                "#.\\ ?/8",
            ),
            *("?#.\\ ?/?", "#?.\\ ?/?", "0#.\\ ?/?", "#0.\\ ?/?", "#.\\ .?/?", "#\\ .\\ ?/?"),
            *("#.,\\ ?/?", '#."x"??/??"y"', "#.\\ ?/?;0", "#\\ ,\\ ?/?", "#\\ ,,?/?", '#,"x",?/?'),
            *("0,0\\ ?/?", "#,##0,\\ ?/?", "#,##0 ?/?,", "?,??0 ??/??", "#,##0.\\ ?/?"),
        )
        for code in (each, each.translate(SWAPPED))
    )
)
POINTED_FRACTION_VALUES = (
    *("0", "0.5", "1234.5", "12", "-1234.5", "0.0001", "1234.5678", "0.123", "5.25", "-0.5"),
    "99.99",
)
# Placeholders after the denominator past a literal, in runs that mix them.
LATER_PLACEHOLDERS = (
    *('?/?"x"0?0', '?/?"x"#?#', '?/?"x"0??', '??/?"x"?', '?/?"x"?0?', '?/?"x"#0#', '?/?"x"?#?'),
    *("?/? 0?0", "?/?-#?#", '?/?"x"??0', '?/?"x"0#?', '"€Y"7851539637/7*x522607"%yA;"'),
)
LATER_PLACEHOLDER_VALUES = ("0", "0.5", "1234.5678", "0.001234", "12.345", "-0.04", "1.5")
# Marks after a fraction's whole part before a fill, a tag, a fixed digit or more of the whole
# part, and exponents in a fraction's section or beside it.
FRACTION_MARKS = tuple(
    dict.fromkeys(
        code
        for each in (
            *("#.*x?/?", "#.[$-409]?/?", "#,*x?/?", "#,[$-409]?/?", "#,*x ?/?", "#,_x?/?"),
            *('0"x",0 ?/?', "0\\ ,0 ?/?", "#\\1,%?/?", "#\\1, ?/?", "#\\1,?/?", '#"x",#?/?'),
            *("0E+0 ?/?", "?/?E+0", "# ?/?;0E+0", "0E+0;# ?/?", "# ?/?;;;@E+0"),
        )
        for code in (each, each.translate(SWAPPED))
    )
)
FRACTION_MARK_VALUES = ("0", "0.5", "1234.5", "-1234.5", "12.25")
# A grouped whole part with placeholders after the denominator.
GROUPED_LATER = (
    *("#,##0 ?/?}0", '#,##0 ?/??"x"#"y"?', "#,##0 ??/??_ %0%0", "#,##0 ?/?0"),
    *("# ##0 ?/?}0", '# ##0 ?/??"x"#"y"?', "# ##0 ??/??_ %0%0", "# ##0 ?/?0"),
)
GROUPED_LATER_VALUES = (
    *("0", "0.5", "1234.5678", "12", "123456789.123", "32766.6", "0.001234"),
    "-1234.5",
)
# Marks alone where no placeholder is, and B2's weekday before a month written in each length.
DIGITLESS = tuple(
    dict.fromkeys(
        code
        for each in (",.", ".,", '"x".,', "..,", ".,.", ",.,", ",,.", ". ,", '.,"x"', "\\.,")
        for code in (each, each.translate(SWAPPED))
    )
)
DIGITLESS_VALUES = ("5", "-5", "0", "0.5", "1234567.891")
WEEKLY_MONTHS = tuple(
    dict.fromkeys(
        code
        for day, month in (("d", "m"), ("T", "M"), ("j", "m"), ("g", "m"))
        for code in (
            f"B2{day * 3} {month * 5}",
            f"B2{day * 4} {month * 6}",
            f"B2{day * 4} {month * 4} {month * 3}",
            f"B2{day * 4} {month * 3} {month * 4}",
            f"B2{day * 4} {month * 4} {month * 4}",
            f"B2{day * 4}{month * 4}",
            f"B2{day * 4} {day * 2} {month * 4}",
            f"B2{day * 4} h {month * 4}",
        )
    )
)
# Names of months and days under the tags of languages beyond the suite.
FOREIGN_TAGS = ("801", "C01", "1401", "40D", "41E", "411", "404", "419", "408", "429", "420", "41F")
FOREIGN_NAMES = tuple(
    f"[$-{tag}]{code}" for tag in FOREIGN_TAGS for code in ("mmmm", "dddd", "mmm", "ddd", "mmmmm")
)
FOREIGN_DAYS = ("DATE(2026,1,15)", "DATE(2026,5,15)", "DATE(2026,10,25)", "DATE(2026,10,28)")
# The longest texts TEXT writes, of numbers, of text and of codes about 255 characters.
LONG_TEXTS = (
    *(f'TEXT({value},"0")' for value in ("1E+253", "1E+254", "1E+255", "1E+300", "-1E+254")),
    *(f'TEXT({value},"0.0")' for value in ("1E+252", "1E+253", "-1E+252")),
    *(f'TEXT(1E+254,"{code}")' for code in ("0 ", '0"" ""', "#", "0;0", "General")),
    *(f'TEXT(REPT("a",{count}),"@")' for count in (254, 255, 256, 300)),
    *(f'TEXT(REPT("a",{count}),"@x")' for count in (254, 255)),
    *(f'TEXT(1,REPT("0",{count}))' for count in (253, 254, 255, 256)),
    *(f'TEXT(1,REPT("x",{count})&"0")' for count in (253, 254, 255)),
    *(f'TEXT(1,"0"&REPT(" ",{count}))' for count in (253, 254, 255)),
    *(f'TEXT(DATE(2026,5,15),"d"&REPT("x",{count}))' for count in (253, 254, 255)),
    *(f'TEXT("abc",REPT("x",{count})&"@")' for count in (253, 254, 300)),
    *(f'TEXT(1,REPT("""x""",{count})&"0")' for count in (50, 85, 86)),
)
# Codes about the longest Excel keeps: spaces and other literals on either side of the bound, a
# run of literals longer than its quote, marks Excel may keep bare, and runs of group marks about
# where the power of ten they scale by turns over.
LONG_CODES = (
    *(f'TEXT(1,"0"&REPT(" ",{count}))' for count in (126, 127, 128, 200, 251, 252)),
    *(f'TEXT(1,REPT("x",{count})&"0")' for count in (126, 127, 128, 200, 252)),
    *(f'TEXT(1,"0"&REPT("{mark}",200))' for mark in ("-", ":", "$", "(", "+", "/")),
    *(
        f'TEXT(1,"0"&REPT("{mark}",{count}))'
        for mark in (",", ".")
        for count in (42, 43, 44, 85, 86, 100, 170, 171)
    ),
)
# An ambiguous m before an elapsed time and after a language's own minute, an elapsed time after
# a clock's of each unit, and the noon marks run together.
ELAPSED_MINUTES = tuple(
    dict.fromkeys(
        code
        for each in (
            *("mm:.0[s]", "mm.0[s]", "mm:dddd[s]", "mm[s]", "mm:[s]", "h[h]", "[h]:[mm]"),
            *("m:ss[mm]", "mm:ss[m]", "ss[s]", "m:ssMM", "mssMM", "hmssMM", "ssMM", "MMss"),
            *("m MM ss", "mMM.0", 'h"x"m"y"ssMM', "MM:[ss]", "hh:MM[s]", "m:MM:s", "[h]m[ss]MM"),
            *("[h]:m:[ss] MM", "[h]m:ssMM"),
            *("A/PAM/PM", "AM/PMA/P", "A/P A/P", "hA/PA/P", "A/Pa/p", "AM/PM am/pm"),
        )
        for code in (each, each.translate(SWAPPED))
    )
)
ELAPSED_MINUTE_VALUES = ("0", "0.5", "1234.5678", "-1", "2.75")
# The first section's language tag over the later ones, a code of text alone, a section's system
# date or time beside another's, the noon marks after a number about a negative that writes as
# nothing, and an escaped question mark after a date's code.
TAG_SCOPES = tuple(
    dict.fromkeys(
        code
        for each in (
            *("[$-40C]mmm;[$-407]mmm", "General;0;mmm[$-41A]", '"x"A/P[$-409]@', "[$-41A]A/P"),
            *("0;[$-F800]#0", "[$-F400][>3]0;[$-F400]0", "[$-41A]0;A/P", "0;[$-41A]A/P"),
            *("0;0#A/P", "0;00,A/P", "0;0A/P", "0;A/P", "0;0.0A/P", "A/P;0", "0A/P;0"),
            *("[<5]0,A/P;0", "[<0]0,A/P", "[<0]0A/P", "[<5]0A/P;0", "[<0]0,A/P;0"),
            *("[hh]\\?/", "hh\\?/", "d\\?/", "[hh]\\?", "\\?/", "s\\?/", "\\?", "0\\?/"),
            '[Blue]General\\4sA/PsA/P"]"[hh]\\?/',
        )
        for code in (each, each.translate(SWAPPED))
    )
)
TAG_SCOPE_VALUES = ("0", "-1", "-0.5", "-0.4", "0.5", "5", "1234.5678", '"abc"')
# Sections of a colour, a condition or a tag alone in each place, and a slash beside text.
BARE_SECTIONS = (
    *("[Red];0", "0;[Red]", "0;0;[Red]", "0;0;0;[Red]", "[Red][$-409]", "[>3]", "[Red][>3]"),
    *("[>3];[Red]", "[$-409];0", "0;[$-409]", "[Red];[$-F400]", "[$-F400]@;0", "0;0;0;[$-F400]@"),
    *("@/", '@"x"@/', "@/x", '"x"/@', "@\\/", "@/*;", "@*;", "/@", "@//"),
)
BARE_SECTION_VALUES = ("0", "-1", "0.5", "5", "-1234.5678", '"abc"')
# Decimal marks past a denominator a % or a literal ended, and fractions of digits with no
# placeholder, over values whose numerators grow past the digits written.
DENOMINATOR_ENDS = tuple(
    dict.fromkeys(
        code
        for each in (
            *("?/?%.0", "?/?%.#", "?/?%.?", "?/?%.#0", "?/?%.0#", "?/?%.?0", '?/?"x".0'),
            *('?/?"x".#0', '?/?"x"0.0', '?/?"x"#.#', "?/?%,.0", "?/?%.,0", "?/?%..0", "?/?%.0.0"),
            *("# ?/?%.00", "?/??%.", "?/?\\x.0", "?/?*x.0", "?/?_x.0", "?/?[$-409].0"),
            *("81/7", "667694/81", "1/1", "5/4", "12/34", "1/23456", "123456/7", '"x"12/34'),
            *('12/34"x"', "12/3.4", '"x"61/{%1=.', "61/1=.", "12/3%", "0/0"),
        )
        for code in (each, each.translate(SWAPPED))
    )
)
DENOMINATOR_END_VALUES = (
    *("0", "1", "-1", "0.5", "9.99", "10", "99", "100", "1000", "12345.6", "-0.04", "0.001234"),
)
# Fractions whose whole part has a space between its placeholders (a group mark in a language
# that groups by a space) before a literal, a % or more placeholders, and placeholders past the
# denominator.
SPACED_WHOLES = (
    *('? 0"x"?0/??', '? 0"x"?/?', '# 0"x"?/?', "## 0%)0/?", '## 0%")"0/?}0', "### ?#%%?/?0#"),
    *("000 ??#%#/?", "0 #0?=#/??_ %0%0", "000 #%%0?/##%#0%", "# 0#%##/00?0", "# #_x?/?"),
    *("# ?%%#?0/0??#", "# ##x0/#>0", "0 0%?/?", "? #?/?", "0 ?\\x?/?"),
)
SPACED_WHOLE_VALUES = (
    *("0", "0.5", "1", "-0.5", "-1", "0.001234", "1234.5678", "-1234.5678", "12.25"),
)
# Every run of one to three placeholders after a denominator a literal or a literal and a decimal
# mark ended, over denominators that write blanks and that do not; runs after a first run; and a
# grouped whole part with placeholders after its denominator.
LATER_RUNS = tuple(
    f"?/{under}{apart}{''.join(run)}"
    for under in ("?", "??", "#")
    for apart in ('"x"', '"x".')
    for size in (1, 2, 3)
    for run in itertools.product("0#?", repeat=size)
) + tuple(
    f'?/?"x"{first}"y"{second}'
    for first in ("0", "?", "#", "0?", "?0")
    for second in ("0", "?", "#", "?#", "#?", "0?")
)
LATER_RUN_VALUES = ("0", "0.5", "1234.5678")
GROUPED_LATER_MORE = tuple(
    whole + later
    for whole in ("#,##0 ", "#,0 ", "# ##0 ")
    for later in (
        *("?/?}00", "?/?}#", "?/?}?", "?/?}0}0", '?/?"x"0', "?/?%0", "?/?-0", "?/?}0.0"),
        *('?/?"x"#"y"', '?/?"x"?', '?/??"x"0', "??/??}0", "?/?}0,"),
    )
)
GROUPED_LATER_MORE_VALUES = ("0", "0.5", "1234.5678", "1234567.25", "-0.5")
# Scaled fractions of numbers whose scaling runs past a double, which a cell showed as a fraction
# of nothing.
SCALED_OVERFLOWS = ("# ?/?,", "?/?,", "# ?/?,,", "# ?/8,", "#,\\ ?/?,", "0 ?/?,", "# ??/??,")
SCALED_OVERFLOW_VALUES = (
    *("1E+50", "1E+55", "1.79E+55", "1.8E+55", "1E+56", "1E+100", "1E+200", "1E+253"),
    *("1E+300", "-1E+253", "1E+52", "1E+58"),
)


def _number(rng: Random) -> str:
    """A whole number: a value on a bound some rule may draw or of one to seven random digits,
    now and then after leading zeros."""
    if rng.random() < 0.5:
        value = rng.choice(BOUNDS)
    else:
        value = str(rng.randrange(10 ** rng.randint(1, 7)))
    return "0" * rng.choice((0, 0, 0, 0, 0, 1, 2, 3)) + value


def _part(rng: Random, most: int, width: int = 1) -> str:
    """A part of a date or a time, mostly within its range."""
    if rng.random() < 0.8:
        value = str(rng.randint(0, most))
        return value.zfill(width) if rng.random() < 0.5 else value
    return _number(rng)


def _amount(rng: Random) -> str:
    if rng.random() < 0.3:
        group = rng.choice((".", ",", " ", " "))
        count = rng.randint(1, 3)
        text = str(rng.randint(1, 999)) + "".join(
            group + f"{rng.randrange(1000):03}" for _ in range(count)
        )
    else:
        text = _number(rng)
    if rng.random() < 0.4:
        text += rng.choice(",.") + _number(rng)
    if rng.random() < 0.1:
        text += rng.choice("eE") + rng.choice(("", "+", "-")) + str(rng.randint(0, 400))
    if rng.random() < 0.15:
        text = f"{text} {_number(rng)}/{_number(rng)}"
    ahead = rng.choice(("", "", "", "", "-", "+", "(", "€", "$", "€ ", "-€", "%", "- "))
    behind = rng.choice(("", "", "", "", "%", ")", "€", " €", "$", "-", " %", "%)"))
    return ahead + text + behind


def _year(rng: Random) -> str:
    if rng.random() < 0.6:
        return rng.choice(("2026", "1900", "1899", "1904", "2000", "29", "30", "99", "0", "00"))
    return _number(rng)


def _numeric_day(rng: Random) -> str:
    day, month, year = _part(rng, 31, 2), _part(rng, 12, 2), _year(rng)
    order = rng.choice(("dmy", "dmy", "mdy", "ymd", "ymd", "dm", "md", "my", "ym"))
    parts = [{"d": day, "m": month, "y": year}[each] for each in order]
    marks = ("/", ".", "-", ". ", " ", ", ", "/ ")
    mark = rng.choice(marks)
    text = parts[0]
    for part in parts[1:]:
        text += (mark if rng.random() < 0.9 else rng.choice(marks)) + part
    return text + ("." if rng.random() < 0.15 else "")


def _named_day(rng: Random) -> str:
    day, year = _part(rng, 31), _year(rng)
    month = rng.choice(NAMES)
    shape = rng.choice(
        (
            *("{d} {M} {y}", "{d}. {M} {y}.", "{M} {d}, {y}", "{d}-{M}-{y}", "{M} {y}"),
            *("{d} {M}", "{M} {d}", "{y} {M} {d}", "{d}/{M}/{y}", "{d}.{M}.{y}", "{M}-{y}"),
            *("{d} {M}, {y}", "{M}, {d} {y}", "{d}{M}{y}", "{M} {d} {y}"),
        )
    )
    text = shape.format(d=day, M=month, y=year)
    if rng.random() < 0.1:
        text = rng.choice(WEEKDAYS) + rng.choice((", ", " ", ",")) + text
    return text


def _time(rng: Random) -> str:
    text = _part(rng, 24)
    count = rng.choice((0, 1, 1, 1, 2, 2))
    for _ in range(count):
        text += rng.choice((":", ":", ":", " : ", ": ")) + _part(rng, 60, 2)
    if count and rng.random() < 0.3:
        text += rng.choice(",.") + _number(rng)
    if rng.random() < 0.35 or not count:
        text += rng.choice(("", " ", " ", "  ")) + rng.choice(NOON)
    return text


def _form(rng: Random) -> str:
    """A number, a date, a time or both as people write one in Croatian or in English."""
    kind = rng.choices(("amount", "numeric", "named", "time", "moment"), (4, 4, 3, 4, 5))[0]
    match kind:
        case "amount":
            return _amount(rng)
        case "numeric":
            return _numeric_day(rng)
        case "named":
            return _named_day(rng)
        case "time":
            return _time(rng)
    day = (_numeric_day if rng.random() < 0.6 else _named_day)(rng)
    gap = rng.choice((" ", " ", " ", "  ", ", ", "T", " ,", " ", "\t", ","))
    return day + gap + _time(rng) if rng.random() < 0.8 else _time(rng) + gap + day


def _mutated(rng: Random, text: str) -> str:
    """The text with one to three characters put in, taken out, changed or doubled."""
    for _ in range(rng.randint(1, 3)):
        at = rng.randrange(len(text) + 1)
        change = rng.choice(("in", "out", "change", "double"))
        if change == "in" or not text:
            text = text[:at] + rng.choice(MUTANTS) + text[at:]
        elif at == len(text):
            continue
        elif change == "out":
            text = text[:at] + text[at + 1 :]
        elif change == "change":
            text = text[:at] + rng.choice(MUTANTS) + text[at + 1 :]
        else:
            text = text[:at] + text[at] + text[at:]
    return text


def _soup(rng: Random) -> str:
    """One to nine numbers, marks and words in any order."""
    pieces = []
    for _ in range(rng.randint(1, 9)):
        pieces.append(
            rng.choice(
                (
                    _number,
                    lambda rng: rng.choice(SOUP),
                    lambda rng: rng.choice(SOUP),
                    lambda rng: rng.choice(NOON),
                    lambda rng: rng.choice(NAMES),
                    lambda rng: rng.choice(WEEKDAYS),
                )
            )(rng)
        )
    return "".join(pieces)


def _discerning(
    orders: tuple[Callable[..., float], ...],
    draw: Callable[[Random], tuple],
    wanted: int,
    seed: int,
) -> list[str]:
    """Texts drawn until as many give a different fifteen digits by some of the orders a number
    may be computed in, so that the order Excel takes shows."""
    rng, found = Random(seed), []
    while len(found) < wanted:
        formula, *values = draw(rng)
        if len({f"{order(*values):.15g}" for order in orders}) > 1:
            found.append(formula)
    return found


def _mixed(rng: Random, percent: str = "") -> tuple:
    below = rng.randint(2, 32767)
    whole, above = rng.randrange(10 ** rng.randint(1, 9)), rng.randint(1, below - 1)
    return f'VALUE("{whole} {above}/{below}{percent}")', whole, above, below


def _sampled(seed: int) -> list[str]:
    """SAMPLED texts drawn at random, the same for a seed: a written form as it is, a form
    changed, or numbers, marks and words in any order, read by one of the functions that read
    text."""
    rng = Random(seed)
    formulas = []
    for _ in range(SAMPLED):
        drawn = rng.random()
        text = _soup(rng) if drawn < 0.2 else _form(rng)
        if 0.2 <= drawn < 0.65:
            text = _mutated(rng, text)
        name = rng.choices(("VALUE", "DATEVALUE", "TIMEVALUE", "NUMBERVALUE"), (5, 2, 2, 2))[0]
        marks = ""
        if name == "NUMBERVALUE" and rng.random() < 0.5:
            marks = rng.choice((',","', ',"."', ',",","."', ',".",","', ',","," "', ',"."," "'))
        formulas.append(f'{name}("{text}"{marks})')
    return formulas


READING = {
    title: list(dict.fromkeys(formulas))
    for title, formulas in {
        "Read numbers": [
            *(f'VALUE("{sign}{shape}")' for sign in ("", "-", "+") for shape in SHAPES),
            *(f'VALUE("{shape}%")' for shape in SHAPES),
            *(
                f'VALUE("{sign}{shape}{end}")'
                for sign in SIGNS
                for end in ENDS
                for shape in ("1", "1,5", "1.5")
            ),
            *(
                f'VALUE("{currency}{" " * apart}{sign}{" " * after}{number}")'
                for currency in ("€", "$", "£")
                for apart in range(4)
                for sign in ("", "+", "-")
                for after in range(3)
                for number in ("1", "386")
            ),
            *(f'NUMBERVALUE("{shape}")' for shape in SHAPES),
            *(f'NUMBERVALUE("{shape}",",",".")' for shape in SHAPES),
            *(f'NUMBERVALUE("{shape}",".",",")' for shape in SHAPES),
            *(
                f'NUMBERVALUE("{sign}1,5{end}",",")'
                for sign in SIGNS
                for end in ("", "%", ")", "€")
            ),
            *(
                f'VALUE("{a}{group}{b}")'
                for group in ".,\u00a0\u202f"
                for a in ("0", "00", "01", "001", "0001", "1", "10")
                for b in ("001", "100", "234", "2026", "0001")
            ),
            *(f'VALUE("{ahead}1{behind}")' for ahead, behind in DECORATIONS),
            *(f'NUMBERVALUE("{ahead}1,5{behind}",",")' for ahead, behind in DECORATIONS),
            *(
                f'NUMBERVALUE("{shape.format(text)}","{decimal}","{group}")'
                for text in ("1.234,5", "1,234.5")
                for shape in ("{}", "-{}", "({})", "€{}", "{}%", "{}€")
                for decimal, group in ((".", ","), (",", "."))
            ),
            *(
                f'{name}("1{gap}234")'
                for name in ("VALUE", "NUMBERVALUE")
                for gap in ("\t", "\u2009", "\u202f")
            ),
            *(
                f'NUMBERVALUE("1,5",{marks})'
                for marks in (
                    '""',
                    '","',
                    '"."',
                    '",",""',
                    '",",","',
                    '"ab"',
                    ",",
                    '",",',
                    '"",","',
                    '";"',
                    '"%"',
                    '"e"',
                )
            ),
            *(
                f'{name}("{text.replace("{}", blank)}")'
                for name in ("VALUE", "NUMBERVALUE")
                for blank in (" ", *BLANKS)
                for text in (
                    *(
                        "{}1",
                        "1{}",
                        "({}1{})",
                        "€{}1",
                        "1{}€",
                        "1{}%",
                        "%{}1",
                        "€{}(1)",
                        "({}1){}%",
                    ),
                    *("-{}1",),
                )
            ),
            *(
                f'VALUE("{text}")'
                for text in (
                    *("+ 1", "-  1", "- 1%", "- €1", "€- 1", "€ - 1", "- (1)", "- 1 1/2", "- 1,5"),
                    *("- 1.5", "- 1.234", "+  1", "- $1", "$- 1", "- 5/6/2026", "- 1:45"),
                )
            ),
            *(
                f'VALUE("{ahead}1{behind}")'
                for ahead in _spelled(AHEAD, 3, 0)
                for behind in _spelled(BEHIND, 2, 0)
            ),
            *(
                f'{name}("1"&CHAR({code})&"234")'
                for name in ("VALUE", "NUMBERVALUE")
                for code in (9, 10, 11, 12, 13, 32, 160)
            ),
            *(
                f'NUMBERVALUE("{text}"{marks})'
                for text in (
                    *("1-2", "5-6-2026", "2026-6-5", "-5-6", "(5-6)", "5-6%", "1+2", "1%2", "5(6)"),
                    *("€5-6", "5/6-2026", "1.5", "5.6.2026"),
                )
                for marks in ("", ',",","."', ',".",","')
            ),
        ],
        "Read fractions": [
            *(f'VALUE("1 {above}/{below}")' for above in PARTS for below in PARTS),
            *(f'VALUE("{whole} 1/2")' for whole in WHOLES),
            *(f'VALUE("{sign}1 1/2{end}")' for sign in SIGNS for end in ENDS),
            *(
                f'VALUE("{text}")'
                for text in (
                    *(
                        "1  1/2",
                        "1 1 /2",
                        "1 1/ 2",
                        "1 1 / 2",
                        "1 1/2/3",
                        "1 1/2 1/2",
                        "1 1-2",
                        "1 1.2",
                    ),
                    *(
                        "1 2",
                        "1 1,5/2",
                        "1 1.5/2",
                        "1 -1/2",
                        "1 1/-2",
                        "1 1/2e3",
                        "1e3 1/2",
                        "1 1/2 PM",
                    ),
                    *("1 1/2-", " 1 1/2 ", "1\u00a01/2", "1\t1/2", "1/2", "0/2", "13/40", "40/13"),
                )
            ),
            *(
                f'VALUE("1 {above}/{below}")'
                for part in ("00001", "0001", "00000", "000", "032767", "0032767")
                for above, below in ((part, "2"), ("1", part))
            ),
            *(
                f'VALUE("{whole} 1/2")'
                for whole in (
                    *("0.001", "01.001", "1.000", "0,001", "01,001", "1,000", "1.000.000"),
                    *("1,000,000",),
                )
            ),
            *(f'{name}("1 1/2")' for name in ("NUMBERVALUE", "DATEVALUE", "TIMEVALUE")),
            *(f'{name}("0 1/2")' for name in ("NUMBERVALUE", "DATEVALUE", "TIMEVALUE")),
        ],
        "Read dates": [
            *(f'VALUE("{a}{mark}{b}")' for mark in "/.-" for a in SQUARE for b in SQUARE),
            *(f'VALUE("{a}/{b}/{c}")' for a in CUBE for b in CUBE for c in CUBE),
            *(f'VALUE("{text}")' for text in CALENDAR),
            *(f'VALUE("5{gap}6/2026")' for gap in GAPS[1:]),
            *(f'VALUE("5/6{gap}2026")' for gap in GAPS[1:]),
            *(f'VALUE("5{gap}6")' for gap in GAPS[1:]),
            *(
                f'VALUE("{text}")'
                for text in ("5/6/2026.", " 5/6/2026", "5/6/2026 ", ".5/6/2026", "/5/6/2026")
            ),
            *(
                f'VALUE("{text}")'
                for text in ("5/6/2026/", "5//6/2026", "5/6/2026/7", "5/6/7/8", "-5/6/2026")
            ),
            *(
                f'DATEVALUE("{text}")'
                for text in ("5/6/2026", "5.6.2026", "5/6", "2026/6/5", "5/0", "1 1/2")
            ),
            *(
                f'VALUE("{text.replace("{}", blank)}")'
                for blank in BLANKS
                for text in ("5.{}6.{}2026", "5{}/6/2026", "5/{}6/2026", "{}5/6/2026", "5/6/2026{}")
            ),
        ],
        "Read named": [
            *(
                f'VALUE("{text}")'
                for names in MONTHS.values()
                for name in names
                for text in (f"6 {name} 2026", f"{name} 2026", f"{name} 6, 2026")
            ),
            *(
                f'VALUE("{text}")'
                for month in ("lis", "Oct")
                for text in (
                    *(f"{a} {month}" for a in NAMED),
                    *(f"{month} {a}" for a in NAMED),
                    *(f"{a} {month} {b}" for a in NAMED for b in NAMED),
                    *(f"{month} {a}, {b}" for a in NAMED for b in NAMED),
                )
            ),
            *dict.fromkeys(
                f'VALUE("{text}")'
                for month in ("lis", "Oct")
                for gap in GAPS
                for text in (
                    f"6{gap}{month} 2026",
                    f"6 {month}{gap}2026",
                    f"6-{month}{gap}2026",
                    f"6{gap}{month}",
                    f"{month}{gap}2026",
                    f"{month}{gap}27",
                    f"{month}{gap}6, 2026",
                    f"{month} 6{gap}2026",
                )
            ),
            *(
                f'VALUE("6 {name[:length]}{point} 2026")'
                for names in MONTHS.values()
                for name in names[:12]
                for length in range(1, len(name) + 1)
                for point in ("", ".")
            ),
            *(
                f'VALUE("{text}")'
                for text in (
                    "6 lis 2026.",
                    "6 Oct 2026.",
                    "6. lis. 2026.",
                    "6 lis 2026 ",
                    " Oct 6, 2026",
                    "Oct 6, 2026,",
                )
            ),
            *(
                f'VALUE("{text.replace("{}", blank)}")'
                for blank in BLANKS
                for month in ("lis", "Oct")
                for text in (f"6{{}}{month} 2026", f"6 {month}{{}}2026", f"{month} 6,{{}}2026")
            ),
        ],
        "Read short names": [
            *(
                f'VALUE("6 {name} 2026")'
                for code in LANGUAGES
                for name in formats.short_months(code)
            ),
            *(f'VALUE("6 {name} 2026")' for name in OTHER_SHORT),
            *(
                f'VALUE("{text.format(month)}")'
                for month in ("vel", "Feb", "fév")
                for text in COMMAED
            ),
        ],
        "Read joined names": [
            *(
                f'VALUE("{text}")'
                for month in ("lis", "Oct", "Feb")
                for mark in (",", ".")
                for text in (
                    *(f"1:45{mark}5.5 {month} 2026", f"1:45{mark}5.5{month}2026"),
                    *(f"1:45{mark}5/5 {month} 2026", f"1:45{mark}5-5-{month}-2026"),
                    *(f"1:45{mark}5 5 {month} 2026", f"1:45{mark}5 {month} 5, 2026"),
                    *(f"1:45{mark}5. 5 {month} 2026", f"9:00{mark}1899.30{month}2"),
                    *(f"1:45.5 {month} 2026", f"1:45/5 {month} 2026", f"1:45-5 {month} 2026"),
                    *(f"1:45 5{month}2026", f"1:45 .5{month}.2026", f"1:45.{month} 5, 2026"),
                )
            ),
            *(
                f'VALUE("{text}")'
                for month in sorted({formats.short_months(code)[9] for code in LANGUAGES})
                for mark in (",", ".")
                for text in (
                    *(f"1:45{mark}5, {month} 2026", f"1:45{mark}5, {month}-2026"),
                    *(f"1:45{mark}5 , {month} 2026", f"1:45{mark}5. {month} 2026"),
                    *(f"1:45{mark}5, 5 {month} 2026", f"1:45:05{mark}5, {month} 2026"),
                    *(f"1:45, {month} 2026", f"1:45{mark} {month} 2026"),
                )
            ),
            *(
                f'VALUE("{text}")'
                for month in sorted({formats.short_months(code)[9] for code in LANGUAGES})
                for text in (
                    *(f"5, {month}-2026", f"5, {month}.2026", f"5, {month}/2026"),
                    *(f"5, {month} - 2026", f"5, {month} -2026", f"5, {month}. 2026"),
                    *(f"5 , {month}-2026", f"5,{month}-2026", f"5, {month}-26", f"5, {month}-5"),
                    *(f"1:45.5, {month}.2026", f"1:45.5, {month}/2026", f"1:45.5,{month}-2026"),
                    *(f"1:45, 5, {month}-2026", f"5.6.2026 1:45, 5, {month}-2026"),
                )
            ),
            *(
                f'_xlfn.NUMBERVALUE("{text}",{marks})'
                for month in sorted({formats.short_months(code)[9] for code in LANGUAGES})
                for marks in ('"."', '","', '".",","', '",","."')
                for text in (
                    *(f"9:00.1899,30 {month} 2", f"9:00.1899,30{month}2"),
                    *(f"9:00.1899 30 {month} 2", f"9:00,1899.30 {month} 2"),
                    *(f"1:45.5,5 {month} 2026", f"1:45,5.5 {month} 2026"),
                    *(f"1:45.5,{month} 2026", f"1:45.5, {month} 2026", "1:45.5,5/6/2026"),
                    *(f"1:45.5,5.{month}.2026", f"30 {month} 2", f"1:45 30 {month} 2"),
                )
            ),
        ],
        "Read codes": [
            *(
                f'TEXT({MOMENT},"{letter * times}")'
                for letter in string.ascii_letters
                for times in range(1, 6)
            ),
            *(
                f'TEXT({MOMENT},"[{letter * times}]")'
                for letter in string.ascii_letters
                for times in (1, 2)
            ),
            *(f'TEXT({value},"{name}")' for value in ("1234.5", MOMENT) for name in GENERAL_NAMES),
            *(f'TEXT({MOMENT},"{code}")' for code in TIMED_CODES),
            *(f'TEXT(1234.5678,"{code.replace('"', '""')}")' for code in NUMBER_CODES),
            *(f'TEXT(-0.5,"{code.replace('"', '""')}")' for code in NUMBER_CODES),
            *(f'TEXT({part},"{code}")' for code in FRACTION_CODES for part in FRACTION_PARTS),
            *(
                f'TEXT({value},"{code.replace('"', '""')}")'
                for codes, values in (
                    (FRACTION_SHAPES, FRACTION_VALUES),
                    (SPACED_CODES, SPACED_VALUES),
                    (CONDITION_CODES, CONDITION_VALUES),
                    (ZERO_CODES, ZERO_VALUES),
                )
                for code in codes
                for value in values
            ),
            *(f'TEXT({day},"B2dd/mm/yyyy")' for day in HIJRI_DAYS),
            *(f'TEXT({MOMENT},"{code}")' for code in CALENDAR_CODES),
            *(
                f'TEXT({day},"{prefix}{code}")'
                for calendar, prefixes in NAMED_CALENDARS.items()
                for prefix in prefixes
                for codes, days in (
                    (MONTH_NAMES, HIJRI_MONTHS if calendar == "B2" else GREGORIAN_MONTHS),
                    (DAY_NAMES, WEEK),
                )
                for code in codes
                for day in days
            ),
            *(f'TEXT({day},"{code}")' for code in FIRST_CODES for day in FIRST_DAYS),
            *(
                f'TEXT({value},"{code.replace('"', '""')}")'
                for codes, values in (
                    (WEEKDAY_CODES, WEEKDAY_VALUES),
                    (CALENDAR_TEXTS, CALENDAR_TEXT_VALUES),
                    (CONDITIONED, CONDITIONED_VALUES),
                    (NEAR_CONDITIONED, NEAR_CONDITIONED_VALUES),
                    (GROUPED_EXPONENTS, GROUPED_EXPONENT_VALUES),
                    (APART_CODES, APART_VALUES),
                    (WIDE_FRACTIONS, WIDE_FRACTION_VALUES),
                    (MARKED_FRACTIONS, MARKED_FRACTION_VALUES),
                    (TRAILED_FRACTIONS, TRAILED_FRACTION_VALUES),
                    (BOUND_FRACTIONS, BOUND_FRACTION_VALUES),
                    (BLANK_CODES, BLANK_VALUES),
                    (PADDED_GROUPS, PADDED_GROUP_VALUES),
                    (WEEKLY_CODES, WEEKDAY_VALUES),
                    (TEXT_CODES, TEXT_VALUES),
                    (OPPOSED_CONDITIONED, OPPOSED_VALUES),
                    (DENOMINATED, DENOMINATED_VALUES),
                    (FIXED_BOUNDS, FIXED_BOUND_VALUES),
                    (FREE_BOUNDS, FREE_BOUND_VALUES),
                    (SCALED_FRACTIONS, SCALED_FRACTION_VALUES),
                    (ZERO_EXPONENTS, ZERO_EXPONENT_VALUES),
                    (PARTED_GROUPS, PARTED_VALUES),
                    (MARKS_ALONE, MARKS_ALONE_VALUES),
                    (WRITTEN_BOUNDS, WRITTEN_BOUND_VALUES),
                    (LITERAL_GROUPS, LITERAL_GROUP_VALUES),
                    (TEXT_SECTIONS, TEXT_SECTION_VALUES),
                    (WHOLE_GROUPED, WHOLE_GROUPED_VALUES),
                    (GIVEN_DENOMINATORS, GIVEN_DENOMINATOR_VALUES),
                    (POINTED_FRACTIONS, POINTED_FRACTION_VALUES),
                    (LATER_PLACEHOLDERS, LATER_PLACEHOLDER_VALUES),
                    (FRACTION_MARKS, FRACTION_MARK_VALUES),
                    (GROUPED_LATER, GROUPED_LATER_VALUES),
                    (DIGITLESS, DIGITLESS_VALUES),
                    (WEEKLY_MONTHS, WEEKDAY_VALUES),
                    (FOREIGN_NAMES, FOREIGN_DAYS),
                    (ELAPSED_MINUTES, ELAPSED_MINUTE_VALUES),
                    (TAG_SCOPES, TAG_SCOPE_VALUES),
                    (BARE_SECTIONS, BARE_SECTION_VALUES),
                    (DENOMINATOR_ENDS, DENOMINATOR_END_VALUES),
                    (SPACED_WHOLES, SPACED_WHOLE_VALUES),
                    (LATER_RUNS, LATER_RUN_VALUES),
                    (GROUPED_LATER_MORE, GROUPED_LATER_MORE_VALUES),
                    (SCALED_OVERFLOWS, SCALED_OVERFLOW_VALUES),
                )
                for code in codes
                for value in values
            ),
            *(f'TEXT(DATE(2001,2,3),"{code}")' for code in TAGGED_CODES),
            *LONG_TEXTS,
            *LONG_CODES,
        ],
        "Read times": [
            *(f'VALUE("{h}:{m}")' for h in CLOCK for m in CLOCK),
            *(
                f'VALUE("{h}:{m}:{s}")'
                for h in ("0", "1", "12", "24", "100", "10000")
                for m in CLOCK
                for s in SECONDS
            ),
            *(
                f'VALUE("{h}:{m} {noon}")'
                for noon in ("AM", "PM")
                for h in CLOCK
                for m in ("0", "00", "30", "59", "60", "99")
            ),
            *(f'VALUE("{h} {noon}")' for noon in ("AM", "PM") for h in CLOCK),
            *(
                f'VALUE("{h}:30:{s} {noon}")'
                for noon in ("AM", "PM")
                for h in ("1", "12", "13")
                for s in ("59", "60", "5,5", "5.5")
            ),
            *(
                f'VALUE("{text}")'
                for noon in NOON
                for text in (f"1:45 {noon}", f"1 {noon}", f"1:45{noon}")
            ),
            *(
                f'VALUE("{text}")'
                for text in (
                    *(
                        ":45",
                        "1:",
                        "1::45",
                        "1:45:",
                        "1:45:30:5",
                        ":45:30",
                        "1:45,5",
                        "1:45.5",
                        "1,5:45",
                    ),
                    *(
                        "1.5:45",
                        "-1:45",
                        "+1:45",
                        "(1:45)",
                        "1:45%",
                        "€1:45",
                        "1:-45",
                        " 1:45 ",
                        "1 :45",
                    ),
                    *("1: 45", "1 : 45", "1:45 :30"),
                )
            ),
            *(
                f'TIMEVALUE("{text}")'
                for text in ("1:45", "13:45:30", "1:45 PM", "1 PM", "24:00", "100:00", "1:45:30,5")
            ),
            *(
                f'VALUE("{text}")'
                for token in LEADING
                for text in (
                    f"{token}:45:30",
                    f"1:{token}:30",
                    f"1:45:{token}",
                    f"{token}:45",
                    f"1:{token}",
                )
            ),
            *(
                f'VALUE("{clock}:{seconds.replace(",", mark)}")'
                for clock in ("0:0", "23:59")
                for seconds in MILLISECONDS
                for mark in ",."
            ),
            *(
                f'VALUE("{time}{closing}{noon}")'
                for time in ("1", "1:45", "1:45:30", "1:45,5", "1:45:30,5", "1:45.5", "1:45:30.5")
                for closing in CLOSINGS
                for noon in ("", " AM")
            ),
            *(
                f'VALUE("{text}")'
                for text in (
                    *("1  :  45", "1\u00a0:45", "1:\u00a045", "1\t:45", "1:45\u00a0AM"),
                    *("1:45\tAM", "1:45  AM", "1,5 AM", "1.5 AM"),
                )
            ),
            *(
                f'VALUE("{minutes}:{seconds}{mark}5{noon}")'
                for minutes in ("0", "1", "13", "59", "60", "100", "9999")
                for seconds in ("0", "45", "59", "60", "99")
                for mark in ",."
                for noon in ("", " AM")
            ),
            *(f'VALUE("{text}")' for noon in NOONS for text in (f"1:45 {noon}", f"1 {noon}")),
            *(
                f'{name}("{text}")'
                for name in ("VALUE", "DATEVALUE", "TIMEVALUE")
                for text in (
                    *("24:00", "100:00", "9999:59:59", "5/6/2026 24:00", "5/6/2026 100:00"),
                    *("24:00 5/6/2026", "5.6.2026 100:00", "6 Oct 2026 100:00"),
                )
            ),
            *(
                f'VALUE("{text.replace("{}", blank)}")'
                for blank in BLANKS
                for text in ("{}1:45", "1:45{}")
            ),
            *(
                f'VALUE("{hours} {half}{mark}{gap}{number}")'
                for hours in ("0", "1", "6", "12", "13")
                for half in HALVES
                for mark in ("", ".", ",")
                for gap in (" ", "")
                for number in ("2026", "5", "0", "99", "12345")
            ),
            *(
                f'VALUE("{time} {half}{mark} 2026")'
                for time in ("6:30", "6:30:15")
                for half in HALVES
                for mark in (".", ",")
            ),
            *(
                f'{name}("6 {half}. 2026")'
                for name in ("DATEVALUE", "TIMEVALUE")
                for half in HALVES
            ),
            *(
                f'VALUE("{text.replace("{}", number)}{mark}5")'
                for number in ("0", "23", "24", "59", "60", "99", "100", "9999")
                for text in ("{} A", "{} P", "{}:30 A", "1:{} A")
                for mark in (",", ".")
            ),
            *(
                f'VALUE("{text.replace("{}", mark)}")'
                for mark in (",", ".")
                for text in (
                    *("6 A{}", "6 A{} ", "6 A{}{}5", "6 A {}5", "6  A{}5", "6 A{}5 PM", "6 A{}05"),
                    *("5/6/2026 6 A{}5", "6 A{}5 5/6/2026", "-6 A{}5", "6 A{}5555555", "6 B{}5"),
                    *("6 M{}5", "6 AM{}5", "6 A.M.{}5", "6:30 A{}5:5"),
                )
            ),
            *(
                f'{name}("6 {half}, 2026")'
                for name in ("DATEVALUE", "TIMEVALUE")
                for half in ("A", "P")
            ),
        ],
        "Read endings": [
            *(
                f'VALUE("{start}{ending}")'
                for start, longest in (
                    ("1:45", 4),
                    ("5/6/2026 1:45", 4),
                    ("6", 4),
                    ("1:45:30", 3),
                    ("5/6/2026 1:45:30", 3),
                    ("5/6/2026 6", 3),
                )
                for ending in _spelled(ENDING, longest)
            ),
        ],
        "Read joined": [
            f'VALUE("{start}{"".join(pieces)}")'
            for start in JOINED
            for length in (1, 2, 3)
            for pieces in itertools.product(PIECES, repeat=length)
        ],
        "Read checked": [
            *(
                f'VALUE("{day}{time}{mark}{seconds}:{dropped}{tail}")'
                for day in ("", "5/6/2026 ")
                for time in ("1:45", "23:59", "0:00")
                for mark in (",", ".")
                for seconds in SECONDS_TWICE
                for dropped in DROPPED
                for tail in ("", " PM", ",", ", 5/6/2026", "/6/2026")
            ),
            *(
                f'VALUE("{day}1:45{mark}{fraction} {half}{mark}{gap}{digits}{tail}")'
                for day in ("", "5/6/2026 ")
                for mark in (",", ".")
                for fraction in ("0", "05", "5", "25", "125", "0125")
                for half in ("A", "PM")
                for gap in ("", " ")
                for digits in SCALED
                for tail in ("", "/6", "/6/2026", " 5")
            ),
            *(
                f'VALUE("{time} {half}{lead}{day}")'
                for time in ("6", "1:45", "1:45:30", "1:45,5", "1:45.5", "1:45:30,5", "1:45:30.5")
                for half in ("A", "PM", "a", "pm")
                for lead in HALVED
                for day in LATER
            ),
            *(
                f'VALUE("{day} {time}{" 5" * count}")'
                for day in COUNTED
                for time in ("1:45", "1:45:30", "1:45 PM", "1:45:30,5", "1:45:30.5")
                for count in range(7)
            ),
        ],
        "Read limits": [
            *(
                f'VALUE("{text}")'
                for mark in (",", ".")
                for fraction in SCALED_LARGE
                for text in (
                    f"1:45{mark}{fraction}",
                    f"1:45{mark}{fraction}:0",
                    f"1:45{mark}{fraction} PM",
                )
            ),
            *(
                f'VALUE("{text}")'
                for mark in (",", ".")
                for fraction in SCALED_LARGE
                for digits in ("5", "05", "005")
                for text in (
                    f"1:45{mark}{fraction}:0, {digits}/6/2026",
                    *(f"1:45{mark}{fraction} {half}{mark}{digits}/6/2026" for half in ("A", "PM")),
                    *(
                        f"5/6/2026 1:45{mark}{fraction} {half}{mark}{digits}"
                        for half in ("A", "PM")
                    ),
                )
            ),
            *(
                f'VALUE("{day}{time}{mark}05{tail}")'
                for day in ("", "5/6/2026 ")
                for time in ("1:45", "1:45:30")
                for mark in (",", ".")
                for tail in (", 5/6/2026", ", 05/6/2026", ",5/6/2026", " 5, 5", ", 5", " 5,5")
            ),
            *(
                f'VALUE("1:45{mark}05:0{lead}5/6/2026")'
                for mark in (",", ".")
                for lead in (",", ", ", ".", ". ", " ,")
            ),
        ],
        "Read moments": [
            *(
                f'VALUE("{text}")'
                for day in DAYS
                for time in TIMES
                for text in (
                    f"{day} {time}",
                    f"{time} {day}",
                    f"{day}  {time}",
                    f"{day}, {time}",
                    f"{day}T{time}",
                )
            ),
            *(
                f'{name}("{day} {time}")'
                for name in ("DATEVALUE", "TIMEVALUE")
                for day in DAYS
                for time in TIMES
            ),
            *(
                f'VALUE("{day} {time}{tail}{noon}")'
                for day in ("5/6/2026", "5.6.2026", "6 lis 2026", "6 Oct 2026")
                for time in ("1", "1:45", "1:45:30")
                for tail in TAILS
                for noon in ("", " PM")
            ),
            *(
                f'{name}("{text}")'
                for name in ("DATEVALUE", "TIMEVALUE")
                for text in (*DAYS, *TIMES)
            ),
            *(
                f'VALUE("{text}")'
                for blank in BLANKS
                for day in ("5/6/2026", "6 lis 2026", "6 Oct 2026")
                for time in ("1:45", "1:45 PM")
                for text in (f"{day}{blank}{time}", f"{time}{blank}{day}")
            ),
            *(
                f'VALUE("{day}{time}{gap}{end}{noon}")'
                for day in ("", "5/6/2026 ")
                for time in ("1:45", "1:45:30")
                for gap in (" ", "  ")
                for end in (",5", ".5", "/5", ",", ".", ",5.5", ".5/5", "/5/5")
                for noon in ("", " PM")
            ),
            *(
                f'VALUE("{day} {time}{end}")'
                for day in ("5/6/2026", "5.6.2026")
                for time in ("1:45", "1:45:30")
                for end in ("..", "//", "/.", "./", "/5.", "/5//5", "-", "--5", ".-", ",,", ",5,5")
            ),
            *(
                f'VALUE("{text}")'
                for join in _spelled(JOINS, 3)
                for text in (f"5/6/2026{join}1:45", f"1:45{join}5/6/2026")
            ),
        ],
        "Read bounds": [
            *(
                f'{name}("{mantissa}E{power}{percent}")'
                for name in ("VALUE", "NUMBERVALUE")
                for mantissa in MANTISSAS
                for power in range(-330, -299)
                for percent in ("", "%")
            ),
            *(
                f'VALUE("{mantissa}E{power}")'
                for mantissa in ("0", "000", "1", "999999999999999")
                for power in range(290, 320)
            ),
            *(f'VALUE("0E{power}%")' for power in range(305, 315)),
            *(
                f'VALUE("{text}")'
                for mark in (",", ".")
                for fraction in WRAPPING
                for text in (
                    f"1:45{mark}{fraction}:0, 5/6/2026",
                    *(f"1:45{mark}{fraction} {half}{mark}5/6/2026" for half in ("A", "PM")),
                    f"5/6/2026 1:45{mark}{fraction} PM{mark}5",
                )
            ),
        ],
        "Read arithmetic": [
            *_discerning(
                (lambda w, a, b: w + a / b, lambda w, a, b: (w * b + a) / b), _mixed, 150, 1
            ),
            *_discerning(
                (
                    lambda w, a, b: w / 100 + a / b / 100,
                    lambda w, a, b: w / 100 + a / (b * 100),
                    lambda w, a, b: (w + a / b) / 100,
                    lambda w, a, b: (w * b + a) / b / 100,
                    lambda w, a, b: (w * b + a) / (b * 100),
                ),
                lambda rng: _mixed(rng, "%"),
                150,
                2,
            ),
        ],
        "Read words": [
            f'{name}("{place.replace("W", word)}")'
            for word in dict.fromkeys((*NAMES, *NOON, *NOONS, *WEEKDAYS, "e", "T", "x", "abc"))
            for place in PLACED
            for name in ("VALUE", "DATEVALUE", "TIMEVALUE", "NUMBERVALUE")
        ],
        **{f"Read sample {seed}": _sampled(seed) for seed in range(1, SAMPLES + 1)},
    }.items()
}

PAIRED_FUNCTIONS = ("CORREL", "PEARSON", "RSQ", "SLOPE", "INTERCEPT")
# Each kind of value a pair may hold at either place (numbers, text, logicals, blanks, empty
# text a formula gives, errors), in references and in arrays, and arrays of unlike counts,
# shapes and spreads.
PAIRED_ARGUMENTS = [
    ("Data!A1:A10", "Data!F1:F10"),
    ("Data!F1:F10", "Data!A1:A10"),
    ("Data!A1:A10", "Data!B1:B10"),
    ("Data!B1:B10", "Data!A1:A10"),
    ("Data!A1:A10", "Data!C1:C10"),
    ("Data!C1:C10", "Data!A1:A10"),
    ("Data!B1:B10", "Data!C1:C10"),
    ("Data!A1:A10", "Data!M1:M10"),
    ("Data!M1:M10", "Data!F1:F10"),
    ("Data!A1:A10", "Data!F1:F9"),
    ("Data!A1:A4", "Data!L1:M2"),
    ("Data!A1:A4", "Data!H2:H5"),
    ("Data!A1:A3", "Data!K1:K3"),
    ("Data!L1:L8", "Data!L1:L8"),
    ("Data!A1:A2", "Data!F1:F2"),
    ("Data!A1", "Data!F1"),
    ("Data!A1:A3", "{5,5,5}"),
    ("{5,5,5}", "Data!A1:A3"),
    ("{1,2,3}", "{2,4,7}"),
    ("{1,2,3}", "{1;2;3}"),
    ("{1,2,3}", "{1,2}"),
    ('{1,"a",3,TRUE}', "{2,4,7,9}"),
    ("{1,2,3,4}", '{2,"4",7,9}'),
    ("Data!A1:A10", "Data!A1:A10*2"),
    ("Data!A:A", "Data!F:F"),
    ("Data!B4", "Data!A1"),
    ("Data!E1:E10", "Data!A1:A10"),
    ("1", "2"),
    ("Data!N10:N14", "Data!A1:A5"),
    ("Data!A1", "Data!B4"),
    ("Data!B4", "Data!B4"),
    ("Data!D1", "Data!A1"),
    ("Data!B3", "Data!A1"),
    ("Data!C1", "Data!A1"),
    ('"a"', "1"),
    ("TRUE", "1"),
    ('{"a"}', "{1}"),
    ("Data!N1:N3", "Data!A1:A3"),
    ("Data!N1:N3", "Data!N4:N6"),
]


def _drawn(rng: Random, columns: str = "ABCFJLM", shortest: int = 2) -> list[tuple[str, str]]:
    """Pairs of columns of Data drawn at random among those given, of like and of unlike
    lengths, each sample drawn before Excel saved any of it."""
    found = []
    for _ in range(30):
        a, b = rng.choice(columns), rng.choice(columns)
        start, other, length = rng.randint(1, 4), rng.randint(1, 4), rng.randint(shortest, 6)
        longer = rng.random() < 0.1
        found.append(
            (
                f"Data!{a}{start}:{a}{start + length - 1}",
                f"Data!{b}{other}:{b}{other + length - 1 + longer}",
            )
        )
    return found


PAIRED_DRAWN = [*_drawn(Random(19)), *_drawn(Random(29), "ABCFJLMN", 1)]
PAIRED = [
    f"{name}({first},{second})"
    for name in PAIRED_FUNCTIONS
    for first, second in [*PAIRED_ARGUMENTS, *PAIRED_DRAWN]
]
CASES = {
    "Operators": [
        "1+2*3",
        "(1+2)*3",
        "-2^2",
        "2^3^2",
        "10/4",
        "1/0",
        "5%",
        "50%*200",
        '"a"&"b"',
        "1&2",
        '"a"="A"',
        '"a"<"B"',
        '"1"<2',
        "TRUE>1",
        'TRUE>"z"',
        '1="1"',
        "0.1+0.2=0.3",
        "1-0.9",
        "(1-0.9)-0.1",
        "0.1+0.2-0.3",
        "1/3*3=1",
        "10^-2",
        '"10"^2',
        "9E+307*10",
        "2^1024",
        '"3"+4',
        '"3"*"4"',
        '"abc"+1',
        "TRUE+TRUE",
        '-"5"',
        "--TRUE",
        '+"x"',
        "Data!B4+1",
        'Data!B4&"x"',
        "Data!B4=0",
        'Data!B4=""',
        'Data!C5=""',
        "Data!C5=0",
        "Data!C1+1",
        "#N/A",
        '"x"&#DIV/0!',
        "SUM(Data!A1:A3 Data!A2:A5)",
        "SUM((Data!A1,Data!A3))",
        "Data!A1:A3 Data!B2",
        "100000*100000",
        "123456789*987654321",
        "2^53+1",
        "(0.1+0.2)-0.3",
        "0.3-(0.1+0.2)",
        "0.1+0.2-0.3+1-1",
        "SUM(0.1,0.2,-0.3)",
    ],
    "Logical": [
        "IF(TRUE,1,2)",
        "IF(FALSE,1,2)",
        "IF(FALSE,1)",
        "IF(TRUE,,2)",
        'IF(1,"y","n")',
        'IF(0,"y","n")',
        'IF("TRUE",1,2)',
        'IF("x",1,2)',
        "IF(Data!B4,1,2)",
        "IF(TRUE,1,1/0)",
        "IF(Data!C1,1,2)",
        "IF(Data!B2,1,2)",
        "IFS(FALSE,1,TRUE,2)",
        "IFS(FALSE,1)",
        'IFS(1>2,"a",2>1,"b",1/0,"c")',
        'IFERROR(1/0,"err")',
        'IFERROR(5,"err")',
        'IFERROR(NA(),"")',
        "IFERROR(Data!C1,0)",
        "IFERROR(Data!B4,1)",
        'IFNA(NA(),"na")',
        'IFNA(1/0,"na")',
        'IFNA(3,"na")',
        "AND(TRUE,TRUE)",
        "AND(TRUE,FALSE)",
        'AND(1,"TRUE")',
        "AND(Data!B1:B10)",
        "AND(Data!D1:D3)",
        "AND(Data!B4)",
        "OR(FALSE,0)",
        "OR(Data!B8:B9)",
        'OR("x")',
        "XOR(TRUE,TRUE,TRUE)",
        "XOR(TRUE,FALSE)",
        "XOR(Data!B1:B3)",
        "NOT(0)",
        'NOT("")',
        'NOT("x")',
        "NOT(Data!B4)",
        "NOT(Data!C1)",
        "TRUE()",
        "FALSE()",
        'SWITCH(2,1,"a",2,"b","c")',
        'SWITCH(9,1,"a","default")',
        'SWITCH(9,1,"a")',
        'SWITCH("B","a",1,"b",2)',
        'SWITCH(1,1,"a",1/0,"b")',
    ],
    "Information": [
        "ISBLANK(Data!B4)",
        "ISBLANK(Data!C5)",
        'ISBLANK("")',
        "ISBLANK(Data!B10)",
        "ISBLANK(Data!C1)",
        "ISERROR(Data!C1)",
        "ISERROR(Data!A1)",
        "ISERR(NA())",
        "ISERR(1/0)",
        "ISNA(NA())",
        "ISNA(Data!C2)",
        "ISNA(1/0)",
        "ISNUMBER(5)",
        'ISNUMBER("5")',
        "ISNUMBER(Data!B2)",
        "ISNUMBER(Data!G1)",
        "ISNUMBER(Data!B3)",
        "ISTEXT(Data!B2)",
        "ISTEXT(Data!B4)",
        "ISTEXT(Data!C5)",
        "ISNONTEXT(Data!B4)",
        'ISNONTEXT("")',
        "ISNONTEXT(Data!C1)",
        "ISLOGICAL(Data!B3)",
        "ISLOGICAL(1)",
        "ISEVEN(2.5)",
        "ISEVEN(-3)",
        "ISODD(3.9)",
        'ISEVEN("4")',
        "ISEVEN(Data!B4)",
        "ISODD(TRUE)",
        'ISODD("x")',
        "NA()",
        "N(5)",
        'N("5")',
        "N(TRUE)",
        "N(Data!B2)",
        "N(Data!B3)",
        "N(Data!G3)",
        "N(Data!C1)",
        "N(Data!B4)",
        "TYPE(1)",
        'TYPE("a")',
        "TYPE(TRUE)",
        "TYPE(Data!C1)",
        "TYPE({1,2})",
        "TYPE(Data!B4)",
        "ERROR.TYPE(Data!C1)",
        "ERROR.TYPE(NA())",
        "ERROR.TYPE(1)",
        "ERROR.TYPE(Data!C7)",
        "ERROR.TYPE(#VALUE!)",
        "ERROR.TYPE(#REF!)",
        "ERROR.TYPE(#NAME?)",
        "ERROR.TYPE(#NULL!)",
    ],
    "Lookup": [
        "VLOOKUP(30,Data!H2:J6,2,FALSE)",
        "VLOOKUP(35,Data!H2:J6,2,TRUE)",
        "VLOOKUP(35,Data!H2:J6,2)",
        "VLOOKUP(35,Data!H2:J6,2,FALSE)",
        "VLOOKUP(5,Data!H2:J6,2,TRUE)",
        "VLOOKUP(30,Data!H2:J6,4,FALSE)",
        "VLOOKUP(30,Data!H2:J6,0,FALSE)",
        'VLOOKUP("milk",Data!I2:J6,2,FALSE)',
        'VLOOKUP("M*",Data!I2:J6,2,FALSE)',
        'VLOOKUP("Cheese",Data!I2:J6,2,0)',
        'VLOOKUP("30",Data!H2:J6,2,FALSE)',
        "VLOOKUP(30,Data!H2:J6,2.9,FALSE)",
        "VLOOKUP(Data!C1,Data!H2:J6,2,FALSE)",
        'HLOOKUP("Price",Data!H1:J6,3,FALSE)',
        'HLOOKUP("Name",Data!H1:J6,6,FALSE)',
        'HLOOKUP("Nothing",Data!H1:J6,2,FALSE)',
        "XLOOKUP(40,Data!H2:H6,Data!I2:I6)",
        'XLOOKUP(45,Data!H2:H6,Data!I2:I6,"none")',
        "XLOOKUP(45,Data!H2:H6,Data!I2:I6)",
        "XLOOKUP(45,Data!H2:H6,Data!I2:I6,,-1)",
        "XLOOKUP(45,Data!H2:H6,Data!I2:I6,,1)",
        'XLOOKUP("*ee*",Data!I2:I6,Data!J2:J6,,2)',
        'XLOOKUP("North",Data!E1:E10,Data!F1:F10,,0,-1)',
        "XLOOKUP(30,Data!H2:H6,Data!I2:I6,,0,2)",
        'XLOOKUP("eggs",Data!I2:I6,Data!H2:H6)',
        "XLOOKUP(Data!B4,Data!B1:B10,Data!A1:A10)",
        "SUM(XLOOKUP(20,Data!H2:H6,Data!J2:J6):Data!J6)",
        "MATCH(30,Data!H2:H6,0)",
        "MATCH(35,Data!H2:H6)",
        "MATCH(35,Data!H2:H6,1)",
        'MATCH("eggs",Data!I2:I6,0)',
        "MATCH(5,Data!H2:H6,1)",
        "MATCH(45,{50,40,30,20,10},-1)",
        'MATCH("b?n*",Data!D1:D10,0)',
        "MATCH(TRUE,Data!B1:B10,0)",
        "XMATCH(40,Data!H2:H6)",
        "XMATCH(45,Data!H2:H6,1)",
        'XMATCH("North",Data!E1:E10,0,-1)',
        "XMATCH(45,Data!H2:H6,-1)",
        "LOOKUP(35,Data!H2:H6,Data!I2:I6)",
        "LOOKUP(100,Data!H2:H6,Data!J2:J6)",
        "LOOKUP(1,Data!H2:H6,Data!I2:I6)",
        "LOOKUP(30,Data!H2:J6)",
        "INDEX(Data!H2:J6,2,3)",
        "INDEX(Data!A1:A10,4)",
        "SUM(INDEX(Data!H2:J6,0,3))",
        "INDEX(Data!H2:J6,6,1)",
        "SUM(Data!A1:INDEX(Data!A1:A10,3))",
        "INDEX({1,2;3,4},2,1)",
        "INDEX(Data!H2:J6,2.7,1)",
        'CHOOSE(2,"a","b","c")',
        'CHOOSE(4,"a","b")',
        'CHOOSE(1.9,"a","b")',
        'CHOOSE(2,1/0,"ok")',
        "SUM(CHOOSE(2,Data!A1:A2,Data!A3:A4))",
        "ROW(Data!B7)",
        "ROW()",
        "ROWS(Data!H2:J6)",
        "COLUMN(Data!J1)",
        "COLUMN()",
        "COLUMNS(Data!H2:J6)",
        "ROWS({1,2;3,4})",
        "COLUMNS({1,2,3})",
        "SUM(OFFSET(Data!A1,1,0,3,1))",
        "OFFSET(Data!A1,2,0)",
        "OFFSET(Data!A1,-1,0)",
        "SUM(OFFSET(Data!H1,1,2,5))",
        'INDIRECT("Data!A3")',
        'SUM(INDIRECT("Data!A1:A4"))',
        'INDIRECT("Data!R2C1",FALSE)',
        'INDIRECT("nonsense")',
        'INDIRECT("Data!"&"A"&5)',
        'HYPERLINK("https://example.com","Example")',
        'HYPERLINK("https://example.com")',
        'HYPERLINK("https://example.com",42)',
        "ADDRESS(2,3)",
        "ADDRESS(2,3,4)",
        "ADDRESS(2,3,1,FALSE)",
        'ADDRESS(2,3,1,TRUE,"Data")',
        "ADDRESS(1,16385)",
        "ADDRESS(2,3,2)",
        "ADDRESS(2,3,3)",
        'ADDRESS(1,1,1,TRUE,"My Sheet")',
        "ADDRESS(0,1)",
        "SUM(Data!A1:Data!A3)",
        "SUM(INDEX(Data!A1:A3,1):Data!A3)",
        "SUM(Data!A1:INDEX(Data!A1:A3,3))",
        "SUM((Data!A1):Data!A3)",
    ],
    "Math": [
        "SUM(1,2,3)",
        'SUM("1",TRUE)',
        "SUM(Data!B1:B10)",
        "SUM(Data!A1:A10)",
        "SUM(Data!C1:C10)",
        'SUM("x")',
        "SUM(Data!B4)",
        "SUM(Data!A1:A3,Data!A10,5)",
        "SUM(0.1,0.2,-0.3)",
        "SUM(Data!B2:B3)",
        "SUM(Data!A:A)",
        'SUMIF(Data!E1:E10,"North",Data!F1:F10)',
        'SUMIF(Data!F1:F10,">200")',
        'SUMIF(Data!F1:F10,">=100",Data!A1:A10)',
        'SUMIF(Data!E1:E10,"n*",Data!F1:F10)',
        'SUMIF(Data!E1:E10,"<>North",Data!F1:F10)',
        "SUMIF(Data!B1:B10,2,Data!A1:A10)",
        'SUMIF(Data!B1:B10,"2",Data!A1:A10)',
        'SUMIF(Data!B1:B10,"",Data!A1:A10)',
        "SUMIF(Data!E1:E10,Data!E1,Data!F1:F10)",
        'SUMIF(Data!E1:E10,"North",Data!F1)',
        'SUMIF(Data!C1:C10,">0")',
        'SUMIFS(Data!F1:F10,Data!E1:E10,"North",Data!F1:F10,">60")',
        'SUMIFS(Data!F1:F10,Data!E1:E10,"South")',
        'SUMIFS(Data!F1:F10,Data!G1:G10,">="&DATE(2026,1,1),Data!G1:G10,"<"&DATE(2027,1,1))',
        'SUMIFS(Data!F1:F10,Data!E1:E10,"North",Data!E1:E5,"North")',
        "SUMPRODUCT(Data!A1:A3,Data!F1:F3)",
        'SUMPRODUCT((Data!E1:E10="North")*Data!F1:F10)',
        "SUMPRODUCT(Data!B1:B10)",
        "SUMPRODUCT(Data!A1:A3,Data!A1:A2)",
        'SUMPRODUCT(--(Data!D1:D10="apple"))',
        "SUMPRODUCT({1,2;3,4},{1,1;1,1})",
        "SUBTOTAL(9,Data!N10:N14)",
        "SUBTOTAL(109,Data!N10:N14)",
        "SUBTOTAL(1,Data!N10:N13)",
        "SUBTOTAL(101,Data!N10:N13)",
        "SUBTOTAL(2,Data!N10:N14)",
        "SUBTOTAL(3,Data!N10:N14)",
        "SUBTOTAL(103,Data!N10:N14)",
        "SUBTOTAL(4,Data!N10:N13)",
        "SUBTOTAL(104,Data!N10:N13)",
        "SUBTOTAL(5,Data!N10:N13)",
        "SUBTOTAL(6,Data!N10:N13)",
        "SUBTOTAL(7,Data!N10:N13)",
        "SUBTOTAL(8,Data!N10:N13)",
        "SUBTOTAL(10,Data!N10:N13)",
        "SUBTOTAL(11,Data!N10:N13)",
        "SUBTOTAL(12,Data!N10:N13)",
        "SUBTOTAL(9,Data!A1:A10,Data!F1:F3)",
        "SUBTOTAL(9,Data!C1:C10)",
        "PRODUCT(2,3,4)",
        "PRODUCT(Data!B1:B6)",
        "PRODUCT(Data!B4)",
        'PRODUCT("2",TRUE)',
        "ROUND(2.5,0)",
        "ROUND(-2.5,0)",
        "ROUND(1.005,2)",
        "ROUND(2.675,2)",
        "ROUND(1234.5678,-2)",
        "ROUND(-1234.5678,1)",
        "ROUND(0.5,0)",
        "ROUND(Data!M9,5)",
        'ROUND("2.5",0)',
        "ROUND(1.15,1)",
        "ROUND(1.45,1)",
        "ROUND(5.015,2)",
        "ROUND(0.285,2)",
        "ROUND(1E+300,-300)",
        "ROUND(2.5,0.9)",
        "ROUNDUP(3.2,0)",
        "ROUNDUP(-3.2,0)",
        "ROUNDUP(3.14159,3)",
        "ROUNDUP(31415.92654,-2)",
        "ROUNDUP(0.1+0.2,1)",
        "ROUNDDOWN(3.7,0)",
        "ROUNDDOWN(-3.7,0)",
        "ROUNDDOWN(0.3-0.1,1)",
        "ROUNDDOWN(4.35,1)",
        "MROUND(10,3)",
        "MROUND(-10,-3)",
        "MROUND(5,-2)",
        "MROUND(1.3,0.2)",
        "MROUND(2.5,1)",
        "MROUND(5,0)",
        "INT(8.9)",
        "INT(-8.9)",
        "INT(Data!G8)",
        "TRUNC(-8.9)",
        "TRUNC(3.14159,2)",
        "TRUNC(1234.5,-2)",
        "ABS(-4)",
        'ABS("-4")',
        "ABS(Data!B7)",
        "SIGN(-0.0001)",
        "SIGN(0)",
        "MOD(3,2)",
        "MOD(-3,2)",
        "MOD(3,-2)",
        "MOD(-3,-2)",
        "MOD(5,0)",
        "MOD(5.5,2)",
        "MOD(0.3,0.1)",
        "MOD(1E+10,3)",
        "QUOTIENT(5,2)",
        "QUOTIENT(-10,3)",
        "QUOTIENT(1,0)",
        "POWER(2,10)",
        "POWER(-8,1/3)",
        "POWER(0,0)",
        "POWER(4,0.5)",
        "POWER(0,-1)",
        "SQRT(16)",
        "SQRT(-1)",
        "SQRT(2)",
        "EXP(1)",
        "EXP(710)",
        "LN(10)",
        "LN(0)",
        "LOG(8,2)",
        "LOG(100)",
        "LOG(10,1)",
        "LOG10(1000)",
        "LOG10(-1)",
        "PI()",
        "FACT(5)",
        "FACT(5.9)",
        "FACT(-1)",
        "FACT(0)",
        "FACT(170)",
        "FACT(171)",
        "EVEN(1.5)",
        "EVEN(-1)",
        "EVEN(0)",
        "ODD(1.5)",
        "ODD(2)",
        "ODD(-2)",
        "ODD(0)",
        "CEILING(2.5,1)",
        "CEILING(-2.5,-2)",
        "CEILING(-2.5,2)",
        "CEILING(1.5,0.1)",
        "CEILING(2.5,-1)",
        "CEILING(0.234,0.01)",
        "CEILING(5,0)",
        "CEILING.MATH(-5.5)",
        "CEILING.MATH(-5.5,2,-1)",
        "CEILING.MATH(6.7,2)",
        "CEILING.MATH(-5.5,-2)",
        "FLOOR(3.7,2)",
        "FLOOR(-2.5,-2)",
        "FLOOR(-2.5,2)",
        "FLOOR(1.58,0.1)",
        "FLOOR(2.5,-2)",
        "FLOOR(5,0)",
        "FLOOR.MATH(-5.5)",
        "FLOOR.MATH(-5.5,2,-1)",
        "FLOOR.MATH(24.3,5)",
        "AND(RAND()>=0,RAND()<1)",
        "RANDBETWEEN(5,5)",
        "RANDBETWEEN(3,1)",
        "AND(RANDBETWEEN(1,6)>=1,RANDBETWEEN(1,6)<=6)",
        "SUM(Data!A1:A3*2)",
    ],
    "Statistical": [
        "AVERAGE(1,2,3,4)",
        "AVERAGE(Data!B1:B10)",
        'AVERAGE("1",TRUE)',
        "AVERAGE(Data!B4)",
        "AVERAGE(Data!A1:A10,Data!C1)",
        "AVERAGE(Data!G1:G3)",
        'AVERAGEIF(Data!E1:E10,"North",Data!F1:F10)',
        'AVERAGEIF(Data!F1:F10,">1000")',
        'AVERAGEIF(Data!F1:F10,">100")',
        'AVERAGEIFS(Data!F1:F10,Data!E1:E10,"South",Data!F1:F10,"<200")',
        'AVERAGEIFS(Data!F1:F10,Data!E1:E10,"Nowhere")',
        "COUNT(Data!B1:B10)",
        'COUNT(1,"2",TRUE,"x")',
        "COUNT(Data!C1:C10)",
        "COUNT(Data!G1:G10)",
        "COUNT(1/0)",
        "COUNTA(Data!B1:B10)",
        "COUNTA(Data!C1:C10)",
        'COUNTA(1,"",Data!B4)',
        "COUNTA(Data!B4)",
        "COUNTBLANK(Data!B1:B10)",
        "COUNTBLANK(Data!C1:C10)",
        "COUNTIF(Data!B1:B10,2)",
        'COUNTIF(Data!B1:B10,"2")',
        'COUNTIF(Data!B1:B10,"")',
        'COUNTIF(Data!B1:B10,"=")',
        'COUNTIF(Data!B1:B10,"<>")',
        "COUNTIF(Data!B1:B10,TRUE)",
        'COUNTIF(Data!B1:B10,"TRUE")',
        'COUNTIF(Data!D1:D10,"apple*")',
        'COUNTIF(Data!D1:D10,"a~*b")',
        'COUNTIF(Data!D1:D10,"?????")',
        'COUNTIF(Data!A1:A10,">"&Data!A5)',
        'COUNTIF(Data!G1:G10,">="&DATE(2026,1,1))',
        'COUNTIF(Data!D1:D10,"APPLE")',
        'COUNTIF(Data!C1:C10,"#DIV/0!")',
        'COUNTIF(Data!B1:B10,"<1")',
        'COUNTIF(Data!B1:B10,"<a")',
        'COUNTIF(Data!B1:B10,">=0")',
        'COUNTIFS(Data!E1:E10,"North",Data!F1:F10,">80")',
        'COUNTIFS(Data!E1:E10,"North",Data!D1:D10,"*e*")',
        "MAX(Data!A1:A10)",
        "MAX(Data!B1:B10)",
        'MAX("10",2)',
        "MAX(Data!D1:D10)",
        "MAX(Data!C1:C10)",
        "MIN(Data!B1:B10)",
        "MIN(Data!G1:G10)",
        "MIN(Data!B4,5)",
        'MAXIFS(Data!F1:F10,Data!E1:E10,"North")',
        'MINIFS(Data!F1:F10,Data!E1:E10,"East")',
        'MAXIFS(Data!F1:F10,Data!E1:E10,"Nowhere")',
        "MEDIAN(Data!L1:L8)",
        "MEDIAN(1,2,3)",
        "MEDIAN(Data!B1:B10)",
        "MEDIAN(Data!B4)",
        "MODE(Data!L1:L8)",
        "MODE(1,2,3)",
        "MODE.SNGL(Data!L1:L8)",
        "MODE(1,1,2,2)",
        "LARGE(Data!F1:F10,2)",
        "LARGE(Data!F1:F10,11)",
        "LARGE(Data!F1:F10,1.5)",
        "SMALL(Data!L1:L8,3)",
        "SMALL(Data!B1:B10,1)",
        "SMALL(Data!F1:F10,0)",
        "RANK(300,Data!F1:F10)",
        "RANK(300,Data!F1:F10,1)",
        "RANK(4,Data!L1:L8)",
        "RANK(6,Data!L1:L8)",
        "RANK.EQ(5,Data!L1:L8,1)",
        "STDEV(Data!L1:L8)",
        "STDEV.S(Data!L1:L8)",
        "STDEV.P(Data!L1:L8)",
        "VAR(Data!L1:L8)",
        "VAR.S(1)",
        "VAR.P(Data!L1:L8)",
        "STDEV(Data!B1:B10)",
        "VAR.S(Data!F1:F10)",
        "COUNTIF(Data!B1:B10,Data!B4)",
        "AVERAGE(1,)",
        *PAIRED,
    ],
    "Text": [
        'CONCATENATE("a","b",12)',
        "CONCAT(Data!D1:D3)",
        'CONCAT("x",Data!B4,"y")',
        "CONCAT(Data!C1:C3)",
        'TEXTJOIN(", ",TRUE,Data!D1:D4)',
        'TEXTJOIN("-",FALSE,"a",Data!B4,"b")',
        'TEXTJOIN("-",TRUE,"a",Data!B4,"b")',
        'TEXTJOIN("-",TRUE,Data!C5,"z")',
        'LEFT("Excel",2)',
        'LEFT("Excel")',
        'LEFT("Excel",10)',
        'LEFT("Excel",-1)',
        "LEFT(12345,2)",
        'RIGHT("Excel",3)',
        'RIGHT("Excel",0)',
        "RIGHT(Data!B4,1)",
        'MID("Excel",2,3)',
        'MID("Excel",10,2)',
        'MID("Excel",0,2)',
        'MID("Excel",2,-1)',
        'LEN("Excel")',
        "LEN(Data!D9)",
        "LEN(Data!B4)",
        "LEN(12.5)",
        'LEN("čćžšđ")',
        "LEN(Data!C1)",
        'FIND("c","Excel")',
        'FIND("C","Excel")',
        'FIND("e","Excel",3)',
        'FIND("","Excel")',
        'FIND("x","Excel",9)',
        'SEARCH("C","Excel")',
        'SEARCH("e?c","Excel")',
        'SEARCH("~*","a*b")',
        'SEARCH("z","Excel")',
        'SEARCH("*l","Excel")',
        'SUBSTITUTE("aaa","a","b")',
        'SUBSTITUTE("aaa","a","b",2)',
        'SUBSTITUTE("aaa","A","b")',
        'SUBSTITUTE("abc","","x")',
        'SUBSTITUTE("aaa","a","b",0)',
        'REPLACE("abcdef",2,3,"X")',
        'REPLACE("abc",10,1,"Z")',
        'REPLACE("abc",0,1,"Z")',
        "TRIM(Data!D9)",
        'TRIM("  a  ")',
        'TRIM("a" & CHAR(160) & " b")',
        'UPPER("čćžšđ abc")',
        'LOWER("ABC Ž")',
        'PROPER("hello wORLD o\'neil 2nd")',
        'TEXT(0.5,"0%")',
        'TEXT(1234.5,"0")',
        'TEXT(-1,"0;(0)")',
        'TEXT("abc","@")',
        'TEXT(5,"000")',
        'TEXT(0,"0;-0;\\z\\e\\r\\o")',
        'TEXT(Data!B4,"0")',
        'EXACT("abc","ABC")',
        'EXACT("a","a")',
        'EXACT(1,"1")',
        'REPT("ab",3)',
        'REPT("ab",0)',
        'REPT("ab",-1)',
        'REPT("a",2.9)',
        "CHAR(65)",
        "CHAR(0)",
        "CHAR(256)",
        'CODE("A")',
        'CODE("")',
        'CODE("abc")',
        'CLEAN("a"&CHAR(10)&"b")',
        'VALUE("12")',
        'VALUE(" 12 ")',
        'VALUE("1e3")',
        'VALUE("50%")',
        'VALUE("abc")',
        'VALUE("")',
        "VALUE(Data!B4)",
        "VALUE(TRUE)",
        'VALUE("-12")',
        'VALUE("(12)")',
        'VALUE("$12")',
        "VALUE(12)",
        'NUMBERVALUE("1.234,5",",",".")',
        'NUMBERVALUE("1 234,5",","," ")',
        'NUMBERVALUE("12%%",".",",")',
        'NUMBERVALUE("1,5",",,")',
        'TEXTBEFORE("a-b-c","-")',
        'TEXTBEFORE("a-b-c","-",2)',
        'TEXTBEFORE("a-b-c","-",-1)',
        'TEXTBEFORE("abc","x")',
        'TEXTBEFORE("abc","x",,,,"none")',
        'TEXTBEFORE("aXb","x",,1)',
        'TEXTBEFORE("a-b","-",3)',
        'TEXTBEFORE("abc","x",,,1)',
        'TEXTAFTER("a-b-c","-")',
        'TEXTAFTER("a-b-c","-",-1)',
        'TEXTAFTER("a-b-c","-",3)',
        'TEXTAFTER("aXb","x",,1)',
        'T("abc")',
        "T(12)",
        "T(Data!B2)",
        "T(Data!C1)",
    ],
    "Date": [
        "DATE(2026,10,27)",
        "DATE(2026,13,1)",
        "DATE(2026,0,1)",
        "DATE(2026,2,30)",
        "DATE(99,1,1)",
        "DATE(1900,2,29)",
        "DATE(1900,1,0)",
        "DATE(-1,1,1)",
        "DATE(10000,1,1)",
        "DATE(2026,-13,1)",
        "DATE(1899,12,31)",
        "TIME(13,45,30)",
        "TIME(25,0,0)",
        "TIME(0,-1,0)",
        "TIME(0,90,0)",
        "TIME(0,0,-1)",
        "TIME(12,0,0.9)",
        "TODAY()>=DATE(2026,10,27)",
        "NOW()>=TODAY()",
        "YEAR(Data!G1)",
        "MONTH(Data!G1)",
        "DAY(Data!G1)",
        "YEAR(0)",
        "DAY(0)",
        "MONTH(60)",
        "DAY(60)",
        "DAY(61)",
        "YEAR(-1)",
        'YEAR("2026-10-27")',
        "YEAR(2958465)",
        "YEAR(2958466)",
        "HOUR(Data!G8)",
        "MINUTE(Data!G8)",
        "SECOND(Data!G8)",
        "HOUR(0.5)",
        "MINUTE(0.999999)",
        "SECOND(1.5/86400)",
        "SECOND(0.4999999/86400)",
        "HOUR(1.75)",
        "WEEKDAY(Data!G3)",
        "WEEKDAY(Data!G3,2)",
        "WEEKDAY(Data!G3,3)",
        "WEEKDAY(Data!G3,11)",
        "WEEKDAY(Data!G3,17)",
        "WEEKDAY(Data!G3,4)",
        "WEEKDAY(0)",
        "WEEKDAY(60)",
        "WEEKNUM(Data!G3)",
        "WEEKNUM(Data!G3,2)",
        "WEEKNUM(DATE(2027,1,1),21)",
        "WEEKNUM(DATE(2027,1,3),11)",
        "ISOWEEKNUM(DATE(2027,1,1))",
        "ISOWEEKNUM(Data!G3)",
        "ISOWEEKNUM(DATE(2026,12,31))",
        "EDATE(Data!G2,1)",
        "EDATE(Data!G1,12)",
        "EDATE(Data!G2,-1)",
        "EDATE(Data!G2,1.9)",
        "EDATE(Data!G1,-12)",
        "EOMONTH(Data!G3,0)",
        "EOMONTH(Data!G1,-12)",
        "EOMONTH(Data!G3,1.5)",
        "EOMONTH(Data!G2,1)",
        'DATEDIF(Data!G1,Data!G3,"Y")',
        'DATEDIF(Data!G1,Data!G3,"M")',
        'DATEDIF(Data!G1,Data!G3,"D")',
        'DATEDIF(Data!G1,Data!G3,"YM")',
        'DATEDIF(Data!G1,Data!G3,"MD")',
        'DATEDIF(Data!G1,Data!G3,"YD")',
        'DATEDIF(Data!G3,Data!G1,"D")',
        'DATEDIF(Data!G1,Data!G3,"x")',
        'DATEDIF(Data!G2,DATE(2026,3,1),"MD")',
        "DAYS(Data!G3,Data!G2)",
        'DAYS("2026-10-27","2026-01-01")',
        "DAYS(Data!G2,Data!G3)",
        "NETWORKDAYS(Data!G3,Data!G10)",
        "NETWORKDAYS(Data!G3,Data!G10,Data!K1:K3)",
        "NETWORKDAYS(Data!G10,Data!G3)",
        "NETWORKDAYS(Data!G3,Data!G3)",
        "WORKDAY(Data!G3,10)",
        "WORKDAY(Data!G3,40,Data!K1:K3)",
        "WORKDAY(Data!G3,-5)",
        "WORKDAY(Data!G3,0)",
        'DATEVALUE("2026-10-27")',
        'DATEVALUE("2026-02-30")',
        'TIMEVALUE("13:45:30")',
        'TIMEVALUE("25:00")',
        'TIMEVALUE("2026-10-27 06:00")',
        "YEARFRAC(Data!G2,Data!G3)",
        "YEARFRAC(Data!G2,Data!G3,1)",
        "YEARFRAC(Data!G2,Data!G3,2)",
        "YEARFRAC(Data!G2,Data!G3,3)",
        "YEARFRAC(Data!G2,Data!G3,4)",
        "YEARFRAC(Data!G1,Data!G5,1)",
        "YEARFRAC(Data!G3,Data!G2)",
        "YEARFRAC(Data!G1,Data!G3,5)",
        "EDATE(TRUE,1)",
        "EOMONTH(Data!G3,TRUE)",
        "WEEKNUM(TRUE)",
        "NETWORKDAYS(TRUE,10)",
        "YEARFRAC(TRUE,100)",
    ],
    "Financial": [
        "PMT(0.05/12,360,200000)",
        "PMT(0,12,1200)",
        "PMT(0.06/12,60,-20000,0,1)",
        "PMT(0.05/12,0,1000)",
        "PV(0.05/12,240,-1000)",
        "PV(0,10,-100)",
        "FV(0.06/12,120,-200,-5000,1)",
        "FV(0,10,-100)",
        "FV(0.05,10,-100)",
        "NPER(0.01,-100,1000)",
        "NPER(0,-100,1000)",
        "NPER(0.01,100,1000)",
        "RATE(60,-500,25000)",
        "RATE(10,-100,1000)",
        "RATE(12,-100,1000,0,1,0.1)",
        "NPV(0.1,Data!O2:O5)+Data!O1",
        "NPV(0.1,-1000,300,400,500,200)",
        "NPV(0.1,Data!B1:B10)",
        "IRR(Data!O1:O5)",
        "IRR(Data!O1:O5,0.2)",
        "IRR({-100,-100})",
        "PV(0.05/12,240,-1000,0,1)",
        "PV(0.07,15,-500,1000)",
        "PV(0.03,-5,100)",
        "FV(0.05/12,120.5,-100)",
        "FV(-0.02,12,-100,500)",
        "PMT(0.08/12,48,15000,-2000)",
        "PMT(0.1,3.5,1000)",
    ],
    "Locale": [
        TOLD,
        '1.5&""',
        'TRUE&""',
        '"x"&1234.5',
        '"x"&Data!G3',
        '"x"&1/3',
        '"x"&1E+21',
        '"x"&123456789012345678',
        '"x"&(0.1+0.2)',
        '"x"&-0.000001',
        'TEXT(1234.567,"#,##0.00")',
        'TEXT(1234.567,"0.0")',
        'TEXT(Data!G3,"dd.mm.yyyy")',
        'TEXT(Data!G3,"yyyy-mm-dd")',
        'TEXT(Data!G3,"dddd")',
        'TEXT(Data!G3,"mmmm")',
        'TEXT(Data!G3,"ddd d. mmm yyyy")',
        'TEXT(Data!G8,"hh:mm:ss")',
        'TEXT(Data!G8,"h:mm AM/PM")',
        'TEXT(0.123,"0.0%")',
        'TEXT(1234567.891,"#,##0")',
        'TEXT(1234.5,"General")',
        'TEXT(0.000012345,"0.00E+00")',
        'TEXT(1.5,"# ?/?")',
        'TEXT(-1234.5,"#,##0.00;[Red]-#,##0.00")',
        'TEXT(Data!G8,"[h]:mm")',
        'VALUE("1,5")',
        'VALUE("1.5")',
        'VALUE("1.234,5")',
        'VALUE("1,234.5")',
        'VALUE("27.10.2026")',
        'VALUE("13:45")',
        'DATEVALUE("27.10.2026")',
        'DATEVALUE("27.10.2026.")',
        'DATEVALUE("10/27/2026")',
        'DATEVALUE("27-Oct-2026")',
        'DATEVALUE("27.10.")',
        'TIMEVALUE("1:45 PM")',
        'NUMBERVALUE("2,5")',
        'NUMBERVALUE("2.5")',
        'NUMBERVALUE("2.5%")',
        "FIXED(1234.567,1)",
        "FIXED(1234.567,1,TRUE)",
        "FIXED(-1234.567,-1)",
        "FIXED(0.5)",
        'CODE("č")',
        "CHAR(232)",
        "UPPER(TRUE)",
        'CONCATENATE("a",TRUE,1.5)',
        "LEN(1/3)",
        '"1,5"+1',
        '"1.5"+1',
        'IF("ISTINA",1,2)',
        'AND("TRUE")',
        '"x"&1E-07',
        '"x"&0.0000012345',
        '"x"&1E+20',
        '"x"&0.1234567890123456789',
        'VALUE("27.10.26")',
        'VALUE("27. 10. 2026")',
        'VALUE("1.5.")',
        'VALUE("10/27")',
        'DATEVALUE("27/10/2026")',
        'AND(" TRUE")',
        'TEXT(1/3,"General")',
        '"x"&1E+19',
        '"x"&9.99999999999999E+19',
        '"x"&-1.23456789012345E+19',
        '"x"&1.2345E-07',
        '"x"&1E-08',
        '"x"&1E-10',
        '"x"&1E-15',
        '"x"&1E-18',
        '"x"&1E-19',
        '"x"&1E-20',
        '"x"&1E-21',
        '"x"&1.23456789012345E-08',
        '"x"&0.00123456789012345',
        '"x"&0.000123456789012345',
        '"x"&0.0000123456789012345',
        'TEXT(0.0001,"General")',
        'TEXT(0.00001,"General")',
        'TEXT(0.000123456789,"General")',
        'TEXT(0.00123456789,"General")',
        'TEXT(-1/3,"General")',
        'TEXT(123456789012,"General")',
        'TEXT(12345678901,"General")',
        'TEXT(99999999999.9,"General")',
        'TEXT(1234567890.55,"General")',
        'TEXT(1E+20,"General")',
        'TEXT(1.5E-10,"General")',
        'TEXT(1E-11,"General")',
        'VALUE("10.27")',
        'VALUE("27/10")',
        'VALUE("10/2027")',
        'VALUE("13/2026")',
        'VALUE("27-10-2026")',
        'VALUE("2026/10/27")',
        'DATEVALUE("27/10.2026")',
        'VALUE("2026/10")',
        'VALUE("2026.10.27")',
        'VALUE("2026.10.27.")',
        'VALUE("27-10")',
        'VALUE("10-2027")',
        'VALUE("1.23")',
        'VALUE("12.34")',
        'VALUE("1.1.29")',
        'VALUE("1.1.30")',
        'DATEVALUE("29.2.1900")',
        'DATEVALUE("28.2.1900")',
        'DATEVALUE("1.3.1900")',
        'DATEVALUE("1.1.1900")',
        'DATEVALUE("31.12.1899")',
        'DATEVALUE("31.12.9999")',
        'DATEVALUE("1.1.10000")',
        'DATEVALUE("29.2.2027")',
        'DATEVALUE("0.10.2026")',
        'DATEVALUE("27.0.2026")',
        'DATEVALUE("27.10.126")',
        'DATEVALUE("10-27-2026")',
        'DATEVALUE("10.27.2026")',
        'DATEVALUE("2/29/1900")',
        'DATEVALUE("1/1/29")',
        'DATEVALUE("1/1/30")',
        'VALUE("27. listopada 2026")',
        'VALUE("27. listopad 2026")',
        'VALUE("27-lis-2026")',
        'VALUE("27 lis 2026")',
        'VALUE("lis 2026")',
        'VALUE("27-lis")',
        'VALUE("lis-45")',
        'VALUE("Oct 27, 2026")',
        'VALUE("October 27, 2026")',
        'VALUE("27 October 2026")',
        'VALUE("Oct-2026")',
        'VALUE("27-Oct")',
        'VALUE("Oct-45")',
        'VALUE("27-OCT-2026")',
        'VALUE("27-Oct-26")',
        'VALUE("27.10.2026 13:45")',
        'VALUE("27.10.2026 1:45 PM")',
        'VALUE("10/27/2026 13:45")',
        'VALUE("27-Oct-2026 13:45")',
        'VALUE("Oct 27, 2026 1:45 PM")',
        'VALUE("13:45 27.10.2026")',
        'VALUE("25:00")',
        'TIMEVALUE("25:00")',
        'VALUE("100:00")',
        'VALUE("10000:00")',
        'VALUE("13:45:30,5")',
        'VALUE("13:45:30.5")',
        'VALUE("1:45 pm")',
        'VALUE("1:45 p")',
        'VALUE("1:45PM")',
        'VALUE("12:00 AM")',
        'VALUE("12:30 PM")',
        'VALUE("0:30 AM")',
        'VALUE("13:45 PM")',
        'VALUE("13:60")',
        'VALUE("1:45:60")',
        'VALUE("0:00")',
        'VALUE("1:5")',
        'VALUE("1 PM")',
        'VALUE("1PM")',
        'VALUE("13:45:30:00")',
        'VALUE("-1:00")',
        'VALUE("1 234,5")',
        'VALUE("1 234.5")',
        'VALUE("1.234.567")',
        'VALUE("1,234,567")',
        'VALUE("1.234.567,5")',
        'VALUE("-1,5%")',
        'VALUE("(1,5)")',
        'VALUE("(1.5)")',
        'VALUE("1,5e3")',
        'VALUE("1.5e3")',
        'VALUE("€ 12")',
        'VALUE("12 €")',
        'VALUE("12€")',
        'VALUE("-12 €")',
        'VALUE("$12")',
        'VALUE("12$")',
        'VALUE("-$12")',
        'VALUE("$-12")',
        'VALUE("1,5-")',
        'VALUE("+1,5")',
        'VALUE("1,")',
        'VALUE(",5")',
        'VALUE("1.")',
        'VALUE(".5")',
        'VALUE("1e")',
        'VALUE("1.2345")',
        'VALUE("1.000")',
        'VALUE("1,000")',
        'VALUE("1,5 %")',
        'VALUE("%1,5")',
        'VALUE("12%%")',
        'VALUE("1 000 000")',
        'NUMBERVALUE("1.234,5",",",".")',
        'NUMBERVALUE("1,234.5",".",",")',
        'NUMBERVALUE(" 1 234 , 5 ")',
        'NUMBERVALUE("2,5%%")',
        'NUMBERVALUE("")',
        'NUMBERVALUE("1.5",",",";")',
        'NUMBERVALUE("1,5,5")',
        'NUMBERVALUE("1,2.3",".",",")',
        'NUMBERVALUE("1.2,3",".",",")',
        'NUMBERVALUE("12e3")',
        'NUMBERVALUE("(12)")',
        'NUMBERVALUE("-12")',
        'NUMBERVALUE("12-")',
        'NUMBERVALUE("€12")',
        'NUMBERVALUE("1,5","ab")',
        'NUMBERVALUE("1,5","")',
        'NUMBERVALUE("1;5",";")',
        'NUMBERVALUE("123456789012345678")',
        'NUMBERVALUE("-")',
        'NUMBERVALUE(",")',
        'NUMBERVALUE("%")',
        "FIXED(1E+300,2)",
        "FIXED(1234.5,-5)",
        "FIXED(1234.5,127)",
        "FIXED(1234.5,128)",
        "FIXED(-0.0001,2)",
        "FIXED(1234.5,,TRUE)",
        "FIXED(0.5,0)",
        "FIXED(2.5,0)",
        "FIXED(1.005,2)",
        "FIXED(-1234.5,-2,TRUE)",
        'VALUE("13:99")',
        'VALUE("1:45:99")',
        'VALUE("0:75")',
        'VALUE("9999:59:59")',
        'VALUE("1:100")',
        'VALUE("12:75 PM")',
        'VALUE("1:45 PM 27.10.2026")',
        'VALUE("13:45:30 27.10.2026")',
        'VALUE("1234.567")',
        'VALUE("1.23.456")',
        'VALUE("12.345")',
        'VALUE("1.2345.678")',
        'VALUE("12.345,6")',
        'VALUE("1.234,")',
        'VALUE("1,2345")',
        'VALUE("1,23")',
        'VALUE("-%1,5")',
        'VALUE("% 1,5")',
        'VALUE("%-1,5")',
        'VALUE("(1,5%)")',
        'VALUE("27 listopad")',
        'VALUE("listopad 27, 2026")',
        'VALUE("27-Lis-2026")',
        'VALUE("27. lis. 2026")',
        'VALUE("27. LISTOPAD 2026")',
        "FIXED(1E+188,2)",
        "FIXED(1E+189,2)",
        "FIXED(-1E+188,2)",
        "FIXED(1E+200,2,TRUE)",
        "FIXED(1E+251,2,TRUE)",
        "FIXED(1E+252,2,TRUE)",
        'NUMBERVALUE("27.10.2026")',
        'NUMBERVALUE("13:45")',
        'NUMBERVALUE("1 PM")',
        'NUMBERVALUE("lis 2026")',
        'VALUE("1:1000")',
        'VALUE("1:10000")',
        'VALUE("1:45:10000")',
        'VALUE("Oct 27")',
        'VALUE("lis 27")',
        'VALUE("Oct 27 2026")',
        'VALUE("listopad 27 2026")',
        'VALUE("lis2026")',
        'VALUE("27lis2026")',
        'VALUE("Oct2026")',
        'VALUE("27Oct2026")',
        'NUMBERVALUE("1.234,5",",")',
        'NUMBERVALUE("1,5",",",",")',
        'NUMBERVALUE("1.5",".",".")',
        'VALUE("Oct 27,2026")',
        'VALUE("Oct, 27, 2026")',
        'VALUE("Oct. 27, 2026")',
        'VALUE("Oct-27-2026")',
        'VALUE("Oct/27/2026")',
        'VALUE("Oct 27-2026")',
        'VALUE("27/Oct/2026")',
        'VALUE("27/lis/2026")',
        'VALUE("27, Oct 2026")',
        'VALUE("27, lis 2026")',
        'VALUE("27 Oct, 2026")',
        'VALUE("27 lis, 2026")',
        'VALUE("27.-Oct-2026")',
        'VALUE("27.-lis-2026")',
        'VALUE("27 - Oct - 2026")',
        'VALUE("27 - lis - 2026")',
        'NUMBERVALUE("1,234.5",".")',
        'NUMBERVALUE("1.234,5",,".")',
        'NUMBERVALUE("1,234.5",,",")',
    ],
    **READING,
}


def workbook() -> Workbook:
    book = Workbook()
    data = book.active
    data.title = "Data"
    for col, values in DATA.items():
        for row, value in enumerate(values, 1):
            if value is not None:
                data[f"{col}{row}"] = value
    data.row_dimensions[HIDDEN_ROW].hidden = True
    for title, formulas in CASES.items():
        sheet = book.create_sheet(title)
        for row, formula in enumerate(formulas, 1):
            sheet.cell(row, 1, "=" + written(parse(formula)))
    return book


if __name__ == "__main__":
    workbook().save(sys.argv[1])
