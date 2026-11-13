from datetime import timedelta

from django.utils import timezone

from apps.tasks.models import Task

from .company import Seeded

# Text, days until due (None: no date) and whether it is done.
TASKS = (
    (
        ("Odgovoriti Meridianu na pitanja o montaži", "Answer Meridian's questions on the fitting"),
        1,
        False,
    ),
    (("Potvrditi ponudu za namještaj do petka", "Confirm the furniture quote by Friday"), 3, False),
    (("Poslati vizualizacije sale za sastanke", "Send the meeting room renderings"), 5, False),
    (("Rezervirati kombi za obilazak gradilišta", "Book the van for the site visit"), 9, False),
    (("Naručiti uzorke parketa", "Order the parquet samples"), -6, True),
    (("Pripremiti prezentaciju za Meridian", "Prepare the Meridian presentation"), -3, True),
    (("Pročitati pravilnik o radu", "Read the office handbook"), None, False),
)


def seed(seeded: Seeded) -> None:
    say, user = seeded.say, seeded.user
    today = timezone.localdate()
    for text, due, done in TASKS:
        Task.objects.create(
            owner=user,
            text=say(*text),
            due=None if due is None else today + timedelta(days=due),
            done_at=timezone.now() + timedelta(days=due) if done else None,
        )
