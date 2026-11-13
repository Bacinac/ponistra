from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "apps.users"

    def ready(self) -> None:
        from django.contrib.auth.signals import user_logged_in

        from apps.collab import live

        from . import confirmation
        from .models import User

        user_logged_in.connect(confirmation.signed_in)
        live.audience(
            "g", lambda key: User.objects.filter(groups=int(key)).values_list("pk", flat=True)
        )
