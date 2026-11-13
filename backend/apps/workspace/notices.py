"""What the workspace's owner hears on their devices while away from it (KR3, KR11): a chat of a
round waiting on their decision, a round's coordinator answering or asking for their input, a round
whose chats have all finished, a round consolidated and waiting for its push, a browser or night
check that failed, and a weekly limit of the plan running out or spending credits (KR21). Each is
read from what the workspace lists when it says that changed, against what it showed before, so
that each reaches the owner once. A round whose chats have all
finished consolidates itself unless its owner turned that off (KR12): its coordinator is asked to,
and `objedini` stops at a chat that still asks or failed."""

import threading
import uuid
from datetime import datetime

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.core.api import Refused
from apps.core.asyncdb import released
from apps.push import notices as push
from apps.push.models import Notice

from .models import Command, Seen
from .views import _asked, sent

FINISHED = {"idle", "closed"}
HEARD = {"stop": "said", "notification": "asks"}
# The coordinator's skill reads this as the round consolidating itself (`objedini`, Sam od sebe).
AUTO = "objedini sam od sebe"
CHECKS = ("browser", "night")
# The share of a weekly window of the plan at which its owner hears that it runs out.
LIMITED = 80
WEEKLY = {"week", "model"}
# Two changes heard at once would each compare what they read with the other's.
_one_at_a_time = threading.Lock()


def _tag(key: str) -> str:
    return push.topic("code", uuid.uuid5(uuid.NAMESPACE_URL, key))


def compared(before: dict, projects: list[dict]) -> tuple[dict, list[tuple[dict, str]]]:
    """What the workspace shows now, and the notices, each with its tag, for what changed since it
    showed `before`."""
    shown = {"waiting": {}, "ready": [], "rounds": {}, "failed": {}, "heard": {}}
    told = []
    for project in projects:
        name = project.get("name")
        for round in project.get("rounds", []):
            shown["rounds"][round["id"]] = name
            for member in [round["coordinator"], *round["chats"]]:
                if member["state"] != "waiting" or not member["id"]:
                    continue
                shown["waiting"][member["id"]] = member["at"]
                if before.get("waiting", {}).get(member["id"]) != member["at"]:
                    event = {
                        "event": "waiting",
                        "project": name,
                        "chat": member["title"],
                        "session": member["id"],
                    }
                    told.append((event, _tag(member["id"])))
            coordinator = round["coordinator"]
            heard = coordinator.get("heard")
            if coordinator["id"] and heard and heard.get("event") in HEARD:
                shown["heard"][coordinator["id"]] = heard["at"]
                if before.get("heard", {}).get(coordinator["id"]) != heard["at"]:
                    event = {
                        "event": HEARD[heard["event"]],
                        "project": name,
                        "chat": coordinator["title"],
                        "session": coordinator["id"],
                        "text": heard.get("said") or heard.get("message") or "",
                    }
                    told.append((event, _tag(coordinator["id"])))
            chats = round["chats"]
            if round["started"] and chats and all(chat["state"] in FINISHED for chat in chats):
                shown["ready"].append(round["id"])
                if round["id"] not in before.get("ready", []):
                    event = {"event": "ready", "project": name, "round": round["id"]}
                    told.append((event, _tag(round["id"])))
        for check in CHECKS:
            run = (project.get("gate") or {}).get(check)
            if not run or run["outcome"] != "failed":
                continue
            key, ran = f"{project['path']} {check}", f"{run['tree']} {run['at']}"
            shown["failed"][key] = ran
            if before.get("failed", {}).get(key) != ran:
                event = {"event": check, "project": name, "failed": run.get("failed")}
                told.append((event, _tag(key)))
    for round, name in before.get("rounds", {}).items():
        if round not in shown["rounds"]:
            told.append(({"event": "consolidated", "project": name, "round": round}, _tag(round)))
    return shown, told


def limited(before: dict, usage: dict | None) -> tuple[list[str], list[tuple[dict, str]]]:
    """The weekly windows of the plan past their mark, and those whose use goes on in credits,
    and the notices for those not past it before, each once a window. A measure that failed
    changes nothing, as it says nothing new."""
    if not usage or usage.get("error"):
        return before.get("limits", []), []
    shown, told = [], []
    credits = usage.get("credits") or {}
    for window in usage.get("windows", []):
        if window["kind"] not in WEEKLY:
            continue
        percent = window["percent"]
        marks = ["limit"] if percent >= LIMITED else []
        if percent >= 100 and credits.get("using"):
            marks.append("credits")
        for mark in marks:
            which = f"{mark} {window['kind']} {window['name'] or ''}"
            key = f"{which} {window['resets']}"
            shown.append(key)
            if key not in before.get("limits", []):
                event = {"event": mark, "window": window["kind"], "name": window["name"]}
                told.append(({**event, "percent": round(percent)}, _tag(which)))
    return shown, told


def due(before: dict, projects: list[dict]) -> list[dict]:
    """The rounds to consolidate by themselves: every chat of each has finished, its coordinator
    is free, nothing is asked of it, its owner left it to consolidate itself and it was not yet
    asked to since its chats last finished. A coordinator still busy when the chats finish is
    asked once it is free."""
    asked = set(before.get("consolidating", []))
    return [
        round
        for project in projects
        for round in project.get("rounds", [])
        if round["started"]
        and round["chats"]
        and all(chat["state"] in FINISHED for chat in round["chats"])
        and round["id"] not in asked
        and round["coordinator"]["state"] == "idle"
        and round.get("auto", True)
        and not round.get("asked")
    ]


def _consolidated(round: dict) -> bool:
    """Whether the round was asked to consolidate after its chats last changed, which the state
    seen before may not know."""
    ats = [chat["at"] for chat in round["chats"] if chat.get("at")]
    since = Command.objects.filter(kind=Command.Kind.CONSOLIDATE, round=round["id"])
    if ats:
        since = since.filter(created_at__gte=datetime.fromisoformat(max(ats)))
    return since.exists()


def told() -> None:
    """Tells the owner what changed in the workspace since it was last heard. The first time it is
    heard only sets what it shows, as what was there before was never news."""
    owners = list(
        get_user_model()
        .objects.filter(email__iexact=settings.WORKSPACE, is_active=True)
        .values_list("pk", flat=True)
    )
    if not owners:
        return
    released()
    with _one_at_a_time:
        try:
            listed = async_to_sync(_asked)("GET", "projects")
        except Refused:
            return
        with transaction.atomic():
            seen, first = Seen.objects.select_for_update().get_or_create(pk=1)
            before = seen.shown
            shown, news = compared(before, listed["projects"])
            shown["limits"], over = limited(before, listed.get("usage"))
            news += over
            rounds = [] if first else due(before, listed["projects"])
            shown["consolidating"] = (
                shown["ready"]
                if first
                else [round for round in before.get("consolidating", []) if round in shown["ready"]]
                + [round["id"] for round in rounds]
            )
            seen.shown = shown
            seen.save()
            if first:
                return
            for data, tag in news:
                push.tell(owners, Notice.Kind.CODE, data, tag=tag)
            asked = [
                Command.objects.create(
                    kind=Command.Kind.CONSOLIDATE, round=round["id"], text=AUTO, auto=True
                )
                for round in rounds
                if not _consolidated(round)
            ]
        for command in asked:
            async_to_sync(sent)(command)
