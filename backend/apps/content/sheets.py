"""Changing the grids of a document's tables (D16), the same way for a run's operations and
for what a browser sends: cells written, lines put in, taken out and reordered, sizes and
names set. A formula arrives as text in the canonical form, its references in A1 by the
places rows and columns have now, another table's after that table's name, unique in the
document, and is kept in pieces by their ids; a browser gets it back as text, so the ids
stay on the server."""

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import replace

from . import formulas, grids, names, patching, schema
from . import rows as stored
from .blocks import Cell, key_of, spanned
from .formulas import column_name, quote_name
from .grids import FORMULA, OWN, ROWS, TO, Axis, Col, Laid, diff
from .table import Draft, Table

MISSING = "#REF!"


class Refused(Exception):
    """Why an operation of a run cannot be carried out: a code, what it concerns and which
    of the run's operations it was."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.operation: int | None = None


class Whole(Mapping):
    """A document's grids, each read whole when it is first asked for."""

    def __init__(self, sheets: Sheets, cut: bool):
        self.sheets, self.cut = sheets, cut
        self.read: dict[str, Laid] = {}
        self.parted: list[str] = []

    def __getitem__(self, table: str) -> Laid:
        if table not in self.read:
            found = self.sheets.peek(table)
            if found is None:
                raise KeyError(table)
            self.read[table] = self._whole(found) if isinstance(found, Draft) else found
        return self.read[table]

    def _whole(self, draft: Draft) -> Laid:
        cols = max(len(draft.col_ids()), 1)
        if draft.size * cols <= grids.MOST_CELLS:
            return draft.laid()
        if not self.cut:
            raise Refused("cells_over_ceiling", draft.name)
        self.parted.append(draft.name)
        return draft.first(grids.MOST_CELLS // cols)

    def __iter__(self) -> Iterator[str]:
        return (table for table, _ in self.sheets.tables())

    def __len__(self) -> int:
        return sum(1 for _ in self.sheets.tables())


class Sheets:
    """The grids of a document's tables and its defined names being changed, those of the
    tables of a tab's text in its order first: each grid copied from the one given as it is
    first asked for, and the names as one is first set, so what changed is the difference. A
    table made here is the tab's, or with no tab the document's headers' and footers'.

    Where it is known, `placing` holds the tables that stand in the texts of the document's
    tabs, each with the text of its cells that have a node: a grid whose block was taken out
    of the text is then computed no more and gives its name to no formula."""

    def __init__(
        self,
        grids: Mapping[str, Laid | Table],
        order: Iterable[str] | None = None,
        tab: str | None = None,
        defined: Mapping[str, dict] | None = None,
        placing: Mapping[str, Mapping[str, str]] | None = None,
        document=None,
    ):
        self.base = dict(grids)
        self.order = list(order) if order is not None else list(self.base)
        self.tab = tab
        self.copies: dict[str, dict] = {}
        self.document = document
        self.now: dict[str, Laid | Draft | None] = {}
        self.defined = dict(defined or {})
        self._names: dict[str, dict] | None = None
        self.placing = placing

    def stands(self, table: str) -> bool:
        """Whether the table stands in the document: in a tab's text, in a header's or a
        footer's, or made here; every grid does where that is not known."""
        if self.placing is None or table in self.placing:
            return True
        laid = self.peek(table)
        return laid is not None and (laid.tab is None or table not in self.base)

    def __contains__(self, table: str) -> bool:
        return self.peek(table) is not None

    def peek(self, table: str) -> Laid | Draft | None:
        """The grid as it now is, for reading only."""
        if table in self.now:
            return self.now[table]
        found = self.base.get(table)
        return self.get(table) if isinstance(found, Table) else found

    def get(self, table: str) -> Laid | Draft:
        """The grid, to change: a table Postgres holds as a draft of it, one held whole as a
        copy."""
        if table not in self.now:
            found = self.base.get(table)
            if found is None:
                raise KeyError(table)
            self.now[table] = (
                Draft(self.document, found) if isinstance(found, Table) else found.copy()
            )
        found = self.now[table]
        if found is None:
            raise KeyError(table)
        return found

    def grids(self, cut: bool = False) -> Whole:
        """Every grid there is, as it now is, by table, for reading only, each read as it is
        asked for: whole, and past the ceiling refused or, where asked, only its first rows."""
        return Whole(self, cut)

    def tables(self) -> Iterator[tuple[str, Laid | Draft]]:
        """Every grid there is, those of the tab's text in its order first."""
        seen = set()
        for table in [*self.order, *self.base, *self.now]:
            if table in seen:
                continue
            seen.add(table)
            if (found := self.peek(table)) is not None:
                yield table, found

    def make(self, laid: Laid) -> None:
        if self.peek(laid.table) is not None:
            raise Refused("taken", laid.table)
        self.now[laid.table] = laid

    def copied(self, source: Draft, table: str, name: str, locale: str | None) -> None:
        """A copy of the table Postgres holds, its rows copied there when the change is stored,
        each formula as the value it shows written in the locale, where one is given. Until
        then it reads the rows of its source."""
        if self.peek(table) is not None:
            raise Refused("taken", table)
        made = {"tab": self.tab, "name": name, "from": source.table}
        self.copies[table] = made | ({"values": locale} if locale else {})
        self.now[table] = Draft(
            self.document, replace(source.base, table=table, name=name, tab=self.tab)
        )

    def names(self) -> Mapping[str, dict]:
        """The defined names as they now are, by id, for reading only."""
        return self.defined if self._names is None else self._names

    def name(self, key: str, entry: dict | None) -> None:
        """Sets the defined name of the id, None taking it out."""
        if self._names is None:
            self._names = dict(self.defined)
        if entry is None:
            self._names.pop(key, None)
        else:
            self._names[key] = entry

    def patches(self) -> list[dict]:
        found = [{"table": table, "made": made} for table, made in self.copies.items()]
        found += [
            patch
            for table, now in self.now.items()
            if (patch := _patch(self.base.get(table), now)) is not None
        ]
        if self._names is not None and (patch := names.diff(self.defined, self._names)):
            found.append(patch)
        return found


def _patch(base: Laid | Table | None, now: Laid | Draft | None) -> dict | None:
    if isinstance(now, Draft):
        return now.patch()
    if isinstance(base, Table):
        return {"table": base.table, "gone": {}}
    return diff(base, now)


def inverse(patch: dict) -> dict:
    """The patch, of a grid or of the defined names, that takes the one given back."""
    return names.inverse(patch) if names.NAMES in patch else patching.inverse(patch)


def apply_stored(
    document,
    tables: Mapping[str, Table],
    defined: Mapping[str, dict],
    patches: list[dict],
    guard: bool = False,
) -> tuple[dict[str, Table], dict[str, dict], list[patching.Done], list[dict]]:
    """The tables Postgres holds and the defined names with the patches applied, each to its
    table or to the names as those before it left them, and those that changed anything as
    they went: of the tables, and of the names. Not written for the names, which their caller
    stores with what else it keeps of the document."""
    now = dict(tables)
    done = []
    renamed = []
    for patch in patches:
        if names.NAMES in patch:
            defined, went = names.apply(defined, patch, guard)
            if went is not None:
                renamed.append(went)
            continue
        went = patching.apply(document, now.get(patch["table"]), patch, guard)
        if went.patch is None:
            continue
        if went.table is None:
            now.pop(patch["table"], None)
        else:
            now[patch["table"]] = went.table
        done.append(went)
    return now, dict(defined), done, renamed


def merged(laid: Laid | Draft) -> list:
    """The table's merged cells as it shows them: each that reaches beyond its own slot, as
    far as no merge before it covers."""
    merges = laid.merges()
    if not merges:
        return []
    cells = [Cell(*key.split(":", 1), to=to) for key, to in merges.items()]
    rows = laid.places({cell.row for cell in cells} | {cell.to.partition(":")[0] for cell in cells})
    cols = {id: at for at, id in enumerate(laid.col_ids())}
    return [each for each in spanned(cells, rows, cols) if each.rows > 1 or each.cols > 1]


def covered(laid: Laid | Draft) -> set[str]:
    """The slots a merged cell covers beyond its own."""
    cols = laid.col_ids()
    found = set()
    for each in merged(laid):
        rows = laid.ids(each.y, each.y + each.rows - 1)
        found |= {
            key_of(rows[y - each.y], cols[x])
            for y in range(each.y, each.y + each.rows)
            for x in range(each.x, each.x + each.cols)
            if (y, x) != (each.y, each.x)
        }
    return found


def named(sheets: Sheets) -> dict[str, str]:
    """The tables a formula finds by name, case-folded, the first of those that share one,
    which a document brought from elsewhere may."""
    found: dict[str, str] = {}
    for table, laid in sheets.tables():
        if laid.name and sheets.stands(table):
            found.setdefault(laid.name.casefold(), table)
    return found


def _point(
    end: formulas.End, laid: Laid | Draft, cols: list[str], shift: tuple[int, int]
) -> dict | None:
    point: dict = {}
    if end.row is not None:
        row = end.row + (0 if end.abs_row else shift[0])
        if not 1 <= row <= laid.size:
            return None
        point["row"] = laid.ids_at([row - 1])[row - 1]
        if end.abs_row:
            point["absRow"] = True
    if end.col is not None:
        col = end.col + (0 if end.abs_col else shift[1])
        if not 1 <= col <= len(cols):
            return None
        point["col"] = cols[col - 1]
        if end.abs_col:
            point["absCol"] = True
    return point


def pieces_of(
    sheets: Sheets, text: str, own: str, defined: set[str], shift: tuple[int, int] = (0, 0)
) -> list:
    """A formula as a table keeps it: each reference by the ids of its rows and columns. A
    formula copied from elsewhere comes with how far it moved, in rows and columns, which its
    relative references move with, as in Excel: one moved outside its table is #REF!."""
    tables = named(sheets)
    ids = list(tables.values())
    pieces: list = []
    for part in formulas.Formulas(list(tables), defined).parts(text.removeprefix("=")):
        if isinstance(part, formulas.Ref):
            table = own if part.sheet is None else ids[part.sheet]
            laid = sheets.peek(table)
            cols = laid.col_ids()
            start = _point(part.start, laid, cols, shift)
            end = _point(part.end, laid, cols, shift) if part.end else {}
            if start is None or end is None:
                if shift == (0, 0):
                    raise Refused("outside", part.text)
                piece: list | dict | str = MISSING
            else:
                piece = {
                    **({"table": table} if table != own else {}),
                    "from": start,
                    **({"to": end} if part.end else {}),
                }
        else:
            piece = part
            bare = formulas.QUOTED.sub('""', piece)
            for found in formulas.SHEET.finditer(bare):
                if formulas.address(bare, found.end()):
                    raise Refused("no_table", found[0].removesuffix("!"))
        if isinstance(piece, str) and pieces and isinstance(pieces[-1], str):
            pieces[-1] += piece
        else:
            pieces.append(piece)
    return pieces


def _place(
    point, rows: Mapping[str, int], cols: Mapping[str, int], here: tuple[str | None, str | None]
) -> str | None:
    if not isinstance(point, dict):
        return None
    text = ""
    if "col" in point:
        col = here[1] if point["col"] == grids.OWN else point["col"]
        if col not in cols:
            return None
        text += ("$" if point.get("absCol") else "") + column_name(cols[col])
    if "row" in point:
        row = here[0] if point["row"] == grids.OWN else point["row"]
        if row not in rows:
            return None
        text += ("$" if point.get("absRow") else "") + str(rows[row])
    return text or None


class _Standing:
    """Where each row of a table stands, counted from 1, as far as asked for."""

    def __init__(self, laid: Laid | Draft):
        self.laid = laid
        self.found: dict[str, int | None] = {}

    def get(self, id: str) -> int | None:
        if id not in self.found:
            place = self.laid.place(id)
            self.found[id] = None if place is None else place + 1
        return self.found[id]

    def __contains__(self, id: object) -> bool:
        return isinstance(id, str) and self.get(id) is not None

    def __getitem__(self, id: str) -> int:
        if (found := self.get(id)) is None:
            raise KeyError(id)
        return found


class Places:
    """Where every row and column of the document's tables stands, counted from 1, and the
    name a formula gives each table by, to write formulas as text."""

    def __init__(self, sheets: Sheets):
        self.sheets = sheets
        self.found: dict[str, tuple[_Standing, dict[str, int]]] = {}
        self.names = {
            table: laid.name
            for table, laid in sheets.tables()
            if laid.name and sheets.stands(table)
        }

    def of(self, table: str) -> tuple[_Standing, dict[str, int]] | None:
        if table not in self.found:
            laid = self.sheets.peek(table)
            if laid is None:
                return None
            self.found[table] = (
                _Standing(laid),
                {id: at for at, id in enumerate(laid.col_ids(), 1)},
            )
        return self.found[table]

    def learn(self, cells: Iterable[tuple[str, dict]]) -> None:
        """Reads at once where the rows stand that the formulas of the cells name, each cell
        given with its table, rather than row by row as their texts are written."""
        wanted: dict[str, set[str]] = {}
        for own, cell in cells:
            for piece in cell.get(FORMULA) or ():
                if not isinstance(piece, dict):
                    continue
                for end in ("from", "to"):
                    target = (piece.get(end) or {}).get("row")
                    if isinstance(target, str) and target != OWN:
                        wanted.setdefault(piece.get("table", own), set()).add(target)
        for table, ids in wanted.items():
            if (found := self.of(table)) is None:
                continue
            standing = found[0]
            if missing := ids - standing.found.keys():
                places = standing.laid.places(missing)
                for id in missing:
                    standing.found[id] = places[id] + 1 if id in places else None

    def text(self, pieces: list, own: str, row: str | None = None, col: str | None = None) -> str:
        """The formula of the cell at the row and column given as it is typed, in the canonical
        form, each reference in A1 by the places its rows and columns have, after the name of
        its table where that is another; one whose table, row or column is gone is #REF!."""
        text = "="
        for piece in pieces:
            if isinstance(piece, str):
                text += piece
                continue
            table = piece.get("table", own) if isinstance(piece, dict) else None
            places = self.of(table) if table else None
            if places is None or ("table" in piece and table not in self.names):
                text += MISSING
                continue
            ends = [piece.get("from"), *([piece["to"]] if "to" in piece else [])]
            found = [_place(end, *places, (row, col)) for end in ends]
            if not found or None in found:
                text += MISSING
                continue
            sheet = quote_name(self.names[table]) + "!" if "table" in piece else ""
            text += sheet + ":".join(found)
        return text


class Lines:
    """A table's columns, read by place as its rows are."""

    def __init__(self, ids: list[str]):
        self.list = ids
        self.at = {id: at for at, id in enumerate(ids)}
        self.size = len(ids)

    def places(self, ids: Iterable[str]) -> dict[str, int]:
        return {id: self.at[id] for id in ids if id in self.at}

    def ids_at(self, places: Iterable[int]) -> dict[int, str]:
        return {place: self.list[place] for place in places if 0 <= place < self.size}

    def ids(self, first: int, last: int) -> list[str]:
        return self.list[max(first, 0) : max(last + 1, 0)]


def without_lines(
    pieces: list, part: str, lines, gone: Mapping[str, int], table: str, own: str | None
) -> list | None:
    """The pieces with each range in the table whose first or last row or column goes keeping
    the rest of its lines, as in Excel; a reference to nothing but what goes stays, to show
    #REF!. A reference without a table of its own is in its formula's own table; None where
    nothing changed. The lines are read by place, those that go given with theirs."""
    changed = False
    kept_pieces = []
    out = set(gone.values())
    for piece in pieces:
        start, end = (piece.get("from"), piece.get("to")) if isinstance(piece, dict) else (0, 0)
        if (
            isinstance(start, dict)
            and isinstance(end, dict)
            and (piece.get("table") or own) == table
            and (start.get(part) in gone or end.get(part) in gone)
        ):
            first, last = start.get(part), end.get(part)
            at = lines.places([first, last])
            if first in at and last in at and at[first] <= at[last]:
                low, high = at[first], at[last]
                while low <= high and low in out:
                    low += 1
                while high >= low and high in out:
                    high -= 1
                if low <= high:
                    ends = lines.ids_at([low, high])
                    piece = {
                        **piece,
                        "from": {**start, part: ends[low]},
                        "to": {**end, part: ends[high]},
                    }
                    changed = True
        kept_pieces.append(piece)
    return kept_pieces if changed else None


def reordered(
    pieces: list, before: list[str], after: list[str], table: str, own: str | None
) -> list | None:
    """The pieces with each range in the table over several rows covering the same places
    after its rows are reordered, as in Excel; None where nothing changed."""
    at = dict(zip(before, after, strict=True))
    changed = False
    kept_pieces = []
    for piece in pieces:
        start, end = (piece.get("from"), piece.get("to")) if isinstance(piece, dict) else (0, 0)
        if (
            isinstance(start, dict)
            and isinstance(end, dict)
            and (piece.get("table") or own) == table
            and (first := start.get("row")) is not None
            and (last := end.get("row")) is not None
            and first != last
            and (at.get(first, first), at.get(last, last)) != (first, last)
        ):
            piece = {
                **piece,
                "from": {**start, "row": at.get(first, first)},
                "to": {**end, "row": at.get(last, last)},
            }
            changed = True
        kept_pieces.append(piece)
    return kept_pieces if changed else None


Change = Callable[[list, str | None], list | None]


def rewrite(
    sheets: Sheets,
    change: Change,
    table: str | None = None,
    spans: Iterable[tuple[int, int]] = (),
    mentioned: Iterable[str] = (),
) -> None:
    """Every formula of the document's tables and every defined name as `change` makes its
    pieces, given the table a reference without a table of its own is in, none for a name. Of
    a table Postgres holds, the formulas that can be changed: those of its rows read, those
    within the spans of places given of the table given, and those naming the lines given."""
    for key, entry in list(sheets.names().items()):
        if kept := change(entry["pieces"], None):
            sheets.name(key, {**entry, "pieces": kept})
    drafts = [found for _, found in sheets.tables() if isinstance(found, Draft)]
    mentions = stored.mentioning(sheets.document, mentioned) if drafts and mentioned else {}
    for name, laid in list(sheets.tables()):
        if isinstance(laid, Draft):
            ids = {*laid.owned, *laid.made, *mentions.get(name, ())}
            if name == table:
                for first, last in spans:
                    ids |= set(laid.ids(first, last))
            laid.load(ids)
            rows = [row for id in ids if (row := laid.row(id)) is not None]
        else:
            rows = laid.rows
        found = [
            (row.id, col, cell[FORMULA])
            for row in rows
            for col, cell in row.cells.items()
            if isinstance(cell.get(FORMULA), list)
        ]
        changed = [
            (row, col, kept)
            for row, col, pieces in found
            if (kept := change(grids.formula_in(pieces, row, col), name))
        ]
        if changed:
            laid = sheets.get(name)
            for row, col, kept in changed:
                laid.own(row).cells[col][FORMULA] = grids.formula_at(kept, row, col)


def _spans(places: Iterable[int], reach: int) -> list[tuple[int, int]]:
    return [(first - reach, first + count - 1 + reach) for first, count in _runs(places)]


def _runs(places: Iterable[int]) -> list[tuple[int, int]]:
    found: list[list[int]] = []
    for place in sorted(set(places)):
        if found and place == found[-1][0] + found[-1][1]:
            found[-1][1] += 1
        else:
            found.append([place, 1])
    return [(first, count) for first, count in found]


def _reach(sheets: Sheets) -> int:
    return stored.reach(sheets.document) if sheets.document is not None else 0


def write(laid: Laid, row: str, col: str, given: Mapping[str, object]) -> None:
    """Sets the parts of the cell given, a part given as None cleared. A look is kept only
    where it is not the one the cell's row or column gives it."""
    if laid.row(row) is None or laid.col(col) is None:
        raise Refused("no_cell", key_of(row, col))
    cells = laid.own(row).cells
    cell = cells.setdefault(col, {})
    for part, value in given.items():
        if part == grids.LOOK and isinstance(value, dict):
            shown = grids.look(value)
            if shown == (laid.inherited(row, col) or {}):
                cell.pop(part, None)
            else:
                cell[part] = shown
        elif value is None or value == "" or value == {}:
            cell.pop(part, None)
        elif part == FORMULA and isinstance(value, list):
            cell[part] = grids.formula_at(value, row, col)
        else:
            cell[part] = value
    if not cell:
        del cells[col]


def put_lines(
    laid: Laid | Draft,
    axis: Axis,
    ids: list[str],
    before: str | None = None,
    sizes: list[float | None] | None = None,
) -> None:
    """Puts new lines in, before the line given or at the end."""
    if axis == ROWS:
        if taken := sorted(laid.places(ids)):
            raise Refused("taken", taken[0])
        if len(set(ids)) != len(ids):
            raise Refused("taken", ids[0])
        if before is not None and not laid.has(before):
            raise Refused("no_line", before)
        laid.put_rows(ids, before, sizes or [])
        return
    now = laid.col_ids()
    if taken := sorted(set(now) & set(ids)):
        raise Refused("taken", taken[0])
    if len(set(ids)) != len(ids):
        raise Refused("taken", ids[0])
    if before is not None and before not in now:
        raise Refused("no_line", before)
    at = now.index(before) if before is not None else len(now)
    sizes = sizes or []
    for offset, id in enumerate(ids):
        size = sizes[offset] if offset < len(sizes) else None
        laid.cols.insert(at + offset, Col(id, size))


def take_lines(sheets: Sheets, table: str, axis: Axis, gone: set[str]) -> dict[str, str]:
    """Takes the lines out of the table: a merged cell keeps its slots in the others, with its
    formula and number format, and one within them goes, as in the editor; every formula of
    the document that refers to them is rewritten. Returns where each merged cell moved that kept
    its place, "row:col" before and after, as a cell with a node in the text moves with it."""
    laid = sheets.get(table)
    cols = laid.col_ids()
    lines, part = (laid, "row") if axis == ROWS else (Lines(cols), "col")
    at = lines.places(gone)
    if missing := sorted(gone - at.keys()):
        raise Refused("no_line", missing[0])
    if len(at) >= lines.size:
        raise Refused("lines", "a table keeps a row and a column")
    moved: dict[str, str] = {}
    for each in merged(laid):
        start, size = (each.y, each.rows) if axis == ROWS else (each.x, each.cols)
        span = lines.ids(start, start + size - 1)
        kept = [line for line in span if line not in gone]
        if size == 1 or not kept or (kept[0], kept[-1]) == (span[0], span[-1]):
            continue
        rows = laid.ids(each.y, each.y + each.rows - 1)
        top, left = rows[0], cols[each.x]
        bottom, right = rows[-1], cols[each.x + each.cols - 1]
        if axis == ROWS:
            top, bottom = kept[0], kept[-1]
        else:
            left, right = kept[0], kept[-1]
        cell = laid.own(each.cell.row).cells.pop(each.cell.col, {})
        if isinstance(cell.get(FORMULA), list):
            before = (each.cell.row, each.cell.col)
            cell[FORMULA] = grids.moved_formula(cell[FORMULA], before, (top, left))
        if (top, left) != (bottom, right):
            cell[TO] = key_of(bottom, right)
        else:
            cell.pop(TO, None)
        if cell:
            laid.own(top).cells[left] = cell
        moved[key_of(each.cell.row, each.cell.col)] = key_of(top, left)
    spans = _spans(at.values(), _reach(sheets)) if axis == ROWS else []
    rewrite(
        sheets,
        lambda pieces, owner: without_lines(pieces, part, lines, at, table, owner),
        table,
        spans,
        gone,
    )
    laid = sheets.get(table)
    if axis == ROWS:
        laid.take_rows(gone)
    else:
        laid.take_cols(gone)
    return moved


def order_rows(sheets: Sheets, table: str, ordered: list[str]) -> tuple[list[str], list[str]]:
    """Puts the rows given, where they stand, in the order given; a range over several rows
    keeps covering the same places and a reference within one row follows it, as in the
    editor. Returns the order before and after of the rows from the first of those given to
    the last."""
    laid = sheets.get(table)
    at = laid.places(ordered)
    if missing := sorted(set(ordered) - at.keys()):
        raise Refused("no_line", missing[0])
    if not at:
        return [], []
    first, last = min(at.values()), max(at.values())
    before = laid.ids(first, last)
    queue, given = iter(ordered), set(ordered)
    after = [next(queue) if id in given else id for id in before]
    if after == before:
        return before, after
    for each in merged(laid):
        if each.rows > 1 and any(
            first <= y <= last and after[y - first] != before[y - first]
            for y in range(each.y, each.y + each.rows)
        ):
            raise Refused("merged_rows", key_of(each.cell.row, each.cell.col))
    reach = _reach(sheets)
    rewrite(
        sheets,
        lambda pieces, owner: reordered(pieces, before, after, table, owner),
        table,
        [(first - reach, last + reach)],
        before,
    )
    sheets.get(table).order_rows(first, after)
    return before, after


def sized(laid: Laid, widths: Mapping[str, float | None], heights: Mapping[str, float | None]):
    for col in laid.cols:
        if col.id in widths:
            col.width = widths[col.id]
    for id, height in heights.items():
        if laid.row(id) is not None:
            laid.own(id).height = height


def _numbered(name: str, taken: Iterable[str]) -> str:
    """The name with the first number from 2 in brackets that none of those taken has,
    case-folded."""
    number = 2
    while True:
        suffix = f" ({number})"
        found = name[: schema.TABLE_NAME_LENGTH - len(suffix)] + suffix
        if found.casefold() not in taken:
            return found
        number += 1


def copy_name(sheets: Sheets, name: str) -> str:
    """The name of a copy of the table of the name, none for a table without a name."""
    return _numbered(name, named(sheets)) if name else ""


def apart(laids: Iterable[Laid], taken: Iterable[str]) -> None:
    """Names each grid whose name one of those taken has, or a grid before it, ignoring case,
    as a copy of it would be: grids brought into a document beside its own tables."""
    folded = {name.casefold() for name in taken}
    for laid in laids:
        if laid.name and laid.name.casefold() in folded:
            laid.name = _numbered(laid.name, folded)
        if laid.name:
            folded.add(laid.name.casefold())


def parted(sheets: Sheets, kept: Iterable[str]) -> bool:
    """Names each table standing that shares a name with one before it, ignoring case, as a
    copy of it would be, the tables kept coming first: a table whose block came back into a
    tab's text after another took its name. Whether any was renamed."""
    first = set(kept)
    standing = sorted(
        (table for table, laid in sheets.tables() if laid.name and sheets.stands(table)),
        key=lambda table: table not in first,
    )
    folded: set[str] = set()
    clashing = []
    for table in standing:
        name = sheets.peek(table).name.casefold()
        if name in folded:
            clashing.append(table)
        folded.add(name)
    for table in clashing:
        laid = sheets.get(table)
        laid.name = _numbered(laid.name, folded)
        folded.add(laid.name.casefold())
    return bool(clashing)


def name_problem(sheets: Sheets, table: str, name: str) -> str | None:
    """Why the table cannot have the name, none where it can."""
    if name and not schema.holds("tableName", name):
        return "name"
    taken = named(sheets)
    if name and taken.get(name.casefold(), table) != table:
        return "name_taken"
    return None
