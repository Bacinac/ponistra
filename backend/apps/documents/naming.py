from django.db import transaction

from .models import Node


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")[:200]


def follow(document: Node, texts: list[str]) -> None:
    """Names a document that follows its text after the first line its first tab now reads,
    and tells whoever has it open."""
    title = first_line(next((text for text in texts if text.strip()), ""))
    if not title or title == document.title:
        return
    if Node.objects.filter(pk=document.pk, follows_text=True).update(title=title):
        from apps.collab import server  # its own imports reach this module

        room = document.room
        transaction.on_commit(lambda: server.announce(room, "tabs"))
