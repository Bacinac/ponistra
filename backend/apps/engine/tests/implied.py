"""The texts and formulas whose number format Excel gives as they are entered (D22 E3): `python -m
apps.engine.tests.implied` writes implied-<language>.tsv for each document language, what is typed
in each cell in order, and the function (MACRO) Excel runs over each under the language's regional
format (excel.py) types them into a new workbook and saves it as implied-<language>.xlsx, with a CSV
of what each cell shows beside it. A cell of each kind of format comes first, then each text typed,
in the marks of the file's own language and then in those of one writing the other decimal mark,
each with the formulas over it beside it; then the formulas over the cells of each kind: every
operator over every pair, nested operators, every function of the registry with each of its
arguments a cell of each kind and the others a cell nothing is written to, functions over pairs of
cells and over ranges starting at each kind; then each text of a kind and some formulas entered in a
cell given a format first; last, lines of cells given a format to show a value in: times around the
rounding of their seconds and their parts of a second in each format of a time, a day of each month
and each day of the week in each format naming them, half seconds of many days in the formats that
count elapsed time, times drawn at random in each format of a time, the doubles next to a half
second in [s] and [m], and a fresh draw of them all. A formula reads only the cells of a kind or
cells to its left, which Excel has entered before it."""

import math
import sys
from itertools import product
from pathlib import Path
from random import Random

from apps.engine.formats import SHORT_DATE
from apps.engine.parse import CANONICAL, SEMICOLONS
from apps.engine.registry import FUNCTIONS
from apps.engine.tests import cases
from apps.engine.tests.saved import LANGUAGES

PATHS = {code: Path(__file__).with_name(f"implied-{code}.tsv") for code in LANGUAGES}
SHOWN = {code: path.with_name(f"implied-{code}-shown.csv") for code, path in PATHS.items()}
SYNTAX = {code: CANONICAL if code in ("en", "en-GB") else SEMICOLONS for code in LANGUAGES}
# The marks a language's numbers are grouped by as typed: French by the narrow space Windows
# writes and the spaces a writer may.
GROUPS = {
    "hr": (".",),
    "en": (",",),
    "en-GB": (",",),
    "de": (".",),
    "fr": ("\u202f", "\u00a0", " "),
    "it": (".",),
    "es": (".",),
}
HEADER = ("typed", "same", "times two", "two times", "sum")
OVER = ("=A{r}", "=A{r}*2", "=2*A{r}", "=SUM(A{r})")
BLANK = "Z1"

KINDS = {
    "hr": {
        "plain": "1250",
        "grouped": "1.250,5",
        "whole": "1.250",
        "currency": "1.250,50 €",
        "whole_currency": "12 €",
        "other_currency": "€12",
        "percent": "12,5%",
        "whole_percent": "12%",
        "scientific": "1,5E3",
        "fraction": "1 1/2",
        "fraction2": "1 12/25",
        "date": "1.2.2026",
        "later": "15.3.2026",
        "day_month": "1.2",
        "month_year": "veljača 2026",
        "time": "9:05",
        "evening": "17:30",
        "seconds": "9:05:30",
        "tenths": "9:05:30,5",
        "ampm": "9:05 PM",
        "duration": "25:10",
        "moment": "1.2.2026 9:05",
        "text": "abc",
        "logical": "TRUE",
        "blank": "",
    },
    "en": {
        "plain": "1250",
        "grouped": "1,250.5",
        "whole": "1,250",
        "currency": "$1,250.50",
        "whole_currency": "$12",
        "other_currency": "12 €",
        "percent": "12.5%",
        "whole_percent": "12%",
        "scientific": "1.5E3",
        "fraction": "1 1/2",
        "fraction2": "1 12/25",
        "date": "2/1/2026",
        "later": "3/15/2026",
        "day_month": "1-Feb",
        "month_year": "Feb-2026",
        "time": "9:05",
        "evening": "17:30",
        "seconds": "9:05:30",
        "tenths": "9:05:30.5",
        "ampm": "9:05 PM",
        "duration": "25:10",
        "moment": "2/1/2026 9:05",
        "text": "abc",
        "logical": "TRUE",
        "blank": "",
    },
    "en-GB": {
        "plain": "1250",
        "grouped": "1,250.5",
        "whole": "1,250",
        "currency": "£1,250.50",
        "whole_currency": "£12",
        "other_currency": "12 €",
        "percent": "12.5%",
        "whole_percent": "12%",
        "scientific": "1.5E3",
        "fraction": "1 1/2",
        "fraction2": "1 12/25",
        "date": "1/2/2026",
        "later": "15/3/2026",
        "day_month": "1-Feb",
        "month_year": "Feb-2026",
        "time": "9:05",
        "evening": "17:30",
        "seconds": "9:05:30",
        "tenths": "9:05:30.5",
        "ampm": "9:05 PM",
        "duration": "25:10",
        "moment": "1/2/2026 9:05",
        "text": "abc",
        "logical": "TRUE",
        "blank": "",
    },
    "de": {
        "plain": "1250",
        "grouped": "1.250,5",
        "whole": "1.250",
        "currency": "1.250,50 €",
        "whole_currency": "12 €",
        "other_currency": "€12",
        "percent": "12,5%",
        "whole_percent": "12%",
        "scientific": "1,5E3",
        "fraction": "1 1/2",
        "fraction2": "1 12/25",
        "date": "1.2.2026",
        "later": "15.3.2026",
        "day_month": "1.2",
        "month_year": "Februar 2026",
        "time": "9:05",
        "evening": "17:30",
        "seconds": "9:05:30",
        "tenths": "9:05:30,5",
        "ampm": "9:05 PM",
        "duration": "25:10",
        "moment": "1.2.2026 9:05",
        "text": "abc",
        "logical": "TRUE",
        "blank": "",
    },
    "fr": {
        "plain": "1250",
        "grouped": "1\u202f250,5",
        "whole": "1\u202f250",
        "currency": "1\u202f250,50 €",
        "whole_currency": "12 €",
        "other_currency": "€12",
        "percent": "12,5%",
        "whole_percent": "12%",
        "scientific": "1,5E3",
        "fraction": "1 1/2",
        "fraction2": "1 12/25",
        "date": "1/2/2026",
        "later": "15/3/2026",
        "day_month": "1/2",
        "month_year": "février 2026",
        "time": "9:05",
        "evening": "17:30",
        "seconds": "9:05:30",
        "tenths": "9:05:30,5",
        "ampm": "9:05 PM",
        "duration": "25:10",
        "moment": "1/2/2026 9:05",
        "text": "abc",
        "logical": "TRUE",
        "blank": "",
    },
    "it": {
        "plain": "1250",
        "grouped": "1.250,5",
        "whole": "1.250",
        "currency": "1.250,50 €",
        "whole_currency": "12 €",
        "other_currency": "€12",
        "percent": "12,5%",
        "whole_percent": "12%",
        "scientific": "1,5E3",
        "fraction": "1 1/2",
        "fraction2": "1 12/25",
        "date": "1/2/2026",
        "later": "15/3/2026",
        "day_month": "1/2",
        "month_year": "febbraio 2026",
        "time": "9:05",
        "evening": "17:30",
        "seconds": "9:05:30",
        "tenths": "9:05:30,5",
        "ampm": "9:05 PM",
        "duration": "25:10",
        "moment": "1/2/2026 9:05",
        "text": "abc",
        "logical": "TRUE",
        "blank": "",
    },
    "es": {
        "plain": "1250",
        "grouped": "1.250,5",
        "whole": "1.250",
        "currency": "1.250,50 €",
        "whole_currency": "12 €",
        "other_currency": "€12",
        "percent": "12,5%",
        "whole_percent": "12%",
        "scientific": "1,5E3",
        "fraction": "1 1/2",
        "fraction2": "1 12/25",
        "date": "1/2/2026",
        "later": "15/3/2026",
        "day_month": "1/2",
        "month_year": "febrero 2026",
        "time": "9:05",
        "evening": "17:30",
        "seconds": "9:05:30",
        "tenths": "9:05:30,5",
        "ampm": "9:05 PM",
        "duration": "25:10",
        "moment": "1/2/2026 9:05",
        "text": "abc",
        "logical": "TRUE",
        "blank": "",
    },
}
PAIRED = (
    "plain", "grouped", "currency", "other_currency", "percent", "scientific", "fraction", "date",
    "day_month", "time", "seconds", "duration", "moment", "text", "blank",
)  # fmt: skip
ARGUED = (
    "grouped", "currency", "other_currency", "percent", "scientific", "fraction", "date", "time",
    "seconds", "duration", "moment",
)  # fmt: skip
CALLS_PAIRED = ("plain", "grouped", "currency", "percent", "date", "time", "duration", "moment")
TRIPLED = ("plain", "currency", "percent", "date", "time", "moment")

TYPED = (
    # numbers
    "1250", "1250{d}5", "1250{d}50", "1250{d}555", "{d}5", "0{d}5", "-1250{d}5", "+1250", "007",
    "1250{d}", "1{g}250", "1{g}250{d}5", "1{g}250{d}50", "1{g}250{d}555", "-1{g}250", "+1{g}250",
    "12{g}345{g}678", "12{g}345{g}678{d}9", "1{g}25", "1{g}2500", "(1250)", "(1{g}250{d}5)",
    "1250-", " 1250 ", "1 250", "1 250{d}5", "1250{d}0", "1{g}250{d}0", "1{g}250E3",
    "1{g}250{d}5E3",
    # percents
    "12%", "12{d}5%", "12{d}55%", "0{d}125%", "1{g}250%", "-12%", "(12%)", "12 %", "%12",
    "1E2%", "12{d}50%", "12{d}0%", "1{g}250{d}5%",
    # exponents
    "1E3", "1e3", "1{d}5E3", "1{d}25E-3", "1E+03", "-1{d}5E3", "12E3", "1{d}2345E10", "1E-20",
    # fractions
    "1 1/2", "0 1/2", "1 1/3", "1 12/25", "1 123/1000", "-1 1/2", "10 3/4", "0 3/40", "1 12/5",
    "1 10/3", "0 123/4", "1 1/10", "1 0/5",
    # currencies
    "12 €", "12€", "12{d}5 €", "1{g}250 €", "1{g}250{d}50 €", "-12 €", "-12{d}5 €", "(12 €)",
    "€12", "€ 12", "€12{d}5", "€1{g}250{d}50", "12 EUR", "12 kn", "$12", "$12{d}5", "$1{g}250",
    "$1{g}250{d}50", "-$12", "$-12", "($12)", "12$", "12 $", "£12", "¥12", "12{d}0 €", "€ -12",
    "-€12", "€(12)", "12{d}555 €",
    # dates
    "1.2.2026", "1.2.2026.", "01.02.2026", "1.2.26", "1.2.", "1.2", "1. 2. 2026.", "1. 2. 2026",
    "1-2-2026", "1-2-26", "1/2/2026", "1/2/26", "1/2", "2/1/2026", "13/1/2026", "1/13/2026",
    "2026-02-01", "2026-2-1", "2026/2/1", "2026.2.1", "1-Feb-2026", "1-Feb-26", "1-Feb",
    "Feb-26", "Feb-2026", "Feb 1", "Feb 1, 2026", "February 1, 2026", "1 February 2026",
    "February 2026", "1. veljače 2026.", "1. veljače 2026", "1. veljača", "veljača 2026",
    "1-vlj-2026", "1.13.2026", "31.2.2026", "29.2.2028", "1.2.1900", "1.1.10000", "0.1.2026",
    "1 veljača 2026", "1. veljača 2026", "1 veljače", "vel 2026", "1. vel", "1 Feb", "1 Feb 2026",
    "1-February-2026", "12/25",
    # times
    "9:05", "09:05", "9:5", "9:05:30", "9:05:30{d}5", "9:05:30{d}55", "9:05 PM", "9:05 pm",
    "9:05PM", "9:05:30 AM", "9 PM", "9 AM", "21:05", "25:10", "25:10:30", "100:00", "0:05{d}5",
    "12:00 AM", "12:00 PM", "24:00", "9:60", "-9:05", "9:05:60", "9:75", "0:90", "1:30:75",
    "25:10 PM", "9:05:30{d}5 PM", "1:2:3", "100:00:00",
    # dates with times
    "1.2.2026 9:05", "1.2.2026 9:05:30", "1.2.2026 9:05 PM", "1.2.2026. 9:05", "2/1/2026 9:05",
    "2/1/2026 9:05 PM", "2026-02-01 9:05", "1-Feb-2026 9:05", "9:05 1.2.2026", "1.2. 9:05",
    "1.2.2026 25:10", "1.2.2026 0:00", "1/2/2026 12:00 AM", "1.2.2026 9:05:30{d}5",
    # the rest
    "TRUE", "FALSE", "true", "ISTINA", "abc", "12 abc", "#N/A", "#DIV/0!",
)  # fmt: skip
# The months by their names: Windows' Croatian short names, the Croatian names alone and after a
# day, the English short and full names; then the forms a text names a month in, and the names
# ICU writes where Windows writes another.
MONTHS = (
    ("sij", "vlj", "ožu", "tra", "svi", "lip", "srp", "kol", "ruj", "lis", "stu", "pro"),
    (
        "siječanj", "veljača", "ožujak", "travanj", "svibanj", "lipanj", "srpanj", "kolovoz",
        "rujan", "listopad", "studeni", "prosinac",
    ),
    (
        "siječnja", "veljače", "ožujka", "travnja", "svibnja", "lipnja", "srpnja", "kolovoza",
        "rujna", "listopada", "studenoga", "prosinca",
    ),
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    (
        "January", "February", "March", "April", "May", "June", "July", "August", "September",
        "October", "November", "December",
    ),
)  # fmt: skip
NAMING = ("1-{m}-2026", "1. {m} 2026.", "{m} 2026", "1 {m}", "{m}-26")
ICU_NAMES = ("velj", "studenog")

LITERAL = (
    "DATE(2026{l}2{l}1)", "TIME(9{l}5{l}0)", "TIME(21{l}5{l}30)", "TODAY()", "NOW()",
    'DATEVALUE("{date!}")', 'TIMEVALUE("9:05")', "PMT(0{d}05/12{l}60{l}10000)",
    "IPMT(0{d}05/12{l}1{l}60{l}10000)", "PPMT(0{d}05/12{l}1{l}60{l}10000)",
    "FV(0{d}05/12{l}60{l}-200)", "PV(0{d}05/12{l}60{l}-200)", "NPV(0{d}1{l}100{l}200)",
    "RATE(60{l}-200{l}10000)", "CUMIPMT(0{d}05/12{l}60{l}10000{l}1{l}12{l}0)",
    "SLN(10000{l}1000{l}5)", "DB(10000{l}1000{l}5{l}1)", "EFFECT(0{d}05{l}12)",
    "NOMINAL(0{d}05{l}12)", "DOLLAR(1250{d}5)", "FIXED(1250{d}5)", 'VALUE("12{d}5%")',
    'VALUE("{currency!}")', "1/3", "PI()", 'HYPERLINK("https://example.com"{l}"x")',
)  # fmt: skip
OPERATORS = ("+", "-", "*", "/", "^", "&", "=")
UNARY = ("-{a}", "+{a}", "({a})", "{a}%", "--{a}")
NESTED = ("{a}+{b}-{c}", "{a}-{b}+{c}", "{a}+({b}-{c})", "{a}-({b}-{c})")
RESULTS = (
    "DATE(2026{l}2{l}1)", "TIME(9{l}5{l}0)", "NOW()", "PMT(0{d}05/12{l}60{l}10000)",
    "RATE(60{l}-200{l}10000)",
)  # fmt: skip
WITH_RESULTS = ("{f}+{a}", "{a}+{f}", "{f}-{a}", "{a}-{f}", "SUM({f}{l}{a})", "SUM({a}{l}{f})")
RANGED = (
    "SUM({r})", "AVERAGE({r})", "MAX({r})", "MIN({r})", "MEDIAN({r})", "PRODUCT({r})",
    "INDEX({r}{l}1)", "LARGE({r}{l}1)", "SMALL({r}{l}1)", "SUBTOTAL(9{l}{r})", 'SUMIF({r}{l}">0")',
)  # fmt: skip
# Formats a cell holds before a text or a formula is entered in it, as Excel writes them in
# English, then what is entered: each kind's text, and formulas over the cells of some kinds.
FORMATTED = (
    "0.00", "#,##0", '#,##0.00\\ "€"', '"$"#,##0.00', "0%", "0.00E+00", "# ?/?", "d-mmm", "h:mm",
    "[h]:mm:ss", "m/d/yyyy", "@",
)  # fmt: skip
ENTERED = (
    "{plain!}", "{grouped!}", "{currency!}", "{other_currency!}", "{percent!}", "{scientific!}",
    "{fraction!}", "{date!}", "{day_month!}", "{time!}", "{duration!}", "{moment!}", "{text!}",
    "={currency}", "={date}", "={percent}", "={time}", "={plain}", "=DATE(2026{l}2{l}1)",
    "=PMT(0{d}05/12{l}60{l}10000)", "=SUM({currency})", "={currency}*2", "1/2", "-1/2", "3/4",
    "1/13", "13/2", "0 1/2",
)  # fmt: skip


def kept(format: str, code: str) -> str:
    """The format Excel keeps of one the macro gives a cell: VBA writes a dollar as the regional
    format's currency and m/d/yyyy as its short date, Excel's built-in format 14."""
    if format == "m/d/yyyy":
        return SHORT_DATE
    return format.replace('"$"', f'"{KINDS[code]["whole_currency"].strip("0123456789 ")}"')


# Times as seconds of a day, around the rounding of a second and of its parts: whole seconds,
# odd and even, before a minute, an hour and a day turn, after no day, one, and many, each with
# the parts of a second given; then the formats each is shown in, Windows' time among them.
DAYS = (0, 1, 45000)
HOURS = (0, 1, 12, 23)
MINUTES = (0, 59)
SECONDS = (0, 29, 30, 59)
PARTS = ("5", "49999", "50001", "05", "25", "95", "005", "0005")
TIMED = (
    "h:mm:ss", "[h]:mm:ss", "mm:ss", "[mm]:ss", "[ss]", "h:mm", "[h]:mm", "h:mm AM/PM",
    "h:mm:ss AM/PM", "mm:ss.0", "[ss].00", "h:mm:ss.000", "yyyy-mm-dd hh:mm:ss",
    "[$-F400]h:mm:ss AM/PM",
)  # fmt: skip
# The 15th of each month and each day of a week, in the formats that name them: Windows' long
# date and a language's own among them.
NAMED = (
    "mmm", "mmmm", "mmmmm", "d. mmmm yyyy", "d. mmm yyyy", "ddd", "dddd", "dddd, d. mmmm yyyy",
    "d-mmm-yy", "d-mmm", "mmm-yy", "mmmm yyyy", "[$-F800]dddd, mmmm dd, yyyy",
    "[$-x-sysdate]dddd, mmmm dd, yyyy", "[$-41A]d. mmmm yyyy", "[$-409]mmmm d, yyyy",
)  # fmt: skip
# Half seconds of many days, each written three ways that land on different doubles around the
# half, in the formats that count elapsed time with a clock beside them; then times drawn at
# random, of any day and parts of a second, a half at their last place as often as not.
TIED_DAYS = (0, 1, 2, 7, 31, 365, 1000, 10000, 45000, 100000)
TIED = ("[h]", "[m]", "[s]", "[h]:mm:ss", "[mm]:ss", "h:mm:ss")
TIES = 120
DRAWN = 400
# The doubles next to a half second, four below it to four above, for where Excel's rounding of
# an elapsed count turns: halves of seconds and halves of minutes, the edges of [s] and [m].
EDGES = 30
NEIGHBOURS = 4
EDGED = ("[s]", "[m]")
# A fresh draw of the same, counted before it is looked at: the doubles around halves of seconds
# and of minutes in each count of elapsed time and a clock, around the last half tick before a
# second in the formats that show its parts by their places, and times drawn at random.
CHECKED = ("[h]", "[m]", "[s]", "h:mm:ss", "[h]:mm:ss", "[mm]:ss")
PARTED = {1: ("[ss].0", "mm:ss.0"), 2: ("[ss].00", "[mm]:ss.00"), 3: ("[ss].000", "h:mm:ss.000")}
CHECKS = 15
# Numbers in formats whose marks stand where no digit is around them, or once more than a number
# takes, with conditions of each kind, fractions with marks about the slash and the whole part,
# exponents with group marks, calendars and the tags of languages beyond the suite, as a cell holds
# them written in English, about the longest text a cell shows, and the forms Excel saves some of
# them in.
SHAPED = (
    ".0", ",0", "0.0.0", "0,0,0", ".0.0", "00,000", "0,000", "#,##0,", '0,"K"', "0,€", "#,?/?",
    "0.0,", "0 0", "# ##0", "0 ", "#,##0.00,,", '#,##0" "', "0.,0", "[>100]0", "[<0]0;[>100]0",
    "[>100]0;[<-100]0", "0;(0)", "0.00;(0.00)", "# ?/?", "# #?/?", "#\\ ?/?", "B20", "[DBNum1]0",
    "[<-100]0", "[<=0]0", "[<>0]0;0", "#,##0E+00", "0,0E+00", "# ? /?", "?/ ?", "0 \\€", '0,"K",',
    "B1mmmm", "B2mmmm", "B2dd/mm/yyyy", "[DBNum3]0", "?0", "?/?", "0/8", "#/100", "[<0]0",
    "[<=0]0.0", "[=0]0", "[>=0]0", "[<=0]?/?", '[<=0]0;"x"0', "#,##0.0E+00", "000,000E+00",
    "B1dddd", "B2dddd", "B2mmm", "[$-401]B2mmmm", "B2[$-401]mmmm", "[$-409]B2dd/mm/yyyy",
    "[$-401]mmmm", "[$-401]dddd", "[$-40C]B2mmmm", "B2[$-40C]mmmm", "[$-40C]mmmm", "[$-409]B2mmmm",
    "[$-401]B1mmmm", "[$-41A]B2mmmm", "[$-401]B2dddd", "B2dddd mmmm", '[<=0]0;"x"0;"z"0', "# ?/?,",
    "##0.0E+00", '@"B1"', '"x"@', "?/32767", "?/32768", "?,?#0", "0, .", ",", "#,##0 ?/?",
    "#,##0\\ ?/?", "#,#\\ ?/?", "#,,\\ ?/?", "0,\\ ?/?", "#,\\ ?/?,", "#\\ ,?/?", '#,"x"?/?',
    "?/65536", "?/65535", "?/40000", "?/0?", "?/?0", "0", '0" "', "0;@", "@;0", "[$-801]mmmm",
    "[$-C01]dddd",
    "[$-40D]mmmm", "[$-41E]mmmm", "[$-411]mmmm", "[$-404]dddd", "[$-419]mmmm", "[$-408]mmmm",
    "[$-429]mmmm", "[$-41F]dddd", "[$-401]mmm", "[$-401]ddd", '[<0.5]0;"x"0', '[<1.5]0;"x"0',
    "0.x,,", "0x,,", '0"x",,', ",.", ".,", "#,\\ ?/?", ".", "[$-801]dddd", "[$-C01]mmmm",
    "[$-1401]mmmm", "[$-1401]dddd", "[$-40D]dddd", "[$-41E]dddd", "[$-41E]mmm", "[$-411]dddd",
    "[$-404]mmmm", "[$-419]dddd", "[$-419]mmm", "[$-408]dddd", "[$-429]dddd", "[$-420]mmmm",
    "[$-420]dddd", "[$-41F]mmmm",
)  # fmt: skip
SHAPED_VALUES = (
    *("1234.5678", "-0.5", "1234567.891", "0", "12345678901", "-0.4", "-0.004", "50", "-150"),
    *("2147483647", "2147483648", "268435456", "21474837", "-0.04", "-1.4"),
    *("4096", "4095.875", "0.0001", "1073741824", "46203", "1E+253", "1E+254", "1E+255", "0.005"),
    "1",
)

# The arguments Excel requires of each function whose form the registry does not write yet.
REQUIRED = {
    "ACCRINT": 6, "ACCRINTM": 4, "ACOS": 1, "ACOSH": 1, "ACOT": 1, "ACOTH": 1, "AGGREGATE": 3,
    "AMORDEGRC": 6, "AMORLINC": 6, "ARABIC": 1, "AREAS": 1, "ARRAYTOTEXT": 1, "ASC": 1,
    "ASIN": 1, "ASINH": 1, "ATAN": 1, "ATAN2": 2, "ATANH": 1, "AVEDEV": 1, "AVERAGEA": 1,
    "BAHTTEXT": 1, "BASE": 2, "BESSELI": 2, "BESSELJ": 2, "BESSELK": 2, "BESSELY": 2,
    "BETA.DIST": 4, "BETA.INV": 3, "BETADIST": 3, "BETAINV": 3, "BIN2DEC": 1, "BIN2HEX": 1,
    "BIN2OCT": 1, "BINOM.DIST": 4, "BINOM.DIST.RANGE": 3, "BINOM.INV": 3, "BINOMDIST": 4,
    "BITAND": 2, "BITLSHIFT": 2, "BITOR": 2, "BITRSHIFT": 2, "BITXOR": 2,
    "CEILING.PRECISE": 1, "CELL": 1, "CHIDIST": 2, "CHIINV": 2, "CHISQ.DIST": 3,
    "CHISQ.DIST.RT": 2, "CHISQ.INV": 2, "CHISQ.INV.RT": 2, "CHISQ.TEST": 2, "CHITEST": 2,
    "CHOOSECOLS": 2, "CHOOSEROWS": 2, "COMBIN": 2, "COMBINA": 2, "COMPLEX": 2, "CONFIDENCE": 3,
    "CONFIDENCE.NORM": 3, "CONFIDENCE.T": 3, "CONVERT": 3, "COS": 1, "COSH": 1,
    "COT": 1, "COTH": 1, "COUPDAYBS": 3, "COUPDAYS": 3, "COUPDAYSNC": 3, "COUPNCD": 3,
    "COUPNUM": 3, "COUPPCD": 3, "COVAR": 2, "COVARIANCE.P": 2, "COVARIANCE.S": 2,
    "CRITBINOM": 3, "CSC": 1, "CSCH": 1, "CUBEKPIMEMBER": 3, "CUBEMEMBER": 2,
    "CUBEMEMBERPROPERTY": 3, "CUBERANKEDMEMBER": 3, "CUBESET": 2, "CUBESETCOUNT": 1,
    "CUBEVALUE": 1, "CUMIPMT": 6, "CUMPRINC": 6, "DAVERAGE": 3, "DAYS360": 2, "DB": 4,
    "DBCS": 1, "DCOUNT": 3, "DCOUNTA": 3, "DDB": 4, "DEC2BIN": 1, "DEC2HEX": 1, "DEC2OCT": 1,
    "DECIMAL": 2, "DEGREES": 1, "DELTA": 1, "DETECTLANGUAGE": 1, "DEVSQ": 1, "DGET": 3,
    "DISC": 4, "DMAX": 3, "DMIN": 3, "DOLLAR": 1, "DOLLARDE": 2, "DOLLARFR": 2, "DPRODUCT": 3,
    "DROP": 2, "DSTDEV": 3, "DSTDEVP": 3, "DSUM": 3, "DURATION": 5, "DVAR": 3, "DVARP": 3,
    "ECMA.CEILING": 2, "EFFECT": 2, "ENCODEURL": 1, "ERF": 1, "ERF.PRECISE": 1, "ERFC": 1,
    "ERFC.PRECISE": 1, "EXPAND": 2, "EXPON.DIST": 3, "EXPONDIST": 3, "F.DIST": 4,
    "F.DIST.RT": 3, "F.INV": 3, "F.INV.RT": 3, "F.TEST": 2, "FACTDOUBLE": 1, "FDIST": 3,
    "FIELDVALUE": 2, "FILTER": 2, "FILTERXML": 2, "FINDB": 2, "FINV": 3, "FISHER": 1,
    "FISHERINV": 1, "FLOOR.PRECISE": 1, "FORECAST": 3, "FORECAST.ETS": 3,
    "FORECAST.ETS.CONFINT": 3, "FORECAST.ETS.SEASONALITY": 2, "FORECAST.ETS.STAT": 3,
    "FORECAST.LINEAR": 3, "FORMULATEXT": 1, "FREQUENCY": 2, "FTEST": 2, "FVSCHEDULE": 2,
    "GAMMA": 1, "GAMMA.DIST": 4, "GAMMA.INV": 3, "GAMMADIST": 4, "GAMMAINV": 3, "GAMMALN": 1,
    "GAMMALN.PRECISE": 1, "GAUSS": 1, "GCD": 1, "GEOMEAN": 1, "GESTEP": 1, "GETPIVOTDATA": 2,
    "GROUPBY": 3, "GROWTH": 1, "HARMEAN": 1, "HEX2BIN": 1, "HEX2DEC": 1, "HEX2OCT": 1,
    "HSTACK": 1, "HYPGEOM.DIST": 5, "HYPGEOMDIST": 4, "IMABS": 1, "IMAGE": 1, "IMAGINARY": 1,
    "IMARGUMENT": 1, "IMCONJUGATE": 1, "IMCOS": 1, "IMCOSH": 1, "IMCOT": 1, "IMCSC": 1,
    "IMCSCH": 1, "IMDIV": 2, "IMEXP": 1, "IMLN": 1, "IMLOG10": 1, "IMLOG2": 1, "IMPOWER": 2,
    "IMPRODUCT": 1, "IMREAL": 1, "IMSEC": 1, "IMSECH": 1, "IMSIN": 1, "IMSINH": 1,
    "IMSQRT": 1, "IMSUB": 2, "IMSUM": 1, "IMTAN": 1, "INFO": 1, "INTRATE": 4,
    "IPMT": 4, "ISFORMULA": 1, "ISO.CEILING": 1, "ISPMT": 4, "ISREF": 1, "JIS": 1, "KURT": 1,
    "LCM": 1, "LEFTB": 1, "LENB": 1, "LINEST": 1, "LOGEST": 1, "LOGINV": 3,
    "LOGNORM.DIST": 4, "LOGNORM.INV": 3, "LOGNORMDIST": 3, "MAXA": 1, "MDETERM": 1,
    "MDURATION": 5, "MIDB": 3, "MINA": 1, "MINVERSE": 1, "MIRR": 3, "MMULT": 2,
    "MODE.MULT": 1, "MULTINOMIAL": 1, "MUNIT": 1, "NEGBINOM.DIST": 4, "NEGBINOMDIST": 3,
    "NETWORKDAYS.INTL": 2, "NOMINAL": 2, "NORM.DIST": 4, "NORM.INV": 3, "NORM.S.DIST": 2,
    "NORM.S.INV": 1, "NORMDIST": 4, "NORMINV": 3, "NORMSDIST": 1, "NORMSINV": 1,
    "OCT2BIN": 1, "OCT2DEC": 1, "OCT2HEX": 1, "ODDFPRICE": 8, "ODDFYIELD": 8, "ODDLPRICE": 7,
    "ODDLYIELD": 7, "PDURATION": 3, "PERCENTILE": 2, "PERCENTILE.EXC": 2,
    "PERCENTILE.INC": 2, "PERCENTOF": 2, "PERCENTRANK": 2, "PERCENTRANK.EXC": 2,
    "PERCENTRANK.INC": 2, "PERMUT": 2, "PERMUTATIONA": 2, "PHI": 1, "PHONETIC": 1,
    "PIVOTBY": 4, "POISSON": 3, "POISSON.DIST": 3, "PPMT": 4, "PRICE": 6, "PRICEDISC": 4,
    "PRICEMAT": 5, "PROB": 3, "QUARTILE": 2, "QUARTILE.EXC": 2, "QUARTILE.INC": 2,
    "RADIANS": 1, "RANDARRAY": 0, "RANK.AVG": 2, "RECEIVED": 4, "REGEXEXTRACT": 2,
    "REGEXREPLACE": 3, "REGEXTEST": 2, "REPLACEB": 4, "RIGHTB": 1, "ROMAN": 1, "RRI": 3,
    "RTD": 3, "SEARCHB": 2, "SEC": 1, "SECH": 1, "SEQUENCE": 1, "SERIESSUM": 4,
    "SHEET": 0, "SHEETS": 0, "SIN": 1, "SINH": 1, "SKEW": 1, "SKEW.P": 1, "SLN": 3,
    "SORTBY": 2, "SQRTPI": 1, "STANDARDIZE": 3, "STDEVA": 1, "STDEVP": 1,
    "STDEVPA": 1, "STEYX": 2, "STOCKHISTORY": 2, "SUMSQ": 1, "SUMX2MY2": 2, "SUMX2PY2": 2,
    "SUMXMY2": 2, "SYD": 4, "T.DIST": 3, "T.DIST.2T": 2, "T.DIST.RT": 2, "T.INV": 2,
    "T.INV.2T": 2, "T.TEST": 4, "TAKE": 2, "TAN": 1, "TANH": 1, "TBILLEQ": 3,
    "TBILLPRICE": 3, "TBILLYIELD": 3, "TDIST": 3, "TEXTSPLIT": 2, "TINV": 2, "TOCOL": 1,
    "TOROW": 1, "TRANSLATE": 1, "TRANSPOSE": 1, "TREND": 1, "TRIMMEAN": 2, "TRIMRANGE": 1,
    "TTEST": 4, "UNICHAR": 1, "UNICODE": 1, "UNIQUE": 1, "USDOLLAR": 1, "VALUETOTEXT": 1,
    "VARA": 1, "VARP": 1, "VARPA": 1, "VDB": 5, "VSTACK": 1, "WEBSERVICE": 1, "WEIBULL": 4,
    "WEIBULL.DIST": 4, "WORKDAY.INTL": 2, "WRAPCOLS": 2, "WRAPROWS": 2, "XIRR": 2, "XNPV": 3,
    "YIELD": 6, "YIELDDISC": 4, "YIELDMAT": 5, "Z.TEST": 2, "ZTEST": 2,
}  # fmt: skip
# Functions Excel takes only with a LAMBDA, or only inside one, each argument at its place.
CALLED = {
    "BYCOL": "BYCOL({0}{l}LAMBDA(x{l}SUM(x)))",
    "BYROW": "BYROW({0}{l}LAMBDA(x{l}SUM(x)))",
    "ISOMITTED": "LET(f{l}LAMBDA(x{l}ISOMITTED(x)){l}f({0}))",
    "LAMBDA": "LET(f{l}LAMBDA(x{l}x){l}f({0}))",
    "LET": "LET(x{l}{0}{l}x)",
    "MAKEARRAY": "MAKEARRAY(1{l}1{l}LAMBDA(x{l}y{l}{0}))",
    "MAP": "MAP({0}{l}LAMBDA(x{l}x))",
    "REDUCE": "REDUCE({0}{l}{1}{l}LAMBDA(x{l}y{l}x+y))",
    "SCAN": "SCAN({0}{l}{1}{l}LAMBDA(x{l}y{l}x+y))",
}
# The arguments that set how large an array a function makes, left blank: a date there is a
# matrix of billions of cells (MUNIT of 1.2.2026 is 46054 by 46054), which Excel never ends.
SIZED = {"EXPAND": (1, 2), "MUNIT": (0,), "RANDARRAY": (0, 1), "SEQUENCE": (0, 1)}
# Functions Excel takes only from its own editors, never as a formula typed.
UNTYPED = {"PY", "PYTHON_STR", "PYTHON_TYPE", "PYTHON_TYPENAME", "PQSOURCE", "QUERYSTRING"}
# Functions that reach outside the workbook, to Microsoft's cloud, the web or an RTD or OLAP
# server: Excel stops to ask before it lets them connect and then waits on them, which stalls a
# macro entering them behind its window.
OUTSIDE = {
    "CUBEKPIMEMBER", "CUBEMEMBER", "CUBEMEMBERPROPERTY", "CUBERANKEDMEMBER", "CUBESET",
    "CUBESETCOUNT", "CUBEVALUE", "DETECTLANGUAGE", "FIELDVALUE", "IMAGE", "RTD", "STOCKHISTORY",
    "TRANSLATE", "WEBSERVICE",
}  # fmt: skip


def _places(name: str) -> tuple[int, int]:
    """How many arguments a call of the function is given, and how many of them are probed: an
    optional or repeated one past the required too, where the registry writes the form."""
    if name in CALLED:
        count = len({part for part in ("{0}", "{1}") if part in CALLED[name]})
        return count, count
    function = FUNCTIONS[name]
    if function.args is None:
        return REQUIRED[name], REQUIRED[name]
    required = sum(1 for arg in function.args if not arg.optional)
    more = len(function.args) > required or any(arg.repeat for arg in function.args)
    return required, required + more


def _call(name: str, given: dict[int, str], list_mark: str) -> str:
    count = max([_places(name)[0], *(place + 1 for place in given)])
    args = [given.get(place, BLANK) for place in range(count)]
    if name in CALLED:
        return CALLED[name].format(*args, l=list_mark)
    return f"{name}({list_mark.join(args)})"


def functions() -> list[str]:
    """Each function's name probed, in the registry's order."""
    for name in REQUIRED:
        assert FUNCTIONS[name].args is None, f"{name}'s form is in the registry: drop it here"
    return [name for name in FUNCTIONS if name not in UNTYPED | OUTSIDE]


def typed(code: str) -> list[str]:
    """The texts typed, in the marks of the language and then in those of one writing the other
    decimal mark, then the months by each of their names in each form."""
    other = "hr" if SYNTAX[code].decimal == "." else "en"
    found = [
        text.format(d=SYNTAX[each].decimal, g=group)
        for each in (code, other)
        for group in GROUPS[each]
        for text in TYPED
    ]
    names = [name for each in MONTHS for name in each] + list(ICU_NAMES)
    names += [name for each in ("de", "fr", "it", "es") for name in cases.MONTHS[each]]
    return list(dict.fromkeys(found + [form.format(m=name) for name in names for form in NAMING]))


def formulas(code: str, at: dict[str, str]) -> list[str]:
    """The formulas over the cells of each kind, written in the language, each kind by the
    address of its cell."""
    syntax = SYNTAX[code]
    marks = {"d": syntax.decimal, "l": syntax.list}
    found = [
        text.replace("{date!}", KINDS[code]["date"])
        .replace("{currency!}", KINDS[code]["currency"])
        .format(**marks)
        for text in LITERAL
    ]
    found += [at[a] + op + at[b] for op in OPERATORS for a, b in product(PAIRED, repeat=2)]
    found += [text.format(a=at[a]) for text in UNARY for a in KINDS[code]]
    found += [
        text.format(a=at[a], b=at[b], c=at[c])
        for text in NESTED
        for a, b, c in product(TRIPLED, repeat=3)
    ]
    found += [
        text.format(f=result.format(**marks), a=at[a], **marks)
        for result in RESULTS
        for text in WITH_RESULTS
        for a in PAIRED
    ]
    for name in functions():
        found.append(_call(name, {}, syntax.list))
        found += [
            _call(name, {place: at[kind]}, syntax.list)
            for place in range(_places(name)[1])
            if place not in SIZED.get(name, ())
            for kind in ARGUED
        ]
    found += [
        _call(name, {0: at[a], 1: at[b]}, syntax.list)
        for name in functions()
        if FUNCTIONS[name].args is not None and _places(name)[1] >= 2
        for a, b in product(CALLS_PAIRED, repeat=2)
    ]
    kinds = list(KINDS[code])
    found += [
        text.format(r=f"{at[kinds[first]]}:{at[kinds[first + size]]}", **marks)
        for text in RANGED
        for size in (1, 2)
        for first in range(len(kinds) - size)
    ]
    return ["=" + text for text in found]


def entered(code: str, at: dict[str, str]) -> list[tuple[str, str]]:
    """Each format a cell holds and what is then entered in it, the kind's text by `{kind!}`."""
    syntax = SYNTAX[code]
    found = []
    for held in FORMATTED:
        for text in ENTERED:
            for kind, typed_as in KINDS[code].items():
                text = text.replace(f"{{{kind}!}}", typed_as)
            found.append((held, text.format(d=syntax.decimal, l=syntax.list, **at)))
    return found


def _at(code: str) -> dict[str, str]:
    """The address of the cell of each kind, in the rows after the header."""
    return {kind: f"A{y}" for y, kind in enumerate(KINDS[code], start=2)}


def rows(code: str) -> list[list[str]]:
    """The sheet's rows: a header, the cell of each kind and each text typed, with the formulas
    over it beside it, then the formulas over the cells of each kind, then the cells given a
    format before what is entered in them (entered)."""
    at = _at(code)
    found = [list(HEADER), *([text] for text in KINDS[code].values())]
    found += [[text] for text in typed(code)]
    over = len(found)
    found = [
        line + [each.format(r=y) for each in OVER] if 1 < y <= over else line
        for y, line in enumerate(found, start=1)
    ]
    found += [[text] for text in formulas(code, at)]
    return found + [[text] for _, text in entered(code, at)]


def formatted(code: str) -> list[tuple[int, int, str, str]]:
    """The cells of the last rows (entered): the row, the column, the format the cell is given
    first and what is then entered in it."""
    pairs = entered(code, _at(code))
    first = len(rows(code)) - len(pairs) + 1
    return [(y, 1, held, text) for y, (held, text) in enumerate(pairs, start=first)]


def showing(code: str) -> list[list[tuple[str, str]]]:
    """The lines of cells after the rows, each a format and the formula of the value it shows:
    each time in each format of TIMED, each day in each format of NAMED, each half second in
    each format of TIED, each time drawn in each format of TIMED and the doubles around each
    half in each format of EDGED; then the fresh draw, in CHECKED, PARTED and TIMED, and each
    number of SHAPED_VALUES in each format of SHAPED."""
    syntax = SYNTAX[code]
    times = [
        f"=({hours}*3600+{minutes}*60+{seconds}{syntax.decimal}{part})/86400+{days}"
        for days, hours, minutes, seconds, part in product(DAYS, HOURS, MINUTES, SECONDS, PARTS)
    ]
    days = [(month, 15) for month in range(1, 13)] + [(2, day) for day in range(1, 8)]
    dated = [f"=DATE(2026{syntax.list}{month}{syntax.list}{day})" for month, day in days]
    draw = Random(30)
    tied = [
        text
        for days in TIED_DAYS
        for second in draw.sample(range(86_400), TIES)
        for text in (
            f"=({second}{syntax.decimal}5)/86400+{days}",
            f"={2 * second + 1}/172800+{days}",
            f"={days}+{second}/86400+1/172800",
        )
    ]
    drawn = _drawn(draw, syntax)
    edged = _edges(draw, syntax, EDGES)
    check = Random(31)
    checked = _edges(check, syntax, CHECKS)
    parted = [
        (places, text)
        for places in PARTED
        for text in _edges(check, syntax, CHECKS, "9" * places + "5", minutes=False)
    ]
    fresh = _drawn(check, syntax)
    shaped = [f"={value.replace('.', syntax.decimal)}" for value in SHAPED_VALUES]
    return (
        [[(format, text) for format in TIMED] for text in times]
        + [[(format, text) for format in NAMED] for text in dated]
        + [[(format, text) for format in TIED] for text in tied]
        + [[(format, text) for format in TIMED] for text in drawn]
        + [[(format, text) for format in EDGED] for text in edged]
        + [[(format, text) for format in CHECKED] for text in checked]
        + [[(format, text) for format in PARTED[places]] for places, text in parted]
        + [[(format, text) for format in TIMED] for text in fresh]
        + [[(format, text) for format in SHAPED] for text in shaped]
    )


def _drawn(draw: Random, syntax) -> list[str]:
    """DRAWN times of any day and parts of a second, a half at their last place as often as
    not."""
    found = []
    for _ in range(DRAWN):
        days = draw.choice((0, 1, draw.randrange(2, 2_958_466)))
        second, places = draw.randrange(86_400), draw.randrange(1, 7)
        part = str(draw.randrange(10**places)).zfill(places)
        if draw.random() < 0.5:
            part = part[:-1] + "5"
        found.append(
            f"=({second}{syntax.decimal}{part})/86400+{days}"
            if draw.random() < 0.5
            else f"={days}+{second}{syntax.decimal}{part}/86400"
        )
    return found


def _edges(draw: Random, syntax, count: int, part: str = "5", minutes: bool = True) -> list[str]:
    """The doubles from NEIGHBOURS below to NEIGHBOURS above a second and its part, half of it
    unless given, for `count` seconds of each day of TIED_DAYS and as many that end a minute."""
    found = []
    for days in TIED_DAYS:
        seconds = draw.sample(range(86_400), count)
        if minutes:
            seconds += [60 * minute + 59 for minute in draw.sample(range(1440), count)]
        for second in seconds:
            step = round(math.log2(math.ulp(float(f"{second}.{part}") / 86_400 + days)))
            text = f"=({second}{syntax.decimal}{part})/86400+{days}"
            found += [
                f"{text}{'-' if k < 0 else '+'}{abs(k)}*2^{step}"
                for k in range(-NEIGHBOURS, NEIGHBOURS + 1)
            ]
    return found


def entries(code: str) -> list[tuple[int, int, str, str]]:
    """What Excel types, in order: the row, the column, the format the cell is given first and
    the text."""
    found = rows(code)
    held = {y: each for y, _, each, _ in formatted(code)}
    return [
        (y, x, held.get(y, "") if x == 1 else "", text)
        for y, line in enumerate(found, start=1)
        for x, text in enumerate(line, start=1)
        if text
    ] + [
        (y, x, format, text)
        for y, line in enumerate(showing(code), start=len(found) + 1)
        for x, (format, text) in enumerate(line, start=1)
    ]


# The function Excel runs from a module of a workbook the script of excel.py makes, given a file
# written here and the country of its regional format: it checks the regional format is the
# file's, types each entry into a new workbook's sheet, and saves the sheet beside the file as
# the workbook and, its columns wide enough to show every value, as a CSV of what each cell
# shows (SHOWN), unless B2, the formula over A2, does not show what A2 does, and as a TSV of how
# it writes the format of each cell given one in the language (NumberFormatLocal); each entry Excel
# rejects or takes longer than a quarter of a second over goes into a log beside them. Opening a
# CSV instead enters no format with its formulas, and Excel has opened one of these as an Excel
# 4.0 macro sheet, whose formulas it never computes.
MACRO = """Function Implied(path As String, country As Long) As String
    Dim lines() As String, parts() As String, base As String, note As String, written() As String
    Dim book As Workbook, sheet As Worksheet, cell As Range, stream As Object
    Dim i As Long, n As Long, rejected As Long, began As Single, at As Single
    If Application.International(xlCountrySetting) <> country Then
        Implied = "NOT SAVED: the regional format is not the one of " & path
        Exit Function
    End If
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 2
    stream.Charset = "utf-8"
    stream.Open
    stream.LoadFromFile path
    lines = Split(stream.ReadText, vbCrLf)
    stream.Close
    ReDim written(UBound(lines))
    Set book = Workbooks.Add(xlWBATWorksheet)
    Set sheet = book.Worksheets(1)
    Application.Calculation = xlCalculationManual
    began = Timer
    For i = 0 To UBound(lines)
        If lines(i) <> "" Then
            parts = Split(lines(i), vbTab)
            Set cell = sheet.Cells(CLng(parts(0)), CLng(parts(1)))
            On Error Resume Next
            If parts(2) <> "" Then cell.NumberFormat = parts(2)
            If Err.Number <> 0 Then note = note & "format " & (i + 1) & " " & parts(2) & vbCrLf
            Err.Clear
            at = Timer
            cell.Formula2Local = parts(3)
            If Err.Number <> 0 Then
                rejected = rejected + 1
                note = note & "rejected " & (i + 1) & " " & parts(3) & vbCrLf
            End If
            On Error GoTo 0
            If Timer - at > 0.25 Then note = note & "slow " & (i + 1) & " " & parts(3) & vbCrLf
            If parts(2) <> "" Then
                written(i) = parts(0) & vbTab & parts(1) & vbTab & cell.NumberFormatLocal
            End If
            n = n + 1
        End If
    Next
    Application.Calculation = xlCalculationAutomatic
    base = Left(path, InStrRev(path, ".") - 1)
    stream.Open
    stream.WriteText note
    stream.SaveToFile base & ".log", 2
    stream.Close
    stream.Open
    stream.WriteText Join(written, vbCrLf)
    stream.SaveToFile base & "-local.tsv", 2
    stream.Close
    If sheet.Range("B2").Text = sheet.Range("A2").Text Then
        book.SaveAs base & ".xlsx", xlOpenXMLWorkbook
        sheet.UsedRange.Columns.AutoFit
        book.SaveAs base & "-shown.csv", xlCSVUTF8, Local:=True
        Implied = n & " entered, " & rejected & " rejected, " & Round(Timer - began) & " s"
    Else
        Implied = "NOT SAVED: the sheet does not compute"
    End If
    book.Close False
End Function"""


def write(code: str, path: Path) -> None:
    """The entries a line each, their parts parted by tabs, which no text holds."""
    lines = ["\t".join(map(str, entry)) for entry in entries(code)]
    assert not any(mark in line for line in lines for mark in "\r\n"), "a text breaks its line"
    assert all(line.count("\t") == 3 for line in lines), "a text holds a tab"
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8", newline="")


if __name__ == "__main__":
    for code in sys.argv[1:] or PATHS:
        write(code, PATHS[code])
