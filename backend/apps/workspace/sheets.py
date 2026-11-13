"""The time worked written where others read it (VT2): Clockify's time entries and a TaskStreamer's
time sheets. Each of our projects is written to the project of the sheet it is mapped to, our
projects on one project of theirs joined into the same blocks, from the sheet's first day on. A
day is written once none of its blocks can still grow, and again whenever what was measured of it
changes. The entries named by the sheet's label are taken as its own and replaced; whatever anyone
entered by hand is never touched. Clockify gets one entry for each project and day, as long as its
blocks together, TaskStreamer one for each block."""

import logging
from asyncio import sleep
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

import httpx2
from django.db import transaction
from django.utils import timezone

from apps.core.asyncdb import database
from apps.core.sealed import opened

from . import worked
from .models import Sheet, Written

log = logging.getLogger(__name__)

SEALED = "workspace sheet"
CLOCKIFY = "https://api.clockify.me/api/v1"
WORKLOG = "/api/v1/timesheets/worklog/"
WAIT = httpx2.Timeout(30)
# Clockify answers a key of its free plan 30 times an hour; the rest is left for asking by hand.
BUDGET = 28
HOUR = timedelta(hours=1)
# The workspace says what it read once a minute, so a block may grow until then after the pause.
SETTLED = worked.IDLE + timedelta(minutes=2)
SHORTEST = 60
ENTRIES = 1000
DAYS_SENT = 31
EVERY = timedelta(minutes=15)

Span = worked.Span


class Unwritten(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Planned:
    """One day's blocks on one project of the sheet, and the projects of ours they came from."""

    spans: list[Span] = field(default_factory=list)
    ours: set[str] = field(default_factory=set)


def client() -> httpx2.Client:
    return httpx2.Client(timeout=WAIT, trust_env=False)


def midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=timezone.get_current_timezone())


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _moment(text) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if isinstance(text, str) else None
    except ValueError:
        return None


def _answered(answer: httpx2.Response):
    status = answer.status_code
    if status == 429:
        raise Unwritten("sheet_busy")
    if status in (401, 403):
        raise Unwritten("sheet_refused")
    if status == 404:
        raise Unwritten("sheet_missing")
    if status >= 400:
        raise Unwritten("sheet_failed")
    try:
        return answer.json() if answer.content else None
    except ValueError:
        raise Unwritten("sheet_answer") from None


def _key(sheet: Sheet, key: str | None) -> str:
    found = key if key is not None else opened(SEALED, sheet.key)
    if not found:
        raise Unwritten("sheet_key")
    return found


def clockify(sheet: Sheet, method: str, path: str, body=None, key: str | None = None):
    """Clockify's answer, each request counted against the hour's budget of the sheet's key."""
    now = timezone.now()
    recent = [each for each in sheet.asked if (_moment(each) or now) > now - HOUR]
    if len(recent) >= BUDGET:
        raise Unwritten("sheet_busy")
    sheet.asked = [*recent, now.isoformat()]
    if sheet.pk:
        Sheet.objects.filter(pk=sheet.pk).update(asked=sheet.asked)
    try:
        with client() as http:
            answer = http.request(
                method, CLOCKIFY + path, headers={"X-Api-Key": _key(sheet, key)}, json=body
            )
    except httpx2.HTTPError:
        raise Unwritten("sheet_unreachable") from None
    return _answered(answer)


def taskstreamer(sheet: Sheet, method: str, body=None, params=None, key: str | None = None):
    try:
        with client() as http:
            answer = http.request(
                method,
                sheet.address.rstrip("/") + WORKLOG,
                headers={"Authorization": f"ApiKey {_key(sheet, key)}"},
                json=body,
                params=params,
            )
    except httpx2.HTTPError:
        raise Unwritten("sheet_unreachable") from None
    return _answered(answer)


def found(sheet: Sheet, key: str | None = None) -> None:
    """Where the sheet's key writes in Clockify and the projects it offers there."""
    me = clockify(sheet, "GET", "/user", key=key)
    if not isinstance(me, dict) or not me.get("id") or not me.get("activeWorkspace"):
        raise Unwritten("sheet_answer")
    sheet.space, sheet.account = me["activeWorkspace"], me["id"]
    listed = clockify(
        sheet, "GET", f"/workspaces/{sheet.space}/projects?page-size=5000&archived=false", key=key
    )
    if not isinstance(listed, list):
        raise Unwritten("sheet_answer")
    sheet.offered = sorted(
        (
            {"id": each["id"], "name": each.get("name") or each["id"]}
            for each in listed
            if isinstance(each, dict) and isinstance(each.get("id"), str)
        ),
        key=lambda each: each["name"].lower(),
    )


def wanted(sheet: Sheet) -> dict[date, dict[str, Planned]]:
    """Each day's blocks on each project of the sheet, from its first day on."""
    planned: dict[date, dict[str, Planned]] = defaultdict(lambda: defaultdict(Planned))
    for project, spans in worked.blocks().items():
        theirs = sheet.projects.get(project)
        if not theirs or project in sheet.excluded:
            continue
        for span in spans:
            day = worked.day_of(span[0])
            if day >= sheet.since:
                each = planned[day][theirs]
                each.spans.append(span)
                each.ours.add(project)
    for projects in planned.values():
        for each in projects.values():
            each.spans = worked.joined(each.spans, timedelta(0))
    return planned


def shown(spans: list[Span]) -> list[list[str]]:
    return [[stamp(began), stamp(ended)] for began, ended in spans]


def settled(day: date, projects: dict[str, Planned], now: datetime) -> bool:
    if now < midnight(day + timedelta(days=1)):
        return False
    return all(ended <= now - SETTLED for each in projects.values() for _, ended in each.spans)


def due(
    sheet: Sheet, now: datetime | None = None
) -> tuple[dict[date, dict[str, Planned]], list[date]]:
    """What the sheet should hold, and the days on which it no longer holds it."""
    now = now or timezone.now()
    planned = wanted(sheet)
    held: dict[date, dict[str, list]] = defaultdict(dict)
    for day, project, spans in sheet.written.values_list("day", "project", "spans"):
        held[day][project] = spans
    days = [
        day
        for day in sorted(planned.keys() | held.keys())
        if day >= sheet.since
        and settled(day, planned.get(day, {}), now)
        and {project: shown(each.spans) for project, each in planned.get(day, {}).items()}
        != held.get(day, {})
    ]
    return planned, days


def described(sheet: Sheet, each: Planned) -> str:
    return f"{sheet.label} — {'/'.join(sorted(ours for ours in each.ours if ours))}".rstrip(" —")


def _own(sheet: Sheet, entry: dict) -> bool:
    return (entry.get("description") or "").startswith(sheet.label)


def _entries_of(sheet: Sheet, began: datetime, ended: datetime) -> list[dict]:
    entries: list[dict] = []
    for page in range(1, 100):
        listed = clockify(
            sheet,
            "GET",
            f"/workspaces/{sheet.space}/user/{sheet.account}/time-entries"
            f"?start={stamp(began)}&end={stamp(ended)}&page-size={ENTRIES}&page={page}",
        )
        if not isinstance(listed, list):
            raise Unwritten("sheet_answer")
        entries.extend(each for each in listed if isinstance(each, dict))
        if len(listed) < ENTRIES:
            break
    return entries


def _interval(entry: dict) -> tuple[datetime, datetime] | None:
    interval = entry.get("timeInterval") or {}
    began, ended = _moment(interval.get("start")), _moment(interval.get("end"))
    return (began, ended) if began and ended else None


def _clockified(sheet: Sheet, project: str, each: Planned) -> dict | None:
    began = each.spans[0][0].replace(microsecond=0)
    lasted = worked.seconds(each.spans)
    if lasted < SHORTEST:
        return None
    return {
        "start": stamp(began),
        "end": stamp(began + timedelta(seconds=lasted)),
        "description": described(sheet, each),
        "projectId": project,
    }


def _same(entry: dict, body: dict) -> bool:
    interval = _interval(entry)
    return (
        interval is not None
        and entry.get("projectId") == body["projectId"]
        and (entry.get("description") or "") == body["description"]
        and interval == (_moment(body["start"]), _moment(body["end"]))
    )


def _held(sheet: Sheet, day: date, projects: dict[str, Planned], entries: dict[str, list]) -> None:
    Written.objects.filter(sheet=sheet, day=day).delete()
    Written.objects.bulk_create(
        Written(
            sheet=sheet,
            day=day,
            project=project,
            spans=shown(each.spans),
            entries=entries.get(project, []),
        )
        for project, each in projects.items()
    )


def _clockify_day(sheet: Sheet, day: date, projects: dict[str, Planned]) -> None:
    held = set(Written.objects.filter(sheet=sheet, day=day).values_list("project", flat=True))
    managed = set(sheet.projects.values()) | held
    there = [
        entry
        for entry in _entries_of(sheet, midnight(day), midnight(day + timedelta(days=1)))
        if _own(sheet, entry) and entry.get("projectId") in managed
    ]
    entries: dict[str, list] = {}
    making = []
    for project, each in projects.items():
        body = _clockified(sheet, project, each)
        if body is None:
            continue
        match = next((entry for entry in there if _same(entry, body)), None)
        if match:
            there.remove(match)
            entries[project] = [match["id"]]
        else:
            making.append((project, body))
    for entry in there:
        clockify(sheet, "DELETE", f"/workspaces/{sheet.space}/time-entries/{entry['id']}")
    for project, body in making:
        made = clockify(sheet, "POST", f"/workspaces/{sheet.space}/time-entries", body)
        if not isinstance(made, dict) or not made.get("id"):
            raise Unwritten("sheet_answer")
        entries[project] = [made["id"]]
    _held(sheet, day, projects, entries)


def _sessions(sheet: Sheet, planned: dict[date, dict[str, Planned]], days: list[date]) -> list:
    local = timezone.get_current_timezone()
    return [
        {
            "project": project,
            "start": began.replace(microsecond=0).astimezone(local).isoformat(),
            "end": ended.replace(microsecond=0).astimezone(local).isoformat(),
            "description": described(sheet, each),
        }
        for day in days
        for project, each in planned.get(day, {}).items()
        for began, ended in each.spans
        if (ended - began).total_seconds() >= SHORTEST
    ]


def _taskstreamer_days(sheet: Sheet, planned: dict[date, dict[str, Planned]], days: list[date]):
    answer = taskstreamer(
        sheet,
        "POST",
        {
            "user": sheet.person,
            "days": [day.isoformat() for day in days],
            "sessions": _sessions(sheet, planned, days),
        },
    )
    if not isinstance(answer, dict):
        raise Unwritten("sheet_answer")
    for day in days:
        _held(sheet, day, planned.get(day, {}), {})


def write(sheet: Sheet) -> dict:
    """Writes each day the sheet no longer holds as measured, as far as its budget reaches."""
    with transaction.atomic():
        sheet = Sheet.objects.select_for_update().get(pk=sheet.pk)
        planned, days = due(sheet)
        done = 0
        error = ""
        try:
            if sheet.kind == Sheet.Kind.CLOCKIFY:
                for day in days:
                    _clockify_day(sheet, day, planned.get(day, {}))
                    done += 1
            else:
                for at in range(0, len(days), DAYS_SENT):
                    batch = days[at : at + DAYS_SENT]
                    _taskstreamer_days(sheet, planned, batch)
                    done += len(batch)
        except Unwritten as unwritten:
            error = unwritten.code
        sheet.error = error
        if done:
            sheet.written_at = timezone.now()
        sheet.save(update_fields=["error", "written_at"])
    if error and error != "sheet_busy":
        log.warning("workspace: the time worked was not written to %s: %s", sheet.kind, error)
    return {"written": done, "left": len(days) - done, "error": error or None}


def _seconds_of(began: datetime | None, ended: datetime | None) -> int:
    return round((ended - began).total_seconds()) if began and ended and ended > began else 0


def _there(sheet: Sheet, first: date, last: date) -> list[tuple[date, str, bool, int]]:
    """What the sheet holds from one day to another: the day, project, whether the entry is the
    sheet's own and how long it lasts."""
    if sheet.kind == Sheet.Kind.CLOCKIFY:
        return [
            (
                worked.day_of(interval[0]),
                entry.get("projectId") or "",
                _own(sheet, entry),
                _seconds_of(*interval),
            )
            for entry in _entries_of(sheet, midnight(first), midnight(last))
            if (interval := _interval(entry))
        ]
    answer = taskstreamer(
        sheet,
        "GET",
        params={
            "user": sheet.person,
            "from": first.isoformat(),
            "to": (last - timedelta(days=1)).isoformat(),
        },
    )
    listed = answer.get("entries") if isinstance(answer, dict) else None
    if not isinstance(listed, list):
        raise Unwritten("sheet_answer")
    there = []
    for entry in listed:
        if not isinstance(entry, dict):
            continue
        began, ended = _moment(entry.get("started_at")), _moment(entry.get("ended_at"))
        day = _moment(entry.get("date"))
        if began and day:
            there.append(
                (
                    day.date(),
                    entry.get("project") or "",
                    bool(entry.get("tool")),
                    _seconds_of(began, ended),
                )
            )
    return there


def compared(sheet: Sheet, month: str) -> dict:
    """The month as measured beside what the sheet holds: each day's time on each project of the
    sheet, measured, entered as the sheet's own and entered by others, and whether the day is
    before the sheet's first, still open, or holds its own entries as measured or otherwise."""
    year, number = map(int, month.split("-"))
    first = date(year, number, 1)
    last = date(year + number // 12, number % 12 + 1, 1)
    now = timezone.now()
    planned = wanted(sheet)
    managed = set(sheet.projects.values())
    rows: dict[date, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"measured": 0, "own": 0, "others": 0})
    )
    for day, projects in planned.items():
        if first <= day < last:
            for project, each in projects.items():
                rows[day][project]["measured"] = worked.seconds(each.spans)
    for day, project, own, lasted in _there(sheet, first, last):
        if first <= day < last and project in managed:
            rows[day][project]["own" if own else "others"] += lasted
    listed = []
    for day in sorted(rows, reverse=True):
        if day < sheet.since:
            state = "before"
        elif not settled(day, planned.get(day, {}), now):
            state = "open"
        elif all(abs(each["measured"] - each["own"]) < SHORTEST for each in rows[day].values()):
            state = "same"
        else:
            state = "differs"
        listed.append(
            {
                "day": day.isoformat(),
                "state": state,
                "projects": [
                    {"project": project, **counted}
                    for project, counted in sorted(rows[day].items())
                ],
            }
        )
    return {"month": month, "days": listed}


def _nightly() -> None:
    for sheet in Sheet.objects.filter(nightly=True):
        write(sheet)


async def writing() -> None:
    """Writes the sheets that write by themselves whenever a day has settled or changed since."""
    while True:
        try:
            await database(_nightly, own_thread=True)()
        except Exception:
            log.exception("workspace: the sheets were not written")
        await sleep(EVERY.total_seconds())
