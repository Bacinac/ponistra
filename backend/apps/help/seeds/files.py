"""The office files the company's documents are imported from, written as Word, Excel and
PowerPoint write them, and the PDFs it keeps as they are."""

import io
import zipfile
from xml.sax.saxutils import escape

import pikepdf
from docx import Document
from docx.shared import Cm
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference

from .company import picture


def _saved(made) -> bytes:
    written = io.BytesIO()
    made.save(written)
    return written.getvalue()


PROPOSAL = {
    "title": ("Ponuda za uređenje ureda", "Office fit-out proposal"),
    "client": (
        "Za: Meridian d.o.o., Trnjanska cesta 500, Zagreb",
        "For: Meridian Ltd, 500 Trnjanska Street, Zagreb",
    ),
    "scope": ("Opseg radova", "Scope of work"),
    "scope_text": (
        (
            "Ponuda obuhvaća projekt, nabavu namještaja i montažu u prostoru od 240 m² na "
            "trećem katu, s dvije sale za sastanke i otvorenim uredom za 28 radnih mjesta.",
            "The proposal covers the design, the furniture and the fitting of 240 m² on the "
            "third floor, with two meeting rooms and an open office for 28 desks.",
        ),
        (
            "Radovi traju šest tjedana od potpisa ugovora, a ured za to vrijeme ostaje otvoren: "
            "bučni radovi idu poslije 17 sati i subotom.",
            "The work takes six weeks from the signing of the contract, and the office stays "
            "open: the noisy work is done after 5 pm and on Saturdays.",
        ),
    ),
    "concept": ("Koncept", "Concept"),
    "concept_text": (
        "Svijetlo drvo, prirodni materijali i biljke; sala za sastanke kao na slici, s ekranom "
        "i akustičnim panelima.",
        "Light wood, natural materials and plants; the meeting room as in the picture, with a "
        "screen and acoustic panels.",
    ),
    "price": ("Cijena", "Price"),
    "rows": (
        (("Stavka", "Item"), ("Iznos (EUR)", "Amount (EUR)")),
        (("Projekt i vizualizacije", "Design and renderings"), 4200),
        (("Namještaj", "Furniture"), 18650),
        (("Rasvjeta", "Lighting"), 3900),
        (("Montaža", "Fitting"), 5300),
        (("Ukupno bez PDV-a", "Total before VAT"), 32050),
    ),
    "schedule": ("Rokovi", "Schedule"),
    "steps": (
        (
            "Projekt i odabir materijala, 1. i 2. tjedan",
            "Design and choice of materials, weeks 1–2",
        ),
        ("Nabava i isporuka, 3. i 4. tjedan", "Purchase and delivery, weeks 3–4"),
        ("Montaža i primopredaja, 5. i 6. tjedan", "Fitting and handover, weeks 5–6"),
    ),
}

# Who remarks on which words of the proposal, and what.
REMARKS = (
    (
        "concept_text",
        "Ana Kovač",
        (
            "Predlažem hrast umjesto bukve, bolje se slaže s parketom.",
            "I suggest oak instead of beech; it goes better with the parquet.",
        ),
    ),
    (
        "price",
        "Marta Jurić",
        (
            "Montaža je 300 EUR niža ako dostava ide istim kamionom.",
            "The fitting is 300 EUR less if the delivery comes on the same lorry.",
        ),
    ),
)


def proposal(say) -> bytes:
    made = Document()
    made.add_heading(say(*PROPOSAL["title"]), level=0)
    made.add_paragraph(say(*PROPOSAL["client"]))
    made.add_heading(say(*PROPOSAL["scope"]), level=1)
    for paragraph in PROPOSAL["scope_text"]:
        made.add_paragraph(say(*paragraph))
    made.add_heading(say(*PROPOSAL["concept"]), level=1)
    concept = made.add_paragraph(say(*PROPOSAL["concept_text"]))
    made.add_picture(io.BytesIO(picture("meeting-room.jpg")), width=Cm(15))
    price = made.add_heading(say(*PROPOSAL["price"]), level=1)
    rows = PROPOSAL["rows"]
    table = made.add_table(rows=len(rows), cols=2)
    table.style = "Light Grid Accent 1"
    for at, (label, amount) in enumerate(rows):
        table.cell(at, 0).text = say(*label)
        table.cell(at, 1).text = say(*amount) if at == 0 else f"{amount:,}".replace(",", ".")
    made.add_heading(say(*PROPOSAL["schedule"]), level=1)
    for step in PROPOSAL["steps"]:
        made.add_paragraph(say(*step), style="List Number")
    remarked = {"concept_text": concept.runs, "price": price.runs}
    for key, author, words in REMARKS:
        initials = "".join(part[0] for part in author.split())
        made.add_comment(remarked[key], text=say(*words), author=author, initials=initials)
    return _saved(made)


def minutes(say, people: list[str], points: list[tuple[str, str]]) -> bytes:
    made = Document()
    made.add_heading(say("Zapisnik sa sastanka", "Meeting minutes"), level=0)
    made.add_paragraph(f"{say('Prisutni', 'Present')}: {', '.join(people)}")
    made.add_heading(say("Zaključci", "Decisions"), level=1)
    for point in points:
        made.add_paragraph(say(*point), style="List Bullet")
    return _saved(made)


BUDGET = (
    (("Projekt i vizualizacije", "Design and renderings"), 4200),
    (("Namještaj", "Furniture"), 18650),
    (("Rasvjeta", "Lighting"), 3900),
    (("Montaža", "Fitting"), 5300),
    (("Biljke i dekoracija", "Plants and decoration"), 1250),
)
MONTHS = (("Studeni", "November"), ("Prosinac", "December"), ("Siječanj", "January"))
PAID = ((8000, 6200, 1450), (2500, 9800, 6350), (0, 3900, 0), (0, 2650, 2650), (0, 0, 1250))


def budget(say) -> bytes:
    book = Workbook()
    costs = book.active
    costs.title = say("Troškovi", "Costs")
    costs.append(
        [
            say("Stavka", "Item"),
            say("Iznos (EUR)", "Amount (EUR)"),
            say("PDV 25 %", "VAT 25%"),
            say("S PDV-om", "With VAT"),
        ]
    )
    for at, (label, amount) in enumerate(BUDGET, 2):
        costs.append([say(*label), amount, f"=B{at}*0.25", f"=B{at}+C{at}"])
    last = len(BUDGET) + 1
    costs.append(
        [say("Ukupno", "Total"), f"=SUM(B2:B{last})", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})"]
    )
    costs.column_dimensions["A"].width = 28
    for column in "BCD":
        costs.column_dimensions[column].width = 14
        for row in range(2, last + 2):
            costs[f"{column}{row}"].number_format = "#,##0.00"
    payments = book.create_sheet(say("Plaćanja", "Payments"))
    payments.append([say("Stavka", "Item"), *(say(*month) for month in MONTHS)])
    for (label, _), paid in zip(BUDGET, PAID, strict=True):
        payments.append([say(*label), *paid])
    payments.append([say("Ukupno", "Total"), *(f"=SUM({c}2:{c}{last})" for c in "BCD")])
    payments.column_dimensions["A"].width = 28
    chart = BarChart()
    chart.type = "col"
    chart.grouping = "stacked"
    chart.overlap = 100
    chart.title = say("Plaćanja po mjesecima", "Payments by month")
    chart.y_axis.title = "EUR"
    chart.add_data(
        Reference(payments, min_col=1, max_col=4, min_row=2, max_row=last),
        from_rows=True,
        titles_from_data=True,
    )
    chart.set_categories(Reference(payments, min_col=2, max_col=4, min_row=1))
    chart.width, chart.height = 16, 8
    payments.add_chart(chart, "F2")
    return _saved(book)


NS = (
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
)
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ML = "application/vnd.openxmlformats-officedocument.presentationml"
EMU = 12700
WIDE, HIGH = 12192000, 6858000
INK, PETROL, SAGE, PAPER = "1F2A2C", "2F6B6E", "8A9A5B", "F5F3EE"

THEME = f"""<a:theme {NS} name="Lipa"><a:themeElements><a:clrScheme name="Lipa">
<a:dk1><a:srgbClr val="{INK}"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
<a:dk2><a:srgbClr val="{PETROL}"/></a:dk2><a:lt2><a:srgbClr val="{PAPER}"/></a:lt2>
<a:accent1><a:srgbClr val="{PETROL}"/></a:accent1><a:accent2><a:srgbClr val="{SAGE}"/></a:accent2>
<a:accent3><a:srgbClr val="B5654A"/></a:accent3><a:accent4><a:srgbClr val="A07D3B"/></a:accent4>
<a:accent5><a:srgbClr val="5B6C8F"/></a:accent5><a:accent6><a:srgbClr val="6E5B8A"/></a:accent6>
<a:hlink><a:srgbClr val="{PETROL}"/></a:hlink><a:folHlink><a:srgbClr val="6E5B8A"/></a:folHlink>
</a:clrScheme><a:fontScheme name="Lipa"><a:majorFont><a:latin typeface="Georgia"/></a:majorFont>
<a:minorFont><a:latin typeface="Arial"/></a:minorFont></a:fontScheme><a:fmtScheme name="Lipa">
<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill>
<a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
</a:fillStyleLst><a:lnStyleLst><a:ln w="6350"/><a:ln w="12700"/><a:ln w="19050"/></a:lnStyleLst>
<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/>
</a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill>
<a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>"""


def _frame(x: float, y: float, w: float, h: float) -> str:
    return (
        f'<a:xfrm><a:off x="{int(x * EMU)}" y="{int(y * EMU)}"/>'
        f'<a:ext cx="{int(w * EMU)}" cy="{int(h * EMU)}"/></a:xfrm>'
    )


def _text(
    paragraphs: list[str], size: int, colour: str, bold: bool = False, bullets: bool = False
) -> str:
    fill = f'<a:solidFill><a:srgbClr val="{colour}"/></a:solidFill>'
    look = f'<a:rPr lang="en-GB" sz="{size * 100}" b="{int(bold)}">{fill}</a:rPr>'
    mark = (
        '<a:pPr marL="285750" indent="-285750"><a:buChar char="•"/></a:pPr>'
        if bullets
        else "<a:pPr><a:buNone/></a:pPr>"
    )
    return "".join(
        f"<a:p>{mark}<a:r>{look}<a:t>{escape(each)}</a:t></a:r></a:p>" for each in paragraphs
    )


def _box(number: int, place: str, body: str = "", holder: str = "") -> str:
    """A text box, or the placeholder the holder names, which a slide fills and a layout
    places."""
    kind = "<p:cNvSpPr/>" if holder else '<p:cNvSpPr txBox="1"/>'
    text = body or "<a:p><a:endParaRPr/></a:p>"
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{number}" name="Text {number}"/>{kind}'
        f"<p:nvPr>{holder}</p:nvPr></p:nvSpPr><p:spPr>{place}"
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr><p:txBody>'
        f'<a:bodyPr wrap="square" lIns="0" rIns="0"/><a:lstStyle/>{text}</p:txBody></p:sp>'
    )


def _image(number: int, rid: str, place: str, alt: str) -> str:
    return (
        f'<p:pic><p:nvPicPr><p:cNvPr id="{number}" name="Picture {number}" descr="{escape(alt)}"/>'
        f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
        f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        f'<p:spPr>{place}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
    )


def _tree(*shapes: str, background: str = "", name: str = "") -> str:
    filled = (
        f'<p:bg><p:bgPr><a:solidFill><a:srgbClr val="{background}"/></a:solidFill>'
        "<a:effectLst/></p:bgPr></p:bg>"
        if background
        else ""
    )
    named = f' name="{escape(name)}"' if name else ""
    return (
        f'<p:cSld{named}>{filled}<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
        f"<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>{''.join(shapes)}</p:spTree></p:cSld>"
    )


def _rels(relations: list[tuple[str, str, str]]) -> str:
    items = "".join(
        f'<Relationship Id="{rid}" Type="{DOC}/{kind}" Target="{target}"/>'
        for rid, kind, target in relations
    )
    return f'<Relationships xmlns="{RELS}">{items}</Relationships>'


TITLE = _frame(48, 36, 864, 64)
LEFT, RIGHT, WHOLE = (
    _frame(48, 120, 420, 373),
    _frame(492, 120, 420, 373),
    _frame(48, 120, 864, 373),
)
HOLDERS = {
    "title": '<p:ph type="title"/>',
    "body": '<p:ph idx="1"/>',
    "second": '<p:ph idx="2"/>',
}

# Each layout's name, its type and its placeholders: a title slide, two contents side by side and
# a title with one content.
LAYOUTS = (
    (
        "Naslovni slajd",
        "title",
        (
            _box(2, _frame(64, 190, 820, 90), holder='<p:ph type="ctrTitle"/>'),
            _box(3, _frame(64, 290, 820, 40), holder='<p:ph type="subTitle" idx="1"/>'),
        ),
    ),
    (
        "Dva sadržaja",
        "twoObj",
        (
            _box(2, TITLE, holder=HOLDERS["title"]),
            _box(3, LEFT, holder=HOLDERS["body"]),
            _box(4, RIGHT, holder=HOLDERS["second"]),
        ),
    ),
    (
        "Naslov i sadržaj",
        "obj",
        (_box(2, TITLE, holder=HOLDERS["title"]), _box(3, WHOLE, holder=HOLDERS["body"])),
    ),
)


def _slides(say) -> list[tuple[int, str, dict[str, bytes], str]]:
    """Each slide's layout, its shapes, its pictures by relation id and its speaker notes; the
    pictures stand in the boxes of its layout, so that they keep their places."""

    def title(words: str) -> str:
        return _box(2, TITLE, _text([words], 34, PETROL, True), HOLDERS["title"])

    def points(number: int, place: str, *said: tuple[str, str], size: int = 22) -> str:
        return _box(number, place, _text([say(*each) for each in said], size, INK, bullets=True))

    return [
        (
            1,
            _tree(
                _box(
                    2,
                    _frame(64, 190, 820, 90),
                    _text(
                        [say("Novi ured za Meridian", "A new office for Meridian")],
                        44,
                        "FFFFFF",
                        True,
                    ),
                    '<p:ph type="ctrTitle"/>',
                ),
                _box(
                    3,
                    _frame(64, 290, 820, 40),
                    _text(
                        [say("Lipa Studio · prijedlog uređenja", "Lipa Studio · fit-out proposal")],
                        20,
                        "E8EFE9",
                    ),
                    '<p:ph type="subTitle" idx="1"/>',
                ),
                background=PETROL,
            ),
            {},
            say(
                "Pozdrav i kratko predstavljanje tima.",
                "Welcome and a short introduction of the team.",
            ),
        ),
        (
            2,
            _tree(
                title(say("Što predlažemo", "What we propose")),
                points(
                    3,
                    _frame(48, 120, 420, 340),
                    ("Otvoreni ured za 28 radnih mjesta", "An open office for 28 desks"),
                    ("Dvije sale za sastanke s ekranom", "Two meeting rooms with a screen"),
                    ("Tihe kabine za pozive", "Quiet booths for calls"),
                    (
                        "Svijetlo drvo, biljke i mekana rasvjeta",
                        "Light wood, plants and soft lighting",
                    ),
                ),
                _image(
                    4, "rIdP1", _frame(500, 120, 412, 309), say("Sala za sastanke", "Meeting room")
                ),
            ),
            {"rIdP1": picture("meeting-room.jpg")},
            say(
                "Naglasiti da ured ostaje otvoren tijekom radova.",
                "Stress that the office stays open during the work.",
            ),
        ),
        (
            2,
            _tree(
                title(say("Prostor za odmor", "A place to rest")),
                _image(3, "rIdP1", _frame(48, 120, 420, 280), say("Dnevni boravak", "Living room")),
                points(
                    4,
                    _frame(492, 140, 420, 300),
                    ("Kauči i niski stolići uz prozor", "Sofas and low tables by the window"),
                    ("Biljke u svakoj zoni", "Plants in every zone"),
                    size=20,
                ),
            ),
            {"rIdP1": picture("living-room.jpg")},
            "",
        ),
        (
            2,
            _tree(
                title(say("Materijali", "Materials")),
                _image(3, "rIdP1", _frame(48, 120, 420, 315), say("Hrastov parket", "Oak parquet")),
                _image(4, "rIdP2", _frame(492, 120, 420, 315), say("Uzorci drva", "Wood samples")),
            ),
            {"rIdP1": picture("parquet.jpg"), "rIdP2": picture("wood-samples.jpg")},
            say(
                "Hrastov parket, zaštićen uljem; uzorci stižu u utorak.",
                "Oiled oak parquet; the samples arrive on Tuesday.",
            ),
        ),
        (
            2,
            _tree(
                title(say("Rasvjeta", "Lighting")),
                _image(
                    3,
                    "rIdP1",
                    _frame(48, 120, 420, 315),
                    say("Viseće svjetiljke", "Pendant lights"),
                ),
                points(
                    4,
                    _frame(492, 130, 420, 300),
                    ("Viseće svjetiljke iznad stolova", "Pendant lights above the tables"),
                    ("Topla svjetlost 3000 K", "Warm light at 3000 K"),
                    ("Prigušivanje po zonama", "Dimming by zone"),
                    size=20,
                ),
            ),
            {"rIdP1": picture("pendant-lights.jpg")},
            "",
        ),
        (
            3,
            _tree(
                title(say("Rokovi i cijena", "Schedule and price")),
                points(
                    3,
                    _frame(48, 120, 864, 260),
                    ("1.–2. tjedan: projekt i materijali", "Weeks 1–2: design and materials"),
                    ("3.–4. tjedan: nabava i isporuka", "Weeks 3–4: purchase and delivery"),
                    ("5.–6. tjedan: montaža i primopredaja", "Weeks 5–6: fitting and handover"),
                    ("Ukupno 32.050 EUR bez PDV-a", "In all 32,050 EUR before VAT"),
                    size=24,
                ),
            ),
            {},
            say("Cijena vrijedi 30 dana.", "The price is valid for 30 days."),
        ),
    ]


def deck(say) -> bytes:
    files: dict[str, str | bytes] = {"ppt/theme/theme1.xml": THEME}
    types = [
        ("/ppt/presentation.xml", f"{ML}.presentation.main+xml"),
        ("/ppt/slideMasters/slideMaster1.xml", f"{ML}.slideMaster+xml"),
        ("/ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
    ]
    listed = "".join(
        f'<p:sldLayoutId id="{2147483648 + at}" r:id="rIdL{at}"/>'
        for at in range(1, len(LAYOUTS) + 1)
    )
    colours = (
        '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
        'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" '
        'folHlink="folHlink"/>'
    )
    files["ppt/slideMasters/slideMaster1.xml"] = (
        f"<p:sldMaster {NS}>{_tree(background=PAPER)}{colours}"
        f"<p:sldLayoutIdLst>{listed}</p:sldLayoutIdLst></p:sldMaster>"
    )
    notes_body = '<p:ph type="body" idx="1"/>'
    files["ppt/notesMasters/notesMaster1.xml"] = (
        f"<p:notesMaster {NS}>{_tree(_box(2, _frame(36, 360, 468, 300), holder=notes_body))}"
        f"{colours}</p:notesMaster>"
    )
    files["ppt/notesMasters/_rels/notesMaster1.xml.rels"] = _rels(
        [("rId1", "theme", "../theme/theme1.xml")]
    )
    types.append(("/ppt/notesMasters/notesMaster1.xml", f"{ML}.notesMaster+xml"))
    master = [("rIdT", "theme", "../theme/theme1.xml")]
    for at, (name, kind, holders) in enumerate(LAYOUTS, 1):
        files[f"ppt/slideLayouts/slideLayout{at}.xml"] = (
            f'<p:sldLayout {NS} type="{kind}">{_tree(*holders, name=name)}</p:sldLayout>'
        )
        files[f"ppt/slideLayouts/_rels/slideLayout{at}.xml.rels"] = _rels(
            [("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")]
        )
        types.append((f"/ppt/slideLayouts/slideLayout{at}.xml", f"{ML}.slideLayout+xml"))
        master.append((f"rIdL{at}", "slideLayout", f"../slideLayouts/slideLayout{at}.xml"))
    files["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = _rels(master)
    relations = [
        ("rId1", "slideMaster", "slideMasters/slideMaster1.xml"),
        ("rIdNM", "notesMaster", "notesMasters/notesMaster1.xml"),
    ]
    slides = []
    for at, (layout, tree, pictures, notes) in enumerate(_slides(say), 1):
        files[f"ppt/slides/slide{at}.xml"] = f"<p:sld {NS}>{tree}</p:sld>"
        own = [("rId1", "slideLayout", f"../slideLayouts/slideLayout{layout}.xml")]
        for rid, data in pictures.items():
            files[f"ppt/media/slide{at}{rid}.jpg"] = data
            own.append((rid, "image", f"../media/slide{at}{rid}.jpg"))
        if notes:
            said = _box(2, _frame(36, 360, 468, 300), _text([notes], 12, INK), notes_body)
            files[f"ppt/notesSlides/notesSlide{at}.xml"] = f"<p:notes {NS}>{_tree(said)}</p:notes>"
            files[f"ppt/notesSlides/_rels/notesSlide{at}.xml.rels"] = _rels(
                [
                    ("rId1", "slide", f"../slides/slide{at}.xml"),
                    ("rId2", "notesMaster", "../notesMasters/notesMaster1.xml"),
                ]
            )
            own.append(("rIdN", "notesSlide", f"../notesSlides/notesSlide{at}.xml"))
            types.append((f"/ppt/notesSlides/notesSlide{at}.xml", f"{ML}.notesSlide+xml"))
        files[f"ppt/slides/_rels/slide{at}.xml.rels"] = _rels(own)
        types.append((f"/ppt/slides/slide{at}.xml", f"{ML}.slide+xml"))
        relations.append((f"rIdS{at}", "slide", f"slides/slide{at}.xml"))
        slides.append(f'<p:sldId id="{255 + at}" r:id="rIdS{at}"/>')
    files["ppt/presentation.xml"] = (
        f'<p:presentation {NS}><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/>'
        '</p:sldMasterIdLst><p:notesMasterIdLst><p:notesMasterId r:id="rIdNM"/>'
        f"</p:notesMasterIdLst><p:sldIdLst>{''.join(slides)}</p:sldIdLst>"
        f'<p:sldSz cx="{WIDE}" cy="{HIGH}"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
    )
    files["ppt/_rels/presentation.xml.rels"] = _rels(relations)
    files["_rels/.rels"] = _rels([("rId1", "officeDocument", "ppt/presentation.xml")])
    overrides = "".join(
        f'<Override PartName="{name}" ContentType="{kind}"/>' for name, kind in types
    )
    files["[Content_Types].xml"] = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Default Extension="jpg" ContentType="image/jpeg"/>{overrides}</Types>'
    )
    written = io.BytesIO()
    with zipfile.ZipFile(written, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return written.getvalue()


# Helvetica's own glyphs for the letters WinAnsi leaves out, by the codes they take here.
LETTERS = {"Č": "Ccaron", "č": "ccaron", "Ć": "Cacute", "ć": "cacute", "Đ": "Dcroat", "đ": "dcroat"}
CODES = {letter: 0x80 + at for at, letter in enumerate(LETTERS)}


def _encoded(text: str) -> bytes:
    return b"".join(
        bytes([CODES[each]]) if each in CODES else each.encode("cp1252") for each in text
    )


def _escaped(text: str) -> bytes:
    return _encoded(text).replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def pdf(pages: list[list[tuple[int, str]]]) -> bytes:
    """A PDF of A4 pages, each a list of lines in their sizes, written in Helvetica."""
    made = pikepdf.new()
    differences = pikepdf.Array([0x80, *(pikepdf.Name(f"/{name}") for name in LETTERS.values())])
    font = made.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Font,
            Subtype=pikepdf.Name.Type1,
            BaseFont=pikepdf.Name.Helvetica,
            Encoding=pikepdf.Dictionary(
                Type=pikepdf.Name.Encoding,
                BaseEncoding=pikepdf.Name.WinAnsiEncoding,
                Differences=differences,
            ),
        )
    )
    for lines in pages:
        stream = b"BT 72 770 Td"
        for size, line in lines:
            stream += b" /F1 %d Tf 0 -%d Td (%s) Tj" % (size, round(size * 1.6), _escaped(line))
        stream += b" ET"
        page = pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, 595, 842],
            Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)),
            Contents=made.make_stream(stream),
        )
        made.pages.append(pikepdf.Page(page))
    return _saved(made)
