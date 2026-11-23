"""The workspace's files as PONISTRA reaches them over its HTTP door: one request of the owner
handed on, a file's bytes read as they come, and a project of it as a `Remote` that a transfer
reads from and writes into like any location."""

import logging
from collections.abc import AsyncIterator
from datetime import datetime

import httpx2
from django.conf import settings

from apps.core.api import Refused
from apps.locations.remote import Entry, Stat

logger = logging.getLogger(__name__)

ASKED_WITHIN = 10
# What the workspace says of a command its owner should hear: gone, closed or busy meanwhile.
PASSED = {404, 409}
FILES_PASSED = {400, 403, 404, 409, 413}
FILE_PATH = 4096


def kept_here() -> bool:
    return bool(settings.WORKSPACE) and not settings.WORKSPACE_URL


def address(path: str) -> tuple[str, dict]:
    if not settings.WORKSPACE_TOKEN:
        raise Refused(503, "workspace_not_linked")
    base = "http://workspace:8081" if kept_here() else settings.WORKSPACE_URL.rstrip("/")
    return f"{base}/ponistra/{path}", {"Authorization": f"Bearer {settings.WORKSPACE_TOKEN}"}


def refused(method: str, path: str, answer, passed: set[int]) -> Refused:
    """The workspace's refusal as the owner's, where it is about what they asked; its token
    refused is a fault of the link instead."""
    error = answer.json().get("error", "refused") if answer.status_code in passed else None
    if error and error != "refused":
        return Refused(answer.status_code, error)
    logger.warning("the code workspace refused %s %s: %s", method, path, answer.status_code)
    return Refused(502, "workspace_unreachable")


async def asked(
    method: str,
    path: str,
    payload: dict | None = None,
    params: dict | None = None,
    passed: set[int] = PASSED,
    within: float = ASKED_WITHIN,
) -> dict:
    url, headers = address(path)
    try:
        async with httpx2.AsyncClient(timeout=within, trust_env=False) as client:
            answer = await client.request(method, url, headers=headers, json=payload, params=params)
    except httpx2.HTTPError as error:
        logger.warning("the code workspace did not answer %s %s: %s", method, path, error)
        raise Refused(502, "workspace_unreachable") from error
    if answer.status_code != 200:
        raise refused(method, path, answer, set() if path == "projects" else passed)
    return answer.json()


def placed(given) -> dict:
    """A path within one of the workspace's projects, as the workspace checks it again."""
    folder, path = given.get("folder"), given.get("path", "")
    if not isinstance(path, str) or len(path) > FILE_PATH or "\0" in path:
        raise Refused(400, "invalid_path")
    if not isinstance(folder, str) or not folder.startswith("/") or len(folder) > FILE_PATH:
        raise Refused(400, "invalid_folder")
    return {"folder": folder, "path": path}


async def streamed(where: dict, headers: dict | None = None):
    """The workspace's answer to a file's bytes, open for its body to be read as it comes, with
    the client that must close after it."""
    url, authorised = address("files/raw")
    client = httpx2.AsyncClient(timeout=httpx2.Timeout(ASKED_WITHIN, read=None), trust_env=False)
    try:
        answer = await client.send(
            client.build_request(
                "GET", url, headers={**authorised, **(headers or {})}, params=where
            ),
            stream=True,
        )
    except httpx2.HTTPError as error:
        await client.aclose()
        logger.warning("the code workspace did not send %s: %s", where["path"], error)
        raise Refused(502, "workspace_unreachable") from error
    if answer.status_code not in (200, 206):
        await answer.aread()
        await answer.aclose()
        await client.aclose()
        if answer.status_code == 416:
            raise Refused(416, "unsatisfiable")
        raise refused("GET", "files/raw", answer, FILES_PASSED)
    return client, answer


async def put(where: dict, name: str, parts: AsyncIterator[bytes]) -> dict:
    """A new file of a project from the bytes as they come; one by its name already there is
    refused."""
    url, headers = address("files/put")
    try:
        async with httpx2.AsyncClient(
            timeout=httpx2.Timeout(ASKED_WITHIN, write=None), trust_env=False
        ) as client:
            answer = await client.post(
                url, headers=headers, params={**where, "name": name}, content=parts
            )
    except httpx2.HTTPError as error:
        logger.warning("the code workspace did not take %s: %s", name, error)
        raise Refused(502, "workspace_unreachable") from error
    if answer.status_code != 200:
        raise refused("POST", "files/put", answer, FILES_PASSED)
    return answer.json()


def _modified(given: object) -> datetime | None:
    try:
        return datetime.fromisoformat(given) if isinstance(given, str) else None
    except ValueError:
        return None


def _entry(given: dict) -> Entry:
    modified = _modified(given.get("modified"))
    return Entry(given["name"], given["kind"], given.get("size"), modified, given.get("link"))


def _split(path: str) -> tuple[str, str]:
    above, _, name = path.rpartition("/")
    return above, name


class Workspace:
    """A project of the workspace, its paths from the project's folder."""

    def __init__(self, folder: str):
        self.folder = placed({"folder": folder})["folder"]

    def _at(self, path: str) -> dict:
        return {"folder": self.folder, "path": path}

    async def _asked(self, method: str, path: str, **given) -> dict:
        return await asked(method, path, passed=FILES_PASSED, **given)

    async def listed(self, path: str) -> list[Entry]:
        found = await self._asked("GET", "files", params=self._at(path))
        return [_entry(each) for each in found["entries"]]

    async def stat(self, path: str) -> Entry:
        return (await self.described(path)).entry

    async def described(self, path: str) -> Stat:
        found = await self._asked("GET", "files/stat", params=self._at(path))
        return Stat(
            _entry(found),
            mode=found.get("mode"),
            uid=found.get("uid"),
            gid=found.get("gid"),
            owner=found.get("owner"),
            group=found.get("group"),
        )

    async def chunks(self, path: str, start: int, length: int) -> AsyncIterator[bytes]:
        if length <= 0:
            return
        client, answer = await streamed(
            self._at(path), {"Range": f"bytes={start}-{start + length - 1}"}
        )
        try:
            async for part in answer.aiter_bytes():
                yield part
        finally:
            await answer.aclose()
            await client.aclose()

    async def whole(self, path: str, most: int) -> bytes | None:
        client, answer = await streamed(self._at(path))
        try:
            if int(answer.headers.get("content-length", 0)) > most:
                return None
            return await answer.aread()
        finally:
            await answer.aclose()
            await client.aclose()

    async def put(self, path: str, parts: AsyncIterator[bytes]) -> None:
        above, name = _split(path)
        await put(self._at(above), name, parts)

    async def mkdir(self, path: str) -> None:
        above, name = _split(path)
        await self._asked("POST", "files/folder", {**self._at(above), "name": name})

    async def rename(self, path: str, to: str) -> None:
        await self._asked("POST", "files/rename", {**self._at(path), "to": to})

    async def remove(self, path: str) -> None:
        await self._asked("POST", "files/remove", {"folder": self.folder, "paths": [path]})

    async def chmod(self, path: str, mode: int) -> None:
        await self._asked("POST", "files/mode", {**self._at(path), "mode": mode})

    async def chown(self, path: str, uid: int, gid: int) -> None:
        await self._asked("POST", "files/owner", {**self._at(path), "uid": uid, "gid": gid})

    async def close(self) -> None:
        return None
