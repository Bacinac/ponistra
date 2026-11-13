"""ActiveSync's binary XML (MS-ASWBXML): each element a byte of its code page, the code pages
standing for the namespaces."""

from collections.abc import Iterator
from dataclasses import dataclass, field

SWITCH_PAGE, END, STR_I, STR_T, OPAQUE = 0x00, 0x01, 0x03, 0x83, 0xC3
CONTENT = 0x40
# Version 1.3, no public identifier, UTF-8, no string table.
HEADER = bytes([0x03, 0x01, 0x6A, 0x00])

PAGES: dict[str, tuple[int, tuple[str, ...]]] = {
    "AirSync": (
        0,
        (
            "Sync",
            "Responses",
            "Add",
            "Change",
            "Delete",
            "Fetch",
            "SyncKey",
            "ClientId",
            "ServerId",
            "Status",
            "Collection",
            "Class",
            "",
            "CollectionId",
            "GetChanges",
            "MoreAvailable",
            "WindowSize",
            "Commands",
            "Options",
            "FilterType",
            "",
            "",
            "Conflict",
            "Collections",
            "ApplicationData",
            "DeletesAsMoves",
            "",
            "Supported",
            "SoftDelete",
            "MIMESupport",
            "MIMETruncation",
            "Wait",
            "Limit",
            "Partial",
            "ConversationMode",
            "MaxItems",
            "HeartbeatInterval",
        ),
    ),
    "Contacts": (
        1,
        (
            "Anniversary",
            "AssistantName",
            "AssistantPhoneNumber",
            "Birthday",
            "Body",
            "BodySize",
            "BodyTruncated",
            "Business2PhoneNumber",
            "BusinessAddressCity",
            "BusinessAddressCountry",
            "BusinessAddressPostalCode",
            "BusinessAddressState",
            "BusinessAddressStreet",
            "BusinessFaxNumber",
            "BusinessPhoneNumber",
            "CarPhoneNumber",
            "Categories",
            "Category",
            "Children",
            "Child",
            "CompanyName",
            "Department",
            "Email1Address",
            "Email2Address",
            "Email3Address",
            "FileAs",
            "FirstName",
            "Home2PhoneNumber",
            "HomeAddressCity",
            "HomeAddressCountry",
            "HomeAddressPostalCode",
            "HomeAddressState",
            "HomeAddressStreet",
            "HomeFaxNumber",
            "HomePhoneNumber",
            "JobTitle",
            "LastName",
            "MiddleName",
            "MobilePhoneNumber",
            "OfficeLocation",
            "OtherAddressCity",
            "OtherAddressCountry",
            "OtherAddressPostalCode",
            "OtherAddressState",
            "OtherAddressStreet",
            "PagerNumber",
            "RadioPhoneNumber",
            "Spouse",
            "Suffix",
            "Title",
            "WebPage",
            "YomiCompanyName",
            "YomiFirstName",
            "YomiLastName",
            "CompressedRTF",
            "Picture",
            "Alias",
            "WeightedRank",
        ),
    ),
    "Email": (
        2,
        (
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "DateReceived",
            "",
            "DisplayTo",
            "Importance",
            "MessageClass",
            "Subject",
            "Read",
            "To",
            "Cc",
            "From",
            "ReplyTo",
            "AllDayEvent",
            "Categories",
            "Category",
            "DtStamp",
            "EndTime",
            "InstanceType",
            "BusyStatus",
            "Location",
            "MeetingRequest",
            "Organizer",
            "RecurrenceId",
            "Reminder",
            "ResponseRequested",
            "Recurrences",
            "Recurrence",
            "Recurrence_Type",
            "Recurrence_Until",
            "Recurrence_Occurrences",
            "Recurrence_Interval",
            "Recurrence_DayOfWeek",
            "Recurrence_DayOfMonth",
            "Recurrence_WeekOfMonth",
            "Recurrence_MonthOfYear",
            "StartTime",
            "Sensitivity",
            "TimeZone",
            "GlobalObjId",
            "ThreadTopic",
            "",
            "",
            "",
            "InternetCPID",
            "Flag",
            "Status",
            "ContentClass",
            "FlagType",
            "CompleteTime",
            "DisallowNewTimeProposal",
        ),
    ),
    "Calendar": (
        4,
        (
            "TimeZone",
            "AllDayEvent",
            "Attendees",
            "Attendee",
            "Email",
            "Name",
            "Body",
            "BodyTruncated",
            "BusyStatus",
            "Categories",
            "Category",
            "Rtf",
            "DtStamp",
            "EndTime",
            "Exception",
            "Exceptions",
            "Deleted",
            "ExceptionStartTime",
            "Location",
            "MeetingStatus",
            "OrganizerEmail",
            "OrganizerName",
            "Recurrence",
            "Type",
            "Until",
            "Occurrences",
            "Interval",
            "DayOfWeek",
            "DayOfMonth",
            "WeekOfMonth",
            "MonthOfYear",
            "Reminder",
            "Sensitivity",
            "Subject",
            "StartTime",
            "UID",
            "AttendeeStatus",
            "AttendeeType",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "DisallowNewTimeProposal",
            "ResponseRequested",
            "AppointmentReplyTime",
            "ResponseType",
            "CalendarType",
            "IsLeapMonth",
            "FirstDayOfWeek",
            "OnlineMeetingConfLink",
            "OnlineMeetingExternalLink",
            "ClientUid",
        ),
    ),
    "FolderHierarchy": (
        7,
        (
            "Folders",
            "Folder",
            "DisplayName",
            "ServerId",
            "ParentId",
            "Type",
            "",
            "Status",
            "",
            "Changes",
            "Add",
            "Delete",
            "Update",
            "SyncKey",
            "FolderCreate",
            "FolderDelete",
            "FolderUpdate",
            "FolderSync",
            "Count",
        ),
    ),
    "Contacts2": (
        12,
        (
            "CustomerId",
            "GovernmentId",
            "IMAddress",
            "IMAddress2",
            "IMAddress3",
            "ManagerName",
            "CompanyMainPhone",
            "AccountName",
            "NickName",
            "MMS",
        ),
    ),
    "Ping": (
        13,
        (
            "Ping",
            "AutdState",
            "Status",
            "HeartbeatInterval",
            "Folders",
            "Folder",
            "Id",
            "Class",
            "MaxFolders",
        ),
    ),
    "Provision": (
        14,
        (
            "Provision",
            "Policies",
            "Policy",
            "PolicyType",
            "PolicyKey",
            "Data",
            "Status",
            "RemoteWipe",
            "EASProvisionDoc",
        ),
    ),
    "Search": (
        15,
        (
            "Search",
            "",
            "Store",
            "Name",
            "Query",
            "Options",
            "Range",
            "Status",
            "Response",
            "Result",
            "Properties",
            "Total",
        ),
    ),
    "GAL": (
        16,
        (
            "DisplayName",
            "Phone",
            "Office",
            "Title",
            "Company",
            "Alias",
            "FirstName",
            "LastName",
            "HomePhone",
            "MobilePhone",
            "EmailAddress",
        ),
    ),
    "AirSyncBase": (
        17,
        (
            "BodyPreference",
            "Type",
            "TruncationSize",
            "AllOrNone",
            "",
            "Body",
            "Data",
            "EstimatedDataSize",
            "Truncated",
            "Attachments",
            "Attachment",
            "DisplayName",
            "FileReference",
            "Method",
            "ContentId",
            "ContentLocation",
            "IsInline",
            "NativeBodyType",
            "ContentType",
            "Preview",
            "BodyPartPreference",
            "BodyPart",
            "Status",
        ),
    ),
    "Settings": (
        18,
        (
            "Settings",
            "Status",
            "Get",
            "Set",
            "Oof",
            "OofState",
            "StartTime",
            "EndTime",
            "OofMessage",
            "AppliesToInternal",
            "AppliesToExternalKnown",
            "AppliesToExternalUnknown",
            "Enabled",
            "ReplyMessage",
            "BodyType",
            "DevicePassword",
            "Password",
            "DeviceInformation",
            "Model",
            "IMEI",
            "FriendlyName",
            "OS",
            "OSLanguage",
            "PhoneNumber",
            "UserInformation",
            "EmailAddresses",
            "SmtpAddress",
            "UserAgent",
            "EnableOutboundSMS",
            "MobileOperator",
        ),
    ),
    "MeetingResponse": (
        8,
        (
            "CalendarId",
            "CollectionId",
            "MeetingResponse",
            "RequestId",
            "Request",
            "Result",
            "Status",
            "UserResponse",
            "",
            "InstanceId",
            "",
            "ProposedStartTime",
            "ProposedEndTime",
            "SendResponse",
        ),
    ),
    "ItemOperations": (
        20,
        (
            "ItemOperations",
            "Fetch",
            "Store",
            "Options",
            "Range",
            "Total",
            "Properties",
            "Data",
            "Status",
            "Response",
            "Version",
            "Schema",
            "Part",
            "EmptyFolderContents",
            "DeleteSubFolders",
            "UserName",
            "Password",
            "Move",
            "DstFldId",
            "ConversationId",
            "MoveAlways",
        ),
    ),
    "ComposeMail": (
        21,
        (
            "SendMail",
            "SmartForward",
            "SmartReply",
            "SaveInSentItems",
            "ReplaceMime",
            "",
            "Source",
            "FolderId",
            "ItemId",
            "LongId",
            "InstanceId",
            "Mime",
            "ClientId",
            "Status",
            "AccountId",
        ),
    ),
    "Email2": (
        22,
        (
            "UmCallerID",
            "UmUserNotes",
            "UmAttDuration",
            "UmAttOrder",
            "ConversationId",
            "ConversationIndex",
            "LastVerbExecuted",
            "LastVerbExecutionTime",
            "ReceivedAsBcc",
            "Sender",
            "CalendarType",
            "IsLeapMonth",
            "AccountId",
            "FirstDayOfWeek",
            "MeetingMessageType",
        ),
    ),
}
# Each code page's tokens start at 0x05, the first after the global ones.
TOKENS = {
    (space, name): (page, 0x05 + at)
    for space, (page, names) in PAGES.items()
    for at, name in enumerate(names)
    if name
}
NAMES = {token: key for key, token in TOKENS.items()}


class Malformed(ValueError):
    pass


@dataclass
class Element:
    """An element as `Namespace:Name`, holding elements or a value: text to send, or the bytes
    the server sent, as a message's MIME must keep them."""

    tag: str
    children: list[Element] = field(default_factory=list)
    value: str | bytes | None = None

    @property
    def name(self) -> str:
        return self.tag.split(":", 1)[1]

    @property
    def string(self) -> str:
        if isinstance(self.value, bytes):
            return self.value.decode("utf-8", "replace")
        return self.value or ""

    def __iter__(self) -> Iterator[Element]:
        return iter(self.children)

    def find(self, path: str) -> Element | None:
        """The first element down `path`, its steps names without their namespace."""
        found: Element | None = self
        for step in path.split("/"):
            found = next((child for child in found.children if child.name == step), None)
            if found is None:
                return None
        return found

    def findall(self, path: str) -> list[Element]:
        *parents, last = path.split("/")
        parent = self.find("/".join(parents)) if parents else self
        return [child for child in parent.children if child.name == last] if parent else []

    def text(self, path: str, default: str = "") -> str:
        found = self.find(path)
        return default if found is None or found.value is None else found.string


def element(tag: str, *content: Element | str | bytes | int) -> Element:
    """`element("AirSync:SyncKey", "0")`, or one holding the elements given."""
    if len(content) == 1 and isinstance(content[0], str | bytes | int):
        given = content[0]
        return Element(tag, value=str(given) if isinstance(given, int) else given)
    return Element(tag, [child for child in content if isinstance(child, Element)])


def _number(value: int) -> bytes:
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(out))


def encoded(root: Element) -> bytes:
    out = bytearray(HEADER)
    page = None

    def put(node: Element) -> None:
        nonlocal page
        space, name = node.tag.split(":", 1)
        node_page, token = TOKENS[(space, name)]
        if node_page != page:
            out.extend((SWITCH_PAGE, node_page))
            page = node_page
        if node.value is None and not node.children:
            out.append(token)
            return
        out.append(token | CONTENT)
        if isinstance(node.value, bytes):
            out.append(OPAQUE)
            out.extend(_number(len(node.value)))
            out.extend(node.value)
        elif node.value is not None:
            out.append(STR_I)
            out.extend(node.value.encode() + b"\x00")
        for child in node.children:
            put(child)
        out.append(END)

    put(root)
    return bytes(out)


def decoded(data: bytes) -> Element:
    at = 0

    def byte() -> int:
        nonlocal at
        if at >= len(data):
            raise Malformed("wbxml ends early")
        at += 1
        return data[at - 1]

    def number() -> int:
        value = 0
        for _ in range(5):
            given = byte()
            value = (value << 7) | (given & 0x7F)
            if not given & 0x80:
                return value
        raise Malformed("wbxml number too long")

    byte()
    if number() == 0:
        number()
    number()
    size = number()
    table = data[at : at + size]
    at += size

    page = 0
    root = Element("_:root")
    stack = [root]
    while at < len(data):
        token = byte()
        if token == SWITCH_PAGE:
            page = byte()
        elif token == END:
            if len(stack) == 1:
                raise Malformed("wbxml closes more than it opens")
            stack.pop()
        elif token == STR_I:
            end = data.find(b"\x00", at)
            if end < 0:
                raise Malformed("wbxml string without its end")
            stack[-1].value = data[at:end]
            at = end + 1
        elif token == STR_T:
            start = number()
            end = table.find(b"\x00", start)
            stack[-1].value = table[start:end]
        elif token == OPAQUE:
            size = number()
            stack[-1].value = data[at : at + size]
            at += size
        else:
            space, name = NAMES.get((page, token & 0x3F), (f"page{page}", f"x{token & 0x3F:02x}"))
            node = Element(f"{space}:{name}")
            stack[-1].children.append(node)
            if token & CONTENT:
                stack.append(node)
    if len(stack) != 1 or len(root.children) != 1:
        raise Malformed("wbxml leaves an element open")
    return root.children[0]
