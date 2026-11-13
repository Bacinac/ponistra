"""The colleagues the user meets (D15, S4): a correspondent the directory of the organisation's
ActiveSync server confirms becomes a contact whose source it is, and every colleague it lists is
refreshed from it once a night. The directory can only be searched by the start of a name, so
it is never walked."""

import re
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.mail import correspondents, signin
from apps.mail import taking as mail_taking
from apps.mail.activesync import directory as mail_directory
from apps.mail.activesync import sync as activesync
from apps.mail.activesync.client import Session
from apps.mail.imap import Failed
from apps.mail.models import Account, Correspondent, Named

from . import numbers, taking
from .cards import listed
from .models import Contact, Directory, Entry, Taken, ordered, revised
from .vcard import Card

# An address the directory did not list is asked again after this: a colleague who has joined.
AGAIN = timedelta(days=30)
# A colleague is refreshed once in this, wherever several of the installation's users meet them.
FRESH = timedelta(hours=20)
MOST = 25
DETAILS = ("name", "given", "family", "title", "company", "office", "phone", "mobile", "home")
NUMBERS = ("phone", "mobile", "home")


def due(passed_at: datetime | None) -> datetime:
    """When the account's directory is next gone through: at CONTACTS_AT after the last time, at
    once if never."""
    if passed_at is None:
        return datetime.min.replace(tzinfo=UTC)
    last = timezone.localtime(passed_at)
    at = last.replace(
        hour=settings.CONTACTS_AT.hour, minute=settings.CONTACTS_AT.minute, second=0, microsecond=0
    )
    return at if at > last else at + timedelta(days=1)


def domains(account: Account) -> set[str]:
    """The domains the organisation's colleagues write from, as far as its directory has shown."""
    host = account.activesync_host
    found = {account.address.rpartition("@")[2].lower()}
    for addresses in (
        Entry.objects.filter(host=host, listed=True).values_list("address", flat=True),
        Named.objects.filter(host=host).exclude(address="").values_list("address", flat=True),
    ):
        found |= {each.rpartition("@")[2].lower() for each in addresses}
    return found - {""}


def queries(name: str, address: str) -> list[str]:
    """What to search the directory by for a person: their name, then the words of their
    address before the @, which it may find by a first or last name."""
    found = []
    common = mail_taking.common(name) or name
    if "@" not in common and len(common.strip()) >= 2:
        found.append(common.strip())
    words = [each for each in re.split(r"[._\-+]", address.partition("@")[0]) if len(each) >= 2]
    words = sorted(words, key=len, reverse=True)
    found += [each for each in words if each.casefold() not in common.casefold()][:2]
    return found


def _asked(client: Session, name: str, address: str) -> dict | None:
    """What the directory gives of the person; {} where it answered without them, None where it
    did not answer."""
    answered = False
    for query in queries(name, address):
        people = mail_directory.searched(client, query, MOST)
        if people is None:
            continue
        answered = True
        for person in people:
            if person["address"].lower() == address:
                return person
    return {} if answered else None


def _kept(host: str, address: str, person: dict) -> Entry:
    values = {key: (person.get(key) or "")[:500] for key in DETAILS}
    for key in NUMBERS:
        values[key] = numbers.written(values[key])
    entry, _ = Entry.objects.update_or_create(
        host=host,
        address=address,
        defaults={**values, "listed": bool(person), "asked_at": timezone.now()},
    )
    return entry


def candidates(account: Account) -> list[Correspondent]:
    """The owner's correspondents at the organisation's domains the directory has not been
    asked about lately, nor already gave the owner."""
    host, mine = account.activesync_host, correspondents.own(account.owner_id)
    given = Taken.objects.filter(
        owner_id=account.owner_id, kind=Taken.Kind.DIRECTORY, source=host
    ).values_list("item", flat=True)
    unlisted = Entry.objects.filter(
        host=host, listed=False, asked_at__gt=timezone.now() - AGAIN
    ).values_list("address", flat=True)
    known = set(given) | set(unlisted) | set(mine)
    wanted = domains(account)
    return [
        each
        for each in account.owner.mail_correspondents.order_by("-written", "-heard", "address")
        if each.address.lower() not in known and each.address.rpartition("@")[2].lower() in wanted
    ]


def met(client: Session, account: Account) -> int:
    """Makes a contact of each correspondent the directory confirms as a colleague; how many."""
    host, count = account.activesync_host, 0
    for each in candidates(account):
        address = each.address.lower()
        entry = Entry.objects.filter(host=host, address=address, listed=True).first()
        if entry is None:
            person = _asked(client, each.name, address)
            if person is None:
                raise Failed("activesync_unreachable")
            entry = _kept(host, address, person)
        if entry.listed and taking.colleague(account.owner_id, entry):
            count += 1
    return count


@transaction.atomic
def _left(entry: Entry) -> None:
    """The directory no longer lists the colleague: what it said of them last stays with each
    contact as its own, as a personal source's would."""
    fields, points = listed(entry)
    ordered(*entry.contacts.values_list("owner_id", flat=True))
    for contact in entry.contacts.all():
        taking.joined(contact, Card(fields={**Card().fields, **fields}, points=points))
    entry.contacts.update(entry=None, revision=revised())
    Entry.objects.filter(pk=entry.pk).update(listed=False, asked_at=timezone.now())


def refreshed(client: Session, account: Account) -> int:
    """Asks the directory again about each colleague the owner has from it; how many changed."""
    stale = Entry.objects.filter(
        host=account.activesync_host,
        listed=True,
        contacts__owner_id=account.owner_id,
        asked_at__lt=timezone.now() - FRESH,
    ).distinct()
    count = 0
    for entry in stale:
        person = _asked(client, entry.name, entry.address)
        if person is None:
            raise Failed("activesync_unreachable")
        if not person:
            _left(entry)
            count += 1
            continue
        before = {key: getattr(entry, key) for key in DETAILS}
        after = _kept(entry.host, entry.address, person)
        if {key: getattr(after, key) for key in DETAILS} != before:
            taking.revise(after)
            count += 1
    return count


def searched(account: Account, typed: str) -> list[dict] | None:
    """The colleagues the account's directory finds by the start of a name; None where it did
    not answer."""
    login, _ = signin.login(account)
    with activesync.session(account, login.password) as client:
        return mail_directory.searched(client, typed, MOST)


def chosen(account: Account, address: str, name: str) -> Contact | None:
    """The contact the colleague the user chose from the account's directory became; None where
    the directory does not list them."""
    login, _ = signin.login(account)
    with activesync.session(account, login.password) as client:
        person = _asked(client, name, address.lower())
    if person is None:
        raise Failed("activesync_unreachable")
    if not person:
        return None
    entry = _kept(account.activesync_host, address.lower(), person)
    return taking.colleague(account.owner_id, entry, chosen=True)


def passed(account_id: int) -> None:
    """Goes through the account's directory for the colleagues its owner met and the changes to
    those it lists, noting when and what failed."""
    account = Account.objects.get(pk=account_id)
    directory, _ = Directory.objects.get_or_create(account=account)
    error = ""
    try:
        login, _ = signin.login(account)
        with activesync.session(account, login.password) as client:
            met(client, account)
            refreshed(client, account)
    except Failed as failed:
        error = failed.code
    Directory.objects.filter(pk=directory.pk).update(passed_at=timezone.now(), error=error)
