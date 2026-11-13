"""How a sheet's fill handle continues a series (D22): numbers by their trend, dates by days or
months, text ending in a number by counting on; each cell read as the engine reads what is typed
in it, in its number format, and the text written as that format shows the value."""

import calendar
import itertools
import re
from datetime import date, timedelta

from apps.engine.carried import entered
from apps.engine.values import significant

from . import calculation

# A number ending a text, as in "Stavka 7", which a series counts on.
COUNTED = re.compile(r"^(.*?)(\d+)(\D*)$", re.DOTALL)
# What a number format quotes, escapes or brackets, which shows as written.
LITERAL = re.compile(r'"[^"]*"|\\.|\[[^\]]*\]')
# Excel's day zero.
EPOCH = date(1899, 12, 30)


def _dated(format: str) -> bool:
    return bool(re.search(r"[dy]", LITERAL.sub("", format), re.IGNORECASE))


def _trend(values: list[float], count: int) -> list[float]:
    """The next values of the least-squares line through those given, as Excel continues a
    series of numbers."""
    n = len(values)
    middle = (n - 1) / 2
    mean = sum(values) / n
    spread = sum((x - middle) ** 2 for x in range(n))
    slope = sum((x - middle) * (y - mean) for x, y in enumerate(values)) / spread
    return [float(f"{mean + slope * (n + k - middle):.15g}") for k in range(count)]


def _months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _dates(values: list[float], count: int) -> list[float]:
    """The next dates of a series: one goes on by a day, dates on the same day of the month
    by the months between them, others by their trend in days."""
    if len(values) == 1:
        return [values[0] + k + 1 for k in range(count)]
    days = [EPOCH + timedelta(days=int(value)) for value in values]
    apart = {
        (later.year - earlier.year) * 12 + later.month - earlier.month
        for earlier, later in itertools.pairwise(days)
    }
    if len(apart) == 1 and (step := apart.pop()) and len({day.day for day in days}) == 1:
        time = values[-1] - int(values[-1])
        return [(_months(days[-1], step * (k + 1)) - EPOCH).days + time for k in range(count)]
    return _trend(values, count)


def series(cells: list[tuple[str, str | None]], count: int, locale: str) -> list[str] | None:
    """The text of the next `count` cells after those given, each its typed text and number
    format, where they make a series, as a sheet's fill handle continues it; None where they
    make none, as one number, and are repeated instead."""
    language = calculation.language(locale)
    read = [calculation.read_in(text, language, format or "") for text, format in cells]
    if all(isinstance(value, float) for value in read):
        shown = [
            entered(format or "", calculation.implied(text, language, format or ""))
            for text, format in cells
        ]
        dated = {_dated(format) for format in shown}
        if dated == {True}:
            found = _dates(read, count)
        elif dated == {False} and len(read) > 1:
            found = _trend(read, count)
        else:
            return None
        texts = []
        for k, value in enumerate(found):
            format = shown[k % len(shown)]
            written = calculation.shown(value, format, locale)
            back = calculation.read_in(written, language, format)
            kept = isinstance(back, float) and significant(back) == significant(value)
            texts.append(written if kept else calculation.written(value, language))
        return texts
    counted = [COUNTED.match(text) for text, _ in cells]
    if not all(isinstance(value, str) for value in read) or not all(counted):
        return None
    if len({(found[1], found[3]) for found in counted}) > 1:
        return None
    numbers = [int(found[2]) for found in counted]
    step = 1 if len(numbers) == 1 else round((numbers[-1] - numbers[0]) / (len(numbers) - 1))
    first, digits, last = counted[-1].groups()
    width = len(digits) if digits.startswith("0") else 0
    return [f"{first}{abs(numbers[-1] + step * (k + 1)):0{width}d}{last}" for k in range(count)]
