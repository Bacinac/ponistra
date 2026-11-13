from string import hexdigits

from django.core.management.base import BaseCommand, CommandError

from apps.backups import backups


class Command(BaseCommand):
    help = (
        "Lists the snapshots kept, or prints for a snapshot, latest or a moment the one a restore "
        "starts from, the version that took it and whether it holds a base or a dump of the "
        "database."
    )

    def add_arguments(self, parser):
        parser.add_argument("--which", metavar="SNAPSHOT")

    def handle(self, *args, which, **options):
        try:
            if which:
                self.which(which)
                return
            found = backups.snapshots()
        except backups.Failed as failed:
            raise CommandError(failed) from None
        for snapshot in found:
            when = snapshot["time"].strftime("%d.%m.%Y. %H:%M")
            version = snapshot["version"] or "-"
            tags = " ".join(snapshot["tags"])
            self.stdout.write(f"{snapshot['id']}  {when}  {version}  {tags}".rstrip())

    def which(self, which: str) -> None:
        if which != "latest" and all(character in hexdigits for character in which):
            found = backups.snapshots(which)
        else:
            found = backups.snapshots(backups.chosen(which)[0]["short_id"])
        if not found or not found[0]["version"]:
            raise CommandError(f"no snapshot {which} with a version")
        kind = "base" if found[0]["starts"] else "dump"
        self.stdout.write(f"{found[0]['id']} {found[0]['version']} {kind}")
