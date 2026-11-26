"""A guest of a Ponistra OS machine as a source of Files (DT7): its SFTP session comes over the
machine's link (ponistra-os `agent/API.md`, Guest files) and acts as root in the guest, so it is
offered only to who manages the machine, and a guest with an owner only to that owner."""

import json
import logging
import re
import uuid

from apps.computers import link, streams
from apps.computers.models import Computer
from apps.core.api import Refused
from apps.core.asyncdb import database

from . import sftp
from .remote import Failed

log = logging.getLogger(__name__)

# Incus's instance names.
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}")
# Guests still being made or that failed to be have no files to open yet.
MAKING = {"Creating", "Setting up", "Importing", "Error"}
# The link carries a refusal before the session as the agent's error alone, whose sentences
# (guests.ErrForbidden, ErrNotFound, ErrConflict, ErrIncusDown) still tell its status.
REFUSALS = [
    ("not for this account", Failed("guest_owned", 403)),
    ("no such guest", Failed("guest_missing", 404)),
    ("not possible in the guest's current state", Failed("guest_not_running")),
    ("guests are unavailable", Failed("guest_unavailable", 503)),
]
# Why a machine lists no guests, by the status its link answered.
LISTING = {503: "guest_offline", 504: "location_unreachable"}


def _managed(user):
    return Computer.objects.managed(user).filter(left_at__isnull=True)


def managed(user, pk: object) -> Computer:
    """The machine the request names, where the user manages it."""
    try:
        key = uuid.UUID(str(pk))
    except ValueError:
        raise Refused(404, "not_found") from None
    found = _managed(user).filter(pk=key).first()
    if found is None:
        raise Refused(404, "not_found")
    return found


def named(guest: object) -> str:
    if not isinstance(guest, str) or not NAME.fullmatch(guest):
        raise Refused(404, "not_found")
    return guest


def _offered(guest: dict, account: str) -> bool:
    owner = guest.get("owner") or ""
    return guest.get("status") not in MAKING and owner in ("", account)


async def listed(user) -> list[dict]:
    """Every machine the user manages with the guests it offers them, as each machine answers
    now; one off its link says so and the rest are listed all the same."""
    account = link.account(user)
    computers = await database(lambda: list(_managed(user).order_by("name")))()
    found = []
    for computer in computers:
        shown = {"id": str(computer.pk), "name": computer.name, "guests": []}
        status, _, body = await link.requested(computer, "GET", "/v1/guests", account)
        if status != 200:
            shown["error"] = LISTING.get(status, "guest_refused")
            if status not in LISTING:
                log.warning("%s did not list its guests: %s %s", computer.name, status, body[:200])
        else:
            shown["guests"] = [
                {"name": guest["name"], "kind": guest.get("kind", ""), "status": guest["status"]}
                for guest in sorted(json.loads(body), key=lambda guest: guest["name"])
                if _offered(guest, account)
            ]
        found.append(shown)
    return found


def refused(error: streams.Refused) -> Failed:
    if error.status == 503:
        return Failed("guest_offline", 503)
    if error.status == 504:
        return Failed("location_unreachable")
    for sentence, failed in REFUSALS:
        if sentence in error.error:
            return failed
    log.warning("a guest's files were refused: %s %s", error.status, error.error)
    return Failed("guest_refused")


def why(stream: streams.Stream) -> Failed:
    """The session's end as the location's error: the guest's side ended, Incus failed, or the
    link broke."""
    code, reason = stream.ended or (1006, "")
    if code == 1000:
        return Failed("location_closed")
    if code == 1003:
        return Failed("location_garbled")
    if code == 1011:
        log.warning("a guest's files ended in Incus: %s", reason)
        return Failed("location_failed")
    return Failed("location_unreachable")


def carrier(computer: Computer, guest: str, account: str) -> sftp.Streamed:
    async def opening() -> streams.Stream:
        try:
            return await streams.opened(computer, "GET", f"/v1/guests/{guest}/sftp", account)
        except streams.Refused as error:
            raise refused(error) from None

    return sftp.Streamed(f"{computer.name}/{guest}", opening, why)


async def reached(computer: Computer, guest: str, user) -> sftp.Sftp:
    """The guest's files over a session of the user's own, as the owner rule asks of each
    account; kept open for their next request, as a location's connection is."""
    account = link.account(user)
    key = f"guest:{computer.pk}/{guest}:{account}"
    carried = carrier(computer, guest, account)
    return sftp.Sftp(await sftp.connection(key, lambda: sftp.Connection(carried, "/")))
