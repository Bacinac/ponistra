"""The recorder service (S2-5), which only the backend reaches: it joins a meeting's room as a
hidden participant and writes each participant's sound and picture as they were sent, each
microphone's speech also cut into utterances, until it is told to stop or the room stays empty.
What it wrote it keeps until the backend has taken it."""

from collections.abc import Iterator
from contextlib import contextmanager

import httpx2

ADDRESS = "http://recorder:8080"
WAIT = httpx2.Timeout(30, connect=5)
# Stopping waits for every file to be closed and indexed.
STOPPING = httpx2.Timeout(120, connect=5)
CALLBACK = "http://backend:8030/api/meetings/recorded"


class Unavailable(Exception):
    pass


def _client(timeout: httpx2.Timeout = WAIT) -> httpx2.Client:
    return httpx2.Client(base_url=ADDRESS, timeout=timeout, trust_env=False)


def _asked(method: str, path: str, timeout: httpx2.Timeout = WAIT, **sent) -> httpx2.Response:
    try:
        with _client(timeout) as client:
            return client.request(method, path, **sent)
    except httpx2.HTTPError as error:
        raise Unavailable(f"recorder: {error!r}") from error


def start(pk: str, url: str, token: str, key: str) -> None:
    answer = _asked(
        "POST",
        "/recordings",
        json={"id": pk, "url": url, "token": token, "callback": CALLBACK, "key": key},
    )
    if answer.status_code != 201:
        raise Unavailable(f"recorder answered {answer.status_code}: {answer.text[:200]}")


def stop(pk: str) -> dict:
    """Ends the recording and gives what it made."""
    answer = _asked("POST", f"/recordings/{pk}/stop", STOPPING)
    if answer.status_code != 200:
        raise Unavailable(f"recorder answered {answer.status_code}: {answer.text[:200]}")
    return answer.json()


def made(pk: str) -> dict | None:
    """What the recording made, or None where the recorder holds no such recording."""
    answer = _asked("GET", f"/recordings/{pk}")
    if answer.status_code == 404:
        return None
    if answer.status_code != 200:
        raise Unavailable(f"recorder answered {answer.status_code}: {answer.text[:200]}")
    return answer.json()


@contextmanager
def opened(pk: str, name: str) -> Iterator[httpx2.Response]:
    """One of the files the recording made, as a stream."""
    try:
        with _client() as client, client.stream("GET", f"/recordings/{pk}/files/{name}") as answer:
            if answer.status_code != 200:
                raise Unavailable(f"recorder answered {answer.status_code} for {name}")
            yield answer
    except httpx2.HTTPError as error:
        raise Unavailable(f"recorder: {error!r}") from error


def read(pk: str, name: str) -> bytes:
    answer = _asked("GET", f"/recordings/{pk}/files/{name}")
    if answer.status_code != 200:
        raise Unavailable(f"recorder answered {answer.status_code} for {name}")
    return answer.content


def forget(pk: str) -> None:
    answer = _asked("DELETE", f"/recordings/{pk}")
    if answer.status_code not in (204, 404):
        raise Unavailable(f"recorder answered {answer.status_code}: {answer.text[:200]}")
