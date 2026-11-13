from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.backups import backups


class Command(BaseCommand):
    help = (
        "Builds the database as a snapshot left it, as far as the WAL reaches (latest) or at a "
        "moment (YYYY-MM-DD HH:MM) in --into/data, puts back its files and prints the version it "
        "ran with; the backend must be stopped."
    )

    def add_arguments(self, parser):
        parser.add_argument("which")
        parser.add_argument("--into", type=Path, required=True)

    def handle(self, *args, which, into, **options):
        try:
            self.stdout.write(backups.restore(which, into))
        except backups.Failed as failed:
            raise CommandError(failed) from None
