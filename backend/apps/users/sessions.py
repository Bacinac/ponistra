"""Sessions in our own table, which knows whose each one is and the browser that signed in with
it, and those the server opens itself, for a browser that works as one of its users."""

import copy
import hashlib
import ipaddress
from datetime import datetime, timedelta
from importlib import import_module

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore as DatabaseStore
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.decorators import sync_and_async_middleware

SIGNED_IN = "signed_in"
SEEN = "seen_at"
OFFLINE = "offline"
# Signed in with a password while the policy holds the user to passkeys: until they add one,
# the API answers nothing else.
PASSKEY_DUE = "passkey_due"
# When the person at the browser last showed who they are, by signing in or confirming since:
# what an open session must not do alone waits for a recent one (D33).
CONFIRMED = "confirmed_at"
CONFIRMED_FOR = timedelta(minutes=10)
SEEN_EVERY = timedelta(minutes=5)
# How long a sign-in lasts however busy its browser keeps it: past this the browser signs in
# again, so a session someone took does not outlive it by being used.
LASTS = timedelta(days=30)


class SessionStore(DatabaseStore):
    """Saves only what its request changed, over what the row holds by then: the same browser's
    requests run side by side, and one that loaded the session before another wrote it (marking
    it seen, as a slow request does on its way out) took back that write when it saved the whole
    of it, a confirmation (D33) or a passkey's challenge among them."""

    def __init__(self, session_key=None):
        super().__init__(session_key)
        self._loaded = {}

    @classmethod
    def get_model_class(cls):
        from .models import Session

        return Session

    def load(self):
        data = super().load()
        self._loaded = copy.deepcopy(data)
        return data

    async def aload(self):
        data = await super().aload()
        self._loaded = copy.deepcopy(data)
        return data

    def _merged(self, kept: dict) -> dict:
        ours = self._session
        dropped = self._loaded.keys() - ours.keys()
        merged = {key: value for key, value in kept.items() if key not in dropped}
        merged.update(
            (key, value)
            for key, value in ours.items()
            if key not in self._loaded or self._loaded[key] != value
        )
        return merged

    def save(self, must_create=False):
        if must_create or self.session_key is None:
            return super().save(must_create)
        with transaction.atomic():
            kept = (
                self.model.objects.select_for_update()
                .filter(session_key=self.session_key)
                .values_list("session_data", flat=True)
                .first()
            )
            if kept is not None:
                self._session_cache = self._merged(self.decode(kept))
            super().save()
        self._loaded = copy.deepcopy(self._session_cache)

    async def asave(self, must_create=False):
        await sync_to_async(self.save)(must_create)

    def create_model_instance(self, data):
        session = super().create_model_instance(data)
        browser = data.get(SIGNED_IN) or {}
        session.user_id = data.get(SESSION_KEY)
        session.agent = browser.get("agent", "")
        session.address = browser.get("address")
        session.signed_in_at = browser.get("at")
        session.seen_at = data.get(SEEN)
        session.offline = bool(data.get(OFFLINE))
        return session

    def get_session_cookie_age(self):
        # Read from the cache alone: the async path has loaded it before it asks, where loading
        # it here would reach the database from the event loop.
        age = super().get_session_cookie_age()
        browser = getattr(self, "_session_cache", {}).get(SIGNED_IN)
        if not browser:
            return age
        left = datetime.fromisoformat(browser["at"]) + LASTS - timezone.now()
        return max(0, min(age, int(left.total_seconds())))


def _store(key: str | None = None):
    return import_module(settings.SESSION_ENGINE).SessionStore(key)


def opened(user, lifetime: int) -> str:
    """The key of a new session signing the user in for that many seconds."""
    session = _store()
    session[SESSION_KEY] = str(user.pk)
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session.set_expiry(lifetime)
    session.create()
    return session.session_key


def closed(key: str) -> None:
    _store(key).delete()


def client_ip(request) -> str | None:
    # An installation's Caddy sends the reader's address alone as X-Forwarded-For; on the dev
    # host the tunnel's CF-Connecting-IP comes through Vite, whose REMOTE_ADDR is only the proxy.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    return request.META.get("HTTP_CF_CONNECTING_IP") or forwarded or request.META.get("REMOTE_ADDR")


def address_of(request) -> str | None:
    try:
        return str(ipaddress.ip_address(client_ip(request) or ""))
    except ValueError:
        return None


def started(request, way: str, passkey_due: bool = False) -> None:
    """Marks the session just signed in with the browser that signed in with it, and clears the
    sessions that have run out."""
    from apps.journal import entries

    SessionStore.clear_expired()
    entries.signed_in(request, way)
    request.session[SIGNED_IN] = {
        "agent": request.META.get("HTTP_USER_AGENT", "")[:300],
        "address": address_of(request),
        "at": timezone.now().isoformat(),
    }
    if passkey_due:
        request.session[PASSKEY_DUE] = True


def confirm(session) -> None:
    session[CONFIRMED] = timezone.now().isoformat()


def fresh(confirmed: str | None, within: timedelta = CONFIRMED_FOR) -> bool:
    return confirmed is not None and timezone.now() - datetime.fromisoformat(confirmed) < within


def numbered(key: str) -> str:
    """What the browser is shown of a session's key, which signs in whoever holds it."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def listed(user, current: str | None) -> list[dict]:
    from .models import Session

    found = Session.objects.filter(
        user=user, signed_in_at__isnull=False, expire_date__gt=timezone.now()
    ).order_by(F("seen_at").desc(nulls_last=True), "-signed_in_at")
    return [
        {
            "id": numbered(session.session_key),
            "agent": session.agent,
            "address": session.address,
            "signed_in_at": session.signed_in_at,
            "seen_at": session.seen_at or session.signed_in_at,
            "current": session.session_key == current,
            "offline": session.offline,
        }
        for session in found
    ]


def ended(user, number: str | None = None) -> int:
    """Ends one of the user's sessions, or every one of them; the count it ended."""
    from .models import Session

    keys = [
        key
        for key in Session.objects.filter(user=user).values_list("session_key", flat=True)
        if number is None or numbered(key) == number
    ]
    Session.objects.filter(session_key__in=keys).delete()
    return len(keys)


def _stale(seen: str | None) -> bool:
    return seen is None or timezone.now() - datetime.fromisoformat(seen) > SEEN_EVERY


@sync_and_async_middleware
def seen(get_response):
    """Marks every few minutes when a signed-in browser was last seen."""
    if iscoroutinefunction(get_response):

        async def marking(request):
            response = await get_response(request)
            if (await request.auser()).is_authenticated and _stale(
                await request.session.aget(SEEN)
            ):
                await request.session.aset(SEEN, timezone.now().isoformat())
            return response

        return marking

    def marked(request):
        response = get_response(request)
        if request.user.is_authenticated and _stale(request.session.get(SEEN)):
            request.session[SEEN] = timezone.now().isoformat()
        return response

    return marked
