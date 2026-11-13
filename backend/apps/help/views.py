from django.http import JsonResponse

from apps.core.api import Refused, api

from . import library


@api("GET", visitors=True)
def index(request):
    language = library.language_of(request.GET.get("lang"), request.user)
    return JsonResponse(library.contents(request.user, language))


@api("GET", visitors=True)
def article(request, section: str, slug: str):
    identifier = f"{section}/{slug}"
    language = library.language_of(request.GET.get("lang"), request.user)
    page = library.article(request.user, identifier, language)
    if page is None:
        raise Refused(404, "not_found")
    return JsonResponse(
        {"id": identifier, "title": page.title, "summary": page.summary, "html": page.html}
    )
