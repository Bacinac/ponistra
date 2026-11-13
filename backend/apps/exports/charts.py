"""A chart of the document as Word and Excel keep one (DrawingML): its kind, title and legend,
and the cells of its sheet each series takes its name, categories and values from, with what
they show until Office computes them again, in the document's font and the series colours
the editor draws."""

from dataclasses import dataclass

from lxml import etree

from apps.content import charts, fonts, palette
from apps.content.formulas import column_name
from apps.content.grids import FORMAT
from apps.content.models import GridRow
from apps.content.schema import CHART_TITLE_LENGTH, STACKING
from apps.imports.word import EMU_PER_CM

C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"c": C, "a": A, "r": R}
# The editor draws a chart across the text, its height so many times less (editor/charts.ts).
ASPECT = 5 / 3
EMU_PER_PIXEL = 9525
GROUPS = {
    "column": "barChart",
    "bar": "barChart",
    "line": "lineChart",
    "area": "areaChart",
    "pie": "pieChart",
    "doughnut": "doughnutChart",
    "scatter": "scatterChart",
}
ROUND = {"pie", "doughnut"}
CATEGORIES, VALUES = 1, 2


@dataclass(frozen=True)
class Sheet:
    """A table as a sheet: its document, its id and its grid's key, its sheet's name, the ids
    of its rows and columns in order and the text of its cells that have a node."""

    document: object
    table: str
    grid: int
    name: str
    rows: list[str]
    cols: list[str]
    texts: dict[str, str]


def q(name: str) -> str:
    prefix, _, local = name.partition(":")
    return f"{{{NS[prefix]}}}{local}"


def sub(parent, tag: str, attrs: dict | None = None, text: str | None = None):
    element = etree.SubElement(
        parent, q(tag), {q(k) if ":" in k else k: str(v) for k, v in (attrs or {}).items()}
    )
    if text is not None:
        element.text = text
    return element


def _val(parent, tag: str, value) -> None:
    sub(parent, tag, {"val": value})


def size(across: float) -> tuple[int, int]:
    """A chart's width and height in EMU across a text so many centimetres wide."""
    width = round(across * EMU_PER_CM)
    return width, round(width / ASPECT)


def space(attrs: dict, sheet: Sheet | None, font: str):
    """The chart part of a chart block over its sheet, without series where its cells are
    gone."""
    chart = charts.chart_of(attrs)
    kind = attrs.get("kind") if attrs.get("kind") in GROUPS else "column"
    stacked = kind in STACKING and attrs.get("stacked") is True
    title = attrs.get("title").strip() if isinstance(attrs.get("title"), str) else ""
    found = etree.Element(q("c:chartSpace"), nsmap=NS)
    _val(found, "c:date1904", 0)
    _val(found, "c:roundedCorners", 0)
    body = sub(found, "c:chart")
    if title:
        _title(body, title[:CHART_TITLE_LENGTH])
    else:
        _val(body, "c:autoTitleDeleted", 1)
    plot = sub(body, "c:plotArea")
    sub(plot, "c:layout")
    group = sub(plot, f"c:{GROUPS[kind]}")
    if kind in ("column", "bar"):
        _val(group, "c:barDir", "col" if kind == "column" else "bar")
        _val(group, "c:grouping", "stacked" if stacked else "clustered")
    elif kind in ("line", "area"):
        _val(group, "c:grouping", "stacked" if stacked else "standard")
    elif kind == "scatter":
        _val(group, "c:scatterStyle", "lineMarker")
    _val(group, "c:varyColors", int(kind in ROUND))
    formats = "General"
    if chart is not None and sheet is not None and chart.table == sheet.table:
        formats = _series(group, kind, chart, sheet)
    if kind in ("column", "bar"):
        _val(group, "c:gapWidth", 150)
        if stacked:
            _val(group, "c:overlap", 100)
    elif kind == "line":
        _val(group, "c:marker", 1)
    elif kind in ROUND:
        _val(group, "c:firstSliceAng", 0)
        if kind == "doughnut":
            _val(group, "c:holeSize", 50)
    if kind not in ROUND:
        _val(group, "c:axId", CATEGORIES)
        _val(group, "c:axId", VALUES)
        _axes(plot, kind, formats)
    if attrs.get("legend") is not False:
        legend = sub(body, "c:legend")
        _val(legend, "c:legendPos", "b")
        _val(legend, "c:overlay", 0)
    _val(body, "c:plotVisOnly", 1)
    _val(body, "c:dispBlanksAs", "gap")
    text = sub(found, "c:txPr")
    sub(text, "a:bodyPr")
    sub(text, "a:lstStyle")
    paragraph = sub(text, "a:p")
    run = sub(sub(paragraph, "a:pPr"), "a:defRPr")
    sub(run, "a:latin", {"typeface": fonts.office(font)})
    sub(run, "a:cs", {"typeface": fonts.office(font)})
    sub(paragraph, "a:endParaRPr")
    return found


def linked(found, rid: str) -> None:
    """The chart given the workbook its data is edited in, by its relationship."""
    data = sub(found, "c:externalData", {"r:id": rid})
    _val(data, "c:autoUpdate", 0)


def _title(body, title: str) -> None:
    element = sub(body, "c:title")
    rich = sub(sub(element, "c:tx"), "c:rich")
    sub(rich, "a:bodyPr")
    sub(rich, "a:lstStyle")
    paragraph = sub(rich, "a:p")
    sub(sub(paragraph, "a:pPr"), "a:defRPr", {"b": 1})
    run = sub(paragraph, "a:r")
    sub(run, "a:rPr", {"b": 1})
    sub(run, "a:t", text=title)
    _val(element, "c:overlay", 0)


def _series(group, kind: str, chart: charts.Chart, sheet: Sheet) -> str:
    """The chart's series as the editor reads them out of the range, each where its cells
    are; the number format of the first value, for the value axis."""
    shown = charts.read(sheet.document, chart, {sheet.table}, {sheet.table: sheet.texts})
    if shown is charts.MISSING:
        return "General"
    rows = {id: index for index, id in enumerate(sheet.rows, 1)}
    cols = {id: index for index, id in enumerate(sheet.cols, 1)}
    top, bottom = sorted((rows[chart.top], rows[chart.bottom]))
    left, right = sorted((cols[chart.left], cols[chart.right]))
    series = shown["series"]
    names = bool(series) and series[0]["name"] is not None
    labels = shown["labels"] is not None
    colours = palette.chart()
    first = "General"
    for number, each in enumerate(series):
        if chart.by == "cols":
            line = left + labels + number
            name, values = (top, line), (top + names, line, bottom, line)
            categories = (top + names, left, bottom, left)
        else:
            line = top + labels + number
            name, values = (line, left), (line, left + names, line, right)
            categories = (top, left + names, top, right)
        codes = _formats(sheet, _cells(*values))
        if number == 0 and codes:
            first = codes[0]
        colour = colours[number % len(colours)]
        element = sub(group, "c:ser")
        _val(element, "c:idx", number)
        _val(element, "c:order", number)
        if names:
            _strings(sub(element, "c:tx"), _ref(sheet.name, *name, *name), [each["name"]])
        _look(element, kind, colour)
        if kind in ROUND:
            for point in range(len(each["values"])):
                dot = sub(element, "c:dPt")
                _val(dot, "c:idx", point)
                _val(dot, "c:bubble3D", 0)
                _fill(sub(dot, "c:spPr"), colours[point % len(colours)], edge="FFFFFF")
        if kind == "column" or kind == "bar":
            _val(element, "c:invertIfNegative", 0)
        across = _ref(sheet.name, *categories)
        if kind == "scatter":
            if "x" in shown:
                _numbers(sub(element, "c:xVal"), across, shown["x"], "General")
            elif labels:
                _strings(sub(element, "c:xVal"), across, shown["labels"])
        elif labels:
            _strings(sub(element, "c:cat"), across, shown["labels"])
        tag = "c:yVal" if kind == "scatter" else "c:val"
        _numbers(sub(element, tag), _ref(sheet.name, *values), each["values"], codes)
        if kind in ("line", "scatter"):
            _val(element, "c:smooth", 0)
    return first


def _formats(sheet: Sheet, cells: list[tuple[int, int]]) -> list[str]:
    """The number format of each of the cells given, by row and column from 1."""
    ids = {sheet.rows[row - 1] for row, _ in cells}
    held = dict(GridRow.objects.filter(grid=sheet.grid, row__in=ids).values_list("row", "cells"))
    return [
        (held.get(sheet.rows[row - 1], {}).get(sheet.cols[col - 1]) or {}).get(FORMAT) or "General"
        for row, col in cells
    ]


def _cells(top: int, left: int, bottom: int, right: int) -> list[tuple[int, int]]:
    return [(row, col) for row in range(top, bottom + 1) for col in range(left, right + 1)]


def _ref(sheet: str, top: int, left: int, bottom: int, right: int) -> str:
    start = f"${column_name(left)}${top}"
    end = f"${column_name(right)}${bottom}"
    quoted = sheet.replace("'", "''")
    return f"'{quoted}'!{start}" if (top, left) == (bottom, right) else f"'{quoted}'!{start}:{end}"


def _strings(parent, ref: str, texts: list[str]) -> None:
    found = sub(parent, "c:strRef")
    sub(found, "c:f", text=ref)
    cache = sub(found, "c:strCache")
    _val(cache, "c:ptCount", len(texts))
    for index, text in enumerate(texts):
        if text:
            sub(sub(cache, "c:pt", {"idx": index}), "c:v", text=text)


def _numbers(parent, ref: str, numbers: list[float | None], codes: list[str] | str) -> None:
    codes = codes if isinstance(codes, list) else [codes] * len(numbers)
    general = codes[0] if codes else "General"
    found = sub(parent, "c:numRef")
    sub(found, "c:f", text=ref)
    cache = sub(found, "c:numCache")
    sub(cache, "c:formatCode", text=general)
    _val(cache, "c:ptCount", len(numbers))
    for index, number in enumerate(numbers):
        if number is not None:
            own = codes[index] if index < len(codes) and codes[index] != general else None
            point = sub(cache, "c:pt", {"idx": index, **({"formatCode": own} if own else {})})
            sub(point, "c:v", text=repr(float(number)))


def _fill(shape, colour: str, edge: str | None = None) -> None:
    sub(sub(shape, "a:solidFill"), "a:srgbClr", {"val": colour})
    if edge:
        sub(sub(sub(shape, "a:ln", {"w": 19050}), "a:solidFill"), "a:srgbClr", {"val": edge})


def _look(element, kind: str, colour: str) -> None:
    """A series in its colour: bars and areas filled, a line drawn with its markers, points
    of a scatter without a line between them; a round chart's colours go by its points."""
    if kind in ROUND:
        return
    shape = sub(element, "c:spPr")
    if kind in ("column", "bar", "area"):
        _fill(shape, colour)
        return
    line = sub(shape, "a:ln", {"w": 28575, "cap": "rnd"})
    if kind == "line":
        sub(sub(line, "a:solidFill"), "a:srgbClr", {"val": colour})
        sub(line, "a:round")
    else:
        sub(line, "a:noFill")
    marker = sub(element, "c:marker")
    _val(marker, "c:symbol", "circle")
    _val(marker, "c:size", 5 if kind == "line" else 7)
    _fill(sub(marker, "c:spPr"), colour, edge=colour)


def _axes(plot, kind: str, formats: str) -> None:
    """The axis along the categories, or a scatter's x values, and the one across the
    values, crossing each other at zero."""
    across = "l" if kind == "bar" else "b"
    upright = "b" if kind == "bar" else "l"
    between = "midCat" if kind == "scatter" else "between"
    first = sub(plot, "c:valAx" if kind == "scatter" else "c:catAx")
    _axis(first, CATEGORIES, VALUES, across, "General", grid=False)
    if kind == "scatter":
        _val(first, "c:crossBetween", between)
    else:
        _val(first, "c:auto", 1)
        _val(first, "c:lblAlgn", "ctr")
        _val(first, "c:lblOffset", 100)
        _val(first, "c:noMultiLvlLbl", 0)
    second = sub(plot, "c:valAx")
    _axis(second, VALUES, CATEGORIES, upright, formats, grid=True)
    _val(second, "c:crossBetween", between)


def _axis(axis, own: int, other: int, position: str, formats: str, grid: bool) -> None:
    _val(axis, "c:axId", own)
    _val(sub(axis, "c:scaling"), "c:orientation", "minMax")
    _val(axis, "c:delete", 0)
    _val(axis, "c:axPos", position)
    if grid:
        sub(axis, "c:majorGridlines")
    sub(axis, "c:numFmt", {"formatCode": formats, "sourceLinked": 1})
    _val(axis, "c:majorTickMark", "out")
    _val(axis, "c:minorTickMark", "none")
    _val(axis, "c:tickLblPos", "nextTo")
    _val(axis, "c:crossAx", other)
    _val(axis, "c:crosses", "autoZero")
