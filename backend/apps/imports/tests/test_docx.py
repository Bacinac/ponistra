import zipfile
from datetime import UTC, datetime

import pytest

from apps.content import lists
from apps.content.blocks import Block, Field, Note, Run, in_order
from apps.imports import docx, office, reading

from .word_files import numbered, p, theme, word_file

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
STYLES = """
<w:docDefaults>
  <w:rPrDefault><w:rPr><w:rFonts w:asciiTheme="minorHAnsi" w:hAnsiTheme="minorHAnsi"/>
    <w:sz w:val="22"/></w:rPr></w:rPrDefault>
  <w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="259" w:lineRule="auto"/></w:pPr>
  </w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>
  <w:basedOn w:val="Normal"/>
  <w:pPr><w:numPr><w:numId w:val="1"/></w:numPr><w:spacing w:before="240" w:after="0"/>
    <w:ind w:left="432" w:hanging="432"/></w:pPr>
  <w:rPr><w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi"/><w:b/>
    <w:color w:val="2F5496"/><w:sz w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>
  <w:basedOn w:val="Heading1"/>
  <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr></w:pPr>
  <w:rPr><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:customStyle="1" w:styleId="Quote1"><w:name w:val="Citat"/>
  <w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:i/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/>
  <w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="720"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/>
  <w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="TOCHeading"><w:name w:val="TOC Heading"/>
  <w:basedOn w:val="Heading1"/><w:pPr><w:numPr><w:numId w:val="0"/></w:numPr></w:pPr></w:style>
<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/>
  <w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>
"""
HEADINGS = """
<w:abstractNum w:abstractNumId="0">
  <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>
  </w:lvl>
  <w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1.%2."/>
  </w:lvl>
</w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
"""
LISTS = """
<w:abstractNum w:abstractNumId="1">
  <w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/></w:lvl>
</w:abstractNum>
<w:abstractNum w:abstractNumId="2">
  <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>
  </w:lvl>
  <w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/>
    <w:lvlText w:val="%2."/></w:lvl>
</w:abstractNum>
<w:abstractNum w:abstractNumId="3">
  <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/>
    <w:lvlText w:val="%1)"/></w:lvl>
</w:abstractNum>
<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
<w:num w:numId="3"><w:abstractNumId w:val="2"/></w:num>
<w:num w:numId="4"><w:abstractNumId w:val="2"/>
  <w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>
<w:num w:numId="5"><w:abstractNumId w:val="3"/></w:num>
<w:abstractNum w:abstractNumId="4">
  <w:lvl w:ilvl="0"><w:start w:val="5"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>
  </w:lvl>
</w:abstractNum>
<w:num w:numId="6"><w:abstractNumId w:val="4"/></w:num>
"""


def lvl(ilvl: int, format: str, text: str, props: str = "", font: str = "") -> str:
    fonts = f'<w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/></w:rPr>' if font else ""
    return (
        f'<w:lvl w:ilvl="{ilvl}"><w:start w:val="1"/><w:numFmt w:val="{format}"/>'
        f'<w:lvlText w:val="{text}"/>{props}{fonts}</w:lvl>'
    )


FORMATTED = (
    '<w:abstractNum w:abstractNumId="10">'
    + lvl(0, "decimal", "Članak %1.", font="Times New Roman")
    + lvl(1, "decimal", "%1.%2.")
    + lvl(2, "lowerLetter", "%1.%2.%3)")
    + '</w:abstractNum><w:abstractNum w:abstractNumId="11">'
    + lvl(0, "bullet", "\uf0b7", font="Symbol")
    + lvl(1, "bullet", "o", font="Courier New")
    + lvl(2, "bullet", "\uf0a7", font="Wingdings")
    + lvl(3, "bullet", "\uf02d", font="Symbol")
    + lvl(4, "bullet", "\uf0d8", font="Wingdings")
    + lvl(5, "bullet", "\uf078", font="Wingdings")
    + '</w:abstractNum><w:abstractNum w:abstractNumId="12">'
    + lvl(0, "ordinal", "%1.")
    + lvl(1, "decimalZero", "%2.")
    + lvl(2, "decimal", "%1.%3.")
    + '</w:abstractNum><w:abstractNum w:abstractNumId="13">'
    + lvl(0, "upperRoman", "%1.")
    + lvl(1, "decimal", "%1.%2.", "<w:isLgl/>")
    + "</w:abstractNum>"
    + "".join(
        f'<w:num w:numId="{num}"><w:abstractNumId w:val="{abstract}"/></w:num>'
        for num, abstract in ((10, 10), (11, 10), (12, 11), (13, 12), (14, 13))
    )
)


def read(tmp_path, body: str, **parts) -> reading.Imported:
    path = tmp_path / "file.docx"
    path.write_bytes(word_file(body, **parts))
    return docx.read(path, "hr")


def run(text: str, props: str = "") -> str:
    return f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{text}</w:t></w:r>'


def content(found: reading.Imported) -> list[Block]:
    [tab] = found.tabs
    return tab.blocks


def section(references: str = "", landscape: bool = False, first: bool = False) -> str:
    """A section of A4 pages with 2.5 cm margins, which names its headers and footers."""
    size = (
        'w:w="16838" w:h="11906" w:orient="landscape"' if landscape else 'w:w="11906" w:h="16838"'
    )
    return (
        f"<w:sectPr>{references}<w:pgSz {size}/>"
        '<w:pgMar w:top="1418" w:right="1418" w:bottom="1418" w:left="1418" w:header="709" '
        f'w:footer="709"/>{"<w:titlePg/>" if first else ""}</w:sectPr>'
    )


def named(side: str, kind: str, part: str) -> str:
    return f'<w:{side}Reference w:type="{kind}" r:id="rId{part}"/>'


def ending(text: str, ends: str) -> str:
    """The paragraph that ends a section."""
    return f"<w:p><w:pPr>{ends}</w:pPr>{run(text)}</w:p>"


def field(instruction: str, shown: str | None) -> str:
    result = f'<w:r><w:fldChar w:fldCharType="separate"/></w:r>{run(shown)}' if shown else ""
    return (
        f'<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve">'
        f'{instruction}</w:instrText></w:r>{result}<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


def test_styles_come_over_as_the_document_styles(tmp_path):
    body = (
        p("Uvod", "Heading1")
        + p("Predmet", "Heading2")
        + p("Citat", "Quote1")
        + p("Uvučeno", "ListParagraph")
    )
    found = read(
        tmp_path,
        body,
        styles=STYLES,
        numbering=HEADINGS,
        theme=theme("Calibri Light", "Calibri"),
    )
    assert found.theme == {"headings": "Carlito", "text": "Carlito"}
    text, h1, h2 = found.styles["text"], found.styles["h1"], found.styles["h2"]
    assert (text["font"], text["size"], text["after"], text["line"]) == ("text", 11, 8, 1.24)
    assert (h1["font"], h1["size"], h1["bold"], h1["color"]) == ("headings", 16, True, "#2f5496")
    assert (h1["before"], h1["after"]) == (12, 0)
    assert (h1["numbering"], h1["prefix"], h1["suffix"], h1["nested"]) == ("1", "", ".", False)
    assert (h2["size"], h2["numbering"], h2["suffix"], h2["nested"]) == (13, "1", ".", True)
    assert found.styles["Quote1"] == {
        **text,
        "name": "Citat",
        "italic": True,
        "align": "center",
    }
    assert "ListParagraph" not in found.styles
    assert [(block.type, block.attrs, block.text) for block in content(found)] == [
        ("heading", {"level": 1}, "Uvod"),
        ("heading", {"level": 2}, "Predmet"),
        ("paragraph", {"style": "Quote1"}, "Citat"),
        ("paragraph", {"indent": 1.27}, "Uvučeno"),
    ]
    assert found.report["lost"] == {}


def test_a_paragraph_keeps_its_indents_its_first_line_never_before_its_left_edge(tmp_path):
    body = "".join(
        f"<w:p><w:pPr><w:ind {ind}/></w:pPr>{run('tekst')}</w:p>"
        for ind in (
            'w:left="1134" w:hanging="567" w:right="567"',
            'w:start="567" w:firstLine="850"',
            'w:left="283" w:hanging="567"',
        )
    )
    assert [block.attrs for block in content(read(tmp_path, body, styles=STYLES))] == [
        {"indent": 2.0, "firstLine": -1.0, "right": 1.0},
        {"indent": 1.0, "firstLine": 1.5},
        {"indent": 0.5, "firstLine": -0.5},
    ]


def test_tab_stops_join_their_styles_and_keep_their_leaders(tmp_path):
    styles = (
        STYLES + '<w:style w:type="paragraph" w:styleId="Form"><w:name w:val="Form"/>'
        '<w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9071"/>'
        '<w:tab w:val="left" w:pos="1134"/></w:tabs></w:pPr></w:style>'
    )
    body = (
        '<w:p><w:pPr><w:pStyle w:val="Form"/><w:tabs><w:tab w:val="clear" w:pos="1134"/>'
        '<w:tab w:val="center" w:pos="4536"/><w:tab w:val="decimal" w:pos="5670"/>'
        '<w:tab w:val="bar" w:pos="6000"/></w:tabs></w:pPr>' + run("Ime") + "</w:p>"
    )
    (block,) = content(read(tmp_path, body, styles=styles))
    assert block.attrs["tabs"] == [
        {"at": 8.0, "kind": "center"},
        {"at": 10.0, "kind": "decimal"},
        {"at": 16.0, "kind": "right", "leader": "dot"},
    ]


def test_an_empty_paragraph_keeps_the_formatting_of_its_mark(tmp_path):
    body = (
        '<w:p><w:pPr><w:rPr><w:b/><w:color w:val="C00000"/></w:rPr></w:pPr></w:p>'
        "<w:p><w:pPr><w:rPr><w:b/></w:rPr></w:pPr>" + run("tekst") + "</w:p>"
    )
    empty, written = content(read(tmp_path, body, styles=STYLES))
    assert empty.attrs["endMarks"] == {"strong": {}, "color": {"color": "#c00000"}}
    assert "endMarks" not in written.attrs


def test_a_run_unlike_its_style_is_marked(tmp_path):
    body = (
        "<w:p>"
        + run("Obično ")
        + run("podebljano", "<w:b/>")
        + run(
            " Arial",
            '<w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:color w:val="C00000"/>'
            '<w:sz w:val="28"/><w:highlight w:val="yellow"/>',
        )
        + run(" velika", "<w:caps/>")
        + run("2", '<w:vertAlign w:val="superscript"/>')
        + run(" skriveno", "<w:vanish/>")
        + "</w:p>"
    )
    found = read(tmp_path, body, styles=STYLES, theme=theme("Calibri Light", "Calibri"))
    assert content(found)[0].runs == [
        Run("Obično "),
        Run("podebljano", {"strong": {}}),
        Run(
            " Arial",
            {
                "color": {"color": "#c00000"},
                "highlight": {"color": "#ffff00"},
                "font": {"family": "Arial"},
                "size": {"pt": 14.0},
            },
        ),
        Run(" VELIKA"),
        Run("2", {"sup": {}}),
    ]
    assert found.report["fonts"] == []
    assert found.report["lost"] == {"hiddenText": 1}


KERNED = """
<w:docDefaults><w:rPrDefault><w:rPr><w:kern w:val="2"/><w:sz w:val="24"/></w:rPr>
  </w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>
  <w:rPr><w:kern w:val="28"/><w:sz w:val="56"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="NoSpacing"><w:name w:val="No Spacing"/>
  <w:basedOn w:val="Normal"/><w:rPr><w:kern w:val="0"/></w:rPr></w:style>
"""


def test_text_is_kerned_where_word_kerns_it(tmp_path):
    body = (
        '<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr>'
        + run("Naslov")
        + run(" sitno", '<w:sz w:val="20"/>')
        + "</w:p><w:p>"
        + run("Tekst")
        + run(" bez", '<w:kern w:val="0"/>')
        + "</w:p>"
        + p("Zbijeno", "NoSpacing")
    )
    found = read(tmp_path, body, styles=KERNED)
    assert [found.styles[id]["kerning"] for id in ("text", "title", "h1", "NoSpacing")] == [
        True,
        True,
        True,
        False,
    ]
    title, text, tight = content(found)
    assert title.runs == [
        Run("Naslov"),
        Run(" sitno", {"size": {"pt": 10.0}, "kerning": {"on": False}}),
    ]
    assert text.runs == [Run("Tekst"), Run(" bez", {"kerning": {"on": False}})]
    assert tight.attrs == {"style": "NoSpacing"}
    kerned = "<w:p>" + run("Aptos", '<w:kern w:val="2"/>') + "</w:p>"
    plain = read(tmp_path, p("Calibri") + kerned, styles=STYLES)
    assert [plain.styles[id]["kerning"] for id in ("text", "title")] == [False, False]
    assert content(plain)[1].runs == [Run("Aptos", {"kerning": {"on": True}})]


def test_lists_count_as_word_counts_them(tmp_path):
    body = (
        numbered("Prvi", 3)
        + numbered("Podstavka", 3, 1)
        + p("Između")
        + numbered("Drugi", 3)
        + numbered("Točka", 2)
        + numbered("Treći", 3)
        + numbered("Opet prvi", 4)
        + numbered("Opet drugi", 4)
        + numbered("Slovo", 5)
        + numbered("Peti", 6)
    )
    found = read(tmp_path, body, styles=STYLES, numbering=LISTS)
    [letters] = found.formats
    assert [block.attrs for block in content(found)] == [
        {"list": "number"},
        {"list": "number", "indent": 1.25},
        {},
        {"list": "number", "continued": True},
        {"list": "bullet"},
        {"list": "number", "continued": True},
        {"list": "number", "restart": True},
        {"list": "number"},
        {"list": "number", "restart": True, "format": letters},
        {"list": "number"},
    ]
    assert found.formats[letters][:2] == [
        {"numbering": "a", "prefix": "", "suffix": ")", "nested": False},
        {"numbering": "a", "prefix": "", "suffix": ".", "nested": False},
    ]
    assert found.report["lost"] == {"listNumbers": 1}


def test_lists_keep_words_numbers_and_bullets_where_ours_show_them(tmp_path):
    body = (
        numbered("Članak", 10)
        + numbered("Stavak", 10, 1)
        + numbered("Točka", 10, 2)
        + p("Između")
        + numbered("Drugi popis", 11)
        + p()
        + numbered("Crtica", 12, 3)
        + numbered("Strelica", 12, 4)
        + numbered("Nepoznat znak", 12, 5)
        + p()
        + numbered("Redni", 13)
        + numbered("S nulom", 13, 1)
        + numbered("Preskočen", 13, 2)
        + p()
        + numbered("Rimski", 14)
        + numbered("Zakonski", 14, 1)
    )
    found = read(tmp_path, body, styles=STYLES, numbering=FORMATTED)
    article, bullets, roman = found.formats
    assert [block.attrs.get("format") for block in content(found) if block.runs] == [
        article,
        article,
        article,
        None,
        article,
        bullets,
        bullets,
        bullets,
        None,
        None,
        None,
        roman,
        roman,
    ]
    assert found.formats[article][:4] == [
        {"numbering": "1", "prefix": "Članak ", "suffix": ".", "nested": False},
        {"numbering": "1", "prefix": "", "suffix": ".", "nested": True},
        {"numbering": "a", "prefix": "", "suffix": ")", "nested": True},
        lists.standard("number", 3),
    ]
    assert [level["prefix"] for level in found.formats[bullets][:6]] == [
        "•",
        "◦",
        "▪",
        "–",
        "➢",
        "▪",
    ]
    assert found.formats[roman][:2] == [
        {"numbering": "I", "prefix": "", "suffix": ".", "nested": False},
        lists.standard("number", 1),
    ]
    assert found.report["lost"] == {"listFormats": 5}


def test_headings_word_numbers_one_by_one_count_by_their_style(tmp_path):
    plain = STYLES.replace('<w:numPr><w:numId w:val="1"/></w:numPr>', "")
    own = '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="3"/></w:numPr>'
    body = p("Uvod", "Heading1", own) + p("Tekst") + p("Plan", "Heading1", own)
    found = read(tmp_path, body + p("Prilozi", "Heading1"), styles=plain, numbering=LISTS)
    h1 = found.styles["h1"]
    assert (h1["numbering"], h1["prefix"], h1["suffix"]) == ("1", "", ".")
    assert found.report["lost"] == {"listNumbers": 1}
    found = read(tmp_path, p("Prilozi", "Heading1") + body, styles=plain, numbering=LISTS)
    assert found.styles["h1"]["numbering"] == ""
    assert found.report["lost"] == {"listNumbers": 2}


def test_a_nested_list_after_a_gap_continues_the_list_above_it(tmp_path):
    body = (
        numbered("Prvi", 3)
        + p()
        + numbered("Podstavka", 3, 1)
        + numbered("Druga podstavka", 3, 1)
        + p()
        + numbered("Drugi", 3)
    )
    found = read(tmp_path, body, styles=STYLES, numbering=LISTS)
    assert [block.attrs for block in content(found)] == [
        {"list": "number"},
        {},
        {"list": "number", "indent": 1.25, "continued": True},
        {"list": "number", "indent": 1.25},
        {},
        {"list": "number", "continued": True},
    ]
    assert found.report["lost"] == {}


def test_a_heading_without_its_styles_number_is_counted(tmp_path):
    body = p("Bez broja", "Heading1", '<w:numPr><w:numId w:val="0"/></w:numPr>')
    found = read(tmp_path, body, styles=STYLES, numbering=HEADINGS)
    assert content(found)[0].attrs == {"level": 1}
    assert found.report["lost"] == {"listNumbers": 1}


def test_a_cell_keeps_its_shading_over_the_design_its_table_s_style_and_look_give(tmp_path):
    cell = "<w:tc><w:tcPr>{}</w:tcPr><w:p>{}</w:p></w:tc>"
    shaded = '<w:shd w:val="clear" w:color="auto" w:fill="{}"/>'
    banded = (
        '<w:style w:type="table" w:styleId="Grid4"><w:name w:val="Grid Table 4"/>'
        '<w:tblStylePr w:type="firstRow"><w:rPr><w:b/><w:color w:val="FFFFFF"/></w:rPr>'
        "<w:tcPr>" + shaded.format("4472C4") + "</w:tcPr></w:tblStylePr></w:style>"
    )

    def table(look: str, *cells: str) -> str:
        return (
            '<w:tbl><w:tblPr><w:tblStyle w:val="Grid4"/>'
            + look
            + '</w:tblPr><w:tblGrid><w:gridCol w:w="3000"/><w:gridCol w:w="3000"/></w:tblGrid>'
            + "<w:tr>"
            + "".join(cells)
            + "</w:tr></w:tbl>"
        )

    body = (
        table(
            '<w:tblLook w:val="04A0" w:firstRow="0" w:noVBand="1"/>',
            cell.format(shaded.format("FFFF00"), run("Žuto")),
            cell.format(shaded.format("D9E2F3"), ""),
        )
        + table("", cell.format(shaded.format("auto"), run("A")), cell.format("", run("B")))
        + table('<w:tblLook w:val="04A0"/>', cell.format("", run("C")))
    )
    found = read(tmp_path, body, styles=banded)
    first, second, third = content(found)
    assert [(cell.text, cell.fill) for cell in first.cells] == [
        ("Žuto", "#ffff00"),
        ("", "#d9e2f3"),
    ]
    assert [cell.fill for cell in second.cells] == ["none", None]
    assert found.report["lost"] == {}
    header = {"marks": {"strong": {}, "color": {"color": "#ffffff"}}, "fill": "#4472c4"}
    assert [table.attrs["designs"] for table in (first, third)] == [
        [
            {
                "rules": "word",
                "name": "Grid Table 4",
                "parts": {"header": header},
                "on": {"firstColumn": True, "rowBands": True},
            }
        ],
        [
            {
                "rules": "word",
                "name": "Grid Table 4",
                "parts": {"header": header},
                "on": {"header": True, "firstColumn": True, "rowBands": True},
            }
        ],
    ]
    assert len(third.cells) == 1


def test_word_draws_neither_its_table_style_s_lines_for_every_cell_nor_a_whole_table_format(
    tmp_path,
):
    line = '<w:{} w:val="single" w:sz="18" w:color="336699"/>'
    edges = "".join(line.format(side) for side in ("top", "left", "insideH"))
    styles = (
        '<w:style w:type="table" w:styleId="Own"><w:name w:val="Own"/><w:rPr><w:b/></w:rPr>'
        f'<w:tcPr><w:tcBorders>{edges}</w:tcBorders><w:shd w:val="clear" w:fill="99CCFF"/></w:tcPr>'
        '<w:tblStylePr w:type="wholeTable"><w:rPr><w:i/></w:rPr>'
        f"<w:tcPr><w:tcBorders>{edges}</w:tcBorders></w:tcPr></w:tblStylePr></w:style>"
    )
    body = (
        '<w:tbl><w:tblPr><w:tblStyle w:val="Own"/></w:tblPr><w:tblGrid><w:gridCol w:w="3000"/>'
        f"</w:tblGrid><w:tr><w:tc><w:p>{run('A')}</w:p></w:tc></w:tr></w:tbl>"
    )
    found = read(tmp_path, body, styles=styles)
    (table,) = content(found)
    (design,) = table.attrs["designs"]
    assert design["parts"] == {"table": {"marks": {"strong": {}}, "fill": "#99ccff"}}
    assert found.report["lost"] == {}


def test_word_counts_a_style_part_once_its_element_holds_anything(tmp_path):
    styles = (
        '<w:style w:type="table" w:styleId="Own"><w:name w:val="Own"/>'
        '<w:tblStylePr w:type="firstRow"><w:tcPr><w:shd w:val="clear" w:fill="99CCFF"/></w:tcPr>'
        '</w:tblStylePr><w:tblStylePr w:type="lastRow"><w:pPr><w:spacing w:after="0"/></w:pPr>'
        '</w:tblStylePr><w:tblStylePr w:type="lastCol"><w:tcPr/></w:tblStylePr>'
        '<w:tblStylePr w:type="nwCell"/></w:style>'
    )
    body = (
        '<w:tbl><w:tblPr><w:tblStyle w:val="Own"/></w:tblPr><w:tblGrid><w:gridCol w:w="3000"/>'
        f"</w:tblGrid><w:tr><w:tc><w:p>{run('A')}</w:p></w:tc></w:tr></w:tbl>"
    )
    (table,) = content(read(tmp_path, body, styles=styles))
    (design,) = table.attrs["designs"]
    assert design["parts"] == {"header": {"fill": "#99ccff"}, "totals": {}, "lastColumn": {}}


def test_cells_set_apart_keep_the_table_s_shading_and_a_row_set_apart_otherwise_counts(tmp_path):
    def table(props: str, row: str = "") -> str:
        return (
            f'<w:tbl><w:tblPr>{props}</w:tblPr><w:tblGrid><w:gridCol w:w="3000"/></w:tblGrid>'
            f"<w:tr><w:trPr>{row}</w:trPr><w:tc><w:p>{run('A')}</w:p></w:tc></w:tr></w:tbl>"
        )

    gap = '<w:tblCellSpacing w:w="{}" w:type="dxa"/>'
    lines = '<w:tblBorders><w:insideH w:val="single" w:sz="4" w:color="000000"/></w:tblBorders>'
    shade = '<w:shd w:val="clear" w:color="auto" w:fill="DDDDDD"/>'
    body = (
        table(gap.format(144) + lines + shade, gap.format(144))
        + table(lines + shade)
        + table(gap.format(15) + shade, gap.format(40))
    )
    found = read(tmp_path, body)
    spaced, close, bare = (table.attrs["designs"][0] for table in content(found))
    insideH = {"line": "single", "width": 0.5, "color": "#000000"}
    assert spaced == {
        "rules": "word",
        "lines": {"insideH": insideH},
        "spacing": 7.2,
        "background": "#dddddd",
    }
    assert close == {"rules": "word", "lines": {"insideH": insideH}}
    assert bare == {"rules": "word", "spacing": 0.75, "background": "#dddddd"}
    assert found.report["lost"] == {"tableStyles": 1}


def test_a_table_keeps_its_merged_cells_widths_row_heights_and_header_rows(tmp_path):
    cell = "<w:tc>{}<w:p>{}</w:p></w:tc>"
    body = (
        '<w:tbl><w:tblPr><w:tblBorders><w:top w:val="single"/></w:tblBorders></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="3000"/><w:gridCol w:w="3000"/><w:gridCol w:w="6000"/>'
        '</w:tblGrid><w:tr><w:trPr><w:trHeight w:val="600" w:hRule="exact"/><w:tblHeader/>'
        "</w:trPr>"
        + cell.format('<w:tcPr><w:gridSpan w:val="2"/></w:tcPr>', run("Spojeno"))
        + cell.format('<w:tcPr><w:vMerge w:val="restart"/></w:tcPr>', run("Okomito"))
        + '</w:tr><w:tr><w:trPr><w:trHeight w:val="900" w:hRule="auto"/>'
        '<w:tblHeader w:val="0"/></w:trPr>'
        + cell.format("", "")
        + cell.format("", run("B2"))
        + cell.format("<w:tcPr><w:vMerge/></w:tcPr>", "")
        + "</w:tr></w:tbl>"
        + '<w:tbl><w:tblGrid><w:gridCol w:w="100"/></w:tblGrid><w:tr>'
        + cell.format("", run("Bez okvira"))
        + "</w:tr></w:tbl>"
    )
    table, plain = content(read(tmp_path, body))
    rows, cols = table.grid.rows, table.grid.cols
    assert table.attrs == {
        "widths": dict(zip(cols, [25.0, 25.0, 50.0], strict=True)),
        "designs": [{"rules": "word", "lines": {"top": {"line": "single", "width": 0.25}}}],
        "heights": {rows[0]: 30.0},
        "frozen": rows[0],
    }
    assert [(cell.row, cell.col, cell.to, cell.text) for cell in table.cells] == [
        (rows[0], cols[0], f"{rows[0]}:{cols[1]}", "Spojeno"),
        (rows[0], cols[2], f"{rows[1]}:{cols[2]}", "Okomito"),
        (rows[1], cols[1], None, "B2"),
    ]
    assert "designs" not in plain.attrs


def test_pictures_come_over_and_what_cannot_be_shown_is_counted(tmp_path):
    def drawing(rid: str, cx: int) -> str:
        return (
            f'<w:r><w:drawing><wp:inline><wp:extent cx="{cx}" cy="100"/>'
            '<wp:docPr id="1" name="Slika" descr="Logotip"/><a:graphic>'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:blipFill><a:blip r:embed="{rid}"/></pic:blipFill></pic:pic>'
            "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
        )

    body = (
        f'<w:p><w:pPr><w:jc w:val="center"/></w:pPr>{drawing("rId10", 2880000)}</w:p>'
        f"<w:p>{run('Uz tekst')}{drawing('rId10', 99_000_000)}{drawing('rId11', 100)}</w:p>"
    )
    media = {"rId10": ("image1.png", PNG), "rId11": ("image2.emf", b"\x01\x00\x00\x00emf")}
    found = read(tmp_path, body, media=media)
    image, paragraph, wide = content(found)
    assert (image.type, wide.type, paragraph.text) == ("image", "image", "Uz tekst")
    sha256 = next(iter(found.images))
    assert found.images == {sha256: PNG}
    assert image.attrs == {"blob": sha256, "alt": "Logotip", "width": 50, "align": "center"}
    assert wide.attrs["width"] == 100
    assert found.report["lost"] == {"images": 1}


def test_notes_are_kept_where_their_marks_are(tmp_path):
    footnotes = (
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p>'
        '</w:footnote><w:footnote w:id="1"><w:p><w:r><w:footnoteRef/></w:r>'
        + run(" Izvor: ")
        + run("Narodne novine", "<w:i/>")
        + "</w:p></w:footnote>"
    )
    endnotes = f'<w:endnote w:id="1"><w:p>{run("Kraj")}</w:p></w:endnote>'
    body = (
        f'<w:p>{run("Tekst")}<w:r><w:footnoteReference w:id="1"/></w:r>{run(" i dalje")}'
        '<w:r><w:endnoteReference w:id="1"/></w:r></w:p>'
    )
    found = read(tmp_path, body, footnotes=footnotes, endnotes=endnotes)
    runs = content(found)[0].runs
    assert [type(each) for each in runs] == [Run, Note, Run, Note]
    assert (runs[1].kind, runs[1].runs) == (
        "foot",
        [Run("Izvor: "), Run("Narodne novine", {"em": {}})],
    )
    assert (runs[3].kind, runs[3].runs) == ("end", [Run("Kraj")])
    assert content(found)[0].text == "Tekst i dalje"


def test_comments_keep_their_text_replies_and_authors(tmp_path):
    comments = (
        '<w:comment w:id="0" w:author="Marko Marić" w:date="2026-03-02T10:15:00Z">'
        '<w:p w14:paraId="1A000001"><w:r><w:t>Provjeriti iznos.</w:t></w:r></w:p></w:comment>'
        '<w:comment w:id="1" w:author="Iva Ivić" w:date="2026-03-03T08:00:00Z">'
        '<w:p w14:paraId="1A000002"><w:r><w:t>Provjereno.</w:t></w:r></w:p></w:comment>'
        '<w:comment w:id="2" w:author="Nitko"><w:p><w:r><w:t>Bez mjesta</w:t></w:r></w:p>'
        "</w:comment>"
    )
    extended = (
        '<w15:commentEx w15:paraId="1A000001" w15:done="1"/>'
        '<w15:commentEx w15:paraId="1A000002" w15:paraIdParent="1A000001" w15:done="0"/>'
    )
    body = (
        f"<w:p>{run('Cijena je ')}"
        '<w:commentRangeStart w:id="0"/>'
        f"{run('100 €')}"
        '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r>'
        f"{run('.')}</w:p>"
    )
    found = read(tmp_path, body, comments=comments, extended=extended)
    block = content(found)[0].id
    [thread] = found.threads
    assert (thread.start, thread.end, thread.quote, thread.resolved) == (
        (block, 10),
        (block, 14),
        "100 €",
        True,
    )
    assert [(each.author, each.text, each.date) for each in thread.remarks] == [
        ("Marko Marić", "Provjeriti iznos.", datetime(2026, 3, 2, 10, 15, tzinfo=UTC)),
        ("Iva Ivić", "Provjereno.", datetime(2026, 3, 3, 8, 0, tzinfo=UTC)),
    ]
    assert found.report["lost"] == {"comments": 1}


def test_page_breaks_start_pages_and_split_their_paragraph_with_its_comments(tmp_path):
    comments = (
        '<w:comment w:id="0" w:author="Ana"><w:p><w:r><w:t>Vidi</w:t></w:r></w:p></w:comment>'
    )
    broken = '<w:r><w:br w:type="page"/></w:r>'
    body = (
        p("Uvod")
        + f"<w:p>{run('Prvi dio ')}"
        + '<w:commentRangeStart w:id="0"/>'
        + f"{run('drugi')}{broken}{run('treći')}"
        + '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r></w:p>'
        + f"<w:p>{broken}</w:p>"
        + p("Članak", "Heading1", props="<w:pageBreakBefore/>")
        + p("Kraj", props="<w:pageBreakBefore/>")
        + p("Bez prijeloma", props='<w:pageBreakBefore w:val="0"/>')
        + f'<w:p>{run("Stupac")}<w:r><w:br w:type="column"/></w:r></w:p>'
    )
    found = read(tmp_path, body, styles=STYLES, comments=comments)
    blocks = content(found)
    assert [(block.type, block.text) for block in blocks] == [
        ("paragraph", "Uvod"),
        ("paragraph", "Prvi dio drugi"),
        ("pageBreak", ""),
        ("paragraph", "treći"),
        ("pageBreak", ""),
        ("heading", "Članak"),
        ("pageBreak", ""),
        ("paragraph", "Kraj"),
        ("paragraph", "Bez prijeloma"),
        ("paragraph", "Stupac"),
    ]
    assert blocks[1].id != blocks[3].id
    [thread] = found.threads
    assert (thread.start, thread.end, thread.quote) == (
        (blocks[1].id, 9),
        (blocks[3].id, 4),
        "drugi\ntreći",
    )
    assert found.report["lost"] == {"pageBreaks": 1}


def test_a_page_break_leaves_the_list_its_paragraph_is_in(tmp_path):
    body = numbered("Prva", 3) + numbered("Druga", 3).replace(
        "</w:t></w:r>", '</w:t></w:r><w:r><w:br w:type="page"/><w:t>nastavak</w:t></w:r>'
    )
    blocks = content(read(tmp_path, body, styles=STYLES, numbering=LISTS))
    assert [(block.text, block.attrs.get("list")) for block in blocks] == [
        ("Prva", "number"),
        ("Druga", "number"),
        ("", None),
        ("nastavak", None),
    ]


def test_tracked_changes_come_in_as_proposals_and_links_are_kept(tmp_path):
    def field(instruction: str, shown: str) -> str:
        return (
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve">{instruction}</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f"{run(shown)}"
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        )

    body = (
        f"<w:p>{run('Rok je ')}"
        '<w:del w:id="1" w:author="A"><w:r><w:delText>30</w:delText></w:r></w:del>'
        f'<w:ins w:id="2" w:author="A">{run("15")}</w:ins>'
        f"{run(' dana, vidi ')}"
        f'<w:hyperlink r:id="rId20">{run("propis", '<w:rStyle w:val="Hyperlink"/>')}'
        f"</w:hyperlink>{run(' i ')}"
        f"{field(' HYPERLINK "https://example.com/b" ', 'uputu')}"
        f"{run(', članak ')}{field(' REF _Ref1 \\h ', '5')}"
        f'<w:hyperlink w:anchor="_Ref1">{run(" gore")}</w:hyperlink></w:p>'
    )
    found = read(tmp_path, body, styles=STYLES, links={"rId20": "https://example.com/a"})
    paragraph = content(found)[0]
    assert paragraph.text == "Rok je 3015 dana, vidi propis i uputu, članak 5 gore"
    deleted, inserted = paragraph.runs[1:3]
    change = deleted.marks["deletion"]
    assert (deleted.text, inserted.text) == ("30", "15")
    assert change == {"id": change["id"], "author": "A"}
    assert inserted.marks == {"insertion": change}
    assert [(each.text, each.marks) for each in paragraph.runs if "link" in each.marks] == [
        ("propis", {"link": {"href": "https://example.com/a"}}),
        ("uputu", {"link": {"href": "https://example.com/b"}}),
    ]
    assert found.report["accepted"] == 0
    assert found.report["lost"] == {"fields": 1, "internalLinks": 1}


DATE = "2026-10-19T10:00:00Z"
ANA = f'w:author="Ana Horvat" w:date="{DATE}"'


def test_a_paragraph_inserted_or_deleted_whole_is_one_proposal_with_its_end(tmp_path):
    def ended(change: str, text: str, wrap: str = "") -> str:
        shown = f'<w:{wrap} w:id="9" {ANA}>{run(text)}</w:{wrap}>' if wrap else run(text)
        return f"<w:p><w:pPr><w:rPr>{change}</w:rPr></w:pPr>{shown}</w:p>"

    body = (
        ended(f'<w:ins w:id="1" {ANA}/>', "Novi stavak", "ins")
        + ended(f'<w:ins w:id="2" {ANA}/>', "", "")
        + p("Stari")
        + ended('<w:del w:id="3" w:author="Ivo" w:date="nije datum"/>', "Kraj")
    )
    new, empty, old, last = content(read(tmp_path, body))
    inserted = new.attrs["insertion"]
    assert inserted | {"id": "p"} == {"id": "p", "author": "Ana Horvat", "date": DATE}
    assert new.runs == [Run("Novi stavak", {"insertion": inserted})]
    assert empty.attrs == {"insertion": inserted}
    assert old.attrs == {}
    deleted = last.attrs["deletion"]
    assert deleted == {"id": deleted["id"], "author": "Ivo"} and deleted["id"] != inserted["id"]


def test_a_formatting_change_keeps_what_it_replaced_where_it_changed_ours(tmp_path):
    def changed(id: int, before: str) -> str:
        return f'<w:rPrChange w:id="{id}" {ANA}><w:rPr>{before}</w:rPr></w:rPrChange>'

    body = (
        f"<w:p>{run('Važno', '<w:b/>' + changed(1, '<w:i/>'))}"
        f"{run(' razmak', '<w:spacing w:val="20"/>' + changed(2, ''))}</w:p>"
        '<w:p><w:pPr><w:pStyle w:val="Quote1"/>'
        f'<w:pPrChange w:id="3" {ANA}><w:pPr><w:jc w:val="right"/></w:pPr></w:pPrChange>'
        f"</w:pPr>{run('Citat')}</w:p>"
        '<w:p><w:pPr><w:spacing w:after="0"/>'
        f'<w:pPrChange w:id="4" {ANA}><w:pPr/></w:pPrChange></w:pPr>{run("Isto")}</w:p>'
    )
    text, quote, same = content(read(tmp_path, body, styles=STYLES))
    [bold, spaced] = text.runs
    formatting = bold.marks["formatting"]
    assert bold.marks == {"strong": {}, "formatting": formatting}
    assert formatting["before"] == {"em": {}} and formatting["author"] == "Ana Horvat"
    assert spaced.marks == {}
    before = quote.attrs["formatting"]["before"]
    assert before == {"type": "paragraph", "attrs": {"align": "right"}}
    assert quote.attrs["style"] != before["attrs"].get("style")
    assert "formatting" not in same.attrs


def test_rows_pictures_page_breaks_and_notes_proposed_come_in_as_proposals(tmp_path):
    drawing = (
        '<w:r><w:drawing><wp:inline><wp:extent cx="100" cy="100"/>'
        '<wp:docPr id="1" name="Slika"/><a:graphic>'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic><pic:blipFill><a:blip r:embed="rId10"/></pic:blipFill></pic:pic>'
        "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
    )
    cell = f"<w:tc><w:p>{run('Stari')}</w:p></w:tc>"
    inserted = f'<w:tc><w:p><w:ins w:id="2" {ANA}>{run("Novi")}</w:ins></w:p></w:tc>'
    body = (
        '<w:tbl><w:tblGrid><w:gridCol w:w="9000"/></w:tblGrid>'
        f"<w:tr>{cell}</w:tr>"
        f'<w:tr><w:trPr><w:ins w:id="1" {ANA}/></w:trPr>{inserted}</w:tr></w:tbl>'
        f'<w:p>{run("Prije")}<w:ins w:id="3" w:author="Ivo">{drawing}'
        '<w:r><w:br w:type="page"/></w:r><w:r><w:footnoteReference w:id="1"/></w:r>'
        f"{run('Poslije')}</w:ins></w:p>"
    )
    footnotes = f'<w:footnote w:id="1"><w:p>{run("Izvor")}</w:p></w:footnote>'
    found = read(tmp_path, body, media={"rId10": ("image1.png", PNG)}, footnotes=footnotes)
    table, before, image, page_break, after = content(found)
    [proposal] = table.attrs["proposedRows"].values()
    assert list(table.attrs["proposedRows"]) == [table.grid.rows[1]]
    assert table.cells[1].blocks[0].runs == [Run("Novi", proposal)]
    ivo = image.attrs["insertion"]
    assert (before.text, ivo["author"]) == ("Prije", "Ivo")
    assert page_break.attrs == {"insertion": ivo}
    [note, text] = after.runs
    assert (note.proposed, note.runs) == ({"insertion": ivo}, [Run("Izvor")])
    assert text == Run("Poslije", {"insertion": ivo})
    assert "insertion" not in before.attrs and "insertion" not in after.attrs


def test_tracked_changes_a_proposal_cannot_hold_are_taken_as_word_shows_them(tmp_path):
    header = (
        f'<w:p><w:pPr><w:rPr><w:ins w:id="1" {ANA}/></w:rPr></w:pPr>'
        f'<w:ins w:id="2" {ANA}>{run("Novo")}</w:ins>'
        f'<w:del w:id="3" {ANA}><w:r><w:delText>Staro</w:delText></w:r></w:del></w:p>'
    )
    body = (
        '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>'
        f'<w:tblPrChange w:id="4" {ANA}><w:tblPr/></w:tblPrChange></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="9000"/></w:tblGrid>'
        f"<w:tr><w:tc><w:p>{run('Ćelija')}</w:p></w:tc></w:tr></w:tbl>" + p("Tekst")
    )
    found = read(
        tmp_path,
        body,
        section=section(named("header", "default", "header")),
        header=header,
    )
    assert [block.runs for block in found.parts["header"]] == [[Run("Novo")]]
    assert found.parts["header"][0].attrs == {}
    assert found.report["accepted"] == 4


TOC = (
    '<w:p><w:pPr><w:pStyle w:val="TOC1"/></w:pPr><w:r><w:fldChar w:fldCharType="begin"/>'
    '</w:r><w:r><w:instrText> TOC \\o "1-2" \\h </w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    f"{run('Uvod 1')}</w:p>"
    f'<w:p><w:pPr><w:pStyle w:val="TOC1"/></w:pPr>{run("Predmet 2")}'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
)


def test_a_table_of_contents_becomes_ours_below_its_heading(tmp_path):
    found = read(tmp_path, p("Sadržaj", "TOCHeading") + TOC + p("Tekst"), styles=STYLES)
    shown = [(block.type, block.attrs, block.text) for block in content(found)]
    assert shown == [
        ("paragraph", {"style": "TOCHeading", "indent": 0.76, "firstLine": -0.76}, "Sadržaj"),
        ("contents", {"depth": 2}, ""),
        ("paragraph", {}, "Tekst"),
    ]
    assert found.report["lost"] == {}


def test_a_table_of_contents_in_a_layout_table_stays_in_its_cell(tmp_path):
    grid = '<w:tblGrid><w:gridCol w:w="9000"/></w:tblGrid>'
    body = f"<w:tbl>{grid}<w:tr><w:tc>{TOC}</w:tc></w:tr></w:tbl>"
    [table] = content(read(tmp_path, body, styles=STYLES))
    assert [(block.type, block.attrs) for block in table.cells[0].blocks] == [
        ("contents", {"depth": 2})
    ]


def test_each_section_after_the_first_follows_a_break_that_keeps_what_it_sets_itself(tmp_path):
    header = f"<w:p>{run('Stranica ')}{field(' PAGE ', '3')}{run(' od ')}"
    header += '<w:fldSimple w:instr=" NUMPAGES "><w:r><w:t>9</w:t></w:r></w:fldSimple></w:p>'
    footer = f"<w:p>{field('PAGE', None)}{field('AUTHOR', 'Ana')}</w:p>"
    first = named("header", "first", "header2")
    body = (
        p("Ugovor", "Heading1")
        + ending("Tekst", section(named("header", "default", "header") + first, first=True))
        + p("Prilog", "Heading1")
        + ending("Tablica", section(named("footer", "default", "footer"), landscape=True))
        + p("Zaključak", "Heading1")
    )
    found = read(
        tmp_path,
        body,
        section=section(first=True),
        styles=STYLES,
        header=header,
        header2=f"<w:p>{run('Naslovnica')}</w:p><w:p/>",
        footer=footer,
    )
    a4 = {"width": 21.0, "height": 29.7, "top": 2.5, "right": 2.5, "bottom": 2.5, "left": 2.5}
    a4 |= {"header": 1.25, "footer": 1.25, "start": None}
    assert found.page == {**a4, "firstPage": True}
    paged = [[Run("Stranica "), Field("page"), Run(" od "), Field("pages")]]
    assert {name: [block.runs for block in part] for name, part in found.parts.items()} == {
        "header": paged,
        "headerFirst": [[Run("Naslovnica")], []],
    }
    [tab] = found.tabs
    assert (tab.title, tab.page, tab.parts) == ("", None, None)
    assert [block.text or block.type for block in tab.blocks] == [
        "Ugovor",
        "Tekst",
        "sectionBreak",
        "Prilog",
        "Tablica",
        "sectionBreak",
        "Zaključak",
    ]
    attached, last = [block.id for block in tab.blocks if block.type == "sectionBreak"]
    page, parts = tab.sections[attached]
    assert page == {**a4, "width": 29.7, "height": 21.0, "firstPage": False}
    assert {name: [block.runs for block in part] for name, part in parts.items()} == {
        "footer": [[Field("page"), Run("Ana")]],
    }
    assert tab.sections[last] == ({**a4, "firstPage": True}, {})
    assert found.report["lost"] == {"fields": 1}


def test_a_section_names_a_header_of_its_own_and_one_going_on_from_the_page_before_does_not_break(
    tmp_path,
):
    body = ending("Prvi", section(named("header", "default", "header"))) + p("Drugi")
    last = section(named("header", "default", "header2") + named("header", "even", "header"))
    found = read(
        tmp_path,
        body,
        section=last,
        header=f"<w:p>{run('Zaglavlje')}</w:p>",
        header2=f"<w:p>{run('Drugo zaglavlje')}</w:p>",
        settings="<w:evenAndOddHeaders/>",
    )
    [tab] = found.tabs
    assert [block.text or block.type for block in tab.blocks] == ["Prvi", "sectionBreak", "Drugi"]
    assert [block.text for block in found.parts["header"]] == ["Zaglavlje"]
    [(page, parts)] = tab.sections.values()
    assert page is None
    assert {name: [block.text for block in part] for name, part in parts.items()} == {
        "header": ["Drugo zaglavlje"]
    }
    assert found.report["lost"] == {"evenHeaders": 1}
    going_on = section(named("header", "default", "header"))
    going_on = going_on.replace("<w:sectPr>", '<w:sectPr><w:type w:val="continuous"/>')
    found = read(tmp_path, body, section=going_on, header=f"<w:p>{run('Zaglavlje')}</w:p>")
    [tab] = found.tabs
    assert ([block.text for block in tab.blocks], tab.sections) == (["Prvi", "Drugi"], {})


def test_a_text_box_comes_after_its_paragraph(tmp_path):
    box = (
        '<w:r><w:pict><v:shape xmlns:v="urn:schemas-microsoft-com:vml"><v:textbox>'
        f"<w:txbxContent>{p('U okviru')}</w:txbxContent></v:textbox></v:shape></w:pict></w:r>"
    )
    found = read(tmp_path, f"<w:p>{run('Prije')}{box}</w:p>")
    assert [block.text for block in in_order(content(found))] == ["Prije", "U okviru"]
    assert found.report["lost"] == {"textBoxes": 1}


def test_a_horizontal_line_comes_over_drawn_or_as_a_bordered_empty_paragraph(tmp_path):
    line = (
        '<w:r><w:pict><v:rect xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" style="width:0;height:1.5pt" '
        'o:hralign="center" o:hrstd="t" o:hr="t"/></w:pict></w:r>'
    )
    found = read(
        tmp_path,
        f"<w:p>{line}</w:p>"
        + p("Između")
        + p(props=border("bottom"))
        + p("Kraj")
        + f"<w:tbl><w:tr><w:tc><w:p>{line}</w:p></w:tc></w:tr></w:tbl>",
    )
    blocks = content(found)
    assert [block.type for block in blocks] == [
        *("horizontalRule", "paragraph", "horizontalRule", "paragraph", "table"),
    ]
    assert found.report["lost"] == {"shapes": 1}


def border(*sides: str) -> str:
    drawn = "".join(f'<w:{side} w:val="single" w:sz="6" w:space="1"/>' for side in sides)
    return f"<w:pBdr>{drawn}</w:pBdr>"


def test_paragraph_borders_come_over_as_lines_drawn_as_word_draws_them(tmp_path):
    ruled = (
        '<w:style w:type="paragraph" w:customStyle="1" w:styleId="Ruled"><w:name w:val="Crtano"/>'
        f'<w:basedOn w:val="Normal"/><w:pPr>{border("bottom")}</w:pPr></w:style>'
    )
    found = read(
        tmp_path,
        p("Naslov", "Ruled")
        + p("Prvi", props=border("top", "bottom"))
        + p("Drugi", props=border("top", "bottom"))
        + p("Sam")
        + p("Gore", props=border("top", "bottom", "between"))
        + p("Dolje", props=border("top", "bottom", "between"))
        + p("Bez", "Ruled", props='<w:pBdr><w:bottom w:val="nil"/></w:pBdr>')
        + p("Okvir", props=border("top", "left", "bottom", "right"))
        + f"<w:tbl><w:tr><w:tc>{p('Ćelija', props=border('bottom'))}</w:tc></w:tr></w:tbl>",
        section=section(
            named("header", "default", "header") + named("footer", "default", "footer")
        ),
        header=p("Tvrtka d.o.o.", props=border("bottom")) + p("Adresa", props=border("bottom")),
        footer=p("Stranica", props=border("top")),
        styles=STYLES + ruled,
    )
    shown = [block.text or block.type for block in content(found)]
    rule = "horizontalRule"
    assert shown == [
        *("Naslov", rule, rule, "Prvi", "Drugi", rule, "Sam"),
        *(rule, "Gore", rule, "Dolje", rule, "Bez", rule, "Okvir", rule, "table"),
    ]
    assert [block.text or block.type for block in found.parts["header"]] == [
        *("Tvrtka d.o.o.", "Adresa", rule),
    ]
    assert [block.text or block.type for block in found.parts["footer"]] == [rule, "Stranica"]
    assert found.report["lost"] == {"paragraphBorders": 2}


def test_what_is_not_a_word_file_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "file.docx"
    path.write_bytes(b"not a zip")
    with pytest.raises(reading.Unreadable):
        docx.read(path, "hr")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<broken")
    with pytest.raises(reading.Unreadable):
        docx.read(path, "hr")
    path.write_bytes(word_file(p("Tekst")))
    monkeypatch.setattr(office, "LARGEST", 100)
    with pytest.raises(reading.TooLarge):
        docx.read(path, "hr")
