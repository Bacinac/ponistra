import hashlib
import json

from django.conf import settings
from django.db import migrations
from pycrdt import Doc, XmlElement, XmlFragment

from apps.content import pages

BODY = "body"
GRID = {
    "name": "grid",
    **json.loads(settings.SCHEMA.with_name("tables.json").read_text())["designs"]["grid"],
}
# One writer for every room and every version: the same state rewritten gives the same bytes,
# so a version that matched its room still matches it.
WRITER = 0xD30


def fragments(doc: Doc) -> list[XmlFragment]:
    names = set(doc.keys())
    found = [doc.get(BODY, type=XmlFragment)] if BODY in names else []
    if names & {*pages.PARTS, pages.TABS}:
        found += pages.fragments(doc)
    return found


def designed(data: list[bytes]) -> tuple[Doc, bytes | None]:
    """The state with each table drawn by its lines as the grid design, and one drawn without
    them as none; and the update that makes it so, None where nothing changed."""
    doc = Doc(client_id=WRITER)
    for each in data:
        doc.apply_update(each)
    before = doc.get_state()
    with doc.transaction():
        for fragment in fragments(doc):
            for element in fragment.children:
                if not isinstance(element, XmlElement) or element.tag != "table":
                    continue
                attributes = dict(element.attributes)
                if "designs" in attributes:
                    continue
                if attributes.get("borders") != "none":
                    element.attributes["designs"] = [GRID]
                if "borders" in attributes:
                    del element.attributes["borders"]
    return doc, (doc.get_update(before) if doc.get_state() != before else None)


def design(apps, schema_editor):
    Update = apps.get_model("collab", "Update")
    State = apps.get_model("versions", "State")
    for room, document, tab in Update.objects.values_list("room", "document", "tab").distinct():
        data = Update.objects.filter(room=room).order_by("id").values_list("data", flat=True)
        _, update = designed([bytes(each) for each in data])
        if update is not None:
            Update.objects.create(document_id=document, tab_id=tab, room=room, data=update)
    for pk, data in State.objects.values_list("pk", "data").iterator():
        doc, update = designed([bytes(data)])
        if update is not None:
            whole = doc.get_update()
            State.objects.filter(pk=pk).update(data=whole, sha256=hashlib.sha256(whole).hexdigest())


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0013_row_hidden"),
        ("collab", "0005_references_kept_by_the_database"),
        ("versions", "0007_words"),
    ]

    operations = [migrations.RunPython(design, migrations.RunPython.noop)]
