import base64
import hashlib
import json

from django.db import migrations

OWN = "@"


def digest(value) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return base64.urlsafe_b64encode(hashlib.sha256(text.encode()).digest()[:9]).decode()


def distanced(pieces: list, row: str, at: dict[str, int]) -> list:
    """The formula of a cell in the row with each reference written relative to another row of
    its table by the distance to it, and one written absolute to its own row by the row's id."""
    found = []
    for piece in pieces:
        if isinstance(piece, dict) and "table" not in piece:
            piece = dict(piece)
            for end in ("from", "to"):
                point = piece.get(end)
                if not isinstance(point, dict) or "row" not in point:
                    continue
                target = point["row"]
                if point.get("absRow"):
                    if target == OWN:
                        piece[end] = {**point, "row": row}
                elif target != OWN and target in at:
                    piece[end] = {**point, "row": at[target] - at[row] or OWN}
        found.append(piece)
    return found


def distance(apps, schema_editor):
    Grid = apps.get_model("content", "Grid")
    GridRow = apps.get_model("content", "GridRow")
    Shared = apps.get_model("content", "Shared")
    for document in Grid.objects.values_list("document_id", flat=True).distinct():
        shared = dict(Shared.objects.filter(document=document).values_list("key", "value"))
        found: dict[str, list] = {}
        for grid in Grid.objects.filter(document=document).values_list("pk", flat=True):
            rows = list(
                GridRow.objects.filter(grid=grid)
                .order_by("position")
                .values_list("pk", "row", "cells")
            )
            at = {row: index for index, (_, row, _) in enumerate(rows)}
            changed = []
            for pk, row, cells in rows:
                touched = False
                for cell in cells.values():
                    key = cell.get("formula")
                    if not isinstance(key, str):
                        continue
                    pieces = distanced(shared[key], row, at)
                    if pieces != shared[key]:
                        cell["formula"] = digest(pieces)
                        found[cell["formula"]] = pieces
                        touched = True
                if touched:
                    changed.append(GridRow(pk=pk, cells=cells))
            GridRow.objects.bulk_update(changed, ["cells"], batch_size=1000)
        Shared.objects.bulk_create(
            [Shared(document_id=document, key=key, value=value) for key, value in found.items()],
            ignore_conflicts=True,
        )
        used = {
            value
            for cells in GridRow.objects.filter(grid__document=document).values_list(
                "cells", flat=True
            )
            for cell in cells.values()
            for part in ("formula", "look")
            if isinstance(value := cell.get(part), str)
        }
        used |= set(
            GridRow.objects.filter(grid__document=document).exclude(look="").values_list(
                "look", flat=True
            )
        )
        used |= {
            col["look"]
            for cols in Grid.objects.filter(document=document).values_list("cols", flat=True)
            for col in cols
            if "look" in col
        }
        Shared.objects.filter(document=document).exclude(key__in=used).delete()


class Migration(migrations.Migration):
    dependencies = [("content", "0009_grid_row_words")]

    operations = [migrations.RunPython(distance, migrations.RunPython.noop)]
