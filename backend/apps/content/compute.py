"""What exporting a table and following its references need of the way it is laid out.

A formula is kept in pieces: text in the canonical form xlsx stores (English function names,
commas between arguments, a decimal point) and references by row and column id, each given the
place its row and column have now; a reference into another table of the document carries its id
too. Values are calculated in `calculation`."""

from collections.abc import Mapping
from dataclasses import dataclass

from pycrdt import Doc, XmlElement

from . import blocks, schema, sheets
from . import rows as stored
from .formulas import column_name, quote_name
from .grids import FORMULA, OWN, Laid

MISSING = "#REF!"
Place = tuple[dict[str, int], dict[str, int]]


@dataclass(frozen=True)
class Sheet:
    """What naming a table and writing its references needs: the ids of its rows and columns
    in order and its name."""

    rows: list[str]
    cols: list[str]
    name: str | None = None


def name_of(table: blocks.Block) -> str | None:
    name = table.attrs.get("name")
    return name if isinstance(name, str) and name else None


@dataclass(frozen=True)
class Name:
    """A defined name of the document, as a workbook keeps one: its formula in pieces, every
    reference in it with its table, in force in every table or only in the one named."""

    name: str
    pieces: list
    table: str | None = None


def _point(point, rows: dict[str, int], cols: dict[str, int], here: list[str]) -> str | None:
    if not isinstance(point, dict):
        return None
    text = ""
    if "col" in point:
        col = here[-1] if point["col"] == OWN else point["col"]
        if col not in cols:
            return None
        text += ("$" if point.get("absCol") else "") + column_name(cols[col])
    if "row" in point:
        row = here[0] if point["row"] == OWN else point["row"]
        if row not in rows:
            return None
        text += ("$" if point.get("absRow") else "") + str(rows[row])
    return text or None


def formula_text(
    pieces: list,
    own: str | None,
    places: dict[str, Place],
    titles: dict[str, str],
    key: str = "",
) -> str:
    """The formula of the cell at `key`, "row:col", in the canonical form, each reference in
    A1 by the places its rows and columns have, in the table `own` or after
    the title of its own; one whose table, row or column is gone is #REF!."""
    here = key.split(":")
    text = ""
    for piece in pieces:
        if isinstance(piece, str):
            text += piece
            continue
        if not isinstance(piece, dict):
            text += MISSING
            continue
        table = piece.get("table", own)
        if table not in places or ("table" in piece and table not in titles):
            text += MISSING
            continue
        rows, cols = places[table]
        ends = [piece.get("from"), *([piece["to"]] if "to" in piece else [])]
        found = [_point(end, rows, cols, here) for end in ends]
        if not found or None in found:
            text += MISSING
            continue
        sheet = quote_name(titles[table]) + "!" if "table" in piece else ""
        text += sheet + ":".join(found)
    return text


def places_of(sheets: dict[str, Sheet]) -> dict[str, Place]:
    return {
        id: (
            {row: index for index, row in enumerate(sheet.rows, 1)},
            {col: index for index, col in enumerate(sheet.cols, 1)},
        )
        for id, sheet in sheets.items()
    }


def titles_of(sheets: dict[str, Sheet]) -> dict[str, str]:
    """A sheet name for each table, as a workbook takes one: its own name where that is
    a valid one no table before it has, else a made-up one no table has."""
    titles: dict[str, str] = {}
    taken: set[str] = set()
    for id, sheet in sheets.items():
        if (
            sheet.name
            and schema.holds("tableName", sheet.name)
            and sheet.name.casefold() not in taken
        ):
            titles[id] = sheet.name
            taken.add(sheet.name.casefold())
    made = (f"Sheet{number}" for number in range(1, 2 * len(sheets) + 1))
    for id in sheets:
        if id not in titles:
            titles[id] = next(title for title in made if title.casefold() not in taken)
            taken.add(titles[id].casefold())
    return {id: titles[id] for id in sheets}


def placed_in(
    doc: Doc, grids: Mapping[str, Laid], ids: set[str] | None = None
) -> dict[str, tuple[Laid, XmlElement]]:
    """The tables in the tab's text that have a grid, those given or all of them, in its
    order: each one's grid and its element."""
    found = {}
    for element in blocks.body_of(doc).children:
        if isinstance(element, XmlElement) and element.tag == "table":
            id = element.attributes.get("id")
            if (ids is None or id in ids) and id in grids:
                found[id] = (grids[id], element)
    return found


def tables_in(
    doc: Doc, grids: Mapping[str, Laid], ids: set[str] | None = None
) -> dict[str, blocks.Block]:
    return {
        id: blocks.table_of(element, grids)
        for id, (_, element) in placed_in(doc, grids, ids).items()
    }


def names_in(entries: Mapping[str, dict]) -> list[Name]:
    """The document's defined names, given by id."""
    return [Name(each["name"], each["pieces"], each.get("table")) for each in entries.values()]


def tables_referred(pieces: list) -> set[str]:
    return {
        piece["table"]
        for piece in pieces
        if isinstance(piece, dict) and isinstance(piece.get("table"), str)
    }


def referred(held: sheets.Sheets, names: list[Name], table: str) -> bool:
    """Whether a formula of another table, or a defined name, refers to the table: by its
    name, which it must then keep. A table Postgres holds is read there, and in the rows a
    change to it wrote."""
    if any(table in tables_referred(name.pieces) for name in names):
        return True
    kept = False
    for _, found in held.tables():
        if isinstance(found, Laid):
            rows = found.rows
        else:
            rows = [*found.owned.values(), *found.made.values()]
            kept = True
        if any(
            isinstance(pieces := cell.get(FORMULA), list) and table in tables_referred(pieces)
            for row in rows
            for cell in row.cells.values()
        ):
            return True
    return kept and stored.referring(held.document, table)
