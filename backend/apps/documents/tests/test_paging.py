import json
from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from django.db import connection
from django.utils import timezone
from pycrdt import Map

from apps.collab import server
from apps.collab.models import Update
from apps.content.blocks import Block, Run
from apps.content.pages import COUNTS
from apps.content.tests import helpers
from apps.documents import paging, printing
from apps.documents.models import Node
from apps.users.models import Session, User
from apps.versions.models import Contribution

from .test_printing import document

pytestmark = pytest.mark.django_db(transaction=True)

QUIET = timedelta(seconds=10)


def written(node: Node, at=None) -> Update:
    """A paragraph written into the document's first tab, at that time."""
    doc, _ = helpers.written([Block("paragraph", runs=[Run("Ugovor")])])
    tab = node.tabs_in_order()[0]
    update = Update.objects.create(document=node, tab=tab, room=tab.room, data=doc.get_update())
    if at is not None:
        Update.objects.filter(pk=update.pk).update(created_at=at)
        update.refresh_from_db()
    return update


def counts(node: Node) -> dict:
    return server.read(node.room, lambda own: own.get(COUNTS, type=Map).to_py())


def tend(now) -> None:
    async_to_sync(paging.tend)(now)


@pytest.fixture
def made(api):
    """A document counted an hour ago, with nothing written in it since."""
    node = Node.objects.get(pk=document(api, "Ugovor o djelu"))
    Update.objects.filter(document=node).delete()
    Node.objects.filter(pk=node.pk).update(paged_at=timezone.now() - timedelta(hours=1))
    node.refresh_from_db()
    return node


def test_a_document_never_counted_is_counted_at_once(api, made, printer):
    tab = str(made.tabs_in_order()[0].pk)
    Node.objects.filter(pk=made.pk).update(paged_at=None)
    last = written(made, timezone.now()).created_at
    printer.replies.append((200, json.dumps({tab: 2}).encode()))
    tend(last)
    assert counts(made) == {tab: 2}


def test_a_quiet_document_has_its_tabs_counted_by_a_reader_into_its_own_state(api, made, printer):
    tab = str(made.tabs_in_order()[0].pk)
    last = written(made, timezone.now() - timedelta(minutes=5)).created_at
    tend(last + QUIET / 2)
    assert printer.received == []
    printer.replies.append((200, json.dumps({tab: 3}).encode()))
    tend(last + QUIET)
    [asked] = printer.received
    assert asked["path"] == f"/print/{printing.compact(made.pk)}"
    assert not Session.objects.filter(session_key=asked["session"]).exists()
    assert counts(made) == {tab: 3}
    made.refresh_from_db()
    assert made.paged_at == last
    tend(last + QUIET)
    assert len(printer.received) == 1


def test_a_document_edited_without_pause_is_counted_once_its_first_change_is_a_minute_old(
    api, made, printer
):
    tab = str(made.tabs_in_order()[0].pk)
    first = timezone.now() - timedelta(minutes=5)
    written(made, first)
    written(made, first + timedelta(seconds=55))
    tend(first + timedelta(seconds=59))
    assert printer.received == []
    printer.replies.append((200, json.dumps({tab: 1}).encode()))
    tend(first + timedelta(seconds=60))
    assert counts(made) == {tab: 1}


def test_a_count_that_finds_the_pages_as_they_were_changes_nothing(api, made, printer):
    tab = str(made.tabs_in_order()[0].pk)
    last = written(made, timezone.now() - timedelta(minutes=5)).created_at
    printer.replies.append((200, json.dumps({tab: 2}).encode()))
    tend(last + QUIET)
    stored = Update.objects.filter(room=made.room).count()
    later = written(made, timezone.now() + timedelta(minutes=1)).created_at
    printer.replies.append((200, json.dumps({tab: 2}).encode()))
    tend(later + QUIET)
    assert len(printer.received) == 2
    assert Update.objects.filter(room=made.room).count() == stored
    made.refresh_from_db()
    assert made.paged_at == later


def test_the_count_is_read_by_the_last_editor_who_may_still_read_it_else_by_the_author(
    api, made, printer
):
    tab = str(made.tabs_in_order()[0].pk)
    stranger = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    Contribution.objects.create(document=made, user=stranger, edited_at=timezone.now())
    assert paging.reader_of(made) == api.user
    last = written(made, timezone.now() - timedelta(minutes=5)).created_at
    printer.replies.append((200, json.dumps({tab: 1}).encode()))
    tend(last + QUIET)
    assert counts(made) == {tab: 1}


def test_a_document_nobody_may_read_or_the_printer_fails_is_reported_and_left_until_changed(
    api, made, printer, caplog
):
    last = written(made, timezone.now() - timedelta(minutes=5)).created_at
    Node.objects.filter(pk=made.pk).update(created_by=None)
    tend(last + QUIET)
    assert printer.received == []
    assert f"pages: document {made.pk} could not be counted" in caplog.text
    made.refresh_from_db()
    assert made.paged_at == last
    Node.objects.filter(pk=made.pk).update(created_by=api.user)
    later = written(made, last + timedelta(minutes=1)).created_at
    printer.replies.append((504, b"timed out"))
    tend(later + QUIET)
    assert len(printer.received) == 1
    assert counts(made) == {}
    made.refresh_from_db()
    assert made.paged_at == later


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("when", ["before its reader is found", "while the printer counts it"])
def test_a_document_deleted_while_it_is_counted_is_passed_over(
    api, made, monkeypatch, caplog, when
):
    tab = str(made.tabs_in_order()[0].pk)
    last = written(made, timezone.now() - timedelta(minutes=5)).created_at
    reader_of = paging.reader_of

    def deleted_then_found(document):
        Node.objects.filter(pk=document.pk).delete()
        return reader_of(document)

    def deleted_then_counted(document, session):
        try:
            Node.objects.filter(pk=document).delete()
        finally:
            connection.close()
        return {tab: 7}

    if when == "before its reader is found":
        monkeypatch.setattr(paging, "reader_of", deleted_then_found)
    else:
        monkeypatch.setattr(printing, "counted", deleted_then_counted)
    tend(last + QUIET)
    assert "could not be counted" not in caplog.text
    assert not Node.objects.filter(pk=made.pk).exists()
    assert not Update.objects.filter(room=made.room).exists()


@pytest.mark.django_db(transaction=True)
def test_a_document_put_in_the_trash_while_it_is_counted_is_passed_over(
    api, made, monkeypatch, caplog
):
    tab = str(made.tabs_in_order()[0].pk)
    last = written(made, timezone.now() - timedelta(minutes=5)).created_at

    def trashed_then_counted(document, session):
        try:
            Node.objects.filter(pk=document).update(trashed_at=timezone.now())
        finally:
            connection.close()
        return {tab: 7}

    monkeypatch.setattr(printing, "counted", trashed_then_counted)
    counted = made.paged_at
    tend(last + QUIET)
    assert "could not be counted" not in caplog.text
    made.refresh_from_db()
    assert made.paged_at == counted


def test_the_printer_answers_each_tabs_count_or_nothing_is_taken(printer, made):
    printer.replies.append((200, b'{"a": 2, "b": 1}'))
    assert printing.counted(made.pk, "k") == {"a": 2, "b": 1}
    for reply in (b'{"a": 0}', b'{"a": 1.5}', b"[1]", b"pages"):
        printer.replies.append((200, reply))
        with pytest.raises(printing.Unavailable):
            printing.counted(made.pk, "k")
