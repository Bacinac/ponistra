"""Links brought in from elsewhere (D31), each group a folder: the bookmarks a browser exports, in
the format Netscape gave them, and the services and bookmarks of a Homepage dashboard
(gethomepage.dev), with the icons either names."""

import base64
from dataclasses import dataclass, field
from html.parser import HTMLParser
from itertools import count
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import yaml
from django.db import transaction

from apps.blobs import store
from apps.blobs.models import Blob
from apps.core import fetch
from apps.core.api import Refused
from apps.documents import links
from apps.documents.models import Node
from apps.documents.views import created

from .reading import TooLarge, Unreadable

MOST = 10_000
DATA = "data:image/"


@dataclass
class Link:
    href: str
    title: str = ""
    description: str = ""
    # A data address of an image, an address of the web, or the name of a file given beside.
    icon: str = ""
    tint: str = ""


@dataclass
class Folder:
    title: str = ""
    children: list = field(default_factory=list)


class Bookmarks(HTMLParser):
    """The folders and links of an export: an <H3> names the folder whose <DL> follows it, an <A>
    is a link and a <DD> after it says what it is."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Folder()
        self.open: list[Folder] = []
        self.named: Folder | None = None
        self.last: Link | None = None
        self.into: tuple[object, str] | None = None
        self.count = 0

    def _add(self, child) -> None:
        self.count += 1
        if self.count > MOST:
            raise TooLarge
        (self.open[-1] if self.open else self.root).children.append(child)

    def handle_starttag(self, tag, attrs):
        given = {name: value or "" for name, value in attrs}
        self.into = None
        if tag == "dl":
            self.open.append(self.named or (self.open[-1] if self.open else self.root))
            self.named = None
        elif tag == "h3":
            self.last = None
            self.named = Folder()
            self._add(self.named)
            self.into = (self.named, "title")
        elif tag == "a" and urlsplit(given.get("href", "")).scheme.lower() in ("http", "https"):
            self.last = Link(given["href"], icon=given.get("icon", ""))
            self._add(self.last)
            self.into = (self.last, "title")
        elif tag == "dd" and self.last is not None:
            self.into = (self.last, "description")

    def handle_endtag(self, tag):
        if tag in ("h3", "a"):
            self.into = None
        if tag == "dl" and self.open:
            self.open.pop()
            self.into = None

    def handle_data(self, data):
        if self.into is not None:
            held, name = self.into
            setattr(held, name, getattr(held, name) + data)


def bookmarks(text: str) -> Folder:
    reader = Bookmarks()
    reader.feed(text)
    reader.close()
    if not reader.count:
        raise Unreadable
    return reader.root


def _homepage_icon(given: object) -> tuple[str, str]:
    """The icon Homepage shows for the name it is given, a file given beside it by its name."""
    if not isinstance(given, str) or not given.strip():
        return "", ""
    if given.strip().startswith("/"):
        return PurePosixPath(given.strip()).name, ""
    return links.icon_source(given)


def _homepage_link(name: str, given: dict) -> Link | None:
    href = given.get("href")
    if not isinstance(href, str):
        return None
    description = given.get("description")
    icon, tint = _homepage_icon(given.get("icon"))
    return Link(
        href,
        title=name,
        description=description if isinstance(description, str) else "",
        icon=icon,
        tint=tint,
    )


def _homepage_group(entries: object, into: Folder, count: list[int]) -> None:
    """A group's entries: a service maps its name to its fields, a bookmark to a list of them,
    and a group inside it to a list of entries of its own."""
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict) or len(entry) != 1:
            continue
        [(name, given)] = entry.items()
        count[0] += 1
        if count[0] > MOST:
            raise TooLarge
        name = str(name)
        if isinstance(given, dict):
            child = _homepage_link(name, given)
        elif (
            isinstance(given, list)
            and given
            and all(isinstance(each, dict) and "href" in each for each in given)
        ):
            child = _homepage_link(name, given[0])
        else:
            child = Folder(name)
            _homepage_group(given, child, count)
        if child is not None:
            into.children.append(child)


def homepage(text: str) -> Folder:
    """The groups of a Homepage services.yaml or bookmarks.yaml; what else an entry holds, its
    widget and the credentials the widget reads with among it, is not read."""
    try:
        groups = yaml.safe_load(text)
    except yaml.YAMLError:
        raise Unreadable from None
    root = Folder()
    count = [0]
    if isinstance(groups, list):
        for group in groups:
            if isinstance(group, dict) and len(group) == 1:
                [(name, entries)] = group.items()
                folder = Folder(str(name))
                _homepage_group(entries, folder, count)
                root.children.append(folder)
    if not any(isinstance(each, Folder) and each.children for each in root.children):
        raise Unreadable
    return root


def _drawn(link: Link, given: dict[str, Blob], drawn: dict[tuple[str, str], Blob | None]):
    """The link's icon drawn once for every link that names it: from the export itself, from a
    file given beside it or from the web."""
    key = (link.icon, link.tint)
    if not link.icon or key in drawn:
        return drawn.get(key)
    raw = None
    if link.icon.startswith(DATA) and ";base64," in link.icon:
        try:
            raw = base64.b64decode(link.icon.split(",", 1)[1], validate=True)
        except ValueError:
            pass
    elif link.icon.startswith(("http://", "https://")):
        try:
            with fetch.fetched(link.icon) as body:
                raw = body.read(links.ICON_BYTES + 1)
        except fetch.Unreachable:
            pass
    elif link.icon in given:
        raw = store.path_of(given[link.icon].sha256).read_bytes()
    if raw and link.tint:
        raw = links.tinted(raw, link.tint)
    drawn[key] = raw and links.drawn(raw)
    return drawn[key]


def _title(text: str) -> str:
    return " ".join(text.split())[:200]


def _holding(parent: Node, held: dict) -> tuple[dict, set, count]:
    """What the folder holds as the plan grows: its folders by name, its links' addresses and
    the next place in its order, after what was laid out."""
    if parent.pk not in held:
        folders, hrefs, last = {}, set(), -1
        for child in Node.objects.filter(parent=parent, trashed_at=None):
            if child.kind == Node.Kind.FOLDER:
                folders.setdefault(child.title, child)
            elif child.kind == Node.Kind.LINK:
                hrefs.add(child.href)
            if child.position is not None:
                last = max(last, child.position)
        held[parent.pk] = (folders, hrefs, count(last + 1))
    return held[parent.pk]


def _made(
    children: list, parent: Node, made: list[Node], held: dict, icons: dict[str, Blob], drawn: dict
) -> None:
    """The nodes of the children below the parent, each folder before what it holds and all in
    the order given: a folder joins one of its name already there, a link already there by its
    address is not made again, and a folder with no name gives what it holds to its parent."""
    folders, hrefs, at = _holding(parent, held)
    for child in children:
        if isinstance(child, Folder):
            title = _title(child.title)
            if not title:
                _made(child.children, parent, made, held, icons, drawn)
                continue
            if title not in folders:
                folders[title] = Node(
                    parent=parent, kind=Node.Kind.FOLDER, title=title, position=next(at)
                )
                made.append(folders[title])
                held[folders[title].pk] = ({}, set(), count())
            _made(child.children, folders[title], made, held, icons, drawn)
            continue
        try:
            href = links.address_of({"href": child.href})
        except Refused:
            continue
        if href in hrefs:
            continue
        hrefs.add(href)
        title = _title(child.title)
        made.append(
            Node(
                parent=parent,
                kind=Node.Kind.LINK,
                title=title or links.site_of(href),
                follows_text=not title,
                href=href,
                position=next(at),
                description=" ".join(child.description.split())[: links.DESCRIBED],
                icon=_drawn(child, icons, drawn),
            )
        )


def planned(trees: list[Folder], parent: Node, icons: dict[str, Blob]) -> list[Node]:
    """The groups and links of each tree as they join what the folder holds, their icons drawn,
    before anything is kept."""
    made: list[Node] = []
    held = {parent.pk: ({}, set(), count())} if parent._state.adding else {}
    drawn: dict = {}
    for tree in trees:
        _made(tree.children, parent, made, held, icons, drawn)
    return made


def kept(made: list[Node], user) -> int:
    """The planned nodes kept; how many of them are links."""
    with transaction.atomic():
        for node in made:
            node.created_by = node.updated_by = user
        Node.objects.bulk_create(made)
        links.wake()
    return sum(node.kind == Node.Kind.LINK for node in made)


def text_of(source: Blob) -> str:
    return store.path_of(source.sha256).read_bytes().decode("utf-8", errors="replace")


def folder(source: Blob, parent: Node | None, title: str, user) -> Node:
    """A new folder of the export's links, in the folders the export gives them."""
    standing = Node(kind=Node.Kind.FOLDER)
    made = planned([bookmarks(text_of(source))], standing, {})
    with transaction.atomic():
        top = created(parent, Node.Kind.FOLDER, title, None, user)
        for node in made:
            if node.parent is standing:
                node.parent = top
        kept(made, user)
    return top
