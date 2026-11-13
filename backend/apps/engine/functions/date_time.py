import calendar
import math
from datetime import date

from .. import formats
from ..dates import LAST_SERIAL, day_of, serial
from ..formats import SECONDS_A_DAY
from ..grid import Area, Union, cells
from ..values import NUM, VALUE, Blank, Error, Matrix, number
from . import form

LONGEST_TIME = 32_767


def _month(year: int, month: int) -> tuple[int, int]:
    """A month counted on from January of a year, as DATE carries months over."""
    year, month = divmod(year * 12 + month - 1, 12)
    return year, month + 1


def _first(year: int, month: int) -> int | None:
    """The serial number of the first day of a month; None outside the years Excel counts."""
    year, month = _month(year, month)
    if not 1899 <= year <= 9999:
        return None
    return serial(date(year, month, 1))


def _days(year: int, month: int) -> int:
    """The days of a month, February 1900 having the 29th Excel counts."""
    return 29 if (year, month) == (1900, 2) else calendar.monthrange(year, month)[1]


def _within(value: int) -> int | Error:
    return value if 0 <= value <= LAST_SERIAL else NUM


def _ymd(value: float) -> tuple[int, int, int] | Error:
    found = day_of(value)
    return NUM if found is None else found


def _sunday(value: int) -> int:
    """The day of the week of a serial number, Sunday 0, as Excel counts it: day 1 a Sunday."""
    return (value - 1) % 7


def _shifted(value: float, months: float, last: bool) -> int | Error:
    if value < 0:
        return NUM
    found = _ymd(value)
    if isinstance(found, Error):
        return found
    year, month, day = found
    year, month = _month(year, month + math.trunc(months))
    if not 1900 <= year <= 9999:
        return NUM
    length = _days(year, month)
    return _within(serial(date(year, month, 1)) + (length if last else min(day, length)) - 1)


@form("DATE")
def date_(context, year, month, day):
    year = math.trunc(year)
    if year < 0 or year >= 10_000:
        return NUM
    if year < 1900:
        year += 1900
    first = _first(year, math.trunc(month))
    if first is None:
        return NUM
    return _within(first + math.trunc(day) - 1)


@form("TIME")
def time(context, hour, minute, second):
    if max(hour, minute, second) > LONGEST_TIME:
        return NUM
    seconds = math.trunc(hour) * 3600 + math.trunc(minute) * 60 + math.trunc(second)
    if seconds < 0:
        return NUM
    days = seconds / SECONDS_A_DAY
    return days - math.floor(days)


def _now(context) -> float:
    now = context.now
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return serial(now.date()) + (now - midnight).total_seconds() / SECONDS_A_DAY


@form("TODAY")
def today(context):
    return float(math.floor(_now(context)))


@form("NOW")
def now(context):
    return _now(context)


def _part(value: float, at: int) -> int | Error:
    if value < 0:
        return NUM
    found = _ymd(value)
    return found if isinstance(found, Error) else found[at]


@form("YEAR")
def year(context, value):
    return _part(value, 0)


@form("MONTH")
def month(context, value):
    return _part(value, 1)


@form("DAY")
def day(context, value):
    return _part(value, 2)


def _seconds(value: float) -> int | Error:
    """The seconds of the day of a serial number, rounded to the nearest one."""
    if value < 0 or value >= LAST_SERIAL + 1:
        return NUM
    return math.floor((value - math.floor(value)) * SECONDS_A_DAY + 0.5) % SECONDS_A_DAY


@form("HOUR")
def hour(context, value):
    seconds = _seconds(value)
    return seconds if isinstance(seconds, Error) else seconds // 3600


@form("MINUTE")
def minute(context, value):
    seconds = _seconds(value)
    return seconds if isinstance(seconds, Error) else seconds // 60 % 60


@form("SECOND")
def second(context, value):
    seconds = _seconds(value)
    return seconds if isinstance(seconds, Error) else seconds % 60


WEEK_STARTS = {1: 0, 2: 1, **{kind: (kind - 10) % 7 for kind in range(11, 18)}}


@form("WEEKDAY")
def weekday(context, value, kind=1.0):
    if value < 0 or value >= LAST_SERIAL + 1:
        return NUM
    kind = math.trunc(kind)
    sunday = _sunday(math.floor(value))
    if kind == 3:
        return (sunday - 1) % 7
    if kind not in WEEK_STARTS:
        return NUM
    return (sunday - WEEK_STARTS[kind]) % 7 + 1


def _iso(value: int) -> int:
    thursday = value - (_sunday(value) - 1) % 7 + 3
    year = day_of(thursday)[0] if thursday >= 1 else 1899
    return (thursday - _first(year, 1)) // 7 + 1


@form("WEEKNUM")
def weeknum(context, value, kind=1.0):
    if value < 0 or value >= LAST_SERIAL + 1:
        return NUM
    kind = math.trunc(kind)
    value = math.floor(value)
    if kind == 21:
        return _iso(value)
    if kind not in WEEK_STARTS:
        return NUM
    january = _first(day_of(value)[0], 1)
    offset = (_sunday(january) - WEEK_STARTS[kind]) % 7
    return (value - january + offset) // 7 + 1


@form("ISOWEEKNUM")
def isoweeknum(context, value):
    if value < 1 or value >= LAST_SERIAL + 1:
        return NUM
    return _iso(math.floor(value))


@form("EDATE")
def edate(context, start, months):
    return _shifted(start, months, False)


@form("EOMONTH")
def eomonth(context, start, months):
    return _shifted(start, months, True)


@form("DATEDIF")
def datedif(context, start, end, unit):
    start, end = math.floor(start), math.floor(end)
    if start < 0 or start > end:
        return NUM
    first, last = _ymd(start), _ymd(end)
    if isinstance(first, Error) or isinstance(last, Error):
        return NUM
    (y1, m1, d1), (y2, m2, d2) = first, last
    months = (y2 - y1) * 12 + m2 - m1 - (d2 < d1)
    match unit.upper():
        case "D":
            return end - start
        case "M":
            return months
        case "Y":
            return months // 12
        case "YM":
            return months % 12
        case "MD":
            if d2 >= d1:
                return d2 - d1
            since = date_(context, y2, m2 - 1, d1)
        case "YD":
            since = _shifted(start, months // 12 * 12, False)
        case _:
            return NUM
    return since if isinstance(since, Error) else end - since


@form("DAYS")
def days(context, end, start):
    for each in (end, start):
        if each < 0 or each >= LAST_SERIAL + 1:
            return NUM
    return math.floor(end) - math.floor(start)


def _holidays(context, given) -> set[int] | Error:
    if given is None:
        return set()
    found = set()
    for each in cells(context, given) if isinstance(given, Area | Union | Matrix) else (given,):
        if isinstance(each, Blank):
            continue
        if isinstance(each, Error):
            return each
        value = VALUE if isinstance(each, bool) else number(each, context.language)
        if isinstance(value, Error):
            return value
        found.add(math.floor(value))
    return found


def _working(value: int, holidays: set[int]) -> bool:
    return _sunday(value) not in (0, 6) and value not in holidays


@form("NETWORKDAYS")
def networkdays(context, start, end, holidays=None):
    start, end = math.floor(start), math.floor(end)
    for each in (start, end):
        if each < 0 or each > LAST_SERIAL:
            return NUM
    holidays = _holidays(context, holidays)
    if isinstance(holidays, Error):
        return holidays
    low, high = sorted((start, end))
    weeks, rest = divmod(high - low + 1, 7)
    count = weeks * 5 + sum(_sunday(low + at) not in (0, 6) for at in range(rest))
    count -= sum(low <= each <= high and _working(each, set()) for each in holidays)
    return count if start <= end else -count


@form("WORKDAY")
def workday(context, start, days, holidays=None):
    start, days = math.floor(start), math.trunc(days)
    if start < 0 or start > LAST_SERIAL:
        return NUM
    holidays = _holidays(context, holidays)
    if isinstance(holidays, Error):
        return holidays
    if abs(days) > LAST_SERIAL:
        return NUM
    step = 1 if days > 0 else -1
    at = start
    for _ in range(abs(days)):
        at += step
        while not _working(at, holidays):
            at += step
        if not 0 <= at <= LAST_SERIAL:
            return NUM
    return at


@form("DATEVALUE")
def datevalue(context, text):
    found = formats.moment(text, context.language)
    return VALUE if found is None else math.floor(found)


@form("TIMEVALUE")
def timevalue(context, text):
    found = formats.moment(text, context.language)
    return VALUE if found is None else found - math.floor(found)


def _last_of_month(year: int, month: int, day: int) -> bool:
    return day == _days(year, month)


def _leap(year: int) -> bool:
    return year == 1900 or calendar.isleap(year)


def _actual(start: int, end: int, first, last) -> float:
    (y1, m1, d1), (y2, m2, d2) = first, last
    if y1 == y2 or (y2 == y1 + 1 and (m1, d1) >= (m2, d2)):
        if y1 == y2:
            length = 366 if _leap(y1) else 365
        else:
            february = any(
                _leap(year) and (y1, m1, d1) <= (year, 2, 29) and (year, 2, 29) <= (y2, m2, d2)
                for year in (y1, y2)
            )
            length = 366 if february else 365
        return (end - start) / length
    years = range(y1, y2 + 1)
    return (end - start) / (sum(366 if _leap(year) else 365 for year in years) / len(years))


@form("YEARFRAC")
def yearfrac(context, start, end, basis=0.0):
    start, end, basis = math.floor(start), math.floor(end), math.trunc(basis)
    if not 0 <= basis <= 4:
        return NUM
    start, end = sorted((start, end))
    first, last = _ymd(start), _ymd(end)
    if start < 0 or isinstance(first, Error) or isinstance(last, Error):
        return NUM
    (y1, m1, d1), (y2, m2, d2) = first, last
    match basis:
        case 0:
            if d1 == 31 and d2 == 31:
                d1 = d2 = 30
            elif d1 == 31:
                d1 = 30
            elif d1 == 30 and d2 == 31:
                d2 = 30
            elif m1 == m2 == 2 and _last_of_month(y1, 2, d1) and _last_of_month(y2, 2, d2):
                d1 = d2 = 30
            elif m1 == 2 and _last_of_month(y1, 2, d1):
                d1 = 30
            return ((y2 - y1) * 360 + (m2 - m1) * 30 + d2 - d1) / 360
        case 1:
            return _actual(start, end, first, last)
        case 2:
            return (end - start) / 360
        case 3:
            return (end - start) / 365
    return ((y2 - y1) * 360 + (m2 - m1) * 30 + min(d2, 30) - min(d1, 30)) / 360
