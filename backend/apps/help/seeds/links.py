"""The account's page of links in two groups, each with a drawn icon, read already so that no
page is fetched for them."""

import io

from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from apps.documents import launcher, links
from apps.documents.models import Node
from apps.documents.views import arranged, new_link

from .company import TONES, Seeded

LINKS = (
    (("Država", "Government"), "https://gov.hr", "e-Građani"),
    (
        ("Država", "Government"),
        "https://www.porezna-uprava.hr",
        ("Porezna uprava", "Tax Administration"),
    ),
    (("Država", "Government"), "https://www.hnb.hr", ("Tečajna lista HNB", "HNB exchange rates")),
    (("Alati", "Tools"), "https://www.openstreetmap.org", "OpenStreetMap"),
    (("Alati", "Tools"), "https://www.wikipedia.org", "Wikipedia"),
)


def _icon(letter: str, seed: int) -> bytes:
    tone = TONES[seed % len(TONES)]
    image = Image.new("RGB", (128, 128), tuple(int(tone[at : at + 2], 16) for at in (0, 2, 4)))
    draw = ImageDraw.Draw(image)
    draw.text((64, 66), letter, fill="white", font=ImageFont.load_default(76), anchor="mm")
    written = io.BytesIO()
    image.save(written, "PNG")
    return written.getvalue()


def seed(seeded: Seeded) -> None:
    say, user = seeded.say, seeded.user
    place = launcher.folder_of(user) or launcher.new_place(user, "links")
    for at, (group, href, title) in enumerate(LINKS):
        named = title if isinstance(title, str) else say(*title)
        icon = links.drawn(_icon(named[0].upper(), at), given=True)
        with transaction.atomic():
            into = launcher.group_named(place, say(*group), user)
            node = new_link(into, href, named, user)
            Node.objects.filter(pk=node.pk).update(read_at=timezone.now(), icon=icon)
            arranged(into, [node], None)
