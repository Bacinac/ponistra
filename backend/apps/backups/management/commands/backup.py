from django.core.management.base import BaseCommand, CommandError

from apps.backups import backups


class Command(BaseCommand):
    help = "Takes a snapshot of the database, the files and .env, and prints its id."

    def add_arguments(self, parser):
        parser.add_argument("--tag", action="append", default=[])

    def handle(self, *args, tag, **options):
        try:
            self.stdout.write(backups.backup(*tag))
        except backups.Failed as failed:
            raise CommandError(failed) from None
