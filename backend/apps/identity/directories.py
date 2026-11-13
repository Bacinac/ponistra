"""The loop that reads each LDAP directory as often as it is set to, and a SAML provider's
metadata once a day, so its new signing certificate is known before it signs with it."""

from datetime import timedelta
from logging import getLogger

from django.utils import timezone

from apps.core.asyncdb import database, drain, notify

from . import directory, saml
from .models import Provider
from .people import Refusal

log = getLogger(__name__)

CHANNEL = "identity_directories"
SWEEP = timedelta(minutes=1)
EVERY_MINUTES = 60
METADATA_EVERY = timedelta(days=1)


def wake() -> None:
    notify(CHANNEL)


def due() -> list[int]:
    now = timezone.now()
    found = []
    for provider in Provider.objects.filter(
        enabled=True, kind__in=(Provider.Kind.LDAP, Provider.Kind.SAML)
    ):
        if provider.kind == Provider.Kind.LDAP:
            every = timedelta(minutes=provider.settings.get("every") or EVERY_MINUTES)
        elif provider.settings.get("metadata_url"):
            every = METADATA_EVERY
        else:
            continue
        if provider.synced_at is None or provider.synced_at + every <= now:
            found.append(provider.pk)
    return found


def refreshed(provider_id: int) -> None:
    provider = Provider.objects.get(pk=provider_id)
    provider.settings = {**provider.settings, **saml.fetched(provider.settings["metadata_url"])}
    provider.synced_at, provider.error = timezone.now(), ""
    provider.save(update_fields=["settings", "synced_at", "error"])


def passed(provider_id: int) -> None:
    """One pass over the provider; what fails is kept on it for the administrator, and it is
    tried again at its next turn."""
    provider = Provider.objects.filter(pk=provider_id).first()
    if provider is None:
        return
    try:
        if provider.kind == Provider.Kind.LDAP:
            directory.synced(provider.pk)
        else:
            refreshed(provider.pk)
    except Refusal as refusal:
        log.warning("identity: %s: %s", provider, refusal.code)
        Provider.objects.filter(pk=provider.pk).update(synced_at=timezone.now(), error=refusal.code)
    except Exception:
        log.exception("identity: %s failed", provider)
        Provider.objects.filter(pk=provider.pk).update(synced_at=timezone.now(), error="unexpected")


async def directories() -> None:
    async def step() -> bool:
        for provider_id in await database(due)():
            await database(passed, own_thread=True)(provider_id)
        return False

    await drain(CHANNEL, step, SWEEP, log)
