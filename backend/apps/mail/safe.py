"""A message's HTML as PONISTRA shows it: nothing that runs, nothing from elsewhere until the
reader lets the images in and then only through PONISTRA, and the images the message carries
pointed at its own parts. What the composer writes is held to what the composer makes."""

import re
from collections.abc import Callable
from urllib.parse import unquote

import nh3

TAGS = nh3.ALLOWED_TAGS | {"font", "style"}
# How mail lays itself out: old table attributes as much as CSS.
LOOKS = {
    "align",
    "background",
    "bgcolor",
    "border",
    "cellpadding",
    "cellspacing",
    "class",
    "color",
    "dir",
    "face",
    "height",
    "lang",
    "size",
    "style",
    "title",
    "valign",
    "width",
}
ATTRIBUTES = {tag: set(names) for tag, names in nh3.ALLOWED_ATTRIBUTES.items()} | {"*": LOOKS}
SCHEMES = {"http", "https", "mailto", "tel", "cid", "data"}
REMOTE = re.compile(r"""url\(\s*['"]?\s*(?:https?:)?//|@import\s+['"]\s*(?:https?:)?//""", re.I)
# The images a browser is given to show as they are; any other file is only saved.
SHOWN = {"image/png", "image/jpeg", "image/gif", "image/webp"}
IMAGE = re.compile(r"data:image/(?:png|jpeg|gif|webp);", re.I)
PICTURE = re.compile(r"""url\(\s*(['"]?)\s*((?:https?:)?//[^'"()\s]+)\s*\1\s*\)""", re.I)
STYLES = re.compile(r"(<style[^>]*>)(.*?)(</style>)", re.I | re.S)

WRITTEN_TAGS = {
    *("p", "br", "hr", "blockquote", "ul", "ol", "li"),
    *("strong", "em", "u", "s", "span", "a", "img"),
}
WRITTEN_ATTRIBUTES = {"a": {"href"}, "img": {"src", "alt"}, "span": {"style"}, "p": {"style"}}
WRITTEN_SCHEMES = {"http", "https", "mailto", "tel"}
WRITTEN_LINKS = tuple(f"{scheme}:" for scheme in WRITTEN_SCHEMES)
# Where the composer shows an image the user put in a message or a signature.
WRITTEN_IMAGE = re.compile(r"/api/mail/inline/([0-9a-f]{64})")
UNSHOWN = re.compile(r"<img(?![^>]*\ssrc=)[^>]*>")


def _absolute(address: str) -> str:
    return f"https:{address}" if address.startswith("//") else address


def cleaned(
    markup: str, inline: dict[str, str], away: Callable[[str], str] | None
) -> tuple[str, bool]:
    """The HTML safe to show, and whether it asks for images from elsewhere. `inline` gives where
    each image the message carries is served, by its content id; `away`, once the reader lets the
    images in, where PONISTRA serves one from elsewhere, by its address."""
    remote = bool(REMOTE.search(markup))

    def styled(css: str) -> str:
        return PICTURE.sub(lambda found: f"url('{away(_absolute(found[2]))}')", css)

    # nh3 checks the scheme before this and keeps what it returns, relative or not, so it alone
    # decides where a link or an image may lead.
    def kept(tag: str, attribute: str, value: str) -> str | None:
        nonlocal remote
        if attribute == "style":
            return styled(value) if away else value
        if attribute not in ("src", "background", "href"):
            return value
        address = value.strip()
        lowered = address.lower()
        if lowered.startswith(("http:", "https:", "//")):
            if attribute == "href":
                return address
            remote = True
            return away(_absolute(address)) if away else None
        if attribute == "href":
            return address if lowered.startswith(("mailto:", "tel:")) else None
        if lowered.startswith("cid:"):
            return inline.get(unquote(address[4:]).strip("<>"))
        return address if tag == "img" and IMAGE.match(address) else None

    shown = nh3.clean(
        markup,
        tags=TAGS,
        clean_content_tags={"script"},
        attributes=ATTRIBUTES,
        attribute_filter=kept,
        url_schemes=SCHEMES,
        link_rel="noopener noreferrer",
    )
    if away:
        shown = STYLES.sub(lambda found: found[1] + styled(found[2]) + found[3], shown)
    return shown, remote


def carried(markup: str, cids: list[str]) -> str:
    """A received message's HTML as a reply quotes it or a forward carries it: safe as it is shown,
    its own images by the content ids they travel with again, and those from elsewhere left to the
    recipient's client."""
    return cleaned(markup, {cid: f"cid:{cid}" for cid in cids}, lambda address: address)[0]


def written(markup: str, allowed: Callable[[str], bool]) -> tuple[str, list[str]]:
    """The composer's HTML as it may be kept and sent: only what the composer makes, a text's
    colour, font and size and a paragraph's line spacing its only style, links to the web, an
    address or a number, and those of PONISTRA's images the user may show, whose blobs come
    with it."""
    images: dict[str, None] = {}

    def kept(tag: str, attribute: str, value: str) -> str | None:
        address = value.strip()
        if attribute == "href":
            return address if address.lower().startswith(WRITTEN_LINKS) else None
        if attribute == "src":
            found = WRITTEN_IMAGE.fullmatch(address)
            if found is None or not allowed(found[1]):
                return None
            images[found[1]] = None
            return address
        return value

    shown = nh3.clean(
        markup,
        tags=WRITTEN_TAGS,
        attributes=WRITTEN_ATTRIBUTES,
        attribute_filter=kept,
        url_schemes=WRITTEN_SCHEMES,
        filter_style_properties={"color", "font-family", "font-size", "line-height"},
    )
    return UNSHOWN.sub("", shown), list(images)
