"""Links that take a node outside the installation (D39). Whoever opens a link of the OPEN kind
is signed in as the link's own visitor and reads the node as it is now, and nothing else, so a
link that leaks changes nothing; the recipients of a mail come in by a link of the PEOPLE kind,
each under their own address once a code sent there shows who they are; a link of the UPLOAD kind
lets anyone put files into a folder. Each ends at its date, when its owner ends it, when the node
leaves the living or a folder above keeps it in the browser, and all of them when the
installation's policy says nobody."""

import secrets
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.blobs import previews
from apps.blobs import views as blobs
from apps.blobs.models import Upload
from apps.calendar.invitations import sender_of
from apps.collab.server import revoke
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database
from apps.documents import views as documents
from apps.documents.models import Node
from apps.mail import imap, sending
from apps.push import notices
from apps.push.models import Notice
from apps.search import extraction
from apps.users.models import Policy, User
from apps.users.views import policy

from . import log, rights, visitors
from .models import Access, Code, Grant, OutsideLink, Role

MOST_FAILURES = 10
FAILURES_FORGOTTEN = timedelta(minutes=15)
CODE_DIGITS = 6
CODE_LASTS = timedelta(minutes=15)
CODE_AGAIN = timedelta(minutes=1)
CODE_TRIES = 5
SENDER = 200
CODED = {
    "hr": (
        "Kôd za „{title}”",
        "Vaš kôd za otvaranje „{title}” u Ponistri je {code}.\n\nVrijedi 15 minuta.\n",
    ),
    "en": (
        "Code for “{title}”",
        "Your code to open “{title}” in Ponistra is {code}.\n\nIt lasts 15 minutes.\n",
    ),
}


def url_of(link: OutsideLink) -> str:
    return f"{settings.PUBLIC_URL}/o/{link.token}"


def _described(link: OutsideLink) -> dict:
    return {
        "id": link.pk,
        "kind": link.kind,
        "role": link.role,
        "download": link.download,
        "addresses": link.addresses,
        "url": url_of(link),
        "password": bool(link.password),
        "expires_at": link.expires_at,
        "created_at": link.created_at,
    }


def _until(given) -> datetime | None:
    """The end of the day given, by the installation's clock."""
    if not given:
        return None
    day = parse_date(given) if isinstance(given, str) else None
    if day is None or day < timezone.localdate():
        raise Refused(400, "invalid_link_date")
    return timezone.make_aware(datetime.combine(day, time.max))


def made(user, node: Node, kind: str, **given) -> OutsideLink:
    link = OutsideLink.objects.create(
        node=node, kind=kind, token=secrets.token_urlsafe(32), created_by=user, **given
    )
    log.linked(user, link, link.role if kind != OutsideLink.Kind.UPLOAD else "upload")
    return link


@api("GET", "POST")
def links(request, pk):
    """The node's outside links, for its owner, and a new one where the policy lets them make it:
    one anyone reads by, or one anyone puts files into a folder by."""
    node, reach = documents.live(request.user, pk, Role.OWN)
    if node.kind == Node.Kind.LINK:
        raise Refused(400, "not_shareable")
    allowed = visitors.outward(request.user, reach)
    if request.method == "GET":
        kept = node.outside_links.order_by("created_at")
        return JsonResponse({"allowed": allowed, "links": [_described(each) for each in kept]})
    if not allowed:
        raise Refused(403, "links_not_allowed")
    data = body(request)
    kind = data.get("kind", OutsideLink.Kind.OPEN)
    if kind not in (OutsideLink.Kind.OPEN, OutsideLink.Kind.UPLOAD):
        raise Refused(400, "invalid_link_kind")
    if kind == OutsideLink.Kind.UPLOAD and node.kind != Node.Kind.FOLDER:
        raise Refused(400, "not_a_folder")
    password = data.get("password") or ""
    if (
        not isinstance(password, str)
        or len(password) > 200
        or (password and kind == OutsideLink.Kind.UPLOAD)
    ):
        raise Refused(400, "invalid_link_password")
    download = data.get("download", True)
    if not isinstance(download, bool):
        raise Refused(400, "invalid_download")
    with transaction.atomic():
        link = made(
            request.user,
            node,
            kind,
            password=make_password(password) if password else "",
            expires_at=_until(data.get("expires_on")),
            download=download,
        )
    return JsonResponse(_described(link), status=201)


def ended(user, link: OutsideLink) -> None:
    """Ends a link at once, and whoever it signed in with it."""
    with transaction.atomic():
        log.linked(user, link, None)
        opened = link.visitor
        link.delete()
        if opened is not None:
            opened.delete()
    revoke()


@api("DELETE")
def link(request, pk):
    found = OutsideLink.objects.select_related("node", "visitor").filter(pk=pk).first()
    if found is None:
        raise Refused(404, "not_found")
    documents.live(request.user, found.node_id, Role.OWN)
    ended(request.user, found)
    return HttpResponse(status=204)


def _found(token: str) -> OutsideLink:
    found = OutsideLink.objects.select_related("node", "visitor").filter(token=token).first()
    if (
        found is None
        or (found.expires_at and found.expires_at < timezone.now())
        or not found.node.is_live(found.node.ancestry())
    ):
        raise Refused(404, "no_link")
    return found


def _outward(found: OutsideLink) -> None:
    """Refuses the link to anyone outside where a folder above keeps the node in the browser or
    the installation lets nothing out; a member who reads the node opens it all the same."""
    if (
        any(each.confined for each in found.node.ancestry())
        or policy().outside == Policy.Outside.NOBODY
    ):
        raise Refused(404, "no_link")


def _live(token: str) -> OutsideLink:
    found = _found(token)
    _outward(found)
    return found


@api("GET", signed_in=False)
def door(request, token):
    """What someone holding a link sees of it before they are in: what it asks of them, and the
    node where it asks nothing or they read it already."""
    found = _found(token)
    inside = None
    if found.kind != OutsideLink.Kind.UPLOAD:
        user = request.user
        if user.is_authenticated and rights.reach(user, found.node.ancestry()).role is not None:
            inside = documents.describe(found.node)
    if inside is None:
        _outward(found)
    shown = found.kind == OutsideLink.Kind.UPLOAD or (
        found.kind == OutsideLink.Kind.OPEN and not found.password
    )
    return JsonResponse(
        {
            "kind": found.kind,
            "title": found.node.title if shown or inside else None,
            "password": bool(found.password),
            "node": inside,
        }
    )


def _tried(found: OutsideLink, given) -> bool:
    """Whether the password given is the link's, counting the failures that lock it a while."""
    now = timezone.now()
    with transaction.atomic():
        held = OutsideLink.objects.select_for_update().get(pk=found.pk)
        if held.failed_at is None or now - held.failed_at > FAILURES_FORGOTTEN:
            held.failures = 0
        if held.failures >= MOST_FAILURES:
            raise Refused(429, "too_many_link_tries")
        if isinstance(given, str) and check_password(given, held.password):
            return True
        held.failures += 1
        held.failed_at = now
        held.save(update_fields=["failures", "failed_at"])
    return False


def _opener(found: OutsideLink) -> User:
    """The visitor anyone who opens the link is, made at its first opening, with the grant that
    lets them read the node."""
    with transaction.atomic():
        held = (
            OutsideLink.objects.select_for_update(of=("self",))
            .select_related("visitor")
            .get(pk=found.pk)
        )
        if held.visitor is None:
            held.visitor = User.everyone.create_user(
                f"link-{held.pk}@outside.invalid", None, visitor=True
            )
            held.save(update_fields=["visitor"])
            Grant.objects.create(
                node=held.node,
                user=held.visitor,
                role=Role.READ,
                download=held.download,
                link=held,
                created_by=held.created_by,
            )
        return held.visitor


def _entered(request, found: OutsideLink, user: User, way: str) -> JsonResponse:
    visitors.signed_in_as(request, user, way)
    log.opened_through(found, user)
    return JsonResponse({"node": documents.describe(found.node)})


@api("POST", signed_in=False)
def enter(request, token):
    """Signs in whoever opens the link: anyone, with its password where it has one, as the link's
    visitor; a recipient of the mail under their address, with the code sent there."""
    found = _found(token)
    if found.kind == OutsideLink.Kind.UPLOAD:
        raise Refused(400, "invalid_link_kind")
    if (inside := visitors.member_reads(request, found.node)) is not None:
        return JsonResponse({"node": inside})
    _outward(found)
    data = body(request)
    if found.kind == OutsideLink.Kind.OPEN:
        if found.password and not _tried(found, data.get("password")):
            return JsonResponse({"error": "wrong_link_password"}, status=403)
        return _entered(request, found, _opener(found), "link")
    address = visitors.address_of(data.get("address"))
    if not _coded(found, address, data.get("code")):
        return JsonResponse({"error": "wrong_code"}, status=403)
    return _entered(request, found, _recipient(found, address), "code")


def _coded(found: OutsideLink, address: str, given) -> bool:
    with transaction.atomic():
        code = Code.objects.select_for_update().filter(link=found, address=address).first()
        if code is None or timezone.now() - code.sent_at > CODE_LASTS:
            return False
        if code.tries >= CODE_TRIES:
            raise Refused(429, "too_many_code_tries")
        if isinstance(given, str) and check_password(given.strip(), code.digest):
            code.delete()
            return True
        code.tries += 1
        code.save(update_fields=["tries"])
    return False


def _recipient(found: OutsideLink, address: str) -> User:
    """The recipient at the address as a visitor, with the grant the link gives them."""
    with transaction.atomic():
        user = visitors.visitor_for(address)
        if not Grant.objects.filter(node=found.node, user=user).exists():
            Grant.objects.create(
                node=found.node,
                user=user,
                role=found.role,
                download=found.download,
                link=found,
                created_by=found.created_by,
            )
    revoke()
    return user


def _asked(token: str, address: str):
    """The code to send to the address, where the link lets it in and none went there a moment
    ago, with the account it goes from."""
    found = _live(token)
    if found.kind != OutsideLink.Kind.PEOPLE:
        raise Refused(400, "invalid_link_kind")
    if address not in found.addresses or visitors.colleague(address) is not None:
        return None
    sent = Code.objects.filter(link=found, address=address).first()
    if sent is not None and timezone.now() - sent.sent_at < CODE_AGAIN:
        return None
    account = sender_of(found.created_by) if found.created_by else None
    if account is None:
        return None
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
    Code.objects.update_or_create(
        link=found,
        address=address,
        defaults={"digest": make_password(code), "sent_at": timezone.now(), "tries": 0},
    )
    return account, code, found.node.title


@api("POST", signed_in=False)
async def code(request, token):
    """Sends a code to the address given where the link lets it in, from the account of whoever
    made the link; the answer is the same whether it does or not."""
    data = body(request)
    address = visitors.address_of(data.get("address"))
    asked = await database(_asked)(token, address)
    if asked is not None:
        account, given, title = asked
        language = data.get("language") if data.get("language") in CODED else "en"
        subject, text = CODED[language]
        message = sending.composed(
            account,
            [sending.address("", address)],
            [],
            [],
            subject.format(title=title),
            text.format(title=title, code=given),
            None,
            [],
        )
        try:
            await sending.delivered(account, message)
        except imap.Failed as failed:
            raise Refused(502, failed.code) from None
    return HttpResponse(status=204)


def _asking(token: str) -> OutsideLink:
    found = _live(token)
    if found.kind != OutsideLink.Kind.UPLOAD or found.created_by is None:
        raise Refused(404, "no_link")
    return found


@api("POST", signed_in=False)
async def uploads(request, token):
    """A file someone asked for by the link uploads, in the name of whoever made it."""
    found = await database(_asking)(token)
    return await blobs.begun(request, found.created_by)


@api("GET", "PUT", signed_in=False)
async def upload(request, token, pk):
    found = await database(_asking)(token)
    return await blobs.received(request, found.created_by, pk)


@api("POST", signed_in=False)
def files(request, token):
    """The file uploaded by the link put into its folder, under the name its sender gave, for
    the folder's owners to find in the access log."""
    found = _asking(token)
    data = body(request)
    upload = (
        Upload.objects.select_related("blob")
        .filter(pk=data.get("upload"), user=found.created_by, blob__isnull=False)
        .first()
        if isinstance(data.get("upload"), str)
        else None
    )
    if upload is None:
        raise Refused(400, "unknown_file")
    sender = " ".join(str(data.get("sender") or "").split())[:SENDER]
    with transaction.atomic():
        node = documents.dated(
            documents.created(
                found.node,
                Node.Kind.FILE,
                documents.title_of(data),
                upload.blob,
                found.created_by,
                documents.extension_given(data),
            ),
            documents.modified_of(data),
        )
        Access.objects.create(
            node=node,
            kind=Access.Kind.UPLOADED,
            detail={"link": str(found.pk), "sender": sender},
        )
        upload.delete()
        notices.tell(
            [found.created_by_id],
            Notice.Kind.UPLOADED,
            {
                "node": str(node.pk),
                "title": node.title,
                "folder": found.node.title,
                "sender": sender,
            },
            tag=notices.topic("upload", found.node_id),
        )
    extraction.wake()
    previews.wake()
    return JsonResponse({"title": node.title}, status=201)
