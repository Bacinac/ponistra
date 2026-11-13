"""The installation's speech to text (D28): off until the administrator turns it on with the
installation's own OpenAI API key, sealed and never leaving the server but to OpenAI."""

import httpx2
from django.utils import timezone

from apps.core import sealed

from .installation import Unavailable
from .models import Speech

MODEL = "gpt-transcribe"
API = "https://api.openai.com/v1"
# OpenAI's limit on one file of audio.
LARGEST = 25 * 1024 * 1024
WAIT = httpx2.Timeout(120, connect=10)
# OpenAI tells the kind of audio by its file's name.
EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-m4a": "m4a",
}


# Croatian and Bosnian come back in Serbian Cyrillic now and then, told their language or
# not; the scripts map letter for letter. Russian, Ukrainian and the rest use letters Serbian
# lacks, which keeps them as they are.
_CYRILLIC = "абвгдђежзијклљмнњопрстћуфхцчџшАБВГДЂЕЖЗИЈКЛЉМНЊОПРСТЋУФХЦЧЏШ"
_LATIN = (
    "a b v g d đ e ž z i j k l lj m n nj o p r s t ć u f h c č dž š "
    "A B V G D Đ E Ž Z I J K L Lj M N Nj O P R S T Ć U F H C Č Dž Š"
).split()
LATIN = str.maketrans(dict(zip(_CYRILLIC, _LATIN, strict=True)))
SERBIAN = set(_CYRILLIC)


def setting() -> Speech:
    return Speech.objects.filter(pk=1).first() or Speech()


def opened(found: Speech) -> str | None:
    if not found.key:
        return None
    return sealed.opened("speech key", found.key)


def describe(found: Speech) -> dict:
    return {
        "enabled": found.enabled,
        "hint": found.hint,
        "lost": bool(found.key) and opened(found) is None,
        "changed_at": found.changed_at,
    }


def _client(key: str) -> httpx2.Client:
    return httpx2.Client(
        base_url=API, headers={"Authorization": f"Bearer {key}"}, timeout=WAIT, trust_env=False
    )


def check(key: str) -> None:
    """Asks OpenAI whether the key may use the model, by one call that costs nothing."""
    try:
        with _client(key) as client:
            answer = client.get(f"/models/{MODEL}")
    except httpx2.HTTPError:
        raise Unavailable("speech_unreachable") from None
    if answer.status_code in (401, 403, 404):
        raise Unavailable("speech_key_refused")
    if answer.is_error:
        raise Unavailable("speech_unreachable")


def change(user, enabled: bool, key: str | None) -> Speech:
    found = setting()
    if key is not None:
        check(key)
        found.key, found.hint = sealed.seal("speech key", key), key[-4:]
    if enabled and opened(found) is None:
        raise Unavailable("key_needed")
    found.enabled, found.changed_by, found.changed_at = enabled, user, timezone.now()
    found.save()
    return found


def enabled() -> bool:
    found = setting()
    return found.enabled and opened(found) is not None


def transcribe(audio: bytes, media_type: str, words: str = "") -> str:
    """The text of the audio, as OpenAI's model writes it, told beforehand the names the speaker
    uses."""
    found = setting()
    if not found.enabled:
        raise Unavailable("speech_off")
    if (key := opened(found)) is None:
        raise Unavailable("key_lost")
    fields = {"model": MODEL} | ({"prompt": words} if words else {})
    file = (f"speech.{EXTENSIONS[media_type]}", audio, media_type)
    try:
        with _client(key) as client:
            answer = client.post(
                "/audio/transcriptions",
                data=fields,
                files={"file": file},
            )
    except httpx2.HTTPError:
        raise Unavailable("speech_unreachable") from None
    if answer.status_code in (401, 403):
        raise Unavailable("speech_key_refused")
    if answer.is_error:
        raise Unavailable("speech_failed")
    text = answer.json()["text"].strip()
    cyrillic = {letter for letter in text if "\u0400" <= letter <= "\u04ff"}
    return text.translate(LATIN) if cyrillic and cyrillic <= SERBIAN else text
