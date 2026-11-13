"""A small ActiveSync server for the tests: one mailbox in memory, answering the commands PONISTRA
sends as MS-ASCMD describes them, and where the mailbox is a Domino mail file, the URL commands
that read its directory and its calendar."""

import base64
import json
import threading
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import count
from urllib.parse import parse_qs, unquote, urlsplit

from apps.mail.activesync import sync, wbxml
from apps.mail.activesync.wbxml import element as e
from apps.mail.models import Account

from .mox import letter

USER, PASSWORD = "ana@example.com", "Kamen-Most-Rijeka-72"
# How long a Ping waits for a change here, in place of the heartbeat.
HOLD = 1
WBXML = "application/vnd.ms-sync.wbxml"
MAIL_SERVER = "CN=Inbox/O=Test"
MAIL_FILE = "mail\\ana"


@dataclass
class Item:
    mime: bytes
    date: str
    read: bool = False
    flagged: bool = False
    # A contact's ApplicationData, by tag, in place of a message's.
    contact: dict[str, str] | None = None


@dataclass
class Mailbox:
    # server id: (name, type, parent)
    folders: dict[str, tuple[str, str, str]] = field(
        default_factory=lambda: {
            "1": ("Inbox", "2", "0"),
            "2": ("Sent Items", "5", "0"),
            "3": ("Projekti", "12", "1"),
            "4": ("Calendar", "8", "0"),
            "5": ("Contacts", "9", "0"),
        }
    )
    items: dict[str, dict[str, Item]] = field(default_factory=dict)
    policy: str = ""
    wipe: bool = False
    commands: list[str] = field(default_factory=list)
    # What the client was last told of each folder: its key, the items and their flags.
    told: dict[str, tuple[int, dict[str, tuple[bool, bool]]]] = field(default_factory=dict)
    numbers: count = field(default_factory=lambda: count(100))
    lock: threading.Lock = field(default_factory=threading.Lock)
    host: str = ""
    # Requests received, by which an open Ping knows a later one came, as HCL Traveler does.
    received: int = 0
    # The MIME of each message sent.
    sent: list[bytes] = field(default_factory=list)
    # Each answer to a meeting, by the elements of its request.
    responses: list[dict[str, str]] = field(default_factory=list)
    # The organisation's directory: each person's display name, address and further details.
    people: list[tuple] = field(default_factory=list)
    # Where the server is Domino, the entries of the user's mail file calendar: each {unid,
    # start, end, texts} as its ($Calendar) view gives them.
    domino: list[dict] | None = None
    # Whether Domino refuses to open the mail file.
    sealed: bool = False

    def put(self, folder: str, item: Item) -> str:
        with self.lock:
            server_id = f"{folder}:{next(self.numbers)}"
            self.items.setdefault(folder, {})[server_id] = item
        return server_id

    def changed(self, folder: str) -> bool:
        """Whether the folder holds what the client was not told yet."""
        told = self.told.get(folder, (0, {}))[1]
        items = self.items.get(folder, {})
        return told.keys() != items.keys() or any(
            told[server_id] != (item.read, item.flagged) for server_id, item in items.items()
        )


class Handler(BaseHTTPRequestHandler):
    mailbox: Mailbox

    def log_message(self, *_):
        pass

    def version_string(self) -> str:
        return "Lotus-Domino" if self.mailbox.domino is not None else "Microsoft-IIS/10.0"

    def _signed_in(self) -> bool:
        given = self.headers.get("Authorization", "")
        if given != "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode():
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="eas"')
            self.end_headers()
            return False
        return True

    def do_OPTIONS(self):
        if self._signed_in():
            self.send_response(200)
            self.send_header("MS-ASProtocolVersions", "2.5,12.0,12.1,14.0,14.1")
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_GET(self):
        box = self.mailbox
        path = unquote(urlsplit(self.path).path)
        if box.domino is not None and not self._signed_in():
            return
        if box.domino is None:
            entries = None
        elif path == "/names.nsf/($Users)":
            entries = [
                _entry("", MailServer=[MAIL_SERVER], MailFile=[MAIL_FILE], **{"$38": [USER]})
            ]
        elif path == "/names.nsf/($Servers)":
            entries = [_entry("", ServerName=[MAIL_SERVER], SMTPFullHostDomain=[box.host])]
        elif path == "/mail/ana.nsf/($Calendar)" and not box.sealed:
            entries = [
                _entry(
                    each["unid"],
                    times={"$134": each["start"], "$144": each["start"], "$146": each["end"]},
                    **{"$147": each["texts"]},
                )
                for each in box.domino
            ]
        else:
            entries = None
        data = json.dumps({"viewentry": entries}).encode() if entries is not None else b""
        self.send_response(200 if entries is not None else 403 if box.sealed else 404)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _answer(self, root=None, status: int = 200):
        data = wbxml.encoded(root) if root is not None else b""
        self.send_response(status)
        if data:
            self.send_header("Content-Type", WBXML)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self._signed_in():
            return
        command = parse_qs(urlsplit(self.path).query)["Cmd"][0]
        given = wbxml.decoded(self.rfile.read(int(self.headers["Content-Length"])))
        box = self.mailbox
        with box.lock:
            box.commands.append(command)
            box.received += 1
        if command == "Ping":
            answer = self._Ping(given)
            return self._answer(answer) if answer is not None else self._answer(status=409)
        with box.lock:
            if command == "Provision":
                return self._answer(self._provision(given))
            if not box.policy or self.headers.get("X-MS-PolicyKey") != box.policy or box.wipe:
                return self._answer(status=449)
            answer = getattr(self, f"_{command}")(given)
        self._answer(answer)

    def _provision(self, given):
        box = self.mailbox
        if given.find("RemoteWipe") is not None:
            box.wipe = False
            return e("Provision:Provision", e("Provision:Status", "1"))
        if box.wipe:
            return e("Provision:Provision", e("Provision:Status", "1"), e("Provision:RemoteWipe"))
        acknowledged = given.text("Policies/Policy/Status") == "1"
        key = "222" if acknowledged else "111"
        if acknowledged:
            box.policy = key
        return e(
            "Provision:Provision",
            e("Provision:Status", "1"),
            e(
                "Provision:Policies",
                e(
                    "Provision:Policy",
                    e("Provision:PolicyType", "MS-EAS-Provisioning-WBXML"),
                    e("Provision:Status", "1"),
                    e("Provision:PolicyKey", key),
                ),
            ),
        )

    def _FolderSync(self, given):
        box = self.mailbox
        if given.text("SyncKey") not in ("0", "1"):
            return e("FolderHierarchy:FolderSync", e("FolderHierarchy:Status", "9"))
        added = (
            [
                e(
                    "FolderHierarchy:Add",
                    e("FolderHierarchy:ServerId", server_id),
                    e("FolderHierarchy:ParentId", parent),
                    e("FolderHierarchy:DisplayName", name),
                    e("FolderHierarchy:Type", kind),
                )
                for server_id, (name, kind, parent) in box.folders.items()
            ]
            if given.text("SyncKey") == "0"
            else []
        )
        return e(
            "FolderHierarchy:FolderSync",
            e("FolderHierarchy:Status", "1"),
            e("FolderHierarchy:SyncKey", "1"),
            e("FolderHierarchy:Changes", e("FolderHierarchy:Count", str(len(added))), *added),
        )

    def _Sync(self, given):
        box = self.mailbox
        collection = given.find("Collections/Collection")
        folder, key = collection.text("CollectionId"), int(collection.text("SyncKey"))
        told_key, told = box.told.get(folder, (0, {}))
        if key != told_key:
            return self._collection(folder, "3", "0")
        items = box.items.setdefault(folder, {})
        options = collection.find("Options")
        whole = options is not None and options.text("MIMESupport") == "2"
        commands = []
        more = False
        if key and collection.text("GetChanges", "1") == "1":
            window = int(collection.text("WindowSize") or 100)
            for server_id in [each for each in told if each not in items]:
                commands.append(e("AirSync:Delete", e("AirSync:ServerId", server_id)))
                del told[server_id]
            for server_id, item in items.items():
                flags = (item.read, item.flagged)
                if server_id not in told:
                    if len(commands) >= window:
                        more = True
                        break
                    commands.append(
                        e("AirSync:Add", e("AirSync:ServerId", server_id), self._data(item, whole))
                    )
                elif told[server_id] != flags:
                    commands.append(
                        e(
                            "AirSync:Change",
                            e("AirSync:ServerId", server_id),
                            e("AirSync:ApplicationData", *self._flags(item)),
                        )
                    )
                told[server_id] = flags
        box.told[folder] = (key + 1, told)
        extra = []
        if commands:
            extra.append(e("AirSync:Commands", *commands))
        if more:
            extra.append(e("AirSync:MoreAvailable"))
        return self._collection(folder, "1", str(key + 1), *extra)

    def _collection(self, folder, status, key, *more):
        return e(
            "AirSync:Sync",
            e(
                "AirSync:Collections",
                e(
                    "AirSync:Collection",
                    e("AirSync:SyncKey", key),
                    e("AirSync:CollectionId", folder),
                    e("AirSync:Status", status),
                    *more,
                ),
            ),
        )

    def _flags(self, item):
        flag = (
            e("Email:Flag", e("Email:Status", "2"), e("Email:FlagType", "Flag for follow up"))
            if item.flagged
            else e("Email:Flag")
        )
        return [e("Email:Read", "1" if item.read else "0"), flag]

    def _data(self, item, whole: bool):
        """The item as a phone asks for it: its MIME where it says it reads MIME, else the plain
        text, which a client keeping mail whole has no use for."""
        if item.contact is not None:
            return e(
                "AirSync:ApplicationData",
                *(
                    e(tag, *v) if isinstance(v, list) else e(tag, v)
                    for tag, v in item.contact.items()
                ),
            )
        body = (
            [e("AirSyncBase:Type", "4"), e("AirSyncBase:Data", item.mime)]
            if whole
            else [e("AirSyncBase:Type", "1"), e("AirSyncBase:Data", "Pozdrav")]
        )
        return e(
            "AirSync:ApplicationData",
            e("Email:DateReceived", item.date),
            *self._flags(item),
            e("AirSyncBase:Body", *body),
        )

    def _MeetingResponse(self, given):
        request = given.find("Request")
        self.mailbox.responses.append({each.name: request.text(each.name) for each in request})
        return e(
            "MeetingResponse:MeetingResponse",
            e(
                "MeetingResponse:Result",
                e("MeetingResponse:RequestId", request.text("RequestId")),
                e("MeetingResponse:Status", "1"),
                e("MeetingResponse:CalendarId", request.text("RequestId")),
            ),
        )

    def _SendMail(self, given):
        """Sends the message as it is given and keeps it in Sent Items."""
        box = self.mailbox
        mime = given.find("Mime").value
        box.sent.append(mime)
        if given.find("SaveInSentItems") is not None:
            server_id = f"2:{next(box.numbers)}"
            box.items.setdefault("2", {})[server_id] = Item(
                mime=mime, date="2026-10-24T09:00:00.000Z", read=True
            )
        return None

    def _Search(self, given):
        """Finds the people of the directory whose names hold the query, as Traveler does."""
        query = given.text("Store/Query").casefold()
        found = [person for person in self.mailbox.people if query in person[0].casefold()]
        results = [
            e(
                "Search:Result",
                e(
                    "Search:Properties",
                    e("GAL:DisplayName", name),
                    e("GAL:EmailAddress", address),
                    *(e(f"GAL:{tag}", value) for tag, value in (details or [{}])[0].items()),
                ),
            )
            for name, address, *details in found
        ]
        return e(
            "Search:Search",
            e("Search:Status", "1"),
            e(
                "Search:Response",
                e("Search:Store", e("Search:Status", "1"), *results, e("Search:Total", len(found))),
            ),
        )

    def _Ping(self, given):
        box = self.mailbox
        watched = [each.text("Id") for each in given.findall("Folders/Folder")]
        until = time.monotonic() + HOLD
        received = box.received
        while True:
            with box.lock:
                if box.received != received:
                    return None
                if box.wipe or self.headers.get("X-MS-PolicyKey") != box.policy:
                    return e("Ping:Ping", e("Ping:Status", "142"))
                changed = [folder for folder in watched if box.changed(folder)]
            if changed or time.monotonic() > until:
                break
            time.sleep(0.05)
        if not changed:
            return e("Ping:Ping", e("Ping:Status", "1"))
        return e(
            "Ping:Ping",
            e("Ping:Status", "2"),
            e("Ping:Folders", *[e("Ping:Folder", folder) for folder in changed]),
        )


def _entry(unid: str, times: dict[str, str] | None = None, **texts: list[str]) -> dict:
    """A view entry as Domino's ReadViewEntries gives it in JSON."""
    columns = [
        {"@name": name, "textlist": {"text": [{"0": each} for each in values]}}
        for name, values in texts.items()
    ] + [{"@name": name, "datetime": {"0": value}} for name, value in (times or {}).items()]
    return {"@unid": unid, "entrydata": columns}


def serve(mailbox: Mailbox) -> ThreadingHTTPServer:
    handler = type("Bound", (Handler,), {"mailbox": mailbox})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def contact(**data: str) -> Item:
    """A contact, its fields named as in the Contacts page."""
    return Item(mime=b"", date="", contact={f"Contacts:{tag}": v for tag, v in data.items()})


def appointment(**data) -> Item:
    """An appointment, its fields named as in the Calendar page; a value that is a list holds
    elements, as Attendees and Recurrence do."""
    return Item(
        mime=b"",
        date="",
        contact={tag if ":" in tag else f"Calendar:{tag}": v for tag, v in data.items()},
    )


def item(subject: str, message: EmailMessage | None = None, **flags) -> Item:
    message = message or letter(subject)
    return Item(mime=message.as_bytes(), date="2026-10-23T09:30:00.000Z", **flags)


def everything(account: Account) -> None:
    with sync.session(account, PASSWORD) as client:
        sync.everything(client, account)
