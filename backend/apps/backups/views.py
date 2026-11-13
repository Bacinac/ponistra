import re

from django.http import JsonResponse

from apps.core.api import Refused, api, body
from apps.journal import entries
from apps.journal.entries import Kind
from apps.users.accounts import administrator

from . import offsite
from .offsite import Unavailable

BUCKET = re.compile(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")


def text(data: dict, name: str, limit: int) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise Refused(400, f"invalid_{name}")
    return value.strip()


@api("PATCH", confirmed=("PATCH",))
def offsite_setting(request):
    administrator(request)
    data = body(request)
    endpoint = text(data, "endpoint", 200).rstrip("/")
    if not endpoint.startswith("https://"):
        raise Refused(400, "invalid_endpoint")
    name = text(data, "bucket", 63)
    if not BUCKET.fullmatch(name):
        raise Refused(400, "invalid_bucket")
    access_key = text(data, "access_key", 128)
    secret = text(data, "secret", 256) if data.get("secret") is not None else None
    try:
        found, key = offsite.configured(request.user, endpoint, name, access_key, secret)
    except Unavailable as unavailable:
        raise Refused(422, unavailable.code) from None
    entries.wrote(Kind.SETTING_CHANGED, request=request, setting="offsite", change="changed")
    return JsonResponse({"kit": offsite.kit(found, key)})


@api("POST", confirmed=("POST",))
def offsite_kit(request):
    administrator(request)
    if (found := offsite.offsite()) is None:
        raise Refused(404, "offsite_none")
    try:
        key = offsite.reissued()
    except Unavailable as unavailable:
        raise Refused(422, unavailable.code) from None
    entries.wrote(Kind.SETTING_CHANGED, request=request, setting="offsite_kit", change="changed")
    return JsonResponse({"kit": offsite.kit(found, key)})
