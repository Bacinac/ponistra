"""Where a phone finds the user's address book and calendars: the well-known addresses it starts
from, and the principal that names the user's homes (RFC 6764, RFC 5397)."""

from django.http import HttpResponseNotFound, HttpResponsePermanentRedirect
from django.views.decorators.csrf import csrf_exempt

from apps.calendar import caldav
from apps.contacts import carddav

from .protocol import (
    answer,
    asked,
    common,
    d,
    dav,
    depth,
    element,
    href,
    multistatus,
    parsed,
    privileges,
    unsupported,
)
from .protocol import (
    principal as principal_path,
)

ROOT = "/dav/"


@csrf_exempt
def known(request):
    return HttpResponsePermanentRedirect(ROOT)


def _root(user) -> dict:
    return {
        **common(user),
        d("resourcetype"): lambda: [element(d("collection"))],
        d("displayname"): lambda: "Ponistra",
    }


def _principal(user) -> dict:
    return {
        **common(user),
        **carddav.homes(user),
        **caldav.homes(user),
        d("resourcetype"): lambda: [element(d("principal"))],
        d("displayname"): lambda: user.get_full_name() or user.email,
        d("principal-URL"): lambda: [href(principal_path(user))],
        d("current-user-privilege-set"): lambda: privileges("read"),
    }


@dav
def root(request, user):
    if request.method != "PROPFIND":
        return unsupported()
    names = asked(parsed(request))
    found = [answer(ROOT, _root(user), names)]
    if depth(request):
        found.append(answer(principal_path(user), _principal(user), names))
    return multistatus(found)


@dav
def principal(request, user, pk):
    if int(pk) != user.pk:
        return HttpResponseNotFound()
    if request.method != "PROPFIND":
        return unsupported()
    return multistatus([answer(principal_path(user), _principal(user), asked(parsed(request)))])
