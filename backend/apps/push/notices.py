"""The notices an app hands over for a user's browsers, kept until sent (D15: nothing leaves the
installation but the encrypted notice itself, through the browser's own push service): written
once the transaction they came from commits, sent by one loop, worded for each browser in the
language it reads PONISTRA in, and a browser the service no longer knows is forgotten."""

import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from logging import getLogger

import httpx2
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.asyncdb import database, drain, notify
from apps.users.views import describe as describe_user

from . import webpush
from .models import Keys, Notice, Setting, Subscription

log = getLogger(__name__)

CHANNEL = "push"
SWEEP = timedelta(minutes=5)
RETRY = timedelta(minutes=1)
TRIES = 3
GONE = {404, 410}
# A push service takes 4096 bytes of a notice, so each text is cut to what a notification shows.
TEXT = 160
# What each module holds unread for a user, registered as the app starts; their sum is the count
# on the installed app's icon, which a notice carries for a browser with no window of the app open.
UNREAD: list[Callable[[int], int]] = []
WORDS = {
    "hr": {
        "calls": "{name} vas zove",
        "meeting": "Sastanak",
        "untitled": "(bez predmeta)",
        "sign_in": "Nova prijava u Ponistru",
        "passkey": "Dodan je pristupni ključ",
        "app_password": "Dodana je lozinka aplikacije",
        "later_failed": "Poruka nije poslana",
        "later_refused": "Neki primatelji nisu primili poruku",
        "later_unanswered": "Nitko nije odgovorio na poruku",
        "later_away_failed": "Automatski odgovor nije poslan",
        "health": "Ponistra traži pažnju administratora",
        "uploaded": "Nova datoteka u mapi {folder}",
        "problem_service": "Ne odgovara: {name}",
        "problem_queue": "Red stoji: {name}",
        "problem_disk": "Disk je gotovo pun",
        "problem_snapshots": "Snimke kasne",
        "problem_archive": "Arhiviranje izmjena baze kasni",
        "problem_offsite": "Kopija izvan poslužitelja kasni",
        "problem_source": "Izvor korisnika se ne može pročitati: {name}",
        "database": "baza podataka",
        "converter": "pretvarač dokumenata",
        "printer": "ispis u PDF",
        "ocr": "prepoznavanje teksta",
        "meetings": "sastanci",
        "relay": "relej sastanaka",
        "outside": "vanjski relej sastanaka",
        "jobs": "poslovi",
        "text": "čitanje teksta datoteka",
        "batches": "skupne radnje",
        "code_waiting": "Chat čeka vašu odluku",
        "code_said": "Koordinator javlja",
        "code_asks": "Koordinator čeka vaš unos",
        "code_ready": "Krug je spreman za objedinjavanje",
        "code_consolidated": "Krug je objedinjen i čeka push",
        "code_browser": "Provjera u pregledniku nije prošla",
        "code_night": "Noćna provjera nije prošla",
        "code_general": "Općenito",
        "code_failed": "{project} · palih testova: {count}",
        "code_limit": "Limit pretplate je pri kraju",
        "code_credits": "Troše se krediti",
        "code_week": "Tjedni limit",
        "code_percent": "{name}: {percent} %",
        "code_memory": "Prijedlog za memoriju",
        "code_memories": "Prijedloga za memoriju: {count}",
        "code_advice": "Preporuke za prijedloge memorije: {count}",
        "code_yes": "Da",
        "code_no": "Ne",
    },
    "en": {
        "calls": "{name} is calling",
        "meeting": "Meeting",
        "untitled": "(no subject)",
        "sign_in": "New sign-in to Ponistra",
        "passkey": "A passkey was added",
        "app_password": "An app password was added",
        "later_failed": "A message was not sent",
        "later_refused": "Some recipients did not get a message",
        "later_unanswered": "No one answered a message",
        "later_away_failed": "An automatic answer was not sent",
        "health": "Ponistra needs its administrator",
        "uploaded": "New file in {folder}",
        "problem_service": "Not answering: {name}",
        "problem_queue": "Queue stalled: {name}",
        "problem_disk": "A disk is almost full",
        "problem_snapshots": "Snapshots are late",
        "problem_archive": "Archiving the database's changes is late",
        "problem_offsite": "The off-site copy is late",
        "problem_source": "The user source cannot be read: {name}",
        "database": "database",
        "converter": "document converter",
        "printer": "PDF printing",
        "ocr": "text recognition",
        "meetings": "meetings",
        "relay": "meeting relay",
        "outside": "external meeting relay",
        "jobs": "jobs",
        "text": "reading the text of files",
        "batches": "batch actions",
        "code_waiting": "A chat waits for your decision",
        "code_said": "The coordinator reports",
        "code_asks": "The coordinator waits for your input",
        "code_ready": "A round is ready to consolidate",
        "code_consolidated": "A round is consolidated and waits for its push",
        "code_browser": "The browser check failed",
        "code_night": "The night check failed",
        "code_general": "General",
        "code_failed": "{project} · failed tests: {count}",
        "code_limit": "The plan's limit is running out",
        "code_credits": "Credits are being spent",
        "code_week": "Weekly limit",
        "code_percent": "{name}: {percent}%",
        "code_memory": "A proposal for the memory",
        "code_memories": "Proposals for the memory: {count}",
        "code_advice": "Advice on the memory's proposals: {count}",
        "code_yes": "Yes",
        "code_no": "No",
    },
}
# Where the user sees, and can take back, what a security notice tells of.
SECURITY = {
    "sign_in": "/settings/devices",
    "passkey": "/settings/passkeys",
    "app_password": "/settings/app-passwords",
}
# What a chat waiting on its owner can be answered from the notification itself, as its panel's
# Yes and No would (KR13).
ANSWERED = {"waiting", "asks"}


def setting() -> Setting:
    return Setting.objects.get_or_create(pk=1)[0]


def describe_setting(found: Setting) -> dict:
    return {
        "on": found.on,
        "changed_by": found.changed_by and describe_user(found.changed_by),
        "changed_at": found.changed_at,
    }


def change(user, on: bool) -> Setting:
    """Turns it on or off for the whole installation; off, what waits to be sent goes."""
    with transaction.atomic():
        found = Setting.objects.select_for_update().get_or_create(pk=1)[0]
        found.on, found.changed_by, found.changed_at = on, user, timezone.now()
        found.save()
        if not on:
            Notice.objects.all().delete()
    return found


def topic(prefix: str, key: uuid.UUID | int) -> str:
    """A tag within the 32 URL-safe characters a push service's Topic takes, under which a newer
    notice replaces an older one not yet shown."""
    if isinstance(key, uuid.UUID):
        return f"{prefix}-{webpush.b64(key.bytes)}"
    return f"{prefix}-{key}"


def tell(
    users,
    kind: str,
    data: dict,
    *,
    tag: str = "",
    urgency: str = Notice.Urgency.NORMAL,
    ttl: int = 86400,
) -> None:
    """Hands the users who let a browser be reached a notice, sent once the current transaction
    commits; nothing while the installation sends none."""
    reached = set(Subscription.objects.filter(user_id__in=users).values_list("user_id", flat=True))
    if not reached or not setting().on:
        return
    Notice.objects.bulk_create(
        Notice(user_id=user, kind=kind, data=data, tag=tag, urgency=urgency, ttl=ttl)
        for user in reached
    )
    notify(CHANNEL)


def cut(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= TEXT else text[: TEXT - 1] + "…"


def unread(user: int) -> int:
    return sum(count(user) for count in UNREAD)


def worded(notice: Notice, language: str, waiting: int) -> dict:
    """What the browser shows for the notice, in its language, and what waits unread for the
    user."""
    words = WORDS.get(language, WORDS["hr"])
    data = notice.data
    answers = {}
    match notice.kind:
        case Notice.Kind.MAIL:
            title = data["name"] or data["address"]
            body = data["subject"] or words["untitled"]
            url = f"/mail/{data['folder']}/{data['message']}"
        case Notice.Kind.MESSAGE:
            title = data["title"] or data["by"]
            body = f"{data['by']}: {data['text']}" if data["title"] else data["text"]
            url = f"/chat/{data['conversation']}"
        case Notice.Kind.RING:
            title = words["calls"].format(name=data["by"])
            body = data["title"] or words["meeting"]
            url = f"/meet/{data['meeting']}"
        case Notice.Kind.SECURITY:
            title = words[data["event"]]
            body = data.get("name") or data.get("address") or ""
            url = SECURITY[data["event"]]
        case Notice.Kind.HEALTH:
            kind, _, name = data["problem"].partition(":")
            title = words["health"]
            body = words[f"problem_{kind}"].format(name=words.get(name, name))
            url = "/health"
        case Notice.Kind.UPLOADED:
            title = words["uploaded"].format(folder=data["folder"])
            body = f"{data['sender']}: {data['title']}" if data["sender"] else data["title"]
            url = f"/p/{data['node']}"
        case Notice.Kind.LATER:
            title = words[f"later_{data['event']}"]
            body = data["subject"] or words["untitled"]
            url = "/settings/away" if data["event"] == "away_failed" else "/mail/later"
            if "message" in data:
                url = f"/mail/{data['folder']}/{data['message']}"
        case Notice.Kind.CODE:
            event = data["event"]
            title = words[f"code_{event}"]
            project = data.get("project") or words["code_general"]
            if event == "memory" and data.get("count"):
                title = words["code_memories"].format(count=data["count"])
                body = ""
            elif event == "memory":
                body = f"{project} · {data['file']}: {data['text']}"
            elif event == "advice":
                title = words["code_advice"].format(count=data["count"])
                body = ""
            elif event in ("limit", "credits"):
                name = data["name"] or words["code_week"]
                body = (
                    words["code_percent"].format(name=name, percent=data["percent"])
                    if event == "limit"
                    else name
                )
            elif event == "waiting":
                body = f"{project}: {data['chat']}"
            elif event in ("said", "asks"):
                body = f"{project}: {data['text'] or data['chat']}"
            elif event in ("ready", "consolidated"):
                body = f"{project}: {data['round']}"
            elif data["failed"]:
                body = words["code_failed"].format(project=project, count=data["failed"])
            else:
                body = project
            url = "/workspace?view=memory" if event in ("memory", "advice") else "/workspace"
            yes_no = [
                {"action": "yes", "title": words["code_yes"]},
                {"action": "no", "title": words["code_no"]},
            ]
            # A memory's proposal is accepted or rejected where the notification says (MEM5).
            if event == "memory" and data.get("proposal"):
                answers = {"answer": f"/api/memory/proposals/{data['proposal']}", "actions": yes_no}
            if event in ANSWERED:
                answers = {"session": data["session"], "actions": yes_no}
        case _:
            raise ValueError(f"unknown notice kind {notice.kind!r}")
    return {
        "kind": notice.kind,
        "title": cut(title),
        "body": cut(body),
        "url": url,
        "tag": notice.tag,
        "unread": waiting,
        **answers,
    }


@database
def _taken() -> tuple[Notice, int, list[Subscription], Keys, str] | None:
    """The oldest notice due, taken for a try: not due again for RETRY, and no longer kept once
    its tries are spent or its time to live has passed."""
    now = timezone.now()
    with transaction.atomic():
        notice = (
            Notice.objects.select_for_update(skip_locked=True)
            .filter(due_at__lte=now)
            .order_by("pk")
            .first()
        )
        if notice is None:
            return None
        spent = notice.tried >= TRIES or now > notice.created_at + timedelta(seconds=notice.ttl)
        if spent:
            notice.delete()
            return None
        Notice.objects.filter(pk=notice.pk).update(tried=F("tried") + 1, due_at=now + RETRY)
        found = list(Subscription.objects.filter(user_id=notice.user_id))
    return notice, unread(notice.user_id), found, webpush.keys(), webpush.contact()


@database
def _settled(notice: Notice, gone: list[int], sent: list[int], done: bool) -> None:
    if gone:
        Subscription.objects.filter(pk__in=gone).delete()
    if sent:
        Subscription.objects.filter(pk__in=sent).update(used_at=timezone.now())
    if done:
        Notice.objects.filter(pk=notice.pk).delete()


async def _step(transport: httpx2.AsyncBaseTransport | None = None) -> bool:
    taken = await _taken()
    if taken is None:
        return False
    notice, waiting, subscriptions, keys, contact = taken
    gone, sent, failed = [], [], []
    async with httpx2.AsyncClient(
        timeout=webpush.WAIT, trust_env=False, transport=transport
    ) as client:
        for subscription in subscriptions:
            payload = json.dumps(worded(notice, subscription.language, waiting)).encode()
            try:
                status = await webpush.posted(
                    client,
                    subscription,
                    keys,
                    contact,
                    payload,
                    ttl=notice.ttl,
                    urgency=notice.urgency,
                    topic=notice.tag,
                )
            except httpx2.HTTPError as error:
                log.warning("push: %s unreachable: %r", subscription.endpoint, error)
                failed.append(subscription.pk)
                continue
            if status in GONE:
                gone.append(subscription.pk)
            elif 200 <= status < 300:
                sent.append(subscription.pk)
            else:
                log.warning("push: %s answered %s", subscription.endpoint, status)
                failed.append(subscription.pk)
    await _settled(notice, gone, sent, done=not failed)
    return True


async def deliver() -> None:
    """Sends the notices as they come, and what a lost notification or a failed try left each
    SWEEP."""
    await drain(CHANNEL, _step, SWEEP, log)
