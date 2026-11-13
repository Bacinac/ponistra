from django.apps import AppConfig


class AccessConfig(AppConfig):
    name = "apps.access"

    def ready(self) -> None:
        from apps.collab import live

        from . import rights

        live.audience("n", rights.concerned)
