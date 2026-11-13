"""What the collections do on the server, in the mail's own loop (`apps.mail.later`): a month whose
time came goes first, then a message waiting to be read, then a look for new mail."""

from . import delivering, taking


def step() -> bool:
    return delivering.deliver_next() or taking.read_next() or taking.looked()
