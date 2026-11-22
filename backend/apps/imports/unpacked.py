"""An archive unpacked into a folder beside it, its folders as folders and its files placed as an
upload places them (D23). The converter reads the archive once and sends every file as a tar
stream; a password it asks for travels sealed in the job and leaves it once the job has run."""

import base64
import tarfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.blobs import previews, store
from apps.blobs.views import roomy
from apps.core import sealed
from apps.core.api import Refused, optional_id
from apps.documents.models import Node
from apps.documents.views import beside, created, dated, file_name, live_file
from apps.jobs.kinds import running
from apps.jobs.models import Job
from apps.reader import archives
from apps.reader.client import Unavailable
from apps.search import extraction

from . import convert, placed
from .reading import TooLarge, Unreadable

PURPOSE = "archive password"
TITLE = 200
# A compressed tar's name keeps ".tar" once its last extension is gone.
TAR = ".tar"


def _archive(user, pk) -> tuple[Node, Node | None]:
    node, _ = live_file(user, pk)
    if node.blob.media_type not in store.ARCHIVES:
        raise Refused(400, "not_an_archive")
    return node, beside(user, node)


def unpack_asked(request, data: dict) -> dict:
    node, _ = _archive(request.user, optional_id(data.get("node")))
    password = data.get("password")
    if password is not None and not isinstance(password, str):
        raise Refused(400, "invalid_password")
    roomy(node.blob.size)
    asked = {"node": str(node.pk)}
    if password:
        asked["password"] = base64.b64encode(sealed.seal(PURPOSE, password)).decode()
    return asked


def _titled(node: Node) -> str:
    title = node.title.strip()
    if title.lower().endswith(TAR) and len(title) > len(TAR):
        title = title[: -len(TAR)]
    return title[:TITLE] or node.title[:TITLE]


def _parts(name: str) -> list[str]:
    return [each[:TITLE] for each in PurePosixPath(name).parts if each not in ("", "/", ".", "..")]


class _Unpacked:
    def __init__(self, user, top: Node, local: bool):
        self.user = user
        self.local = local
        self.folders: dict[tuple[str, ...], Node] = {(): top}
        self.count = 0

    def folder(self, parts: tuple[str, ...]) -> Node:
        if parts not in self.folders:
            above = self.folder(parts[:-1])
            self.folders[parts] = created(above, Node.Kind.FOLDER, parts[-1], None, self.user)
        return self.folders[parts]

    def file(self, parts: tuple[str, ...], member: tarfile.TarInfo, data) -> None:
        roomy(member.size)
        blob = store.put(data)
        title, extension = placed.named(parts[-1])
        into = self.folder(parts[:-1])
        try:
            node, _ = placed.placed(blob, into, title, extension, self.user, None)
        except convert.Unavailable:
            raise Refused(503, "converter_unavailable") from None
        dated(node, self.modified(member.mtime))
        self.count += 1

    def modified(self, mtime: float) -> datetime | None:
        if not mtime:
            return None
        moment = datetime.fromtimestamp(mtime, UTC)
        # A ZIP keeps the packer's wall clock, which the converter gives as if it were UTC.
        if self.local:
            return moment.replace(tzinfo=ZoneInfo(settings.TIME_ZONE))
        return moment


def _password(parameters: dict) -> str | None:
    if "password" not in parameters:
        return None
    found = sealed.opened(PURPOSE, base64.b64decode(parameters["password"]))
    if found is None:
        raise Refused(409, "archive_locked")
    return found


def _forgotten(parameters: dict) -> None:
    job = running.get(None)
    if job is not None and "password" in parameters:
        kept = {key: value for key, value in parameters.items() if key != "password"}
        Job.objects.filter(pk=job.pk).update(parameters=kept)


def unpack_done(user, parameters: dict) -> dict:
    """The archive's folders and files in a folder named after it, beside it where the user may
    add, else at the top of their documents; what was unpacked before a failure stays."""
    try:
        node, into = _archive(user, parameters["node"])
        password = _password(parameters)
        try:
            stream = archives.packed(store.path_of(node.blob_id), file_name(node), password)
        except archives.Locked:
            raise Refused(409, "archive_locked") from None
        except TooLarge:
            raise Refused(413, "too_large") from None
        except Unavailable:
            raise Refused(503, "converter_unavailable") from None
        except Unreadable:
            raise Refused(422, "unreadable") from None
        top = created(into, Node.Kind.FOLDER, _titled(node), None, user)
        unpacked = _Unpacked(user, top, node.blob.media_type == store.ZIP)
        try:
            with stream, tarfile.open(fileobj=stream, mode="r|") as members:
                for member in members:
                    parts = tuple(_parts(member.name))
                    if not parts:
                        continue
                    if member.isdir():
                        unpacked.folder(parts)
                    elif member.isfile():
                        data = members.extractfile(member)
                        if data is not None:
                            unpacked.file(parts, member, data)
        except tarfile.TarError:
            raise Refused(422, "unreadable") from None
        finally:
            extraction.wake()
            previews.wake()
        return {"folder": str(top.pk), "count": unpacked.count}
    finally:
        _forgotten(parameters)
