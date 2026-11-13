"""People outside the installation who come in under their own name (D39): one it was shared with
by address, by a link of their own that a mail brought them, and each recipient of a mail that
carried a node as a link, once a code to their address shows who they are. Each is a visitor, an
account that only their links sign in, which no grant to everyone or a group reaches."""

import secrets

from django.conf import settings
from django.contrib.auth import login as start_session
from django.contrib.auth import logout as end_session
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse

from apps.calendar.invitations import sender_of
from apps.collab.server import revoke
from apps.core.api import Refused, api, body
from apps.core.asyncdb import database
from apps.documents import views as documents
from apps.documents.models import Node
from apps.mail import imap, sending
from apps.users import sessions
from apps.users.models import Policy, User
from apps.users.views import policy

from . import log, rights
from .models import Grant, OutsideLink, Role

BACKEND = "django.contrib.auth.backends.ModelBackend"
NAME = 150
SHARED = {
    "hr": (
        "{name} dijeli s vama: {title}",
        "{name} dijeli s vama „{title}” u Ponistri, {role}:\n\n{link}\n\n"
        "Za otvaranje vam ne treba račun.\n",
        {Role.READ: "za čitanje", Role.EDIT: "za uređivanje"},
    ),
    "en": (
        "{name} shares with you: {title}",
        "{name} shares “{title}” with you in Ponistra, {role}:\n\n{link}\n\n"
        "You need no account to open it.\n",
        {Role.READ: "to read", Role.EDIT: "to edit"},
    ),
}


def outward(user, reach: rights.Reach) -> bool:
    """Whether the user may let this node out of the installation: the policy lets them, and no
    folder above keeps it in the browser."""
    kept_inside = any(each.confined for each in reach.ancestry)
    return not kept_inside and policy().links_outside(user)


def address_of(given) -> str:
    address = given.strip().lower() if isinstance(given, str) else ""
    try:
        validate_email(address)
    except ValidationError:
        raise Refused(400, "invalid_address") from None
    return address


def colleague(address: str) -> User | None:
    """The member of the installation the address is theirs, by sign-in or a mailbox."""
    return (
        User.objects.filter(is_active=True)
        .filter(Q(email__iexact=address) | Q(mail_accounts__address__iexact=address))
        .first()
    )


def visitor_for(address: str, name: str = "") -> User:
    found = User.everyone.filter(email=address).first()
    if found is None:
        return User.everyone.create_user(address, None, visitor=True, first_name=name[:NAME])
    if not found.visitor:
        raise Refused(400, "colleague")
    if name and not found.first_name:
        found.first_name = name[:NAME]
        found.save(update_fields=["first_name"])
    return found


def invited_by(users) -> list[User]:
    """The visitors only these users let in: by address, or as a link's recipients or holders."""
    given = Grant.objects.filter(user__visitor=True)
    theirs = set(given.filter(created_by__in=users).values_list("user", flat=True))
    others = set(given.exclude(created_by__in=users).values_list("user", flat=True))
    links = OutsideLink.objects.filter(created_by__in=users, visitor__isnull=False)
    opened = set(links.values_list("visitor", flat=True))
    return list(User.everyone.filter(pk__in=(theirs - others) | opened))


def signed_in_as(request, user: User, way: str) -> None:
    """The browser signed in as the visitor, out of whichever visitor it was before."""
    if request.user.is_authenticated:
        end_session(request)
    start_session(request, user, backend=BACKEND)
    sessions.started(request, way)


def member_reads(request, node: Node) -> dict | None:
    """The node, where a member of the installation is signed in and reads it already; refused
    where they cannot, as the link is for someone outside."""
    user = request.user
    if not user.is_authenticated or user.visitor:
        return None
    if rights.reach(user, node.ancestry()).role is None:
        raise Refused(409, "signed_in_inside")
    return documents.describe(node)


def _shared(user, pk, data: dict) -> tuple[Grant, bool, object, str]:
    node, reach = documents.live(user, pk, Role.OWN)
    documents.laid_out(node)
    if not outward(user, reach):
        raise Refused(403, "links_not_allowed")
    address = address_of(data.get("address"))
    if colleague(address) is not None:
        raise Refused(400, "colleague")
    role = data.get("role")
    if role not in (Role.READ, Role.EDIT):
        raise Refused(400, "invalid_role")
    download = data.get("download", True)
    if not isinstance(download, bool):
        raise Refused(400, "invalid_download")
    name = " ".join(str(data.get("name") or "").split())
    account = sender_of(user)
    with transaction.atomic():
        visitor = visitor_for(address, name)
        grant = Grant.objects.filter(node=node, user=visitor).first()
        made = grant is None
        if made:
            grant = Grant(node=node, user=visitor, created_by=user)
        grant.role, grant.download = role, download
        grant.key = grant.key or secrets.token_urlsafe(32)
        grant.save()
        log.shared(user, grant, role)
    revoke()
    return grant, made, account, node.title


def _unshared(grant: Grant, by) -> None:
    with transaction.atomic():
        log.shared(by, grant, None)
        grant.delete()
    revoke()


@api("POST")
async def visitors(request, pk):
    """Shares the node with someone outside by their address, to read or to edit, and writes them
    a link of their own from the user's account; a mail that does not leave takes it back."""
    data = body(request)
    user = request.user
    grant, made, account, title = await database(_shared)(user, pk, data)
    language = data.get("language") if data.get("language") in SHARED else "en"
    subject, text, roles = SHARED[language]
    name = user.get_full_name() or account.name or account.address
    message = sending.composed(
        account,
        [sending.address("", grant.user.email)],
        [],
        [],
        subject.format(name=name, title=title),
        text.format(
            name=name,
            title=title,
            role=roles[grant.role],
            link=f"{settings.PUBLIC_URL}/v/{grant.key}",
        ),
        None,
        [],
    )
    try:
        await sending.delivered(account, message)
    except imap.Failed as failed:
        if made:
            await database(_unshared)(grant, user)
        raise Refused(502, failed.code) from None
    await database(sending.recorded)(account, message, None)
    return JsonResponse({"id": grant.pk}, status=201 if made else 200)


@api("POST", signed_in=False)
def visit(request, key):
    """Signs in whoever holds the personal link of a visitor, and answers with the node it
    opens."""
    grant = Grant.objects.select_related("node", "user").filter(key=key).first() if key else None
    if (
        grant is None
        or not grant.user.visitor
        or not grant.node.is_live(grant.node.ancestry())
        or policy().outside == Policy.Outside.NOBODY
    ):
        raise Refused(404, "no_link")
    if (inside := member_reads(request, grant.node)) is not None:
        return JsonResponse({"node": inside})
    signed_in_as(request, grant.user, "visit")
    return JsonResponse({"node": documents.describe(grant.node)})
