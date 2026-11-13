import math
from collections import Counter

from .. import selection, sql
from ..criteria import criterion
from ..grid import Area, bounded, numbers, table
from ..values import BLANK, DIV0, NA, NUM, VALUE, Blank, Error, compare, number, total
from . import form, sql_form


def average(found: list[float]):
    return total(found) / len(found) if found else DIV0


def variance(found: list[float], sample: bool):
    if len(found) < (2 if sample else 1):
        return DIV0
    mean = sum(found) / len(found)
    return sum((each - mean) ** 2 for each in found) / (len(found) - sample)


def deviation(found: list[float], sample: bool):
    spread = variance(found, sample)
    return spread if isinstance(spread, Error) else math.sqrt(spread)


def selected(context, target, pairs) -> tuple[list, int] | Error:
    """The cells of the target an area's position meets in every area of the pairs whose cell
    there matches the pair's criterion, and how many of the places beyond all the sheets hold,
    empty in every area, the criteria select; #VALUE! where the areas are not all of one size."""
    if not isinstance(target, Area):
        return VALUE
    tests = []
    for area, given in pairs:
        if not isinstance(area, Area) or (area.height, area.width) != (target.height, target.width):
            return VALUE
        tests.append((area, criterion(given, context.language)))
    height = width = 0
    for area in (target, *(area for area, _ in tests)):
        extent = context.book.extent(area.sheet) or (0, 0)
        height = max(height, min(area.height, extent[0] - area.top + 1))
        width = max(width, min(area.width, extent[1] - area.left + 1))
    value = context.book.value
    found = []
    for row in range(height):
        for col in range(width):
            if all(
                test(value(area.sheet, area.top + row, area.left + col)) for area, test in tests
            ):
                found.append(value(target.sheet, target.top + row, target.left + col))
    beyond = target.height * target.width - height * width
    return found, beyond if beyond and all(test(BLANK) for _, test in tests) else 0


def resized(area: Area, like: Area) -> Area:
    """An area from its first cell, the size of another, as SUMIF reads its sum range."""
    return Area(
        area.sheet, area.top, area.left, area.top + like.height - 1, area.left + like.width - 1
    )


def pairs(given: tuple) -> list:
    return list(zip(given[::2], given[1::2], strict=True))


def selected_numbers(context, target, given) -> list[float] | Error:
    found = selected(context, target, given)
    if isinstance(found, Error):
        return found
    out = []
    for each in found[0]:
        if isinstance(each, Error):
            return each
        if isinstance(each, float):
            out.append(each)
    return out


@form("AVERAGE")
def average_(context, found):
    return average(found)


@form("AVERAGEIF")
def averageif(context, range_, given, average_range=None):
    target = resized(average_range, range_) if isinstance(average_range, Area) else range_
    found = selected_numbers(context, target, [(range_, given)])
    return found if isinstance(found, Error) else average(found)


@form("AVERAGEIFS")
def averageifs(context, average_range, *rest):
    found = selected_numbers(context, average_range, pairs(rest))
    return found if isinstance(found, Error) else average(found)


@form("COUNT")
def count(context, found):
    return sum(
        1
        for value, direct in found
        if isinstance(value, float)
        or (
            direct
            and not isinstance(value, Error)
            and isinstance(number(value, context.language), float)
        )
    )


@form("COUNTA")
def counta(context, found):
    return sum(1 for value, direct in found if direct or not isinstance(value, Blank))


@form("COUNTBLANK")
def countblank(context, range_):
    if not isinstance(range_, Area):
        return VALUE
    cut = bounded(range_, context.book)
    empty = (cut.height * cut.width) - sum(
        1
        for row in range(cut.top, cut.bottom + 1)
        for col in range(cut.left, cut.right + 1)
        if not _empty(context.book.value(cut.sheet, row, col))
    )
    return empty + range_.height * range_.width - cut.height * cut.width


def _empty(value) -> bool:
    return isinstance(value, Blank) or value == ""


@form("COUNTIF")
def countif(context, range_, given):
    found = selected(context, range_, [(range_, given)])
    return found if isinstance(found, Error) else len(found[0]) + found[1]


@form("COUNTIFS")
def countifs(context, *rest):
    given = pairs(rest)
    found = selected(context, given[0][0], given)
    return found if isinstance(found, Error) else len(found[0]) + found[1]


@form("MAX")
def max_(context, found):
    return max(found) if found else 0.0


@form("MIN")
def min_(context, found):
    return min(found) if found else 0.0


@form("MAXIFS")
def maxifs(context, max_range, *rest):
    found = selected_numbers(context, max_range, pairs(rest))
    return found if isinstance(found, Error) else max(found, default=0.0)


@form("MINIFS")
def minifs(context, min_range, *rest):
    found = selected_numbers(context, min_range, pairs(rest))
    return found if isinstance(found, Error) else min(found, default=0.0)


@form("MEDIAN")
def median(context, found):
    if not found:
        return NUM
    ordered = sorted(found)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


@form("MODE", "MODE.SNGL")
def mode(context, found):
    counts = Counter(found)
    most = max(counts.values(), default=0)
    if most < 2:
        return NA
    return next(each for each in found if counts[each] == most)


def _kth(context, array, k, largest: bool):
    found = numbers(context, array)
    if isinstance(found, Error):
        return found
    position = math.ceil(k)
    if not 1 <= position <= len(found):
        return NUM
    return sorted(found, reverse=largest)[position - 1]


@form("LARGE")
def large(context, array, k):
    return _kth(context, array, k, True)


@form("SMALL")
def small(context, array, k):
    return _kth(context, array, k, False)


@form("RANK", "RANK.EQ")
def rank(context, number, ref, order=0.0):
    found = numbers(context, ref)
    if isinstance(found, Error):
        return found
    if not any(compare(each, number, context.language) == 0 for each in found):
        return NA
    if order:
        return 1 + sum(1 for each in found if compare(each, number, context.language) < 0)
    return 1 + sum(1 for each in found if compare(each, number, context.language) > 0)


@form("STDEV", "STDEV.S")
def stdev(context, found):
    return deviation(found, True)


@form("STDEV.P")
def stdevp(context, found):
    return deviation(found, False)


def paired(context, ys, xs) -> tuple[list[float], list[float]] | Error:
    """The pairs of numbers two arrays hold at the same place, read across their rows, a pair
    that holds anything else passed over; an error in either the first one met, #N/A where
    they hold unlike counts of values."""
    found = []
    for given in (ys, xs):
        # Excel refuses a reference to one empty cell, though it passes over the empty cells of
        # a longer one.
        if isinstance(given, Area) and given.height == given.width == 1:
            if isinstance(context.book.value(given.sheet, given.top, given.left), Blank):
                return VALUE
        each = table(context, given)
        if isinstance(each, Error):
            return each
        found.append([value for row in each.rows for value in row])
    ys_, xs_ = found
    if len(ys_) != len(xs_):
        return NA
    kept_y, kept_x = [], []
    for y, x in zip(ys_, xs_, strict=True):
        for value in (y, x):
            if isinstance(value, Error):
                return value
        if isinstance(y, float) and isinstance(x, float):
            kept_y.append(y)
            kept_x.append(x)
    return kept_y, kept_x


def _moments(ys: list[float], xs: list[float]) -> tuple[float, ...] | Error:
    """The means of the pairs and the sums of the products of their deviations from them: x
    by y, x by x and y by y, added as SUM adds; #DIV/0! for no pairs."""
    if not ys:
        return DIV0
    my, mx = total(ys) / len(ys), total(xs) / len(xs)
    dy, dx = [y - my for y in ys], [x - mx for x in xs]
    return (
        my,
        mx,
        total(a * b for a, b in zip(dx, dy, strict=True)),
        total(a * a for a in dx),
        total(b * b for b in dy),
    )


def _spread(context, ys, xs) -> tuple[int, tuple[float, ...]] | Error:
    found = paired(context, ys, xs)
    if isinstance(found, Error):
        return found
    moments = _moments(*found)
    if isinstance(moments, Error):
        return moments
    return len(found[0]), moments


# Excel's CORREL divides the covariance of the population by its deviations and RSQ squares
# that of the sample by the sample's, which round apart in the last bits.
def _correlation(context, ys, xs, apart: int):
    found = _spread(context, ys, xs)
    if isinstance(found, Error):
        return found
    count, (_, _, xy, xx, yy) = found
    if xx == 0 or yy == 0:
        return DIV0
    by = count - apart
    return (xy / by) / (math.sqrt(xx / by) * math.sqrt(yy / by))


@form("CORREL")
def correl(context, array1, array2):
    return _correlation(context, array1, array2, 0)


@form("PEARSON")
def pearson(context, array1, array2):
    return _correlation(context, array1, array2, 0)


@form("RSQ")
def rsq(context, known_ys, known_xs):
    found = _correlation(context, known_ys, known_xs, 1)
    return found if isinstance(found, Error) else found * found


def _slope(context, known_ys, known_xs) -> tuple[float, float, float] | Error:
    found = _spread(context, known_ys, known_xs)
    if isinstance(found, Error):
        return found
    my, mx, xy, xx, _ = found[1]
    return DIV0 if xx == 0 else (xy / xx, my, mx)


@form("SLOPE")
def slope(context, known_ys, known_xs):
    found = _slope(context, known_ys, known_xs)
    return found if isinstance(found, Error) else found[0]


@form("INTERCEPT")
def intercept(context, known_ys, known_xs):
    found = _slope(context, known_ys, known_xs)
    if isinstance(found, Error):
        return found
    slope_, my, mx = found
    return my - slope_ * mx


@form("VAR", "VAR.S")
def var(context, found):
    return variance(found, True)


@form("VAR.P")
def varp(context, found):
    return variance(found, False)


def _aggregate(scope, found, result: str) -> sql.Typed:
    return sql.Typed(
        f"(SELECT CASE WHEN bool_or(e.bad) THEN NULL ELSE {result} END "
        f"FROM {sql.numbers(found, scope)} AS e)",
        sql.NUMBER,
    )


@sql_form("MIN")
def min_sql(scope, found):
    return _aggregate(scope, found, "coalesce(min(e.n), 0::float8)")


@sql_form("MAX")
def max_sql(scope, found):
    return _aggregate(scope, found, "coalesce(max(e.n), 0::float8)")


@sql_form("AVERAGE")
def average_sql(scope, found):
    added = "engine_total(e.n ORDER BY e.k, e.y, e.x)"
    return _aggregate(
        scope,
        found,
        f"CASE WHEN count(e.n) > 0 AND (abs({added}) >= 1e-300 OR {added} = 0) "
        f"THEN {added} / count(e.n) + 0 END",
    )


def _counted(given: sql.Typed, scope) -> sql.Typed:
    """Whether COUNT counts a value given itself: a number, or anything but an error that reads
    as one, which text without a digit never does; NULL where SQL cannot tell."""
    if given.known is not sql.UNKNOWN:
        return sql.constant(isinstance(number(given.known, scope.language), float))
    match given.kind:
        case "number" | "logical":
            return sql.Typed(f"CASE WHEN {given.sql} IS NOT NULL THEN true END", sql.LOGICAL)
        case "text":
            return sql.Typed(f"CASE WHEN {given.sql} !~ '[0-9]' THEN false END", sql.LOGICAL)
        case "blank":
            return sql.constant(True)
    return scope.bound(
        [given],
        lambda v: sql.Typed(
            f"CASE jsonb_typeof({v[0].sql}) WHEN 'number' THEN true WHEN 'boolean' THEN true "
            f"WHEN 'null' THEN true WHEN 'object' THEN false "
            f"WHEN 'string' THEN CASE WHEN ({v[0].sql} #>> '{{}}') !~ '[0-9]' THEN false END END",
            sql.LOGICAL,
        ),
    )


def _count(found, in_area: str, given) -> sql.Typed:
    source = sql.elements(
        found,
        lambda v: in_area.format(v),
        given,
        lambda g: f"{g} AS hit, {g} IS NULL AS bad",
    )
    return sql.Typed(
        f"(SELECT CASE WHEN bool_or(e.bad) THEN NULL "
        f"ELSE count(*) FILTER (WHERE e.hit)::float8 END FROM {source} AS e)",
        sql.NUMBER,
    )


@sql_form("COUNT")
def count_sql(scope, found):
    return _count(
        found,
        "jsonb_typeof({0}) = 'number' AS hit, false AS bad",
        lambda given: _counted(given, scope),
    )


@sql_form("COUNTA")
def counta_sql(scope, found):
    return _count(
        found, "{0} <> 'null'::jsonb AS hit, false AS bad", lambda given: sql.constant(True)
    )


@sql_form("COUNTIF")
def countif_sql(scope, range_, given):
    return selection.selected(scope, range_, [(range_, given)], True)


@sql_form("COUNTIFS")
def countifs_sql(scope, *rest):
    given = pairs(rest)
    return selection.selected(scope, given[0][0], given, True)
