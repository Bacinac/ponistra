from django.http import JsonResponse

from apps.access.models import Role
from apps.blobs import store
from apps.blobs.models import Blob
from apps.blobs.views import serve
from apps.core.api import Refused, api, body
from apps.documents.views import describe, live, taken_out

from . import reading, scanned
from .formats import EXTENSIONS


@api("GET", visitors=True)
def source(request, pk):
    node, reach = live(request.user, pk)
    if node.source is None:
        raise Refused(404, "not_found")
    extension = EXTENSIONS[node.source.media_type]
    taken_out(request.user, node, reach, extension)
    return serve(request, node.source, f"{node.title}.{extension}")


@api("DELETE", visitors=True)
def report(request, pk):
    """The import's report, read by someone who may edit the document, is put away."""
    node, _ = live(request.user, pk, Role.EDIT)
    node.imported = None
    node.save(update_fields=["imported"])
    return JsonResponse(describe(node))


def photo(sha256: object) -> Blob:
    """An uploaded photo of a page."""
    found = Blob.objects.filter(pk=sha256).first() if isinstance(sha256, str) else None
    if found is None:
        raise Refused(400, "unknown_file")
    if found.media_type not in store.IMAGES or found.media_type == "image/svg+xml":
        raise Refused(415, "not_a_photo")
    return found


@api("POST")
def corners(request):
    """Where the page's corners are in the photo uploaded (D43)."""
    try:
        return JsonResponse({"corners": scanned.found(photo(body(request).get("blob")))})
    except reading.Unreadable:
        raise Refused(422, "unreadable") from None
