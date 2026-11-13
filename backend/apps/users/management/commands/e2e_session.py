"""A throwaway account for the browser check in scripts/check.sh."""

import json
import secrets

from django.core.management.base import BaseCommand, CommandError

from apps.access.visitors import invited_by
from apps.calendar.models import Resource
from apps.chat.models import Conversation
from apps.documents.models import Node
from apps.users import sessions
from apps.users.models import Policy, User

DOMAIN = "e2e.invalid"
LIFETIME = 15 * 60
ROOM = "Dvorana (e2e)"
# Told apart by the first name alone, which is what a colleague is searched by; none holds another.
COLLEAGUES = ["Ana", "Bruno", "Cvita", "Dino", "Ema", "Filip", "Goran", "Iva"]


def stop() -> None:
    users = User.objects.filter(email__endswith=f"@{DOMAIN}")
    let_in = invited_by(users)
    Node.objects.filter(created_by__in=users).delete()
    others = User.objects.exclude(email__endswith=f"@{DOMAIN}")
    Conversation.objects.filter(members__user__in=users).exclude(members__user__in=others).delete()
    users.delete()
    User.everyone.filter(pk__in=[each.pk for each in let_in]).delete()
    Resource.objects.filter(name=ROOM).delete()


def start(workers: int, retries: int) -> str:
    """For each of the browser's workers and each try of a test there, the session of an account
    of its own, of a colleague in the same installation with the colleague's name and of an
    administrator, and the password all of them confirm with (D33), which an installation that has
    chosen no policy yet lets them keep after a spec gives them a passkey."""
    if workers * (retries + 1) > len(COLLEAGUES):
        raise CommandError(f"{len(COLLEAGUES)} accounts at most, one to each worker and try")
    Policy.objects.get_or_create(pk=1, defaults={"passkeys": Policy.Passkeys.NOBODY})
    password = secrets.token_urlsafe(16)
    names = iter(COLLEAGUES)
    opened = [[account(next(names), password) for _ in range(retries + 1)] for _ in range(workers)]
    Resource.objects.get_or_create(name=ROOM, defaults={"capacity": 8, "place": "e2e"})
    return json.dumps({"password": password, "workers": opened})


def account(first_name: str, password: str) -> dict[str, str]:
    user = User.objects.create_user(f"{secrets.token_hex(4)}@{DOMAIN}", password)
    colleague = User.objects.create_user(
        f"{secrets.token_hex(4)}@{DOMAIN}", password, first_name=first_name, last_name="Kolegić"
    )
    administrator = User.objects.create_superuser(f"{secrets.token_hex(4)}@{DOMAIN}", password)
    return {
        "own": sessions.opened(user, LIFETIME),
        "colleague": sessions.opened(colleague, LIFETIME),
        "administrator": sessions.opened(administrator, LIFETIME),
        "name": f"{first_name} Kolegić",
    }


class Command(BaseCommand):
    help = (
        "start: print as JSON the session keys of fresh accounts, of their colleagues and of "
        "administrators, one of each to each of the browser's workers and each try of a test "
        "there, and their password; "
        "stop: delete every such account and the documents it made."
    )

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["start", "stop"])
        parser.add_argument("--workers", type=int, default=1)
        parser.add_argument("--retries", type=int, default=0)

    def handle(self, *args, action, workers, retries, **options):
        stop()
        if action == "start":
            self.stdout.write(start(workers, retries))
