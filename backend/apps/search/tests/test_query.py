from datetime import UTC, datetime

import pytest
from django.utils import timezone

from apps.search.query import asked

NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


def local(*given) -> datetime:
    return timezone.make_aware(datetime(*given))


def test_filters_are_taken_out_of_the_words_with_their_place():
    found = asked("ugovor od:ana vrsta:pošta rijeka", NOW)
    assert found.text == "ugovor rijeka"
    assert (found.sender, found.kind) == (["ana"], "mail")
    assert [(each["key"], each["start"], each["end"]) for each in found.filters] == [
        ("from", 7, 13),
        ("kind", 14, 25),
    ]


def test_keys_and_values_are_read_in_either_language_with_or_without_accents():
    assert asked("kind:document", NOW).kind == "document"
    assert asked("vrsta:posta", NOW).kind == "mail"
    assert asked("racun:posao", NOW).account == ["posao"]
    assert asked("has:attachments", NOW).attachment
    assert asked("ima:privitak", NOW).attachment
    assert asked("vrsta:događaj", NOW).kind == "event"
    assert asked("vrsta:zadaci", NOW).kind == "task"
    assert asked("kind:people", NOW).kind == "person"
    assert asked("vrsta:kontakt", NOW).kind == "person"
    assert asked("vrsta:sef", NOW).kind == "vault"


def test_each_kind_of_result_answers_to_the_filters_it_can_meet():
    everything = asked("gume", NOW)
    assert (everything.events, everything.tasks, everything.people) == (True, True, True)
    person = asked("vrsta:osoba", NOW)
    assert (person.documents, person.mail, person.events, person.tasks, person.people) == (
        False,
        False,
        False,
        False,
        True,
    )
    dated = asked("gume datum:2026", NOW)
    assert (dated.events, dated.tasks, dated.people) == (True, True, False)
    sent = asked("gume od:ana", NOW)
    assert (sent.events, sent.tasks, sent.people) == (True, False, False)
    vault = asked("vrsta:sef", NOW)
    assert not (vault.documents or vault.mail or vault.events or vault.tasks or vault.people)
    assert not (everything.versions or vault.versions)
    versions = asked("vrsta:verzija popust od:ana mapa:ponude", NOW)
    assert versions.versions and not (versions.documents or versions.events)
    assert not asked("vrsta:povijest ima:privitak", NOW).versions
    boxed = asked("gume mapa:ponude", NOW)
    assert (boxed.documents, boxed.events, boxed.tasks) == (True, False, False)


def test_a_value_may_be_the_start_of_one_meaning():
    assert asked("vrsta:pošt", NOW).kind == "mail"
    assert asked("vrsta:dok", NOW).kind == "document"
    assert asked("vrsta:d", NOW).filters[0]["error"] == "invalid_kind"


def test_a_quoted_value_keeps_its_spaces():
    found = asked('od:"Ana Kovač" ponuda', NOW)
    assert (found.sender, found.text) == (["Ana Kovač"], "ponuda")


def test_what_is_no_filter_stays_among_the_words():
    found = asked("sastanak 10:30 https://ponistra.hr x:y", NOW)
    assert found.text == "sastanak 10:30 https://ponistra.hr x:y"
    assert found.filters == []


def test_a_folder_of_mail_is_named_by_its_role_in_either_language():
    assert asked("mapa:poslano", NOW).roles == ["sent"]
    assert asked("folder:trash", NOW).roles == ["trash"]
    assert asked("mapa:ponude", NOW).folder == ["ponude"]


@pytest.mark.parametrize(
    "value, start, end, first, last",
    [
        ("2025", (2025, 1, 1), (2026, 1, 1), "2025-01-01", "2025-12-31"),
        ("2025-02", (2025, 2, 1), (2025, 3, 1), "2025-02-01", "2025-02-28"),
        ("2.2025.", (2025, 2, 1), (2025, 3, 1), "2025-02-01", "2025-02-28"),
        ("3.2.2025", (2025, 2, 3), (2025, 2, 4), "2025-02-03", "2025-02-03"),
        ("2024-12..2025-01-15", (2024, 12, 1), (2025, 1, 16), "2024-12-01", "2025-01-15"),
        ("2025..", (2025, 1, 1), None, "2025-01-01", None),
        ("..2025-02", None, (2025, 3, 1), None, "2025-02-28"),
    ],
)
def test_a_period_runs_from_its_first_day_to_its_last_in_local_time(value, start, end, first, last):
    found = asked(f"datum:{value}", NOW)
    assert (found.period.start, found.period.end, found.period.changed) == (
        start and local(*start),
        end and local(*end),
        False,
    )
    assert found.filters[0]["value"] == {"from": first, "to": last}


def test_a_period_may_be_the_last_days_or_when_it_was_changed():
    found = asked("izmjena:tjedan", NOW)
    assert (found.period.start, found.period.end, found.period.changed) == (
        datetime(2026, 10, 17, 12, tzinfo=UTC),
        None,
        True,
    )
    assert found.filters[0]["value"] == {"last": "week"}
    assert asked("date:month", NOW).filters[0]["value"] == {"last": "month"}


@pytest.mark.parametrize("value", ["jučer", "2025-13", "31.2.2025", "2025-02..2025-01", ".."])
def test_a_period_it_cannot_read_is_an_error(value):
    assert asked(f"datum:{value}", NOW).filters[0]["error"] == "invalid_date"


def test_what_a_filter_rules_out():
    assert not asked("vrsta:pošta", NOW).documents
    assert not asked("vrsta:datoteka", NOW).mail
    assert not asked("ima:privitak", NOW).documents
    assert not asked("račun:posao", NOW).documents
    assert asked("od:ana mapa:ponude", NOW).documents and asked("od:ana", NOW).mail
