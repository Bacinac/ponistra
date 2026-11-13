import json
from dataclasses import asdict

from django.conf import settings
from jsonschema import Draft202012Validator

from apps.content import designs
from apps.content.schema import SPEC

CASES = settings.SCHEMA.with_name("tables.cases.json")
SWITCHES = ("header", "totals", "firstColumn", "lastColumn", "rowBands", "columnBands")
ALL = dict.fromkeys(SWITCHES, True)
SIDES = ("top", "bottom", "left", "right")
REGION = (*SIDES, "insideH", "insideV")


def line(kind: str, width: float, color: str | None = None) -> dict:
    return {"line": kind, "width": width, **({"color": color} if color else {})}


WORD = {
    "rules": "word",
    "name": "Grid Table 4 Accent 1",
    "lines": dict.fromkeys(REGION, line("single", 0.5, "#8eaadb")),
    "parts": {
        "header": {
            "fill": "#4472c4",
            "marks": {"strong": {}, "color": {"color": "#ffffff"}},
            "edges": dict.fromkeys(SIDES, line("single", 0.5, "#4472c4")) | {"insideV": "none"},
        },
        "totals": {"marks": {"strong": {}}, "edges": {"top": line("double", 0.5, "#4472c4")}},
        "firstColumn": {"marks": {"strong": {}}},
        "lastColumn": {"marks": {"strong": {}}, "caps": "small"},
        "rowBand1": {"fill": "#d9e2f3"},
        "columnBand1": {"fill": "#d9e2f3", "marks": {"strong": False}},
        "table": {"align": "center", "valign": "center", "edges": {"insideV": line("dotted", 1)}},
        "topRight": {"fill": "none"},
    },
    "bands": {"rows": [1, 1], "columns": [1, 1]},
}
WORD_UNCLAIMED = {
    "rules": "word",
    "lines": {"insideH": line("single", 0.5)},
    "parts": {
        "totals": {"fill": "gray", "edges": {"top": line("thick", 1.5)}},
        "lastColumn": {"marks": {"em": {}}},
        "rowBand2": {"fill": "blue"},
    },
    "bands": {"rows": [2, 1]},
}
WORD_BANDS = {
    "rules": "word",
    "lines": {"insideH": line("single", 1, "#000001"), "insideV": line("single", 1, "#000002")},
    "parts": {
        "rowBand1": {"edges": {"bottom": line("single", 0.5, "#000003")}},
        "columnBand1": {
            "edges": {"right": line("single", 0.5, "#000004"), "insideV": line("thick", 1.5)}
        },
        "bottomLeft": {"fill": "gray"},
    },
    "bands": {"rows": [2, 2], "columns": [3, 3]},
}
EXCEL = {
    "rules": "excel",
    "name": "TableStyleMedium2",
    "parts": {
        "table": {
            "edges": {
                "top": line("single", 0.75, "#8ea9db"),
                "bottom": line("single", 0.75, "#8ea9db"),
                "insideH": line("hair", 0.75, "#8ea9db"),
            }
        },
        "header": {
            "fill": "#4472c4",
            "marks": {"strong": {}, "color": {"color": "#ffffff"}},
            "edges": {"bottom": line("single", 1.5)},
        },
        "totals": {"marks": {"strong": {}}, "edges": {"top": line("double", 2.25, "#4472c4")}},
        "firstColumn": {"marks": {"strong": {}}},
        "lastColumn": {"marks": {"strong": {}}},
        "rowBand1": {
            "fill": "#d9e1f2",
            "edges": {"top": line("dashed", 0.75), "bottom": line("single", 0.75, "red")},
        },
        "columnBand1": {"fill": "#d9e1f2aa"},
        "bottomRight": {"fill": "#ffc000"},
    },
    "bands": {"rows": [2, 1], "columns": [1, 2]},
}
POWERPOINT = {
    "rules": "powerpoint",
    "name": "Medium Style 2 - Accent 1",
    "parts": {
        "table": {
            "fill": "#e9ebf5",
            "marks": {"color": {"color": "#000000"}},
            "edges": dict.fromkeys(REGION, line("single", 1, "#ffffff")),
        },
        "header": {
            "fill": "#4472c4",
            "marks": {"strong": {}, "color": {"color": "#ffffff"}},
            "edges": {"bottom": line("single", 3, "#ffffff")},
        },
        "totals": {
            "fill": "#4472c4",
            "marks": {"strong": {}},
            "edges": {"top": line("single", 3, "#ffffff")},
        },
        "firstColumn": {"fill": "#4472c4", "marks": {"strong": {}}},
        "lastColumn": {"fill": "#4472c4", "marks": {"strong": {}}},
        "rowBand1": {"fill": "#cfd5ea", "edges": {"insideH": "none"}},
        "columnBand1": {"fill": "#cfd5ea"},
    },
    "background": "#ffffff",
}
OWN = {
    (1, 1): {"top": line("single", 2.25, "red"), "left": "none"},
    (2, 2): {"bottom": "none", "right": line("dashed", 1)},
    (0, 0): {"right": line("double", 0.75)},
}


def cases() -> list[dict]:
    found = []

    def case(design: dict, rows: int, cols: int, own: dict | None = None) -> None:
        cells = designs.resolved(design, rows, cols, own)
        found.append(
            {
                "design": design,
                "rows": rows,
                "cols": cols,
                **({"own": {f"{r}:{c}": edges for (r, c), edges in own.items()}} if own else {}),
                "cells": [[asdict(cells[(r, c)]) for c in range(cols)] for r in range(rows)],
            }
        )

    for id in designs.CATALOGUE:
        case(designs.ours(id), 3, 3)
        case({**designs.ours(id), "on": ALL}, 4, 4)
    for design in (WORD, WORD_UNCLAIMED, WORD_BANDS, EXCEL, POWERPOINT):
        case(design, 1, 1)
        case({**design, "on": ALL}, 1, 1)
        case({**design, "on": ALL}, 6, 5)
        case({**design, "on": {"header": True, "rowBands": True, "lastColumn": True}}, 5, 4)
        on = {"totals": True, "firstColumn": True, "columnBands": True}
        case({**design, "on": on}, 5, 4, OWN)
    case({**WORD_BANDS, "bands": {"rows": [1, 1], "columns": [3, 3]}, "on": ALL}, 4, 5)
    case({**WORD, "spacing": 7.2, "on": ALL}, 4, 3)
    case({**WORD, "spacing": 0.75, "on": {"header": True, "rowBands": True}}, 5, 4, OWN)
    return found


LAID_TABLE = {
    "rules": "excel",
    "parts": {
        "table": {
            "edges": {
                "bottom": line("single", 0.75, "#ff0000"),
                "right": line("single", 0.75, "#ff0000"),
            }
        }
    },
}
LAID_OWN = {
    (1, 2): {"left": line("dashed", 1.5)},
    (2, 1): {"right": line("single", 0.75)},
    (2, 2): {"left": line("dashed", 1.5)},
}


TIES = {
    (0, 0): {"right": line("single", 0.75, "#b4c50c")},
    (0, 1): {"left": line("single", 0.75, "#b1a0c7")},
    (1, 0): {"right": line("single", 0.75, "#646464")},
    (1, 1): {"left": line("single", 0.75, "#626468")},
    (2, 0): {"right": line("single", 0.75, "#646464")},
    (2, 1): {"left": line("single", 0.75, "#696264")},
}


def area(top: int, left: int, bottom: int, right: int) -> dict:
    return {"area": {"from": f"r{top}:c{left}", "to": f"r{bottom}:c{right}"}}


def laid_cases() -> list[dict]:
    found = []

    def case(layers: list[dict], rows: int, cols: int, own: dict | None = None) -> None:
        def bounds(design: dict) -> tuple[int, int, int, int]:
            if "area" not in design:
                return 0, 0, rows - 1, cols - 1
            ends = [design["area"][end].split(":") for end in ("from", "to")]
            (top, left), (bottom, right) = ([int(each[1:]) for each in end] for end in ends)
            return top, left, bottom, right

        cells = designs.laid([(each, bounds(each)) for each in layers], rows, cols, own)
        found.append(
            {
                "designs": layers,
                "rows": rows,
                "cols": cols,
                **({"own": {f"{r}:{c}": edges for (r, c), edges in own.items()}} if own else {}),
                "cells": [[asdict(cells[(r, c)]) for c in range(cols)] for r in range(rows)],
            }
        )

    case([{"rules": "excel"}, LAID_TABLE | area(0, 0, 1, 1)], 3, 3, LAID_OWN)
    case([LAID_TABLE | area(0, 0, 1, 1)], 3, 3, LAID_OWN)
    case([], 3, 3, LAID_OWN)
    on = {"on": ALL}
    case([{"rules": "excel"}, EXCEL | on | area(0, 0, 3, 1), EXCEL | area(1, 2, 4, 4)], 6, 5, OWN)
    case([{**WORD, "spacing": 7.2, "on": ALL}], 4, 3, OWN)
    case([{"rules": "excel"}], 3, 2, TIES)
    case([], 3, 2, TIES)
    return found


def written() -> str:
    """The cases as tables.cases.json holds them for the editor's resolver to be checked against:
    `manage.py shell -v 0 -c "$CASES"`, CASES being
    `from apps.content.tests.test_designs import written; print(written())`."""

    def lines(found: list[dict]) -> str:
        return ",\n".join(
            json.dumps(each, separators=(",", ":"), ensure_ascii=False) for each in found
        )

    return '{"cases": [\n' + lines(cases()) + '\n],\n"laid": [\n' + lines(laid_cases()) + "\n]}"


def test_the_cases_the_editor_s_resolver_is_checked_against_are_this_resolver_s():
    assert CASES.read_text() == written() + "\n"


def test_the_cases_designs_and_edges_are_as_the_schema_takes_them():
    design = Draft202012Validator({"$defs": SPEC["$defs"], "$ref": "#/$defs/design"})
    edges = Draft202012Validator({"$defs": SPEC["$defs"], "$ref": "#/$defs/edges"})
    for each in cases() + laid_cases():
        for one in each.get("designs", [each.get("design")]):
            design.validate(one)
        for own in each.get("own", {}).values():
            edges.validate(own)


def test_word_gives_a_lone_row_to_the_header_and_bands_the_rows_after_it():
    alone = designs.resolved({**WORD, "on": ALL}, 1, 1)[(0, 0)]
    assert alone.parts == ["table", "firstColumn", "header", "topLeft"]
    banded = designs.resolved({**WORD, "on": {"header": True, "rowBands": True}}, 4, 1)
    assert [banded[(row, 0)].fill for row in range(4)] == ["#4472c4", "#d9e2f3", None, "#d9e2f3"]


def test_word_lets_a_part_it_does_not_define_yield_to_one_it_does():
    alone = designs.resolved({**WORD_UNCLAIMED, "on": ALL}, 1, 1)[(0, 0)]
    assert alone.parts == [
        "table",
        "lastColumn",
        "firstColumn",
        "header",
        "totals",
        "topLeft",
        "topRight",
        "bottomLeft",
        "bottomRight",
    ]
    assert alone.fill == "gray"


def test_word_claims_a_row_or_column_where_its_part_or_a_corner_it_reaches_is_defined():
    on = {"totals": True, "lastColumn": True, "rowBands": True, "columnBands": True}
    plain = designs.resolved({**WORD_BANDS, "on": on}, 3, 4)
    assert plain[(2, 3)].parts == [
        "table",
        "rowBand2",
        "columnBand2",
        "lastColumn",
        "totals",
        "bottomRight",
    ]
    cornered = designs.resolved({**WORD_BANDS, "on": {**on, "firstColumn": True}}, 3, 4)
    assert cornered[(2, 0)].parts == ["table", "firstColumn", "totals", "bottomLeft"]
    assert cornered[(1, 1)].parts == ["table", "rowBand1", "columnBand1"]


def test_word_ends_a_band_the_table_cuts_short_with_its_inside_line():
    on = {"rowBands": True, "columnBands": True}
    whole = designs.resolved({**WORD_BANDS, "spacing": 1, "on": on}, 4, 3)
    assert whole[(1, 0)].edges["bottom"] == line("single", 0.5, "#000003")
    assert whole[(0, 2)].edges["right"] == line("single", 0.5, "#000004")
    cut = designs.resolved({**WORD_BANDS, "spacing": 1, "on": on}, 3, 2)
    assert cut[(2, 0)].edges["bottom"] == line("single", 1, "#000001")
    assert cut[(0, 1)].edges["right"] == line("thick", 1.5)


def test_word_draws_a_column_band_s_inside_lines_only_with_row_bands_of_two_rows_or_more():
    on = {"rowBands": True, "columnBands": True}
    for rows, drawn in (([2, 2], line("thick", 1.5)), ([1, 1], line("single", 1, "#000002"))):
        cells = designs.resolved(
            {**WORD_BANDS, "bands": {"rows": rows, "columns": [3, 3]}, "on": on}, 2, 3
        )
        assert cells[(0, 0)].edges["right"] == cells[(0, 1)].edges["left"] == drawn


def test_a_shared_edge_goes_to_the_heavier_line_but_in_powerpoint_to_the_later_part():
    word = designs.resolved({**WORD, "on": {"header": True}}, 2, 1)
    assert (
        word[(0, 0)].edges["bottom"] == word[(1, 0)].edges["top"] == line("single", 0.5, "#4472c4")
    )
    excel = designs.resolved({**EXCEL, "on": {"header": True}}, 2, 1)
    assert excel[(0, 0)].edges["bottom"] == excel[(1, 0)].edges["top"] == line("single", 1.5)
    powerpoint = designs.resolved({**POWERPOINT, "on": {"header": True}}, 2, 1)
    assert powerpoint[(0, 0)].edges["bottom"] == line("single", 3, "#ffffff")


def test_a_cell_s_own_edge_wins_unless_powerpoint_keeps_it_on_the_upper_left_cell():
    own = {(1, 1): {"top": line("single", 2.25, "red"), "left": "none"}}
    word = designs.resolved(WORD, 2, 2, own)
    assert word[(1, 1)].edges["top"] == word[(0, 1)].edges["bottom"] == line("single", 2.25, "red")
    assert word[(1, 1)].edges["left"] == word[(1, 0)].edges["right"] is not None
    powerpoint = designs.resolved(POWERPOINT, 2, 2, own)
    assert powerpoint[(1, 1)].edges["top"] == line("single", 1, "#ffffff")


def test_an_edge_between_designs_or_beside_a_cell_under_none_meets_by_the_table_s_first_rules():
    red, thin, dashed = line("single", 0.75, "#ff0000"), line("single", 0.75), line("dashed", 1.5)
    layers = [({"rules": "excel"}, (0, 0, 2, 2)), (LAID_TABLE, (0, 0, 1, 1))]
    sheet = designs.laid(layers, 3, 3, LAID_OWN)
    assert sheet[(1, 0)].edges["bottom"] == sheet[(2, 0)].edges["top"] == red
    assert sheet[(1, 1)].edges["right"] == sheet[(1, 2)].edges["left"] == dashed
    assert sheet[(2, 1)].edges["right"] == sheet[(2, 2)].edges["left"] == dashed
    bare = designs.laid([], 3, 3, LAID_OWN)
    assert bare[(2, 1)].edges["right"] == bare[(2, 2)].edges["left"] == thin


def test_two_lines_of_one_kind_meet_by_the_darker_colour_as_each_program_weighs_it():
    def met(layers: list) -> list[str]:
        cells = designs.laid([(each, (0, 0, 2, 1)) for each in layers], 3, 2, TIES)
        return [cells[(r, 0)].edges["right"]["color"] for r in range(3)]

    assert met([{"rules": "excel"}]) == ["#b1a0c7", "#626468", "#696264"]
    assert met([]) == ["#b4c50c", "#646464", "#646464"]
