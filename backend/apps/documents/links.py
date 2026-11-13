"""A link's page read once the link is made or its address changes (D31): the title the page
gives itself, what it says of itself and its site's icon, from public hosts alone."""

import io
import ipaddress
import re
from html.parser import HTMLParser
from logging import getLogger
from urllib.parse import urljoin, urlsplit, urlunsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from lxml import etree
from PIL import Image

from apps.blobs import store
from apps.blobs.models import Blob
from apps.core import fetch
from apps.core.api import Refused
from apps.core.asyncdb import database, drain, notify
from apps.reader import client

from . import printing
from .models import Node

log = getLogger(__name__)

CHANNEL = "links"
LONGEST = Node._meta.get_field("href").max_length
PAGES = ("text/html", "application/xhtml+xml")
# As much of a page as its head is looked for in, and of an icon's bytes.
PAGE_BYTES = 512 * 1024
ICON_BYTES = 256 * 1024
# The icon's side: a tile of the page of links shows it at 28 points, a row at 18, on screens of
# two pixels a point and more.
SIDE = 64
# An icon larger than this is a picture, or bytes made to swell once decoded.
ICON_PIXELS = 1024 * 1024
# An image the user picks for an icon may be a logo of any size, which is drawn small.
GIVEN_BYTES = 8 * 1024 * 1024
GIVEN_PIXELS = 25_000_000
DESCRIBED = 1000
TRIED_ICONS = 3
SAFE_XML = etree.XMLParser(resolve_entities=False, no_network=True)
# Where Homepage finds the icons it names (its src/components/resolvedicon.jsx).
ICON_SETS = {
    "mdi": "https://cdn.jsdelivr.net/npm/@mdi/svg@latest/svg/{}.svg",
    "si": "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{}.svg",
}
SELFHST = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/{1}/{0}.{1}"
DASHBOARD = "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/{1}/{0}.{1}"
TINT = re.compile(r"-(#[0-9a-f]{6})$", re.IGNORECASE)
# Homepage paints an icon of a set in its theme's colour; a drawn icon keeps one, a grey that
# reads on light tiles and dark alike.
MONOCHROME = "#808080"
CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?([\w-]+)""", re.IGNORECASE)


def wake() -> None:
    """Has the reader look for new links once the current transaction commits."""
    notify(CHANNEL)


def address_of(data: dict) -> str:
    """The page a link was given, of the web and no longer than a link keeps; one given without
    its scheme is taken as https."""
    href = data.get("href")
    if not isinstance(href, str):
        raise Refused(400, "invalid_href")
    href = href.strip()
    if "://" not in href:
        href = f"https://{href}"
    try:
        parts = urlsplit(href)
    except ValueError:
        raise Refused(400, "invalid_href") from None
    if len(href) > LONGEST or parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise Refused(400, "invalid_href")
    return href


def site_of(href: str) -> str:
    """What a link is called until its page is read: its host."""
    return urlsplit(href).hostname.removeprefix("www.")


class Head(HTMLParser):
    """What a page's head says of the page: its title, its description and its icons."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.named: dict[str, str] = {}
        self.icons: list[tuple[int, str]] = []
        self.titling = False

    def handle_starttag(self, tag, attrs):
        given = {name: value or "" for name, value in attrs}
        if tag == "title" and not self.title:
            self.titling = True
        elif tag == "meta":
            name = (given.get("property") or given.get("name") or "").lower()
            if name in ("og:title", "description", "og:description"):
                self.named.setdefault(name, given.get("content", ""))
        elif tag == "link" and given.get("href"):
            rel = given.get("rel", "").lower().split()
            drawing = "image/svg" in given.get("type", "") or given["href"].endswith(".svg")
            if "icon" in rel:
                side = SIDE if drawing else _side(given.get("sizes", ""))
                self.icons.append((side, given["href"]))
            elif "apple-touch-icon" in rel:
                self.icons.append((1, given["href"]))

    def handle_endtag(self, tag):
        if tag == "title":
            self.titling = False

    def handle_data(self, data):
        if self.titling:
            self.title += data

    def described(self) -> tuple[str, str, list[str]]:
        """The page's title, its description and its icons, the best first."""
        title = " ".join((self.title or self.named.get("og:title", "")).split())
        description = self.named.get("description") or self.named.get("og:description", "")
        icons = [href for _, href in sorted(self.icons, key=lambda icon: -icon[0])]
        return title, " ".join(description.split())[:DESCRIBED], icons


def _side(sizes: str) -> int:
    """The largest side an icon's sizes declare; one that declares none ranks above a touch
    icon, which is drawn for a home screen, not for a tab."""
    sides = [int(side) for side in re.findall(r"(\d+)x\d+", sizes.lower())]
    return max(sides, default=2)


def _text(raw: bytes, media_type: str) -> str:
    declared = re.search(r"charset=([\w-]+)", media_type, re.IGNORECASE)
    written = CHARSET.search(raw[:4096])
    charset = declared[1] if declared else written[1].decode() if written else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _page(href: str) -> tuple[str, str, list[str]]:
    """The page's title, its description and the addresses of the icons to try, the best few
    it names and the site's /favicon.ico last."""
    with fetch.fetched(href, accept=", ".join(PAGES)) as body:
        media_type = body.media_type
        raw = body.read(PAGE_BYTES) if media_type.split(";")[0].strip().lower() in PAGES else b""
        url = body.url
    head = Head()
    head.feed(_text(raw, media_type))
    title, description, icons = head.described()
    tried = [urljoin(url, icon) for icon in icons[:TRIED_ICONS]] + [urljoin(url, "/favicon.ico")]
    return title, description, list(dict.fromkeys(tried))


def _above(href: str) -> list[str]:
    """The icons of the site a level up, as a company's mail host bears the company's own; none
    for a host that is a domain alone or an address."""
    parts = urlsplit(href)
    host = parts.hostname or ""
    try:
        ipaddress.ip_address(host)
        return []
    except ValueError:
        pass
    labels = host.split(".")
    if len(labels) < 3:
        return []
    above = ".".join(labels[1:]) + (f":{parts.port}" if parts.port else "")
    try:
        return _page(urlunsplit((parts.scheme, above, "/", "", "")))[2]
    except fetch.Unreachable:
        return []


def _icon(url: str) -> Blob | None:
    """The icon at the address, or None where there is none to draw."""
    try:
        with fetch.fetched(url) as body:
            return drawn(body.read(ICON_BYTES + 1))
    except fetch.Unreachable:
        return None


def tinted(raw: bytes, colour: str) -> bytes:
    """An SVG icon of one colour painted in the colour given; any other image as it is."""
    return client.ask("tint", raw, colour=colour)


def painted(raw: bytes, colour: str) -> bytes:
    """`tinted`, in the reader."""
    try:
        svg = etree.fromstring(raw, SAFE_XML)
    except etree.XMLSyntaxError:
        return raw
    if not isinstance(svg.tag, str) or etree.QName(svg).localname != "svg":
        return raw
    svg.set("fill", colour)
    return etree.tostring(svg)


def drawn(raw: bytes, given: bool = False) -> Blob | None:
    """An icon's bytes drawn as a PNG of SIDE pixels at most, or None where they draw none; an
    SVG is drawn by the printer's browser."""
    if len(raw) > (GIVEN_BYTES if given else ICON_BYTES):
        return None
    if store.sniff(raw[:1024]) == "image/svg+xml":
        try:
            raw = printing.drawn(raw, SIDE, SIDE)
        except printing.Unavailable:
            log.warning("links: the printer drew no icon", exc_info=True)
            return None
    drawn = client.ask("icon", raw, given=given)
    return None if drawn is None else store.put(io.BytesIO(drawn))


def icon(raw: bytes, given: bool) -> bytes | None:
    """An icon's image as a PNG of SIDE pixels at most, or None where it draws none; in the
    reader."""
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > (GIVEN_PIXELS if given else ICON_PIXELS):
                return None
            drawn = image.convert("RGBA")
    except OSError, Image.DecompressionBombError, ValueError:
        return None
    drawn.thumbnail((SIDE, SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    drawn.save(out, "PNG", optimize=True)
    return out.getvalue()


def icon_source(name: str) -> tuple[str, str]:
    """Where an icon named as Homepage names its icons is found, and the colour one of a set is
    painted in: an address, a name of dashboard-icons, `sh-` selfh.st, `mdi-` Material Design
    and `si-` Simple Icons, these two with an optional `-#rrggbb`."""
    name = name.strip()
    if name.startswith(("http://", "https://")):
        return name, ""
    prefix, _, rest = name.partition("-")
    if prefix in ICON_SETS and rest:
        tint = TINT.search(rest)
        named = rest[: tint.start()] if tint else rest
        return ICON_SETS[prefix].format(named.removesuffix(".svg")), tint[1] if tint else MONOCHROME
    if prefix == "sh" and rest:
        extension = next((each for each in ("svg", "webp") if rest.endswith(f".{each}")), "png")
        named = rest.removesuffix(".svg").removesuffix(".webp").removesuffix(".png")
        return SELFHST.format(named, extension), ""
    extension = next((each for each in ("svg", "webp") if name.endswith(f".{each}")), "png")
    return DASHBOARD.format(name.removesuffix(f".{extension}"), extension), ""


def given_icon(given: object) -> Blob:
    """The icon the user gives a link: an image they uploaded, or one named as Homepage names
    its icons."""
    icon = None
    if isinstance(given, dict) and isinstance(given.get("blob"), str):
        blob = Blob.objects.filter(pk=given["blob"]).first()
        if blob is None:
            raise Refused(400, "unknown_file")
        if blob.size <= GIVEN_BYTES:
            icon = drawn(store.path_of(blob.sha256).read_bytes(), given=True)
    elif isinstance(given, str) and given.strip() and len(given) <= LONGEST:
        url, tint = icon_source(given)
        try:
            with fetch.fetched(url) as body:
                raw = body.read(ICON_BYTES + 1)
        except fetch.Unreachable:
            raw = b""
        icon = raw and drawn(tinted(raw, tint) if tint else raw)
    else:
        raise Refused(400, "invalid_icon")
    if not icon:
        raise Refused(422, "icon_unreadable")
    return icon


def read(link: Node, claimed) -> None:
    """Keeps what the link's page says of itself where the link was given no name, description
    or icon of its own, unless it was given another page while it was read; of a page that
    cannot be reached, behind a sign-in say, the site's icon alone; where the site has none, the
    icon of the site a level up."""
    try:
        title, description, icons = _page(link.href)
    except fetch.Unreachable:
        log.info("links: %s could not be read", link.href)
        title, description, icons = "", "", [urljoin(link.href, "/favicon.ico")]
    icon = None
    if not link.icon_id:
        icon = next(filter(None, map(_icon, icons)), None)
        icon = icon or next(filter(None, map(_icon, _above(link.href))), None)
    same = Node.objects.filter(pk=link.pk, href=link.href, read_at=claimed)
    same.filter(description="").update(description=description)
    if icon:
        same.filter(icon=None).update(icon=icon)
    if title:
        same.filter(follows_text=True).update(title=title[:200])


def read_next() -> bool:
    """Reads the page of one link waiting; False when none is. The link is claimed before its
    page is fetched, so that a slow host holds no row."""
    claimed = timezone.now()
    with transaction.atomic():
        waiting = Node.objects.filter(kind=Node.Kind.LINK, read_at=None, trashed_at=None)
        link = waiting.select_for_update(skip_locked=True).first()
        if link is None:
            return False
        Node.objects.filter(pk=link.pk).update(read_at=claimed)
    read(link, claimed)
    return True


async def follow() -> None:
    """Reads links' pages while the server runs: as soon as a link is made or given another page,
    and in a sweep every LINK_SWEEP for whatever a lost notification left."""
    await drain(CHANNEL, database(read_next, own_thread=True), settings.LINK_SWEEP, log)
