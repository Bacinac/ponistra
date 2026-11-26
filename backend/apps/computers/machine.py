"""What a machine itself asks of Ponistra (ponistra-os `agent/API.md`, Ponistra): it enrolls with a
one-time code and from then on signs every request with the token enrolment gave it."""

import json
import re
import secrets
from functools import wraps

from django.db import IntegrityError, transaction
from django.db.models.functions import Lower
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.core.sealed import seal

from . import link
from .models import Code, Computer, Manager

CODE = re.compile(r"[A-Za-z0-9-]{6,64}")
NAME = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
RECOVERY_KEY = "computer recovery key"
BACKUP_PASSWORD = "computer backup password"
SECRET = 1024


class Refusal(Exception):
    def __init__(self, status: int, error: str):
        super().__init__(error)
        self.status = status
        self.error = error


def _given(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        raise Refusal(400, "invalid_json") from None
    if not isinstance(data, dict):
        raise Refusal(400, "invalid_json")
    return data


def answering(*methods: str, signed: bool = True):
    """A view the agent calls: no browser, so no session or CSRF; signed with the machine's token
    unless it is the enrolment, which the code signs."""

    def decorate(view):
        @csrf_exempt
        @wraps(view)
        def answered(request, *args, **kwargs):
            if request.method not in methods:
                return JsonResponse({"error": "method_not_allowed"}, status=405)
            try:
                if signed:
                    token = link.bearer(request.headers.get("Authorization", ""))
                    found = Computer.objects.filter(
                        token=link.digest(token), left_at__isnull=True
                    ).first()
                    if not token or found is None:
                        return JsonResponse({"error": "unknown_computer"}, status=401)
                    return view(request, found, *args, **kwargs)
                return view(request, *args, **kwargs)
            except Refusal as refused:
                return JsonResponse({"error": refused.error}, status=refused.status)

        return answered

    return decorate


def valid_name(value) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value.lower()):
        raise Refusal(400, "invalid_name")
    return value.lower()


def taken(name: str, besides: Computer | None = None) -> bool:
    others = Computer.objects.annotate(lowered=Lower("name")).filter(
        lowered=name.lower(), left_at__isnull=True
    )
    if besides is not None:
        others = others.exclude(pk=besides.pk)
    return others.exists()


def code_digest(code: str) -> str:
    return link.digest(code.upper())


def _secret(given: dict, field: str) -> str:
    value = given.get(field)
    if not isinstance(value, str) or not value or len(value) > SECRET:
        raise Refusal(400, f"invalid_{field}")
    return value


@answering("POST", signed=False)
def enroll(request):
    given = _given(request)
    code = given.get("code")
    if not isinstance(code, str) or not CODE.fullmatch(code):
        raise Refusal(400, "invalid_code")
    name = valid_name(given.get("name"))
    agent = given.get("agent")
    facts = given.get("facts")
    token = secrets.token_urlsafe(32)
    with transaction.atomic():
        found = Code.objects.select_for_update().filter(digest=code_digest(code)).first()
        if found is None:
            raise Refusal(404, "code_unknown")
        if found.used_at is not None:
            raise Refusal(410, "code_used")
        if found.expires_at <= timezone.now():
            raise Refusal(410, "code_expired")
        if taken(name):
            raise Refusal(409, "name_taken")
        try:
            with transaction.atomic():
                made = Computer.objects.create(
                    name=name,
                    token=link.digest(token),
                    agent=agent[:64] if isinstance(agent, str) else "",
                    facts=facts if isinstance(facts, dict) else {},
                    enrolled_by=found.made_by,
                )
        except IntegrityError:
            raise Refusal(409, "name_taken") from None
        Manager.objects.create(computer=made, user=found.made_by)
        found.used_at = timezone.now()
        found.computer = made
        found.save(update_fields=["used_at", "computer"])
    return JsonResponse({"id": str(made.pk), "token": token}, status=201)


@answering("PUT", "DELETE")
def itself(request, computer: Computer):
    """PUT renames the computer, which the machine then takes as its hostname; DELETE is the
    machine leaving: its record, key and password stay for its managers."""
    if request.method == "DELETE":
        computer.left_at = timezone.now()
        computer.token = ""
        computer.save(update_fields=["left_at", "token"])
        return HttpResponse(status=204)
    name = valid_name(_given(request).get("name"))
    with transaction.atomic():
        if taken(name, computer):
            raise Refusal(409, "name_taken")
        computer.name = name
        try:
            with transaction.atomic():
                computer.save(update_fields=["name"])
        except IntegrityError:
            raise Refusal(409, "name_taken") from None
    return HttpResponse(status=204)


@answering("PUT")
def recovery_key(request, computer: Computer):
    computer.recovery_key = seal(RECOVERY_KEY, _secret(_given(request), "key"))
    computer.recovery_key_at = timezone.now()
    computer.save(update_fields=["recovery_key", "recovery_key_at"])
    return HttpResponse(status=204)


@answering("PUT")
def backup_password(request, computer: Computer):
    computer.backup_password = seal(BACKUP_PASSWORD, _secret(_given(request), "password"))
    computer.backup_password_at = timezone.now()
    computer.save(update_fields=["backup_password", "backup_password_at"])
    return HttpResponse(status=204)
