from apps.jobs.kinds import Kind

from . import moving, sharing

MOVE = "mail-move"


def asked(request, data: dict) -> dict:
    """The accounts the mail moves between, the person's own or those of a mailbox they own."""
    owner = request.user
    if (box := data.get("box")) is not None:
        owner = sharing.mailbox(request.user, str(box), sharing.OWN)
    source, into = moving.moving(owner, data)
    return {"owner": owner.pk, "from": source.pk, "to": into.pk}


def done(user, parameters: dict) -> dict:
    """Moves the mail, the mailbox's only while the person still owns it."""
    owner = parameters["owner"]
    owner = user if owner == user.pk else sharing.mailbox(user, str(owner), sharing.OWN)
    return moving.moved(owner, parameters)


KINDS = {MOVE: Kind(asked, done, saves=False)}
