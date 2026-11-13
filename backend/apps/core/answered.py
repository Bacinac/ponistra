from asgiref.sync import iscoroutinefunction
from django.utils.decorators import sync_and_async_middleware

HEADER = "Answered-For"


def asked(request) -> str:
    """The path and query as they reached the server, encoded as the browser sent them, so the page
    can tell an answer meant for another request: a proxy on the way has sent one request as
    another sent alongside it (the LAN's Caddy 2.11.2 over HTTP/2)."""
    scope = getattr(request, "scope", None)
    if scope is None or "raw_path" not in scope:
        return request.get_full_path()
    path = scope["raw_path"].decode("latin-1")
    query = scope.get("query_string", b"").decode("latin-1")
    return f"{path}?{query}" if query else path


@sync_and_async_middleware
def answered(get_response):
    if iscoroutinefunction(get_response):

        async def marking(request):
            response = await get_response(request)
            response[HEADER] = asked(request)
            return response

        return marking

    def marked(request):
        response = get_response(request)
        response[HEADER] = asked(request)
        return response

    return marked
