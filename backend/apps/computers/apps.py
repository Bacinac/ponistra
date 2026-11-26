from django.apps import AppConfig


class ComputersConfig(AppConfig):
    name = "apps.computers"

    def ready(self) -> None:
        from apps.collab import live

        from .models import Manager

        def concerned(key: str):
            return Manager.objects.filter(computer_id=key).values_list("user_id", flat=True)

        live.audience("h", concerned)
