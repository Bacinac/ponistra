from decimal import Decimal

from django.http import JsonResponse

from apps.access.models import Role
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database
from apps.documents.views import live_document
from apps.journal import entries
from apps.journal.entries import Kind
from apps.users.accounts import administrator
from apps.users.views import describe as describe_user

from . import detection, installation, speech, spoken, vocabulary
from .installation import Unavailable
from .models import Consent, Reading, SearchConsent, SpeechConsent


@api("GET", "PATCH")
def setting(request):
    administrator(request)
    if request.method == "GET":
        return JsonResponse(installation.describe(installation.setting()))
    data = body(request)
    if "monthly" in data:
        return JsonResponse(installation.describe(_bound(request, data)))
    enabled, key = _switch(data)
    try:
        found = installation.change(request.user, enabled, key)
    except Unavailable as unavailable:
        raise Refused(422, unavailable.code) from None
    entries.wrote(
        Kind.SETTING_CHANGED, request=request, setting="ai", enabled=enabled, key=bool(key)
    )
    return JsonResponse(installation.describe(found))


def _switch(data: dict) -> tuple[bool, str | None]:
    enabled, key = data.get("enabled"), data.get("key")
    if not isinstance(enabled, bool):
        raise Refused(400, "invalid_enabled")
    if key is not None and (not isinstance(key, str) or not key.strip()):
        raise Refused(400, "invalid_key")
    return enabled, key and key.strip()


def _bound(request, data: dict):
    monthly = _monthly(data)
    found = installation.bound(request.user, monthly)
    entries.wrote(
        Kind.SETTING_CHANGED,
        request=request,
        setting="ai_monthly",
        monthly=None if monthly is None else str(monthly),
    )
    return found


def _monthly(data: dict) -> Decimal | None:
    given = data["monthly"]
    if given is None:
        return None
    if isinstance(given, bool) or not isinstance(given, int | float) or not 0 <= given < 10**8:
        raise Refused(400, "invalid_monthly")
    return Decimal(str(given)).quantize(Decimal("0.01"))


def described(consent: Consent | None) -> dict | None:
    if consent is None:
        return None
    return {
        "given_by": consent.given_by and describe_user(consent.given_by),
        "given_at": consent.given_at,
    }


@api("GET", "POST", "DELETE")
def consent(request, pk):
    document = live_document(request.user, pk, Role.READ if request.method == "GET" else Role.EDIT)
    if request.method == "POST":
        Consent.objects.get_or_create(document=document, defaults={"given_by": request.user})
    elif request.method == "DELETE":
        Consent.objects.filter(document=document).delete()
    found = Consent.objects.select_related("given_by").filter(document=document).first()
    return JsonResponse({"consent": described(found)})


@api("GET", "PUT", "DELETE")
def search_consent(request):
    """Whether the user's sentences in the search box go to the model without asking: yes, no,
    or not answered yet."""
    if request.method == "PUT":
        translate = body(request).get("translate")
        if not isinstance(translate, bool):
            raise Refused(400, "invalid_translate")
        SearchConsent.objects.update_or_create(user=request.user, defaults={"translate": translate})
    elif request.method == "DELETE":
        SearchConsent.objects.filter(user=request.user).delete()
    found = SearchConsent.objects.filter(user=request.user).first()
    return JsonResponse({"translate": found and found.translate})


def _languages(given) -> list[str]:
    if not isinstance(given, list) or not given or len(given) > len(detection.KNOWN):
        raise Refused(400, "invalid_languages")
    if not all(isinstance(each, str) and each in detection.KNOWN for each in given):
        raise Refused(400, "invalid_languages")
    return list(dict.fromkeys(given))


@api("GET", "PUT")
def reading(request):
    """The languages the user reads, none chosen yet meaning the interface's, whether mail in
    another is translated as it opens without asking, and the languages code knows (D35)."""
    if request.method == "PUT":
        data = body(request)
        automatic = data.get("automatic")
        if not isinstance(automatic, bool):
            raise Refused(400, "invalid_automatic")
        languages = None if data.get("languages") is None else _languages(data["languages"])
        Reading.objects.update_or_create(
            user=request.user, defaults={"languages": languages, "automatic": automatic}
        )
    found = Reading.objects.filter(user=request.user).first()
    return JsonResponse(
        {
            "languages": found and found.languages,
            "automatic": bool(found and found.automatic),
            "known": detection.KNOWN,
        }
    )


@api("GET", "PATCH")
def speech_setting(request):
    administrator(request)
    if request.method == "GET":
        return JsonResponse(speech.describe(speech.setting()))
    data = body(request)
    if "monthly" in data:
        return JsonResponse(installation.describe(_bound(request, data)))
    enabled, key = _switch(data)
    try:
        found = speech.change(request.user, enabled, key)
    except Unavailable as unavailable:
        raise Refused(422, unavailable.code) from None
    entries.wrote(
        Kind.SETTING_CHANGED, request=request, setting="speech", enabled=enabled, key=bool(key)
    )
    return JsonResponse(speech.describe(found))


@api("GET", "PUT", "DELETE")
def speech_consent(request):
    """Whether the installation writes speech and has its model read it, and whether the user
    agreed to theirs going to OpenAI and to Anthropic for it."""
    if request.method == "PUT":
        SpeechConsent.objects.get_or_create(user=request.user)
    elif request.method == "DELETE":
        SpeechConsent.objects.filter(user=request.user).delete()
    found = SpeechConsent.objects.filter(user=request.user).first()
    return JsonResponse(
        {
            "enabled": speech.enabled(),
            "understands": installation.enabled(),
            "given_at": found and found.given_at,
        }
    )


@api("POST")
def transcribe(request):
    """The text of what the user said, written by the installation's speech to text."""
    if not SpeechConsent.objects.filter(user=request.user).exists():
        raise Refused(403, "speech_consent")
    media_type = request.content_type or ""
    if media_type not in speech.EXTENSIONS:
        raise Refused(400, "invalid_audio")
    audio = request.body
    if len(audio) > speech.LARGEST:
        raise Refused(413, "audio_too_long")
    try:
        text = speech.transcribe(audio, media_type, vocabulary.prompt(request.user))
    except Unavailable as unavailable:
        raise Refused(422, unavailable.code) from None
    return JsonResponse({"text": text})


# A sentence or two said into the microphone; a dictated page is kept as a note without reading.
SAID = 2_000


@api("POST")
async def understand(request):
    """What the user wants of what they said, read by the installation's model under the
    consent they gave to their speech."""
    if not await SpeechConsent.objects.filter(user=request.user).aexists():
        raise Refused(403, "speech_consent")
    data = body(request)
    text = data.get("text")
    zone = data.get("zone")
    if not isinstance(text, str) or not text.strip() or len(text) > SAID:
        raise Refused(400, "invalid_text")
    if not isinstance(zone, str) or len(zone) > 64:
        raise Refused(400, "invalid_zone")
    if not await database(installation.enabled)():
        raise Refused(409, "ai_off")
    try:
        found = await spoken.understand(request.user, text.strip(), zone)
    except spoken.Ununderstood as ununderstood:
        raise Refused(502, ununderstood.code) from None
    return JsonResponse(found)
