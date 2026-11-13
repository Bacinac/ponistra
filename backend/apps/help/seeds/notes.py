from datetime import timedelta

from django.utils import timezone
from pycrdt import Doc

from apps.collab.models import Update
from apps.content import operations
from apps.content.sheets import Sheets
from apps.documents.launcher import new_place
from apps.documents.models import Favourite, Node
from apps.documents.naming import first_line
from apps.documents.notes import folder_of, paragraphs
from apps.documents.views import created

from .company import Seeded

# The words, a link, days ago and whether the note is kept at hand.
NOTES = (
    (
        (
            "Pitanja za Meridian\nOdvoz starog namještaja?\nParking za kombi tijekom montaže?\n"
            "Tko prima ključeve?",
            "Questions for Meridian\nTaking the old furniture away?\nParking for the van during "
            "the fitting?\nWho takes the keys?",
        ),
        "",
        0,
        True,
    ),
    (
        (
            "Boje zidova\nToplo bijela za otvoreni ured, kadulja za sale.",
            "Wall colours\nWarm white for the open office, sage for the meeting rooms.",
        ),
        "",
        2,
        False,
    ),
    (
        ("Karta gradilišta", "Site map"),
        "https://www.openstreetmap.org/search?query=Trnjanska%20cesta%2C%20Zagreb",
        5,
        False,
    ),
)


def seed(seeded: Seeded) -> None:
    say, user = seeded.say, seeded.user
    place = folder_of(user) or new_place(user, "notes")
    for words, link, days, kept in NOTES:
        text = say(*words)
        note = created(place, Node.Kind.DOCUMENT, first_line(text), None, user)
        Node.objects.filter(pk=note.pk).update(follows_text=True)
        tab = note.tabs.get()
        written = operations.write(Doc(), Sheets({}), paragraphs(text, link))
        Update.objects.create(document=note, tab=tab, room=tab.room, data=written.update)
        at = timezone.now() - timedelta(days=days)
        Node.objects.filter(pk=note.pk).update(created_at=at, updated_at=at)
        if kept:
            Favourite.objects.create(user=user, node=note)
