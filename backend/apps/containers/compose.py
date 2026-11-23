"""A stack is a folder holding a compose file on a Docker host (D55): `docker compose` runs there,
where its files and build contexts are, through the command the host's key is forced to."""

import json
import posixpath
import re
from collections.abc import AsyncIterator

from apps.locations.remote import Failed
from apps.locations.sftp import Target

from .engine import Process

FILES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
VERBS = ("up", "pull", "start", "stop", "restart", "down")
LINE = 64 * 1024
LISTED = 4 * 1024 * 1024


def folder_of(location: str, path: str) -> str:
    """The stack's folder as the account on the host reaches it from its home: the location's
    own folder, which SFTP takes from the home where it is not absolute, and the path below it."""
    base = re.sub(r"^~(/|$)", "", location)
    return posixpath.join(base, path) if base else (path or ".")


def _command(verb: str, folder: str) -> str:
    if "\n" in folder or "\0" in folder:
        raise Failed("invalid_path", 400)
    return f"docker compose {verb} -- {folder}"


async def ran(target: Target, folder: str, verb: str) -> AsyncIterator[dict]:
    """What compose writes as it runs the verb, line by line, and at last how it ended."""
    process = await Process(target, _command(verb, folder)).open()
    try:
        reader = process.reader
        while line := await reader.readline():
            yield {"line": line.decode(errors="replace").rstrip("\r\n")[:LINE]}
        status = await process.ended()
        # compose writes to stdout; what came on stderr is ssh's, the forced command's or cd's.
        if status != 0 and process.said.strip():
            yield {"error": (await process.failure()).error}
        yield {"status": status}
    finally:
        process.close()


def _container(found: dict) -> dict:
    ports = []
    for each in found.get("Publishers") or []:
        if each.get("PublishedPort"):
            host = each.get("URL") or "0.0.0.0"
            ports.append(f"{host}:{each['PublishedPort']}->{each['TargetPort']}/{each['Protocol']}")
    return {
        "id": found.get("ID", ""),
        "name": found.get("Name", ""),
        "service": found.get("Service", ""),
        "image": found.get("Image", ""),
        "state": found.get("State", ""),
        "status": found.get("Status", ""),
        "health": found.get("Health", ""),
        "ports": sorted(set(ports)),
    }


async def listed(target: Target, folder: str) -> tuple[list[dict], list[str]]:
    """The stack's containers as compose finds them, running or not, and what it warned of."""
    process = await Process(target, _command("ps", folder)).open()
    containers: list[dict] = []
    said: list[str] = []
    size = 0
    try:
        while line := await process.reader.readline():
            size += len(line)
            if size > LISTED:
                raise Failed("docker_answer_too_large", 502)
            text = line.decode(errors="replace").strip()
            try:
                found = json.loads(text) if text[:1] in "[{" else None
            except ValueError:
                found = None
            if isinstance(found, dict):
                containers.append(_container(found))
            elif isinstance(found, list):
                containers += [_container(each) for each in found if isinstance(each, dict)]
            elif text:
                said.append(text[:LINE])
        status = await process.ended()
    finally:
        process.close()
    if status != 0:
        if process.said.strip() or not said:
            raise await process.failure()
        raise StackFailed(said)
    return sorted(containers, key=lambda each: (each["service"], each["name"])), said


class StackFailed(Failed):
    """compose refused the stack, as it said why: a compose file it cannot read, most often."""

    def __init__(self, said: list[str]):
        super().__init__("docker_stack_failed", 409)
        self.message = "\n".join(said)
