from django.apps import AppConfig


class VaultConfig(AppConfig):
    name = "apps.vault"

    def ready(self) -> None:
        from apps.collab import live

        from . import views

        live.audience("c", views.concerned)
