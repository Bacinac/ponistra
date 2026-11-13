"""The people outside the company the account works with: clients, suppliers and craftsmen, each
with a drawn picture. Their numbers are made up; the UK ones are from Ofcom's range for drama."""

from apps.contacts import cards
from apps.contacts.vcard import FIELDS, Card

from .company import Seeded, avatar

# Given, family, organisation, title, address, phone, starred.
PEOPLE = (
    (
        "Nikola",
        "Barić",
        "Meridian d.o.o.",
        ("Direktor", "Managing director"),
        "nikola.baric@example.com",
        "+385 99 0000 101",
        True,
    ),
    (
        "Sanja",
        "Petrović",
        "Meridian d.o.o.",
        ("Voditeljica ureda", "Office manager"),
        "sanja.petrovic@example.com",
        "+385 99 0000 102",
        False,
    ),
    (
        "Marko",
        "Vidović",
        "Hrast namještaj d.o.o.",
        ("Prodaja", "Sales"),
        "marko.vidovic@example.org",
        "+385 99 0000 103",
        True,
    ),
    (
        "Iva",
        "Matić",
        "Svjetlo d.o.o.",
        ("Projektantica rasvjete", "Lighting designer"),
        "iva.matic@example.org",
        "+385 99 0000 104",
        False,
    ),
    (
        "Josip",
        "Kralj",
        "Elektro Kralj",
        ("Električar", "Electrician"),
        "josip.kralj@example.net",
        "+385 99 0000 105",
        False,
    ),
    (
        "Goran",
        "Šimunović",
        "Biro Linija",
        ("Arhitekt", "Architect"),
        "goran.simunovic@example.net",
        "+385 99 0000 106",
        False,
    ),
    (
        "Laura",
        "Bennett",
        "Bennett Acoustics Ltd",
        ("Akustičarka", "Acoustic consultant"),
        "laura.bennett@example.net",
        "+44 20 7946 0123",
        True,
    ),
    (
        "Petar",
        "Lovrić",
        "Zeleni kut",
        ("Biljke za urede", "Office plants"),
        "petar.lovric@example.com",
        "+385 99 0000 108",
        False,
    ),
)


def seed(seeded: Seeded) -> None:
    say = seeded.say
    for at, (given, family, organisation, title, address, phone, starred) in enumerate(PEOPLE):
        fields = dict.fromkeys(FIELDS, "")
        fields.update(
            name=f"{given} {family}",
            given=given,
            family=family,
            organisation=organisation,
            title=say(*title),
        )
        points = [
            {"kind": "email", "label": say("posao", "work"), "value": address, "parts": []},
            {"kind": "phone", "label": say("mobitel", "mobile"), "value": phone, "parts": []},
        ]
        card = Card(fields=fields, points=points, photo=avatar(at + 3))
        cards.made(seeded.user.pk, card, starred=starred)
