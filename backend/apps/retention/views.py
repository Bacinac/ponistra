from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse

from apps.core.api import Refused, api, body, optional_id
from apps.documents.models import Node
from apps.journal import entries
from apps.journal.entries import Kind
from apps.users.accounts import administrator
from apps.users.models import User
from apps.users.views import describe as describe_user

from .models import IN_FOLDERS, Hold, Removal, Rule, What

# A hundred years, past any law's term.
MOST_DAYS = 36500
REMOVALS = 20


def _folder(node: Node | None) -> dict | None:
    return node and {"id": node.pk, "title": node.title}


def describe_rule(rule: Rule) -> dict:
    return {
        "id": rule.pk,
        "what": rule.what,
        "folder": _folder(rule.folder),
        "keep_days": rule.keep_days,
        "remove_days": rule.remove_days,
        "created_at": rule.created_at,
    }


def describe_hold(hold: Hold) -> dict:
    return {
        "id": hold.pk,
        "name": hold.name,
        "person": hold.person and describe_user(hold.person),
        "folder": _folder(hold.folder),
        "created_by": hold.created_by and describe_user(hold.created_by),
        "created_at": hold.created_at,
    }


def _days(data: dict, field: str) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if type(value) is not int or not 1 <= value <= MOST_DAYS:
        raise Refused(400, f"invalid_{field}")
    return value


def _terms(data: dict) -> tuple[int | None, int | None]:
    keep, remove = _days(data, "keep_days"), _days(data, "remove_days")
    if keep is None and remove is None:
        raise Refused(400, "rule_says_nothing")
    if keep is not None and remove is not None and remove < keep:
        raise Refused(400, "removed_before_kept")
    return keep, remove


def _live_folder(value) -> Node:
    pk = optional_id(value) if isinstance(value, str) else None
    found = pk and Node.objects.filter(pk=pk, kind=Node.Kind.FOLDER, trashed_at=None).first()
    if not found:
        raise Refused(400, "invalid_folder")
    return found


@api("GET", "POST")
def rules(request):
    administrator(request)
    if request.method == "POST":
        data = body(request)
        what = data.get("what")
        if what not in What.values:
            raise Refused(400, "invalid_what")
        folder = None
        if data.get("folder") is not None:
            if what not in IN_FOLDERS:
                raise Refused(400, "invalid_folder")
            folder = _live_folder(data["folder"])
        keep, remove = _terms(data)
        try:
            with transaction.atomic():
                made = Rule.objects.create(
                    what=what,
                    folder=folder,
                    keep_days=keep,
                    remove_days=remove,
                    created_by=request.user,
                )
        except IntegrityError:
            raise Refused(409, "rule_taken") from None
        _journalled(request, made, "added")
        return JsonResponse(describe_rule(made), status=201)
    found = Rule.objects.select_related("folder").order_by("what", "folder__title", "pk")
    removed = Removal.objects.order_by("-at")[:REMOVALS]
    return JsonResponse(
        {
            "rules": [describe_rule(rule) for rule in found],
            "removals": list(removed.values("at", "documents", "files", "mail", "chat")),
        }
    )


def _journalled(request, rule: Rule, change: str) -> None:
    entries.wrote(
        Kind.SETTING_CHANGED,
        request=request,
        setting="retention",
        change=change,
        name=rule.folder.title if rule.folder else "",
    )


@api("PATCH", "DELETE")
def rule(request, pk):
    administrator(request)
    found = Rule.objects.select_related("folder").filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    if request.method == "DELETE":
        found.delete()
        _journalled(request, found, "removed")
        return HttpResponse(status=204)
    found.keep_days, found.remove_days = _terms(body(request))
    found.save(update_fields=["keep_days", "remove_days"])
    _journalled(request, found, "changed")
    return JsonResponse(describe_rule(found))


@api("GET", "POST")
def holds(request):
    administrator(request)
    if request.method == "POST":
        data = body(request)
        name = data.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise Refused(400, "invalid_name")
        person = folder = None
        if data.get("person") is not None:
            pk = data["person"]
            person = User.objects.filter(pk=pk).first() if type(pk) is int else None
            if person is None:
                raise Refused(400, "invalid_person")
        if data.get("folder") is not None:
            folder = _live_folder(data["folder"])
        if (person is None) == (folder is None):
            raise Refused(400, "hold_one_subject")
        made = Hold.objects.create(
            name=name.strip(), person=person, folder=folder, created_by=request.user
        )
        entries.wrote(
            Kind.SETTING_CHANGED,
            request=request,
            subject=person,
            setting="legal_hold",
            change="added",
            name=made.name,
        )
        return JsonResponse(describe_hold(made), status=201)
    found = Hold.objects.select_related("person", "folder", "created_by").order_by("-pk")
    return JsonResponse({"holds": [describe_hold(hold) for hold in found]})


@api("DELETE")
def hold(request, pk):
    """The hold released."""
    administrator(request)
    found = Hold.objects.select_related("person").filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    found.delete()
    entries.wrote(
        Kind.SETTING_CHANGED,
        request=request,
        subject=found.person,
        setting="legal_hold",
        change="removed",
        name=found.name,
    )
    return HttpResponse(status=204)
