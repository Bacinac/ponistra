from django.db.models import Q
from django.http import JsonResponse

from apps.core.api import Refused, api
from apps.users.accounts import administrator
from apps.users.views import describe as describe_user

from .entries import GROUPS
from .models import Entry

PAGE = 100


def describe(entry: Entry) -> dict:
    return {
        "id": entry.pk,
        "at": entry.at,
        "kind": entry.kind,
        "actor": entry.actor and describe_user(entry.actor),
        "subject": entry.subject and describe_user(entry.subject),
        "address": entry.address,
        "detail": entry.detail,
    }


def number(value: str | None, field: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        raise Refused(400, f"invalid_{field}") from None


@api("GET")
def journal(request):
    """The journal newest first, a page before the entry `before`, narrowed to a group of kinds
    and to what a person did or had done to them."""
    administrator(request)
    asked = request.GET
    found = Entry.objects.select_related("actor", "subject").order_by("-pk")
    group = asked.get("group", "")
    if group:
        if group not in GROUPS:
            raise Refused(400, "invalid_group")
        found = found.filter(kind__in=GROUPS[group])
    person = number(asked.get("user"), "user")
    if person is not None:
        found = found.filter(Q(actor_id=person) | Q(subject_id=person))
    before = number(asked.get("before"), "before")
    if before is not None:
        found = found.filter(pk__lt=before)
    page = list(found[: PAGE + 1])
    return JsonResponse(
        {
            "entries": [describe(entry) for entry in page[:PAGE]],
            "next": page[PAGE - 1].pk if len(page) > PAGE else None,
        }
    )
