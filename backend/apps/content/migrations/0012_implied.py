from django.conf import settings
from django.db import migrations
from django.utils import timezone

from apps.content.calculation import implied
from apps.engine.formats import Language


def formatted(apps, schema_editor):
    """Gives each cell typed without a number format the one Excel gives it as it is typed."""
    GridRow = apps.get_model("content", "GridRow")
    year = timezone.localtime().year
    changed = []
    rows = GridRow.objects.values_list("pk", "cells", "grid__document__locale")
    for pk, cells, locale in rows.iterator(chunk_size=2000):
        language = Language(locale, year, settings.CODE_PAGE)
        touched = False
        for cell in cells.values():
            text = cell.get("text")
            if isinstance(text, str) and not cell.get("format") and "formula" not in cell:
                if format := implied(text, language):
                    cell["format"] = format
                    touched = True
        if touched:
            changed.append(GridRow(pk=pk, cells=cells))
    GridRow.objects.bulk_update(changed, ["cells"], batch_size=2000)


class Migration(migrations.Migration):
    dependencies = [("content", "0011_values")]

    operations = [migrations.RunPython(formatted, migrations.RunPython.noop)]
