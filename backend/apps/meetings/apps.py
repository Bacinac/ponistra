from django.apps import AppConfig


class MeetingsConfig(AppConfig):
    name = "apps.meetings"

    def ready(self) -> None:
        from apps.collab import live

        from . import lobby, rings

        live.part("ringing", rings.ringing)
        live.part("rung", rings.rung)
        live.part("lobby", lobby.waiting)
        live.audience("r", recordings_concerned)


def recordings_concerned(key: str) -> list[int] | None:
    """Whom a change to a meeting's recordings concerns: the members of its conversation."""
    from apps.chat import conversations

    from .models import Meeting

    found = Meeting.objects.filter(pk=key).values_list("conversation_id", flat=True).first()
    return [] if found is None else conversations.concerned(str(found))
