"""A node made again in a folder of the tree: a document with its state, tabs and versions as
its own file holds them, a file with its bytes, a link with its address. A folder is made by
whoever walks it, each node below it copied into it in turn, so that each is placed as the
tree admits it."""

from django.db import transaction

from apps.imports import ponx

from .models import Node
from .views import created


def copied(node: Node, into: Node | None, title: str, user) -> Node:
    if node.kind == Node.Kind.DOCUMENT:
        return ponx.copy(node, into, title, user)
    if node.kind == Node.Kind.FOLDER:
        raise ValueError("a folder is copied by walking it")
    with transaction.atomic():
        made = created(
            into, node.kind, title, node.blob, user, extension=node.extension, href=node.href
        )
        made.description = node.description
        made.icon_id = node.icon_id
        made.save(update_fields=["description", "icon"])
    return made
