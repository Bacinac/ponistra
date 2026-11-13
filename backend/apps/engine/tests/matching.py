"""The workbook in which Excel shows how it matches and orders values (D22). Criteria holds every
criterion of COUNTIF put to every kind of cell, each alone and in whole columns where the empty
cells count too. Match, XMatch, Wild, Equal, Less, VLookup, HLookup and XLookup put each value to
each cell as MATCH, XMATCH, XMATCH with wildcards, the = and < operators, VLOOKUP, HLOOKUP and
XLOOKUP do. Order holds a text for every character Excel may meet, sampled where a script has
thousands that neither case nor decomposition relates, with each one's decompositions and case
forms, Croatian digraphs, hyphens and apostrophes, and the Tibetan letters Croatian weighs the dz
digraphs by before a letter of each weight from Latin to Tibetan; SORT orders them, and each one
is put to the next as =, <, COUNTIF, MATCH and XMATCH do and to the two after it as COUNTIF does.
Halving holds lines of numbers sorted, reversed, drawn at random and interrupted by blanks,
text, logicals and errors, and looks numbers, a text, a logical and an empty cell up in each
line as the lookups that halve a line do: MATCH, VLOOKUP and LOOKUP approximately and XMATCH
searching by halves either way. Sorting sorts values of every kind by each of SORT's arguments,
Probes looks an empty cell, patterns and empty text up where a lookup may read them its own way,
and Nearest looks values of every kind up in lines of them as XMATCH does for the next smaller
or larger one, from the first and from the last. `python -m apps.engine.tests.matching <file>`
writes it without values; saved by Excel, once in Croatian and once in English, it comes here as
matching-hr.xlsx and matching-en.xlsx."""

import sys
import unicodedata
from pathlib import Path
from random import Random

from openpyxl import Workbook
from openpyxl.worksheet.formula import ArrayFormula

from apps.engine.collation import collation
from apps.engine.parse import parse, written
from apps.engine.tests.saved import LANGUAGES, TOLD

PATHS = {code: Path(__file__).with_name(f"matching-{code}.xlsx") for code in LANGUAGES}
LOCALE = ("Column", 1, 4)


class Formula(str):
    """A cell whose value a formula makes: an error, empty text, a control character."""


CELLS = (
    None, Formula('=""'), 0, 12, -12, 1.5, 12.5, 12.0000000000001, 1e15, 46143, True, False,
    "12", "012", " 12", "12 ", "12,0", "12.0", "1,5", "1.5", "1,50", "1.5.", "1.5.2026", "1/5",
    "12%", "1E1", "€12", "(12)", "0", "-0", "0,0", "TRUE", "true", "FALSE", "#N/A",
    Formula("=NA()"), Formula("=1/0"), "abc", "ABC", "abd", "ab", "a", "b", "z", "x", "a*c",
    "abc*", "*", "?", "~", " ", "-", "=", ">", "<", "<>", "=12", "ß", "ss", "SS", "straße",
    "STRASSE", "strasse", "ſ", "s", "S", "İ", "i", "ı", "I", "ǆ", "dž", "Dž", "lj", "lJ", "ǉ", "æ",
    "ae", "co-op", "coop", "~a", "~~", "~~~", "a~b", "12 €", "$12", "\U0001F600", "e\u0301",
)  # fmt: skip
OPERANDS = (
    "", "12", "012", "12,0", "12.0", "1,5", "1.5", "0", "-0", "12%", "1E1", "1.5.2026", "1/5",
    "€12", " 12", "12 ", "abc", "ABC", "ab", "b", "z", "x", "TRUE", "true", "FALSE", "#N/A",
    "#n/a", "#DIV/0!", "a*", "*", "?", "??", "~*", "~?", "~~", "~", "a~", "1*", "12*", "*2", " ",
    "ß", "ss", "SS", "s*", "*ß", "?ß", "stra?e", "stra??e", "STRA*E", "*SSE", "ſ", "ſ*", "s?", "i",
    "İ", "ı", "I", "dž", "ǆ", "lj", "æ", "co-op", "coop", "=", "<", ">", "<>", "=12", "l?", "*j",
    "lj*", "l*", "~a", "~~~", "a~b", "~~*", "12 €", "12€", "$12", "12 $", "-€12", "(€12)",
    "\U0001F600", "e\u0301", "e?", "?\u0301", "a*~", "*~", "~a*", "~~?", "-12 €", "(12 €)",
    "12 € ", "€ 12", "12,5 €", "12.5 €", "1.200 €", "1,200 €", "-$12", "($12)", "$-12", "$ 12",
    "12$", "$12.5", "$12,5", "$1,200", "$1.200",
)  # fmt: skip
OPERATORS = ("", "=", "<>", "<", "<=", ">", ">=")
GIVEN = (None, 0, 12, -12, 1.5, 46143, True, False, Formula("=NA()"), Formula('=""'))
COLUMN = (
    "COUNTIF(Column!$A:$A,$A{r})",
    "COUNTIF(Column!$A$1:$A$200,$A{r})",
    "COUNTIF(Column!$A:$B,$A{r})",
    "COUNTIFS(Column!$A:$A,$A{r},Column!$B:$B,$A{r})",
    "COUNTIFS(Column!$A:$A,$A{r})",
    "SUMIF(Column!$A:$A,$A{r},Column!$C:$C)",
    "SUMIFS(Column!$C:$C,Column!$A:$A,$A{r})",
    "AVERAGEIF(Column!$A:$A,$A{r},Column!$C:$C)",
    "MINIFS(Column!$C:$C,Column!$A:$A,$A{r})",
)
GRIDS = {
    "Match": "ISNUMBER(MATCH($A{r},{c}$1,0))",
    "XMatch": "ISNUMBER(XMATCH($A{r},{c}$1))",
    "Wild": "ISNUMBER(XMATCH($A{r},{c}$1,2))",
    "Equal": "$A{r}={c}$1",
    "Less": "$A{r}<{c}$1",
    "VLookup": "ISNA(VLOOKUP($A{r},{c}$1,1,FALSE))",
    "HLookup": "ISNA(HLOOKUP($A{r},{c}$1,1,FALSE))",
    "XLookup": "ISNA(XLOOKUP($A{r},{c}$1,{c}$1))",
}
ESCAPED = 'SUBSTITUTE(SUBSTITUTE(SUBSTITUTE({},"~","~~"),"*","~*"),"?","~?")'
NEIGHBOURS = (
    "B{r}=B{n}",
    "B{r}<B{n}",
    'COUNTIF(B{r},"="&' + ESCAPED.format("B{n}") + ")",
    "ISNUMBER(MATCH(" + ESCAPED.format("B{n}") + ",B{r},0))",
    "ISNUMBER(XMATCH(B{n},B{r}))",
    'COUNTIF(B{r},"="&' + ESCAPED.format("B{s}") + ")",
    'COUNTIF(B{r},"="&' + ESCAPED.format("B{t}") + ")",
)
# Scripts of thousands of characters that neither case nor decomposition relate to another:
# their first, their last and SAMPLES between.
SAMPLED = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xA000, 0xA48F), (0xAC00, 0xD7A3), (0x12000, 0x1254F),
    (0x13000, 0x143FF), (0x14400, 0x1467F), (0x16800, 0x16A3F), (0x17000, 0x18CFF),
    (0x18D00, 0x18D08), (0x1B170, 0x1B2FB), (0x20000, 0x2EE5F), (0x30000, 0x323AF),
)  # fmt: skip
SAMPLES = 64
UNASSIGNED = 4099
PRIVATE = 509
LATIN, TIBETAN = 14, 64
DZ = ("\u0f51", "\u0f56", "\u0f54")
EXTRA = (
    "", "lj", "Lj", "LJ", "lJ", "ǉ", "ǈ", "Ǉ", "nj", "Nj", "NJ", "ǌ", "ǋ", "Ǌ", "dž", "Dž", "DŽ",
    "dZ", "ǆ", "ǅ", "Ǆ", "dz", "dzs", "ǳ", "l", "lz", "lja", "ljz", "m", "n", "nz", "nja", "o",
    "d", "dzz", "džz", "đ", "dj", "e", "c", "č", "ć", "cz", "čz", "ćz", "s", "š", "sz", "šz", "z",
    "ž", "zz", "žz", "ss", "SS", "sS", "Ss", "ß", "ẞ", "sß", "ßs", "sss", "ßß", "ssss", "st",
    "straße", "strasse", "STRASSE", "ae", "æ", "Æ", "aE", "oe", "œ", "Œ", "ij", "ĳ", "Ĳ", "ff",
    "ﬀ", "fi", "ﬁ", "th", "þ", "co-op", "coop", "co'op", "co op", "co–op", "co—op", "co‐op",
    "co­op", "a-b", "ab", "a'b", "a b", "a–b", "-", "'", "--", "''", "-a", "'a", "a-", "a'",
    " a", "a ", "  a", "a  b", "a\tb", "a\nb", "10", "9", "09", "1", "01", "1a", "a1", "a10",
    "a9", "ạ́", "ạ́", "á", "ạ", "ạ́", "ấ", "ấ", "ấ",
    "é", "é", "́", "́́", "a​b", "a‍b", "a﻿b", "a b",
    "\u0f51", "\u0f51\u030c", "\u0f51\u0306", "\u0f4c\u030c", "\u0f56\u030c", "\u0f56\u0306",
    "\u0f54\u030c", "\u0f54\u0306", "\u01f1\u030c", "\u01f2\u030c", "\u01f3\u030c",
    "\u01f3\u0301", "\u01f1a", "\u01f2a", "\u01f3a", "\u0f51a", "\u0f56a", "\u0f54a",
)  # fmt: skip
LENGTHS = (*range(1, 13), 15, 16, 17, 31, 32, 33, 63, 64, 65, 100)
SHAPES = ("ascending", "descending", "drawn", "swapped", "flat")
DRAWS = 6
LOOKED_UP = ("0", "1", "2", "3", "4", "4.5", "5", "6", "7", "8", "9", "10", '"c"', "TRUE", "$Z$1")
HALVING = (
    "MATCH({v},{a},1)", "MATCH({v},{a},-1)", "VLOOKUP({v},{t},2,TRUE)", "LOOKUP({v},{a},{p})",
    "XMATCH({v},{a},0,2)", "XMATCH({v},{a},-1,2)", "XMATCH({v},{a},1,2)", "XMATCH({v},{a},0,-2)",
    "XMATCH({v},{a},-1,-2)", "XMATCH({v},{a},1,-2)",
)  # fmt: skip
SORTING = (
    3, "b", True, Formula("=NA()"), None, 1, "a", False, Formula("=1/0"), Formula('=""'), -1, "B",
    Formula('=VALUE("x")'), 2.5, None, "A", 1, True, Formula("=NA()"), "a", Formula("=SQRT(-1)"),
    Formula("=INDEX(B1:B2,3)"), Formula("=A1 B1"),
)  # fmt: skip
SORTS = (
    "SORT({a})", "SORT({a},1,-1)", "SORT({a},2,-1)", "SORT({c})", "SORT({c},1,-1)", "SORT({a},1.9)",
    "SORT({a},2,-1.5)", "SORT({a},3)", "SORT({a},0)", "SORT({a},1,0)", "SORT({a},1,2)",
    "SORT({a},1,1.5)", "SORT({a},1,-0.5)", "SORT({a},1,0.5)", "SORT({a},1,-1.9)",
    'SORT({a},1,"1")', "SORT({a},1,TRUE)", "SORT({a},2.9)", 'SORT({a},"2")', "SORT({a},TRUE)",
    "SORT({a},0.5)", "SORT({a},-1)", "SORT({r},1,1,TRUE)", "SORT({r},1,-1,TRUE)",
    "SORT({r},2,1,TRUE)", "SORT({r},3,1,TRUE)", "SORT({r},1,1,2)",
)  # fmt: skip
NEAREST = (
    (None, None, None), ("a", 3, 7), (3, "a", True, None, 7, 1), (True, False, "b", 2, None),
    (Formula("=NA()"), 5, None, "x", 0), (7, 3, 9, 1), (5, 3, 5, 2, 2),
)  # fmt: skip
NEARED = (
    None, 0, 1, 2, 4, 5, 6, 9, 10, -1, "a", "b", "m", "z", Formula('=""'), True, False,
    Formula("=NA()"),
)  # fmt: skip
PROBED = (0, 1, None, 4, "c", True, "ca")
PROBES = (
    "MATCH($Z$1,{a},1)", "MATCH($Z$1,{a},0)", "MATCH($Z$1,{a},-1)", "VLOOKUP($Z$1,{t},2,TRUE)",
    "VLOOKUP($Z$1,{t},2,FALSE)", "HLOOKUP($Z$1,{h},2,TRUE)", "HLOOKUP($Z$1,{h},2,FALSE)",
    "LOOKUP($Z$1,{a},{p})", "XMATCH($Z$1,{a})", "XMATCH($Z$1,{a},0,2)", "XMATCH($Z$1,{a},1,2)",
    "XMATCH($Z$1,{a},-1,2)", "XMATCH($Z$1,{a},0,-2)", "XLOOKUP($Z$1,{a},{p})",
    'XMATCH("c*",{a},2,2)', 'XMATCH("c*",{a},2,-2)', 'XMATCH("c",{a},2,2)',
    'XLOOKUP("c?",{a},{p},,2,2)', 'XMATCH("?a",{a},2,-1)', 'MATCH("C*",{a},1)',
    'VLOOKUP("c*",{t},2,TRUE)', 'MATCH("c",{a},1)', "MATCH(TRUE,{a},1)", "XMATCH(0,$Z$1:$Z$3,1,2)",
    "XMATCH(0,$Z$1:$Z$3,1,1)", 'XMATCH("",{a})', 'MATCH("",{a},0)', 'VLOOKUP("",{t},2,FALSE)',
)  # fmt: skip


def lines() -> list[list]:
    """The lines Halving looks up in, each of numbers from 1 to 9 shaped one of SHAPES, some with
    a third of their places taken by blanks, text, logicals or errors."""
    draw = Random(29)
    found = []
    for length in LENGTHS:
        for shape in SHAPES:
            for _ in range(DRAWS):
                line = [draw.randint(1, 9) for _ in range(length)]
                if shape in ("ascending", "swapped"):
                    line.sort()
                if shape == "descending":
                    line.sort(reverse=True)
                if shape == "swapped":
                    one, other = draw.randrange(length), draw.randrange(length)
                    line[one], line[other] = line[other], line[one]
                if shape == "flat":
                    line = [line[0]] * length
                mixed = draw.random()
                others = (
                    (None,) if mixed < 0.15 else
                    tuple("abcde") if mixed < 0.3 else
                    (True, False, Formula("=NA()")) if mixed < 0.4 else ()
                )  # fmt: skip
                if others:
                    for at in draw.sample(range(length), length // 3 + 1):
                        line[at] = draw.choice(others)
                found.append(line)
    return found


def _forms(letter: str):
    yield letter
    for form in ("NFC", "NFD", "NFKC", "NFKD"):
        yield unicodedata.normalize(form, letter)
    yield from (letter.upper(), letter.lower(), letter.casefold(), letter.title())


def _sampled(code: int) -> bool:
    for first, last in SAMPLED:
        if first <= code <= last:
            step = max(1, (last - first) // SAMPLES)
            return code not in (first, last) and (code - first) % step != 0
    return False


def _weights() -> list[str]:
    """A letter of each primary weight from the Latin script to the Tibetan, which the Tibetan
    letters Croatian weighs the dz digraphs by (collation.UNWRITTEN) are put before."""
    language = collation("hr")
    found = {}
    for code in range(0x20, 0x10000):
        if unicodedata.category(chr(code)) not in ("Cn", "Co", "Cs"):
            kind, alphabetic, _, _ = language._weighed(code)
            if LATIN <= kind <= TIBETAN:
                found.setdefault((kind, alphabetic), chr(code))
    return list(found.values())


def texts() -> list[str]:
    """Each text Order sorts, x before each so that none reads as a number or a comparison."""
    found = dict.fromkeys(EXTRA)
    found.update(dict.fromkeys(lead + each for lead in DZ for each in _weights()))
    for code in range(1, 0x110000):
        letter = chr(code)
        category = unicodedata.category(letter)
        if category == "Cs" or code & 0xFFFE == 0xFFFE:
            continue
        if category == "Cn" and code % (UNASSIGNED if code > 0xFFFF else 7):
            continue
        if category == "Co" and code % PRIVATE:
            continue
        if _sampled(code) and unicodedata.decomposition(letter) == "":
            continue
        found.update(dict.fromkeys(_forms(letter)))
    return ["x" + text for text in found]


def _value(sheet, row: int, col: int, given) -> None:
    if given is None or given == "":
        return
    cell = sheet.cell(row, col)
    if isinstance(given, Formula):
        cell.value = "=" + written(parse(given[1:])) if given != '=""' else given
        return
    cell.value = given
    if isinstance(given, str):
        cell.data_type = "s"


def _text(sheet, row: int, col: int, text: str) -> None:
    if any(ord(each) < 0x20 or ord(each) == 0x7F for each in text):
        parts = [
            f"CHAR({ord(each)})"
            if ord(each) < 0x20 or ord(each) == 0x7F
            else '"' + each.replace('"', '""') + '"'
            for each in text
        ]
        _formula(sheet, row, col, "&".join(parts))
        return
    _value(sheet, row, col, text)


def criteria() -> list:
    found = {}
    for op in OPERATORS:
        for operand in OPERANDS:
            found.setdefault(op + operand, None)
    return [*found, *GIVEN]


def sought() -> list:
    found, seen = [], set()
    for given in (*CELLS, *OPERANDS, *GIVEN):
        key = (type(given), given)
        if key not in seen:
            seen.add(key)
            found.append(given)
    return found


def _letters(col: int) -> str:
    out = ""
    while col:
        col, rest = divmod(col - 1, 26)
        out = chr(65 + rest) + out
    return out


def _formula(sheet, row: int, col: int, formula: str) -> None:
    sheet.cell(row, col, "=" + written(parse(formula)))


def workbook() -> Workbook:
    book = Workbook()
    sheet = book.active
    sheet.title = "Criteria"
    for col, given in enumerate(CELLS, 2):
        _value(sheet, 1, col, given)
    beside = len(CELLS) + 3
    for row, given in enumerate(criteria(), 2):
        _value(sheet, row, 1, given)
        for col in range(2, len(CELLS) + 2):
            _formula(sheet, row, col, f"COUNTIF({_letters(col)}$1,$A{row})")
        for col, formula in enumerate(COLUMN, beside):
            _formula(sheet, row, col, formula.format(r=row))
    column = book.create_sheet("Column")
    for row, given in enumerate(CELLS, 1):
        _value(column, row, 1, given)
        _value(column, row, 2, CELLS[-row])
        column.cell(row, 3, row)
    column.cell(*LOCALE[1:], "=" + TOLD)
    for title, grid in GRIDS.items():
        sheet = book.create_sheet(title)
        for col, given in enumerate(CELLS, 2):
            _value(sheet, 1, col, given)
        for row, given in enumerate(sought(), 2):
            _value(sheet, row, 1, given)
            for col in range(2, len(CELLS) + 2):
                _formula(sheet, row, col, grid.format(r=row, c=_letters(col)))
    sheet = book.create_sheet("Order")
    found = texts()
    last = len(found)
    for row, text in enumerate(found, 1):
        _text(sheet, row, 1, text)
    sheet["B1"] = ArrayFormula(f"B1:B{last}", "=" + written(parse(f"SORT(A1:A{last})")))
    for row in range(1, last):
        for col, formula in enumerate(NEIGHBOURS, 3):
            if row + (col > 7) + (col > 8) < last:
                _formula(sheet, row, col, formula.format(r=row, n=row + 1, s=row + 2, t=row + 3))
    sheet = book.create_sheet("Halving")
    top = row = 1
    for line in lines():
        bottom = top + len(line) - 1
        for at, given in enumerate(line):
            _value(sheet, top + at, 1, given)
            sheet.cell(top + at, 2, at + 1)
        places = {"a": f"$A${top}:$A${bottom}", "p": f"$B${top}:$B${bottom}"}
        places["t"] = f"$A${top}:$B${bottom}"
        for value in LOOKED_UP:
            for col, formula in enumerate(HALVING, 4):
                _formula(sheet, row, col, formula.format(v=value, **places))
            row += 1
        top = bottom + 1
    _sorting(book.create_sheet("Sorting"))
    _probes(book.create_sheet("Probes"))
    _nearest(book.create_sheet("Nearest"))
    return book


def _sorting(sheet) -> None:
    last = len(SORTING)
    for at, given in enumerate(SORTING, 1):
        _value(sheet, at, 1, given)
        sheet.cell(at, 2, at)
        _value(sheet, last + 3, at, given)
        sheet.cell(last + 4, at, at)
    places = {
        "a": f"$A$1:$B${last}",
        "c": f"$A$1:$A${last}",
        "r": f"$A${last + 3}:${_letters(last)}${last + 4}",
    }
    col, row = 4, last + 6
    for formula in SORTS:
        text = "=" + written(parse(formula.format(**places)))
        if "{r}" in formula:
            ref = f"A{row}:{_letters(last)}{row + 1}"
            sheet[f"A{row}"] = ArrayFormula(ref, text)
            row += 3
        else:
            width = 1 if "{c}" in formula else 2
            ref = f"{_letters(col)}1:{_letters(col + width - 1)}{last}"
            sheet[f"{_letters(col)}1"] = ArrayFormula(ref, text)
            col += width + 1


def _probes(sheet) -> None:
    last = len(PROBED)
    for at, given in enumerate(PROBED, 1):
        _value(sheet, at, 1, given)
        sheet.cell(at, 2, at)
        _value(sheet, 1, at + 12, given)
        sheet.cell(2, at + 12, at)
    places = {
        "a": f"$A$1:$A${last}",
        "p": f"$B$1:$B${last}",
        "t": f"$A$1:$B${last}",
        "h": f"$M$1:${_letters(last + 12)}$2",
    }
    for row, formula in enumerate(PROBES, 1):
        _formula(sheet, row, 4, formula.format(**places))


def _nearest(sheet) -> None:
    beside = len(NEAREST) + 2
    for col, line in enumerate(NEAREST, 1):
        for row, given in enumerate(line, 1):
            _value(sheet, row, col, given)
    for row, given in enumerate(NEARED, 1):
        _value(sheet, row, beside, given)
        sought = f"${_letters(beside)}{row}"
        col = beside + 1
        for at, line in enumerate(NEAREST, 1):
            looked = f"${_letters(at)}$1:${_letters(at)}${len(line)}"
            for mode in (-1, 1):
                for search in (1, -1):
                    _formula(sheet, row, col, f"XMATCH({sought},{looked},{mode},{search})")
                    col += 1


if __name__ == "__main__":
    workbook().save(sys.argv[1])
