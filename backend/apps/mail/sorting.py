"""Where a sender's mail goes by the user's rules (`Rule`): as it arrives, and the mail kept
before once a rule is made."""

from collections.abc import Iterable

from django.db.models import Q, QuerySet
from django.db.models.fields.json import KT

from .models import Folder, Message, Role, Rule

# The folders a rule takes no mail out of: the user's own, and what is put away already.
KEPT = (Role.SENT, Role.DRAFTS, Role.TRASH, Role.JUNK, Role.SNOOZED)


def names(address: str) -> list[str]:
    """What a rule may name the address by, the narrowest first: the address, then its domain
    and each domain that one is under."""
    address = address.strip().lower()
    local, _, domain = address.rpartition("@")
    if not local or not domain:
        return []
    labels = domain.split(".")
    return [address, *(".".join(labels[start:]) for start in range(len(labels) - 1))]


def _deciding(owner_id: int, addresses: Iterable[str]) -> dict[str, Rule]:
    """The rule that decides for each address the user has one for: the one of its narrowest
    name."""
    named = {address: names(address) for address in addresses}
    found = {
        rule.sender: rule
        for rule in Rule.objects.filter(
            owner_id=owner_id, sender__in={name for each in named.values() for name in each}
        ).select_related("folder")
    }
    return {
        address: rule
        for address, each in named.items()
        if (rule := next((found[name] for name in each if name in found), None))
    }


def arriving(owner_id: int, address: str, folder: Folder) -> Folder:
    """The folder a message from the address that arrives in the folder is kept in."""
    if folder.role in KEPT:
        return folder
    rule = _deciding(owner_id, [address]).get(address)
    return rule.folder if rule else folder


def _from(sender: str) -> Q:
    """The messages from the sender a rule names."""
    if "@" in sender:
        return Q(sender__address__iexact=sender)
    return Q(sender__address__iendswith=f"@{sender}") | Q(sender__address__iendswith=f".{sender}")


def _under(narrow: str, wide: str) -> bool:
    return "@" not in wide and narrow != wide and narrow.endswith((f"@{wide}", f".{wide}"))


def applied(rule: Rule) -> int:
    """Moves the user's mail the rule decides for to its folder, leaving what a narrower rule
    decides for; how many messages it moved."""
    found = (
        Message.objects.filter(owner_id=rule.owner_id)
        .exclude(folder__role__in=KEPT)
        .exclude(folder=rule.folder)
        .filter(_from(rule.sender))
    )
    for narrow in Rule.objects.filter(owner_id=rule.owner_id).values_list("sender", flat=True):
        if _under(narrow, rule.sender):
            found = found.exclude(_from(narrow))
    return found.update(folder=rule.folder)


def unblocked(owner_id: int, messages: QuerySet[Message]) -> None:
    """Takes away the rules that sent the messages to Junk, as the user says they are not junk."""
    addresses = {
        each.lower() for each in messages.values_list(KT("sender__address"), flat=True) if each
    }
    Rule.objects.filter(
        pk__in=[
            rule.pk
            for rule in _deciding(owner_id, addresses).values()
            if rule.folder.role == Role.JUNK
        ]
    ).delete()
