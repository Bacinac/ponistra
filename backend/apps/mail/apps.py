from django.apps import AppConfig


class MailConfig(AppConfig):
    name = "apps.mail"

    def ready(self) -> None:
        from apps.collab import live
        from apps.push import notices

        from . import sharing, views

        notices.UNREAD.append(views.unseen)
        live.audience("m", sharing.concerned)
