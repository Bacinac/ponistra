"""A machine's alerts (ponistra-os `agent/API.md`, Alerts), which its link sends whenever the list
changes: kept on the computer, and its managers told of a raise, a change of severity and a clear
(decision z4), each of which keeps the alert's id."""

import hashlib
import uuid

from django.db import transaction

from apps.push import notices, webpush
from apps.push.models import Notice

from .models import Computer

SEVERITIES = ("warning", "critical")


def _valid(alert) -> bool:
    return (
        isinstance(alert, dict)
        and isinstance(alert.get("id"), str)
        and alert.get("severity") in SEVERITIES
        and isinstance(alert.get("text"), str)
    )


def raised(alerts: list[dict]) -> dict[str, dict]:
    return {each["id"]: each for each in alerts if not each.get("cleared_at")}


def changes(before: list[dict], now: list[dict]) -> list[tuple[str, dict]]:
    """What the managers are told: each alert raised, of another severity, or cleared since."""
    was, upheld = raised(before), raised(now)
    told = []
    for key, alert in upheld.items():
        if key not in was:
            told.append(("raised", alert))
        elif was[key]["severity"] != alert["severity"]:
            told.append(("severity", alert))
    for key, alert in was.items():
        if key not in upheld:
            cleared = next((each for each in now if each["id"] == key), alert)
            told.append(("cleared", cleared))
    return told


def _tag(computer: uuid.UUID, key: str) -> str:
    return "pc-" + webpush.b64(hashlib.sha256(f"{computer} {key}".encode()).digest()[:16])


def received(pk: uuid.UUID, given: list) -> None:
    alerts = [each for each in given if _valid(each)]
    with transaction.atomic():
        found = Computer.objects.select_for_update().filter(pk=pk).first()
        if found is None:
            return
        told = changes(found.alerts, alerts)
        found.alerts = alerts
        found.save(update_fields=["alerts"])
        managers = list(found.managers.filter(is_active=True).values_list("pk", flat=True))
        for event, alert in told:
            notices.tell(
                managers,
                Notice.Kind.COMPUTER,
                {
                    "computer": str(pk),
                    "name": found.name,
                    "event": event,
                    "severity": alert["severity"],
                    "text": alert["text"],
                },
                tag=_tag(pk, alert["id"]),
                urgency=Notice.Urgency.HIGH
                if event != "cleared" and alert["severity"] == "critical"
                else Notice.Urgency.NORMAL,
            )
