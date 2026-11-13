import io
import re
import zipfile
from dataclasses import asdict
from datetime import datetime, time

import icu
import pikepdf
import pytest
from django.utils import timezone
from lxml import etree
from PIL import ExifTags, Image
from pycrdt import Map

from apps.access.tests.test_access import create
from apps.blobs import store
from apps.blobs.tests.office import with_macros
from apps.blobs.tests.test_blobs import content
from apps.collab import server
from apps.collab.models import Update
from apps.comments.models import Comment, Thread
from apps.content import blocks, styles
from apps.content.blocks import Block, Cell, Field, Grid, Note, Run
from apps.content.tests.helpers import fill
from apps.documents import printing
from apps.documents.models import Node
from apps.exports import docx
from apps.exports.xlsx import doc_of
from apps.imports import docx as reader
from apps.imports.tests.test_docx import (
    ANA,
    DATE,
    HEADINGS,
    LISTS,
    PNG,
    STYLES,
    TOC,
    field,
    named,
    run,
    section,
)
from apps.imports.tests.test_views import bring
from apps.imports.tests.word_files import numbered, p, theme, word_file
from apps.imports.word import WP, R, W
from apps.jobs.tests import handed
from apps.jobs.tests.handed import refused
from apps.search.tests.test_search import pdf_bytes

pytestmark = pytest.mark.django_db

MEDIA_TYPES = {"docx": store.DOCX, "docm": store.DOCM}


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(server, "announce", lambda room, news: None)


def picture(format: str = "PNG", size=(40, 20), **saved) -> bytes:
    found = io.BytesIO()
    Image.new("RGB", size, "teal").save(found, format, **saved)
    return found.getvalue()


def saved(api, node: str, format: str = "docx") -> bytes:
    response = handed.saved(api, format, document=node)
    assert response["Content-Type"] == MEDIA_TYPES[format]
    return content(response)


def read(tmp_path, data: bytes, name: str = "file.docx"):
    path = tmp_path / name
    path.write_bytes(data)
    return reader.read(path, "hr")


def renumbered(value, ids: dict):
    """The value with each proposal's id the order in which its proposal first appears."""
    if isinstance(value, dict):
        if "author" in value and set(value) <= {"id", "author", "user", "date", "before"}:
            value = {**value, "id": ids.setdefault(value["id"], len(ids))}
        return {key: renumbered(each, ids) for key, each in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(renumbered(each, ids) for each in value)
    return value


def shape(found) -> dict:
    """What a file comes in as, by the places of its blocks, rows and columns and the order of
    its proposals rather than their ids."""
    places = {}
    formats = {id: at for at, id in enumerate(found.formats)}

    def runs(each) -> list:
        return [
            (run.kind, [asdict(inner) for inner in run.runs])
            if isinstance(run, Note)
            else asdict(run)
            for run in each.runs
        ]

    def table(block, attrs: dict) -> tuple:
        grid = block.grid
        rows = {id: y for y, id in enumerate(grid.rows)}
        cols = {id: x for x, id in enumerate(grid.cols)}

        def at(key: str) -> tuple[int, int]:
            row, _, col = key.partition(":")
            return rows[row], cols[col]

        attrs["widths"] = {cols[col]: width for col, width in attrs.get("widths", {}).items()}
        attrs["heights"] = {rows[row]: height for row, height in attrs.get("heights", {}).items()}
        if "proposedRows" in attrs:
            attrs["proposedRows"] = {rows[row]: each for row, each in attrs["proposedRows"].items()}
        if "frozen" in attrs:
            attrs["frozen"] = rows[attrs["frozen"]]
        sheet = {
            name: {at(key): each for key, each in getattr(grid, name).items()}
            for name in ("formulas", "formats", "values")
        }
        cells = [
            (rows[cell.row], cols[cell.col], cell.to and at(cell.to), blocks(cell.blocks))
            for cell in block.cells
        ]
        return block.type, attrs, sheet, cells

    def blocks(content) -> list:
        shown = []
        for block in content:
            places[block.id] = len(places)
            attrs = {**block.attrs}
            if "format" in attrs:
                attrs["format"] = formats[attrs["format"]]
            if block.type == "table":
                shown.append(table(block, attrs))
            else:
                shown.append((block.type, attrs, runs(block)))
        return shown

    def parts(found: dict | None) -> dict | None:
        return found and {name: blocks(content) for name, content in found.items()}

    tabs = [
        (
            tab.title,
            blocks(tab.blocks),
            tab.page,
            parts(tab.parts),
            {places[id]: (page, parts(named)) for id, (page, named) in tab.sections.items()},
        )
        for tab in found.tabs
    ]
    threads = [
        (
            [asdict(remark) for remark in thread.remarks],
            thread.resolved,
            thread.start and (places[thread.start[0]], thread.start[1]),
            thread.end and (places[thread.end[0]], thread.end[1]),
            thread.quote,
        )
        for thread in found.threads
    ]
    shown = {
        "tabs": tabs,
        "page": found.page,
        "parts": parts(found.parts),
        "theme": found.theme,
        "styles": found.styles,
        "images": found.images,
        "threads": threads,
        "formats": list(found.formats.values()),
        "lost": found.report["lost"],
    }
    return renumbered(shown, {})


COMMENTS = (
    '<w:comment w:id="0" w:author="Marko Marić" w:date="2026-03-02T10:15:00Z">'
    '<w:p w14:paraId="1A000001"><w:r><w:t>Provjeriti iznos.</w:t></w:r></w:p></w:comment>'
    '<w:comment w:id="1" w:author="Iva Ivić" w:date="2026-03-03T08:00:00Z">'
    '<w:p w14:paraId="1A000002"><w:r><w:t>Provjereno.</w:t></w:r></w:p></w:comment>'
)
EXTENDED = (
    '<w15:commentEx w15:paraId="1A000001" w15:done="1"/>'
    '<w15:commentEx w15:paraId="1A000002" w15:paraIdParent="1A000001" w15:done="0"/>'
)
FOOTNOTES = (
    '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p>'
    '</w:footnote><w:footnote w:id="1"><w:p><w:r><w:footnoteRef/></w:r>'
    + run(" Izvor: ")
    + run("Narodne novine", "<w:i/>")
    + "</w:p></w:footnote>"
)
ENDNOTES = f'<w:endnote w:id="1"><w:p>{run("Kraj")}</w:p></w:endnote>'


def drawing(rid: str, cx: int) -> str:
    return (
        f'<w:r><w:drawing><wp:inline><wp:extent cx="{cx}" cy="100"/>'
        '<wp:docPr id="1" name="Slika" descr="Logotip"/><a:graphic>'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:pic><pic:blipFill><a:blip r:embed="{rid}"/></pic:blipFill></pic:pic>'
        "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
    )


def cell(content: str, props: str = "") -> str:
    return f"<w:tc><w:tcPr>{props}</w:tcPr>{content}</w:tc>"


TABLE = (
    '<w:tbl><w:tblGrid><w:gridCol w:w="3000"/><w:gridCol w:w="6070"/></w:tblGrid>'
    '<w:tr><w:trPr><w:trHeight w:val="600"/><w:tblHeader/></w:trPr>'
    + cell(p("Stavka"))
    + cell(p("Iznos"))
    + "</w:tr><w:tr>"
    + cell(p("Spojeno"), '<w:gridSpan w:val="2"/>')
    + "</w:tr></w:tbl>"
)


def rich(tmp_path) -> bytes:
    marked = (
        "<w:p>"
        + run("Cijena je ")
        + '<w:commentRangeStart w:id="0"/>'
        + run("100 €", "<w:b/>")
        + '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r>'
        + run(" uz ")
        + run("PDV", '<w:i/><w:color w:val="C00000"/><w:sz w:val="28"/>')
        + run(" podrezano", '<w:kern w:val="2"/>')
        + '<w:r><w:footnoteReference w:id="1"/></w:r>'
        + '<w:hyperlink r:id="rId20">'
        + run("izvor", '<w:rStyle w:val="Hyperlink"/>')
        + "</w:hyperlink>"
        + '<w:r><w:endnoteReference w:id="1"/></w:r>'
        + "</w:p>"
    )
    header = f"<w:p>{run('Stranica ')}{field(' PAGE ', '3')}{run(' od ')}"
    header += f"{field(' NUMPAGES ', '9')}</w:p>"
    first = named("header", "first", "header2")
    stops = '<w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9070"/></w:tabs>'
    body = (
        p("Sadržaj", "TOCHeading")
        + TOC
        + p("Ugovor", "Heading1")
        + marked
        + p("Citat", "Quote1")
        + numbered("Prvi", 3)
        + numbered("Podstavka", 3, 1)
        + p("Između")
        + p(props='<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1"/></w:pBdr>')
        + numbered("Drugi", 3)
        + numbered("Točka", 2)
        + numbered("Opet prvi", 4)
        + numbered("Slovo", 5)
        + p("Predmet", "Heading2")
        + TABLE
        + f'<w:p><w:pPr><w:jc w:val="center"/></w:pPr>{drawing("rId10", 2880000)}</w:p>'
        + p("Uvučeno", props='<w:ind w:left="567" w:hanging="283"/>')
        + p("Točkice", props=stops)
        + f"<w:p><w:pPr>{section(named('header', 'default', 'header') + first, first=True)}"
        + f"</w:pPr>{run('Kraj prvog dijela')}</w:p>"
        + p("Prilog", "Heading1")
        + p("Tablica")
    )
    return word_file(
        body,
        media={"rId10": ("image1.png", picture())},
        links={"rId20": "https://example.com/izvor"},
        section=section(named("footer", "default", "footer"), landscape=True),
        styles=STYLES,
        numbering=HEADINGS + LISTS,
        theme=theme("Georgia", "Arial"),
        comments=COMMENTS,
        extended=EXTENDED,
        footnotes=FOOTNOTES,
        endnotes=ENDNOTES,
        header=header,
        header2=f"<w:p>{run('Naslovnica')}</w:p>",
        footer=f"<w:p>{field('PAGE', None)}</w:p>",
    )


def test_a_word_file_goes_back_to_word_as_it_came_in(api, tmp_path):
    original = rich(tmp_path)
    node = bring(api, original, title="Ugovor")["id"]
    before = read(tmp_path, original, "before.docx")
    exported = saved(api, node)
    after = read(tmp_path, exported, "after.docx")
    assert shape(after) == shape(before)
    styled = etree.fromstring(parts_of(exported)["word/styles.xml"])
    assert {each.get(w("ascii")) for each in styled.iter(w("rFonts"))} == {"Arial", "Georgia"}


def tracked(tag: str, id: int, content: str = "", who: str = ANA) -> str:
    return f'<w:{tag} w:id="{id}" {who}>{content}</w:{tag}>'


def gone(text: str) -> str:
    return f'<w:r><w:delText xml:space="preserve">{text}</w:delText></w:r>'


def ended(change: str, content: str, props: str = "") -> str:
    return f"<w:p><w:pPr>{props}<w:rPr>{change}</w:rPr></w:pPr>{content}</w:p>"


def restyled(id: int, props: str, before: str, text: str) -> str:
    change = tracked("pPrChange", id, f"<w:pPr>{before}</w:pPr>")
    return f"<w:p><w:pPr>{props}{change}</w:pPr>{run(text)}</w:p>"


def test_proposals_go_back_to_word_as_its_tracked_changes(api, tmp_path):
    ivo = 'w:author="Ivo" w:date="2026-10-18T09:30:00Z"'
    italic = tracked("rPrChange", 3, "<w:rPr><w:i/></w:rPr>")
    old = cell(f"<w:p>{run('Stari')}</w:p>")
    added = cell(f"<w:p>{tracked('ins', 21, run('Novi'))}</w:p>")
    body = (
        f"<w:p>{run('Rok je ')}{tracked('del', 1, gone('30'))}"
        f"{tracked('ins', 2, run('15', '<w:b/>' + italic))}{run(' dana')}"
        f"{tracked('ins', 4, tracked('del', 5, gone(' točno'), ivo), ivo)}</w:p>"
        + ended(tracked("ins", 7), tracked("ins", 8, run("Novi stavak")))
        + ended(tracked("del", 9, who=ivo), run("Spojeno"))
        + restyled(10, '<w:pStyle w:val="Quote1"/>', '<w:jc w:val="right"/>', "Citat")
        + restyled(11, "", '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr>', "Bilo")
        + restyled(12, "", '<w:numPr><w:ilvl w:val="1"/><w:numId w:val="3"/></w:numPr>', "Dva")
        + '<w:tbl><w:tblGrid><w:gridCol w:w="9000"/></w:tblGrid>'
        f"<w:tr>{old}</w:tr><w:tr><w:trPr>{tracked('ins', 20)}</w:trPr>{added}</w:tr>"
        f"<w:tr><w:trPr>{tracked('del', 22, who=ivo)}</w:trPr>{old}</w:tr></w:tbl>"
        f"<w:p>{run('Prije')}"
        + tracked(
            "ins",
            30,
            f'{drawing("rId10", 952500)}<w:r><w:br w:type="page"/></w:r>'
            f'<w:r><w:footnoteReference w:id="1"/></w:r>{run("Poslije")}',
            'w:author="Iva"',
        )
        + "</w:p>"
    )
    original = word_file(
        body,
        styles=STYLES,
        numbering=LISTS,
        media={"rId10": ("image1.png", picture())},
        footnotes=f'<w:footnote w:id="1"><w:p>{run("Izvor")}</w:p></w:footnote>',
    )
    node = bring(api, original, title="Ugovor")["id"]
    before = read(tmp_path, original, "before.docx")
    exported = saved(api, node)
    after = read(tmp_path, exported, "after.docx")
    assert shape(after) == shape(before)
    proposals = set(re.findall(r"'id': (\d+), 'author'", repr(shape(before))))
    assert len(proposals) == 10 and before.report["accepted"] == 0
    [tab] = after.tabs
    formerly = {
        block.text: block.attrs["formatting"]["before"]["attrs"]
        for block in tab.blocks
        if "formatting" in block.attrs
    }
    assert formerly["Citat"] == {"align": "right"}
    assert formerly["Bilo"]["list"] == "bullet" and formerly["Dva"]["list"] == "number"
    assert formerly["Dva"]["indent"] > formerly["Bilo"].get("indent", 0)
    document = etree.fromstring(parts_of(exported)["word/document.xml"])
    deleted = document.findall(f".//{w('del')}//{w('delText')}")
    assert [each.text for each in deleted] == ["30", " točno"]
    assert not document.findall(f".//{w('del')}//{w('t')}")
    assert len(document.findall(f".//{w('pPrChange')}")) == 3
    assert {each.get(w("date")) for each in document.iter(w("ins"))} >= {DATE, None}


def test_a_proposed_field_and_table_of_contents_go_as_word_tracks_them(api):
    change = {"id": "p", "author": "Ana Horvat", "user": None, "date": DATE}
    content = [
        Block("contents", attrs={"depth": 1, "insertion": change}),
        Block("heading", attrs={"level": 1}, runs=[Run("Uvod")]),
        Block("paragraph", runs=[Run("Stranica "), Field("page", {"deletion": change})]),
    ]
    document, _, _ = made(api, content)
    contents, _, line = paragraphs(parts_of(saved(api, str(document.pk))))
    [inserted] = contents.findall(w("ins"))
    assert contents.find(f"{w('pPr')}/{w('rPr')}/{w('ins')}").get(w("author")) == "Ana Horvat"
    assert inserted.get(w("date")) == DATE
    assert [each.text for each in inserted.iter(w("instrText"))] == [' TOC \\o "1-1" \\h \\z \\u ']
    assert text_of(contents) == "Uvod"
    [deleted] = line.findall(w("del"))
    assert [each.text for each in deleted.iter(w("delInstrText"))] == [" PAGE "]
    assert not line.findall(f".//{w('instrText')}")


def test_what_only_slides_have_stays_out_of_word(api):
    content = [
        Block("heading", attrs={"level": 1, "layout": "two", "hidden": True}, runs=[Run("Cijene")]),
        Block("paragraph", runs=[Run("Najam")]),
        Block("paragraph", attrs={"speaker": True}, runs=[Run("Spomenuti popust")]),
        Block("columnBreak"),
        Block("paragraph", runs=[Run("Prodaja")]),
        Block("slideBreak"),
        Block("paragraph", runs=[Run("Kontakt")]),
    ]
    document, _, _ = made(api, content)
    found = [text_of(each) for each in paragraphs(parts_of(saved(api, str(document.pk))))]
    assert found == ["Cijene", "Najam", "Prodaja", "Kontakt"]


def made(api, content: list[Block], title: str = "Ponuda", edit=None, **looks):
    """A document of one tab of the content, edited after it was written, with styles of the
    looks, and where its blocks' text went."""
    document = Node.objects.get(pk=create(api, "document", title))
    tab = document.tabs_in_order()[0]
    _, written = fill(tab, content, then=edit)
    own = doc_of(document.room)
    before = own.get_state()
    stored = own.get(styles.STYLES, type=Map)
    for id, look in looks.items():
        stored[id] = Map({**styles.TEMPLATE[styles.STYLES]["text"], **look})
    Update.objects.create(document=document, room=document.room, data=own.get_update(before))
    return document, tab, written


def parts_of(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def w(name: str) -> str:
    return f"{{{W}}}{name}"


def levels(parts: dict[str, bytes]) -> dict[str, tuple]:
    """Each numbering's first level as Word shows it, by the numbering's id."""
    numbering = etree.fromstring(parts["word/numbering.xml"])
    found = {}
    for num in numbering.iterfind(w("num")):
        abstract = num.find(w("abstractNumId")).get(w("val"))
        lvl = numbering.find(f"{w('abstractNum')}[@{w('abstractNumId')}='{abstract}']/{w('lvl')}")
        found[num.get(w("numId"))] = tuple(
            lvl.find(w(name)).get(w("val")) for name in ("numFmt", "lvlText", "start")
        )
    return found


def paragraphs(parts: dict[str, bytes]) -> list:
    return list(etree.fromstring(parts["word/document.xml"]).iter(w("p")))


def text_of(paragraph) -> str:
    return "".join(each.text or "" for each in paragraph.iter(w("t")))


def number_of(paragraph) -> str | None:
    found = paragraph.find(f"{w('pPr')}/{w('numPr')}/{w('numId')}")
    return None if found is None else found.get(w("val"))


def test_what_only_a_document_has_is_written_as_word_shows_it(api, tmp_path):
    article = {"name": "Članak", "numbering": "1", "prefix": "Članak ", "suffix": "."}
    grid = Grid(
        ["r"],
        ["a", "b", "c"],
        formulas={"r:b": [{"from": {"row": "r", "col": "a"}}, "*2"]},
        col_looks={"c": {"fill": "#d9e2f3"}},
    )
    cells = [
        Cell("r", "a", [Block("paragraph", runs=[Run("1,25")])], fill="yellow"),
        Cell("r", "b", [Block("paragraph", runs=[Run("=A1*2", {"strong": {}})])]),
    ]
    linked = Run("Prilog", {"link": {"href": "/d/abc"}})
    content = [
        Block("paragraph", attrs={"style": "article"}, runs=[Run("Prvi")]),
        Block("paragraph", attrs={"style": "article"}, runs=[Run("Drugi")]),
        Block("paragraph", attrs={"list": "check", "checked": True}, runs=[Run("Gotovo")]),
        Block("paragraph", attrs={"list": "check"}, runs=[Run("Otvoreno")]),
        Block("paragraph", runs=[linked, Run(" "), Field("title"), Run(" "), Field("date")]),
        Block("table", "t", grid=grid, cells=cells),
    ]
    document, _, _ = made(api, content, article=article)
    data = saved(api, str(document.pk))
    parts = parts_of(data)
    shown = levels(parts)
    first, second, done, undone, line, _, valued, _, _ = paragraphs(parts)
    assert number_of(first) == number_of(second)
    assert shown[number_of(first)] == ("decimal", "Članak %1.", "1")
    assert (shown[number_of(done)][1], shown[number_of(undone)][1]) == ("☑", "☐")
    rels = etree.fromstring(parts["word/_rels/document.xml.rels"])
    link = line.find(w("hyperlink")).get(f"{{{R}}}id")
    assert [each.get("Target") for each in rels if each.get("Id") == link] == [
        "http://testserver/d/abc"
    ]
    dates = icu.DateFormat.createDateInstance(icu.DateFormat.SHORT, icu.Locale("hr"))
    today = dates.format(datetime.combine(timezone.localdate(), time(12)))
    assert text_of(line) == f"Prilog Ponuda {today}"
    assert valued.find(f"{w('pPr')}/{w('jc')}").get(w("val")) == "right"
    assert (text_of(valued), valued.find(f".//{w('b')}") is not None) == ("2,5", True)
    body = etree.fromstring(parts["word/document.xml"])
    shading = [cell.find(f"{w('tcPr')}/{w('shd')}") for cell in body.iter(w("tc"))]
    assert [each.get(w("fill")) if each is not None else None for each in shading] == [
        "FDE68A",
        None,
        "D9E2F3",
    ]
    again = read(tmp_path, data)
    assert {key: again.styles["article"][key] for key in article} == article
    assert [(block.attrs.get("style"), block.text) for block in again.tabs[0].blocks[:2]] == [
        ("article", "Prvi"),
        ("article", "Drugi"),
    ]


def test_a_table_s_design_goes_as_a_word_table_style_or_cell_by_cell_and_comes_back(api, tmp_path):
    line = {"line": "single", "width": 0.5, "color": "#123456"}
    word = {
        "rules": "word",
        "name": "Naš stil",
        "parts": {
            "table": {"valign": "center"},
            "header": {
                "marks": {"strong": {}, "color": {"color": "#fedcba"}},
                "caps": "small",
                "align": "center",
                "fill": "#1f4e79",
                "edges": {"bottom": {"line": "double", "width": 1.5, "color": "#123456"}},
            },
            "rowBand2": {"fill": "#dde5ee"},
            "totals": {"marks": {"strong": False, "underline": {}}, "fill": "none"},
        },
        "lines": {"top": line, "bottom": line, "insideH": "none"},
        "on": {"header": True, "totals": True, "rowBands": True},
        "spacing": 1.5,
        "background": "#eeeeee",
    }
    edged = {"rules": "word", "name": "Rubovi", "parts": {"table": {"edges": {"insideV": line}}}}
    excel = {
        "rules": "excel",
        "parts": {"header": {"marks": {"strong": {}}, "fill": "#abcdef"}},
        "on": {"header": True},
    }
    grid = Grid(["r1", "r2", "r3"], ["c1", "c2"])

    def table(id: str, design: dict) -> Block:
        cells = [
            Cell(row, col, [Block("paragraph", runs=[Run(row + col)])])
            for row in grid.rows
            for col in grid.cols
        ]
        cells[3].fill, cells[3].edges = "#fafbfc", {"left": line, "right": "none"}
        return Block("table", id, {"designs": [design]}, grid=grid, cells=cells)

    document, _, _ = made(api, [table("w", word), table("x", excel), table("e", edged)])
    data = saved(api, str(document.pk))
    parts = parts_of(data)
    named = [
        style.find(w("name")).get(w("val"))
        for style in etree.fromstring(parts["word/styles.xml"]).iter(w("style"))
        if style.get(w("type")) == "table"
    ]
    assert named == ["Naš stil", "Rubovi"]
    again = [block for block in read(tmp_path, data).tabs[0].blocks if block.type == "table"]
    assert again[0].attrs["designs"] == [word]
    assert "designs" not in again[1].attrs
    assert again[2].attrs["designs"] == [
        {"rules": "word", "name": "Rubovi", "lines": {"insideV": line}}
    ]
    drawn = [
        [
            next((cell.fill, cell.edges) for cell in each.cells if (cell.row, cell.col) == slot)
            for slot in ((row, col) for row in each.grid.rows for col in each.grid.cols)
        ]
        for each in again
    ]
    assert drawn[0][3] == ("#fafbfc", {"left": line, "right": "none"})
    assert [fill for fill, _ in drawn[1]] == ["#abcdef", "#abcdef", None, "#fafbfc", None, None]
    body = etree.fromstring(parts["word/document.xml"])
    header = list(body.iter(w("tbl")))[1].find(w("tr"))
    assert {run.find(f"{w('rPr')}/{w('b')}") is not None for run in header.iter(w("r"))} == {True}


def test_comments_go_with_their_stretches_replies_and_resolution(api, tmp_path):
    content = [
        Block("paragraph", "a", runs=[Run("Cijena je 100 €")]),
        Block("paragraph", "b", runs=[Run("Rok plaćanja 😀 je 30 dana")]),
        Block("paragraph", "c", runs=[Run("Izbrisano")]),
    ]

    def deleted(doc):
        del blocks.body_of(doc).children[2]

    document, tab, written = made(api, content, edit=deleted)
    across = {"from": written.position("a", 10), "to": written.position("b", 15, -1)}
    gone = {"from": written.position("c", 0), "to": written.position("c", 8, -1)}
    first = Thread.objects.create(tab=tab, anchor=across, quote="…", resolved_at=timezone.now())
    Comment.objects.create(thread=first, author=api.user, body="Provjeriti.\nHitno.")
    Comment.objects.create(thread=first, outside_author="Iva Ivić", body="Provjereno.")
    lost = Thread.objects.create(tab=tab, anchor=gone, quote="Izbrisano")
    Comment.objects.create(thread=lost, author=api.user, body="Što je bilo ovdje?")
    again = read(tmp_path, saved(api, str(document.pk)))
    a, b = again.tabs[0].blocks
    found = [
        (
            [(remark.author, remark.text) for remark in thread.remarks],
            thread.resolved,
            thread.start,
            thread.end,
        )
        for thread in again.threads
    ]
    assert found == [
        (
            [("ivo@example.com", "Provjeriti.\nHitno."), ("Iva Ivić", "Provjereno.")],
            True,
            (a.id, 10),
            (b.id, 15),
        ),
        ([("ivo@example.com", "Što je bilo ovdje?")], False, (a.id, 0), (a.id, 0)),
    ]


def test_a_tab_without_text_keeps_its_comments_in_a_paragraph_of_their_own(api):
    blob = store.put(io.BytesIO(picture())).sha256
    document, tab, _ = made(api, [Block("image", attrs={"blob": blob, "width": 50})])
    gone = {"from": {"item": {"client": 1, "clock": 0}, "assoc": 0}, "to": None}
    thread = Thread.objects.create(tab=tab, anchor=gone, quote="Slika")
    Comment.objects.create(thread=thread, author=api.user, body="Zamijeniti sliku.")
    parts = parts_of(saved(api, str(document.pk)))
    first, image = paragraphs(parts)
    assert [child.tag for child in first] == [
        w("pPr"),
        w("commentRangeStart"),
        w("commentRangeEnd"),
        w("r"),
    ]
    assert first[3].find(w("commentReference")) is not None
    assert image.find(f".//{w('drawing')}") is not None
    [comment] = etree.fromstring(parts["word/comments.xml"])
    assert text_of(comment) == "Zamijeniti sliku."


def test_pictures_go_in_as_word_reads_them(api, monkeypatch):
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
        b'<rect width="200" height="100" fill="teal"/></svg>'
    )
    drawn = []

    def draw(data, width, height):
        drawn.append((data, width, height))
        return picture(size=(400, 200))

    monkeypatch.setattr(printing, "drawn", draw)
    images = {"webp": picture("WEBP"), "turned": picture("JPEG", exif=exif), "svg": svg}
    blobs = {name: store.put(io.BytesIO(data)).sha256 for name, data in images.items()}
    content = [
        Block("image", attrs={"blob": blobs["webp"], "alt": "Logotip", "width": 50}),
        Block("image", attrs={"blob": blobs["turned"], "width": 25}),
        Block("image", attrs={"blob": blobs["svg"], "width": 100, "align": "center"}),
        Block("image", attrs={"blob": blobs["webp"]}),
    ]
    document, _, _ = made(api, content)
    parts = parts_of(saved(api, str(document.pk)))
    media = {name: data for name, data in parts.items() if name.startswith("word/media/")}
    assert sorted(media) == [
        "word/media/image3.svg",
        "word/media/picture1.png",
        "word/media/picture2.jpg",
        "word/media/picture3.png",
    ]
    assert Image.open(io.BytesIO(media["word/media/picture2.jpg"])).size == (20, 40)
    assert media["word/media/image3.svg"] == svg
    assert drawn == [(svg, 200, 100)]
    body = etree.fromstring(parts["word/document.xml"])
    extents = [(int(each.get("cx")), int(each.get("cy"))) for each in body.iter(f"{{{WP}}}extent")]
    across = 16 * docx.EMU_PER_CM
    assert extents == [
        (across // 2, across // 4),
        (across // 4, across // 2),
        (across, across // 2),
        (40 * docx.EMU_PER_PIXEL, 20 * docx.EMU_PER_PIXEL),
    ]


def test_the_pages_a_pdf_shows_go_in_as_pictures_of_them(api):
    tall = io.BytesIO()
    with pikepdf.open(io.BytesIO(pdf_bytes("Ugovor", "Potpisi", "Prilog"))) as pdf:
        pdf.pages[2].MediaBox = [0, 0, 300, 1200]
        pdf.save(tall)
    blob = store.put(io.BytesIO(tall.getvalue())).sha256
    shown = {"blob": blob, "title": "Najam", "first": 2, "width": 50, "align": "center"}
    document, _, _ = made(api, [Block("pdf", attrs=shown), Block("pdf", attrs={"blob": blob})])
    parts = parts_of(saved(api, str(document.pk)))
    media = {name: data for name, data in parts.items() if name.startswith("word/media/")}
    assert sorted(media) == [f"word/media/page{number}.png" for number in (1, 2, 3)]
    assert Image.open(io.BytesIO(media["word/media/page1.png"])).size == (630, 892)
    body = etree.fromstring(parts["word/document.xml"])
    extents = [(int(each.get("cx")), int(each.get("cy"))) for each in body.iter(f"{{{WP}}}extent")]
    half, high = 8 * docx.EMU_PER_CM, round(24.7 * docx.EMU_PER_CM)
    assert extents == [
        (half, round(half * 842 / 595)),
        (round(high / 4), high),
        (2 * half, round(2 * half * 842 / 595)),
        (2 * half, round(2 * half * 842 / 595)),
        (round(high / 4), high),
    ]
    alts = [each.get("descr") for each in body.iter(f"{{{WP}}}docPr")]
    assert alts == ["Najam · 2", "Najam · 3", "1", "2", "3"]
    first, second, *_ = paragraphs(parts)
    assert [each.find(f"{w('pPr')}/{w('jc')}").get(w("val")) for each in (first, second)] == [
        "center",
        "center",
    ]


def test_without_the_printer_an_svg_picture_is_refused_aloud(api, monkeypatch):
    def draw(data, width, height):
        raise printing.Unavailable

    monkeypatch.setattr(printing, "drawn", draw)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"/>'
    blob = store.put(io.BytesIO(svg)).sha256
    document, _, _ = made(api, [Block("image", attrs={"blob": blob})])
    assert refused(api, "docx", document=document.pk) == (503, "printer_unavailable")


def test_an_image_none_can_read_is_refused_aloud(api):
    blob = store.put(io.BytesIO(PNG)).sha256
    document, _, _ = made(api, [Block("image", attrs={"blob": blob, "width": 50})])
    assert refused(api, "docx", document=document.pk) == (422, "unreadable_image")


def test_a_word_file_with_macros_goes_back_with_its_vba_project(api, tmp_path):
    original = with_macros(word_file(p("Ugovor")))
    node = bring(api, original)
    assert node["macros"] == "docm"
    data = saved(api, node["id"], "docm")
    assert store.put(io.BytesIO(data)).media_type == store.DOCM
    with zipfile.ZipFile(io.BytesIO(original)) as source:
        assert parts_of(data)["word/vbaProject.bin"] == source.read("word/vbaProject.bin")
    assert read(tmp_path, data, "saved.docm").report["macros"] == [
        {"name": "Module1", "code": 'Sub Zbroji()\n    Range("A1") = "Šećer"\nEnd Sub'}
    ]
    assert refused(api, "docm", document=bring(api)["id"]) == (404, "no_macros")
