import socket

import anyio
import httpx2
import pytest

from apps.mail import fetching

from .test_reading import PNG

NAMES = {
    "cdn.example": "93.184.216.34",
    "inside.example": "192.168.1.12",
    "mapped.example": "::ffff:10.0.0.1",
}


@pytest.fixture(autouse=True)
def resolved(monkeypatch):
    async def getaddrinfo(host, port, type=0):
        family = socket.AF_INET6 if ":" in NAMES.get(host, host) else socket.AF_INET
        if host not in NAMES and not host.replace(".", "").isdigit():
            raise socket.gaierror
        return [(family, type, 6, "", (NAMES.get(host, host), port))]

    monkeypatch.setattr(anyio, "getaddrinfo", getaddrinfo)


def fetched(address, answer):
    asked = []

    def handler(request):
        asked.append(request)
        return answer(request)

    found = anyio.run(fetching.fetched, address, httpx2.MockTransport(handler))
    return found, asked


def test_an_image_comes_from_the_address_checked_with_its_host_named():
    found, [request] = fetched(
        "https://cdn.example/a.png?x=1", lambda _: httpx2.Response(200, content=PNG)
    )
    assert found == (PNG, "image/png")
    assert (request.url.host, request.url.path, request.url.query) == (
        "93.184.216.34",
        "/a.png",
        b"x=1",
    )
    assert request.headers["Host"] == "cdn.example"
    assert request.extensions["sni_hostname"] == "cdn.example"
    assert "Cookie" not in request.headers and "Referer" not in request.headers


@pytest.mark.parametrize(
    "address",
    [
        "https://inside.example/a.png",
        "https://mapped.example/a.png",
        "http://127.0.0.1/a.png",
        "https://nowhere.example/a.png",
        "ftp://cdn.example/a.png",
    ],
)
def test_an_address_inside_a_private_network_or_nowhere_is_not_called(address):
    with pytest.raises(fetching.Unreachable):
        fetched(address, lambda _: httpx2.Response(200, content=PNG))


def test_a_redirect_is_checked_as_the_first_address_was():
    def answer(request):
        if request.url.path == "/a.png":
            return httpx2.Response(302, headers={"Location": "/b.png"})
        if request.url.path == "/b.png":
            return httpx2.Response(301, headers={"Location": "https://inside.example/c.png"})
        return httpx2.Response(200, content=PNG)

    with pytest.raises(fetching.Unreachable):
        fetched("https://cdn.example/a.png", answer)
    found, asked = fetched(
        "https://cdn.example/a.png",
        lambda request: (
            httpx2.Response(302, headers={"Location": "/b.png"})
            if request.url.path == "/a.png"
            else httpx2.Response(200, content=PNG)
        ),
    )
    assert found == (PNG, "image/png") and [r.url.path for r in asked] == ["/a.png", "/b.png"]


def test_what_is_no_image_too_large_or_an_error_is_nothing_to_show(monkeypatch):
    for answer in (
        httpx2.Response(200, content=b"<svg onload='x()'></svg>"),
        httpx2.Response(200, content=b"<html>pixel</html>"),
        httpx2.Response(404, content=PNG),
    ):
        assert fetched("https://cdn.example/a.png", lambda _, given=answer: given)[0] is None
    monkeypatch.setattr(fetching, "LARGEST", len(PNG) - 1)
    assert (
        fetched("https://cdn.example/a.png", lambda _: httpx2.Response(200, content=PNG))[0] is None
    )


def test_a_server_that_does_not_answer_is_unreachable():
    def refused(request):
        raise httpx2.ConnectError("refused", request=request)

    with pytest.raises(fetching.Unreachable):
        fetched("https://cdn.example/a.png", refused)


def test_a_token_names_its_address_for_its_message_alone():
    served = fetching.served(7, "https://cdn.example/a.png")
    token = served.rpartition("/")[2]
    assert served.startswith("/api/mail/messages/7/fetched/")
    assert fetching.address(7, token) == "https://cdn.example/a.png"
    assert fetching.address(8, token) is None
    assert fetching.address(7, token[:-1]) is None
