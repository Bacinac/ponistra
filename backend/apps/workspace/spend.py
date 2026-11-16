"""What the workspace's chats took of Anthropic (PJ3): the tokens of their answers as the workspace
counted them from the transcripts, by month and, in one month, by day, project, model, round and
chat, beside what PONISTRA's own model runs cost in that month and the plan's limits as they were
measured. A plan's tokens cost nothing each, so each sum also says what they would have cost at the
API's prices (`worth`, in dollars, of the models with a price; `unpriced` names the others), which
weighs the tokens as the plan's limits roughly do. `rate` is the weekly window's percent per dollar
of worth spent in it so far, by which a round's or a chat's worth reads as a share of the week."""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth
from django.utils import timezone

from apps.actions.models import ActionRun
from apps.ai.model import CACHE_WRITE, PRICES

from .models import Limits, Spend

TOKENS = ("turns", "input", "output", "cache_read", "cache_write")
CHATS = 50
WEEK = timedelta(days=7)


def _price(model: str, sums: dict) -> Decimal | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return (
        sums["input"] * price.input
        + sums["output"] * price.output
        + sums["cache_read"] * price.cached
        + sums["cache_write"] * price.input * CACHE_WRITE
    ) / 1_000_000


def _grouped(rows, **by: str) -> list[dict]:
    """The rows' tokens summed by the fields `by` names, each with its worth over its models."""
    found: dict[tuple, dict] = {}
    for row in rows.values(*by.values(), "model").annotate(**{name: Sum(name) for name in TOKENS}):
        key = tuple(row[column] for column in by.values())
        held = found.setdefault(
            key,
            {
                **{name: row[column] for name, column in by.items()},
                **dict.fromkeys(TOKENS, 0),
                "worth": Decimal(0),
                "unpriced": [],
            },
        )
        for name in TOKENS:
            held[name] += row[name]
        worth = _price(row["model"], row)
        if worth is None:
            held["unpriced"].append(row["model"])
        else:
            held["worth"] += worth
    return [{**each, "worth": float(each["worth"])} for each in found.values()]


def _month_of(moment: datetime) -> str:
    return timezone.localtime(moment).strftime("%Y-%m")


def _bounds(month: str) -> tuple[datetime, datetime]:
    year, number = map(int, month.split("-"))
    zone = timezone.get_current_timezone()
    began = datetime(year, number, 1, tzinfo=zone)
    ended = datetime(year + number // 12, number % 12 + 1, 1, tzinfo=zone)
    return began, ended


def _limits(began: datetime, ended: datetime) -> list[dict]:
    """The five-hour and the weekly window at each measure in the month."""
    shown = []
    for at, windows in Limits.objects.filter(at__gte=began, at__lt=ended).values_list(
        "at", "windows"
    ):
        named = {each["kind"]: each["percent"] for each in windows if each["kind"] != "model"}
        shown.append(
            {"at": at.isoformat(), "session": named.get("session"), "week": named.get("week")}
        )
    return shown


def _rate() -> float | None:
    latest = Limits.objects.order_by("-at").first()
    windows = latest.windows if latest else []
    week = next((each for each in windows if each["kind"] == "week"), None)
    if week is None:
        return None
    began = datetime.fromisoformat(week["resets"]) - WEEK
    worth = sum(each["worth"] for each in _grouped(Spend.objects.filter(hour__gte=began)))
    return week["percent"] / worth if worth > 0 else None


def summed(month: str | None = None) -> dict:
    """The tokens of each month, and of one month, the latest unless named, in detail."""
    zone = timezone.get_current_timezone()
    months = {
        _month_of(each.pop("at")): each
        for each in _grouped(Spend.objects.annotate(at=TruncMonth("hour", tzinfo=zone)), at="at")
    }
    runs = ActionRun.objects.filter(cost__gt=0)
    costs = {
        _month_of(each["at"]): float(each["cost"])
        for each in runs.annotate(at=TruncMonth("started_at", tzinfo=zone))
        .values("at")
        .annotate(cost=Sum("cost"))
    }
    listed = sorted(months.keys() | costs.keys(), reverse=True)
    shown = month if month in listed else (listed[0] if listed else _month_of(timezone.now()))
    began, ended = _bounds(shown)
    spent = Spend.objects.filter(hour__gte=began, hour__lt=ended)
    days = _grouped(spent.annotate(at=TruncDay("hour", tzinfo=zone)), day="at")
    for each in days:
        each["day"] = timezone.localtime(each["day"]).date().isoformat()
    in_month = runs.filter(started_at__gte=began, started_at__lt=ended)
    day_costs = {
        timezone.localtime(each["day"]).date().isoformat(): float(each["cost"])
        for each in in_month.annotate(day=TruncDay("started_at", tzinfo=zone))
        .values("day")
        .annotate(cost=Sum("cost"))
    }
    for day in days:
        day["api"] = day_costs.pop(day["day"], 0.0)
    days += [
        {"day": day, **dict.fromkeys(TOKENS, 0), "worth": 0.0, "unpriced": [], "api": cost}
        for day, cost in day_costs.items()
    ]
    chats = _grouped(spent, chat="transcript__chat", project="transcript__project")
    titles = dict(
        spent.values_list("transcript__chat")
        .annotate(title=Max("transcript__title", filter=~Q(transcript__title="")))
        .values_list("transcript__chat", "title")
    )
    chats.sort(key=lambda each: each["worth"], reverse=True)
    return {
        "months": [
            {
                "month": each,
                **months.get(each, {**dict.fromkeys(TOKENS, 0), "worth": 0.0, "unpriced": []}),
                "api": costs.get(each, 0.0),
            }
            for each in listed
        ],
        "month": shown,
        "days": sorted(days, key=lambda each: each["day"], reverse=True),
        "projects": sorted(
            _grouped(spent, project="transcript__project"), key=lambda each: -each["worth"]
        ),
        "models": sorted(_grouped(spent, name="model"), key=lambda each: -each["worth"]),
        "rounds": sorted(
            _grouped(spent.exclude(round=""), round="round"), key=lambda each: -each["worth"]
        ),
        "chats": [{**each, "title": titles.get(each["chat"]) or None} for each in chats[:CHATS]],
        "actions": sorted(
            (
                {"action": each["action"], "runs": each["runs"], "cost": float(each["cost"])}
                for each in in_month.values("action").annotate(runs=Count("id"), cost=Sum("cost"))
            ),
            key=lambda each: -each["cost"],
        ),
        "limits": _limits(began, ended),
        "rate": _rate(),
    }
