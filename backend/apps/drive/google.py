"""Google Drive's API as the account's user sees it (D44): their My Drive and the shared drives
they are a member of, listed whole once and then by the changes since a page token."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO

from apps.mail import signin
from apps.mail.imap import Failed
from apps.mail.models import Account

API = "https://www.googleapis.com/drive/v3"
TIMEOUT = 60
PAGE = 1000
TRIES = 5
FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
NATIVE = "application/vnd.google-apps."
# What each of Google's own formats is taken as; the rest of them have no file to take.
EXPORTS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pptx",
    ),
    "application/vnd.google-apps.drawing": ("application/pdf", "pdf"),
}
FILE = (
    "id,name,mimeType,parents,modifiedTime,md5Checksum,size,driveId,trashed,exportLinks,"
    "capabilities(canDownload),permissionIds,permissions(type,emailAddress,role)"
)
CHANGE = f"changeType,removed,fileId,file({FILE})"
SHARED = {"supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
# Google's limits on requests answer 403 with these reasons, or 429, and pass when waited out.
SLOWED = {"userRateLimitExceeded", "rateLimitExceeded", "backendError", "internalError"}
SCOPE = {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}


class Missing(Exception):
    """Google no longer knows the file or the shared drive, or the user no longer sees it."""


class Expired(Exception):
    """Google no longer knows the page token of the changes."""


def _reason(refused: urllib.error.HTTPError) -> str:
    try:
        error = json.load(refused).get("error", {})
    except ValueError, AttributeError:
        return ""
    found = [each.get("reason", "") for each in error.get("errors", [])]
    found += [each.get("reason", "") for each in error.get("details", [])]
    return next((each for each in found if each), str(error.get("status", "")))


class Google:
    """The account's Drive, with its access token renewed as it ends."""

    def __init__(self, account: Account) -> None:
        self.account = account

    def _open(self, url: str, params: dict | None = None):
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        renewed = False
        for attempt in range(TRIES):
            request = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {signin.drive(self.account)}"}
            )
            try:
                return urllib.request.urlopen(request, timeout=TIMEOUT)
            except urllib.error.HTTPError as refused:
                reason = _reason(refused)
                if refused.code == 401 and not renewed:
                    signin.forget(self.account)
                    renewed = True
                    continue
                if refused.code == 404:
                    raise Missing from None
                if refused.code == 410:
                    raise Expired from None
                if reason in SCOPE:
                    raise Failed("drive_scope") from None
                if (refused.code == 429 or reason in SLOWED or refused.code >= 500) and (
                    attempt < TRIES - 1
                ):
                    time.sleep(2**attempt)
                    continue
                if reason == "accessNotConfigured":
                    raise Failed("drive_disabled") from None
                if refused.code in (401, 403):
                    raise Failed("drive_refused") from None
                raise Failed("drive_unreachable") from None
            except OSError:
                if attempt < TRIES - 1:
                    time.sleep(2**attempt)
                    continue
                raise Failed("drive_unreachable") from None
        raise Failed("drive_unreachable")

    def get(self, path: str, **params) -> dict:
        with self._open(f"{API}/{path}", params) as response:
            try:
                return json.load(response)
            except ValueError:
                raise Failed("drive_unreachable") from None

    def _pages(self, path: str, key: str, **params) -> Iterator[dict]:
        token = None
        while True:
            page = self.get(path, **params, **({"pageToken": token} if token else {}))
            yield from page.get(key, [])
            if not (token := page.get("nextPageToken")):
                return

    def root(self) -> str:
        return self.get("files/root", fields="id")["id"]

    def drives(self) -> list[dict]:
        """The shared drives the user is a member of."""
        return list(
            self._pages("drives", "drives", pageSize=100, fields="nextPageToken,drives(id,name)")
        )

    def drive(self, drive_id: str) -> dict:
        return self.get(f"drives/{urllib.parse.quote(drive_id)}", fields="id,name")

    def start(self, drive_id: str = "") -> str:
        """Where the changes made from now on begin."""
        params = {"driveId": drive_id, "supportsAllDrives": "true"} if drive_id else {}
        return self.get("changes/startPageToken", **params)["startPageToken"]

    def listed(self, drive_id: str = "") -> Iterator[dict]:
        """Every file and folder not in the trash: the shared drive's, or all the user sees,
        which the caller keeps to what lies below their My Drive."""
        params = {
            "q": "trashed = false",
            "pageSize": PAGE,
            "fields": f"nextPageToken,files({FILE})",
        }
        if drive_id:
            params |= {"corpora": "drive", "driveId": drive_id, **SHARED}
        else:
            params |= {"corpora": "user", "spaces": "drive"}
        return self._pages("files", "files", **params)

    def changes(self, token: str, drive_id: str = "") -> tuple[list[dict], str]:
        """The changes since the page token, each file's last only, and the token after them."""
        params = {
            "pageSize": PAGE,
            "includeRemoved": "true",
            "fields": f"nextPageToken,newStartPageToken,changes({CHANGE})",
        }
        if drive_id:
            params |= {"driveId": drive_id, **SHARED}
        else:
            params["restrictToMyDrive"] = "true"
        found: dict[str, dict] = {}
        while True:
            page = self.get("changes", pageToken=token, **params)
            for change in page.get("changes", []):
                if change.get("changeType", "file") == "file" and change.get("fileId"):
                    found[change["fileId"]] = change
            if new := page.get("newStartPageToken"):
                return list(found.values()), new
            token = page["nextPageToken"]

    def file(self, file_id: str) -> dict:
        return self.get(
            f"files/{urllib.parse.quote(file_id)}", fields=FILE, supportsAllDrives="true"
        )

    def permissions(self, file_id: str) -> list[dict]:
        return list(
            self._pages(
                f"files/{urllib.parse.quote(file_id)}/permissions",
                "permissions",
                pageSize=100,
                supportsAllDrives="true",
                fields="nextPageToken,permissions(type,emailAddress,role)",
            )
        )

    @contextmanager
    def content(self, found: dict) -> Iterator[IO[bytes]]:
        """The file's bytes, a Google format's as what it is taken as."""
        kind = found["mimeType"]
        if kind in EXPORTS:
            link = (found.get("exportLinks") or {}).get(EXPORTS[kind][0])
            if not link:
                raise Missing
            response = self._open(link)
        else:
            response = self._open(
                f"{API}/files/{urllib.parse.quote(found['id'])}",
                {"alt": "media", "supportsAllDrives": "true"},
            )
        with response:
            yield response
