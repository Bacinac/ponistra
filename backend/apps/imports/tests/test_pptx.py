import hashlib
import io
from collections import Counter

import pytest
from lxml import etree

from apps.blobs import store
from apps.blobs.tests.test_blobs import content
from apps.content import slides
from apps.content.blocks import Block, Field, Run
from apps.exports.tests.test_charts import over, sales
from apps.exports.tests.test_docx import made, picture
from apps.exports.tests.test_pptx import at, box, measuring, quiet, slide, tab_of
from apps.imports import pptx
from apps.imports.powerpoint import CLR_MAP, NO_STYLE, built_in_id
from apps.jobs.tests.handed import saved

from .powerpoint_files import (
    NS,
    STYLES,
    THEME,
    body,
    frame,
    holder,
    layout,
    para,
    powerpoint_file,
    presentation,
    run,
    tree,
)
from .test_docx import PNG

pytestmark = pytest.mark.django_db

__all__ = ["measuring", "quiet"]


def read(tmp_path, data: bytes):
    path = tmp_path / "file.pptx"
    path.write_bytes(data)
    return pptx.read(path, "hr")


def exported(api, document, tmp_path):
    return read(tmp_path, content(saved(api, "pptx", document=document.pk)))


def shown(block: Block, names: dict[str, str]) -> tuple:
    attrs = {
        key: names[value]
        if key == "layout"
        else [(each["name"], each.get("on")) for each in value]
        if key == "designs"
        else value
        for key, value in block.attrs.items()
        if key not in ("format", "widths")
    }
    text = "".join(run.text if isinstance(run, Run) else f"[{run.kind}]" for run in block.runs)
    return block.type, attrs, text


def contents(imported, by: str = "name") -> list[tuple]:
    names = {layout["id"]: layout[by] for layout in imported.template["layouts"]}
    return [(tab.title, [shown(block, names) for block in tab.blocks]) for tab in imported.tabs]


def texts(table: Block) -> list[tuple]:
    return [(cell.to is not None, [b.runs for b in cell.blocks]) for cell in table.cells]


def test_a_powerpoint_file_comes_as_its_sections_slides_in_their_layouts(tmp_path):
    imported = read(tmp_path, powerpoint_file())
    image = {"blob": hashlib.sha256(PNG).hexdigest(), "alt": "Graf rasta", "width": 24}
    assert contents(imported) == [
        (
            "Uvod",
            [
                ("title", {"layout": "Naslovni slajd"}, "Godišnji izvještaj"),
                ("subtitle", {}, "Zagreb, 2026"),
            ],
        ),
        (
            "Glavno",
            [
                ("heading", {"level": 1, "layout": "Naslov i sadržaj"}, "Prihodi"),
                ("paragraph", {"list": "bullet"}, "Rast je brz i stalan"),
                ("paragraph", {"list": "bullet", "indent": 1.25}, "Izvoz"),
                ("paragraph", {"list": "bullet", "indent": 2.5}, "Znak"),
                ("paragraph", {"list": "number"}, "Treći"),
                ("paragraph", {"list": "number"}, "Četvrti"),
                ("paragraph", {"align": "center"}, "Napomena"),
                ("paragraph", {"list": "bullet"}, "Više"),
                ("image", image, ""),
                ("table", {"designs": [("Medium Style 2 - Accent 1", {"header": True})]}, ""),
                ("paragraph", {}, "Izvor: HNB"),
                ("paragraph", {"speaker": True}, "Govoriti polako"),
                ("paragraph", {"speaker": True}, "Pitanja na kraju"),
                ("heading", {"level": 1, "layout": "Dva sadržaja", "hidden": True}, "Usporedba"),
                ("paragraph", {"list": "bullet"}, "Lijevo"),
                ("columnBreak", {}, ""),
                ("paragraph", {"list": "bullet"}, "Desno"),
                ("heading", {"level": 1, "layout": "Usporedba"}, "Prije i poslije"),
                ("paragraph", {}, "Prije"),
                ("paragraph", {"list": "bullet"}, "Staro"),
                ("columnBreak", {}, ""),
                ("paragraph", {}, "Poslije"),
                ("paragraph", {"list": "bullet"}, "Novo"),
                (
                    "heading",
                    {"level": 1, "layout": "Naslov i sadržaj", "background": {"color": "#ff0000"}},
                    "Ostalo",
                ),
                ("paragraph", {}, "U skupini"),
            ],
        ),
        ("Kraj", [("heading", {"level": 1, "layout": "Bez pozadine"}, "Kraj")]),
    ]
    assert imported.images == {image["blob"]: PNG}
    main = imported.tabs[1].blocks
    assert main[1].runs == [Run("Rast je "), Run("brz", {"strong": {}}), Run(" i stalan")]
    assert main[6].runs == [Run("Napomena", {"size": {"pt": 20.0}})]
    assert main[7].runs == [Run("Više", {"link": {"href": "https://example.com/izvjestaj"}})]
    assert main[10].runs == [Run("Izvor: HNB", {"size": {"pt": 18.0}})]
    assert main[18].runs == [Run("Prije", {"strong": {}, "size": {"pt": 24.0}})]
    table = main[9]
    assert list(table.attrs["widths"].values()) == [50.0, 25.0, 25.0]
    small = {"size": {"pt": 18.0}}
    assert texts(table) == [
        (True, [[Run("Kvartal", small)]]),
        (False, [[Run("Iznos", small)]]),
        (False, [[Run("Q1", small)]]),
        (False, [[Run("siječanj", small)]]),
        (False, [[Run("1.200", small)]]),
    ]

    bullets = imported.formats[main[1].attrs["format"]]
    assert [level["prefix"] for level in bullets[:3]] == ["•", "–", "▪"]
    numbers = imported.formats[main[4].attrs["format"]]
    assert numbers[0] == {"numbering": "1", "prefix": "", "suffix": ")", "nested": False}
    assert imported.theme == {"headings": "Carlito", "text": "Carlito"}
    assert imported.report == {
        "fonts": [{"from": "Calibri Light", "to": "Carlito"}],
        "lost": {
            "animations": 1,
            "diagrams": 1,
            "listNumbers": 2,
            "media": 1,
            "positions": 1,
            "shapes": 1,
            "slideComments": 1,
            "templateShapes": 1,
            "transitions": 1,
        },
    }


def test_its_layouts_come_as_the_template_with_what_the_master_draws_behind_them(tmp_path):
    template = read(tmp_path, powerpoint_file()).template
    assert (template["width"], template["height"]) == (33.867, 19.05)
    layouts = template["layouts"]
    assert all(slides.LAYOUT.is_valid(layout) for layout in layouts)
    assert [(layout["name"], layout["kind"]) for layout in layouts] == [
        ("Naslovni slajd", "title"),
        ("Naslov i sadržaj", "content"),
        ("Dva sadržaja", "two"),
        ("Usporedba", "two"),
        ("Bez pozadine", "titleOnly"),
        ("Neiskorišten", "titleOnly"),
    ]
    white, gray = {"color": "#ffffff"}, {"color": "#e7e6e6"}
    assert [layout.get("background") for layout in layouts] == [white] * 4 + [gray, white]

    plain = {"bold": False, "italic": False}
    behind = [
        {"type": "rect", "x": 0.0, "y": 0.0, "w": 33.867, "h": 0.5, "fill": "#4472c4"},
        {
            "type": "line",
            **{"x": 1.5, "y": 4.5, "w": 30.0, "h": 0.0},
            "line": {"color": "#ed7d31", "width": 2.0},
        },
        {
            "type": "text",
            **{"x": 1.5, "y": 18.5, "w": 10.0, "h": 0.5},
            "content": "Povjerljivo",
            "text": {"size": 18.0, **plain},
        },
    ]
    number = {
        "type": "number",
        **{"x": 24.0, "y": 17.6, "w": 7.0, "h": 1.0},
        "text": {"size": 12.0, "color": "#808080", **plain, "align": "right"},
    }
    footer = {
        "type": "text",
        **{"x": 11.0, "y": 17.6, "w": 11.0, "h": 1.0},
        "text": {"size": 18.0, **plain},
        "content": "Tvrtka d.o.o.",
    }
    assert [layout["shapes"] for layout in layouts] == [
        behind,
        [*behind, number, footer],
        behind,
        behind,
        [],
        [*behind, number],
    ]

    title = {"font": "headings", "size": 44.0, "color": "#1f3864", "bold": True, "italic": False}
    text = {"font": "text", "size": 28.0, "levels": [28.0, 24.0, 20.0, *[18] * 6]}
    text |= {"color": "#000000", **plain, "anchor": "top"}
    heading = {"x": 1.5, "y": 0.8, "w": 30.0, "h": 3.5, "text": {**title, "align": "left"}}
    heading["text"]["anchor"] = "middle"
    first, content, two, compared, *_ = layouts
    assert first["boxes"] == {
        "title": {
            **{"x": 4.2, "y": 3.1, "w": 25.4, "h": 6.6},
            "text": {**title, "size": 60.0, "align": "center", "anchor": "bottom"},
        },
        "subtitle": {
            **{"x": 4.2, "y": 10.0, "w": 25.4, "h": 4.6},
            "text": {"font": "text", "size": 24.0, "color": "#000000", **plain}
            | {"align": "center", "anchor": "top"},
        },
    }
    assert content["boxes"] == {
        "title": heading,
        "body": {"x": 1.5, "y": 4.8, "w": 30.0, "h": 12.0, "text": text},
    }
    assert two["boxes"] == {
        "title": heading,
        "body": {"x": 1.5, "y": 4.8, "w": 14.5, "h": 12.0, "text": text},
        "second": {"x": 17.5, "y": 4.8, "w": 14.5, "h": 12.0, "text": text},
    }
    assert compared["boxes"] == {
        "title": heading,
        "body": {"x": 1.5, "y": 4.8, "w": 14.5, "h": 11.7, "text": text},
        "second": {"x": 17.5, "y": 4.8, "w": 14.5, "h": 11.7, "text": text},
    }
    assert layouts[4]["boxes"] == {"title": heading}


def test_a_file_as_libreoffice_writes_it_finds_its_placeholders_by_type_and_place(tmp_path):
    """LibreOffice gives a slide's subtitle and content placeholders no index, the content side
    by side where it stands, and each slide a transition without an effect and the background
    its layout already has."""
    white = '<p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></p:bgPr></p:bg>'
    left, right = frame(1.5, 4.8, 14.5, 12), frame(17.5, 4.8, 14.5, 12)
    master = tree(
        holder(2, "title", None, frame(1.5, 0.8, 30, 3.5)),
        holder(3, "body", None, frame(1.5, 4.8, 30, 12)),
        background=white,
    )
    layouts = [
        layout(
            tree(holder(2, "title", None), holder(3, "subTitle", None, frame(4, 10, 25, 4))),
            "title",
        ),
        layout(
            tree(
                holder(2, "title", None), holder(3, None, None, left), holder(4, None, None, right)
            ),
            "twoObj",
        ),
    ]
    still = '<p:transition spd="slow"/>'
    slides = [
        {
            "layout": 1,
            "tree": tree(
                holder(2, "title", None, "", body(para(run("Plan")))),
                holder(3, "subTitle", None, "", body(para(run("Listopad")))),
                background=white,
            ),
            "after": still,
        },
        {
            "layout": 2,
            "tree": tree(
                holder(2, "title", None, "", body(para(run("Usporedba")))),
                holder(3, None, None, right, body(para(run("Desno")))),
                holder(4, None, None, left, body(para(run("Lijevo")))),
                background=white,
            ),
            "after": still,
        },
    ]
    imported = read(tmp_path, presentation(master, STYLES, layouts, slides))
    assert contents(imported, "kind") == [
        (
            "",
            [
                ("title", {"layout": "title"}, "Plan"),
                ("subtitle", {}, "Listopad"),
                ("heading", {"level": 1, "layout": "two"}, "Usporedba"),
                ("paragraph", {"list": "bullet"}, "Lijevo"),
                ("columnBreak", {}, ""),
                ("paragraph", {"list": "bullet"}, "Desno"),
            ],
        )
    ]
    assert imported.report["lost"] == {}


def test_our_slides_come_back_from_powerpoint_as_they_went(api, measuring, tmp_path):
    content = [
        Block("title", runs=[Run("Ponuda")]),
        Block("subtitle", runs=[Run("Listopad")]),
        Block("heading", attrs={"level": 1}, runs=[Run("Cijene")]),
        Block("paragraph", attrs={"list": "bullet"}, runs=[Run("Najam")]),
        Block("paragraph", attrs={"list": "number"}, runs=[Run("Prvo")]),
        Block("paragraph", attrs={"list": "number"}, runs=[Run("Drugo")]),
        Block("paragraph", attrs={"speaker": True}, runs=[Run("Spomenuti popust")]),
        Block(
            "heading",
            attrs={"level": 1, "layout": "two", "hidden": True, "background": {"color": "#2f6b6e"}},
            runs=[Run("Dva")],
        ),
        Block("paragraph", runs=[Run("Lijevo")]),
        Block("columnBreak"),
        Block("paragraph", runs=[Run("Desno "), Field("page"), Run(" od "), Field("pages")]),
    ]
    document, tab, _ = made(api, content)
    other = tab_of(
        api, document, "Prilog", [Block("heading", attrs={"level": 1}, runs=[Run("Kraj")])]
    )
    measuring[str(tab.pk)] = [
        slide(0, box("title", [at(0)]), box("subtitle", [at(1)])),
        slide(
            "content",
            box("title", [at(2)]),
            box("body", [at(3), at(4, 6.4), at(5, 7.6)], fit=0.8),
            notes=[6],
        ),
        slide(
            2,
            box("title", [at(7)]),
            box("body", [at(8)]),
            box("second", [at(9, h=0), at(10)], x=17),
            hidden=True,
        ),
    ]
    measuring[str(other.pk)] = [slide(1, box("title", [at(0)]))]
    imported = exported(api, document, tmp_path)

    assert contents(imported, "kind") == [
        (
            "Ponuda",
            [
                ("title", {"layout": "title"}, "Ponuda"),
                ("subtitle", {}, "Listopad"),
                ("heading", {"level": 1, "layout": "content"}, "Cijene"),
                ("paragraph", {"list": "bullet"}, "Najam"),
                ("paragraph", {"list": "number"}, "Prvo"),
                ("paragraph", {"list": "number"}, "Drugo"),
                ("paragraph", {"speaker": True}, "Spomenuti popust"),
                (
                    "heading",
                    {
                        "level": 1,
                        "layout": "two",
                        "background": {"color": "#2f6b6e"},
                        "hidden": True,
                    },
                    "Dva",
                ),
                ("paragraph", {}, "Lijevo"),
                ("columnBreak", {}, ""),
                ("paragraph", {}, "Desno [page] od 4"),
            ],
        ),
        ("Prilog", [("heading", {"level": 1, "layout": "content"}, "Kraj")]),
    ]
    assert imported.report == {"fonts": [], "lost": {}}
    size = slides.BUILT_IN["size"]
    assert (imported.template["width"], imported.template["height"]) == tuple(size.values())
    ours = slides.built_in(*size.values())
    theirs = imported.template["layouts"]
    assert [layout["kind"] for layout in theirs] == [layout["kind"] for layout in ours]
    plain = {"bold": False, "italic": False}
    for mine, back in zip(ours, theirs, strict=True):
        assert back["shapes"] == [
            {**shape, "text": shape["text"] | plain} for shape in mine["shapes"]
        ]
        assert back["boxes"] == {
            role: {**each, "text": each["text"] | plain} for role, each in mine["boxes"].items()
        }


def test_pictures_tables_and_charts_come_back_from_powerpoint(api, measuring, tmp_path):
    blob = store.put(io.BytesIO(picture())).sha256
    table = sales(tmp_path)
    content = [
        Block("heading", attrs={"level": 1}, runs=[Run("Brojke")]),
        Block("paragraph", runs=[Run("Uvod")]),
        Block("image", attrs={"blob": blob, "alt": "Logotip"}),
        Block("paragraph", runs=[Run("Između")]),
        table,
        over(table, "A1", "C3", title="Prihod"),
    ]
    document, tab, _ = made(api, content)
    inside = {"x": 2.582, "w": 28.702}
    measured = [
        at(1, 5.2, 1, **inside),
        at(2, 6.4, 4, 3, 8),
        at(3, 10.6, **inside),
        at(4, 11.8, 2, **inside),
        at(5, 14, 3, **inside),
    ]
    measuring[str(tab.pk)] = [
        slide(1, box("title", [at(0)]), box("body", measured, x=2.328, w=29.21))
    ]
    imported = exported(api, document, tmp_path)
    ((_, blocks),) = contents(imported, "kind")
    assert [(type, text) for type, _, text in blocks] == [
        ("heading", "Brojke"),
        ("paragraph", "Uvod"),
        ("image", ""),
        ("paragraph", "Između"),
        ("table", ""),
        ("table", ""),
        ("chart", ""),
    ]
    image, grid, chart = (imported.tabs[0].blocks[at] for at in (2, 5, 6))
    assert (image.attrs["blob"], image.attrs["alt"]) == (blob, "Logotip")
    assert imported.images == {blob: picture()}
    assert chart.attrs["range"]["table"] == grid.id
    assert (chart.attrs["kind"], chart.attrs["title"]) == ("column", "Prihod")
    assert imported.report["lost"] == {}


def test_powerpoint_draws_its_own_table_styles_with_the_table_s_background_and_shadow_over_them():
    scheme, faces, formats = pptx.themed(etree.fromstring(THEME))
    master = pptx.Master(None, None, scheme, dict(CLR_MAP), faces, {}, formats=formats)
    lost = Counter()
    looks = pptx.Looks(lost)

    def design(inside: str = "", style: str | None = None) -> dict:
        named = f"<a:tableStyleId>{style}</a:tableStyleId>" if style else ""
        return looks.design(etree.fromstring(f"<a:tblPr {NS}>{inside}{named}</a:tblPr>"), master)

    assert (design()["name"], +lost) == ("No Style, Table Grid", {})
    assert design(style="{00000000-1234-4321-ABCD-000000000000}")["name"] == "No Style, Table Grid"
    assert +lost == {"tableStyles": 1}
    red = '<a:solidFill><a:srgbClr val="FF0000"/></a:solidFill>'
    cast = (
        '<a:effectLst><a:outerShdw dist="381000" dir="2700000"><a:srgbClr val="00B050"/>'
        "</a:outerShdw></a:effectLst>"
    )
    themed = built_in_id("Themed Style 2 - Accent 1")
    plain, own = design(style=themed), design(red + cast, themed)
    assert "shadow" not in plain
    assert plain["background"] != own["background"] == design(red, NO_STYLE)["background"]
    assert {key: own["shadow"][key] for key in ("blur", "distance", "angle")} == {
        "blur": 0,
        "distance": 30,
        "angle": 45,
    }
