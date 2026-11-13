import json

from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_migrate
from django.utils import timezone


def migrated(sender, using, **kwargs) -> None:
    from .models import Migrated

    version = json.loads(settings.REVISION_FILE.read_text())["version"]
    if not Migrated.objects.using(using).filter(pk=1, version=version).exists():
        Migrated.objects.using(using).update_or_create(
            pk=1, defaults={"version": version, "at": timezone.now()}
        )


class BackupsConfig(AppConfig):
    name = "apps.backups"

    def ready(self) -> None:
        post_migrate.connect(migrated, sender=self)
