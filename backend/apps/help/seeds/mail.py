"""The account's mail: signed in to the stack's own mail server, which takes what is sent, while
the threads it already holds are kept as they would have arrived."""

from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.core import sealed
from apps.mail import sync, taking
from apps.mail.imap import Login, imap
from apps.mail.models import Account

from . import files
from .company import DOMAIN, Seeded, picture

SERVER = ("mox", 1143, "none")
LOGIN = Login("mox@localhost", password="moxmoxmox")
ZONE = ZoneInfo("Europe/Zagreb")

CLIENT = ("Nikola Barić", "nikola.baric@example.com")
SUPPLIER = ("Marko Vidović", "marko.vidovic@example.org")


def connected(seeded: Seeded) -> Account:
    """The account on the stack's mail server, its folders taken as far as they are now, so that
    only what arrives from here on comes in."""
    user = seeded.user
    account = Account.objects.create(
        owner=user,
        address=user.email,
        username=LOGIN.username,
        name=user.get_full_name(),
        secret=sealed.seal("mail", LOGIN.password),
        imap_host=SERVER[0],
        imap_port=SERVER[1],
        imap_security=SERVER[2],
        smtp_host=SERVER[0],
        smtp_port=1587,
        smtp_security="none",
        default=True,
        state=Account.State.READY,
        synced_at=timezone.now(),
    )
    with imap(*SERVER, LOGIN) as client:
        for source in sync.sources(client, account):
            selected = client.select_folder(source.name, readonly=True)
            source.uidvalidity = selected[b"UIDVALIDITY"]
            source.low = 1
            source.high = selected[b"UIDNEXT"] - 1
            source.save(update_fields=["uidvalidity", "low", "high"])
    return account


def _letter(
    sender: tuple[str, str],
    to: list[tuple[str, str]],
    subject: str,
    text: str,
    sent: datetime,
    answers: EmailMessage | None = None,
    attached: list[tuple[str, bytes, str]] = (),
    cc: list[tuple[str, str]] = (),
) -> EmailMessage:
    letter = EmailMessage()
    letter["From"] = f"{sender[0]} <{sender[1]}>"
    letter["To"] = ", ".join(f"{name} <{address}>" for name, address in to)
    if cc:
        letter["Cc"] = ", ".join(f"{name} <{address}>" for name, address in cc)
    letter["Subject"] = subject
    letter["Date"] = format_datetime(sent)
    letter["Message-ID"] = make_msgid(domain=sender[1].split("@")[1])
    if answers is not None:
        letter["In-Reply-To"] = answers["Message-ID"]
        letter["References"] = " ".join(
            filter(None, [answers.get("References", ""), answers["Message-ID"]])
        )
    letter.set_content(text)
    for name, data, kind in attached:
        main, sub = kind.split("/")
        letter.add_attachment(data, maintype=main, subtype=sub, filename=name)
    return letter


def _invitation(
    organizer: tuple[str, str], attendees: list[tuple[str, str]], summary: str, starts: datetime
) -> bytes:
    stamp = "%Y%m%dT%H%M%S"
    ends = starts + timedelta(hours=1)
    people = "".join(
        f"ATTENDEE;CN={name};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{address}\r\n"
        for name, address in attendees
    )
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Lipa Studio//Seed//EN\r\nMETHOD:REQUEST\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{make_msgid(domain=DOMAIN)[1:-1]}\r\n"
        f"DTSTAMP:{timezone.now().strftime(stamp)}Z\r\n"
        f"DTSTART;TZID=Europe/Zagreb:{starts.strftime(stamp)}\r\n"
        f"DTEND;TZID=Europe/Zagreb:{ends.strftime(stamp)}\r\n"
        f"SUMMARY:{summary}\r\nLOCATION:Sava\r\n"
        f"ORGANIZER;CN={organizer[0]}:mailto:{organizer[1]}\r\n{people}"
        "SEQUENCE:0\r\nSTATUS:CONFIRMED\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode()


def _quote(say) -> bytes:
    lines = [
        (
            18,
            say(
                "Hrast namještaj d.o.o. – ponuda br. 2026-114",
                "Hrast namještaj Ltd – quote no. 2026-114",
            ),
        ),
        (11, say("Kupac: Lipa Studio, Zagreb", "Customer: Lipa Studio, Zagreb")),
        (11, ""),
        (
            11,
            say(
                "Radni stol, hrast, 160 × 80 cm – 28 kom – 11.760,00 EUR",
                "Desk, oak, 160 × 80 cm – 28 pcs – 11,760.00 EUR",
            ),
        ),
        (
            11,
            say(
                "Stol za sastanke, hrast, 320 cm – 2 kom – 3.400,00 EUR",
                "Meeting table, oak, 320 cm – 2 pcs – 3,400.00 EUR",
            ),
        ),
        (
            11,
            say(
                "Ormar s policama – 6 kom – 3.490,00 EUR", "Shelving cabinet – 6 pcs – 3,490.00 EUR"
            ),
        ),
        (11, ""),
        (12, say("Ukupno bez PDV-a: 18.650,00 EUR", "Total before VAT: 18,650.00 EUR")),
        (11, say("Rok isporuke: 3 tjedna od narudžbe.", "Delivery: 3 weeks from the order.")),
    ]
    return files.pdf([lines])


def seed(seeded: Seeded) -> None:
    say, user, company = seeded.say, seeded.user, seeded.company
    account = connected(seeded)
    folders = {source.kind: source.folder for source in account.sources.exclude(kind="")}
    me = (user.get_full_name(), user.email)

    def person(key: str) -> tuple[str, str]:
        return company.name(key), company.address(key)

    now = timezone.now().astimezone(ZONE)

    def ago(hours: float) -> datetime:
        return now - timedelta(hours=hours)

    asked = _letter(
        CLIENT,
        [me],
        say("Uređenje novog ureda", "Fitting out our new office"),
        say(
            "Poštovana,\n\nselimo se u siječnju na treći kat zgrade u Trnjanskoj 500 (240 m²). "
            "Možete li nam poslati ponudu za projekt, namještaj i montažu do kraja tjedna?\n\n"
            "Lijep pozdrav,\nNikola Barić\nMeridian d.o.o.",
            "Hello,\n\nwe are moving to the third floor of 500 Trnjanska Street in January "
            "(240 m²). Could you send us a proposal for the design, the furniture and the "
            "fitting by the end of the week?\n\nKind regards,\nNikola Barić\nMeridian Ltd",
        ),
        ago(26 * 24),
    )
    answered = _letter(
        me,
        [CLIENT],
        f"Re: {asked['Subject']}",
        say(
            "Poštovani gospodine Bariću,\n\nu privitku je ponuda s konceptom i rokovima. "
            "Rado ćemo je proći zajedno na sastanku.\n\nLijep pozdrav,\n" + me[0],
            "Dear Mr Barić,\n\nthe proposal with the concept and the schedule is attached. "
            "We would be glad to go through it together.\n\nKind regards,\n" + me[0],
        ),
        ago(25 * 24),
        answers=asked,
        attached=[
            (
                say("Ponuda za uređenje ureda.pdf", "Office fit-out proposal.pdf"),
                files.pdf(
                    [
                        [
                            (18, say("Ponuda za uređenje ureda", "Office fit-out proposal")),
                            (11, "Lipa Studio"),
                        ]
                    ]
                ),
                "application/pdf",
            )
        ],
    )
    followed = _letter(
        CLIENT,
        [me],
        f"Re: {asked['Subject']}",
        say(
            "Hvala na ponudi. Dva pitanja: može li montaža početi 12. siječnja, i je li u cijeni "
            "i odvoz starog namještaja?\n\nNikola",
            "Thank you for the proposal. Two questions: can the fitting start on 12 January, and "
            "does the price include taking the old furniture away?\n\nNikola",
        ),
        ago(5),
        answers=answered,
        cc=[person("marija")],
    )
    quoted = _letter(
        SUPPLIER,
        [me],
        say("Ponuda za namještaj – Meridian", "Furniture quote – Meridian"),
        say(
            "Poštovana,\n\nšaljem ponudu za radne stolove, stolove za sastanke i ormare. "
            "Molim potvrdu do petka kako bismo rezervirali proizvodnju.\n\nMarko Vidović\n"
            "Hrast namještaj d.o.o.",
            "Hello,\n\nplease find our quote for the desks, the meeting tables and the "
            "cabinets attached. Please confirm by Friday so that we can book the "
            "production.\n\nMarko Vidović\nHrast namještaj Ltd",
        ),
        ago(28),
        attached=[
            (say("ponuda-2026-114.pdf", "quote-2026-114.pdf"), _quote(say), "application/pdf")
        ],
    )
    samples = _letter(
        person("ana"),
        [me],
        say("Uzorci parketa", "Parquet samples"),
        say(
            "Stigli su uzorci, hrast izgleda odlično uz bijele zidove. Fotografija u privitku.",
            "The samples are here; the oak looks great with the white walls. A photo is attached.",
        ),
        ago(9),
        attached=[("parquet.jpg", picture("parquet.jpg"), "image/jpeg")],
        cc=[person("ivan")],
    )
    sample_reply = _letter(
        person("ivan"),
        [person("ana")],
        f"Re: {samples['Subject']}",
        say(
            "Super. Naručujem 250 m² čim Meridian potvrdi ponudu.",
            "Great. I will order 250 m² as soon as Meridian confirms the proposal.",
        ),
        ago(7),
        answers=samples,
        cc=[me],
    )
    invoice = _letter(
        person("marta"),
        [me],
        say("Račun za listopad", "October invoice"),
        say(
            "Račun za listopad je izdan. Rok plaćanja je 15 dana.",
            "The October invoice has been issued. Payment is due in 15 days.",
        ),
        ago(3 * 24),
    )
    leave = _letter(
        person("maja"),
        [me],
        say("Godišnji odmor – Ana", "Annual leave – Ana"),
        say(
            "Ana je na godišnjem odmoru od ponedjeljka do srijede. Zamjenjuje je Elena.",
            "Ana is on annual leave from Monday to Wednesday. Elena stands in for her.",
        ),
        ago(4 * 24),
    )
    review = (now + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    invited = _letter(
        person("marija"),
        [me, person("ana")],
        say("Pozivnica: Pregled projekta Meridian", "Invitation: Meridian project review"),
        say(
            "Prođimo ponudu prije sastanka s klijentom.",
            "Let us go through the proposal before we meet the client.",
        ),
        ago(2),
        attached=[
            (
                "invite.ics",
                _invitation(
                    person("marija"),
                    [me, person("ana")],
                    say("Pregled projekta Meridian", "Meridian project review"),
                    review,
                ),
                "text/calendar",
            )
        ],
    )
    archived = _letter(
        person("tomislav"),
        [me],
        say("Primopredaja – Apex", "Handover – Apex"),
        say("Primopredaja je potpisana, sve je u redu.", "The handover is signed and all is well."),
        ago(40 * 24),
    )
    for letter, folder, flags in (
        (asked, "inbox", {"seen": True, "answered": True}),
        (answered, "sent", {"seen": True}),
        (followed, "inbox", {"seen": False, "flagged": True}),
        (quoted, "inbox", {"seen": False, "flagged": True}),
        (samples, "inbox", {"seen": True}),
        (sample_reply, "inbox", {"seen": False}),
        (invoice, "inbox", {"seen": True}),
        (leave, "inbox", {"seen": True}),
        (invited, "inbox", {"seen": False}),
        (archived, "archive", {"seen": True}),
    ):
        taken = taking._taken(bytes(letter), letter["Date"].datetime, None)
        taking._once(account, folders[folder], taken, flags)
    seeded.made["account"] = account
