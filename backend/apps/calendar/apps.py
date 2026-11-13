from django.apps import AppConfig


class CalendarConfig(AppConfig):
    name = "apps.calendar"

    def ready(self) -> None:
        from apps.collab import live
        from apps.mail import taking

        from . import invitations, notes, views

        taking.ARRIVED.extend([invitations.noted, notes.noted])
        live.audience("k", views.concerned)
