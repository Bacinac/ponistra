"""A bill's amount in its collection's currency, by the European Central Bank's reference rate
in force on the day it was issued: the last one published before that day, as the Croatian
National Bank applies them."""

import csv
import io
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from logging import getLogger

import httpx2

from .models import Item

log = getLogger(__name__)

SOURCE = "https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A"
WAIT = httpx2.Timeout(30)
# Long enough to reach back over Easter, the longest the bank publishes none.
BACK = timedelta(days=10)
CENT = Decimal("0.01")
UNIT = Decimal("0.000001")


class Unrated(Exception):
    """No reference rate could be had for the currency on the day."""


def client() -> httpx2.Client:
    return httpx2.Client(timeout=WAIT, trust_env=False)


def per_euro(currency: str, day: date) -> Decimal:
    """The units of the currency to one euro in force on the day."""
    if currency == "EUR":
        return Decimal(1)
    try:
        with client() as http:
            answer = http.get(
                SOURCE.format(currency=currency),
                params={
                    "startPeriod": (day - BACK).isoformat(),
                    "endPeriod": (day - timedelta(days=1)).isoformat(),
                    "format": "csvdata",
                },
            )
    except httpx2.HTTPError as error:
        raise Unrated(currency) from error
    if answer.status_code == 404:
        raise Unrated(currency)
    if answer.status_code != 200:
        log.warning("reference rate %s %s: HTTP %s", currency, day, answer.status_code)
        raise Unrated(currency)
    rows = [row for row in csv.DictReader(io.StringIO(answer.text)) if row.get("OBS_VALUE")]
    if not rows:
        raise Unrated(currency)
    try:
        return Decimal(max(rows, key=lambda row: row["TIME_PERIOD"])["OBS_VALUE"])
    except InvalidOperation as error:
        raise Unrated(currency) from error


def rate_of(currency: str, into: str, day: date) -> Decimal:
    """The units of the currency to one of `into` in force on the day."""
    if currency == into:
        return Decimal(1)
    return (per_euro(currency, day) / per_euro(into, day)).quantize(UNIT, ROUND_HALF_UP)


def converted(item: Item) -> bool:
    """Gives the kept bill its amount in its collection's currency where it has none yet;
    whether it has one, or needs none. An owner's own figure is never written over."""
    into = item.collection.currency
    if item.rated == Item.Rated.HAND or item.converted is not None or not into:
        return True
    if item.amount is None or not item.currency or item.date is None:
        return True
    try:
        rate = rate_of(item.currency, into, item.date)
    except Unrated:
        return False
    value = (item.amount / rate).quantize(CENT, ROUND_HALF_UP)
    Item.objects.filter(pk=item.pk, rated=Item.Rated.NONE).update(
        converted=value, rate=rate, rated=Item.Rated.REFERENCE
    )
    item.converted, item.rate, item.rated = value, rate, Item.Rated.REFERENCE
    return True


def by_hand(item: Item, value: Decimal | None) -> None:
    """The owner's own figure for the bill in the collection's currency, as their bank charged
    it; none gives it back to the reference rate."""
    if value is None:
        Item.objects.filter(pk=item.pk).update(converted=None, rate=None, rated=Item.Rated.NONE)
        item.converted, item.rate, item.rated = None, None, Item.Rated.NONE
        converted(item)
        return
    rate = (item.amount / value).quantize(UNIT, ROUND_HALF_UP) if item.amount and value else None
    Item.objects.filter(pk=item.pk).update(converted=value, rate=rate, rated=Item.Rated.HAND)
    item.converted, item.rate, item.rated = value, rate, Item.Rated.HAND
