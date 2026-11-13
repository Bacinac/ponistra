"""What the installation holds of one person, as one zip an administrator saves for them (GDPR
art. 15 and 20): `person.json` with the account, under `data/` every row that names them as a
JSON list per model and field, under `mail/` each message as it came, under `files/` the photos
of their contacts, and under `documents/` their own documents as PONISTRA's own files and
their own files as they are, by the folders they stand in. `manifest.json` lists each part."""

import json
import mimetypes
import re
import shutil
import tempfile
import zipfile
from typing import IO

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from apps.access.rights import mine
from apps.blobs import store
from apps.blobs.models import Blob
from apps.core.api import Refused
from apps.documents.models import Node
from apps.documents.views import extension_of
from apps.exports import ponx
from apps.jobs.kinds import Kind, Saved
from apps.mail import taking
from apps.mail.models import Message

from . import sessions
from .accounts import describe
from .models import User

FORMAT = "ponistra-personal"
VERSION = 1

# The rows naming the person, by the model and the field that names them, with the fields left
# out of each: what signs in or opens something for whoever holds it, never the person's data.
# Binary fields (keys, sealed secrets) and those the database derives stay out of every one.
PARTS: dict[tuple[str, str], tuple[str, ...]] = {
    ("users.Passkey", "user"): (),
    ("users.AppPassword", "user"): ("digest",),
    ("users.Session", "user"): ("session_key", "session_data"),
    ("identity.Identity", "user"): (),
    ("documents.Node", "created_by"): (),
    ("documents.Favourite", "user"): (),
    ("documents.BoardEntry", "updated_by"): (),
    ("access.Grant", "user"): (),
    ("access.Grant", "created_by"): (),
    ("access.OutsideLink", "created_by"): ("token", "password"),
    ("access.Access", "user"): (),
    ("content.TableFilter", "user"): (),
    ("versions.VersionEditor", "user"): (),
    ("versions.Contribution", "user"): (),
    ("versions.FileVersion", "created_by"): (),
    ("comments.Thread", "resolved_by"): (),
    ("comments.Comment", "author"): (),
    ("actions.ActionRun", "user"): (),
    ("actions.ActionRun", "undone_by"): (),
    ("actions.ActionRun", "consented_by"): (),
    ("ai.Consent", "given_by"): (),
    ("ai.SearchConsent", "user"): (),
    ("ai.SpeechConsent", "user"): (),
    ("ai.Reading", "user"): (),
    ("mail.Account", "owner"): ("policy_key", "folder_key"),
    ("mail.Signature", "owner"): (),
    ("mail.Folder", "owner"): (),
    ("mail.Message", "owner"): (),
    ("mail.Decided", "owner"): (),
    ("mail.Rule", "owner"): (),
    ("mail.Deleted", "owner"): (),
    ("mail.Correspondent", "owner"): (),
    ("mail.Draft", "owner"): (),
    ("mail.Unsent", "owner"): (),
    ("mail.Away", "owner"): (),
    ("mail.Key", "owner"): (),
    ("mail.Grant", "user"): (),
    ("mail.Grant", "created_by"): (),
    ("mail.Opening", "user"): (),
    ("agents.Authorization", "user"): ("code",),
    ("agents.Grant", "user"): (),
    ("contacts.Contact", "owner"): (),
    ("contacts.Taken", "owner"): (),
    ("calendar.Calendar", "owner"): (),
    ("calendar.Taken", "owner"): (),
    ("calendar.Invitation", "owner"): (),
    ("tasks.Task", "owner"): (),
    ("chat.Conversation", "created_by"): (),
    ("chat.Member", "user"): (),
    ("chat.Message", "author"): (),
    ("chat.Mention", "user"): (),
    ("chat.Follower", "user"): (),
    ("chat.Reaction", "user"): (),
    ("meetings.Meeting", "organizer"): (),
    ("meetings.Ring", "user"): (),
    ("meetings.Ring", "by"): (),
    ("meetings.Guest", "by"): ("key",),
    ("meetings.Recording", "started_by"): (),
    ("drive.Drive", "user"): (),
    ("push.Subscription", "user"): ("endpoint",),
    ("push.Notice", "user"): (),
    ("vault.Collection", "owner"): (),
    ("vault.Collection", "created_by"): (),
    ("vault.Member", "user"): (),
    ("vault.Member", "created_by"): (),
    ("vault.Event", "user"): (),
    ("vault.Event", "subject"): (),
    ("journal.Entry", "actor"): (),
    ("journal.Entry", "subject"): (),
    ("workspace.Aside", "owner"): (),
}

# The parts whose files come along, rather than a document's, which `documents/` carries.
FILES = {("contacts.Contact", "owner")}

# The relations to a user that are not the person's data, and why.
LEFT: dict[tuple[str, str], str] = {
    ("users.User_groups", "user"): "in person.json",
    ("users.User_user_permissions", "user"): "not used",
    ("versions.Version", "editors"): "through versions.VersionEditor",
    ("documents.Node", "updated_by"): "the last to change a node, replaced by the next",
    ("blobs.Upload", "user"): "a file arriving, gone once it has",
    ("access.OutsideLink", "visitor"): "whom a link signs in, exported as the link's own",
    ("jobs.Job", "user"): "work under way, gone within the hour",
    ("identity.Code", "user"): "a sign-in code that lasts minutes",
    ("identity.Attempt", "confirming"): "a sign-in at a provider that lasts minutes",
    ("contacts.Gone", "owner"): "what a phone was told is gone",
    ("calendar.Gone", "owner"): "what a phone was told is gone",
    ("mail.Grant", "mailbox"): "whom a shared mailbox is shared with; a mailbox is no person",
    ("vault.Vault", "user"): "sealed keys; the vault exports itself",
    ("vault.Key", "user"): "sealed keys",
    ("vault.Key", "confirmed_by"): "sealed keys",
    ("vault.Holder", "user"): "sealed keys",
    ("vault.Holder", "confirmed_by"): "sealed keys",
    ("vault.Escrow", "user"): "sealed keys",
    ("vault.Recovery", "created_by"): "the installation's recovery key",
    ("vault.Folder", "created_by"): "sealed; the vault exports itself",
    ("vault.Item", "created_by"): "sealed; the vault exports itself",
    ("vault.Item", "updated_by"): "sealed; the vault exports itself",
    ("vault.Attachment", "created_by"): "sealed; the vault exports itself",
    ("users.Policy", "changed_by"): "a setting of the installation",
    ("ai.Setting", "changed_by"): "a setting of the installation",
    ("ai.Speech", "changed_by"): "a setting of the installation",
    ("meetings.Relay", "changed_by"): "a setting of the installation",
    ("backups.Offsite", "changed_by"): "a setting of the installation",
    ("mail.Client", "changed_by"): "a setting of the installation",
    ("mail.Setting", "changed_by"): "a setting of the installation",
    ("calendar.Workdays", "changed_by"): "a setting of the installation",
    ("push.Setting", "changed_by"): "a setting of the installation",
    ("shares.Share", "created_by"): "a setting of the installation",
    ("retention.Rule", "created_by"): "a setting of the installation",
    ("retention.Hold", "created_by"): "a setting of the installation",
    ("retention.Hold", "person"): "the organisation's record of a dispute, kept from its subject",
}

UNSAFE = re.compile(r'[\x00-\x1f/\\:*?"<>|]')


def relations() -> set[tuple[str, str]]:
    """Every field anywhere that names a user."""
    return {
        (field.related_model._meta.label, field.remote_field.name)
        for field in User._meta.get_fields(include_hidden=True)
        if field.is_relation and field.auto_created and not field.concrete
    }


def _columns(model: type[models.Model], left: tuple[str, ...]) -> list[str]:
    return [
        field.attname
        for field in model._meta.concrete_fields
        if field.name not in left
        and not isinstance(field, (models.BinaryField, models.GeneratedField))
    ]


def _blobs(model: type[models.Model]) -> list[str]:
    return [
        field.attname
        for field in model._meta.concrete_fields
        if field.is_relation
        and field.related_model is not None
        and field.related_model._meta.label == "blobs.Blob"
    ]


class _Archive:
    def __init__(self, file: IO[bytes]):
        self.zip = zipfile.ZipFile(file, "w", zipfile.ZIP_DEFLATED, allowZip64=True)
        self.parts: list[dict] = []
        self.files: set[str] = set()

    def json(self, name: str, value, **about) -> None:
        self.zip.writestr(name, json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False))
        self.parts.append({"name": name, **about})

    def rows(self, name: str, rows, **about) -> int:
        count = 0
        with self.zip.open(name, "w", force_zip64=True) as part:
            part.write(b"[")
            for row in rows:
                part.write(b",\n" if count else b"\n")
                part.write(json.dumps(row, cls=DjangoJSONEncoder, ensure_ascii=False).encode())
                count += 1
            part.write(b"\n]\n")
        self.parts.append({"name": name, "rows": count, **about})
        return count

    def blob(self, sha256: str, media_type: str) -> str:
        name = f"files/{sha256}{mimetypes.guess_extension(media_type) or ''}"
        if name not in self.files:
            self.files.add(name)
            self.zip.write(store.path_of(sha256), name, zipfile.ZIP_STORED)
        return name

    def stream(self, name: str, source: IO[bytes]) -> None:
        with source, self.zip.open(name, "w", force_zip64=True) as part:
            shutil.copyfileobj(source, part)
        self.parts.append({"name": name})


def _person(user: User) -> dict:
    return {
        **describe(user),
        "groups": list(user.groups.order_by("name").values_list("name", flat=True)),
        "date_joined": user.date_joined,
        "language": user.language,
        "theme": user.theme,
        "projects_theme": user.projects_theme,
        "meetings_theme": user.meetings_theme,
        "sign_in": user.sign_in,
        "call": user.call,
    }


def _noting(found, held: list[str], blobs: set[str]):
    """The rows, noting the files they hold as they pass."""
    for row in found.iterator(chunk_size=1000):
        blobs.update(row[column] for column in held if row[column])
        yield row


def _data(archive: _Archive, user: User) -> None:
    for (label, by), left in sorted(PARTS.items()):
        model = apps.get_model(label)
        columns = _columns(model, left)
        held = _blobs(model) if (label, by) in FILES else []
        found = model._default_manager.filter(**{by: user}).order_by("pk").values(*columns)
        blobs: set[str] = set()
        archive.rows(f"data/{label}.{by}.json", _noting(found, held, blobs), model=label, field=by)
        for blob in Blob.objects.filter(sha256__in=blobs).order_by("sha256"):
            archive.blob(blob.sha256, blob.media_type)


def _mail(archive: _Archive, user: User) -> None:
    """Each message as it came, by its id in data/mail.Message.owner.json."""
    for message in Message.objects.filter(owner=user).order_by("pk").iterator(chunk_size=200):
        name = f"mail/{message.pk}.eml"
        archive.zip.writestr(name, taking.whole(message))
        archive.parts.append({"name": name})


def _named(node: Node, taken: set[str], folder: str, extension: str = "") -> str:
    title = UNSAFE.sub("_", node.title).strip(" .") or str(node.pk)
    name = f"{folder}/{title}{extension}"
    if name in taken:
        name = f"{folder}/{title} ({str(node.pk)[:8]}){extension}"
    taken.add(name)
    return name


def _documents(archive: _Archive, user: User) -> None:
    taken: set[str] = set()
    for top in mine(user).order_by("title", "pk"):
        places = {top.parent_id: "documents"}
        for node in [top, *top.descendants()]:
            folder = places[node.parent_id]
            if node.kind == Node.Kind.FOLDER:
                places[node.pk] = _named(node, taken, folder)
            elif node.kind == Node.Kind.DOCUMENT:
                archive.stream(_named(node, taken, folder, ".ponx"), ponx.packed(node))
            elif node.kind == Node.Kind.FILE:
                extension = extension_of(node)
                name = _named(node, taken, folder, f".{extension}" if extension else "")
                archive.zip.write(store.path_of(node.blob_id), name, zipfile.ZIP_STORED)
                archive.parts.append({"name": name})


def packed(user: User) -> IO[bytes]:
    """The zip, written to a temporary file that goes when it is closed."""
    found = tempfile.TemporaryFile()
    archive = _Archive(found)
    person = _person(user)
    if user.backdrop_id:
        person["backdrop"] = archive.blob(user.backdrop_id, user.backdrop.media_type)
    archive.json("person.json", person)
    _data(archive, user)
    _mail(archive, user)
    _documents(archive, user)
    archive.zip.writestr(
        "manifest.json",
        json.dumps(
            {
                "format": FORMAT,
                "version": VERSION,
                "made": timezone.now().isoformat(),
                "user": user.pk,
                "parts": archive.parts,
            },
            ensure_ascii=False,
        ),
    )
    archive.zip.close()
    found.seek(0)
    return found


def _subject(requester: User, pk) -> User:
    if not (requester.is_active and requester.is_staff):
        raise Refused(403, "forbidden")
    subject = User.everyone.filter(pk=pk).first() if isinstance(pk, int) else None
    if subject is None:
        raise Refused(404, "not_found")
    return subject


def asked(request, data: dict) -> dict:
    subject = _subject(request.user, data.get("user"))
    if not sessions.fresh(request.session.get(sessions.CONFIRMED)):
        raise Refused(403, "confirm_required")
    return {"user": subject.pk}


def done(requester: User, parameters: dict) -> Saved:
    subject = _subject(requester, parameters["user"])
    return Saved(packed(subject), f"{subject.email}.zip")


KINDS = {"personal": Kind(asked, done, saves=True)}
