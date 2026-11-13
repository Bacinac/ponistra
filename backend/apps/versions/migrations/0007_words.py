import django.contrib.postgres.indexes
import django.contrib.postgres.search
from django.db import migrations, models
from pycrdt import Doc

import apps.search.text
from apps.content import blocks


def tab_text(data: bytes) -> str:
    doc = Doc()
    doc.apply_update(bytes(data))
    return "\n".join(block.text for block in blocks.in_order(blocks.read(doc, {})) if block.text)


def piece_text(rows: list) -> str:
    return " ".join(
        text
        for row in rows
        for cell in row[2].values()
        if isinstance(text := cell.get("text"), str) and text
    )


def fill(apps, schema_editor):
    State = apps.get_model("versions", "State")
    VersionTab = apps.get_model("versions", "VersionTab")
    Piece = apps.get_model("versions", "Piece")
    held = VersionTab.objects.values_list("state", flat=True).distinct()
    for state in State.objects.filter(pk__in=held).iterator():
        State.objects.filter(pk=state.pk).update(text=tab_text(state.data))
    for piece in Piece.objects.iterator():
        Piece.objects.filter(pk=piece.pk).update(text=piece_text(piece.rows))


class Migration(migrations.Migration):
    dependencies = [
        ("versions", "0006_shared"),
    ]

    operations = [
        migrations.AddField(
            model_name="state",
            name="text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="piece",
            name="text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(fill, migrations.RunPython.noop),
        migrations.AddField(
            model_name="state",
            name="words",
            field=models.GeneratedField(
                db_persist=True,
                expression=apps.search.text.Words("text"),
                output_field=django.contrib.postgres.search.SearchVectorField(),
            ),
        ),
        migrations.AddField(
            model_name="piece",
            name="words",
            field=models.GeneratedField(
                db_persist=True,
                expression=apps.search.text.Words("text"),
                output_field=django.contrib.postgres.search.SearchVectorField(),
            ),
        ),
        migrations.AddIndex(
            model_name="state",
            index=django.contrib.postgres.indexes.GinIndex(fields=["words"], name="state_words"),
        ),
        migrations.AddIndex(
            model_name="piece",
            index=django.contrib.postgres.indexes.GinIndex(fields=["words"], name="piece_words"),
        ),
    ]
