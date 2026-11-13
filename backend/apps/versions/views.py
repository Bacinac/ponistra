import re

from django.http import HttpResponse, JsonResponse

from apps.access import rights
from apps.access.models import Role
from apps.collab import server
from apps.core.api import Refused, api, body
from apps.documents import boards
from apps.documents import views as documents
from apps.documents.models import Node
from apps.users.views import describe as describe_user

from . import history, kept
from .models import FileVersion, Version, VersionTab


def describe(version: Version) -> dict:
    return {
        "id": version.id,
        "number": version.number,
        "title": version.title,
        "created_at": version.created_at,
        "restored_from": version.restored_from,
        "editors": [describe_user(user) for user in version.editors.all()],
    }


def describe_file(version: FileVersion) -> dict:
    return {
        "id": version.id,
        "number": version.number,
        "title": "",
        "created_at": version.created_at,
        "restored_from": version.restored_from,
        "editors": [describe_user(version.created_by)] if version.created_by else [],
        "agent": version.agent,
    }


def describe_part(part: VersionTab) -> dict:
    return {"id": part.tab, "parent": part.parent, "title": part.title, "position": part.position}


def version_of(request, pk, needs: Role = Role.READ) -> tuple[Version, rights.Reach]:
    version = Version.objects.filter(pk=pk).first()
    if version is None:
        raise Refused(404, "not_found")
    _, reach = documents.live(request.user, version.document_id, needs)
    return version, reach


@api("GET", "POST", visitors=True)
def versions(request, pk):
    needs = Role.EDIT if request.method == "POST" else Role.READ
    node, _ = documents.live(request.user, pk, needs)
    if node.kind == Node.Kind.FILE and request.method == "GET":
        listed = node.file_versions.order_by("-number").select_related("created_by")
        return JsonResponse({"versions": [describe_file(version) for version in listed]})
    document = documents.live_document(request.user, pk, needs)
    if request.method == "POST":
        title = documents.title_of(body(request))
        return JsonResponse(describe(history.take(document, request.user, title)), status=201)
    listed = document.versions.order_by("-number").prefetch_related("editors")
    return JsonResponse({"versions": [describe(version) for version in listed]})


@api("GET", "PATCH", visitors=True)
def version(request, pk):
    needs = Role.EDIT if request.method == "PATCH" else Role.READ
    version, reach = version_of(request, pk, needs)
    if request.method == "PATCH":
        version.title = documents.title_of(body(request))
        version.save(update_fields=["title"])
    return JsonResponse(
        {
            "version": describe(version),
            **documents.placed(reach),
            "tabs": [describe_part(part) for part in version.tabs_in_order()],
        }
    )


@api("POST", visitors=True)
def restore(request, pk):
    version, _ = version_of(request, pk, Role.EDIT)
    restored = server.rewrite(version.document_id, lambda: history.restore(version, request.user))
    server.revoke()
    return JsonResponse(describe(restored))


@api("GET", visitors=True)
def state(request, pk):
    version, _ = version_of(request, pk)
    return HttpResponse(bytes(version.state.data), content_type="application/octet-stream")


@api("GET", visitors=True)
def tab_state(request, pk, tab):
    version, _ = version_of(request, pk)
    part = VersionTab.objects.select_related("state").filter(version=version, tab=tab)
    if (part := part.first()) is None:
        raise Refused(404, "not_found")
    return HttpResponse(bytes(part.state.data), content_type="application/octet-stream")


def _grids(version: Version, tab: str | None) -> JsonResponse:
    """The outlines of the version's grids of the tab, or of the document's headers and footers;
    their rows come by windows (`rows`)."""
    looks: dict = {}
    found = [table.told(looks) for table in kept.opened(version).of(tab)]
    return JsonResponse({"grids": found, "looks": looks})


SPANS = re.compile(r"\d+-\d+(,\d+-\d+)*")
# As many as the widest window of a browser asks for at once, several times over.
MOST_ROWS = 20_000


def _table(version: Version, request):
    book = kept.opened(version)
    table = book.peek(request.GET.get("table", ""))
    if table is None:
        raise Refused(404, "not_found")
    return book, table


def _numbers(given: str) -> list[int]:
    return [int(each) for each in given.split(",")] if given else []


@api("GET", visitors=True)
def rows(request, pk):
    """The rows of a table of the version standing in the spans of places asked for."""
    version, _ = version_of(request, pk)
    book, table = _table(version, request)
    given = request.GET.get("spans", "")
    if not SPANS.fullmatch(given):
        raise Refused(400, "invalid")
    spans = [
        (int(first), int(last)) for first, last in (each.split("-") for each in given.split(","))
    ]
    if sum(max(last - first + 1, 0) for first, last in spans) > MOST_ROWS:
        raise Refused(400, "invalid")
    looks: dict = {}
    return JsonResponse({**table.rows(book, spans, looks), "looks": looks})


@api("GET", visitors=True)
def standing(request, pk):
    """Where rows of a table of the version stand and what stands at places, as asked."""
    version, _ = version_of(request, pk)
    _, table = _table(version, request)
    wanted = request.GET.get("rows", "")
    try:
        return JsonResponse(
            table.standing(
                _numbers(request.GET.get("places", "")),
                wanted.split(",") if wanted else [],
                _numbers(request.GET.get("numbered", "")),
            )
        )
    except ValueError:
        raise Refused(400, "invalid") from None


@api("GET", visitors=True)
def grids(request, pk):
    version, _ = version_of(request, pk)
    return _grids(version, None)


@api("GET", visitors=True)
def tab_grids(request, pk, tab):
    version, _ = version_of(request, pk)
    if not VersionTab.objects.filter(version=version, tab=tab).exists():
        raise Refused(404, "not_found")
    return _grids(version, str(tab))


@api("POST", visitors=True)
def file_restore(request, pk):
    version = FileVersion.objects.filter(pk=pk).first()
    if version is None:
        raise Refused(404, "not_found")
    documents.live(request.user, version.node_id, Role.EDIT)
    return JsonResponse(describe_file(boards.restored(version, request.user)))
