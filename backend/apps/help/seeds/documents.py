import io
from datetime import timedelta

from django.utils import timezone
from docx import Document
from openpyxl import Workbook
from pycrdt import Doc

from apps.blobs import store
from apps.collab.models import Update
from apps.comments.models import Comment
from apps.content import operations
from apps.content.sheets import Sheets
from apps.documents.models import Favourite, Node
from apps.documents.notes import paragraphs
from apps.documents.views import created
from apps.imports.create import document
from apps.versions import history
from apps.versions.models import Version

from . import files
from .company import Company, Seeded, picture

# Named as the site lead's phone names them, the same in every language.
PHOTOS = (
    ("round-table.jpg", "IMG_2041"),
    ("monstera.jpg", "IMG_2044"),
    ("pendant-lights.jpg", "IMG_2047"),
    ("wood-samples.jpg", "IMG_2052"),
    ("living-room.jpg", "IMG_2058"),
)

HANDBOOK = {
    "hr": (
        "Pravilnik o radu",
        (
            ("Radno vrijeme", "Ured radi od 8 do 16 sati; srijedom se radi od kuće."),
            ("Godišnji odmor", "Zahtjev se šalje Maji najmanje dva tjedna unaprijed."),
            ("Oprema", "Laptop i telefon zadužuju se kod Maje, a vraćaju na odlasku."),
        ),
    ),
    "en": (
        "Office handbook",
        (
            (
                "Working hours",
                "The office is open from 8 am to 4 pm; on Wednesdays we work from home.",
            ),
            ("Annual leave", "Send the request to Maja at least two weeks ahead."),
            ("Equipment", "Maja hands out laptops and phones, which go back when you leave."),
        ),
    ),
}

PRICES = (
    ("Usluga / Service", "Jedinica / Unit", "EUR"),
    ("Projekt interijera / Interior design", "m²", 18),
    ("Vizualizacija / Rendering", "kom / pc", 350),
    ("Nadzor montaže / Site supervision", "h", 45),
    ("Savjetovanje / Consulting", "h", 60),
)


def _stored(data: bytes):
    return store.put(io.BytesIO(data))


def _imported(data: bytes, parent: Node | None, title: str, user) -> Node:
    made = document(_stored(data), parent, title, user)
    Node.objects.filter(pk=made.pk).update(imported=None)
    made.tabs.filter(parent=None, title="").update(title=made.title)
    return made


def _file(parent: Node, title: str, data: bytes, extension: str, user) -> Node:
    return created(parent, Node.Kind.FILE, title, _stored(data), user, extension=extension)


def _dated(node: Node, days: int) -> None:
    at = timezone.now() - timedelta(days=days)
    Node.objects.filter(pk=node.pk).update(created_at=at, updated_at=at)


def _handbook(language: str) -> tuple[str, bytes]:
    title, sections = HANDBOOK[language]
    made = Document()
    made.add_heading(title, level=0)
    for heading, text in sections:
        made.add_heading(heading, level=1)
        made.add_paragraph(text)
    written = io.BytesIO()
    made.save(written)
    return title, written.getvalue()


def _prices() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "2026"
    for row in PRICES:
        sheet.append(list(row))
    sheet.column_dimensions["A"].width = 40
    sheet.column_dimensions["B"].width = 16
    written = io.BytesIO()
    book.save(written)
    return written.getvalue()


def shared(company: Company) -> None:
    """What the company's own folders hold, the same for every language's account: the
    handbook in both languages the office speaks, the client's site photos and the price list."""
    by = company.people["marija"]
    home = company.folders["Lipa Studio"]
    for language in ("hr", "en"):
        title, data = _handbook(language)
        _dated(_imported(data, home, title, by), 120)
    meridian = created(company.folders["Clients"], Node.Kind.FOLDER, "Meridian", None, by)
    for name, title in PHOTOS:
        _dated(_file(meridian, title, picture(name), "jpg", company.people["tomislav"]), 12)
    _dated(_imported(_prices(), company.folders["Finance"], "Cjenik / Price list 2026", by), 60)


def _remarked_by(node: Node, company: Company) -> None:
    """The proposal's comments, read from Word under their authors' names, as the colleagues'
    own."""
    for comment in Comment.objects.filter(thread__tab__document=node).exclude(outside_author=""):
        for key in company.people:
            if company.name(key) == comment.outside_author:
                comment.author = company.people[key]
                comment.outside_author = ""
                comment.save(update_fields=["author", "outside_author"])


def _revised(node: Node, say, user, company: Company) -> None:
    """A first draft by the designer, then the version sent to the client with one more
    paragraph."""
    designer = company.people["ana"]
    history.contributed(node.pk, designer.pk)
    first = history.take(node, designer, say("Prvi nacrt", "First draft"))
    tab = node.tabs.filter(parent=None).order_by("position").first()
    doc = Doc()
    doc.apply_update(history.state_of(tab.room))
    added = say(
        "Cijene vrijede 30 dana od datuma ponude. Plaćanje u dva obroka: 40 % pri potpisu "
        "ugovora, ostatak pri primopredaji.",
        "The prices are valid for 30 days from the date of the proposal. Payment in two "
        "instalments: 40% at the signing of the contract, the rest at the handover.",
    )
    written = operations.write(doc, Sheets({}), paragraphs(added, ""))
    Update.objects.create(document=node, tab=tab, room=tab.room, data=written.update)
    history.contributed(node.pk, user.pk)
    sent = history.take(node, user, say("Poslano klijentu", "Sent to the client"))
    now = timezone.now()
    Version.objects.filter(pk=first.pk).update(created_at=now - timedelta(days=27))
    Version.objects.filter(pk=sent.pk).update(created_at=now - timedelta(days=25))


def seed(seeded: Seeded) -> None:
    say, user, company = seeded.say, seeded.user, seeded.company
    projects = created(None, Node.Kind.FOLDER, say("Projekti", "Projects"), None, user)
    archive = created(projects, Node.Kind.FOLDER, say("Arhiva", "Archive"), None, user)
    proposal = _imported(files.proposal(say), projects, say(*files.PROPOSAL["title"]), user)
    _remarked_by(proposal, company)
    _revised(proposal, say, user, company)
    budget = _imported(files.budget(say), projects, say("Proračun ureda", "Office budget"), user)
    deck = _imported(
        files.deck(say), projects, say("Prezentacija za Meridian", "Meridian presentation"), user
    )
    minutes = _imported(
        files.minutes(
            say,
            [company.name(key) for key in ("marija", "ana", "ivan")] + [user.get_full_name()],
            [
                (
                    "Ponuda za uređenje ureda ide klijentu do petka.",
                    "The office fit-out proposal goes to the client by Friday.",
                ),
                ("Ivan naručuje uzorke parketa.", "Ivan orders the parquet samples."),
                (
                    "Ana priprema vizualizacije sale za sastanke.",
                    "Ana prepares the renderings of the meeting room.",
                ),
            ],
        ),
        projects,
        say("Zapisnik sa sastanka", "Meeting minutes"),
        user,
    )
    terms = _file(
        projects,
        say("Uvjeti poslovanja", "Terms of business"),
        files.pdf(
            [
                [
                    (20, say("Uvjeti poslovanja", "Terms of business")),
                    (12, "Lipa Studio d.o.o., Ilica 1000, 10000 Zagreb"),
                    (12, ""),
                    (
                        12,
                        say("1. Ponuda vrijedi 30 dana.", "1. The proposal is valid for 30 days."),
                    ),
                    (12, say("2. Plaćanje u dva obroka.", "2. Payment in two instalments.")),
                    (
                        12,
                        say(
                            "3. Jamstvo na radove dvije godine.",
                            "3. A two-year warranty on the work.",
                        ),
                    ),
                    (
                        12,
                        say(
                            "4. Izmjene opsega dogovaraju se pisano.",
                            "4. Changes of scope are agreed in writing.",
                        ),
                    ),
                ]
            ]
        ),
        "pdf",
        user,
    )
    apex = _file(
        archive,
        say("Primopredaja – Apex", "Handover – Apex"),
        files.pdf(
            [
                [
                    (20, say("Zapisnik o primopredaji", "Handover record")),
                    (12, say("Projekt: ured Apex, Zagreb", "Project: Apex office, Zagreb")),
                    (
                        12,
                        say(
                            "Radovi su završeni bez primjedbi.", "The work is done without remarks."
                        ),
                    ),
                ]
            ]
        ),
        "pdf",
        user,
    )
    for node, days in (
        (proposal, 25),
        (budget, 6),
        (deck, 3),
        (minutes, 2),
        (terms, 90),
        (apex, 40),
        (archive, 40),
    ):
        _dated(node, days)
    for node in (proposal, budget):
        Favourite.objects.create(user=user, node=node)
    seeded.made.update(projects=projects, proposal=proposal, budget=budget, minutes=minutes)
