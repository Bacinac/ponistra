from datetime import timedelta

from django.utils import timezone

from apps.chat import conversations
from apps.chat.models import Attachment, Conversation, Follower, Member, Message, Reaction
from apps.users.models import User

from .company import Seeded

EVERYONE = ("marija", "maja", "ivan", "ana", "elena", "marta", "tomislav", "dino")

# Who writes (None: the account itself), minutes ago, the words, the reactions and the replies.
OFFICE = (
    (
        "maja",
        2900,
        (
            "Dobro jutro! U petak u 16 sati slavimo Martin rođendan u kuhinji. 🎂",
            "Good morning! On Friday at 4 pm we celebrate Marta's birthday in the kitchen. 🎂",
        ),
        (("ana", "🎉"), ("ivan", "🎉"), ("tomislav", "👍"), ("marta", "❤️")),
        (),
    ),
    (
        "marija",
        1500,
        (
            "Od ponedjeljka sala Sava ima novi ekran. Upute za spajanje su na zidu.",
            "From Monday the Sava room has a new screen. The steps to connect are on the wall.",
        ),
        (("elena", "👍"), (None, "👍")),
        (
            ("ivan", 1490, ("Radi li i bežično?", "Does it work wirelessly too?")),
            ("marija", 1480, ("Da, preko aplikacije na ekranu.", "Yes, through the screen's app.")),
        ),
    ),
    (
        "marta",
        240,
        (
            "Podsjetnik: putne naloge za listopad molim do srijede.",
            "A reminder: the October travel claims by Wednesday, please.",
        ),
        (),
        (),
    ),
)

MERIDIAN = (
    (
        None,
        3000,
        (
            "Ponuda je gotova, šaljem je klijentu.",
            "The proposal is done; I am sending it to the client.",
        ),
        (("ana", "👏"),),
        (),
    ),
    (
        "ana",
        2000,
        (
            "Ubacila sam novu sliku sale u prezentaciju.",
            "I put the new picture of the meeting room into the presentation.",
        ),
        (),
        (),
    ),
    (
        "ivan",
        400,
        (
            "Hrast namještaj traži potvrdu do petka.",
            "Hrast namještaj wants a confirmation by Friday.",
        ),
        ((None, "👍"),),
        (),
    ),
    (
        "marija",
        60,
        (
            "Klijent pita može li montaža početi 12. siječnja. Možemo li?",
            "The client asks whether the fitting can start on 12 January. Can we?",
        ),
        (),
        (
            (
                "tomislav",
                50,
                (
                    "Možemo, ako namještaj stigne do 9.",
                    "We can, if the furniture arrives by the 9th.",
                ),
            ),
        ),
    ),
)

DIRECT = (
    ("ana", 180, ("Imaš li minutu za boje zidova?", "Do you have a minute for the wall colours?")),
    (None, 175, ("Imam, javi se.", "I do, give me a call.")),
    (
        "ana",
        20,
        (
            "Šaljem ti tri prijedloga do kraja dana.",
            "I will send you three options by the end of the day.",
        ),
    ),
)


def _written(conversation, author, minutes: int, body: str, parent=None) -> Message:
    message = Message.objects.create(
        conversation=conversation, author=author, body=body, parent=parent
    )
    Message.objects.filter(pk=message.pk).update(
        created_at=timezone.now() - timedelta(minutes=minutes)
    )
    return message


def _filled(conversation, seeded: Seeded, said, read_all: bool) -> list[Message]:
    say, people = seeded.say, seeded.company.people

    def who(key: str | None) -> User:
        return seeded.user if key is None else people[key]

    made = []
    for author, minutes, words, reactions, replies in said:
        message = _written(conversation, who(author), minutes, say(*words))
        for key, emoji in reactions:
            Reaction.objects.create(message=message, user=who(key), emoji=emoji)
        last = message
        for key, ago, reply in replies:
            last = _written(conversation, who(key), ago, say(*reply), parent=message)
        if replies:
            Follower.objects.create(root=message, user=seeded.user, read=last.pk)
        made.append(message)
    last = Message.objects.filter(conversation=conversation).order_by("-pk").first()
    newest = Message.objects.filter(conversation=conversation).order_by("-created_at").first()
    Conversation.objects.filter(pk=conversation.pk).update(changed_at=newest.created_at)
    Member.objects.filter(conversation=conversation).exclude(user=seeded.user).update(read=last.pk)
    if read_all:
        Member.objects.filter(conversation=conversation, user=seeded.user).update(read=last.pk)
    return made


def seed(seeded: Seeded) -> None:
    say, user, people = seeded.say, seeded.user, seeded.company.people
    office = conversations.founded(
        people["maja"], say("Ured", "Office"), False, [user, *(people[k] for k in EVERYONE)]
    )
    _filled(office, seeded, OFFICE, read_all=False)
    meridian = conversations.founded(
        user,
        say("Projekt Meridian", "Meridian project"),
        True,
        [people[k] for k in ("marija", "ivan", "ana", "tomislav")],
    )
    first, *_ = _filled(meridian, seeded, MERIDIAN, read_all=False)
    proposal = seeded.made["proposal"]
    conversations._carrying(first, [Attachment(name=proposal.title, node=proposal)], user)
    direct, _ = conversations.started(user, [people["ana"]], "")
    _filled(
        direct,
        seeded,
        [(author, minutes, words, (), ()) for author, minutes, words in DIRECT],
        read_all=False,
    )
    site, _ = conversations.started(
        user, [people["tomislav"], people["dino"]], say("Gradilište", "Site")
    )
    _filled(
        site,
        seeded,
        [
            (
                "tomislav",
                4000,
                ("Sutra krećemo u 7 iz dvorišta.", "We leave the courtyard at 7 tomorrow."),
                (),
                (),
            ),
            (
                None,
                3990,
                ("Može, ponesite i uzorke.", "Fine, and take the samples along."),
                (("dino", "👍"),),
                (),
            ),
        ],
        read_all=True,
    )
