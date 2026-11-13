"""The installation's days off: the weekend and public holidays of its country, and of its region
where they differ by region, from python-holidays, and the days its administrator closes besides."""

from dataclasses import dataclass
from datetime import date, time, timedelta
from functools import cache

import holidays
from django.db import transaction
from django.utils import timezone

from .models import Closure, Event, Workdays, ordered, revised

COUNTRIES = holidays.list_supported_countries(include_aliases=False)
LANGUAGES = holidays.list_localized_countries(include_aliases=False)


@cache
def subdivisions(country: str) -> list[tuple[str, str]]:
    """The country's regions whose holidays differ, each with its name where the library has
    one."""
    aliases = holidays.country_holidays(country).get_subdivision_aliases()
    return [(each, (aliases.get(each) or [each])[0]) for each in COUNTRIES[country]]


def _language(country: str, interface: str) -> str | None:
    """The language of the country's holiday names nearest the interface's, None for the
    country's own."""
    return next((each for each in LANGUAGES.get(country, []) if each[:2] == interface), None)


# Built a year at a time, whole: a holidays object filled lazily from several threads answers
# from a year it has begun and not finished.
@cache
def _named(country: str, subdivision: str, year: int, language: str | None) -> dict[date, str]:
    return dict(
        holidays.country_holidays(
            country, subdiv=subdivision or None, years=year, language=language
        )
    )


@cache
def _weekend(country: str) -> frozenset[int]:
    return frozenset(holidays.country_holidays(country).weekend)


@dataclass(frozen=True)
class Days:
    country: str
    subdivision: str
    # Each day the organisation closed, with the closure's name.
    closed: dict[date, str]
    opens: time
    closes: time

    def working(self, day: date) -> bool:
        return (
            day.weekday() not in _weekend(self.country)
            and day not in _named(self.country, self.subdivision, day.year, None)
            and day not in self.closed
        )

    def off(self, first: date, last: date) -> list[date]:
        return [
            day
            for day in (first + timedelta(days=offset) for offset in range((last - first).days + 1))
            if not self.working(day)
        ]

    def named(self, first: date, last: date) -> list[tuple[date, str, str]]:
        """Each holiday and closed day from `first` to `last` inclusive: its day and its name in
        Croatian and English."""
        found = []
        for year in range(first.year, last.year + 1):
            hr = _named(self.country, self.subdivision, year, _language(self.country, "hr"))
            en = _named(self.country, self.subdivision, year, _language(self.country, "en"))
            found += [(day, name, en.get(day, name)) for day, name in hr.items()]
        found += [(day, name, name) for day, name in self.closed.items()]
        return sorted(each for each in found if first <= each[0] <= last)


def days() -> Days:
    kept = Workdays.objects.filter(pk=1).first() or Workdays()
    closed = {}
    for each in Closure.objects.all():
        for offset in range((each.last - each.first).days + 1):
            closed.setdefault(each.first + timedelta(days=offset), each.name)
    return Days(kept.country, kept.subdivision, closed, kept.opens, kept.closes)


@transaction.atomic
def changed(by, **fields) -> None:
    """The days off changed, by the fields given or by the closures: every series that moves or
    skips its occurrences on them takes a new revision, so that a phone fetches where they fall
    now."""
    Workdays.objects.update_or_create(
        pk=1, defaults={**fields, "changed_by": by, "changed_at": timezone.now()}
    )
    masters = Event.objects.filter(master__isnull=True).exclude(day_off="")
    ordered(*masters.values_list("calendar__owner_id", flat=True))
    masters.update(revision=revised())


def hours(by, opens: time, closes: time) -> None:
    """The working day's hours, which no event follows: only the times offered for a meeting."""
    Workdays.objects.update_or_create(
        pk=1,
        defaults={"opens": opens, "closes": closes, "changed_by": by, "changed_at": timezone.now()},
    )
