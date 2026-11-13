"""Workbooks for tests, written and read back through openpyxl behind the calls the tests make
of a model: cells typed in, styles as dictionaries, a column's width and a row's height in
pixels."""

import io
import re
import zipfile
from copy import copy
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.worksheet.hyperlink import Hyperlink

NAMESPACE = (
    b'<worksheet xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
)
RELATIONS = b' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
ROOT = b"<workbook" + RELATIONS + b" "
PIXELS_PER_CHARACTER = 9
POINTS_PER_PIXEL = 0.64


def _typed(text: str):
    if text.startswith("'"):
        return text[1:]
    if text.upper() in ("TRUE", "FALSE"):
        return text.upper() == "TRUE"
    for read in (int, float):
        try:
            return read(text)
        except ValueError:
            pass
    return text


def _color(color) -> str | None:
    rgb = getattr(color, "rgb", None)
    return f"#{rgb[2:]}" if isinstance(rgb, str) and len(rgb) == 8 else None


def _style_of(owner) -> dict:
    found: dict = {
        "font": {"name": owner.font.name, "sz": owner.font.sz},
        "num_fmt": owner.number_format,
        "fill": {},
    }
    for key, on in (
        ("b", owner.font.b),
        ("i", owner.font.i),
        ("strike", owner.font.strike),
        ("u", owner.font.u),
    ):
        if on:
            found["font"][key] = True
    if color := _color(owner.font.color):
        found["font"]["color"] = color
    if owner.fill.patternType == "solid" and (color := _color(owner.fill.fgColor)):
        found["fill"] = {"color": color}
    aligned = {
        key: value
        for key, value in (
            ("horizontal", owner.alignment.horizontal),
            ("vertical", owner.alignment.vertical),
            ("wrap_text", owner.alignment.wrap_text),
        )
        if value
    }
    if aligned:
        found["alignment"] = aligned
    edges = {}
    for side in ("left", "right", "top", "bottom"):
        line = getattr(owner.border, side)
        if line is not None and line.style:
            edges[side] = {"style": line.style}
            if color := _color(line.color):
                edges[side]["color"] = color
    if edges:
        found["border"] = edges
    return found


def _styled(owner, style: dict) -> None:
    font = style.get("font") or {}
    owner.font = Font(
        name=font.get("name"),
        sz=font.get("sz"),
        b=font.get("b"),
        i=font.get("i"),
        strike=font.get("strike"),
        u="single" if font.get("u") else None,
        color=f"FF{font['color'][1:]}" if font.get("color") else None,
    )
    if color := (style.get("fill") or {}).get("color"):
        owner.fill = PatternFill("solid", fgColor=f"FF{color[1:]}")
    if "num_fmt" in style:
        owner.number_format = style["num_fmt"]
    if aligned := style.get("alignment"):
        owner.alignment = Alignment(**aligned)
    if edges := style.get("border"):
        owner.border = Border(
            **{
                side: Side(
                    style=line.get("style"),
                    color=f"FF{line['color'][1:]}" if line.get("color") else None,
                )
                for side, line in edges.items()
            }
        )


class Model:
    def __init__(self, book: Workbook, values: Workbook | None = None):
        self.book = book
        self.values = values or book
        self.saved: dict[str, dict[str, object]] = {}

    def _sheet(self, index: int):
        return self.book.worksheets[index]

    def new_sheet(self) -> None:
        self.book.create_sheet()

    def rename_sheet(self, index: int, title: str) -> None:
        self._sheet(index).title = title

    def evaluate(self) -> None:
        pass

    def set_user_input(self, index: int, row: int, col: int, text: str) -> None:
        cell = self._sheet(index).cell(row, col)
        cell.value = _typed(text)
        if text.startswith("'"):
            cell.data_type = "s"

    def set_user_array_formula(
        self, index: int, top: int, left: int, width: int, height: int, text: str
    ) -> None:
        bottom, right = top + height - 1, left + width - 1
        cell = f"{get_column_letter(left)}{top}"
        ref = f"{cell}:{get_column_letter(right)}{bottom}"
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                self._sheet(index).cell(y, x).value = 0
        self._sheet(index)[cell] = ArrayFormula(ref, text)

    def new_defined_name(self, name: str, scope: int | None, formula: str) -> None:
        defined = DefinedName(name, attr_text=formula)
        if scope is None:
            self.book.defined_names[name] = defined
        else:
            self._sheet(scope).defined_names[name] = defined

    def get_defined_name_list(self) -> list[dict]:
        found = [
            {"name": name, "scope": None, "formula": each.attr_text}
            for name, each in self.book.defined_names.items()
        ]
        for index, sheet in enumerate(self.book.worksheets):
            found += [
                {"name": name, "scope": index, "formula": each.attr_text}
                for name, each in sheet.defined_names.items()
            ]
        return found

    def get_worksheets_properties(self) -> list[dict]:
        return [{"name": sheet.title} for sheet in self.book.worksheets]

    def set_sheet_state(self, index: int, state: str) -> None:
        self._sheet(index).sheet_state = state

    def get_cell_style(self, index: int, row: int, col: int) -> dict:
        return _style_of(self._sheet(index).cell(row, col))

    def set_cell_style(self, index: int, row: int, col: int, style: dict) -> None:
        _styled(self._sheet(index).cell(row, col), style)

    def get_row_style(self, index: int, row: int) -> dict:
        return _style_of(self._sheet(index).row_dimensions[row])

    def set_row_style(self, index: int, row: int, style: dict) -> None:
        _styled(self._sheet(index).row_dimensions[row], style)

    def get_column_style(self, index: int, col: int) -> dict:
        return _style_of(self._sheet(index).column_dimensions[get_column_letter(col)])

    def set_column_style(self, index: int, col: int, style: dict) -> None:
        _styled(self._sheet(index).column_dimensions[get_column_letter(col)], style)

    def set_cell_link(self, index: int, row: int, col: int, link: dict) -> None:
        cell = self._sheet(index).cell(row, col)
        if link["type"] == "External":
            cell.hyperlink = link["target"]
        else:
            cell.hyperlink = Hyperlink(ref=cell.coordinate, location=link["location"])

    def merge_cells(self, index: int, top: int, left: int, bottom: int, right: int) -> None:
        self._sheet(index).merge_cells(
            start_row=top, start_column=left, end_row=bottom, end_column=right
        )

    def get_column_width(self, index: int, col: int) -> float:
        return self._sheet(index).column_dimensions[get_column_letter(col)].width * (
            PIXELS_PER_CHARACTER
        )

    def set_column_width(self, index: int, col: int, pixels: float) -> None:
        dimension = self._sheet(index).column_dimensions[get_column_letter(col)]
        dimension.width = pixels / PIXELS_PER_CHARACTER

    def set_column_hidden(self, index: int, col: int, hidden: bool) -> None:
        self._sheet(index).column_dimensions[get_column_letter(col)].hidden = hidden

    def set_row_height(self, index: int, row: int, pixels: float) -> None:
        self._sheet(index).row_dimensions[row].height = pixels * POINTS_PER_PIXEL

    def set_row_hidden(self, index: int, row: int, hidden: bool) -> None:
        self._sheet(index).row_dimensions[row].hidden = hidden

    def set_frozen_rows_count(self, index: int, count: int) -> None:
        self._sheet(index).freeze_panes = f"A{count + 1}"

    def get_cell_formula(self, index: int, row: int, col: int) -> str | None:
        value = self._sheet(index).cell(row, col).value
        return value if isinstance(value, str) and value.startswith("=") else None

    def get_formatted_cell_value(self, index: int, row: int, col: int) -> str:
        value = self.values.worksheets[index].cell(row, col).value
        if value is None:
            return ""
        return format(value, "g") if isinstance(value, float) else str(value)

    def _settled(self) -> None:
        """Each cell written with the style of its row or column, as Excel writes them."""
        for sheet in self.book.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.style_id or cell.value is None:
                        continue
                    line = sheet.row_dimensions.get(cell.row)
                    if line is None or not line.has_style:
                        line = sheet.column_dimensions.get(get_column_letter(cell.column))
                    if line is not None and line.has_style:
                        cell._style = copy(line._style)

    def to_xlsx(self) -> bytes:
        self._settled()
        found = io.BytesIO()
        self.book.save(found)
        written = io.BytesIO()
        with zipfile.ZipFile(found) as source, zipfile.ZipFile(written, "w") as target:
            for name in source.namelist():
                data = source.read(name)
                if name.startswith("xl/worksheets/"):
                    data = data.replace(b"<worksheet ", NAMESPACE, 1)
                    data = self._saved_in(name, data)
                if name == "xl/workbook.xml":
                    data = data.replace(RELATIONS, b"").replace(b"<workbook ", ROOT, 1)
                target.writestr(name, data)
        return written.getvalue()

    def _saved_in(self, name: str, data: bytes) -> bytes:
        """The values Excel would have saved with the formulas of the sheet."""
        found = re.search(r"sheet(\d+)\.xml$", name)
        if found is None:
            return data
        title = self.book.worksheets[int(found[1]) - 1].title
        text = data.decode()
        for address, value in self.saved.get(title, {}).items():
            kind = ' t="str"' if isinstance(value, str) else ""
            if isinstance(value, str) and value.startswith("#"):
                kind = ' t="e"'
            text = re.sub(
                rf'(<c r="{address}"[^>]*?)((?: t="\w+")?)>(<f>.*?</f>)<v></v>',
                lambda found, kind=kind, value=value: f"{found[1]}{kind}>{found[3]}<v>{value}</v>",
                text,
                count=1,
            )
        return text.encode()

    def save_to_xlsx(self, path: str) -> None:
        Path(path).write_bytes(self.to_xlsx())


def create() -> Model:
    return Model(Workbook())


def load(path) -> Model:
    return Model(load_workbook(path), load_workbook(path, data_only=True))
