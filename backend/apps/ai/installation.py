"""The installation's AI (D14, D15): off until the administrator turns it on with the
installation's own Anthropic API key, which is kept sealed and never leaves the server, and
each user's runs bounded by what they may take in a month, where the administrator sets it."""

from decimal import Decimal

import anthropic
from django.db.models import Sum
from django.utils import timezone

from apps.actions.models import ActionRun
from apps.core import sealed

from .models import Setting

CHECKED_WITH = "claude-haiku-5-5"


class Unavailable(Exception):
    """Why the installation's actions cannot call a model now."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def setting() -> Setting:
    return Setting.objects.filter(pk=1).first() or Setting()


def opened(found: Setting) -> str | None:
    """The setting's key, none where it has none or the installation's secret has changed
    since it was sealed."""
    if not found.key:
        return None
    return sealed.opened("ai key", found.key)


def describe(found: Setting) -> dict:
    return {
        "enabled": found.enabled,
        "hint": found.hint,
        "lost": bool(found.key) and opened(found) is None,
        "changed_at": found.changed_at,
        "monthly": None if found.monthly is None else float(found.monthly),
    }


def check(key: str) -> None:
    """Asks Anthropic whether the key is good, by one call that costs nothing."""
    try:
        anthropic.Anthropic(api_key=key, max_retries=1, timeout=20).models.retrieve(CHECKED_WITH)
    except anthropic.AuthenticationError, anthropic.PermissionDeniedError:
        raise Unavailable("key_refused") from None
    except anthropic.APIConnectionError:
        raise Unavailable("ai_unreachable") from None


def change(user, enabled: bool, key: str | None) -> Setting:
    """Turns the installation's AI on or off, with a new key where one is given, checked
    first; it cannot be on without a key that opens."""
    found = setting()
    if key is not None:
        check(key)
        found.key, found.hint = sealed.seal("ai key", key), key[-4:]
    if enabled and opened(found) is None:
        raise Unavailable("key_needed")
    found.enabled, found.changed_by, found.changed_at = enabled, user, timezone.now()
    found.save()
    return found


def bound(user, monthly: Decimal | None) -> Setting:
    """Sets how many dollars each user's runs may take in a calendar month, none for no bound."""
    found = setting()
    found.monthly, found.changed_by, found.changed_at = monthly, user, timezone.now()
    found.save()
    return found


def spent(user_id: int) -> Decimal:
    """What the user's runs have taken since the month began, in the installation's time."""
    began = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    runs = ActionRun.objects.filter(user=user_id, started_at__gte=began)
    return runs.aggregate(total=Sum("cost"))["total"] or Decimal(0)


def allowed(user_id: int) -> None:
    """Refuses a model to a user whose runs have taken what a month allows them."""
    monthly = setting().monthly
    if monthly is not None and spent(user_id) >= monthly:
        raise Unavailable("limit_reached")


def client() -> anthropic.Anthropic:
    """A client with the installation's key, refused while its AI is off."""
    found = setting()
    if not found.enabled:
        raise Unavailable("ai_off")
    if (key := opened(found)) is None:
        raise Unavailable("key_lost")
    return anthropic.Anthropic(api_key=key)


def enabled() -> bool:
    found = setting()
    return found.enabled and opened(found) is not None
