"""The user's collections out of their mail (ZB): what each takes, where it keeps it, to whom and
when it goes; and each month, which its owner may send again or for the first time."""

from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone

from apps.ai import installation
from apps.core.api import Refused, api, body
from apps.core.asyncdb import notify
from apps.mail import sending
from apps.mail.models import Account

from . import months, taking
from .models import Collection, Item, Month

LISTED = 50
MONTHS = 13


def _node(node) -> dict | None:
    if node is None or node.trashed_at is not None:
        return None
    return {"id": node.pk, "title": node.title}


def _month(month: Month, collection: Collection) -> dict:
    return {
        "id": month.pk,
        "month": f"{month.month:%Y-%m}",
        "folder": _node(month.folder),
        "table": _node(month.table),
        "past": month.past,
        "asked_at": month.asked_at,
        "delivered_at": month.delivered_at,
        "unsent": month.unsent_id,
        "failed": month.failed,
        "kept": month.kept,
        "waiting": month.waiting,
        "passed": month.passed,
        "missed": month.missed,
        "due_at": months.moment_of(collection, month.month),
    }


def describe(collection: Collection) -> dict:
    counted = {
        name: Count("items", filter=Q(items__state=state))
        for name, state in (
            ("kept", Item.State.KEPT),
            ("waiting", Item.State.WAITING),
            ("passed", Item.State.PASSED),
            ("missed", Item.State.FAILED),
        )
    }
    found = (
        collection.months.annotate(**counted)
        .select_related("folder", "table")
        .order_by("-month")[:MONTHS]
    )
    return {
        "id": collection.pk,
        "name": collection.name,
        "accounts": collection.accounts,
        "senders": collection.senders,
        "words": collection.words,
        "attached": collection.attached,
        "recognise": collection.recognise,
        "since": collection.since.isoformat(),
        "folder": _node(collection.folder),
        "to": collection.to,
        "account": collection.account_id,
        "day": collection.day,
        "hour": collection.hour,
        "sends": collection.sends,
        "text": collection.text,
        "active": collection.active,
        "error": collection.error,
        "months": [_month(each, collection) for each in found],
    }


def _strings(data: dict, name: str, longest: int) -> list[str]:
    given = data.get(name, [])
    if (
        not isinstance(given, list)
        or len(given) > LISTED
        or not all(isinstance(each, str) and 0 < len(each.strip()) <= longest for each in given)
    ):
        raise Refused(400, f"collecting_invalid_{name}")
    return list(dict.fromkeys(each.strip() for each in given))


def _senders(data: dict) -> list[str]:
    found = [each.lower().lstrip("@") for each in _strings(data, "senders", 320)]
    for each in found:
        local, at, domain = each.rpartition("@")
        if "." not in domain or (at and not local) or " " in each:
            raise Refused(400, "collecting_invalid_senders")
    return list(dict.fromkeys(found))


def _people(data: dict) -> list[dict]:
    given = data.get("to", [])
    if not isinstance(given, list) or len(given) > LISTED:
        raise Refused(400, "collecting_invalid_to")
    found = []
    for each in given:
        address = each.get("address") if isinstance(each, dict) else None
        name = each.get("name", "") if isinstance(each, dict) else None
        try:
            validate_email(address)
        except ValidationError:
            raise Refused(400, "collecting_invalid_to") from None
        if not isinstance(name, str) or len(name) > 200:
            raise Refused(400, "collecting_invalid_to")
        found.append({"name": name.strip(), "address": address.strip()})
    return found


def _whole(data: dict, name: str, low: int, high: int) -> int:
    given = data.get(name)
    if type(given) is not int or not low <= given <= high:
        raise Refused(400, f"collecting_invalid_{name}")
    return given


def _flag(data: dict, name: str) -> bool:
    given = data.get(name)
    if type(given) is not bool:
        raise Refused(400, f"collecting_invalid_{name}")
    return given


def _since(data: dict) -> date:
    try:
        given = date.fromisoformat(data.get("since"))
    except TypeError, ValueError:
        raise Refused(400, "collecting_invalid_since") from None
    if given > timezone.localdate():
        raise Refused(400, "collecting_invalid_since")
    return given


def _accounts(user, data: dict) -> tuple[list[int], Account | None]:
    own = set(Account.objects.filter(owner=user).values_list("pk", flat=True))
    given = data.get("accounts", [])
    if not isinstance(given, list) or any(
        type(each) is not int or each not in own for each in given
    ):
        raise Refused(400, "collecting_invalid_accounts")
    sends = data.get("account")
    if sends is not None and (type(sends) is not int or sends not in own):
        raise Refused(400, "collecting_invalid_account")
    return sorted(set(given)), Account.objects.filter(pk=sends).first() if sends else None


def _kept(user, data: dict, found: Collection) -> Collection:
    """The collection as the user set it: what it takes, by the model only once they let the
    messages out to it, and whom it sends them to."""
    name = data.get("name")
    if not isinstance(name, str) or not 0 < len(name.strip()) <= 150:
        raise Refused(400, "invalid_name")
    text = data.get("text", "")
    if not isinstance(text, str) or len(text) > 10_000:
        raise Refused(400, "collecting_invalid_text")
    sends = data.get("sends")
    if sends not in Collection.Sends.values:
        raise Refused(400, "collecting_invalid_sends")
    accounts, account = _accounts(user, data)
    taken = {
        "accounts": accounts,
        "senders": _senders(data),
        "words": _strings(data, "words", 100),
        "attached": _flag(data, "attached"),
        "since": _since(data),
    }
    recognise, to = _flag(data, "recognise"), _people(data)
    if sends == Collection.Sends.SEND and not to:
        raise Refused(400, "collecting_no_recipients")
    if recognise and not found.recognise:
        if not installation.enabled():
            raise Refused(409, "ai_off")
        if data.get("consent") != "once":
            raise Refused(428, "consent_needed")
    if any(getattr(found, field) != value for field, value in taken.items()):
        found.mark = 0
    for field, value in taken.items():
        setattr(found, field, value)
    found.name, found.text, found.sends = name.strip(), text, sends
    found.recognise, found.to, found.account = recognise, to, account
    found.day, found.hour = _whole(data, "day", 1, 28), _whole(data, "hour", 0, 23)
    found.active, found.error = _flag(data, "active"), ""
    with transaction.atomic():
        found.save()
        months.folder_of(found)
    taking.forget(found.pk)
    notify(sending.LATER)
    return found


def _mine(user, pk: int) -> Collection:
    found = Collection.objects.filter(owner=user, pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    return found


@api("GET", "POST")
def collections(request):
    """The user's collections, or one more of them."""
    if request.method == "POST":
        made = _kept(request.user, body(request), Collection(owner=request.user))
        return JsonResponse(describe(made), status=201)
    found = Collection.objects.filter(owner=request.user).select_related("folder")
    found = found.order_by("name", "pk")
    return JsonResponse({"collections": [describe(each) for each in found]})


@api("GET", "PUT", "DELETE")
def collection(request, pk):
    found = _mine(request.user, pk)
    if request.method == "GET":
        return JsonResponse(describe(found))
    if request.method == "DELETE":
        taking.forget(found.pk)
        found.delete()
        return JsonResponse({})
    return JsonResponse(describe(_kept(request.user, body(request), found)))


@api("POST")
def month_sent(request, pk, month):
    """Sends the month now, again or for the first time, with what it holds by then."""
    found = Month.objects.filter(collection=_mine(request.user, pk), pk=month).first()
    if found is None:
        raise Refused(404, "not_found")
    Month.objects.filter(pk=found.pk).update(asked_at=timezone.now(), delivered_at=None, failed="")
    months.touched(pk)
    notify(sending.LATER)
    return JsonResponse({})
