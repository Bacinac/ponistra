from django.db import migrations, models

SHOWN = """
CREATE OR REPLACE FUNCTION grid_row_text(cells jsonb, shown jsonb) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
RETURN (
    SELECT coalesce(string_agg(coalesce(shown ->> key, cells -> key ->> 'text'), ' '), '')
    FROM (SELECT jsonb_object_keys(cells) UNION SELECT jsonb_object_keys(shown)) AS found(key)
)
"""

WAS = """
CREATE OR REPLACE FUNCTION grid_row_text(cells jsonb, shown jsonb) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
RETURN (
    SELECT coalesce(string_agg(coalesce(shown -> key ->> 'text', cells -> key ->> 'text'), ' '), '')
    FROM (SELECT jsonb_object_keys(cells) UNION SELECT jsonb_object_keys(shown)) AS found(key)
)
"""


def shown(apps, schema_editor):
    """Keeps the text each cell showed, its value calculated again as its table is next used."""
    GridRow = apps.get_model("content", "GridRow")
    changed = []
    for pk, cells, values in GridRow.objects.exclude(values={}).values_list(
        "pk", "cells", "values"
    ):
        found = {
            col: value["text"]
            for col, value in values.items()
            if isinstance(value, dict)
            and isinstance(value.get("text"), str)
            and value["text"] != (cells.get(col) or {}).get("text")
        }
        changed.append(GridRow(pk=pk, values={}, shown=found))
    GridRow.objects.bulk_update(changed, ["values", "shown"], batch_size=2000)


class Migration(migrations.Migration):
    dependencies = [("content", "0010_distances")]

    operations = [
        migrations.AddField(
            model_name="gridrow", name="shown", field=models.JSONField(default=dict)
        ),
        migrations.AddField(
            model_name="grid",
            name="calculated",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.RunPython(shown, migrations.RunPython.noop),
        migrations.RunSQL(SHOWN, WAS),
    ]
