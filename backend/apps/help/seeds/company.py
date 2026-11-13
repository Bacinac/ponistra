"""Lipa Studio, the made-up interior design firm in Zagreb the help's pictures and the demo show:
its people, its teams, its rooms and its shared folders, made once for every language's account."""

import io
import secrets
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from django.contrib.auth.models import Group
from PIL import Image, ImageDraw

from apps.access import company as shared
from apps.access.models import Role
from apps.calendar.models import Resource
from apps.documents.models import Node
from apps.users.models import User

NAME = "Lipa Studio"
DOMAIN = "lipastudio.test"
MEDIA = Path(__file__).resolve().parent.parent / "media"

TEAMS = ("Management", "Projects", "Design", "Finance", "Site")

# Key, first and last name, teams, administrator; the first two keys are the accounts each
# language's pictures are taken as.
PEOPLE = (
    ("klara", "Klara", "Novak", ("Projects",), False),
    ("sarah", "Sarah", "Miller", ("Projects",), True),
    ("marija", "Marija", "Horvat", ("Management",), True),
    ("maja", "Maja", "Knežević", ("Management",), False),
    ("ivan", "Ivan", "Babić", ("Projects",), False),
    ("ana", "Ana", "Kovač", ("Design",), False),
    ("elena", "Elena", "Rossi", ("Design",), False),
    ("marta", "Marta", "Jurić", ("Finance",), False),
    ("tomislav", "Tomislav", "Marić", ("Site",), False),
    ("dino", "Dino", "Perić", ("Site",), False),
)
ACCOUNTS = {"hr": "klara", "en": "sarah"}

ROOMS = (
    ("Sava", Resource.Kind.ROOM, 12, "1st floor"),
    ("Drava", Resource.Kind.ROOM, 6, "1st floor"),
    ("Kupa", Resource.Kind.ROOM, 4, "Ground floor"),
    ("Projector", Resource.Kind.EQUIPMENT, None, "Office"),
    ("Van ZG 1001 LS", Resource.Kind.VEHICLE, 3, "Courtyard"),
)

# Each shared folder and the teams' roles on it; everyone reads the first.
FOLDERS = (
    ("Lipa Studio", {None: Role.READ, "Management": Role.OWN}),
    ("Clients", {"Management": Role.OWN, "Projects": Role.EDIT, "Design": Role.EDIT}),
    ("Finance", {"Management": Role.OWN, "Finance": Role.EDIT}),
)

TONES = ("2F6B6E", "8A9A5B", "B5654A", "5B6C8F", "A07D3B", "6E5B8A", "3F7D58", "8F5B6E")


@dataclass
class Company:
    people: dict[str, User]
    teams: dict[str, Group]
    rooms: dict[str, Resource]
    folders: dict[str, Node]

    def address(self, key: str) -> str:
        return self.people[key].email

    def name(self, key: str) -> str:
        return self.people[key].get_full_name()


@dataclass
class Seeded:
    """One language's account, what it is seeded with and in which words."""

    user: User
    language: str
    company: Company
    say: Callable[[str, str], str]
    made: dict = field(default_factory=dict)


def picture(name: str) -> bytes:
    return (MEDIA / name).read_bytes()


def avatar(seed: int, size: int = 256) -> bytes:
    """A drawn figure on a tone of its own, standing for a made-up person who has no photo."""
    tone = TONES[seed % len(TONES)]
    back = tuple(int(tone[at : at + 2], 16) for at in (0, 2, 4))
    front = tuple(min(255, part + 70) for part in back)
    image = Image.new("RGB", (size, size), back)
    draw = ImageDraw.Draw(image)
    head = size * 0.19
    middle = size / 2
    draw.ellipse((middle - head, size * 0.2, middle + head, size * 0.2 + 2 * head), fill=front)
    draw.ellipse((size * 0.18, size * 0.62, size * 0.82, size * 1.3), fill=front)
    written = io.BytesIO()
    image.save(written, "PNG")
    return written.getvalue()


def _address(key: str, first: str, last: str) -> str:
    if key in ACCOUNTS.values():
        return f"{key}@{DOMAIN}"
    plain = unicodedata.normalize("NFKD", f"{first}.{last}".lower())
    return f"{plain.encode('ascii', 'ignore').decode()}@{DOMAIN}"


def _person(key: str, first: str, last: str, administrator: bool) -> User:
    return User.objects.create_user(
        _address(key, first, last),
        secrets.token_urlsafe(16),
        first_name=first,
        last_name=last,
        is_staff=administrator,
    )


def founded() -> Company:
    people = {
        key: _person(key, first, last, administrator)
        for key, first, last, _, administrator in PEOPLE
    }
    teams = {name: Group.objects.create(name=name) for name in TEAMS}
    for key, _, _, joined, _ in PEOPLE:
        people[key].groups.add(*(teams[name] for name in joined))
    rooms = {
        name: Resource.objects.create(name=name, kind=kind, capacity=capacity, place=place)
        for name, kind, capacity, place in ROOMS
    }
    by = people["marija"]
    folders = {}
    for title, roles in FOLDERS:
        node = Node.objects.create(
            kind=Node.Kind.FOLDER, title=title, company=True, created_by=by, updated_by=by
        )
        shared.given(
            node, {teams[team].pk if team else None: role for team, role in roles.items()}, by
        )
        folders[title] = node
    return Company(people, teams, rooms, folders)


def found() -> Company | None:
    """The company an earlier run made, or None where none did."""
    keys = {f"{key}@{DOMAIN}" for key in ACCOUNTS.values()}
    if not User.everyone.filter(email__in=keys).exists():
        return None
    people = {
        key: User.everyone.get(email=_address(key, first, last))
        for key, first, last, _, _ in PEOPLE
    }
    return Company(
        people,
        {each.name: each for each in Group.objects.filter(name__in=TEAMS)},
        {each.name: each for each in Resource.objects.filter(name__in=[r[0] for r in ROOMS])},
        {
            each.title: each
            for each in Node.objects.filter(company=True, title__in=[f[0] for f in FOLDERS])
        },
    )
