from django.db import migrations

PLACES = {"notes": "Notes", "links": "Links", "boards": "Boards"}


def named_by_flag(apps, schema_editor):
    node = apps.get_model("documents", "Node")
    for flag, title in PLACES.items():
        node.objects.filter(**{flag: True}).update(title=title)


class Migration(migrations.Migration):
    dependencies = [("documents", "0027_boards_place")]

    operations = [migrations.RunPython(named_by_flag, migrations.RunPython.noop)]
