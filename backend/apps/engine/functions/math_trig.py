import math
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP

from .. import selection, sql
from ..grid import Area, Union, bounded, table
from ..values import (
    DIV0,
    NUM,
    VALUE,
    Blank,
    Error,
    power,
    rounded,
    significant,
    total,
)
from . import form, sql_form
from .statistical import average, deviation, pairs, resized, selected_numbers, variance


@form("SUM")
def sum_(context, found):
    return total(found)


@form("SUMIF")
def sumif(context, range_, given, sum_range=None):
    target = resized(sum_range, range_) if isinstance(sum_range, Area) else range_
    found = selected_numbers(context, target, [(range_, given)])
    return found if isinstance(found, Error) else total(found)


@form("SUMIFS")
def sumifs(context, sum_range, *rest):
    found = selected_numbers(context, sum_range, pairs(rest))
    return found if isinstance(found, Error) else total(found)


@form("SUMPRODUCT")
def sumproduct(context, *arrays):
    tables = []
    for each in arrays:
        each = table(context, each)
        if isinstance(each, Error):
            return each
        tables.append(each)
    shape = (tables[0].height, tables[0].width)
    if any((each.height, each.width) != shape for each in tables):
        return VALUE
    result = 0.0
    for row in range(shape[0]):
        for col in range(shape[1]):
            product = 1.0
            for each in tables:
                value = each.rows[row][col]
                if isinstance(value, Error):
                    return value
                product *= value if isinstance(value, float) else 0.0
            result += product
    return result


SUBTOTALS = {
    1: average,
    2: len,
    3: len,
    4: lambda found: max(found, default=0.0),
    5: lambda found: min(found, default=0.0),
    6: lambda found: math.prod(found) if found else 0.0,
    7: lambda found: deviation(found, True),
    8: lambda found: deviation(found, False),
    9: total,
    10: lambda found: variance(found, True),
    11: lambda found: variance(found, False),
}


@form("SUBTOTAL")
def subtotal(context, function_num, *refs):
    way = math.trunc(function_num)
    visible = way > 100
    way -= 100 if visible else 0
    if way not in SUBTOTALS:
        return VALUE
    found = []
    book = context.book
    for ref in refs:
        for area in ref.areas if isinstance(ref, Union) else (ref,):
            cut = bounded(area, book)
            for row in range(cut.top, cut.bottom + 1):
                if visible and book.hidden(cut.sheet, row):
                    continue
                for col in range(cut.left, cut.right + 1):
                    if book.subtotal(cut.sheet, row, col):
                        continue
                    value = book.value(cut.sheet, row, col)
                    if way == 3:
                        if not isinstance(value, Blank):
                            found.append(value)
                    elif isinstance(value, float):
                        found.append(value)
                    elif isinstance(value, Error) and way != 2:
                        return value
    return SUBTOTALS[way](found)


@form("PRODUCT")
def product(context, found):
    return math.prod(found) if found else 0.0


@form("ROUND")
def round_(context, number, digits):
    return rounded(number, math.trunc(digits))


@form("ROUNDUP")
def roundup(context, number, digits):
    return rounded(number, math.trunc(digits), ROUND_UP)


@form("ROUNDDOWN")
def rounddown(context, number, digits):
    return rounded(number, math.trunc(digits), ROUND_DOWN)


@form("MROUND")
def mround(context, number, multiple):
    if multiple == 0:
        return 0.0
    if (number < 0) != (multiple < 0) and number != 0:
        return NUM
    return rounded(number / multiple, 0, ROUND_HALF_UP) * multiple


@form("INT")
def int_(context, number):
    return float(math.floor(number))


@form("TRUNC")
def trunc(context, number, digits=0.0):
    return rounded(number, math.trunc(digits), ROUND_DOWN)


@form("ABS")
def abs_(context, number):
    return abs(number)


@form("SIGN")
def sign(context, number):
    return float((number > 0) - (number < 0))


@form("MOD")
def mod(context, number, divisor):
    if divisor == 0:
        return DIV0
    return number - divisor * math.floor(number / divisor)


@form("QUOTIENT")
def quotient(context, numerator, denominator):
    if denominator == 0:
        return DIV0
    return float(math.trunc(numerator / denominator))


@form("POWER")
def power_(context, number, exponent):
    return power(number, exponent)


@form("SQRT")
def sqrt(context, number):
    return NUM if number < 0 else math.sqrt(number)


@form("EXP")
def exp(context, number):
    try:
        return math.exp(number)
    except OverflowError:
        return NUM


@form("LN")
def ln(context, number):
    return NUM if number <= 0 else math.log(number)


@form("LOG")
def log(context, number, base=10.0):
    if number <= 0 or base <= 0:
        return NUM
    if base == 1:
        return DIV0
    if base == 10:
        return math.log10(number)
    if base == 2:
        return math.log2(number)
    return math.log(number) / math.log(base)


@form("LOG10")
def log10(context, number):
    return NUM if number <= 0 else math.log10(number)


@form("PI")
def pi(context):
    return math.pi


@form("FACT")
def fact(context, number):
    if number < 0:
        return NUM
    whole = math.trunc(number)
    return NUM if whole > 170 else float(math.factorial(whole))


def _away(number: float, step: int, offset: int) -> float:
    """The nearest whole number away from zero that is `offset` more than a multiple of
    `step`."""
    size = math.ceil(abs(number))
    while size % step != offset:
        size += 1
    return float(math.copysign(size, number)) + 0.0


@form("EVEN")
def even(context, number):
    return _away(number, 2, 0)


@form("ODD")
def odd(context, number):
    if number == 0:
        return 1.0
    return _away(number, 2, 1)


def _multiple(number: float, step: float, way) -> float:
    """`number` taken by `way` (math.ceil or math.floor) to a multiple of `step`, the quotient
    and the result on the fifteen digits Excel keeps."""
    count = way(float(significant(number / step)))
    return float(significant(count * step))


@form("CEILING")
def ceiling(context, number, significance):
    if significance == 0:
        return 0.0
    if number > 0 and significance < 0:
        return NUM
    return _multiple(number, significance, math.ceil)


@form("FLOOR")
def floor(context, number, significance):
    if significance == 0:
        return DIV0
    if number > 0 and significance < 0:
        return NUM
    return _multiple(number, significance, math.floor)


@form("CEILING.MATH")
def ceiling_math(context, number, significance=1.0, mode=0.0):
    step = abs(significance)
    if step == 0:
        return 0.0
    if number < 0 and mode:
        return -_multiple(-number, step, math.ceil)
    return _multiple(number, step, math.ceil)


@form("FLOOR.MATH")
def floor_math(context, number, significance=1.0, mode=0.0):
    step = abs(significance)
    if step == 0:
        return 0.0
    if number < 0 and mode:
        return -_multiple(-number, step, math.floor)
    return _multiple(number, step, math.floor)


@form("RAND")
def rand(context):
    return context.random.random()


@form("RANDBETWEEN")
def randbetween(context, bottom, top):
    low, high = math.ceil(bottom), math.floor(top)
    if low > high:
        return NUM
    return float(context.random.randint(low, high))


@sql_form("SUM")
def sum_sql(scope, found):
    return sql.Typed(
        f"(SELECT CASE WHEN bool_or(e.bad) THEN NULL "
        f"ELSE engine_total(e.n ORDER BY e.k, e.y, e.x) END FROM {sql.numbers(found, scope)} AS e)",
        sql.NUMBER,
    )


def _rounded(scope, given: sql.Typed, digits: sql.Typed, way: str) -> sql.Typed:
    """values.rounded on the number's fifteen significant digits, which numeric holds exactly
    and rounds half away from zero."""
    shown, places = f"({given.sql})::numeric", f"trunc({digits.sql})::int"
    cut = f"trunc({shown}, {places})"
    match way:
        case "half":
            done = f"round({shown}, {places})"
        case "down":
            done = cut
        case _:
            done = (
                f"CASE WHEN {cut} = {shown} THEN {shown} "
                f"ELSE {cut} + sign({shown}) * power(10::numeric, -{places}) END"
            )
    return sql.Typed(f"CASE WHEN abs({digits.sql}) < 300 THEN ({done})::float8 + 0 END", sql.NUMBER)


@sql_form("ROUND")
def round_sql(scope, given, digits):
    return _rounded(scope, given, digits, "half")


@sql_form("ROUNDUP")
def roundup_sql(scope, given, digits):
    return _rounded(scope, given, digits, "up")


@sql_form("ROUNDDOWN")
def rounddown_sql(scope, given, digits):
    return _rounded(scope, given, digits, "down")


@sql_form("ABS")
def abs_sql(scope, given):
    return sql.Typed(f"abs({given.sql})", sql.NUMBER)


@sql_form("INT")
def int_sql(scope, given):
    return sql.Typed(f"floor({given.sql})", sql.NUMBER)


@sql_form("SUMIF")
def sumif_sql(scope, range_, given, sum_range=None):
    target = range_ if sum_range is None else sum_range.resized(range_.height, range_.width)
    return selection.selected(scope, target, [(range_, given)], False)


@sql_form("SUMIFS")
def sumifs_sql(scope, sum_range, *rest):
    return selection.selected(scope, sum_range, pairs(rest), False)
