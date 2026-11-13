import secrets

import pytest

from apps.core.api import Refused
from apps.mail import moving, taking
from apps.mail.models import Folder, Message, Source
from apps.users.models import User

from .mox import letter, server
from .test_views import kept

pytestmark = [pytest.mark.django_db, pytest.mark.xdist_group("mox")]


@pytest.fixture
def owner():
    return User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")


@pytest.fixture
def name():
    made = f"Selidba {secrets.token_hex(4)}"
    yield made
    with server() as client:
        if client.folder_exists(made):
            client.delete_folder(made)


def brought(account, path: list[str], role: str = "", flags=None, subject="Ponuda") -> Message:
    folder = taking.folder(account, role, path)
    source = Source.objects.create(account=account, folder=folder, name="/".join(path) or role)
    return taking.took(source, letter(subject).as_bytes(), flags or {})


def test_the_mail_an_account_brought_moves_into_the_same_folders_of_another(owner, name):
    old, new = kept(owner, "stari@firma.test"), kept(owner)
    message = brought(old, [name], flags={"seen": True, "flagged": True})
    thrown = brought(old, [], "trash", subject="Smeće")
    assert moving.moved(owner, {"from": old.pk, "to": new.pk}) == {"moved": 1}
    with server() as client:
        client.select_folder(name, readonly=True)
        [uid] = client.search()
        found = client.fetch([uid], ["FLAGS", "BODY.PEEK[HEADER.FIELDS (SUBJECT)]"])[uid]
    assert {b"\\Seen", b"\\Flagged"} <= set(found[b"FLAGS"])
    assert b"Ponuda" in found[b"BODY[HEADER.FIELDS (SUBJECT)]"]
    message.refresh_from_db()
    assert message.account == new
    assert message.folder == Folder.objects.get(parent__account=new, name=name)
    thrown.refresh_from_db()
    assert thrown.account == old
    assert moving.moved(owner, {"from": old.pk, "to": new.pk}) == {"moved": 0}


def test_mail_moves_only_between_two_of_the_owners_accounts_into_one_over_imap(owner):
    old, new = kept(owner, "stari@firma.test"), kept(owner)
    stranger = kept(User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71"))
    for given, error in (
        ({"from": old.pk, "to": old.pk}, "invalid_to"),
        ({"from": old.pk, "to": stranger.pk}, "not_found"),
        ({"from": old.pk}, "not_found"),
    ):
        with pytest.raises(Refused) as refused:
            moving.moving(owner, given)
        assert refused.value.error == error
    new.protocol = "activesync"
    new.save()
    with pytest.raises(Refused):
        moving.moving(owner, {"from": old.pk, "to": new.pk})
