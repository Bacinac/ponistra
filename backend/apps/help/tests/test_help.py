import io
import json

import pytest
from django.core.management import call_command

from apps.access.tests.test_access import person
from apps.help import library, source
from apps.mail.models import Message
from apps.users.models import User

pytestmark = pytest.mark.django_db

HR = """# Odgoda poruke

Poruka nestaje iz popisa do odabranog trenutka.

## Kako se koristi

1. Otvorite {t:mail.snooze}.
2. Pritisnite {k:Mod-/}.

![Popis](shot:mail-list)

## Kako radi

Vraća se u [Poštu](/mail).

## Ograničenja

Nema ih.

## Povezano

- [Čitanje](help:mail/reading)
"""
EN = """# Snoozing a message

The message leaves the list until the chosen moment.

## How to use it

1. Open {t:mail.snooze}.
2. Press {k:Mod-/}.

![List](shot:mail-list)

## How it works

It returns to [Mail](/mail).

## Limits

None.

## Related

- [Reading](help:mail/reading)
"""


def article(folder, identifier, order=10, audience="everyone", covers=()):
    section, slug = identifier.split("/")
    (folder / section).mkdir(exist_ok=True)
    (folder / section / f"{slug}.json").write_text(
        json.dumps({"order": order, "audience": audience, "covers": list(covers), "describes": {}})
    )
    (folder / section / f"{slug}.hr.md").write_text(HR)
    (folder / section / f"{slug}.en.md").write_text(EN)


@pytest.fixture
def shelf(settings, tmp_path):
    folder, i18n = tmp_path / "help", tmp_path / "i18n"
    folder.mkdir()
    i18n.mkdir()
    (folder / "sections.json").write_text('[{"id": "start"}, {"id": "mail"}, {"id": "admin"}]')
    for language, snooze, sections in (
        ("hr", "Odgodi", ("Prvi koraci", "Pošta", "Administracija")),
        ("en", "Snooze", ("Getting started", "Mail", "Administration")),
    ):
        (i18n / f"{language}.ts").write_text(
            "export const x = {\n"
            f"  'mail.snooze': '{snooze}',\n"
            f"  'help.section.start': '{sections[0]}',\n"
            f"  'help.section.mail': '{sections[1]}',\n"
            f"  'help.section.admin': '{sections[2]}',\n"
            "};\n"
        )
    settings.HELP, settings.I18N = folder, i18n
    article(folder, "mail/snoozing", covers=["route:/mail/:folder"])
    article(folder, "mail/reading", order=5)
    article(folder, "admin/users", audience="admin", covers=["route:/users"])
    return folder


@pytest.fixture
def signed():
    return person("reader@example.com")


@pytest.fixture
def user(signed):
    return signed.user


def test_the_contents_follow_the_sections_and_their_order(shelf, signed):
    contents = signed.get("/api/help?lang=en").json()
    assert [each["title"] for each in contents["sections"]] == ["Mail"]
    assert [each["id"] for each in contents["sections"][0]["articles"]] == [
        "mail/reading",
        "mail/snoozing",
    ]
    assert contents["sections"][0]["articles"][0]["summary"] == (
        "The message leaves the list until the chosen moment."
    )
    assert contents["screens"] == [{"path": "/mail/:folder", "article": "mail/snoozing"}]


def test_an_article_is_filled_in_from_the_releases_own_strings(shelf, signed):
    page = signed.get("/api/help/mail/snoozing?lang=hr").json()
    assert page["title"] == "Odgoda poruke"
    assert "<strong>Odgodi</strong>" in page["html"]
    assert '<kbd data-keys="Mod-/">Ctrl+/</kbd>' in page["html"]
    assert '<img data-shot="mail-list" alt="Popis">' in page["html"]
    assert 'href="/help/mail/reading"' in page["html"]
    assert "Odgoda poruke" not in page["html"]
    assert "<h2>Kako se koristi</h2>" in page["html"]
    assert "Poruka nestaje" not in page["html"]


def test_the_language_falls_back_to_the_accounts_then_to_croatian(shelf, signed, user):
    assert signed.get("/api/help/mail/snoozing").json()["title"] == "Odgoda poruke"
    user.language = "en"
    user.save()
    assert signed.get("/api/help/mail/snoozing").json()["title"] == "Snoozing a message"
    assert signed.get("/api/help/mail/snoozing?lang=hr").json()["title"] == "Odgoda poruke"


def test_what_is_for_administrators_stays_with_them(shelf, signed, user):
    assert signed.get("/api/help/admin/users").status_code == 404
    assert "admin" not in str(signed.get("/api/help").json()["sections"])
    assert all(each["id"] != "admin/users" for each in library.found(user, "Odgoda", "hr", 10))
    user.is_staff = True
    user.save()
    assert signed.get("/api/help/admin/users").status_code == 200


def test_an_article_that_does_not_exist_is_not_found(shelf, signed):
    assert signed.get("/api/help/mail/nothing").status_code == 404


def test_the_help_is_for_those_signed_in(shelf, client):
    assert client.get("/api/help").status_code == 401


def test_search_finds_a_word_however_it_ends_and_without_its_marks(shelf, user):
    for asked in ("odgoda", "ODGODU", "posta", "poštu"):
        assert library.found(user, asked, "hr", 10), asked
    assert library.found(user, "tražilica", "hr", 10) == []
    assert library.found(user, "odgoda tražilica", "hr", 10) == []


def test_search_box_answers_with_the_help_unless_narrowed(shelf, signed):
    found = signed.get("/api/search?q=odgoda&lang=hr").json()
    assert {each["id"] for each in found["help"]} == {"mail/snoozing", "mail/reading"}
    assert signed.get("/api/search?q=odgoda kind:event&lang=hr").json()["help"] == []


def test_an_agent_reads_what_a_reader_does_without_the_pictures(shelf, user):
    reading = library.article(user, "mail/snoozing", "en").reading
    assert "**Snooze**" in reading
    assert "`Ctrl+/`" in reading
    assert "shot:" not in reading
    assert "/help/mail/reading" in reading


def test_the_interface_strings_are_read_with_their_escapes():
    assert source.fold("Pošta Đuro") == "posta duro"
    assert source.shortcut("Mod-Shift-k") == "Ctrl+Shift+K"
    assert source.shortcut("F1") == "F1"


def test_every_string_of_the_real_interface_is_read(settings):
    for language in source.LANGUAGES:
        text = (settings.I18N / f"{language}.ts").read_text()
        assert len(source.messages(settings.I18N / f"{language}.ts")) == text.count("\n  '")


@pytest.mark.xdist_group("mox")
def test_the_company_and_its_accounts_are_seeded_once_in_each_language():
    output = io.StringIO()
    call_command("help_seed", stdout=output)
    sessions = json.loads(output.getvalue())
    assert set(sessions) == set(source.LANGUAGES)
    hr = User.objects.get(email="klara@lipastudio.test")
    en = User.objects.get(email="sarah@lipastudio.test")
    assert (hr.language, en.language) == ("hr", "en")
    assert Message.objects.filter(owner=hr, subject="Račun za listopad").exists()
    assert Message.objects.filter(
        owner=en, subject="October invoice", folder__role="inbox"
    ).exists()
    people = User.objects.count()
    again = io.StringIO()
    call_command("help_seed", stdout=again)
    assert set(json.loads(again.getvalue())) == set(source.LANGUAGES)
    assert User.objects.count() == people
