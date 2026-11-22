from django.http import FileResponse, HttpResponse, JsonResponse
from django.utils.http import content_disposition_header

from apps.blobs import store
from apps.core.api import Refused, api, body
from apps.documents.views import file_name, live_file, taken_out
from apps.imports.reading import TooLarge, Unreadable

from . import shown
from .archives import Locked
from .client import Unavailable


def _password(request) -> str | None:
    if request.method != "POST":
        return None
    password = body(request).get("password")
    if password is not None and not isinstance(password, str):
        raise Refused(400, "invalid_password")
    return password or None


def _refused(error: Exception) -> Refused:
    if isinstance(error, Locked):
        return Refused(409, "archive_locked")
    if isinstance(error, TooLarge):
        return Refused(413, "too_large")
    if isinstance(error, Unavailable):
        return Refused(503, "converter_unavailable")
    return Refused(422, "unreadable")


@api("GET", "POST", visitors=True)
def node_shown(request, pk):
    """What the file shows of what it holds; POSTed with the password an archive asks for."""
    node, _ = live_file(request.user, pk)
    try:
        found = shown.of(
            store.path_of(node.blob_id),
            file_name(node),
            f"/api/nodes/{node.pk}/shown/",
            node.blob.media_type,
            _password(request),
        )
    except (Locked, TooLarge, Unavailable, Unreadable) as error:
        raise _refused(error) from None
    if found is None:
        raise Refused(404, "not_found")
    return JsonResponse(found)


@api("GET", "POST", visitors=True)
def node_shown_part(request, pk, part):
    """One part of what the file shows: an archive's entry or a message's attachment, saved; a
    picture the browser cannot show, drawn whole."""
    node, reach = live_file(request.user, pk)
    try:
        found = shown.part(
            store.path_of(node.blob_id),
            file_name(node),
            part,
            node.blob.media_type,
            _password(request),
        )
    except (Locked, TooLarge, Unavailable, Unreadable) as error:
        raise _refused(error) from None
    if found is None:
        raise Refused(404, "not_found")
    if not found.shown:
        taken_out(request.user, node, reach, found.name.rpartition(".")[2] or "file")
    disposition = content_disposition_header(not found.shown, found.name)
    if isinstance(found.data, bytes):
        response = HttpResponse(found.data, content_type=found.media_type)
    else:
        response = FileResponse(found.data, content_type=found.media_type)
    response["Content-Disposition"] = disposition
    response["Cache-Control"] = "private, no-cache"
    # Nothing a file holds runs as a page of ours: an HTML attachment is only saved.
    response["Content-Security-Policy"] = "sandbox"
    response["X-Content-Type-Options"] = "nosniff"
    return response
