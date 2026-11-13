"""Charts as Excel and Word keep them (DrawingML), read into ours: the kind, whether its
series stack, its title and legend, and the cells each series takes its name, categories and
values from, with the values the file last showed. Where those cells lie in a sheet decides
the range our chart is drawn over; what a chart of ours cannot keep is told apart, never
guessed at."""

import re
from dataclasses import dataclass, field

from apps.content.blocks import Block
from apps.content.formulas import column_number
from apps.content.schema import CHART_TITLE_LENGTH

C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
KINDS = {
    "barChart": "column",
    "bar3DChart": "column",
    "lineChart": "line",
    "line3DChart": "line",
    "areaChart": "area",
    "area3DChart": "area",
    "pieChart": "pie",
    "pie3DChart": "pie",
    "doughnutChart": "doughnut",
    "scatterChart": "scatter",
}
UNSUPPORTED = {
    "ofPieChart",
    "bubbleChart",
    "radarChart",
    "stockChart",
    "surfaceChart",
    "surface3DChart",
}
AXES = {"catAx", "valAx", "dateAx", "serAx"}
SERIES_REF = re.compile(
    r"(?:'((?:[^']|'')+)'|([^'!]+))!\$?([A-Za-z]{1,3})\$?(\d+)(?::\$?([A-Za-z]{1,3})\$?(\d+))?"
)


@dataclass(frozen=True)
class Area:
    """A rectangle of one sheet, its rows and columns counted from 1."""

    sheet: str
    top: int
    left: int
    bottom: int
    right: int

    def turned(self) -> Area:
        return Area(self.sheet, self.left, self.top, self.right, self.bottom)


@dataclass
class Series:
    """Where a series' name, categories (or x values) and values are, and what they last
    showed."""

    name: Area | None = None
    labels: Area | None = None
    values: Area | None = None
    shown_name: str | None = None
    shown_labels: list[str] = field(default_factory=list)
    shown_values: list[float | None] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)


@dataclass
class Found:
    """A chart as read: its kind ours, or None where we have no such kind, and whether it
    holds what ours cannot keep."""

    kind: str | None
    stacked: bool = False
    title: str | None = None
    legend: bool = False
    series: list[Series] = field(default_factory=list)
    details: bool = False


@dataclass(frozen=True)
class Layout:
    """The range a chart is drawn over, as rows and columns of its sheet, and how our chart
    reads it; `neat` where it reads the same series the file's chart had."""

    box: Area
    by: str
    names: bool
    labels: bool
    neat: bool = True


def parse(root) -> Found | None:
    """The chart of a chart part, None where the part holds none."""
    plot = root.find(f"{C}chart/{C}plotArea")
    if plot is None:
        return None
    groups = [child for child in plot if _local(child.tag) in KINDS.keys() | UNSUPPORTED]
    group = next((each for each in groups if _local(each.tag) in KINDS), None)
    if group is None:
        return Found(None)
    local = _local(group.tag)
    kind = KINDS[local]
    if kind == "column" and _value(group.find(f"{C}barDir")) == "bar":
        kind = "bar"
    grouping = _value(group.find(f"{C}grouping"))
    axes = sum(1 for child in plot if _local(child.tag) in AXES)
    found = Found(
        kind,
        stacked=grouping in ("stacked", "percentStacked"),
        legend=root.find(f"{C}chart/{C}legend") is not None,
        details=len(groups) > 1 or grouping == "percentStacked" or "3D" in local or axes > 2,
    )
    ordered = sorted(group.findall(f"{C}ser"), key=lambda ser: _number(ser.find(f"{C}order")))
    for ser in ordered:
        series = _series(ser, scatter=kind == "scatter")
        found.details |= series.name is None and series.shown_name is not None
        found.series.append(series)
    found.title = _title(root.find(f"{C}chart"), found.series)
    return found


def _series(ser, scatter: bool) -> Series:
    series = Series()
    tx = ser.find(f"{C}tx")
    if tx is not None:
        if (ref := tx.find(f"{C}strRef")) is not None:
            series.name = _area(ref.findtext(f"{C}f"))
            shown = _cached(ref.find(f"{C}strCache"))
            series.shown_name = shown[0] if shown else None
        else:
            series.shown_name = tx.findtext(f"{C}v")
    labels = ser.find(f"{C}xVal" if scatter else f"{C}cat")
    if labels is not None:
        for tag in ("strRef", "numRef", "multiLvlStrRef"):
            if (ref := labels.find(f"{C}{tag}")) is not None:
                series.labels = _area(ref.findtext(f"{C}f"))
                cache = ref.find(f"{C}strCache")
                if cache is None:
                    cache = ref.find(f"{C}numCache")
                series.shown_labels = [each or "" for each in _cached(cache)]
                break
    values = ser.find(f"{C}yVal" if scatter else f"{C}val")
    ref = values.find(f"{C}numRef") if values is not None else None
    if ref is not None:
        series.values = _area(ref.findtext(f"{C}f"))
        cache = ref.find(f"{C}numCache")
        series.shown_values = [_float(each) for each in _cached(cache)]
        series.formats = _formats(cache, len(series.shown_values))
    return series


def _title(chart, series: list[Series]) -> str | None:
    """The chart's own title, or, set to show one without text, Excel's: the name of its only
    series."""
    if chart is None or (title := chart.find(f"{C}title")) is None:
        return None
    tx = title.find(f"{C}tx")
    if tx is None:
        text = series[0].shown_name if len(series) == 1 else None
    elif (rich := tx.find(f"{C}rich")) is not None:
        lines = ["".join(t.text or "" for t in p.iter(f"{A}t")) for p in rich.iter(f"{A}p")]
        text = " ".join(line.strip() for line in lines if line.strip())
    else:
        shown = _cached(tx.find(f"{C}strRef/{C}strCache"))
        text = shown[0] if shown else None
    return (text or "").strip()[:CHART_TITLE_LENGTH] or None


def _cached(cache) -> list[str | None]:
    if cache is None:
        return []
    count = _number(cache.find(f"{C}ptCount"))
    points: dict[int, str] = {}
    for pt in cache.findall(f"{C}pt"):
        index = int(pt.get("idx") or 0)
        if 0 <= index < 100_000:
            points[index] = pt.findtext(f"{C}v") or ""
    size = max(count, max(points, default=-1) + 1)
    return [points.get(index) for index in range(size)]


def _formats(cache, size: int) -> list[str]:
    if cache is None:
        return []
    general = cache.findtext(f"{C}formatCode") or "General"
    own = {int(pt.get("idx") or 0): pt.get("formatCode") for pt in cache.findall(f"{C}pt")}
    return [own.get(index) or general for index in range(size)]


def _area(formula: str | None) -> Area | None:
    found = SERIES_REF.fullmatch((formula or "").strip().strip("()"))
    if not found:
        return None
    sheet = found[2] or found[1].replace("''", "'")
    left = column_number(found[3])
    top = int(found[4])
    right = column_number(found[5]) if found[5] else left
    bottom = int(found[6]) if found[6] else top
    return Area(
        sheet.strip(), min(top, bottom), min(left, right), max(top, bottom), max(left, right)
    )


def layout(series: list[Series]) -> Layout | None:
    """The range over the cells the series refer to, in one sheet, and how it reads: series
    down the columns or along the rows as their values run, the first line naming them and
    the first line across giving the categories where the series take theirs from there."""
    values = [each.values for each in series]
    if not series or None in values:
        return None
    areas = [area for each in series for area in (each.name, each.labels, each.values) if area]
    if len({area.sheet.casefold() for area in areas}) != 1:
        return None
    by = _way(values)
    if by is None:
        return None

    def turn(area: Area) -> Area:
        return area if by == "cols" else area.turned()

    turned = [turn(area) for area in areas]
    box = Area(
        areas[0].sheet,
        min(area.top for area in turned),
        min(area.left for area in turned),
        max(area.bottom for area in turned),
        max(area.right for area in turned),
    )
    names = any(each.name for each in series)
    labels = any(each.labels for each in series)
    first, top = box.left + labels, box.top + names

    def at(area: Area | None, top: int, left: int, bottom: int, right: int) -> bool:
        if area is None:
            return False
        area = turn(area)
        return (area.top, area.left, area.bottom, area.right) == (top, left, bottom, right)

    neat = len(series) == box.right - first + 1 and all(
        at(each.values, top, col, box.bottom, col)
        and (not names or at(each.name, box.top, col, box.top, col))
        and (not labels or at(each.labels, top, box.left, box.bottom, box.left))
        for col, each in zip(range(first, box.right + 1), series, strict=False)
    )
    return Layout(box if by == "cols" else box.turned(), by, names, labels, neat)


def _way(values: list[Area]) -> str | None:
    tall = all(area.left == area.right for area in values)
    wide = all(area.top == area.bottom for area in values)
    if tall and wide:
        return "rows" if len(values) > 1 and len({area.left for area in values}) == 1 else "cols"
    return "cols" if tall else "rows" if wide else None


def chart(found: Found, layout: Layout, over: dict) -> Block:
    return Block(
        "chart",
        attrs={
            "range": over,
            "kind": found.kind,
            "stacked": found.stacked,
            "by": layout.by,
            "names": layout.names,
            "labels": layout.labels,
            "title": found.title,
            "legend": found.legend,
        },
    )


def _local(tag) -> str:
    return tag.rpartition("}")[2] if isinstance(tag, str) else ""


def _value(element) -> str | None:
    return element.get("val") if element is not None else None


def _number(element) -> int:
    try:
        return int(_value(element) or 0)
    except ValueError:
        return 0


def _float(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "") else None
    except ValueError:
        return None
