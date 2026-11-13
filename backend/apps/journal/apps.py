from django.apps import AppConfig


class JournalConfig(AppConfig):
    name = "apps.journal"

    def ready(self) -> None:
        from axes.signals import user_locked_out
        from django.contrib.auth.signals import user_logged_out, user_login_failed

        from . import entries

        user_login_failed.connect(entries.failed)
        user_logged_out.connect(entries.signed_out)
        user_locked_out.connect(entries.locked)
