"""PONISTRA's side of LiveKit: the key a browser joins a room with, and who is in a room as
LiveKit's API lists them. Both are JWTs signed with the installation's PONISTRA_LIVEKIT_SECRET."""

import json
import time

import httpx2
import jwt
from django.conf import settings

KEY = "ponistra"
# The browser connects at once; LiveKit itself renews the key for as long as it stays.
JOINING = 10 * 60
ASKING = 60
WAIT = 5


class Unavailable(Exception):
    pass


def _signed(claims: dict, seconds: int) -> str:
    now = int(time.time())
    return jwt.encode(
        {"iss": KEY, "nbf": now, "exp": now + seconds, **claims},
        settings.LIVEKIT_SECRET,
        algorithm="HS256",
    )


def guest_identity(pk: int) -> str:
    """What a guest's participants are named by, each with a mark of its own after a dot, as a
    user's are by their id."""
    return f"guest{pk}"


def is_guest(identity: str) -> bool:
    return identity.startswith("guest")


def joining(room: str, identity: str, name: str, guest: bool = False) -> str:
    return _signed(
        {
            "sub": identity,
            "name": name,
            "metadata": json.dumps({"guest": guest}),
            "video": {
                "room": room,
                "roomJoin": True,
                "canPublish": True,
                "canSubscribe": True,
                "canPublishData": True,
            },
        },
        JOINING,
    )


async def present(room: str) -> list[str]:
    """The names of those in the room now."""
    return [each.get("name", "") for each in await _participants(room)]


async def inside(room: str) -> list[str]:
    """The identities those in the room now joined with."""
    return [each.get("identity", "") for each in await _participants(room)]


async def _participants(room: str) -> list[dict]:
    key = _signed({"video": {"room": room, "roomAdmin": True}}, ASKING)
    try:
        async with httpx2.AsyncClient(timeout=WAIT, trust_env=False) as client:
            answer = await client.post(
                f"{settings.LIVEKIT_URL}/twirp/livekit.RoomService/ListParticipants",
                json={"room": room},
                headers={"Authorization": f"Bearer {key}"},
            )
    except httpx2.HTTPError as error:
        raise Unavailable(f"LiveKit at {settings.LIVEKIT_URL}: {error!r}") from error
    if answer.status_code == 404:
        return []
    if answer.status_code != 200:
        raise Unavailable(f"LiveKit answered {answer.status_code}: {answer.text[:200]}")
    return answer.json().get("participants", [])


def recording(room: str) -> str:
    """The key the recorder joins the room with: hidden from those in it, taking what each of
    them sends and sending nothing."""
    return _signed(
        {
            "sub": "recorder",
            "video": {
                "room": room,
                "roomJoin": True,
                "canPublish": False,
                "canSubscribe": True,
                "canPublishData": False,
                "hidden": True,
                "recorder": True,
            },
        },
        JOINING,
    )


def address() -> str:
    """LiveKit as the recorder reaches it."""
    return "ws://" + settings.LIVEKIT_URL.removeprefix("http://")


def recorded(room: str, recording: bool) -> None:
    """Tells everyone in the room, guests too, whether it is being recorded, through the room's
    metadata."""
    key = _signed({"video": {"room": room, "roomAdmin": True}}, ASKING)
    try:
        with httpx2.Client(timeout=WAIT, trust_env=False) as client:
            answer = client.post(
                f"{settings.LIVEKIT_URL}/twirp/livekit.RoomService/UpdateRoomMetadata",
                json={"room": room, "metadata": json.dumps({"recording": recording})},
                headers={"Authorization": f"Bearer {key}"},
            )
    except httpx2.HTTPError as error:
        raise Unavailable(f"LiveKit at {settings.LIVEKIT_URL}: {error!r}") from error
    if answer.status_code == 404 and not recording:
        return
    if answer.status_code != 200:
        raise Unavailable(f"LiveKit answered {answer.status_code}: {answer.text[:200]}")
