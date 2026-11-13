from django.apps import AppConfig


class CollabConfig(AppConfig):
    name = "apps.collab"

    def ready(self):
        from apps.core.views import shipped

        from . import live

        live.part("release", lambda _user: shipped())
