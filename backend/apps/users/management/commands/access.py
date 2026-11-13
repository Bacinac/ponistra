import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.users import sessions
from apps.users.accounts import handed_password
from apps.users.models import User


class Command(BaseCommand):
    help = "Gives a user who cannot sign in a new password, prints it, and ends their sessions."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email, **options):
        user = User.objects.filter(email__iexact=email.strip()).first()
        if user is None:
            raise CommandError(f"no account has the address {email}")
        if not user.is_active:
            raise CommandError(f"{user.email} is deactivated")
        password = secrets.token_urlsafe(18)
        user.set_password(password)
        with transaction.atomic():
            user.save(update_fields=["password"])
            handed_password(user)
            sessions.ended(user)
        self.stdout.write(password)
