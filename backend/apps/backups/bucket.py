"""An S3 bucket reached path-style with a key pair and Signature Version 4, as Cloudflare R2 takes
it. Nothing here reads the installation's settings: a recovery runs it on an empty machine."""

import hashlib
import hmac
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree

import httpx2

REGION = "auto"
EMPTY = hashlib.sha256(b"").hexdigest()
XML = "{http://s3.amazonaws.com/doc/2006-03-01/}"
TIMEOUT = 60
GENERATION = re.compile(r"\d{4}-\d{2}-\d{2}/")


class Unreachable(Exception):
    pass


class Refused(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(f"HTTP {status} {code}")
        self.status, self.code = status, code


@dataclass(frozen=True)
class Item:
    key: str
    modified: datetime


def encoded(value: str, safe: str = "") -> str:
    return quote(value, safe=f"-_.~{safe}")


def keyed(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode(), hashlib.sha256).digest()


class Bucket:
    def __init__(
        self,
        endpoint: str,
        name: str,
        access_key: str,
        secret: str,
        timeout: float = TIMEOUT,
        transport: httpx2.BaseTransport | None = None,
    ):
        self.endpoint, self.name = endpoint.rstrip("/"), name
        self.access_key, self.secret = access_key, secret
        self.client = httpx2.Client(timeout=timeout, transport=transport)

    def signed(self, method: str, key: str, query: dict, digest: str) -> tuple[str, dict]:
        now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = f"/{self.name}/{encoded(key, '/')}" if key else f"/{self.name}"
        search = "&".join(f"{encoded(k)}={encoded(v)}" for k, v in sorted(query.items()))
        headers = {
            "host": urlsplit(self.endpoint).netloc,
            "x-amz-content-sha256": digest,
            "x-amz-date": now,
        }
        names = ";".join(sorted(headers))
        lines = [f"{name}:{headers[name]}" for name in sorted(headers)]
        canonical = "\n".join([method, path, search, *lines, "", names, digest])
        scope = f"{now[:8]}/{REGION}/s3/aws4_request"
        hashed = hashlib.sha256(canonical.encode()).hexdigest()
        signing = f"AWS4{self.secret}".encode()
        for part in (now[:8], REGION, "s3", "aws4_request"):
            signing = keyed(signing, part)
        signature = keyed(signing, f"AWS4-HMAC-SHA256\n{now}\n{scope}\n{hashed}").hex()
        headers["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={names}, Signature={signature}"
        )
        return f"{self.endpoint}{path}{'?' + search if search else ''}", headers

    def request(
        self, method: str, key: str = "", query: dict | None = None, body: bytes = b""
    ) -> httpx2.Response:
        digest = hashlib.sha256(body).hexdigest() if body else EMPTY
        url, headers = self.signed(method, key, query or {}, digest)
        try:
            return self.client.request(method, url, headers=headers, content=body)
        except httpx2.TransportError as error:
            raise Unreachable(f"{self.endpoint}: {error}") from None

    def checked(self, method: str, key: str = "", **options) -> httpx2.Response:
        response = self.request(method, key, **options)
        if not response.is_success:
            raise refused(response)
        return response

    def listed(self, prefix: str, delimiter: str = "") -> tuple[list[Item], list[str]]:
        """The objects under the prefix, and the common prefixes below it where a delimiter is
        given."""
        items, prefixes, token = [], [], ""
        while True:
            query = {"list-type": "2", "prefix": prefix}
            if delimiter:
                query["delimiter"] = delimiter
            if token:
                query["continuation-token"] = token
            root = ElementTree.fromstring(self.checked("GET", query=query).content)
            items += [
                Item(
                    found.findtext(f"{XML}Key"),
                    datetime.fromisoformat(found.findtext(f"{XML}LastModified")),
                )
                for found in root.iter(f"{XML}Contents")
            ]
            prefixes += [
                found.findtext(f"{XML}Prefix") for found in root.iter(f"{XML}CommonPrefixes")
            ]
            if root.findtext(f"{XML}IsTruncated") != "true":
                return items, prefixes
            token = root.findtext(f"{XML}NextContinuationToken")

    def read(self, key: str) -> bytes | None:
        """The object's bytes, none where there is no such object."""
        response = self.request("GET", key)
        if response.status_code == 404:
            return None
        if not response.is_success:
            raise refused(response)
        return response.content

    def put(self, key: str, body: bytes = b"") -> None:
        self.checked("PUT", key, body=body)

    def get(self, key: str, into: Path) -> None:
        url, headers = self.signed("GET", key, {}, EMPTY)
        part = into.with_name(f"{into.name}.part")
        try:
            with self.client.stream("GET", url, headers=headers) as response:
                if not response.is_success:
                    response.read()
                    raise refused(response)
                with part.open("wb") as file:
                    for chunk in response.iter_bytes():
                        file.write(chunk)
        except httpx2.TransportError as error:
            raise Unreachable(f"{self.endpoint}: {error}") from None
        part.rename(into)

    def delete(self, key: str) -> bool:
        """Whether the object went; false where the bucket refuses, as its lock does."""
        response = self.request("DELETE", key)
        if response.is_success:
            return True
        if response.status_code in (403, 409):
            return False
        raise refused(response)

    def generations(self) -> list[str]:
        """The generations the bucket holds, oldest first."""
        _, prefixes = self.listed("", "/")
        return sorted(prefix.rstrip("/") for prefix in prefixes if GENERATION.fullmatch(prefix))


def refused(response: httpx2.Response) -> Refused:
    try:
        code = ElementTree.fromstring(response.content).findtext("Code") or ""
    except ElementTree.ParseError:
        code = ""
    return Refused(response.status_code, code)


def fetch(bucket: Bucket, into: Path) -> str:
    """Downloads the newest generation that holds a snapshot into the empty directory, which is
    then the repository restic opens; returns that generation."""
    for generation in reversed(bucket.generations()):
        items, _ = bucket.listed(f"{generation}/")
        if any(item.key.startswith(f"{generation}/snapshots/") for item in items):
            break
    else:
        raise Refused(404, "NoSnapshot")
    for item in items:
        target = into / item.key.removeprefix(f"{generation}/")
        target.parent.mkdir(parents=True, exist_ok=True)
        bucket.get(item.key, target)
    return generation


if __name__ == "__main__":
    # python -m apps.backups.bucket <directory>, with the recovery kit in the environment.
    fetched = fetch(
        Bucket(
            os.environ["PONISTRA_OFFSITE_ENDPOINT"],
            os.environ["PONISTRA_OFFSITE_BUCKET"],
            os.environ["PONISTRA_OFFSITE_ACCESS_KEY"],
            os.environ["PONISTRA_OFFSITE_SECRET"],
        ),
        Path(sys.argv[1]),
    )
    print(fetched)
