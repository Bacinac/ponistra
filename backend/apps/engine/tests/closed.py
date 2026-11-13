"""Codes as closed domains (D22): fractions, tables of every one-section code their alphabet makes
about one slash, each in the grammar of its language, and the counts of elapsed time. A sample
meets each context a token can stand in once if at all, so a rule read from one only describes the
codes drawn; read from such a table it has met every context up to the table's length, and a rule
read from the codes one token shorter that holds all of the longest is not a description of them.

short: every code of up to MOST tokens of SYMBOLS, and of up to KINDS_MOST tokens of PLACED with
one token of a kind KINDS holds put among them, over VALUES; en all of them, the other languages
the codes of up to OTHERS_MOST tokens of SYMBOLS, which tell whether the language's marks change
anything but how a code is written.
long: every code of LONG tokens of LONGER, the codes one token longer than short's, which a rule
read from short must hold; its literals are one, as short found every kind of them to be, and
group marks and percent signs, which act on the whole code, are short's. Over SPREAD.
given: a whole part of WHOLES, a numerator of NUMERATORS, a denominator GIVEN and a tail of TAILS,
over DEEP.
scaled: SCALING, the layouts group marks scale, over SCALED.
places: PLACES, free denominators of seven to ten places and given ones taking the best fraction,
over CONVERGING.
conditions: every code of up to three sections each holding no condition or one of CONDITION_OPS
against a bound of CONDITION_BOUNDS and a body of CONDITION_BODIES, alone or closed by a text
section, over CONDITION_VALUES: which section writes a number and whether its sign stays.
texts: every code of up to TEXTS_MOST tokens of TEXTS_MARKS, which meet the text mark and the
slash in every order, over TEXTS_VALUES, a text among them.
grouped: a whole part with a group mark of GROUPED_WHOLES, a fraction of GROUPED_FRACTIONS, a
literal and up to GROUPED_MOST of GROUPED_MARKS, over GROUPED_VALUES.
runs: the group mark's wholes of RUNS_WHOLES before a fraction of RUNS_FRACTIONS and a literal,
then a run of RUNS_MOST placeholders 0, runs of 0 split by a literal, and RUNS_MIXED, over
GROUPED_VALUES.
mixed: a group mark's whole, a fraction of one placeholder each side and a literal, then a 0 or #
and a ? followed by up to MIXED_MOST zeros or by ?s, then runs of # and ?, over GROUPED_VALUES.
lone: a section of one of CONDITION_OPS against a bound of CONDITION_BOUNDS and a body of
LONE_BODIES, alone or closed by a text section, over CONDITION_VALUES: when a lone condition that
leaves the number out writes it in General.
clocks: every code the grammar holds of up to CLOCKS_MOST of CLOCKS_MARKS, over CLOCKS_VALUES: the
decimal mark and the colon beside the parts of a time.
noons: every code the grammar holds of one of NOONS_LEADS, an elapsed time of NOONS_ELAPSED and
up to two of NOONS_TAILS, over CLOCKS_VALUES: what follows an elapsed time the marks of the
morning and the afternoon came before.
wide: every code the grammar holds of a whole part of WIDE_WHOLES, a parting of WIDE_PARTINGS, a
numerator of WIDE_NUMERATORS, a denominator's run of WIDE_RUNS and a tail of WIDE_TAILS, over
WIDE_VALUES: how long a whole part about 255 characters a fraction writes.
blanks: every code the grammar holds of 0, a space, a numerator of BLANKS_NUMERATORS, a run of one
to BLANKS_MOST of 0, #, ? and 1 or a denominator of BLANKS_GIVEN and a tail of BLANKS_TAILS, over
WIDE_VALUES: how much of a fraction of nothing its whole part leaves no space for counts toward the
255 characters.
years: in each language, every code the grammar holds of one to YEARS_MOST of the year's or the
weekday's letter in either case before one of YEARS_NOONS, alone or before the hour's letter, over
CLOCKS_VALUES: where those marks end a run of a letter they begin with.
commas: every code the grammar holds of COMMAS_LEAST to COMMAS_MOST of COMMAS_MARKS with a group
mark, and those of several decimal marks closed by a General section, over COMMAS_VALUES: which
group marks about a decimal mark scale the number.
fractions: every code the grammar holds of one of FRACTIONS_HEADS, a denominator of
FRACTIONS_GIVEN and up to FRACTIONS_MOST of FRACTIONS_TAILS, over FRACTIONS_VALUES: what follows a
denominator the code gives.
choices: every code of a first section of CHOICES_BODIES under one of CHOICES_FIRST, a second
of CHOICES_BODIES under one of CHOICES_SECOND and a third of CHOICES_THIRD or none, over
CONDITION_VALUES: which section writes a number by what each section holds.
minutes: every code the grammar holds of up to MINUTES_MOST of MINUTES_MARKS, over CLOCKS_VALUES:
which m is a minute and which hour the marks of the morning and the afternoon count.
denominators: every code the grammar holds of one of DENOMINATORS_HEADS, a denominator of
DENOMINATORS_GIVEN and up to two of DENOMINATORS_TAILS, over DENOMINATORS_VALUES: what a tag, a
mark or an escape after a denominator does to it.
trailing: every code the grammar holds of 0/, a denominator of DENOMINATORS_GIVEN and up to
TRAILING_MOST of TRAILING_TAILS, over DENOMINATORS_VALUES: where a given denominator ends among the
digits after it.
percented: every code the grammar holds of one of PERCENTED_HEADS, a denominator of
PERCENTED_GIVEN, a space, digits of PERCENTED_LATER and one of PERCENTED_TAILS, over
PERCENTED_VALUES: which denominator the digits after the run give beside a percent sign.
spread: every code the grammar holds of one of SPREAD_HEADS and up to SPREAD_MOST of
SPREAD_MARKS, over PERCENTED_VALUES: what percent signs, group marks and a decimal mark among the
placeholders after a denominator do.
zeros: every code the grammar holds of one of ZEROS_WHOLES, one of ZEROS_FRACTIONS and up to
ZEROS_MOST of ZEROS_TAILS, over ZEROS_VALUES: what a grouped whole part writes about a fraction
of nothing.
wholes: every code the grammar holds of one of WHOLES_HEADS, one of WHOLES_BETWEEN, #/, a
denominator of WHOLES_GIVEN and one of WHOLES_TAGS, over DENOMINATORS_VALUES: what pads a tag after
a whole part, a numerator and a denominator.
systems: every code the grammar holds of a first section of one of SYSTEMS_TAGS under one of
SYSTEMS_CONDITIONS over one of SYSTEMS_FIRST, a second of SYSTEMS_SECOND and a third of
SYSTEMS_THIRD or none, over SYSTEMS_VALUES: which section a system's date or time tag leaves a
number.
tagged: every code the grammar holds of a first section of one of TAGGED_LEADS over one of
TAGGED_FIRST, up to two of TAGGED_MIDDLE and a text section of the parts of one of TAGGED_BODIES
with one of TAGGED_MARKS before, between or after them or none, over TAGGED_VALUES: what a system's
date or time tag makes of the text section.
dollars: every code the grammar holds of one of DOLLARS_HEADS, a run of one to DOLLARS_MOST $ and
one of DOLLARS_TAILS, over 1: how much of the longest code a run of $ takes where it stands.
exponents: every code the grammar holds of one of EXPONENTS_HEADS and up to EXPONENTS_MOST of
EXPONENTS_TAILS, over DENOMINATORS_VALUES: what follows the sign of an exponent.
sections: every code the grammar holds of a first section of SECTIONS_FIRST, a second of up to
SECTIONS_MOST of SECTIONS_MARKS holding @ and a third of SECTIONS_THIRD or none, over
SECTIONS_VALUES: what a text mark in a section before the last does.
scales: every code the grammar holds of one of SCALES_HEADS and up to SCALES_MOST of SCALES_MARKS,
over SCALES_VALUES: what among the decimal places keeps the group marks at a decimal mark from
scaling the number.
covered: every code the grammar holds of up to COVERED_MOST of COVERED_MARKS with a tag of
COVERED_TAGS before, between or after them, over COVERED_VALUES: where a system's date or time is
#VALUE! by what the section it stands for writes.
powers: POWERS_CODES over POWERS_VALUES, mantissas rounding up or not at each exponent about 99 and
100 of either sign: the room General gives an exponent.
orders: every code the grammar holds of one of ORDERS_HEADS and one of ORDERS_TAILS, over
ORDERS_VALUES, numbers whose fraction tells how each percent sign and group mark scaled the double:
in what order Excel scales a fraction's number.
months: every code the grammar holds, written in German, of up to MONTHS_MOST of MONTHS_MARKS, over
MONTHS_VALUES: which M is a minute where the month's letter and the minute's differ in case.
hidden: every code the grammar holds of a system's long date tag before up to HIDDEN_MOST of
HIDDEN_MARKS, over COVERED_VALUES: which of the ways a section cannot write a number keeps the
system's date from standing for it.
later: every code the grammar holds of one of LATER_HEADS, a denominator of LATER_GIVEN and up
to LATER_MOST of LATER_TAILS, over DENOMINATORS_VALUES: which digits after a denominator, through
tags, literals and placeholders, give it.
owed: every code the grammar holds of one of OWED_WHOLES, one of OWED_FRACTIONS, "x" and up to
OWED_MOST of OWED_MARKS, over OWED_VALUES: what the placeholders after a grouped fraction write
where its denominator's run left a space.
spare: every code the grammar holds of one of SPARE_HEADS and up to SPARE_MOST of SPARE_MARKS, over
SPARE_VALUES, fractions whose denominators run one to five digits past the code's: where those
digits go among the placeholders after a literal.
paid: every code the grammar holds of a grouped whole part, one of PAID_FRACTIONS, "x" and up to
PAID_MOST of OWED_MARKS, over PAID_VALUES: how the placeholders after a grouped fraction pay the
spaces a run of three or four ? left.
twice: every code the grammar holds of one of TWICE_WHOLES, TWICE_NUMERATORS, "/", one of
TWICE_DENOMINATORS and one of TWICE_ENDS, over TWICE_VALUES: how the group marks of a fraction's
two scaling ends scale it.
inside: every code the grammar holds of one of INSIDE_BASES with one of INSIDE_MARKS put at each
place inside it, over INSIDE_VALUES: whether a tag or a literal parts the placeholders about it.
wider: every code the grammar holds of one of WIDER_TAGS, one of WIDER_WHOLES, one of
WIDER_FRACTIONS and one of WIDER_ENDS, over WIDER_VALUES: whether a fraction scaled past the width
Excel writes still leaves the system's date or time.
beside: every code the grammar holds of one of BESIDE_TAGS, one of BESIDE_WHOLES, one of
BESIDE_NUMERATORS, "/" and one of BESIDE_DENOMINATORS, over WIDER_VALUES: what of a fraction
beside the system's date Excel takes before the date stands for the number.
placed: every code the grammar holds of one of PLACED_BASES with one of PLACED_TAGS put at each
place in it, over PLACED_VALUES: how much of a scaled fraction before the system's tag Excel holds
to the width.
ties: every code of a whole part of TIES_HEADS, a denominator of TIES_DENOMINATORS and a scaling of
TIES_SCALES, each over the values of at most 15 digits that a whole of TIES_WHOLES and one of the
TIES_MOST smallest counts and a half over its denominator make, scaled down as the code scales up:
how Excel rounds a count that is half way in decimal.
held: every code of a whole part of HELD_HEADS, a fraction of HELD_FRACTIONS and a scaling of
HELD_SCALES, over the values the HELD_STEPS numbers of fifteen digits from each of HELD_BASES make
with as many places as bring them, scaled, to each of HELD_DIGITS digits before the decimal mark:
what whole part Excel writes once the scaled number reaches fifteen digits.
budgets: each code grammar covers and BUDGET_DRAWN more drawn from BUDGET_SEED, with up to
PADDED_DOLLARS $ and an x run of any length to the longest put after its first section's brackets,
over 1: how much of the longest code each takes.
probes: every code the grammar holds of one or two of PROBED, of three of PROBED_NUMBERS and of
COLONS, with up to
PADDED_DOLLARS $ and an x run near the longest put after its first section's brackets, over 1: what
each part takes beside each other.
elapsed: ELAPSED, counts of hours, minutes and seconds, over AGES, serials whose counts outgrow 15
digits and doubles.
scientific: every code of up to SCIENTIFIC_MANTISSA marks of group, decimal and placeholder
before E+ or E- and up to three placeholders of exponent, over SCIENTIFIC_VALUES.
tails: every code of a numerator #, a denominator of one placeholder, a literal, up to TAILS_OWN
marks, a decimal mark and up to TAILS_PAST marks, which holds what the nine drawn show of the
tail after a literal; over TAILS_VALUES.
nine: NINE_CODES codes of NINE tokens of LONGER drawn at random, which the rules read from the
tables before it must hold as they hold up to longer's length. Over SPREAD, measured once.
longer: every code of LONG + 1 tokens of LONGER, which the rules read from the tables before it
must hold before Excel computes it; a check measured once, as its five million rows are no test to
keep, the rules it confirms being held by the tables they were read from. Over SPREAD.

`write` (excel.py's parts closed-<table>) writes closed-<table>-<language>-codes.xlsx, TEXT of
each code written in the language over its values, ROWS to a sheet, which excel.py has Excel
compute and save as closed-<table>-<language>.xlsx. What Excel saved is kept in closed/ beside
this module."""

import itertools
import random
import re
from decimal import Decimal
from fractions import Fraction
from functools import cache
from pathlib import Path

from openpyxl import Workbook

from apps.engine import formats
from apps.engine.tests import grammar
from apps.engine.tests.saved import LANGUAGES

TABLES = (
    "short",
    "long",
    "given",
    "scaled",
    "places",
    "elapsed",
    "conditions",
    "texts",
    "grouped",
    "runs",
    "mixed",
    "lone",
    "clocks",
    "noons",
    "years",
    "wide",
    "blanks",
    "commas",
    "fractions",
    "choices",
    "minutes",
    "denominators",
    "trailing",
    "wholes",
    "percented",
    "spread",
    "zeros",
    "systems",
    "tagged",
    "dollars",
    "exponents",
    "sections",
    "scales",
    "covered",
    "powers",
    "orders",
    "months",
    "hidden",
    "later",
    "owed",
    "spare",
    "paid",
    "twice",
    "inside",
    "wider",
    "beside",
    "placed",
    "ties",
    "held",
    "budgets",
    "probes",
)
CHECKS = ("longer", "nine", "tails", "scientific")
PARTS = tuple(f"closed-{table}" for table in TABLES + CHECKS)
SYMBOLS = (("0",), ("#",), ("?",), ("digit", "4"), (".",), (",",), ("%",), ("ecma", " "))
SYMBOLS += (("quoted", "x"),)
MOST = 6
OTHERS_MOST = 5
PLACED = (("0",), ("#",), ("?",), ("quoted", "x"))
KINDS = tuple(("ecma", mark) for mark in sorted(grammar.SHOWN_LITERALLY - {"/", " "}))
KINDS += tuple((kind, mark) for kind in ("quoted", "escaped") for mark in "q.5,% ")
KINDS += (("space", "u"), ("fill", "f"), ("E", "+"), ("E", "-"))
KINDS += tuple(("noon", noon) for noon in grammar.NOONS)
KINDS_MOST = 5
# Zero; a fraction alone and its negative; a whole part longer than its placeholders, negative;
# one whose fraction rounds to the next whole.
VALUES = ("0", "0.6", "-0.6", "-1234.5678", "12.999")
LONG = 7
NINE = 9
SCIENTIFIC_MANTISSA = 5
SCIENTIFIC_MARKS = (("0",), ("#",), ("?",), (".",), (",",))
SCIENTIFIC_EXPONENT = (("0",), ("#",), ("?",))
SCIENTIFIC_VALUES = ("0", "0.0123", "12345.6789")
TAILS_OWN = 3
TAILS_PAST = 5
TAILS_MARKS = (("0",), ("#",), ("?",), ("quoted", "x"))
TAILS_VALUES = ("0", "0.3", "12.999")
CONDITION_OPS = ("<", "<=", "=", ">=", ">", "<>")
CONDITION_BOUNDS = ("-5", "0", "5")
CONDITION_BODIES = ('"{}"0', "General")
CONDITION_TEXT = '"t"@'
CONDITION_MARKS = "abc"
LONE_BODIES = (
    "General",
    '"x"General',
    'General"x"',
    "\\xGeneral",
    " General",
    '"x"General"y"',
    "$General",
    "-General",
    '"x"0',
    "x0",
    "0",
    '""General',
    "General General",
)
CLOCKS_MARKS = (".", ":", "0", "00", "AM/PM", "A/P", "h", "s", "x", "[h]", "[s]", "E+")
CLOCKS_MOST = 3
NOONS_LEADS = ("AM/PM", "A/P", "hAM/PM", "AM/PMh", '"x"AM/PM', "AM/PM:")
NOONS_ELAPSED = ("[h]", "[hh]", "[m]", "[s]")
NOONS_TAILS = (
    ":",
    "s",
    "ss",
    "m",
    "mm",
    "h",
    "d",
    "y",
    "x",
    ".0",
    "/",
    "0",
    "AM/PM",
    "General",
    "@",
)
CLOCKS_VALUES = ("0", "1", "0.5", "1.2345678", "-1.5")
WIDE_WHOLES = ("0", "#", "?", "00#")
WIDE_PARTINGS = (" ", "_b", '"xy"', "\\!")
WIDE_NUMERATORS = ("#", "?", "0", "#?", ".", "#.", ".0")
WIDE_RUNS = ("#", "0", "?", "00?0")
WIDE_TAILS = ("", "0", '"x"')
WIDE_VALUES = tuple(
    f"{mantissa}E+{power}" for power in range(247, 257) for mantissa in ("1", "-7.960681710667")
)
BLANKS_NUMERATORS = ("#", "##")
BLANKS_MOST = 4
BLANKS_GIVEN = ("1", "2", "10", "16", "100", "20000")
BLANKS_TAILS = ("", '"x"', '"x"0', '"x"?', '"x"1')
YEARS_NOONS = ("AM/PM", "A/P", "am/pm", "a/p")
YEARS_MOST = 5
CHOICES_BODIES = ('"a"0', "General", "mmm", "d", '"a"', "#.", "0.0", "0E+0", "# ?/?", "[h]", "")
CHOICES_FIRST = ("", "[>5]", "[<-5]")
CHOICES_SECOND = ("", "[>-5]", "[<5]", "[<>5]", "[=0]")
CHOICES_THIRD = (None, '"c"0', "General", "mmm", '"t"@', "")
MINUTES_MARKS = ("m", "mm", "h", "s", "ss", ".", ":", "0", "[h]", "[m]", "[s]", "d", "AM/PM")
MINUTES_MOST = 4
COMMAS_MARKS = (".", ",", "?", "0", "#", '"a"')
COMMAS_LEAST = 2
COMMAS_MOST = 5
COMMAS_VALUES = ("1", "1234567.891", "0.5")
FRACTIONS_HEADS = ("# ?/", "?/", "# ??/", "# ?/?")
FRACTIONS_GIVEN = ("3", "37", "3754")
FRACTIONS_TAILS = ("%", "0", "2", "x", "AM/PM", '"q"', " ", "?", "#")
FRACTIONS_MOST = 3
FRACTIONS_VALUES = ("1", "1.5", "0.25", "10")
DENOMINATORS_HEADS = ("# ?/", "0/")
DENOMINATORS_GIVEN = ("?", "?0?", "2", "092", "66570")
DENOMINATORS_TAILS = ("[$£]", "[$EUR-410]", ".", ",", "%", "_'", "\\[", "0", "#", '"x"')
DENOMINATORS_VALUES = ("0", "0.5", "-1", "1234.5678")
TRAILING_TAILS = ("_'", " ", "6", "64", "#", "0", ".", "%")
TRAILING_MOST = 3
WHOLES_HEADS = ("?", "0", "00", "?0", "?00", "#0", "")
WHOLES_BETWEEN = ('"€"', " ", "")
WHOLES_GIVEN = ("092", "2", "37", "?", "??")
WHOLES_TAGS = ("[$EUR-410]", "[$£]", '"x"', "")
PERCENTED_HEADS = ("0/", "%0/")
PERCENTED_GIVEN = ("2", "37", "66570")
PERCENTED_LATER = ("6", "64", "6485", "32767", "32769", "40000")
PERCENTED_TAILS = ("", "%", "%0", "0", ".0", "%.0", "#.%0", ".%0", "0%")
PERCENTED_VALUES = ("0", "1", "0.5", "0.001")
SPREAD_HEADS = ("0/#", "0?/%#")
SPREAD_MARKS = ("%", "?", "#", "0", ",", ".")
SPREAD_MOST = 5
ZEROS_WHOLES = ("#,##0 ", "0 ", "0,")
ZEROS_FRACTIONS = ("?/?", "?0/#", "?0%#/%#")
ZEROS_TAILS = ("0", "?", "#", "%", '"x"')
ZEROS_MOST = 3
ZEROS_VALUES = ("0", "0.5", "1234.5678")
SYSTEMS_TAGS = ("", "[$-F800]", "[$-F400]", "[$USD-F400]")
SYSTEMS_CONDITIONS = ("", "[=5]", "[>5]")
SYSTEMS_FIRST = ("0", '"a"0', "General", "#00.", "#00,", '"y"\\",0', "0.0")
SYSTEMS_SECOND = ("0", "000 00#/?0?", "0.0E+0", "0?/%#0,,.?", '"b"0', "General", "")
SYSTEMS_SECOND += ("0[$£]", "0[$CHF-409]", "[$-409]0", "[$-F400]0", "[$€-41A]General")
SYSTEMS_THIRD = (None, "0", "m.", "@", "General", "0[$£]")
SYSTEMS_VALUES = ("0", "1", "-1", "-0.5", "5", '"t"')
TAGGED_LEADS = (*SYSTEMS_TAGS, "[$-409]")
TAGGED_FIRST = ("0", '"a"0')
TAGGED_MIDDLE = ("0", "[$-F400]0", '"m"[$-409]0', '0[$£]"m"')
TAGGED_BODIES = (
    ("@",),
    ("@", "@"),
    ('"x"', "@"),
    ("@", '"x"'),
    ("-", "@"),
    ("\\x", "@"),
    ("_x", "@"),
)
TAGGED_BODIES += (("*x", "@"),)
TAGGED_MARKS = ("[$-F400]", "[$-F800]", "[$-409]", "[$USD-F400]", "[$£]")
TAGGED_VALUES = ('"t"', "1", "-1", "0")
DOLLARS_HEADS = ("", "0", "0.0", '"x"', "0;0", "[Red]")
DOLLARS_TAILS = ("", "0", '"x"', ";0")
DOLLARS_MOST = 255
EXPONENTS_HEADS = ("0E+", "#0,#E+", "0.0E-")
EXPONENTS_TAILS = ("\\[", "[$CHF-409]", "0", '"$"', "%", ",", ".", "#")
EXPONENTS_MOST = 3
SECTIONS_FIRST = ("##.#0", "0", "")
SECTIONS_MARKS = (":", "/", "_%", "@", "0", "[Black]", '"a"', ".")
SECTIONS_MOST = 3
SECTIONS_THIRD = (None, "0")
SECTIONS_VALUES = ("0", "1", "-1", "-0.5", '"t"')
SCALES_HEADS = ("0,.", "#,##0,.", "0,,.", ".,.", "?,.")
SCALES_MARKS = ("0", "?", "#", ".", '"x"', "\\x", " ", "%", "_)", "*x", "5", ",")
SCALES_MOST = 3
SCALES_VALUES = ("1", "1234.5678", "0.001234", "1234567.891", "-1234.5678")
COVERED_TAGS = ("[$-F800]", "[$-F400]", "[$USD-F800]")
COVERED_MARKS = ("0", "?", "/", "4", "%", ",", ".", "E+", '"x"', "A/P")
COVERED_MOST = 3
# About the bounds of a numerator in 16 bits over 4 and of the last day.
COVERED_VALUES = ("1", "1234.5678", "10000", "32768", "2958465", "2958466", "-5", "0.5")
POWERS_CODES = ("General", "@", "0;@", '"x"General', "General;@")
POWERS_VALUES = tuple(
    f"{sign}{mantissa}E{power:+d}"
    for power in (-101, -100, -99, -98, -97, -5, -4, 9, 10, 11, 97, 98, 99, 100, 101)
    for mantissa in ("1", "1.23456789", "9.9999", "9.99994", "9.99995", "9.999949", "9.99999")
    for sign in ("", "-")
)
ORDERS_HEADS = ("?/???", "# ?/???", "?/??", "# ??/??")
ORDERS_TAILS = tuple(
    "%" * percents + digit + "," * groups
    for percents in (1, 2, 3)
    for digit in ("", "0")
    for groups in (0, 1, 2)
)
ORDERS_VALUES = (
    "0.0003", "0.0007", "0.00013", "5.616", "24.24", "0.6504", "0.1742", "0.0988", "0.0029",
    "80.21", "0.8813", "23.79", "84.13", "9.361", "0.7661", "0.00277", "9.401E-05", "2.066",
    "0.03541", "0.04459", "0.8753", "0.1059", "4.477", "426.3", "743.7", "13.71", "14.73",
    "34.81", "0.233",
)  # fmt: skip
MONTHS_MARKS = ("M", "MM", "m", "mm", "h", "s", "ss", ",", "0", ":", "[m]", "[s]", "AM/PM")
MONTHS_MOST = 5
MONTHS_VALUES = ("0.5", "1.2345678", "1234.5678")
HIDDEN_MARKS = ("0", "?", "/", ",", ".", "%", " ")
HIDDEN_MOST = 5
LATER_HEADS = ("?/", "# ?/")
LATER_GIVEN = ("2", "33871", "?")
LATER_TAILS = ("9", "#", "0", "?", ".", "[$£]", '"x"')
LATER_MOST = 4
OWED_WHOLES = ("#,##0 ", "0,0 ", "#,0#-")
OWED_FRACTIONS = ("?/??", "??/??", "?#/??", "#/??")
OWED_MARKS = ("0", "#", "?")
OWED_MOST = 4
OWED_VALUES = ("0", "1", "0.5", "1234.5678")
SPARE_HEADS = ('?/2"x"', '# ?/2"x"', '?/33871"x"', '#,##0 ?/2"x"')
SPARE_MARKS = ("0", "#", "?", ".", '"y"')
SPARE_MOST = 5
SPARE_VALUES = ("0", "0.5", "0.3", "0.01", "1234.5678", "3.14159")
PAID_FRACTIONS = ("?/???", "??/???", "#/???", "?/????")
PAID_MOST = 5
PAID_VALUES = ("0", "1", "0.5", "0.25", "0.1", "1234.5678")
TWICE_WHOLES = ("", "0 ", "#,##0 ")
TWICE_NUMERATORS = ("?", "?%", "?%%", "0?")
TWICE_DENOMINATORS = ("?", "??", "?%0", "?%%#00", "%#%?")
TWICE_ENDS = (",.,", ",,.,", ",.,,", ",,.,,", ",.,.", ",.0,", ",..,", ",.", ",.0")
TWICE_VALUES = ("0", "1", "0.5", "1234.5678", "0.001234", "-0.5")
INSIDE_BASES = (
    "000",
    "0.00",
    "#,##0",
    "00%",
    "0E+00",
    "?/??",
    "# ?/?",
    "??/#0",
    "?/##.#0",
    "?/##,.#0",
    "0 ??/??",
)
INSIDE_MARKS = ("[$-409]", "[$-F800]", '""', "[$€]", '"x"')
INSIDE_VALUES = ("0", "1", "0.5", "1234.5678", "-1")
WIDER_TAGS = ("", "[$-F800]", "[$-F400]")
WIDER_WHOLES = ("", "0 ", "46260 ", "#,##0 ", "# ")
WIDER_FRACTIONS = ("?/?", "#/##")
WIDER_ENDS = (",", ",,", ",.", "%,", "%%%,")
WIDER_VALUES = ("0", "1", "0.5", "1234.5678", "0.000001", "-1")
BESIDE_TAGS = ("", "[$-F800]")
PLACED_BASES = (
    "0 ??/##,",
    "#,##0 ?/?,",
    "00 #/#0,",
    "0 ?/#,",
    "# ??/??,",
    '0"x" ?/?,',
    "0 ?/?%%,,",
)
PLACED_TAGS = ("[$-F800]", "[$-F400]")
PLACED_VALUES = ("0", "1", "0.1", "0.01", "0.001", "0.0001", "0.00001", "0.000001")
TIES_HEADS = ("# ", "")
TIES_DENOMINATORS = (*range(1, 100), 128, 255, 256, 1000, 1024, 4096, 21475, 32767)
TIES_SCALES = ("", "%", "%%")
TIES_WHOLES = (0, 1, 7, 12, 99, 123, 1234, 2047, 46000, 65535, 123456, 999999)
TIES_MOST = 12
HELD_HEADS = ("# ", "0 ")
HELD_FRACTIONS = ("?/1", "?/2", "?/4", "?/8", "?/?", "??/??", "???/???")
HELD_SCALES = {",,": -6, ",": -3, "%": 2, "%%": 4, "%%%": 6}
HELD_BASES = (
    100000000000000,
    123456789012300,
    281474976710600,
    562949953421300,
    900719925474000,
    999999999999800,
)
HELD_STEPS = 100
HELD_DIGITS = (13, 14, 15, 16)
BESIDE_WHOLES = ("0 ", "46260 ", "# ", "46260_B*;", "0*;")
BESIDE_NUMERATORS = ("?", "#", "89")
BESIDE_DENOMINATORS = (
    "#",
    "#,",
    "#,.#0",
    '#"x"#,.#0',
    '#"x"#.#0',
    '#"x"#,',
    '"A"#"x"#,.#0',
    "#[$-409]#,.#0",
)
CONDITION_VALUES = (
    "-1000",
    "-6",
    "-5",
    "-4",
    "-1",
    "-0.5",
    "-0.4",
    "0",
    "0.4",
    "0.5",
    "1",
    "4",
    "5",
    "6",
    "1000",
)
TEXTS_MARKS = (("@",), ("/",), ("quoted", "x"), ("0",), ("?",), (".",))
TEXTS_MOST = 6
TEXTS_VALUES = ("0", "-1.5", "12.999", '"abc"')
GROUPED_WHOLES = ("#,##0 ", "0 ")
GROUPED_FRACTIONS = ("?/?",)
GROUPED_MARKS = ("0", "#", "?", ",")
GROUPED_MOST = 3
GROUPED_VALUES = ("0.5", "1234.5678")
RUNS_WHOLES = ("#,##0 ", "#,### ", "0,0 ")
RUNS_FRACTIONS = ("?/?", "??/??")
RUNS_MOST = 8
RUNS_SPLIT = ('0"y"0', '00"y"0', '0"y"00', '0"y"0"y"0', '000"y"000', '0000"y"0000', "0 0", "0.0")
RUNS_MIXED = ("00?0", "0?00", "0?0?0", "0?", "0??0")
MIXED_MOST = 9
BUDGET_DRAWN = 300
BUDGET_SEED = 626028135
PROBED = (
    "0",
    "#",
    "?",
    ".",
    ",",
    "%",
    "/",
    " ",
    "E+",
    "e-",
    "@",
    "$",
    "-",
    "x",
    '"a"',
    '"ab"',
    '""',
    "\\a",
    "_a",
    "*a",
    ":",
    "5",
    ";",
    "\\$",
    '"$"',
    "d",
    "dd",
    "ddd",
    "dddd",
    "m",
    "mm",
    "mmm",
    "mmmm",
    "mmmmm",
    "y",
    "yy",
    "yyyy",
    "h",
    "hh",
    "s",
    "ss",
    "AM/PM",
    "A/P",
    "General",
    "[Red]",
    "[>1]",
    "[$-409]",
    "[$€]",
    "[$€-409]",
    "[h]",
    "[mm]",
    "[ss]",
    ".0",
    "s.00",
)
PROBED_NUMBERS = ("0", "#", "?", ".", ",", "%", "/", " ", "x")
PROBED_SIZES = range(60, 84)
PADDED_DOLLARS = 2
# Excel refused no code of budgets and probes up to SURE characters long ([$€] and 78 x, 82, is the
# shortest), and past it numformat's weights only come near its own, so a longer code is not held.
SURE = 81
LEADING = re.compile(r"^((?:\[[^\]]*\])*)")
COLONS = (
    "0::x",
    "0:x:",
    "0x::",
    "0x:",
    "0 :: ",
    "::0",
    ":0:",
    "0::0",
    '0":"',
    '0"::"',
    "0\\:\\:",
    "0.0::",
    "0:-:",
    "#::",
)
NINE_CODES = 60000
NINE_SEED = 102963206341246
LONGER = (("0",), ("#",), ("?",), (".",), ("quoted", "x"))
# VALUES but 0,6, with parts whose best fraction over each run of one to five placeholders has a
# denominator of each length the run holds, of nothing over the shortest (0,0123 and 0,0045), and
# rounding to the next whole without one (5,97 over a single place).
SPREAD = ("0", "-0.6", "12.999", "-1234.5678", "0.3", "0.0123", "5.97", "0.0045")
WHOLES = ((), (("#",), ("ecma", " ")), (("0",), ("ecma", " ")))
NUMERATORS = ((("?",),), (("#",),), (("?",), ("?",)), (("0",), ("?",)))
# Denominators of each length about the bounds of 15 and 16 bits and the places 2**16 less one of
# them leaves, and after leading zeros.
GIVEN = (
    *("1", "2", "9", "10", "16", "99", "100", "128", "999", "1000", "1024", "9999", "10000"),
    *("16384", "32767", "32768", "32769", "32770", "32771", "32800", "32991", "33000", "40000"),
    *("50000", "60000", "65000", "65436", "65526", "65530", "65533", "65534", "65535", "65536"),
    *("65537", "65540", "98304", "99999", "08", "092", "0100", "032769"),
)
TAILS = ((), (("?",),), (("?",), ("?",)), (("0",),))
TAILS += tuple((("quoted", "x"), *tail) for tail in TAILS[1:3] + ((("0",), ("?",)),))
# Parts whose continued fractions run deep, π's to a denominator of every length, about whole
# parts of up to nine digits and the bound of 15 bits.
DEEP = ("0", "0.5", "-0.6", "0.123", "0.0123", "5.97", "-1234.5678", "3.14159265358979")
DEEP += ("67577.9495", "123456789.123", "32767.5", "0.999999")
SCALING = ("0 #/0,", "0 ./0,", "# ./#,", "# ?/?,", "?/?,", "0 ?/?,", "# ??/??,", "0 0/0,")
SCALING += ("0 .0/0,", "#/0,", "0/0,", "0 #/0,,", "0%#/0,", '0"x"#/0,', '0 #/0,"x"')
SCALING += ("0 ./00,", '0 "x"./0,', '0 ."x"/0,', "0 .#/0,", "0 .?/0,", "#,##0 ?/?,", "0 #/00,")
SCALING += ('0 #/0"x",',)
# Scaled 10**253 times up they run from 10**245 to past 10**253, with either sign.
SCALED = tuple(
    sign + format(Decimal(digits).scaleb(-places), "f")
    for sign in ("", "-")
    for digits in ("1", "6", "9.99")
    for places in range(9)
)
PLACES = ("?/???????", "?/????????", "?/?????????", "?/??????????", "# ?/????????")
PLACES += ("# ?/??????????", "0/00000000", "?/40000", "# ?/40000", "?/32769", "?/65535", "?/65536")
# Parts whose convergents have denominators of seven, eight below and above 2**24, nine and ten
# digits (√2 less one: 6625109, 15994428, 38613965, 131836323, 1000082191), e, γ, π's part, the
# golden ratio's, a whole part whose products with the numerators pass 32 bits, and the
# reciprocals of 2**31 less one and of the largest prime below 2**32.
CONVERGING = ("0.414213562373095", "-0.414213562373095", "1.4142135623731", "2.71828182845905")
CONVERGING += ("0.577215664901533", "0.14159265358979", "0.618033988749895", "12345.4142135624")
CONVERGING += ("0.00000000046566128752458", "0.000000000232830644807878")
ELAPSED = ("[h]", "[m]", "[s]", "[hhh]", "[hh]:mm", "[mm]:ss", "[s].00", "[h]:mm:ss.000")
# Serials whose seconds pass 2**53 (104249991,374 days) and grow to past the largest double.
AGES = ("1000000000", "104249991.374", "104249992", "123456789.123", "1000000000000")
AGES += ("-123456789.123", "4.3074212E+171", "1E+100", "8.134370293E+246", "9.99999999999999E+307")
ROWS = 1_000_000


def _around(symbols: tuple, sizes: range):
    for size in sizes:
        for cut in range(size):
            for left in itertools.product(symbols, repeat=cut):
                for right in itertools.product(symbols, repeat=size - 1 - cut):
                    yield (*left, ("/",), *right)


def _kinded():
    for kind in KINDS:
        for tokens in _around(PLACED, range(1, KINDS_MOST)):
            for at in range(len(tokens) + 1):
                yield (*tokens[:at], kind, *tokens[at:])


def _given():
    for whole, numerator, given, tail in itertools.product(WHOLES, NUMERATORS, GIVEN, TAILS):
        digits = tuple(("0",) if digit == "0" else ("digit", digit) for digit in given)
        yield (*whole, *numerator, ("/",), *digits, *tail)


def languages(table: str) -> tuple[str, ...]:
    """The languages a table is saved in: short's in each, as it holds how each language writes
    the marks, months' in German alone, whose month and minute are letters of two cases, the
    others' in en alone."""
    if table == "months":
        return ("de",)
    return LANGUAGES if table in ("short", "years") else ("en",)


@cache
def codes(table: str, language: str) -> list[str]:
    """Each code of the table in the language, written as TEXT reads it, once: French writes its
    group separator as a space."""
    if table == "short":
        found = _around(SYMBOLS, range(1, (MOST if language == "en" else OTHERS_MOST) + 1))
        if language == "en":
            found = itertools.chain(found, _kinded())
    elif table == "long":
        found = _around(LONGER, range(LONG, LONG + 1))
    elif table == "longer":
        found = _around(LONGER, range(LONG + 1, LONG + 2))
    elif table == "nine":
        found = _drawn()
    elif table == "tails":
        found = _tailed()
    elif table == "scientific":
        found = _scientific()
    elif table == "given":
        found = _given()
    elif table == "conditions":
        return list(_conditioned())
    elif table == "lone":
        return [
            f"[{op}{bound}]{body}{text}"
            for op in CONDITION_OPS
            for bound in CONDITION_BOUNDS
            for body in LONE_BODIES
            for text in ("", ";" + CONDITION_TEXT)
            if grammar.valid(f"[{op}{bound}]{body}{text}", language)
        ]
    elif table == "clocks":
        found = (
            "".join(parts)
            for size in range(1, CLOCKS_MOST + 1)
            for parts in itertools.product(CLOCKS_MARKS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "noons":
        found = (
            lead + elapsed + "".join(tail)
            for lead in NOONS_LEADS
            for elapsed in NOONS_ELAPSED
            for size in range(3)
            for tail in itertools.product(NOONS_TAILS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "wide":
        found = (
            "".join(parts)
            for parts in itertools.product(
                WIDE_WHOLES, WIDE_PARTINGS, WIDE_NUMERATORS, ("/",), WIDE_RUNS, WIDE_TAILS
            )
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "blanks":
        found = (
            "0 " + numerator + "/" + "".join(run) + tail
            for numerator in BLANKS_NUMERATORS
            for run in (
                *(
                    run
                    for size in range(1, BLANKS_MOST + 1)
                    for run in itertools.product("0#?1", repeat=size)
                ),
                *BLANKS_GIVEN,
            )
            for tail in BLANKS_TAILS
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "years":
        letters = formats.CODES[language]
        found = (
            letter * size + noon + tail
            for each in (letters.year, letters.weekday)
            for letter in dict.fromkeys((each.lower(), each.upper()))
            for size in range(1, YEARS_MOST + 1)
            for noon in YEARS_NOONS
            for tail in ("", letters.hour)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "choices":
        found = (
            ";".join(part for part in (first + one, second + two, third) if part is not None)
            for first in CHOICES_FIRST
            for one in CHOICES_BODIES
            for second in CHOICES_SECOND
            for two in CHOICES_BODIES
            for third in CHOICES_THIRD
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "minutes":
        found = (
            "".join(parts)
            for size in range(1, MINUTES_MOST + 1)
            for parts in itertools.product(MINUTES_MARKS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "commas":
        found = (
            "".join(parts)
            for size in range(COMMAS_LEAST, COMMAS_MOST + 1)
            for parts in itertools.product(COMMAS_MARKS, repeat=size)
        )
        held = [code for code in found if "," in code and grammar.valid(code, language)]
        return held + [code + ";General" for code in held if code.count(".") > 1]
    elif table == "fractions":
        found = (
            head + given + "".join(tail)
            for head in FRACTIONS_HEADS
            for given in FRACTIONS_GIVEN
            for size in range(FRACTIONS_MOST + 1)
            for tail in itertools.product(FRACTIONS_TAILS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "denominators":
        found = (
            head + given + "".join(tail)
            for head in DENOMINATORS_HEADS
            for given in DENOMINATORS_GIVEN
            for size in range(3)
            for tail in itertools.product(DENOMINATORS_TAILS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "trailing":
        found = (
            "0/" + given + "".join(tail)
            for given in DENOMINATORS_GIVEN
            for size in range(TRAILING_MOST + 1)
            for tail in itertools.product(TRAILING_TAILS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "wholes":
        found = (
            head + between + "#/" + given + tag
            for head in WHOLES_HEADS
            for between in WHOLES_BETWEEN
            for given in WHOLES_GIVEN
            for tag in WHOLES_TAGS
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "percented":
        found = (
            head + given + " " + later + tail
            for head in PERCENTED_HEADS
            for given in PERCENTED_GIVEN
            for later in PERCENTED_LATER
            for tail in PERCENTED_TAILS
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "spread":
        found = (
            head + "".join(tail)
            for head in SPREAD_HEADS
            for size in range(SPREAD_MOST + 1)
            for tail in itertools.product(SPREAD_MARKS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "zeros":
        found = (
            whole + fraction + "".join(tail)
            for whole in ZEROS_WHOLES
            for fraction in ZEROS_FRACTIONS
            for size in range(ZEROS_MOST + 1)
            for tail in itertools.product(ZEROS_TAILS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "systems":
        found = (
            ";".join(part for part in (tag + condition + first, second, third) if part is not None)
            for tag in SYSTEMS_TAGS
            for condition in SYSTEMS_CONDITIONS
            for first in SYSTEMS_FIRST
            for second in SYSTEMS_SECOND
            for third in SYSTEMS_THIRD
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "tagged":
        marked = [
            "".join(body) if mark is None else "".join((*body[:at], mark, *body[at:]))
            for body in TAGGED_BODIES
            for mark in (None, *TAGGED_MARKS)
            for at in ((0,) if mark is None else range(len(body) + 1))
        ]
        found = (
            ";".join((lead + first, *middle, text))
            for lead in TAGGED_LEADS
            for first in TAGGED_FIRST
            for size in range(3)
            for middle in itertools.product(TAGGED_MIDDLE, repeat=size)
            for text in marked
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "dollars":
        found = (
            head + "$" * size + tail
            for head in DOLLARS_HEADS
            for tail in DOLLARS_TAILS
            for size in range(1, DOLLARS_MOST + 1)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "exponents":
        found = (
            head + "".join(tail)
            for head in EXPONENTS_HEADS
            for size in range(EXPONENTS_MOST + 1)
            for tail in itertools.product(EXPONENTS_TAILS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "sections":
        found = (
            ";".join(part for part in (first, "".join(second), third) if part is not None)
            for first in SECTIONS_FIRST
            for size in range(1, SECTIONS_MOST + 1)
            for second in itertools.product(SECTIONS_MARKS, repeat=size)
            if "@" in second
            for third in SECTIONS_THIRD
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "scales":
        found = (
            head + "".join(tail)
            for head in SCALES_HEADS
            for size in range(SCALES_MOST + 1)
            for tail in itertools.product(SCALES_MARKS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "covered":
        found = (
            "".join((*body[:at], tag, *body[at:]))
            for tag in COVERED_TAGS
            for size in range(1, COVERED_MOST + 1)
            for body in itertools.product(COVERED_MARKS, repeat=size)
            for at in range(size + 1)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "orders":
        found = (head + tail for head in ORDERS_HEADS for tail in ORDERS_TAILS)
        return [code for code in found if grammar.valid(code, language)]
    elif table == "months":
        found = (
            "".join(parts)
            for size in range(1, MONTHS_MOST + 1)
            for parts in itertools.product(MONTHS_MARKS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "hidden":
        found = (
            "[$-F800]" + "".join(body)
            for size in range(1, HIDDEN_MOST + 1)
            for body in itertools.product(HIDDEN_MARKS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "later":
        found = (
            head + given + "".join(tail)
            for head in LATER_HEADS
            for given in LATER_GIVEN
            for size in range(LATER_MOST + 1)
            for tail in itertools.product(LATER_TAILS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "owed":
        found = (
            f'{whole}{fraction}"x"{"".join(tail)}'
            for whole in OWED_WHOLES
            for fraction in OWED_FRACTIONS
            for size in range(OWED_MOST + 1)
            for tail in itertools.product(OWED_MARKS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "spare":
        found = (
            head + "".join(tail)
            for head in SPARE_HEADS
            for size in range(SPARE_MOST + 1)
            for tail in itertools.product(SPARE_MARKS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "paid":
        found = (
            f'#,##0 {fraction}"x"{"".join(tail)}'
            for fraction in PAID_FRACTIONS
            for size in range(PAID_MOST + 1)
            for tail in itertools.product(OWED_MARKS, repeat=size)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "twice":
        found = (
            f"{whole}{numerator}/{denominator}{end}"
            for whole in TWICE_WHOLES
            for numerator in TWICE_NUMERATORS
            for denominator in TWICE_DENOMINATORS
            for end in TWICE_ENDS
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "inside":
        found = itertools.chain(
            INSIDE_BASES,
            (
                base[:at] + mark + base[at:]
                for base in INSIDE_BASES
                for mark in INSIDE_MARKS
                for at in range(1, len(base))
            ),
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "wider":
        found = (
            f"{tag}{whole}{fraction}{end}"
            for tag in WIDER_TAGS
            for whole in WIDER_WHOLES
            for fraction in WIDER_FRACTIONS
            for end in WIDER_ENDS
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "beside":
        found = (
            f"{tag}{whole}{numerator}/{denominator}"
            for tag in BESIDE_TAGS
            for whole in BESIDE_WHOLES
            for numerator in BESIDE_NUMERATORS
            for denominator in BESIDE_DENOMINATORS
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "placed":
        found = (
            base[:at] + tag + base[at:]
            for base in PLACED_BASES
            for tag in PLACED_TAGS
            for at in range(len(base) + 1)
        )
        return [code for code in dict.fromkeys(found) if grammar.valid(code, language)]
    elif table == "grouped":
        return list(_grouped())
    elif table == "runs":
        return list(_runs())
    elif table == "mixed":
        return list(_mixed())
    elif table == "budgets":
        return _padded(_budgeted(), range(84))
    elif table == "probes":
        return _padded(_probed(), PROBED_SIZES)
    elif table == "texts":
        found = _around(TEXTS_MARKS, range(1, TEXTS_MOST + 1))
    else:
        listed = {"scaled": SCALING, "places": PLACES, "elapsed": ELAPSED, "powers": POWERS_CODES}[
            table
        ]
        return [code for code in listed if grammar.valid(code, language)]
    written = dict.fromkeys(grammar.written((tokens,), language) for tokens in found)
    return [code for code in written if grammar.valid(code, language)]


def values(table: str) -> tuple[str, ...]:
    each = {
        "scientific": SCIENTIFIC_VALUES,
        "tails": TAILS_VALUES,
        "short": VALUES,
        "given": DEEP,
        "scaled": SCALED,
        "places": CONVERGING,
        "elapsed": AGES,
        "conditions": CONDITION_VALUES,
        "lone": CONDITION_VALUES,
        "clocks": CLOCKS_VALUES,
        "noons": CLOCKS_VALUES,
        "years": CLOCKS_VALUES,
        "wide": WIDE_VALUES,
        "blanks": WIDE_VALUES,
        "choices": CONDITION_VALUES,
        "minutes": CLOCKS_VALUES,
        "commas": COMMAS_VALUES,
        "fractions": FRACTIONS_VALUES,
        "denominators": DENOMINATORS_VALUES,
        "exponents": DENOMINATORS_VALUES,
        "trailing": DENOMINATORS_VALUES,
        "wholes": DENOMINATORS_VALUES,
        "systems": SYSTEMS_VALUES,
        "tagged": TAGGED_VALUES,
        "percented": PERCENTED_VALUES,
        "spread": PERCENTED_VALUES,
        "zeros": ZEROS_VALUES,
        "sections": SECTIONS_VALUES,
        "scales": SCALES_VALUES,
        "covered": COVERED_VALUES,
        "powers": POWERS_VALUES,
        "orders": ORDERS_VALUES,
        "months": MONTHS_VALUES,
        "hidden": COVERED_VALUES,
        "later": DENOMINATORS_VALUES,
        "owed": OWED_VALUES,
        "spare": SPARE_VALUES,
        "paid": PAID_VALUES,
        "twice": TWICE_VALUES,
        "inside": INSIDE_VALUES,
        "wider": WIDER_VALUES,
        "beside": WIDER_VALUES,
        "placed": PLACED_VALUES,
        "texts": TEXTS_VALUES,
        "grouped": GROUPED_VALUES,
        "runs": GROUPED_VALUES,
        "mixed": GROUPED_VALUES,
        "budgets": ("1",),
        "dollars": ("1",),
        "probes": ("1",),
    }
    return each.get(table, SPREAD)


def rows(table: str, language: str) -> list[tuple[str, str]]:
    if table == "ties":
        return _tied()
    if table == "held":
        return _held()
    return [(code, value) for code in codes(table, language) for value in values(table)]


def _tied() -> list[tuple[str, str]]:
    found = []
    for head, denominator, scale in itertools.product(TIES_HEADS, TIES_DENOMINATORS, TIES_SCALES):
        code = f"{head}?/{denominator}{scale}"
        for whole, count in itertools.product(TIES_WHOLES, range(min(denominator, TIES_MOST))):
            value = (whole + Fraction(2 * count + 1, 2 * denominator)) / 100 ** len(scale)
            written = Decimal(value.numerator) / Decimal(value.denominator)
            digits = written.normalize().as_tuple().digits
            if Fraction(written) == value and len(digits) <= 15:
                found.append((code, f"{written.normalize():f}"))
    return found


def _held() -> list[tuple[str, str]]:
    found = []
    for scale, power in HELD_SCALES.items():
        written = [
            f"{Decimal(base + step).scaleb(digits - 15 - power).normalize():f}"
            for digits in HELD_DIGITS
            for base in HELD_BASES
            for step in range(HELD_STEPS)
        ]
        for head, fraction in itertools.product(HELD_HEADS, HELD_FRACTIONS):
            code = f"{head}{fraction}{scale}"
            if grammar.valid(code, "en"):
                found += [(code, value) for value in written]
    return found


def workbook(table: str, language: str) -> Workbook:
    book = Workbook(write_only=True)
    for at, (code, value) in enumerate(rows(table, language)):
        if not at % ROWS:
            sheet = book.create_sheet(f"TEXT {at // ROWS + 1}")
        sheet.append([f'=TEXT({value},"{code.replace('"', '""')}")'])
    return book


def _scientific():
    for size in range(1, SCIENTIFIC_MANTISSA + 1):
        for mantissa in itertools.product(SCIENTIFIC_MARKS, repeat=size):
            for sign in "+-":
                for width in range(1, 4):
                    for exponent in itertools.product(SCIENTIFIC_EXPONENT, repeat=width):
                        yield (*mantissa, ("E", sign), *exponent)


def _conditioned():
    conditions = ("", *(f"[{op}{bound}]" for op in CONDITION_OPS for bound in CONDITION_BOUNDS))
    for count in (1, 2, 3):
        for chosen in itertools.product(conditions, repeat=count):
            for bodies in itertools.product(CONDITION_BODIES, repeat=count):
                numbers = [
                    condition + body.format(CONDITION_MARKS[at])
                    for at, (condition, body) in enumerate(zip(chosen, bodies, strict=True))
                ]
                yield ";".join(numbers)
                if count < 3:
                    yield ";".join((*numbers, CONDITION_TEXT))


def _grouped():
    for whole in GROUPED_WHOLES:
        for fraction in GROUPED_FRACTIONS:
            for size in range(GROUPED_MOST + 1):
                for tail in itertools.product(GROUPED_MARKS, repeat=size):
                    yield f'{whole}{fraction}"x"{"".join(tail)}'


def _runs():
    runs = ["0" * size for size in range(1, RUNS_MOST + 1)]
    for whole in RUNS_WHOLES:
        for fraction in RUNS_FRACTIONS:
            for run in (*runs, *RUNS_SPLIT, *RUNS_MIXED):
                yield f'{whole}{fraction}"x"{run}'


def _mixed():
    tails = []
    for first in "0#":
        tails += [first + "?" + "0" * size for size in range(MIXED_MOST + 1)]
        tails += [first + "?" * size for size in range(2, 5)]
    tails += ["#" * size for size in range(1, 9)] + ["?" * size for size in range(1, 5)]
    tails += ["0?#", "0?#0", "#?#", "0#?0", "0?0#", "0?0?"]
    for tail in tails:
        yield f'#,##0 ?/?"x"{tail}'


def _tailed():
    for run in (("0",), ("#",), ("?",)):
        for own in range(TAILS_OWN + 1):
            for past in range(TAILS_PAST + 1):
                for before in itertools.product(TAILS_MARKS, repeat=own):
                    for after in itertools.product(TAILS_MARKS, repeat=past):
                        yield (("#",), ("/",), *run, ("quoted", "x"), *before, (".",), *after)


def _drawn():
    """NINE_CODES codes of NINE tokens of LONGER about one slash, drawn from NINE_SEED: all of
    them being 9 * 5**8 codes, past what a table can hold."""
    draw = random.Random(NINE_SEED)
    for _ in range(NINE_CODES):
        cut = draw.randrange(NINE)
        left = draw.choices(LONGER, k=cut)
        right = draw.choices(LONGER, k=NINE - 1 - cut)
        yield (*left, ("/",), *right)


def write(folder: Path, table: str) -> None:
    for language in languages(table):
        workbook(table, language).save(folder / f"closed-{table}-{language}-codes.xlsx")


def _budgeted() -> list[str]:
    codes = [*grammar.covering(), *grammar.drawn(BUDGET_SEED, BUDGET_DRAWN)]
    return list(dict.fromkeys(grammar.written(code, "en") for code in codes))


def _probed() -> list[str]:
    pairs = ("".join(parts) for size in (1, 2) for parts in itertools.product(PROBED, repeat=size))
    triples = ("".join(parts) for parts in itertools.product(PROBED_NUMBERS, repeat=3))
    found = dict.fromkeys((*pairs, *triples, *COLONS))
    return [code for code in found if grammar.valid(code, "en")]


def _padded(codes: list[str], sizes: range) -> list[str]:
    return [
        LEADING.sub(lambda lead, run="$" * dollars + "x" * size: lead[1] + run, code, count=1)
        for code in codes
        for dollars in range(PADDED_DOLLARS + 1)
        for size in sizes
    ]
