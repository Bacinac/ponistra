"""Excel's calendar (D22): days counted from 1900 as serial numbers, a day's time as the fraction
after them."""

import math
from datetime import date, timedelta

EPOCH = date(1899, 12, 31)
LAST_SERIAL = 2_958_465
LEAP_DAY = 60
HIJRI_EPOCH = date(622, 7, 18)
HIJRI_CYCLE = 10_631
HIJRI_LEAP_YEARS = frozenset({2, 5, 7, 10, 13, 15, 18, 21, 24, 26, 29})


def serial(day: date) -> int:
    """The serial number of a day, as Excel counts them from 1900, which takes 1900 for a leap
    year as Lotus 1-2-3 did: every day from 1 March 1900 is one later than the calendar's."""
    days = (day - EPOCH).days
    return days + 1 if days >= LEAP_DAY else days


def dated(year: int, month: int, day: int) -> int | None:
    """The serial number of a day by its year, month and day, 29 February 1900 among them; None
    for a day the calendar lacks or outside 1900 to 9999."""
    if (year, month, day) == (1900, 2, 29):
        return LEAP_DAY
    try:
        found = serial(date(year, month, day))
    except ValueError:
        return None
    return found if 1 <= found <= LAST_SERIAL else None


def day_of(value: float) -> tuple[int, int, int] | None:
    """The year, month and day of a serial number: 0 is 0 January 1900 and 60 the 29 February
    1900 Excel counts; None outside 0 to 31 December 9999."""
    days = math.floor(value)
    if not 0 <= days <= LAST_SERIAL:
        return None
    if days == 0:
        return 1900, 1, 0
    if days == LEAP_DAY:
        return 1900, 2, 29
    day = calendar_day(days)
    return day.year, day.month, day.day


def calendar_day(days: int) -> date:
    """The calendar's day a serial number stands for, the 29 February 1900 Excel counts taken for
    the day after the 28th."""
    return EPOCH + timedelta(days=days - 1 if days > LEAP_DAY else days)


def hijri(days: int) -> tuple[int, int, int] | None:
    """The year, month and day of a serial number in the tabular Hijri calendar Excel's B2 writes,
    the Kuwaiti one: years of twelve months of 30 and 29 days in turn from 15 July 622 of the
    Julian calendar, the last month of 30 in the eleven leap years of every thirty; 0 is
    29/08/1317 as 1 is, and None for the 29 February 1900 the Hijri calendar has no day for."""
    if days == LEAP_DAY:
        return None
    cycles, rest = divmod((calendar_day(days or 1) - HIJRI_EPOCH).days, HIJRI_CYCLE)
    year = 1
    while rest >= (length := 355 if year in HIJRI_LEAP_YEARS else 354):
        rest -= length
        year += 1
    month = 1
    while rest >= (length := 30 if month % 2 or (month == 12 and year in HIJRI_LEAP_YEARS) else 29):
        rest -= length
        month += 1
    return cycles * 30 + year, month, rest + 1
