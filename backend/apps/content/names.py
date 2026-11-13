"""A document's defined names (D16), kept in Postgres beside its grids: each by its id, with
the name formulas use, the formula it stands for in pieces by row and column id and, where
it is in force in one table alone, that table.

A change to them is a patch, {"names": {id: [before, after]}}, each entry whole or None
where there is none, so its inverse takes it back; taken back with a guard, an entry goes
back only where nobody changed it since."""

from collections.abc import Iterable, Mapping

from django.db import transaction

from apps.content.blocks import new_id
from apps.content.grids import pieces_rekeyed
from apps.content.models import Name

NAMES = "names"


def entry(name: str, pieces: list, table: str | None = None) -> dict:
    return {"name": name, "pieces": pieces, **({"table": table} if table else {})}


def of_document(document) -> dict[str, dict]:
    """The document's defined names, by id."""
    return {
        key: entry(name, pieces, table)
        for key, name, pieces, table in Name.objects.filter(document=document)
        .order_by("pk")
        .values_list("key", "name", "pieces", "table")
    }


def in_force(found: Mapping[str, dict], name: str, table: str | None) -> dict | None:
    """The defined name of that name in force in the table, whatever its case: the table's own
    before the document's."""
    folded = name.casefold()
    named = [each for each in found.values() if each["name"].casefold() == folded]
    return next((each for each in named if each.get("table") == table), None) or next(
        (each for each in named if "table" not in each), None
    )


def diff(before: Mapping[str, dict], after: Mapping[str, dict]) -> dict | None:
    """The patch that turns the names before into those after, none where they are alike."""
    changed = {
        key: [before.get(key), after.get(key)]
        for key in [*before, *(key for key in after if key not in before)]
        if before.get(key) != after.get(key)
    }
    return {NAMES: changed} if changed else None


def inverse(patch: dict) -> dict:
    return {NAMES: {key: [after, before] for key, (before, after) in patch[NAMES].items()}}


def apply(
    held: Mapping[str, dict], patch: dict, guard: bool = False
) -> tuple[dict[str, dict], dict | None]:
    """The names with the patch applied, and the patch as it went, with what it found, none
    where it changed nothing."""
    now = dict(held)
    done = {}
    for key, (before, after) in patch[NAMES].items():
        found = now.get(key)
        if (guard and found != before) or found == after:
            continue
        done[key] = [found, after]
        if after is None:
            del now[key]
        else:
            now[key] = after
    return now, ({NAMES: done} if done else None)


def store(document, patch: dict) -> None:
    """Writes what an applied patch changed, of the document given or by its id."""
    document = getattr(document, "pk", document)
    changed = patch[NAMES]
    if gone := [key for key, (_, after) in changed.items() if after is None]:
        Name.objects.filter(document=document, key__in=gone).delete()
    if kept := {key: after for key, (_, after) in changed.items() if after is not None}:
        Name.objects.bulk_create(
            [_row(document, key, each) for key, each in kept.items()],
            update_conflicts=True,
            unique_fields=["document", "key"],
            update_fields=["name", "pieces", "table"],
        )


@transaction.atomic
def put(document, entries: Mapping[str, dict]) -> None:
    """Writes the names given beside the document's: what an importer or a restored version
    brings where nobody has the document open."""
    document = getattr(document, "pk", document)
    Name.objects.bulk_create([_row(document, key, each) for key, each in entries.items()])


def _row(document, key: str, each: dict) -> Name:
    return Name(
        document_id=document,
        key=key,
        name=each["name"],
        pieces=each["pieces"],
        table=each.get("table") or "",
    )


def rekeyed(entries: Mapping[str, dict], by: Mapping[str, str]) -> dict[str, dict]:
    """The names referring to the tables, and in force in them, by the new ids given."""
    found = {}
    for key, each in entries.items():
        table = each.get("table")
        pieces = pieces_rekeyed(each["pieces"], by)
        found[key] = entry(each["name"], pieces, by.get(table, table) if table else None)
    return found


def joined(
    held: Mapping[str, dict], brought: Mapping[str, dict], tables: Iterable[str]
) -> dict[str, dict]:
    """The names brought from a file into the document beside those it holds, each by a new
    id. One the document already has in force in all of it is put in force in each of the
    tables brought instead, except one that has its own of the name, as a sheet's own name
    stands before the workbook's in Excel."""
    taken = {each["name"].casefold() for each in held.values() if not each.get("table")}
    own = {
        (each["table"], each["name"].casefold()) for each in brought.values() if each.get("table")
    }
    found = {}
    for each in brought.values():
        folded = each["name"].casefold()
        if each.get("table") or folded not in taken:
            found[new_id()] = each
            continue
        for table in tables:
            if (table, folded) not in own:
                found[new_id()] = entry(each["name"], each["pieces"], table)
    return found
