"""vCards as phones send and read them (RFC 2426, RFC 6350): a contact written as vCard 3.0, which
an iPhone and DAVx5 both read, and taken from 3.0 or 4.0. The lines of a card PONISTRA does not
show are kept as they came, to be given back."""

import base64
import binascii
import re
from dataclasses import dataclass, field

FIELDS = (
    "name",
    "given",
    "family",
    "middle",
    "prefix",
    "suffix",
    "nickname",
    "organisation",
    "department",
    "title",
    "birthday",
    "note",
)
# The vCard label each of ours stands for, and back.
TYPES = {
    "mobile": "CELL",
    "work": "WORK",
    "home": "HOME",
    "fax": "FAX",
    "pager": "PAGER",
    "main": "MAIN",
    "other": "OTHER",
}
# How an iPhone writes the labels of its own list.
APPLE = {
    "_$!<mobile>!$_": "mobile",
    "_$!<work>!$_": "work",
    "_$!<home>!$_": "home",
    "_$!<main>!$_": "main",
    "_$!<other>!$_": "other",
    "_$!<pager>!$_": "pager",
    "_$!<workfax>!$_": "fax",
    "_$!<homefax>!$_": "fax",
    "_$!<homepage>!$_": "",
    "iphone": "mobile",
}
KNOWN = {
    "BEGIN",
    "END",
    "VERSION",
    "PRODID",
    "REV",
    "UID",
    "FN",
    "N",
    "NICKNAME",
    "ORG",
    "TITLE",
    "BDAY",
    "NOTE",
    "EMAIL",
    "TEL",
    "ADR",
    "URL",
    "PHOTO",
    "LABEL",
}
GROUPS = {"KIND": "group", "X-ADDRESSBOOKSERVER-KIND": "group"}
LONGEST = 75
PRODID = "-//PONISTRA//Contacts//EN"
IMAGES = {b"\xff\xd8\xff": "JPEG", b"\x89PNG": "PNG", b"GIF8": "GIF"}


class Malformed(ValueError):
    pass


@dataclass
class Line:
    group: str
    name: str
    params: dict[str, list[str]]
    value: str
    raw: str

    def types(self) -> set[str]:
        found = set()
        for each in self.params.get("TYPE", []):
            found |= {part.strip().lower() for part in each.split(",") if part.strip()}
        return found


@dataclass
class Card:
    fields: dict[str, str] = field(default_factory=lambda: dict.fromkeys(FIELDS, ""))
    points: list[dict] = field(default_factory=list)
    uid: str = ""
    photo: bytes | None = None
    extra: list[str] = field(default_factory=list)
    group: bool = False


def _split(text: str, at: str) -> list[str]:
    """`text` split at each `at` outside double quotes."""
    parts, current, quoted = [], [], False
    for char in text:
        if char == '"':
            quoted = not quoted
        if char == at and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _line(raw: str) -> Line | None:
    head, colon, value = raw.partition(":")
    # A colon inside a quoted parameter is not the one before the value.
    if head.count('"') % 2:
        pieces = _split(raw, ":")
        head, value = pieces[0], ":".join(pieces[1:])
    elif not colon:
        return None
    head_parts = _split(head, ";")
    group, _, name = head_parts[0].rpartition(".")
    params: dict[str, list[str]] = {}
    for param in head_parts[1:]:
        key, equals, given = param.partition("=")
        # vCard 2.1 names a type without TYPE=.
        key, given = (key, given) if equals else ("TYPE", key)
        params.setdefault(key.strip().upper(), []).append(given.strip().strip('"'))
    return Line(group.lower(), name.strip().upper(), params, value, raw)


def unescaped(value: str) -> str:
    return re.sub(r"\\(.)", lambda m: "\n" if m[1] in "nN" else m[1], value)


def _components(value: str) -> list[str]:
    return [unescaped(part) for part in re.split(r"(?<!\\);", value)]


def _quoted_printable(value: str) -> str:
    raw = re.sub(rb"=\r?\n", b"", value.encode())
    decoded = re.sub(rb"=([0-9A-Fa-f]{2})", lambda m: bytes([int(m[1], 16)]), raw)
    return decoded.decode("utf-8", "replace")


def _birthday(line: Line) -> str:
    value = line.value.strip().split("T")[0]
    if line.params.get("X-APPLE-OMIT-YEAR"):
        value = "--" + value[-5:].replace("-", "")
    found = re.fullmatch(r"(\d{4}|--)-?(\d{2})-?(\d{2})", value)
    if not found:
        return ""
    year, month, day = found.groups()
    return f"{year}-{month}-{day}" if year != "--" else f"--{month}-{day}"


def _label(line: Line) -> str:
    types = line.types()
    for given, label in (
        ("cell", "mobile"),
        ("iphone", "mobile"),
        ("fax", "fax"),
        ("pager", "pager"),
        ("main", "main"),
        ("work", "work"),
        ("home", "home"),
        ("other", "other"),
    ):
        if given in types:
            return label
    return ""


def _photo(line: Line) -> bytes | None:
    value = line.value.strip()
    try:
        if value.startswith("data:"):
            meta, _, data = value.partition(",")
            return base64.b64decode(data) if meta.endswith(";base64") else None
        encoding = {each.upper() for each in line.params.get("ENCODING", [])}
        return base64.b64decode(value) if encoding & {"B", "BASE64"} else None
    except binascii.Error, ValueError:
        return None


def address_text(parts: list[str]) -> str:
    box, extended, street, city, region, code, country = (parts + [""] * 7)[:7]
    place = " ".join(each for each in (code, city) if each)
    lines = (box, extended, street, place, region, country)
    return "\n".join(each for each in lines if each)


def lines(text: str) -> list[Line]:
    """The lines of the text's first card, unfolded and decoded."""
    unfolded = re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n").replace("\r", "\n"))
    given = [each for each in unfolded.split("\n") if each.strip()]
    begin = next((i for i, each in enumerate(given) if each.strip().upper() == "BEGIN:VCARD"), None)
    if begin is None:
        raise Malformed("no vCard")
    read = []
    for raw in given[begin + 1 :]:
        line = _line(raw)
        if line is None:
            continue
        if line.name == "END":
            return read
        if "QUOTED-PRINTABLE" in {each.upper() for each in line.params.get("ENCODING", [])}:
            line.value = _quoted_printable(line.value)
        read.append(line)
    raise Malformed("unterminated vCard")


def parsed(text: str) -> Card:
    """The first card of the text."""
    read = lines(text)
    labels = {
        each.group: unescaped(each.value)
        for each in read
        if each.name == "X-ABLABEL" and each.group
    }
    named = {each.group for each in read if each.group and each.name in KNOWN}
    card = Card()
    for line in read:
        if line.name == "X-ABLABEL" and line.group in named:
            continue
        _taken(card, line, labels.get(line.group, "") if line.group else "")
    return card


def _taken(card: Card, line: Line, custom: str) -> None:
    fields, name = card.fields, line.name
    if name in GROUPS and line.value.strip().lower() == GROUPS[name]:
        card.group = True
    if name in ("BEGIN", "VERSION", "PRODID", "REV", "LABEL"):
        return
    if name == "UID":
        card.uid = line.value.strip()
    elif name == "FN":
        fields["name"] = unescaped(line.value).strip()
    elif name == "N":
        parts = (_components(line.value) + [""] * 5)[:5]
        names = ("family", "given", "middle", "prefix", "suffix")
        for key, value in zip(names, parts, strict=True):
            fields[key] = value.strip()
    elif name in ("NICKNAME", "TITLE", "NOTE"):
        key = {"NICKNAME": "nickname", "TITLE": "title", "NOTE": "note"}[name]
        value = unescaped(line.value).strip()
        fields[key] = value.split(",")[0].strip() if name == "NICKNAME" else value
    elif name == "ORG":
        parts = _components(line.value)
        fields["organisation"] = parts[0].strip()
        fields["department"] = "; ".join(each.strip() for each in parts[1:] if each.strip())
    elif name == "BDAY":
        fields["birthday"] = _birthday(line)
    elif name in ("EMAIL", "TEL", "URL"):
        value = unescaped(line.value).strip()
        if name == "TEL" and value.lower().startswith("tel:"):
            value = value[4:]
        if not value:
            return
        kind = {"EMAIL": "email", "TEL": "phone", "URL": "url"}[name]
        label = APPLE.get(custom.lower(), custom) if custom else _label(line)
        card.points.append({"kind": kind, "label": label, "value": value, "parts": []})
    elif name == "ADR":
        parts = [each.strip() for each in (_components(line.value) + [""] * 7)[:7]]
        if any(parts):
            label = APPLE.get(custom.lower(), custom) if custom else _label(line)
            card.points.append(
                {"kind": "address", "label": label, "value": address_text(parts), "parts": parts}
            )
    elif name == "PHOTO":
        photo = _photo(line)
        if photo is None:
            card.extra.append(line.raw)
        else:
            card.photo = photo
    else:
        card.extra.append(line.raw)


def _escaped(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _folded(line: str) -> str:
    """The line broken into pieces of at most 75 octets, none inside a character."""
    data = line.encode()
    if len(data) <= LONGEST:
        return line
    pieces, start, limit = [], 0, LONGEST
    while start < len(data):
        end = min(start + limit, len(data))
        while end < len(data) and data[end] & 0xC0 == 0x80:
            end -= 1
        pieces.append(data[start:end].decode())
        start, limit = end, LONGEST - 1
    return "\r\n ".join(pieces)


def shown_name(fields: dict, points: list[dict]) -> str:
    """The name to show for a contact: its own, else one made from its parts, its firm, its
    address or its number."""
    if fields.get("name"):
        return fields["name"]
    parts = [fields.get(key, "") for key in ("prefix", "given", "middle", "family", "suffix")]
    if made := " ".join(each for each in parts if each):
        return made
    if fields.get("organisation"):
        return fields["organisation"]
    for kind in ("email", "phone"):
        if found := next((p["value"] for p in points if p["kind"] == kind), ""):
            return found
    return ""


def written(card: Card, revision: str = "") -> str:
    """The card as vCard 3.0, its lines ended by CRLF."""
    fields = card.fields
    out = ["BEGIN:VCARD", "VERSION:3.0", f"PRODID:{PRODID}", f"UID:{card.uid}"]
    out.append(f"FN:{_escaped(shown_name(fields, card.points))}")
    parts = [fields.get(key, "") for key in ("family", "given", "middle", "prefix", "suffix")]
    out.append("N:" + ";".join(_escaped(each) for each in parts))
    if fields.get("nickname"):
        out.append(f"NICKNAME:{_escaped(fields['nickname'])}")
    if fields.get("organisation") or fields.get("department"):
        org = [fields.get("organisation", "")]
        org += [each for each in [fields.get("department", "")] if each]
        out.append("ORG:" + ";".join(_escaped(each) for each in org))
    if fields.get("title"):
        out.append(f"TITLE:{_escaped(fields['title'])}")
    if birthday := fields.get("birthday"):
        if birthday.startswith("--"):
            out.append(f"BDAY;X-APPLE-OMIT-YEAR=1604:1604-{birthday[2:]}")
        else:
            out.append(f"BDAY;VALUE=date:{birthday}")
    if fields.get("note"):
        out.append(f"NOTE:{_escaped(fields['note'])}")
    labelled = 0
    for point in card.points:
        name = {"email": "EMAIL", "phone": "TEL", "url": "URL", "address": "ADR"}[point["kind"]]
        label = point.get("label", "")
        types = ["INTERNET"] if name == "EMAIL" else []
        group = ""
        if label in TYPES and not (name == "EMAIL" and label in ("mobile", "fax", "pager")):
            types.append(TYPES[label])
        elif label:
            labelled += 1
            group = f"label{labelled}."
        head = group + name + (f";TYPE={','.join(types)}" if types else "")
        if name == "ADR":
            value = ";".join(_escaped(each) for each in (point.get("parts") or [""] * 7))
        elif name == "URL":
            value = point["value"]
        else:
            value = _escaped(point["value"])
        out.append(f"{head}:{value}")
        if group:
            out.append(f"{group}X-ABLabel:{_escaped(label)}")
    if card.photo:
        kind = next((name for head, name in IMAGES.items() if card.photo.startswith(head)), "JPEG")
        out.append(f"PHOTO;ENCODING=b;TYPE={kind}:{base64.b64encode(card.photo).decode()}")
    if revision:
        out.append(f"REV:{revision}")
    out += card.extra
    out.append("END:VCARD")
    return "".join(_folded(line) + "\r\n" for line in out)
