"""Lipa Studio, a made-up company, with an account of it per language full of what the help's
pictures and the demo show, for scripts/check.sh --shots and scripts/demo.sh."""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.documents.models import Node
from apps.documents.notes import folder_of
from apps.help import source
from apps.help.seeds import SEEDS, company, documents, notes
from apps.users import sessions
from apps.users.models import Policy

LIFETIME = 60 * 60


def _complete(found: company.Company) -> bool:
    for language in source.LANGUAGES:
        place = folder_of(found.people[company.ACCOUNTS[language]])
        if place is None or Node.objects.filter(parent=place).count() < len(notes.NOTES):
            return False
    return True


def _filled(found: company.Company, language: str) -> None:
    user = found.people[company.ACCOUNTS[language]]
    user.language = language
    user.save(update_fields=["language"])

    def say(hr: str, en: str) -> str:
        return hr if language == "hr" else en

    seeded = company.Seeded(user, language, found, say)
    for seed in SEEDS:
        seed(seeded)


class Command(BaseCommand):
    help = "Seed Lipa Studio with an account per language and print the accounts' sessions."

    def handle(self, *args, **options):
        Policy.objects.get_or_create(pk=1, defaults={"passkeys": Policy.Passkeys.NOBODY})
        found = company.found()
        if found is None:
            found = company.founded()
            documents.shared(found)
            for language in source.LANGUAGES:
                _filled(found, language)
        elif not _complete(found):
            raise CommandError(
                f"{company.NAME} was seeded only in part; seed it into an empty installation."
            )
        accounts = {
            language: sessions.opened(found.people[company.ACCOUNTS[language]], LIFETIME)
            for language in source.LANGUAGES
        }
        self.stdout.write(json.dumps(accounts))
