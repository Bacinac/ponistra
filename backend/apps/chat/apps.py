from django.apps import AppConfig


class ChatConfig(AppConfig):
    name = "apps.chat"

    def ready(self) -> None:
        from apps.collab import live
        from apps.push import notices

        from . import conversations

        live.part("conversations", conversations.summaries)
        live.audience("o", conversations.concerned)
        notices.UNREAD.append(conversations.unread)
