"""The user's mail accounts, their folders and messages (D15, S3)."""

import io
import json
import re
import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta
from email.headerregistry import Address
from functools import partial, reduce
from html import escape
from itertools import chain, count
from logging import getLogger
from operator import or_
from urllib.parse import urlsplit
from uuid import UUID

from anyio import to_thread
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.expressions import ArraySubquery
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery, TextField, Value
from django.db.models.fields.json import KT
from django.db.models.functions import Coalesce, Collate, Lower, NullIf
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.utils.http import content_disposition_header

from apps.access import mailed
from apps.actions import runs
from apps.actions.models import ActionRun
from apps.actions.registry import ACTIONS, TARGETS, unfit
from apps.ai import detection, installation, model
from apps.ai.installation import Unavailable
from apps.ai.models import Reading
from apps.blobs import store
from apps.blobs.models import Blob, Upload
from apps.blobs.views import describe as describe_blob
from apps.blobs.views import serve as serve_blob
from apps.calendar import invitations
from apps.contacts import search as contacts
from apps.content import schema
from apps.core import sealed
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database, notify, waited
from apps.core.emoji import qualified
from apps.journal import entries
from apps.journal.entries import Kind
from apps.retention import kept as retention
from apps.users.accounts import administrator, text

from . import (
    absence,
    acting,
    correspondents,
    fetching,
    imap,
    mime,
    opened,
    reactions,
    safe,
    sealing,
    secured,
    sending,
    sharing,
    signin,
    sync,
    taking,
    translating,
)
from .activesync import client as activesync
from .activesync import directory
from .activesync import sync as activesync_sync
from .models import (
    Account,
    Arrival,
    Attachment,
    Away,
    Client,
    Correspondent,
    Decided,
    Draft,
    Fetched,
    Folder,
    Message,
    Provider,
    Role,
    Sealed,
    Security,
    Signature,
    SignatureImage,
    Unsent,
    UnsentFile,
)
from .servers import APP_PASSWORDS, guessed

log = getLogger(__name__)
# Exchange's folders for Outlook on a computer: its notes, what it has yet to send, its sync logs.
OUTLOOK_OWN = {"Notes", "Outbox", "Sync Issues"}

PAGE = 50
FLAGS = ("seen", "flagged")
# The account colours (`ACCOUNT_COLORS` in compose.tsx) in the order new accounts take them, so
# that the first few are told apart at a glance: petrol, orange, violet, green, rose, blue, gold.
TURNS = (0, 2, 3, 1, 4, 6, 5)
DOMAIN = re.compile(r"[^\s@/]+\.[^\s@/]+")
# What a folder's list may be sorted by, each newest first among its equals.
SORTS = ("date", "correspondent", "priority")
# Where a provider sends the user back once they have signed in.
RETURN = "/api/oauth/{provider}"


def _address(data: dict) -> str:
    address = str(data.get("address", "")).strip().lower()
    try:
        validate_email(address)
    except ValidationError:
        raise Refused(400, "invalid_email") from None
    return address


def _server(data: dict, kind: str) -> dict:
    given = data.get(kind)
    if not isinstance(given, dict):
        raise Refused(400, f"invalid_{kind}")
    host = str(given.get("host", "")).strip().lower()
    port = given.get("port")
    security = given.get("security")
    if not host or len(host) > 253 or not isinstance(port, int) or not 0 < port < 65536:
        raise Refused(400, f"invalid_{kind}")
    if security not in Security.values:
        raise Refused(400, f"invalid_{kind}")
    return {f"{kind}_host": host, f"{kind}_port": port, f"{kind}_security": security}


def _activesync_host(data: dict) -> str:
    """The server's name, with its port where it is not 443; a pasted address is cut to it."""
    given = data.get("activesync")
    host = str(given.get("host", "")).strip().lower() if isinstance(given, dict) else ""
    host = urlsplit(host if "//" in host else f"//{host}").netloc
    found = re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*(:(\d{1,5}))?", host)
    if not found or len(host) > 253 or not 0 < int(found[3] or 443) < 65536:
        raise Refused(400, "invalid_activesync")
    return host


def _fields(data: dict) -> dict:
    protocol = data.get("protocol", Account.Protocol.IMAP)
    if protocol not in Account.Protocol.values:
        raise Refused(400, "invalid_protocol")
    fields = {
        "address": _address(data),
        "name": text(data, "name", 150),
        "username": text(data, "username", 320, required=True),
        "login": Account.Login.PASSWORD,
        "protocol": protocol,
    }
    if protocol == Account.Protocol.ACTIVESYNC:
        unused = {"host": "", "port": None, "security": ""}
        servers = {
            f"{kind}_{key}": value for kind in ("imap", "smtp") for key, value in unused.items()
        }
        return fields | servers | {"activesync_host": _activesync_host(data)}
    return fields | _server(data, "imap") | _server(data, "smtp") | {"activesync_host": ""}


def _signed_in(fields: dict, login: imap.Login, device: str) -> None:
    try:
        if fields["protocol"] == Account.Protocol.ACTIVESYNC:
            given = (fields["activesync_host"], login.username, login.password, device)
            with activesync.Session(*given) as session:
                session.signed_in()
            return
        servers = [fields[f"imap_{key}"] for key in ("host", "port", "security")]
        with imap.imap(*servers, login):
            pass
        servers = [fields[f"smtp_{key}"] for key in ("host", "port", "security")]
        imap.smtp_checked(*servers, login)
    except imap.Failed as failed:
        raise Refused(400, failed.code) from None


async def _checked(fields: dict, login: imap.Login, device: str = "") -> None:
    """Signs in to the servers, so that the account is kept only once it works."""
    signed_in = partial(_signed_in, fields, login, device)
    await to_thread.run_sync(signed_in, abandon_on_cancel=True)


def describe_folder(folder: Folder) -> dict:
    return {
        "id": folder.pk,
        "name": folder.name,
        "role": folder.role,
        "parent": folder.parent_id,
        "account": folder.account_id,
        "unseen": folder.unseen,
        "count": folder.count,
    }


def _own_signature(account: Account) -> Signature | None:
    try:
        return account.own_signature
    except Signature.DoesNotExist:
        return None


def _signature_of(account: Account) -> str:
    own = _own_signature(account)
    return own.html if own else shared_signature(account.owner)


def describe(account: Account) -> dict:
    own = _own_signature(account)
    return {
        "id": account.pk,
        "address": account.address,
        "name": account.name,
        "label": account.label,
        "signature": _signature_of(account),
        "own_signature": own is not None,
        "username": account.username,
        "login": account.login,
        "protocol": account.protocol,
        "activesync": {"host": account.activesync_host},
        "imap": {
            "host": account.imap_host,
            "port": account.imap_port,
            "security": account.imap_security,
        },
        "smtp": {
            "host": account.smtp_host,
            "port": account.smtp_port,
            "security": account.smtp_security,
        },
        "color": account.color,
        "default": account.default,
        "together": account.together,
        "unseen": _unseen(account.pk),
        "state": account.state,
        "error": account.error,
        "synced_at": account.synced_at,
        "older": account.sources.filter(low__gt=1).exists(),
    }


@api("POST")
async def servers(request):
    """The servers the address's mail is likely on, for the user to confirm."""
    address = _address(body(request))
    return JsonResponse(await to_thread.run_sync(guessed, address, abandon_on_cancel=True))


def _of(account: int) -> Q:
    """The messages that came to the account."""
    came = Arrival.objects.filter(message=OuterRef("pk"), source__account_id=account)
    return Q(account_id=account) | Exists(came)


def _unseen(account: int) -> int:
    return Message.objects.filter(_of(account), folder__role=Role.INBOX, seen=False).count()


def unseen(user: int) -> int:
    """The messages not yet read in the inboxes of the user's accounts, as each account counts
    them."""
    return sum(
        _unseen(account)
        for account in Account.objects.filter(owner_id=user).values_list("pk", flat=True)
    )


def _apart() -> Q:
    """The messages in the shared folders that only accounts kept apart from them brought."""
    shared = Arrival.objects.filter(message=OuterRef("pk"), source__account__together=True)
    return ~Q(folder__role="") & Q(account__together=False) & ~Exists(shared)


def _shown(found, account: str | None):
    """The messages a list shows: those of the account it names, or all but those kept apart."""
    if not account:
        return found.exclude(_apart())
    try:
        return found.filter(_of(int(account)))
    except ValueError:
        raise Refused(400, "invalid_account") from None


def _counted(user):
    def counted(**where):
        found = Message.objects.filter(folder=OuterRef("pk"), **where).exclude(_apart())
        found = found.exclude(reactions.ATTACHED)
        total = found.order_by().values("folder").annotate(total=Count("pk")).values("total")
        return Coalesce(Subquery(total), 0)

    return user.mail_folders.annotate(unseen=counted(seen=False), count=counted())


def _folders(user) -> list[Folder]:
    """The user's folders, but those Exchange keeps for Outlook itself while nothing is in them."""
    folders = list(_counted(user).order_by("name"))
    inside = defaultdict(list)
    for folder in folders:
        inside[folder.parent_id].append(folder)
    nodes = {folder.pk for folder in folders if folder.account_id}

    def empty(folder: Folder) -> bool:
        return not folder.count and all(empty(each) for each in inside[folder.pk])

    def left(folder: Folder):
        yield folder.pk
        for each in inside[folder.pk]:
            yield from left(each)

    hidden = {
        pk
        for folder in folders
        if folder.parent_id in nodes and folder.name in OUTLOOK_OWN and empty(folder)
        for pk in left(folder)
    }
    return [folder for folder in folders if folder.pk not in hidden]


def _decided(user) -> list[dict]:
    return [
        {"domain": domain, "shown": shown}
        for domain, shown in user.mail_decided.order_by("domain").values_list("domain", "shown")
    ]


def _rules(user) -> list[dict]:
    return [
        {"id": pk, "sender": sender, "folder": folder}
        for pk, sender, folder in user.mail_rules.order_by("sender").values_list(
            "pk", "sender", "folder_id"
        )
    ]


def _mailboxes(person) -> list[dict]:
    """The shared mailboxes the person reaches, by name, each with their role and its unread."""
    held = sharing.roles(person)
    boxes = get_user_model().everyone.filter(pk__in=held, mailbox=True)
    return [
        sharing.described(box, held[box.pk], unseen(box.pk))
        for box in boxes.order_by("first_name", "pk")
    ]


def _listed(user, person) -> dict:
    return {
        "mailboxes": _mailboxes(person),
        # The person's role in the mailbox listed, none in their own.
        "role": sharing.role_in(person, user.pk) if user != person else None,
        "accounts": [describe(account) for account in user.mail_accounts.order_by("address")],
        "signature": shared_signature(user),
        "folders": [describe_folder(each) for each in _folders(user)],
        "images": _decided(user),
        "rules": _rules(user),
        "plain": sorted(settings.MAIL_PLAIN_HOSTS),
        "app_passwords": APP_PASSWORDS,
        # The providers an account signs in through, by the incoming server their accounts use.
        "providers": {each: signin.WAYS[each].imap[0] for each in signin.ready()},
    }


def _connected(user, fields: dict, secret: str, device: str) -> dict:
    try:
        with transaction.atomic():
            taken = set(user.mail_accounts.values_list("color", flat=True))
            made = Account.objects.create(
                owner=user,
                secret=sealed.seal("mail", secret),
                device=device,
                color=next(each for each in chain(TURNS, count(len(TURNS))) if each not in taken),
                default=not user.mail_accounts.filter(default=True).exists(),
                **fields,
            )
            notify(sync.CHANNEL)
    except IntegrityError:
        raise Refused(409, "account_exists") from None
    return describe(made)


@api("GET", "POST")
@sharing.boxed(sharing.OWN)
async def accounts(request):
    if request.method == "GET":
        return JsonResponse(await database(_listed)(request.user, request.person))
    data = body(request)
    fields = _fields(data)
    password = str(data.get("password", ""))
    if not password:
        raise Refused(400, "invalid_password")
    # The device the account is to the ActiveSync server, which its administrator sees and
    # may block or wipe.
    device = secrets.token_hex(16)
    await _checked(fields, imap.Login(fields["username"], password=password), device)
    made = await database(_connected)(request.user, fields, password, device)
    return JsonResponse(made, status=201)


@api("GET", "POST")
def mailboxes(request):
    """The shared mailboxes the user reaches; a new one, which they own, on POST."""
    if request.method == "GET":
        return JsonResponse({"mailboxes": _mailboxes(request.user)})
    box = sharing.made(request.user, body(request).get("name"))
    return JsonResponse(sharing.described(box, sharing.OWN, 0), status=201)


@api("PATCH", "DELETE", confirmed=("DELETE",))
def mailbox(request, pk):
    """Renames the shared mailbox, or removes it with its accounts and its mail."""
    box = sharing.mailbox(request.user, str(pk), sharing.OWN)
    if request.method == "DELETE":
        sharing.removed(box, request.user)
        return HttpResponse(status=204)
    sharing.renamed(box, body(request).get("name"))
    return JsonResponse(sharing.described(box, sharing.OWN, unseen(box.pk)))


@api("GET", "POST")
def mailbox_grants(request, pk):
    """Whom the shared mailbox is shared with, and as what; POST gives a colleague, a group or
    everyone a role in it, or changes the one they hold."""
    needs = sharing.READ if request.method == "GET" else sharing.OWN
    box = sharing.mailbox(request.user, str(pk), needs)
    if request.method == "POST":
        made = sharing.granted(box, request.user, body(request))
        return JsonResponse(sharing.describe_grant(made), status=201)
    found = box.mail_shared.select_related("user", "group").order_by("created_at", "pk")
    return JsonResponse({"grants": [sharing.describe_grant(each) for each in found]})


@api("DELETE")
def mailbox_grant(request, pk, grant):
    sharing.taken_back(sharing.mailbox(request.user, str(pk), sharing.OWN), grant)
    return HttpResponse(status=204)


def _mine(user, pk: int) -> Account:
    found = Account.objects.filter(pk=pk, owner=user).first()
    if found is None:
        raise Refused(404, "not_found")
    return found


def _removed(found: Account) -> None:
    """Removes the account; its mail stays where it was, and its folders that hold none go."""
    with transaction.atomic():
        node = Folder.objects.filter(account=found).first()
        found.delete()
        if node is not None:
            taking.pruned(node)
        if found.default:
            heirs = Account.objects.filter(owner_id=found.owner_id).order_by("created_at", "pk")
            if heir := heirs.first():
                heir.default = True
                heir.save(update_fields=["default"])
        notify(sync.CHANNEL)


def _looks(found: Account, data: dict) -> dict:
    """The account's names, signature and colour, whether new messages go from it and whether its
    mail shows in the shared folders. A label that only repeats the address is none."""
    if "name" in data:
        found.name = text(data, "name", 150)
    if "label" in data:
        label = text(data, "label", 200)
        found.label = "" if label.casefold() == found.address.casefold() else label
    if "signature" in data and data["signature"] is not None:
        _written_signature(data["signature"], found.owner)
    if "color" in data:
        color = data["color"]
        if not isinstance(color, int) or isinstance(color, bool) or not 0 <= color < 1000:
            raise Refused(400, "invalid_color")
        found.color = color
    if "default" in data and data["default"] is not True:
        raise Refused(400, "invalid_default")
    if "together" in data:
        if not isinstance(data["together"], bool):
            raise Refused(400, "invalid_together")
        found.together = data["together"]
    with transaction.atomic():
        if data.get("default"):
            others = Account.objects.filter(owner_id=found.owner_id, default=True)
            others.exclude(pk=found.pk).update(default=False)
            found.default = True
        found.save(update_fields=["name", "label", "color", "default", "together"])
        if "signature" in data:
            if data["signature"] is None:
                Signature.objects.filter(account=found).delete()
            else:
                _signed(found.owner, found, data["signature"])
    return describe(found)


def _written_signature(given, owner) -> tuple[str, list[str]]:
    """The signature as it is kept, empty where it shows nothing, and the images it shows."""
    if not isinstance(given, str) or len(given) > 100_000:
        raise Refused(400, "invalid_signature")
    html, images = safe.written(given, partial(shows_image, owner))
    return (html if images or sending.plain(html) else ""), images


def _signed(owner, account: Account | None, given) -> str:
    """Keeps the signature every account of the owner takes, or the account's own."""
    html, images = _written_signature(given, owner)
    with transaction.atomic():
        signature, _ = Signature.objects.update_or_create(
            owner=owner, account=account, defaults={"html": html}
        )
        signature.images.exclude(blob_id__in=images).delete()
        SignatureImage.objects.bulk_create(
            [SignatureImage(signature=signature, blob_id=sha256) for sha256 in images],
            ignore_conflicts=True,
        )
    return html


def shared_signature(user) -> str:
    found = Signature.objects.filter(owner=user, account=None).first()
    return found.html if found else ""


@api("PUT")
@sharing.boxed(sharing.OWN)
def signature(request):
    """The signature every account of the user takes where it has none of its own."""
    return JsonResponse({"signature": _signed(request.user, None, body(request).get("html"))})


def _changed(found: Account, fields: dict, secret: str) -> dict:
    where = ("protocol", "activesync_host", "imap_host", "username")
    moved = any(getattr(found, field) != fields[field] for field in where)
    for field, value in fields.items():
        setattr(found, field, value)
    found.secret = sealed.seal("mail", secret)
    found.state, found.error = Account.State.SYNCING, ""
    if moved:
        found.policy_key = found.folder_key = ""
    try:
        with transaction.atomic():
            if moved:
                found.sources.all().delete()
            found.save()
            notify(sync.CHANNEL)
    except IntegrityError:
        raise Refused(409, "account_exists") from None
    return describe(found)


@api("PATCH", "DELETE")
@sharing.boxed(sharing.OWN, of=sharing.ACCOUNT)
async def account(request, pk):
    found = await database(_mine)(request.user, pk)
    if request.method == "DELETE":
        await database(_removed)(found)
        return HttpResponse(status=204)
    data = body(request)
    if "address" not in data:
        return JsonResponse(await database(_looks)(found, data))
    fields = _fields(data)
    password = str(data.get("password", ""))
    if not password and found.login == Account.Login.PASSWORD:
        password = sealed.opened("mail", found.secret) or ""
    if not password:
        raise Refused(400, "invalid_password")
    await _checked(fields, imap.Login(fields["username"], password=password), found.device)
    signin.forget(found)
    return JsonResponse(await database(_changed)(found, fields, password))


def _provider(provider: str) -> str:
    if provider not in Provider.values:
        raise Refused(404, "not_found")
    return provider


def _return(request, provider: str) -> str:
    """The address the provider sends the user back to, as the installation is reached: what its
    administrator registers with the provider."""
    return request.build_absolute_uri(RETURN.format(provider=provider))


@api("POST")
@sharing.boxed(sharing.OWN)
async def oauth(request, provider):
    """The provider's page on which the user signs in to the account to connect, or to connect
    again; what the way back needs is kept in their session meanwhile."""
    provider = _provider(provider)
    hint = str(body(request).get("address", "")).strip()
    try:
        url, kept = await database(signin.started)(provider, _return(request, provider), hint)
    except imap.Failed as failed:
        raise Refused(409, failed.code) from None
    box = request.user.pk if request.user != request.person else None
    await request.session.aset("mail_oauth", {"provider": provider, "box": box, **kept})
    return JsonResponse({"url": url})


def _granted_fields(provider: str, granted: signin.Granted) -> dict:
    servers = {
        f"{kind}_{key}": value
        for kind, server in (("imap", granted.imap), ("smtp", granted.smtp))
        for key, value in zip(("host", "port", "security"), server, strict=True)
    }
    return {
        "address": granted.address,
        "username": granted.address,
        "login": provider,
        "protocol": Account.Protocol.IMAP,
        "activesync_host": "",
        **servers,
    }


def _granted(user, fields: dict, refresh: str) -> None:
    """Connects the account, or signs an account already connected in through OAuth from now on:
    its mail stays, and is taken further from where it was."""
    found = user.mail_accounts.filter(address=fields["address"]).first()
    if found is None:
        _connected(user, fields | {"name": user.get_full_name()}, refresh, "")
        return
    signin.forget(found)
    _changed(found, fields, refresh)


def _back(code: str = "") -> HttpResponseRedirect:
    return HttpResponseRedirect(f"/mail?oauth={code}" if code else "/mail")


async def returned(request, provider):
    """Where the provider sends the user back: the account is kept once its servers let it in
    with what the provider gave, and the user is back in their mail, told why where it was not."""
    if provider not in Provider.values:
        raise Http404
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponseRedirect("/")
    kept = await request.session.apop("mail_oauth", None)
    state = request.GET.get("state", "")
    if (
        not kept
        or kept["provider"] != provider
        or not secrets.compare_digest(kept["state"].encode(), state.encode())
    ):
        return _back("oauth_state")
    if request.GET.get("error") or not request.GET.get("code"):
        return _back("oauth_denied")
    if kept.get("box"):
        try:
            user = await database(sharing.mailbox)(user, str(kept["box"]), sharing.OWN)
        except Refused as refused:
            return _back(refused.error)
    code = request.GET["code"]
    trade = partial(signin.granted, provider, code, kept["verifier"], kept["redirect"])
    try:
        granted = await waited(trade)
        fields = _granted_fields(provider, granted)
        await _checked(fields, imap.Login(granted.address, token=granted.access))
        await database(_granted)(user, fields, granted.refresh)
    except imap.Failed as failed:
        return _back(failed.code)
    except Refused as refused:
        return _back(refused.error)
    return _back()


def _client(request, provider: str, found: Client | None) -> dict:
    return {
        "provider": provider,
        "redirect": _return(request, provider),
        "client_id": found.client_id if found else "",
        "hint": found.hint if found else "",
        "lost": found is not None and sealed.opened("oauth client", found.secret) is None,
        "expires": found.expires if found else None,
        "changed_at": found.changed_at if found else None,
    }


@api("GET")
def clients(request):
    """The installation's clients at the providers its accounts sign in through, for its
    administrator: never a secret, only how it ends."""
    administrator(request)
    kept = {found.provider: found for found in Client.objects.all()}
    return JsonResponse(
        {"clients": [_client(request, each, kept.get(each)) for each in Provider.values]}
    )


def _expires(data: dict) -> date | None:
    given = data.get("expires")
    if given in (None, ""):
        return None
    try:
        return date.fromisoformat(str(given))
    except ValueError:
        raise Refused(400, "invalid_expires") from None


def _client_kept(user, provider: str, client_id: str, secret: str, expires) -> Client:
    found, _ = Client.objects.update_or_create(
        provider=provider,
        defaults={
            "client_id": client_id,
            "secret": sealed.seal("oauth client", secret),
            "hint": secret[-4:],
            "expires": expires,
            "changed_by": user,
        },
    )
    return found


@api("PATCH", "DELETE")
async def client(request, provider):
    """Enters the installation's client at the provider, checked with the provider first, or
    removes it: accounts that sign in through it stop until it is entered again."""
    administrator(request)
    provider = _provider(provider)
    if request.method == "DELETE":
        await database(lambda: Client.objects.filter(provider=provider).delete())()
        await database(entries.wrote)(
            Kind.SETTING_CHANGED, request=request, setting="mail_client", provider=provider
        )
        return HttpResponse(status=204)
    data = body(request)
    client_id = text(data, "client_id", 255, required=True)
    expires = _expires(data)
    secret = str(data.get("secret", "")).strip()
    if not secret:
        try:
            _, secret = await database(signin.client)(provider)
        except imap.Failed:
            raise Refused(400, "invalid_secret") from None
    check = partial(signin.checked, provider, client_id, secret, _return(request, provider))
    try:
        await to_thread.run_sync(check, abandon_on_cancel=True)
    except imap.Failed as failed:
        raise Refused(422 if failed.code == "oauth_client" else 502, failed.code) from None
    found = await database(_client_kept)(request.user, provider, client_id, secret, expires)
    await database(entries.wrote)(
        Kind.SETTING_CHANGED, request=request, setting="mail_client", provider=provider, kept=True
    )
    return JsonResponse(_client(request, provider, found))


def describe_message(message: Message) -> dict:
    return {
        "id": message.pk,
        "folder": message.folder_id,
        "account": message.account_id,
        "accounts": message.accounts,
        "subject": message.subject,
        "sender": message.sender,
        "to": message.to,
        "date": message.date,
        "seen": message.seen,
        "flagged": message.flagged,
        "answered": message.answered,
        "snoozed_until": message.snoozed_until,
        "awaited_until": message.awaited_until,
        "unanswered": message.unanswered,
        "priority": message.priority,
        "attachments": message.attachments,
        "preview": message.preview,
        "kept": message.kept,
        "sealed": message.sealed,
    }


def _messages(user):
    """The user's messages, each with the accounts it came to, the first first."""
    came = (
        Arrival.objects.filter(message=OuterRef("pk"))
        .exclude(source__account=OuterRef("account"))
        .values("source__account")
        .distinct()
    )
    return Message.objects.filter(owner=user).annotate(
        others=ArraySubquery(came), kept=retention.mail_kept(user.pk)
    )


def _accounts(message: Message) -> Message:
    first = [message.account_id] if message.account_id else []
    message.accounts = [*first, *sorted(message.others)]
    return message


def listed(user, ids) -> dict[int, dict]:
    """The user's messages of the ids, as a list shows each, with the role of the folder each is
    in."""
    found = _messages(user).filter(pk__in=ids).select_related("folder")
    return {
        message.pk: describe_message(_accounts(message)) | {"role": message.folder.role}
        for message in found
    }


def _correspondent(role: str):
    """Whom the list names for a message, in Croatian order: whom it went to in the folders of
    what the user sends, who sent it elsewhere."""
    who = "to__0" if role in (Role.SENT, Role.DRAFTS) else "sender"
    named = Coalesce(
        NullIf(KT(f"{who}__name"), Value("")),
        KT(f"{who}__address"),
        Value(""),
        output_field=TextField(),
    )
    return Collate(named, "hr-x-icu")


def _page(request, found, role: str) -> tuple[list[Message], str | None]:
    """A page of the messages in the order `sort` and `descending` ask for, newest first among
    those it holds equal; `before` continues where the last page ended."""
    sort = request.GET.get("sort", "date")
    if sort not in SORTS:
        raise Refused(400, "invalid_sort")
    descending = request.GET.get("descending", "1") == "1"
    keys = [("placed", descending), ("id", descending)]
    if sort != "date":
        by = _correspondent(role) if sort == "correspondent" else F("priority")
        found = found.annotate(by=by)
        keys = [("by", descending), ("placed", True), ("id", True)]
    found = found.order_by(*(f"-{name}" if down else name for name, down in keys))
    if before := request.GET.get("before"):
        try:
            *ahead, moment, last = json.loads(before)
            ahead = [int(each) if sort == "priority" else str(each) for each in ahead]
            values = [*ahead, datetime.fromisoformat(moment), int(last)]
        except TypeError, ValueError:
            raise Refused(400, "invalid_before") from None
        if len(values) != len(keys):
            raise Refused(400, "invalid_before")
        after = Q()
        for at, (name, down) in reversed(list(enumerate(keys))):
            past = Q(**{f"{name}__{'lt' if down else 'gt'}": values[at]})
            after = past | (Q(**{name: values[at]}) & after) if after else past
        found = found.filter(after)
    page = list(found[: PAGE + 1])
    shown = page[:PAGE]
    after = None
    if len(page) > PAGE:
        last = shown[-1]
        given = [last.by] if sort != "date" else []
        after = json.dumps([*given, last.placed.isoformat(), last.pk])
    return [_accounts(message) for message in shown], after


WAITING = 5
FLAGGED_DAYS = 14


@api("GET")
@sharing.boxed()
def waiting(request):
    """The mail that waits on the user: unread in the inboxes from people they write to, and what
    they flagged of the last two weeks, newest first."""
    wrote = Correspondent.objects.filter(
        owner=request.user, written__gt=0, address=OuterRef("from_address")
    )
    found = (
        _messages(request.user)
        .exclude(_apart())
        .exclude(folder__role__in=(Role.TRASH, Role.JUNK, Role.SNOOZED))
        .annotate(from_address=Lower(KT("sender__address")))
        .filter(
            Q(folder__role=Role.INBOX, seen=False) & Exists(wrote)
            | Q(flagged=True, date__gte=timezone.now() - timedelta(days=FLAGGED_DAYS))
        )
        .select_related("folder")
    )
    shown = found.order_by("-date")[:WAITING]
    return JsonResponse(
        {
            "messages": [
                describe_message(_accounts(each)) | {"role": each.folder.role} for each in shown
            ],
            "count": found.count(),
        }
    )


def _marked(found):
    """Of the messages, those the user flagged, in whatever folder but Trash and Junk."""
    return found.filter(flagged=True).exclude(folder__role__in=(Role.TRASH, Role.JUNK))


def _folder_of(user, pk: int) -> Folder:
    folder = Folder.objects.filter(pk=pk, owner=user).first()
    if folder is None:
        raise Refused(404, "not_found")
    return folder


@api("GET")
@sharing.boxed(of=sharing.FOLDER)
def messages(request, pk):
    """A page of the folder's messages, or of those one account brought to it."""
    folder = _folder_of(request.user, pk)
    return _page_of(request, _messages(request.user).filter(folder_id=pk), folder.role)


@api("GET")
@sharing.boxed()
def flagged(request):
    """A page of the messages the user flagged, across their folders."""
    return _page_of(request, _marked(_messages(request.user)), "")


def _page_of(request, found, role: str) -> JsonResponse:
    found = _shown(found.exclude(reactions.ATTACHED), request.GET.get("account"))
    shown, after = _page(request, found, role)
    totals = found.aggregate(count=Count("pk"), unseen=Count("pk", filter=Q(seen=False)))
    held = opened.counted(request.user, shown)
    described = [describe_message(each) | {"opened": held.get(each.pk)} for each in shown]
    return JsonResponse({"messages": described, "before": after} | totals)


def _chosen(listed, where):
    """The messages chosen in a list: those it names, or every one the list shows, the read or the
    unread alone if it says so."""
    if not isinstance(where, dict):
        raise Refused(400, "invalid_where")
    account = where.get("account")
    found = _shown(listed.exclude(reactions.ATTACHED), None if account is None else str(account))
    if "messages" in where:
        named = where["messages"]
        if not isinstance(named, list) or not all(type(each) is int for each in named):
            raise Refused(400, "invalid_messages")
        found = found.filter(pk__in=named)
    if "seen" in where:
        if not isinstance(where["seen"], bool):
            raise Refused(400, "invalid_seen")
        found = found.filter(seen=where["seen"])
    return found


@api("POST")
@sharing.boxed(of=sharing.FOLDER)
def chosen(request, pk):
    """Does the action to the messages chosen in the folder's list. Taken out of Junk into the
    Inbox, their senders are blocked no more."""
    folder = _folder_of(request.user, pk)
    listed = Message.objects.filter(owner=request.user, folder_id=pk)
    return _acted_on(request, listed, folder.role == Role.JUNK)


@api("POST")
@sharing.boxed()
def flagged_chosen(request):
    """Does the action to the messages chosen in the list of those the user flagged."""
    return _acted_on(request, _marked(Message.objects.filter(owner=request.user)), False)


def _acted_on(request, listed, from_junk: bool) -> JsonResponse:
    """Does the action the registry names `mail.<action>` to the messages chosen, in PONISTRA
    only."""
    data = body(request)
    found = _chosen(listed, data.get("where", {}))
    action = ACTIONS.get(f"mail.{data.get('action')}")
    if action is None or action.target != "messages" or action.model:
        raise Refused(400, "invalid_action")
    parameters = {name: data[name] for name in ("to", "at", "by") if name in data}
    if why := unfit(action, parameters):
        raise Refused(400, why)
    doing = acting.Acting(request.user, request.person, from_junk)
    return JsonResponse({"changed": action.plan(doing, found, parameters)})


@api("POST")
@sharing.boxed()
async def message_action(request, name):
    """Runs the registry's action on the messages named: at once where our code does it, or, for
    one with a model, once the user lets these messages out to it, giving back what it proposes,
    which the user then moves as they accept it."""
    action = ACTIONS.get(name)
    if action is None or action.target != "messages":
        raise Refused(404, "unknown_action")
    data = body(request)
    target, parameters = data.get("target"), data.get("parameters", {})
    if not schema.validator(TARGETS["messages"]).is_valid(target):
        raise Refused(400, "invalid_target")
    if why := unfit(action, parameters):
        raise Refused(400, why)
    found = await database(_named)(request.user, target["messages"])
    doing = acting.Acting(request.user, request.person)
    if action.model is None:
        changed = await database(action.plan)(doing, found, parameters)
        return JsonResponse({"changed": changed})
    if data.get("consent") != "once":
        raise Refused(428, "consent_needed")
    consent = await _let_out(request.person, "once")
    messages = await database(list)(found.order_by("-date", "-pk"))
    prompt = await database(action.plan)(doing, messages, parameters)
    run = await database(ActionRun.objects.create)(
        user=request.person,
        action=action.id,
        target=target,
        parameters=parameters,
        consent=consent,
        consented_by=request.person,
    )
    try:
        answer = await runs.decided(run, action.model, prompt)
    except (model.Failed, Unavailable) as failed:
        raise Refused(502, failed.code) from None
    proposals = await database(acting.proposed)(doing, answer)
    return JsonResponse({"run": str(run.pk), "proposals": proposals})


def _named(user, ids: list[int]):
    """The user's messages by their ids, every one of them."""
    found = Message.objects.filter(owner=user, pk__in=ids).exclude(reactions.ATTACHED)
    if found.count() != len(ids):
        raise Refused(404, "not_found")
    return found


def loaded(user, pk: int) -> Message:
    found = _messages(user).select_related("folder", "raw").filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    return _accounts(found)


def listing(user, role: str, unseen: bool, since, account: int | None, limit: int) -> list[Message]:
    """The newest messages in the folders of the role, as the list of those folders shows them."""
    found = _messages(user).filter(folder__role=role).exclude(reactions.ATTACHED)
    found = _shown(found, None if account is None else str(account))
    if unseen:
        found = found.filter(seen=False)
    if since is not None:
        found = found.filter(date__gte=since)
    return [_accounts(each) for each in found.order_by("-date", "-id")[:limit]]


def describe_draft(draft: Draft) -> dict:
    return {
        "id": draft.pk,
        "way": draft.way,
        "text": draft.text,
        "by": draft.grant.client.name if draft.grant_id else None,
        "created_at": draft.created_at,
    }


@api("GET")
@sharing.boxed()
def drafts(request):
    """The replies outside agents drafted that wait for the user, the latest first, each with the
    message it answers."""
    found = (
        Draft.objects.filter(owner=request.user, message__in=_messages(request.user))
        .select_related("grant__client", "message")
        .order_by("-created_at", "-pk")
    )
    return JsonResponse(
        {
            "drafts": [
                describe_draft(each)
                | {
                    "message": {
                        "id": each.message_id,
                        "folder": each.message.folder_id,
                        "subject": each.message.subject,
                        "sender": each.message.sender,
                    }
                }
                for each in found
            ]
        }
    )


@api("DELETE")
@sharing.boxed(of=sharing.DRAFT)
def drafted(request, pk):
    """Drops a reply an agent drafted, unsent."""
    if not Draft.objects.filter(owner=request.user, pk=pk).delete()[0]:
        raise Refused(404, "not_found")
    return HttpResponse(status=204)


def describe_files(message: Message) -> list[dict]:
    return [
        {"part": each.part, "name": each.name, "type": each.type, "size": each.blob.size}
        for each in message.files.select_related("blob").filter(inline=False).order_by("pk")
    ]


def _parsed(message: Message):
    return mime.parsed(store.path_of(message.raw_id).read_bytes())


def _body(message: Message, parsed, images: bool) -> dict:
    parts = mime.described(parsed)
    inline = {
        each.cid: f"/api/mail/messages/{message.pk}/parts/{each.part}"
        for each in message.files.exclude(cid="")
    }
    if shown := parts.get("html"):
        data = mime.raw(parsed, shown["part"]) or b""
        markup = imap.decoded(data, shown["encoding"], shown["charset"])
        away = partial(fetching.served, message.pk) if images else None
        html, remote = safe.cleaned(markup, inline, away)
        return {"html": html, "text": None, "remote": remote}
    if shown := parts.get("plain"):
        data = mime.raw(parsed, shown["part"]) or b""
        text = imap.decoded(data, shown["encoding"], shown["charset"])
        return {"html": None, "text": text, "remote": False}
    return {"html": None, "text": "", "remote": False}


def _domain(message: Message) -> str:
    """The domain of the sender's address, which the user may trust with its images."""
    address = message.sender.get("address") or ""
    return address.rpartition("@")[2].lower() if "@" in address else ""


@api("GET", "PATCH")
@sharing.boxed(of=sharing.MESSAGE)
def message(request, pk):
    """The message to read; PATCH sets its flags."""
    found = loaded(request.user, pk)
    if request.method == "GET":
        domain = _domain(found)
        decided = request.user.mail_decided.filter(domain=domain).values_list("shown", flat=True)
        chosen = decided.first()
        parsed = _parsed(found)
        shown = _body(found, parsed, chosen is True or request.GET.get("images") == "1")
        shown["bulk"] = bool(mime.header(parsed, "List-Unsubscribe"))
        shown["autocrypt"] = mime.header(parsed, "Autocrypt") or None
        own = _own(request.user)
        shown["reactions"] = reactions.grouped(found, own)
        shown["reactable"] = reactions.offered(found, own, parsed)
        files = {"cc": found.cc, "reply_to": found.reply_to, "attachments": describe_files(found)}
        sender = {"domain": domain or None, "images": chosen}
        # A device keeping the mail for work without the network reads it unasked (D45).
        if request.GET.get("kept") != "1":
            opened.noted(found, request.person)
        seen = {"opened_by": opened.opened_by(request.user, found)}
        meeting = {"invitation": invitations.described(found, request.GET.get("zone", ""))}
        translated = {"language": translating.language_of(found), "translated": None}
        if (into := request.GET.get("into")) and (kept := translating.kept(found, into)):
            cut = translating.body(shown["html"], shown["text"])
            shown["html" if cut.html else "text"] = translating.put_back(cut, kept.blocks)
            translated |= {"translated": into, "subject": kept.subject}
        return JsonResponse(
            describe_message(found) | files | shown | sender | seen | meeting | translated
        )
    data = body(request)
    given = {name: data[name] for name in FLAGS if name in data}
    if not given or not all(isinstance(on, bool) for on in given.values()):
        raise Refused(400, "invalid_flags")
    for name, on in given.items():
        setattr(found, name, on)
    found.save(update_fields=list(given))
    return JsonResponse(describe_message(found))


@api("GET", "PATCH")
@sharing.boxed(sharing.OWN)
def setting(request):
    """The installation's mail: whether the sender of a message sees which of their colleagues
    opened it."""
    administrator(request)
    if request.method == "PATCH":
        on = body(request).get("opened")
        if not isinstance(on, bool):
            raise Refused(400, "invalid_opened")
        found = opened.change(request.user, on)
        entries.wrote(Kind.SETTING_CHANGED, request=request, setting="mail_opened", enabled=on)
        return JsonResponse(opened.describe_setting(found))
    return JsonResponse(opened.describe_setting(opened.setting()))


@api("POST")
@sharing.boxed()
def images(request):
    """Shows the images of the domain's senders, or keeps them out, without asking."""
    data = body(request)
    domain = str(data.get("domain", "")).strip().lower()
    if len(domain) > 253 or not DOMAIN.fullmatch(domain):
        raise Refused(400, "invalid_domain")
    shown = data.get("shown")
    if not isinstance(shown, bool):
        raise Refused(400, "invalid_shown")
    Decided.objects.update_or_create(owner=request.user, domain=domain, defaults={"shown": shown})
    return JsonResponse({"images": _decided(request.user)}, status=201)


@api("DELETE")
@sharing.boxed()
def undecided(request, domain):
    """Asks again before showing the images of the domain's senders."""
    request.user.mail_decided.filter(domain=domain.lower()).delete()
    return HttpResponse(status=204)


@api("DELETE")
@sharing.boxed(of=sharing.RULE)
def rule(request, pk):
    """Lets the sender's mail arrive where it comes again; what the rule moved stays."""
    request.user.mail_rules.filter(pk=pk).delete()
    return HttpResponse(status=204)


def _file(message: Message, number: str) -> Attachment:
    found = message.files.select_related("blob").filter(part=number).first()
    if found is None:
        raise Refused(404, "not_found")
    return found


@api("GET")
@sharing.boxed(of=sharing.MESSAGE)
def part(request, pk, number):
    """A file the message carries: an image its HTML shows, or a file to save."""
    found = _file(loaded(request.user, pk), number)
    name = found.name or "attachment"
    response = serve_blob(request, found.blob, name)
    # Shown only where the bytes are the image the message says they are.
    shown = found.type in safe.SHOWN and found.blob.media_type == found.type
    if response.status_code != 304:
        response["Content-Type"] = found.type if shown else "application/octet-stream"
        response["Content-Disposition"] = content_disposition_header(not shown, name)
    return response


def _kept_image(message: Message, key: str) -> Fetched | None:
    return message.fetched.select_related("blob").filter(key=key).first()


def _keep_image(message: Message, key: str, image: tuple[bytes, str] | None) -> Fetched:
    blob = store.put(io.BytesIO(image[0])) if image else None
    Fetched.objects.bulk_create(
        [Fetched(message=message, key=key, blob=blob)], ignore_conflicts=True
    )
    return message.fetched.select_related("blob").get(key=key)


@api("GET")
@sharing.boxed(of=sharing.MESSAGE)
async def fetched(request, pk, token):
    """An image from elsewhere that the message's HTML shows, fetched by PONISTRA the first time
    it is asked for and kept with the message."""
    address = fetching.address(pk, token)
    if address is None:
        raise Refused(404, "not_found")
    found = await database(loaded)(request.user, pk)
    key = fetching.key(address)
    kept = await database(_kept_image)(found, key)
    if kept is None:
        try:
            image = await fetching.fetched(address)
        except fetching.Unreachable:
            raise Refused(502, "unreachable") from None
        kept = await database(_keep_image)(found, key, image)
    if kept.blob is None:
        raise Refused(404, "not_found")
    response = serve_blob(request, kept.blob, "image")
    if response.status_code != 304:
        response["Content-Disposition"] = content_disposition_header(False, "image")
    return response


@api("POST")
@sharing.boxed(of=sharing.MESSAGE)
def blob(request, pk, number):
    """A file the message carries, as one of PONISTRA's files for the user to make a document of."""
    found = _file(loaded(request.user, pk), number)
    return JsonResponse(describe_blob(found.blob) | {"name": found.name}, status=201)


@api("GET")
@sharing.boxed(of=sharing.MESSAGE)
def original(request, pk):
    """The message as it came, to save."""
    found = loaded(request.user, pk)
    response = HttpResponse(taking.whole(found), content_type="message/rfc822")
    name = f"{found.subject.strip() or 'message'}.eml"
    response["Content-Disposition"] = content_disposition_header(True, name)
    return response


def _cut(message: Message) -> translating.Body:
    shown = _body(message, _parsed(message), False)
    return translating.body(shown["html"], shown["text"])


async def _let_out(user, given) -> ActionRun.Consented:
    """How the user lets their mail out to the model to be translated: this once, or for all of
    it; none yet asks them."""
    if given not in (None, "once"):
        raise Refused(400, "invalid_consent")
    if not await database(installation.enabled)():
        raise Refused(409, "ai_off")
    if given == "once":
        return ActionRun.Consented.ONCE
    if await Reading.objects.filter(user=user, automatic=True).aexists():
        return ActionRun.Consented.USER
    raise Refused(428, "consent_needed")


def _untranslated(untranslated: translating.Untranslated) -> Refused:
    status = 413 if untranslated.code == "message_too_long" else 502
    return Refused(status, untranslated.code)


@api("POST")
@sharing.boxed(of=sharing.MESSAGE)
async def translation(request, pk):
    """The message translated into the language asked for, kept once for each language: by the
    model, once the installation's AI is on and the user lets the message out to it, this once
    or for all of their mail (D35)."""
    data = body(request)
    into = data.get("language")
    if into not in detection.KNOWN:
        raise Refused(400, "invalid_language")
    found = await database(loaded)(request.user, pk)
    if await database(translating.kept)(found, into) is None:
        consent = await _let_out(request.person, data.get("consent"))
        cut = await database(_cut)(found)
        try:
            await translating.translate(request.person, found, cut, into, consent)
        except translating.Untranslated as untranslated:
            raise _untranslated(untranslated) from None
    return JsonResponse({"translated": into})


@api("POST")
@sharing.boxed(of=sharing.MESSAGE)
async def translated_reply(request, pk):
    """The reply the user wrote in their language, in the language of the message it answers,
    which they do not read; and what they wrote, which the message keeps once sent (D35-2)."""
    data = body(request)
    mine = data.get("language")
    if mine not in detection.KNOWN:
        raise Refused(400, "invalid_language")
    subject = text(data, "subject", 998)
    written = data.get("html", "")
    if not isinstance(written, str) or len(written) > 1_000_000:
        raise Refused(400, "invalid_html")
    heading = _heading(data)
    found = await database(loaded)(request.user, pk)
    into = translating.language_of(found)
    if into is None or into == mine:
        raise Refused(409, "unknown_language")
    consent = await _let_out(request.person, data.get("consent"))
    try:
        translated = await translating.reply(
            request.person, found, written, subject, heading, mine, into, consent
        )
    except translating.Untranslated as untranslated:
        raise _untranslated(untranslated) from None
    return JsonResponse(translated)


def quoted_text(message: Message) -> str:
    """The text a reply quotes or a forward carries: the plain body, else what the HTML reads."""
    parsed = _parsed(message)
    parts = mime.described(parsed)
    if shown := parts.get("plain"):
        data = mime.raw(parsed, shown["part"]) or b""
        return imap.decoded(data, shown["encoding"], shown["charset"])
    if shown := parts.get("html"):
        data = mime.raw(parsed, shown["part"]) or b""
        return imap.plain(imap.decoded(data, shown["encoding"], shown["charset"]))
    return ""


def shows_image(user, sha256: str) -> bool:
    """Whether the image is one the user put in a message they write or in a signature: in a
    shared mailbox's, one that someone writing from it uploaded."""
    uploaded = Q(user=user)
    if user.mailbox:
        uploaded = Q(user__in=sharing.writers(user))
    return Blob.objects.filter(pk=sha256, media_type__in=safe.SHOWN).exists() and (
        SignatureImage.objects.filter(signature__owner=user, blob_id=sha256).exists()
        or Upload.objects.filter(uploaded, blob_id=sha256).exists()
        or UnsentFile.objects.filter(unsent__owner=user, blob_id=sha256).exists()
    )


INLINE = re.compile(r"/api/mail/inline/([0-9a-f]{64})")


@api("GET")
def image(request, sha256):
    boxes = get_user_model().everyone.filter(pk__in=sharing.roles(request.user), mailbox=True)
    if not any(shows_image(each, sha256) for each in [request.user, *boxes]):
        raise Refused(404, "not_found")
    blob = Blob.objects.get(pk=sha256)
    return serve_blob(request, blob, f"{sha256[:12]}.{store.IMAGES[blob.media_type]}")


def _own(user) -> set[str]:
    return {each.lower() for each in user.mail_accounts.values_list("address", flat=True)}


def _reacting(user, pk: int, data: dict) -> dict:
    """The reaction the user gives the message, from the account it came to, to everyone it
    went to as a reply to all goes; `said` is the user's words for a client that shows no
    reactions."""
    emoji = data.get("emoji")
    if not emoji or qualified(emoji) != emoji:
        raise Refused(400, "invalid_emoji")
    said = text(data, "said", 200, required=True)
    found = loaded(user, pk)
    own = _own(user)
    if not reactions.offered(found, own, _parsed(found)):
        raise Refused(400, "not_reactable")
    if reactions.mine(found, own) >= reactions.MOST:
        raise Refused(400, "too_many_reactions")
    if found.account is None:
        raise Refused(400, "invalid_account")
    people = []
    for each in sending.recipients(found, sending.ALL, own):
        people.append([])
        for person in each:
            try:
                people[-1].append(sending.address(person.get("name", ""), person["address"]))
            except sending.Invalid, KeyError:
                continue
    if not any(people):
        raise Refused(400, "no_recipients")
    return {
        "account": found.account,
        "people": people,
        "found": found,
        "emoji": emoji,
        "said": said,
    }


@api("POST")
@sharing.boxed(of=sharing.MESSAGE)
async def reaction(request, pk):
    """Reacts to the message with an emoji, sent as a reply all of its people read, and kept in
    the user's Sent folder; the message's reactions then."""
    given = await database(_reacting)(request.user, pk, body(request))
    account, found = given["account"], given["found"]
    message = sending.reacted(account, *given["people"], found, given["emoji"], given["said"])
    try:
        await sending.delivered(account, message)
    except imap.Failed as failed:
        raise Refused(502, failed.code) from None
    await database(sending.recorded)(account, message, None)

    def shown():
        return {"reactions": reactions.grouped(found, _own(request.user))}

    return JsonResponse(await database(shown)())


@api("GET")
@sharing.boxed(of=sharing.MESSAGE)
def draft(request, pk):
    """A reply to the message, a reply to all or its forward as the user starts writing it: from
    the account it came to, to whom, and the files a forward carries; the message itself is quoted
    or carried as it is sent."""
    way = request.GET.get("as")
    if way not in sending.WAYS:
        raise Refused(400, "invalid_as")
    found = loaded(request.user, pk)
    to, cc = sending.recipients(found, way, _own(request.user))
    default = request.user.mail_accounts.filter(default=True).values_list("pk", flat=True).first()
    return JsonResponse(
        {
            "account": found.account_id or default,
            "to": [_person(each) for each in to if each.get("address")],
            "cc": [_person(each) for each in cc if each.get("address")],
            "unnamed": [
                {"name": name, "address": each["address"]}
                for each in [*to, *cc]
                if (name := taking.common(each["address"]))
            ],
            "subject": sending.subject(found.subject, way),
            "attachments": describe_files(found) if way == sending.FORWARD else [],
        }
    )


def _person(person: dict) -> dict:
    return {"name": person.get("name", ""), "address": person["address"]}


def _people(data: dict, name: str) -> list[Address]:
    given = data.get(name, [])
    if not isinstance(given, list) or len(given) > 1000:
        raise Refused(400, "invalid_recipient")
    found = []
    for each in given:
        person = each if isinstance(each, dict) else {}
        named, address = person.get("name", ""), person.get("address")
        if not isinstance(named, str) or not isinstance(address, str) or len(named) > 998:
            raise Refused(400, "invalid_recipient")
        try:
            found.append(sending.address(named, address))
        except sending.Invalid:
            raise Refused(400, "invalid_recipient") from None
    return found


def _files(data: dict) -> list[tuple[str, str, bytes]]:
    """The files the user added, uploaded to PONISTRA's store before the message is sent."""
    given = data.get("files", [])
    if not isinstance(given, list):
        raise Refused(400, "invalid_files")
    found = []
    for each in given:
        sha256 = each.get("sha256") if isinstance(each, dict) else None
        name = each.get("name") if isinstance(each, dict) else None
        if not isinstance(sha256, str) or not isinstance(name, str) or not 0 < len(name) <= 255:
            raise Refused(400, "invalid_files")
        blob = Blob.objects.filter(sha256=sha256).first()
        if blob is None:
            raise Refused(400, "invalid_files")
        found.append((name, blob.media_type, store.path_of(sha256).read_bytes()))
    return found


def _sending(user, data: dict, sharing: bool = True) -> dict:
    """What the message is made of, each piece the user's own: the account it goes from, the
    message it answers or forwards and the files it carries."""
    pk = data.get("account")
    if not isinstance(pk, int) or isinstance(pk, bool):
        raise Refused(400, "invalid_account")
    account = _mine(user, pk)
    way = data.get("as")
    answered = None
    if way is not None:
        given = data.get("original")
        if way not in sending.WAYS or not isinstance(given, int) or isinstance(given, bool):
            raise Refused(400, "invalid_as")
        answered = loaded(user, given)
    elif data.get("original") is not None:
        raise Refused(400, "invalid_as")
    carried = data.get("carried", [])
    if not isinstance(carried, list) or (carried and way != sending.FORWARD):
        raise Refused(400, "invalid_carried")
    if answered is not None:
        known = {each.part: each for each in answered.files.filter(inline=False)}
        if any(not isinstance(number, str) or number not in known for number in carried):
            raise Refused(400, "invalid_carried")
        carried = [
            (each.name or "attachment", each.type, store.path_of(each.blob_id).read_bytes())
            for each in (known[number] for number in carried)
        ]
    to, cc, bcc = (_people(data, name) for name in ("to", "cc", "bcc"))
    if not to and not cc and not bcc:
        raise Refused(400, "no_recipients")
    title = text(data, "subject", 998)
    written = data.get("html", "")
    if not isinstance(written, str) or len(written) > 1_000_000:
        raise Refused(400, "invalid_html")
    own, images = safe.written(written, partial(shows_image, user))
    related = []
    for sha256 in images:
        cid = f"{sha256[:24]}@ponistra"
        own = own.replace(f'"/api/mail/inline/{sha256}"', f'"cid:{cid}"')
        media_type = Blob.objects.get(pk=sha256).media_type
        related.append((cid, media_type, store.path_of(sha256).read_bytes()))
    heading = _heading(data)
    if heading and answered is None:
        raise Refused(400, "invalid_heading")
    forward = way == sending.FORWARD
    quote = plain = None
    if answered is not None:
        quote, plain, carried_images = _quoted(answered, data.get("quoted"))
        related += carried_images
    files = [*carried, *_files(data)]
    source = _source(user, data, None if forward else answered)
    awaited = _awaited(data)
    addresses = [each.addr_spec for each in (*to, *cc, *bcc)]
    if sharing:
        # Last, as what it gives stands from here until the mail fails to leave.
        shared = mailed.shared(user, mailed.given(data), addresses)
        own += shared.markup
    else:
        mailed.checked(user, mailed.given(data), addresses)
        shared = None
    return {
        "account": account,
        "answered": answered if not forward else None,
        "people": (to, cc, bcc),
        "subject": title,
        "text": sending.alternative(own, heading, plain, forward),
        "markup": sending.page(own, heading, quote, forward),
        "related": related,
        "files": files,
        "shared": shared,
        "source": source,
        "awaited": awaited,
    }


def _heading(data: dict) -> list[str]:
    heading = data.get("heading", [])
    if (
        not isinstance(heading, list)
        or len(heading) > 20
        or any(not isinstance(line, str) or len(line) > 1000 for line in heading)
    ):
        raise Refused(400, "invalid_heading")
    return heading


def _source(user, data: dict, answered: Message | None) -> dict | None:
    """What the user wrote in their language before the reply was translated, by its blocks, as
    the translation gave it (D35-2)."""
    given = data.get("source")
    if given is None:
        return None
    if not isinstance(given, dict) or answered is None:
        raise Refused(400, "invalid_reply_source")
    blocks, subject, run = given.get("blocks"), given.get("subject"), given.get("run")
    if (
        given.get("language") not in detection.KNOWN
        or not isinstance(subject, str)
        or len(subject) > 998
        or not isinstance(blocks, dict)
        or len(blocks) > 5000
        or any(not isinstance(each, str) for each in blocks.values())
        or sum(len(each) for each in blocks.values()) > translating.LONGEST
        or not isinstance(run, str)
        or not ActionRun.objects.filter(pk=_uuid(run), user=user, action=translating.REPLY).exists()
    ):
        raise Refused(400, "invalid_reply_source")
    return given


def _uuid(given: str) -> UUID | None:
    try:
        return UUID(given)
    except ValueError:
        return None


def _quoted(message: Message, opened=None) -> tuple[str, str, list[tuple[str, str, bytes]]]:
    """A message as a reply quotes it or a forward carries it: its HTML, or its text drawn as it
    reads, its text, and the images its HTML shows. An encrypted message's text is what the
    browser that opened it gives (`opened`), as the server cannot read it."""
    if message.sealed == Sealed.ENCRYPTED:
        if opened is not None and (not isinstance(opened, str) or len(opened) > 1_000_000):
            raise Refused(400, "invalid_quoted")
        plain = opened or ""
        return f'<div style="white-space:pre-wrap">{escape(plain)}</div>', plain, []
    parsed = _parsed(message)
    shown = mime.described(parsed).get("html")
    if shown is None:
        plain = quoted_text(message)
        return f'<div style="white-space:pre-wrap">{escape(plain)}</div>', plain, []
    inline = list(message.files.exclude(cid=""))
    data = mime.raw(parsed, shown["part"]) or b""
    markup = imap.decoded(data, shown["encoding"], shown["charset"])
    images = [(each.cid, each.type, store.path_of(each.blob_id).read_bytes()) for each in inline]
    return safe.carried(markup, [each.cid for each in inline]), quoted_text(message), images


def _directories(user) -> list[Account]:
    return list(user.mail_accounts.filter(protocol=Account.Protocol.ACTIVESYNC).order_by("address"))


def _searched(account: Account, typed: str) -> list[dict] | None:
    login, _ = signin.login(account)
    with activesync_sync.session(account, login.password) as client:
        return directory.searched(client, typed, correspondents.MOST)


def _colleagues(user, typed: str) -> list[dict]:
    found = contacts.colleagues(user, typed)[: correspondents.MOST]
    return [{"name": each.get_full_name(), "address": each.email} for each in found]


@api("GET")
@sharing.boxed()
async def people(request):
    """Whom the user may be writing to as they type: their contacts, then their colleagues in
    the installation, then the people of their mail, whom they wrote to most first, then those the
    directories of their organisations find; and the accounts whose directory did not answer."""
    typed = request.GET.get("q", "").strip()[:200]
    if not typed:
        return JsonResponse({"people": [], "unanswered": []})
    found = await database(contacts.addresses)(request.user, typed, correspondents.MOST)
    found += await database(_colleagues)(request.user, typed)
    found += await database(correspondents.matching)(request.user, typed)
    unanswered = []
    for account in await database(_directories)(request.user):
        try:
            given = await waited(partial(_searched, account, typed))
        except imap.Failed:
            given = None
        if given is None:
            unanswered.append(account.label or account.address)
        else:
            found += [{"name": each["name"], "address": each["address"]} for each in given]
    known, listed = set(), []
    for each in found:
        if (address := each["address"].lower()) not in known:
            known.add(address)
            listed.append(each)
    return JsonResponse({"people": listed, "unanswered": unanswered})


@api("GET")
@sharing.boxed()
def sender(request):
    """The account a new message to the address goes from: the one the user last wrote to them
    from, else the one they last wrote to; none where the mail knows neither."""
    return JsonResponse({"account": _last_from(request.user, request.GET.get("to", ""))})


def _last_from(user, address: str) -> int | None:
    found = (
        Correspondent.objects.filter(owner=user, address=address.strip().lower())
        .values_list("sent_from", "reached")
        .first()
    )
    return found and (found[0] or found[1])


@api("POST")
@sharing.boxed(of=sharing.SENT_FROM)
async def send(request):
    """Sends what the user wrote from the account they chose, and keeps it in their Sent folder:
    a reply or forward from the account the message came to unless they chose another."""
    data = body(request)
    if data.get("awaited") is not None:
        acting.ahead(data["awaited"])
    if await database(_queued_before)(request.user, data) is True:
        return JsonResponse({"refused": [], "kept": True})
    return JsonResponse(await sent(request.user, data))


async def _withdrawn(shared: mailed.Shared | None) -> None:
    if shared is not None:
        await database(mailed.withdrawn)(shared)


async def sent(user, data: dict) -> dict:
    sealed = data.get("sealed")
    if sealed is not None and mailed.given(data):
        raise Refused(400, "sealed_shared")
    seal = None if sealed is None else await database(secured.sealed_given)(sealed)
    given = await database(_sending)(user, data, sharing=seal is None)
    key = _queued(data)
    try:
        message = sending.composed(
            given["account"],
            *given["people"],
            given["subject"],
            given["text"],
            given["answered"],
            given["files"],
            markup=given["markup"],
            related=given["related"],
        )
        if key is not None:
            del message["Message-ID"]
            message["Message-ID"] = _queued_id(given["account"], key)
        if seal is not None:
            sealing.seal_into(message, seal)
        refused, kept = await sending.delivered(given["account"], message)
    except imap.Failed as failed:
        await _withdrawn(given["shared"])
        raise Refused(502, failed.code) from None
    except BaseException:
        await _withdrawn(given["shared"])
        raise
    # First of all: once it has left, nothing that goes wrong below may offer to send it again.
    left = [Q(pk=unsent)] if type(unsent := data.get("unsent")) is int else []
    if key is not None:
        left.append(Q(written__queued=key))
    if left:
        await database(Unsent.objects.filter(reduce(or_, left), owner=user).delete)()
    kept_as = await database(sending.recorded)(given["account"], message, given["answered"])
    if given["awaited"] is not None and given["awaited"] > timezone.now():
        await database(Message.objects.filter(pk=kept_as.pk).update)(awaited_until=given["awaited"])
    if given["source"] is not None:
        await database(translating.keep_written)(kept_as, given["answered"], given["source"])
    if given["answered"] is not None:
        await database(Draft.objects.filter(owner=user, message=given["answered"]).delete)()
    return {"refused": refused, "kept": kept}


def _queued(data: dict) -> str | None:
    """The key a device that wrote the message without the network gave it (D45), which it asks
    again with until it hears what became of it."""
    key = data.get("queued")
    if key is None:
        return None
    try:
        return str(UUID(key))
    except AttributeError, TypeError, ValueError:
        raise Refused(400, "invalid_queued") from None


def _queued_id(account: Account, key: str) -> str:
    """The Message-ID of a message written without the network, by which a second ask finds it
    sent once the first one's answer was lost."""
    return f"<{key}@{account.address.rpartition('@')[2]}>"


def _queued_before(user, data: dict) -> Unsent | bool:
    """What an earlier ask with the same key made: the message still unsent or waiting, True for
    one already sent, False where there was none."""
    if (key := _queued(data)) is None:
        return False
    if found := Unsent.objects.filter(owner=user, written__queued=key).first():
        return found
    pk = data.get("account")
    account = Account.objects.filter(owner=user, pk=pk).first() if type(pk) is int else None
    if account is None:
        return False
    return Message.objects.filter(owner=user, message_id=_queued_id(account, key)).exists()


def _written(user, data: dict) -> tuple[Account, dict]:
    """The composer's fields as the user left them, each checked as sending checks it, with no
    recipient needed yet."""
    pk = data.get("account")
    if not isinstance(pk, int) or isinstance(pk, bool):
        raise Refused(400, "invalid_account")
    account = _mine(user, pk)
    people = {}
    for name in ("to", "cc", "bcc"):
        _people(data, name)
        people[name] = [
            {"name": each.get("name", ""), "address": each["address"]}
            for each in data.get(name, [])
        ]
    html = data.get("html", "")
    if not isinstance(html, str) or len(html) > 1_000_000:
        raise Refused(400, "invalid_html")
    _files(data)
    files = [
        {"sha256": each["sha256"], "name": each["name"], "size": each.get("size", 0)}
        for each in data.get("files", [])
    ]
    if any(type(each["size"]) is not int for each in files):
        raise Refused(400, "invalid_files")
    written = {**people, "subject": text(data, "subject", 998), "html": html, "files": files}
    if (key := _queued(data)) is not None:
        written["queued"] = key
    if shared := mailed.given(data):
        written["shared"] = shared
    if _awaited(data) is not None:
        written["awaited"] = data["awaited"]
    if (sealed := data.get("sealed")) is not None:
        if shared:
            raise Refused(400, "sealed_shared")
        secured.sealed_given(sealed)
        written["sealed"] = {
            name: sealed[name]
            for name in ("kind", "how", "micalg", "entity", "data")
            if name in sealed
        }
    if (way := data.get("as")) is not None:
        original, carried, heading = (
            data.get("original"),
            data.get("carried", []),
            data.get("heading", []),
        )
        if way not in sending.WAYS or type(original) is not int:
            raise Refused(400, "invalid_as")
        known = set(
            loaded(user, original).files.filter(inline=False).values_list("part", flat=True)
        )
        if not isinstance(carried, list) or any(each not in known for each in carried):
            raise Refused(400, "invalid_carried")
        if not isinstance(heading, list) or not all(isinstance(line, str) for line in heading):
            raise Refused(400, "invalid_heading")
        written |= {"as": way, "original": original, "carried": carried, "heading": heading[:20]}
        if (quoted := data.get("quoted")) is not None:
            if not isinstance(quoted, str) or len(quoted) > 1_000_000:
                raise Refused(400, "invalid_quoted")
            written["quoted"] = quoted
    return account, written


def described_unsent(unsent: Unsent) -> dict:
    return {
        "id": unsent.pk,
        "account": unsent.account_id,
        "updated_at": unsent.updated_at,
        "send_at": unsent.send_at,
        "sending": unsent.sending,
        "failed": unsent.failed,
        **unsent.written,
    }


def _agent_sends_from(user, chosen: int | None, address: str) -> Account:
    if chosen is not None:
        return _mine(user, chosen)
    last = Account.objects.filter(owner=user, pk=_last_from(user, address)).first()
    found = last or Account.objects.filter(owner=user).order_by("-default", "pk").first()
    if found is None:
        raise Refused(404, "not_found")
    return found


def _letter(account: Account, written: str) -> str:
    """The text as the composer would open it: a paragraph a line, the account's signature below."""
    lines = written.rstrip("\n").split("\n")
    html = "".join(f"<p>{escape(line)}</p>" for line in lines)
    signature = _signature_of(account)
    return f'{html}<p></p><div data-signature="">{signature}</div>' if signature else html


def agent_mail(grant, people: dict, subject: str, written: str, chosen, replaces) -> Unsent:
    """A new message an outside agent drafted, among those the user began and has not sent."""
    user = grant.user
    account = _agent_sends_from(user, chosen, people["to"][0]["address"])
    data = {**people, "account": account.pk, "subject": subject, "html": _letter(account, written)}
    _, kept = _written(user, data)
    kept["agent"] = grant.pk
    with transaction.atomic():
        if replaces is None:
            return Unsent.objects.create(owner=user, account=account, written=kept)
        # A save from the composer drops the mark: what the user touched is theirs.
        found = (
            Unsent.objects.select_for_update()
            .filter(owner=user, pk=replaces, send_at=None, written__agent=grant.pk)
            .first()
        )
        if found is None:
            raise Refused(404, "not_found")
        found.account, found.written = account, kept
        found.save()
        return found


def _held(unsent: Unsent) -> None:
    """Keeps the bytes of the files and images the message carries for as long as it waits, past
    the hour that protects an upload nothing refers to yet."""
    written = unsent.written
    wanted = {each["sha256"] for each in written.get("files", [])}
    wanted |= set(INLINE.findall(written.get("html", "")))
    wanted |= secured.sealed_blobs(written.get("sealed"))
    existing = set(Blob.objects.filter(pk__in=wanted).values_list("pk", flat=True))
    unsent.held.exclude(blob_id__in=existing).delete()
    UnsentFile.objects.bulk_create(
        (UnsentFile(unsent=unsent, blob_id=sha256) for sha256 in existing),
        ignore_conflicts=True,
    )


def _waiting_one(user, pk: int) -> Unsent:
    """The message of the user's, unless it is leaving this moment and can no longer be changed."""
    found = Unsent.objects.select_for_update().filter(owner=user, pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    if found.sending:
        raise Refused(409, "mail_sending")
    return found


@api("GET", "POST")
@sharing.boxed(of=sharing.SENT_FROM)
def unsent(request):
    """The messages the user began and has not sent, the latest first; or one more of them."""
    if request.method == "POST":
        data = body(request)
        before = _queued_before(request.user, data)
        if before is True:
            return JsonResponse({"queued": data["queued"], "sent": True})
        account, written = _written(request.user, data)
        with transaction.atomic():
            if isinstance(before, Unsent):
                found = _waiting_one(request.user, before.pk)
                if found.send_at is not None:
                    return JsonResponse(described_unsent(found))
                found.account, found.written = account, written
                found.save()
                _held(found)
                return JsonResponse(described_unsent(found))
            made = Unsent.objects.create(owner=request.user, account=account, written=written)
            _held(made)
        return JsonResponse(described_unsent(made), status=201)
    found = Unsent.objects.filter(owner=request.user, send_at=None).order_by("-updated_at")
    return JsonResponse({"unsent": [described_unsent(each) for each in found]})


@api("GET", "PUT", "DELETE")
@sharing.boxed(of=sharing.UNSENT)
@transaction.atomic
def unsent_one(request, pk):
    if request.method == "GET":
        found = Unsent.objects.filter(owner=request.user, pk=pk).first()
        if found is None:
            raise Refused(404, "not_found")
        return JsonResponse(described_unsent(found))
    found = _waiting_one(request.user, pk)
    if request.method == "DELETE":
        found.delete()
        return JsonResponse({})
    found.account, found.written = _written(request.user, body(request))
    found.save()
    _held(found)
    return JsonResponse(described_unsent(found))


def _awaited(data: dict) -> datetime | None:
    return None if data.get("awaited") is None else acting.moment(data["awaited"])


def _scheduled(user, data: dict) -> Unsent:
    """The message as it will leave at the moment asked for, checked now as sending checks it, so
    that what cannot be sent is refused while the user is still there."""
    at = acting.moment(data.get("at"))
    if (awaited := _sending(user, data, sharing=False)["awaited"]) is not None and awaited <= at:
        raise Refused(400, "mail_awaited_before_sending")
    account, written = _written(user, data)
    if (source := data.get("source")) is not None:
        written["source"] = source
    with transaction.atomic():
        pk = data.get("unsent")
        found = _waiting_one(user, pk) if type(pk) is int else Unsent(owner=user)
        found.account, found.written, found.send_at, found.failed = account, written, at, ""
        found.save()
        _held(found)
        notify(sending.LATER)
    return found


def described_away(found: Away) -> dict:
    return {
        "starts_at": found.starts_at,
        "ends_at": found.ends_at,
        "text_hr": found.text_hr,
        "text_en": found.text_en,
        "failed": found.failed,
    }


def _kept_away(user, data: dict) -> Away:
    starts, ends = acting.moment(data.get("starts_at")), acting.ahead(data.get("ends_at"))
    if ends <= starts:
        raise Refused(400, "invalid_at")
    wording = text(data, "text_hr", 10_000).strip(), text(data, "text_en", 10_000).strip()
    if not any(wording):
        raise Refused(400, "mail_away_empty")
    with transaction.atomic():
        found = Away.objects.select_for_update().filter(owner=user).first() or Away(owner=user)
        # A new period answers everyone anew; a reworded one does not.
        if found.pk and (found.starts_at, found.ends_at) != (starts, ends):
            found.answers.all().delete()
        found.starts_at, found.ends_at = starts, ends
        found.text_hr, found.text_en = wording
        found.failed = ""
        found.save()
    return found


@api("GET", "PUT", "DELETE")
@sharing.boxed(sharing.OWN)
def away(request):
    """The user's time away and what PONISTRA answers meanwhile."""
    if request.method == "PUT":
        return JsonResponse({"away": described_away(_kept_away(request.user, body(request)))})
    if request.method == "DELETE":
        Away.objects.filter(owner=request.user).delete()
        return JsonResponse({"away": None})
    found = Away.objects.filter(owner=request.user).first()
    return JsonResponse({"away": described_away(found) if found else None})


@api("GET")
@sharing.boxed()
def away_in(request, conversation: UUID):
    return JsonResponse({"away": absence.in_talk(request.user, conversation)})


@api("GET", "POST")
@sharing.boxed(of=sharing.SENT_FROM)
def later(request):
    """The messages waiting for their moment to leave, the soonest first; or one more of them,
    which is what the composer's fields say, with the moment under `at`."""
    if request.method == "POST":
        data = body(request)
        before = _queued_before(request.user, data)
        if before is True:
            return JsonResponse({"queued": data["queued"], "sent": True})
        if isinstance(before, Unsent):
            if before.send_at is not None:
                return JsonResponse(described_unsent(before))
            data["unsent"] = before.pk
        return JsonResponse(described_unsent(_scheduled(request.user, data)), status=201)
    found = Unsent.objects.filter(owner=request.user, send_at__isnull=False).order_by("send_at")
    return JsonResponse({"later": [described_unsent(each) for each in found]})


@api("PATCH")
@sharing.boxed(of=sharing.UNSENT)
@transaction.atomic
def later_one(request, pk):
    """Moves the message to another moment, which sends one that failed again, or with none takes
    it back among those the user has not finished, to change it."""
    found = _waiting_one(request.user, pk)
    at = body(request).get("at")
    if at is not None and found.account_id is None:
        raise Refused(409, "mail_account_gone")
    found.send_at, found.failed = None if at is None else acting.moment(at), ""
    found.save(update_fields=["send_at", "failed", "updated_at"])
    if at is not None:
        notify(sending.LATER)
    return JsonResponse(described_unsent(found))
