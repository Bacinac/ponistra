from django.apps import AppConfig


class LocationsConfig(AppConfig):
    name = "apps.locations"

    def ready(self) -> None:
        from apps.collab import live

        from . import reach

        live.audience("l", reach.concerned)
