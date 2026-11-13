import inspect
import json
import uuid
from datetime import timedelta
from functools import wraps

from asgiref.sync import sync_to_async
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware

from apps.users.sessions import CONFIRMED, CONFIRMED_FOR, PASSKEY_DUE, fresh

_csrf = CsrfViewMiddleware(lambda request: None)


class Refused(Exception):
    def __init__(self, status: int, error: str):
        super().__init__(error)
        self.status = status
        self.error = error


def _bearer(request) -> str:
    scheme, _, secret = request.headers.get("Authorization", "").partition(" ")
    return secret.strip() if scheme.lower() == "bearer" else ""


def _held(secret: str):
    # app_passwords' own views are made with this decorator.
    from apps.users.app_passwords import holder

    return holder(secret) if secret else None


def api(
    *methods: str,
    signed_in: bool = True,
    passkey_due: bool = False,
    device: bool = False,
    confirmed: tuple[str, ...] = (),
    confirmed_for: timedelta = CONFIRMED_FOR,
    visitors: bool = False,
):
    """A JSON view, for a signed-in user unless told otherwise, and one who still has to add the
    passkey the policy holds them to only where `passkey_due` says so: wrong method, no session
    and Refused all answer as JSON instead of Django's HTML error pages. Where `device` says so,
    the phone's own app signs in too, with an app password as its bearer token (D26), and the
    view finds it in `request.device`, None for a browser's session. The methods `confirmed`
    names wait until the user has shown who they are within `confirmed_for` (D33). Someone
    visiting from outside (D39) reaches only the views `visitors` opens to them."""

    def signed(request, secret: str, held) -> JsonResponse | None:
        """The device's user in place of the session's, or the session's own CSRF check, which a
        bearer token has no need of: no browser sends one by itself."""
        request.device = held
        if held is not None:
            request.user = held.user
            return None
        if secret:
            return JsonResponse({"error": "not_signed_in"}, status=401)
        return _csrf.process_view(request, None, (), {})

    def refusal(request, user, due: bool, since: str | None) -> JsonResponse | None:
        if request.method not in methods:
            return JsonResponse({"error": "method_not_allowed"}, status=405)
        if signed_in and not user.is_authenticated:
            return JsonResponse({"error": "not_signed_in"}, status=401)
        if signed_in and user.visitor and not visitors:
            return JsonResponse({"error": "visitors_not_allowed"}, status=403)
        if signed_in and due and not passkey_due:
            return JsonResponse({"error": "passkey_required"}, status=403)
        if request.method in confirmed and not fresh(since, confirmed_for):
            return JsonResponse({"error": "confirm_required"}, status=403)
        return None

    def decorate(view):
        # A view that waits on another server is a coroutine: Django runs every synchronous view
        # on one shared thread, which such a wait would hold for everyone.
        if inspect.iscoroutinefunction(view):

            @wraps(view)
            async def waiting(request, *args, **kwargs):
                request.user = await request.auser()
                due = await request.session.aget(PASSKEY_DUE, False)
                since = await request.session.aget(CONFIRMED)
                if device:
                    secret = _bearer(request)
                    held = await sync_to_async(_held)(secret) if secret else None
                    if refused := signed(request, secret, held):
                        return refused
                if refused := refusal(request, request.user, due, since):
                    return refused
                try:
                    return await view(request, *args, **kwargs)
                except Refused as refused:
                    return JsonResponse({"error": refused.error}, status=refused.status)

            if device:
                waiting.csrf_exempt = True
            return waiting

        @wraps(view)
        def wrapper(request, *args, **kwargs):
            due = request.session.get(PASSKEY_DUE, False)
            since = request.session.get(CONFIRMED)
            if device:
                secret = _bearer(request)
                if refused := signed(request, secret, _held(secret)):
                    return refused
            if refused := refusal(request, request.user, due, since):
                return refused
            try:
                return view(request, *args, **kwargs)
            except Refused as refused:
                return JsonResponse({"error": refused.error}, status=refused.status)

        if device:
            wrapper.csrf_exempt = True
        return wrapper

    return decorate


def body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        raise Refused(400, "invalid_json") from None
    if not isinstance(data, dict):
        raise Refused(400, "invalid_json")
    return data


def optional_id(value) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise Refused(400, "invalid_id") from None
