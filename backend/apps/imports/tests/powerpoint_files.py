"""Small PowerPoint files, written part by part as PowerPoint writes them."""

import io
import zipfile

from .test_docx import PNG

NS = (
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
)
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ML = "application/vnd.openxmlformats-officedocument.presentationml"
SECTIONS = "{521415D9-36F7-43E2-AB2F-B90AF26B5E84}"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
CM = 360000

THEME = f"""<a:theme {NS} name="Office"><a:themeElements>
<a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>
<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F3864"/></a:dk2>
<a:lt2><a:srgbClr val="E7E6E6"/></a:lt2><a:accent1><a:srgbClr val="4472C4"/></a:accent1>
<a:accent2><a:srgbClr val="ED7D31"/></a:accent2><a:accent3><a:srgbClr val="A5A5A5"/></a:accent3>
<a:accent4><a:srgbClr val="FFC000"/></a:accent4><a:accent5><a:srgbClr val="5B9BD5"/></a:accent5>
<a:accent6><a:srgbClr val="70AD47"/></a:accent6><a:hlink><a:srgbClr val="0563C1"/></a:hlink>
<a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>
<a:fontScheme name="Office"><a:majorFont><a:latin typeface="Calibri Light"/></a:majorFont>
<a:minorFont><a:latin typeface="Calibri"/></a:minorFont></a:fontScheme>
<a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
<a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/>
</a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="6350"/><a:ln w="12700"/><a:ln w="19050"/>
</a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle>
<a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst>
<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:solidFill>
<a:schemeClr val="phClr"/></a:solidFill><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>"""


def frame(x: float, y: float, w: float, h: float, flips: str = "") -> str:
    return (
        f'<a:xfrm{flips}><a:off x="{round(x * CM)}" y="{round(y * CM)}"/>'
        f'<a:ext cx="{round(w * CM)}" cy="{round(h * CM)}"/></a:xfrm>'
    )


def run(text: str, props: str = "", link: str = "") -> str:
    click = f'<a:hlinkClick r:id="{link}"/>' if link else ""
    return f'<a:r><a:rPr lang="hr-HR"{props}>{click}</a:rPr><a:t>{text}</a:t></a:r>'


def para(*runs: str, props: str = "") -> str:
    return f"<a:p>{props}{''.join(runs)}</a:p>"


def body(*paragraphs: str, styles: str = "", anchor: str = "") -> str:
    held = f' anchor="{anchor}"' if anchor else ""
    return (
        f"<p:txBody><a:bodyPr{held}/><a:lstStyle>{styles}</a:lstStyle>"
        f"{''.join(paragraphs)}</p:txBody>"
    )


def holder(number: int, type: str | None, idx: int | None, place: str = "", text: str = "") -> str:
    kind = f' type="{type}"' if type else ""
    index = f' idx="{idx}"' if idx is not None else ""
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{number}" name="Placeholder {number}"/><p:cNvSpPr/>'
        f"<p:nvPr><p:ph{kind}{index}/></p:nvPr></p:nvSpPr><p:spPr>{place}</p:spPr>"
        f"{text or body(para())}</p:sp>"
    )


def shape(number: int, place: str, geometry: str = "rect", fill: str = "", text: str = "") -> str:
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{number}" name="Shape {number}"/><p:cNvSpPr/><p:nvPr/>'
        f'</p:nvSpPr><p:spPr>{place}<a:prstGeom prst="{geometry}"><a:avLst/></a:prstGeom>'
        f"{fill}</p:spPr>{text}</p:sp>"
    )


def line(number: int, place: str) -> str:
    return (
        f'<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="{number}" name="Line {number}"/><p:cNvCxnSpPr/>'
        f'<p:nvPr/></p:nvCxnSpPr><p:spPr>{place}<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        f'<a:ln w="25400"><a:solidFill><a:schemeClr val="accent2"/></a:solidFill></a:ln>'
        f"</p:spPr></p:cxnSp>"
    )


def picture(number: int, rid: str, place: str, alt: str = "", ph: str = "") -> str:
    return (
        f'<p:pic><p:nvPicPr><p:cNvPr id="{number}" name="Picture {number}" descr="{alt}"/>'
        f"<p:cNvPicPr/><p:nvPr>{ph}</p:nvPr></p:nvPicPr><p:blipFill>"
        f'<a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
        f'<p:spPr>{place}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'
    )


def graphic(number: int, place: str, uri: str, data: str) -> str:
    return (
        f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{number}" name="Frame {number}"/>'
        f"<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>"
        f'{place.replace("a:xfrm", "p:xfrm")}<a:graphic><a:graphicData uri="{uri}">{data}'
        f"</a:graphicData></a:graphic></p:graphicFrame>"
    )


def tree(*shapes: str, name: str = "", background: str = "") -> str:
    named = f' name="{name}"' if name else ""
    return (
        f'<p:cSld{named}>{background}<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/>'
        f"<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>{''.join(shapes)}</p:spTree></p:cSld>"
    )


def _rels(relations: list[tuple[str, str, str]]) -> str:
    items = "".join(
        f'<Relationship Id="{rid}" Type="{type}" Target="{target}"'
        + (' TargetMode="External"' if target.startswith("http") else "")
        + "/>"
        for rid, type, target in relations
    )
    return f'<Relationships xmlns="{RELS}">{items}</Relationships>'


def presentation(
    master: str,
    styles: str,
    layouts: list[str],
    slides: list[dict],
    sections: list[tuple[str, list[int]]] | None = None,
    size: tuple[int, int] = (12192000, 6858000),
    notes_master: str = "",
) -> bytes:
    """A pptx of a master, given as its cSld and txStyles, its layouts and its slides, each a
    dict of its layout's number, its cSld, its own attributes and parts: notes, images, links
    and comments."""
    files: dict[str, str | bytes] = {}
    types = [
        ("/ppt/presentation.xml", f"{ML}.presentation.main+xml"),
        ("/ppt/slideMasters/slideMaster1.xml", f"{ML}.slideMaster+xml"),
        ("/ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
    ]
    files["ppt/theme/theme1.xml"] = THEME
    layout_ids = "".join(
        f'<p:sldLayoutId id="{2147483649 + at}" r:id="rId{at + 1}"/>' for at in range(len(layouts))
    )
    files["ppt/slideMasters/slideMaster1.xml"] = (
        f'<p:sldMaster {NS}>{master}<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
        'accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" '
        'accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
        f"<p:sldLayoutIdLst>{layout_ids}</p:sldLayoutIdLst>{styles}</p:sldMaster>"
    )
    files["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = _rels(
        [
            (f"rId{at + 1}", f"{DOC}/slideLayout", f"../slideLayouts/slideLayout{at + 1}.xml")
            for at in range(len(layouts))
        ]
        + [(f"rId{len(layouts) + 1}", f"{DOC}/theme", "../theme/theme1.xml")]
    )
    for at, layout in enumerate(layouts, 1):
        files[f"ppt/slideLayouts/slideLayout{at}.xml"] = layout
        files[f"ppt/slideLayouts/_rels/slideLayout{at}.xml.rels"] = _rels(
            [("rId1", f"{DOC}/slideMaster", "../slideMasters/slideMaster1.xml")]
        )
        types.append((f"/ppt/slideLayouts/slideLayout{at}.xml", f"{ML}.slideLayout+xml"))
    relations = [("rId1", f"{DOC}/slideMaster", "slideMasters/slideMaster1.xml")]
    listed = []
    if notes_master:
        files["ppt/notesMasters/notesMaster1.xml"] = notes_master
        files["ppt/notesMasters/_rels/notesMaster1.xml.rels"] = _rels(
            [("rId1", f"{DOC}/theme", "../theme/theme1.xml")]
        )
        types.append(("/ppt/notesMasters/notesMaster1.xml", f"{ML}.notesMaster+xml"))
        relations.append(("rIdN", f"{DOC}/notesMaster", "notesMasters/notesMaster1.xml"))
    for at, slide in enumerate(slides, 1):
        name = f"ppt/slides/slide{at}.xml"
        attrs = slide.get("attrs", "")
        files[name] = f"<p:sld {NS}{attrs}>{slide['tree']}{slide.get('after', '')}</p:sld>"
        own = [("rId1", f"{DOC}/slideLayout", f"../slideLayouts/slideLayout{slide['layout']}.xml")]
        for rid, data in slide.get("images", {}).items():
            files[f"ppt/media/image{at}{rid}.png"] = data
            own.append((rid, f"{DOC}/image", f"../media/image{at}{rid}.png"))
        for rid, target in slide.get("links", {}).items():
            own.append((rid, f"{DOC}/hyperlink", target))
        if comments := slide.get("comments"):
            files[f"ppt/comments/comment{at}.xml"] = comments
            own.append(("rIdC", f"{DOC}/comments", f"../comments/comment{at}.xml"))
            types.append((f"/ppt/comments/comment{at}.xml", f"{ML}.comments+xml"))
        if notes := slide.get("notes"):
            files[f"ppt/notesSlides/notesSlide{at}.xml"] = f"<p:notes {NS}>{notes}</p:notes>"
            files[f"ppt/notesSlides/_rels/notesSlide{at}.xml.rels"] = _rels(
                [
                    ("rId1", f"{DOC}/notesMaster", "../notesMasters/notesMaster1.xml"),
                    ("rId2", f"{DOC}/slide", f"../slides/slide{at}.xml"),
                ]
            )
            own.append(("rIdS", f"{DOC}/notesSlide", f"../notesSlides/notesSlide{at}.xml"))
            types.append((f"/ppt/notesSlides/notesSlide{at}.xml", f"{ML}.notesSlide+xml"))
        files[f"ppt/slides/_rels/slide{at}.xml.rels"] = _rels(own)
        types.append((f"/{name}", f"{ML}.slide+xml"))
        relations.append((f"rIdS{at}", f"{DOC}/slide", f"slides/slide{at}.xml"))
        listed.append(f'<p:sldId id="{255 + at}" r:id="rIdS{at}"/>')
    extensions = ""
    if sections:
        listed_sections = "".join(
            f'<p14:section name="{name}" id="{{0000000{at}-0000-0000-0000-000000000000}}">'
            f"<p14:sldIdLst>{''.join(f'<p14:sldId id="{255 + each}"/>' for each in ids)}"
            "</p14:sldIdLst></p14:section>"
            for at, (name, ids) in enumerate(sections)
        )
        extensions = (
            f'<p:extLst><p:ext uri="{SECTIONS}"><p14:sectionLst xmlns:p14="{P14}">'
            f"{listed_sections}</p14:sectionLst></p:ext></p:extLst>"
        )
    notes_list = '<p:notesMasterIdLst><p:notesMasterId r:id="rIdN"/></p:notesMasterIdLst>'
    files["ppt/presentation.xml"] = (
        f'<p:presentation {NS}><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/>'
        f"</p:sldMasterIdLst>{notes_list if notes_master else ''}"
        f"<p:sldIdLst>{''.join(listed)}</p:sldIdLst>"
        f'<p:sldSz cx="{size[0]}" cy="{size[1]}"/><p:notesSz cx="6858000" cy="9144000"/>'
        '<p:defaultTextStyle><a:lvl1pPr><a:defRPr sz="1800"><a:solidFill>'
        '<a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/></a:defRPr>'
        f"</a:lvl1pPr></p:defaultTextStyle>{extensions}</p:presentation>"
    )
    files["ppt/_rels/presentation.xml.rels"] = _rels(relations)
    files["_rels/.rels"] = _rels([("rId1", f"{DOC}/officeDocument", "ppt/presentation.xml")])
    overrides = "".join(
        f'<Override PartName="{name}" ContentType="{type}"/>' for name, type in types
    )
    files["[Content_Types].xml"] = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Default Extension="png" ContentType="image/png"/>{overrides}</Types>'
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


TABLE = "http://schemas.openxmlformats.org/drawingml/2006/table"
DIAGRAM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
STYLES = (
    '<p:txStyles><p:titleStyle><a:lvl1pPr algn="l"><a:defRPr sz="4400" b="1"><a:solidFill>'
    '<a:schemeClr val="tx2"/></a:solidFill><a:latin typeface="+mj-lt"/></a:defRPr></a:lvl1pPr>'
    '</p:titleStyle><p:bodyStyle><a:lvl1pPr marL="228600" indent="-228600"><a:buFont '
    'typeface="Arial"/><a:buChar char="•"/><a:defRPr sz="2800"><a:solidFill><a:schemeClr '
    'val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr><a:lvl2pPr>'
    '<a:buFont typeface="Arial"/><a:buChar char="–"/><a:defRPr sz="2400"/></a:lvl2pPr>'
    '<a:lvl3pPr><a:buFont typeface="Wingdings"/><a:buChar char="§"/><a:defRPr sz="2000"/>'
    '</a:lvl3pPr></p:bodyStyle><p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr>'
    "</p:otherStyle></p:txStyles>"
)
NUMBER_LOOK = (
    '<a:lvl1pPr algn="r"><a:defRPr sz="1200"><a:solidFill><a:schemeClr val="tx1"><a:lumMod '
    'val="50000"/><a:lumOff val="50000"/></a:schemeClr></a:solidFill></a:defRPr></a:lvl1pPr>'
)
ACCENT = '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>'
MASTER = tree(
    holder(2, "title", None, frame(1.5, 0.8, 30, 3.5), body(para(), anchor="ctr")),
    holder(3, "body", 1, frame(1.5, 4.8, 30, 12), body(para(), anchor="t")),
    holder(4, "dt", 10, frame(1.5, 17.6, 7, 1)),
    holder(5, "ftr", 11, frame(11, 17.6, 11, 1)),
    holder(6, "sldNum", 12, frame(24, 17.6, 7, 1), body(para(), styles=NUMBER_LOOK)),
    shape(7, frame(0, 0, 33.867, 0.5), fill=ACCENT),
    line(8, frame(1.5, 4.5, 30, 0)),
    shape(9, frame(1.5, 18.5, 10, 0.5), text=body(para(run("Povjerljivo")))),
    shape(10, frame(30, 0.5, 3, 3), geometry="star5"),
    background='<p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>',
)
FOOTERS = (holder(4, "dt", 10), holder(5, "ftr", 11), holder(6, "sldNum", 12))
CENTERED = '<a:lvl1pPr algn="ctr"><a:defRPr sz="6000"/></a:lvl1pPr>'
UNDER = '<a:lvl1pPr marL="0" indent="0" algn="ctr"><a:buNone/><a:defRPr sz="2400"/></a:lvl1pPr>'
HEADER = '<a:lvl1pPr marL="0" indent="0"><a:buNone/><a:defRPr sz="2400" b="1"/></a:lvl1pPr>'
GRAY = '<p:bg><p:bgPr><a:solidFill><a:schemeClr val="bg2"/></a:solidFill></p:bgPr></p:bg>'


def layout(cSld: str, type: str = "", attrs: str = "") -> str:
    kind = f' type="{type}"' if type else ""
    return f"<p:sldLayout {NS}{kind}{attrs}>{cSld}</p:sldLayout>"


LAYOUTS = [
    layout(
        tree(
            holder(
                2,
                "ctrTitle",
                None,
                frame(4.2, 3.1, 25.4, 6.6),
                body(para(), anchor="b", styles=CENTERED),
            ),
            holder(3, "subTitle", 1, frame(4.2, 10, 25.4, 4.6), body(para(), styles=UNDER)),
            *FOOTERS,
            name="Naslovni slajd",
        ),
        "title",
    ),
    layout(
        tree(holder(2, "title", None), holder(3, None, 1), *FOOTERS, name="Naslov i sadržaj"),
        "obj",
    ),
    layout(
        tree(
            holder(2, "title", None),
            holder(3, None, 1, frame(1.5, 4.8, 14.5, 12)),
            holder(4, None, 2, frame(17.5, 4.8, 14.5, 12)),
            name="Dva sadržaja",
        ),
        "twoObj",
    ),
    layout(
        tree(
            holder(2, "title", None),
            holder(3, "body", 1, frame(1.5, 4.8, 14.5, 1.5), body(para(), styles=HEADER)),
            holder(4, None, 2, frame(1.5, 6.5, 14.5, 10)),
            holder(5, "body", 3, frame(17.5, 4.8, 14.5, 1.5), body(para(), styles=HEADER)),
            holder(6, None, 4, frame(17.5, 6.5, 14.5, 10)),
            name="Usporedba",
        ),
        "twoTxTwoObj",
    ),
    layout(
        tree(holder(2, "title", None), name="Bez pozadine", background=GRAY),
        attrs=' showMasterSp="0"',
    ),
    layout(
        tree(holder(2, "title", None), *FOOTERS, name="Neiskorišten")
        + '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr><p:hf hdr="0" ftr="0" dt="0"/>',
        "titleOnly",
    ),
]
NOTES_MASTER = (
    f"<p:notesMaster {NS}>"
    + tree(holder(2, "body", 1, frame(1, 12, 18, 10)))
    + '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
    'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" '
    'folHlink="folHlink"/><p:notesStyle><a:lvl1pPr><a:defRPr sz="1200"/></a:lvl1pPr>'
    "</p:notesStyle></p:notesMaster>"
)


def cell(text: str = "", attrs: str = "") -> str:
    runs = run(text) if text else ""
    return (
        f"<a:tc{attrs}><a:txBody><a:bodyPr/><a:lstStyle/><a:p>{runs}</a:p></a:txBody>"
        "<a:tcPr/></a:tc>"
    )


GRID = (
    '<a:tbl><a:tblPr firstRow="1"><a:tableStyleId>{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}'
    '</a:tableStyleId></a:tblPr><a:tblGrid><a:gridCol w="3600000"/><a:gridCol w="1800000"/>'
    '<a:gridCol w="1800000"/></a:tblGrid><a:tr h="370840">'
    + cell("Kvartal", ' gridSpan="2"')
    + cell(attrs=' hMerge="1"')
    + cell("Iznos")
    + '</a:tr><a:tr h="370840">'
    + cell("Q1")
    + cell("siječanj")
    + cell("1.200")
    + "</a:tr></a:tbl>"
)
CHILDREN = '<a:chOff x="0" y="0"/><a:chExt cx="1800000" cy="360000"/></a:xfrm>'
GROUP = (
    '<p:grpSp><p:nvGrpSpPr><p:cNvPr id="9" name="Group"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    f"<p:grpSpPr>{frame(2, 10, 10, 2).replace('</a:xfrm>', CHILDREN)}</p:grpSpPr>"
    f"{shape(10, frame(0, 0, 5, 1), text=body(para(run('U skupini'))))}</p:grpSp>"
)
VIDEO = (
    '<p:pic><p:nvPicPr><p:cNvPr id="11" name="Video"/><p:cNvPicPr/><p:nvPr><a:videoFile '
    'r:link="rId9"/></p:nvPr></p:nvPicPr><p:blipFill><a:blip r:embed="rId2"/></p:blipFill>'
    f"<p:spPr>{frame(20, 6, 8, 5)}</p:spPr></p:pic>"
)
COUNTED = '<a:pPr><a:buAutoNum type="arabicParenR" startAt="3"/></a:pPr>'
PLAIN = '<a:pPr marL="0" indent="0" algn="ctr"><a:buNone/></a:pPr>'
NUMBER = '<a:fld id="{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}" type="slidenum"><a:t>2</a:t></a:fld>'
RED = '<p:bg><p:bgPr><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill></p:bgPr></p:bg>'
SLIDES = [
    {
        "layout": 1,
        "tree": tree(
            holder(2, "ctrTitle", None, "", body(para(run("Godišnji izvještaj")))),
            holder(3, "subTitle", 1, "", body(para(run("Zagreb, 2026")))),
        ),
    },
    {
        "layout": 2,
        "tree": tree(
            holder(2, "title", None, "", body(para(run("Prihodi")))),
            holder(
                3,
                None,
                1,
                "",
                body(
                    para(run("Rast je "), run("brz", ' b="1"'), run(" i stalan")),
                    para(run("Izvoz"), props='<a:pPr lvl="1"/>'),
                    para(run("Znak"), props='<a:pPr lvl="2"/>'),
                    para(run("Treći"), props=COUNTED),
                    para(run("Četvrti"), props=COUNTED),
                    para(run("Napomena", ' sz="2000"'), props=PLAIN),
                    para(run("Više", link="rIdL1")),
                    para(),
                ),
            ),
            holder(4, "sldNum", 12, "", body(para(NUMBER))),
            holder(5, "ftr", 11, "", body(para(run("Tvrtka d.o.o.")))),
            shape(6, frame(1.5, 17.2, 10, 1), text=body(para(run("Izvor: HNB")))),
            picture(7, "rId2", frame(20, 8, 7.3, 4), "Graf rasta"),
            graphic(8, frame(2, 12, 20, 3), TABLE, GRID),
        ),
        "images": {"rId2": PNG},
        "links": {"rIdL1": "https://example.com/izvjestaj"},
        "notes": tree(
            holder(2, "sldImg", None),
            holder(
                3, "body", 1, "", body(para(run("Govoriti polako")), para(run("Pitanja na kraju")))
            ),
        ),
    },
    {
        "layout": 3,
        "attrs": ' show="0"',
        "tree": tree(
            holder(2, "title", None, "", body(para(run("Usporedba")))),
            holder(3, None, 1, "", body(para(run("Lijevo")))),
            holder(4, None, 2, "", body(para(run("Desno")))),
        ),
    },
    {
        "layout": 4,
        "tree": tree(
            holder(2, "title", None, "", body(para(run("Prije i poslije")))),
            holder(3, "body", 1, "", body(para(run("Prije")))),
            holder(4, None, 2, "", body(para(run("Staro")))),
            holder(5, "body", 3, "", body(para(run("Poslije")))),
            holder(6, None, 4, "", body(para(run("Novo")))),
        ),
    },
    {
        "layout": 2,
        "tree": tree(
            holder(2, "title", None, "", body(para(run("Ostalo")))),
            graphic(3, frame(2, 5, 10, 4), DIAGRAM, f'<dgm:relIds xmlns:dgm="{DIAGRAM}"/>'),
            VIDEO,
            line(12, frame(2, 15, 10, 0)),
            GROUP,
            background=RED,
        ),
        "images": {"rId2": PNG},
        "after": (
            '<p:transition spd="med"><p:fade/></p:transition><p:timing><p:tnLst><p:par>'
            '<p:cTn id="1"><p:childTnLst><p:anim/></p:childTnLst></p:cTn></p:par></p:tnLst>'
            "</p:timing>"
        ),
        "comments": (
            f'<p:cmLst {NS}><p:cm authorId="0" idx="1"><p:pos x="10" y="10"/>'
            "<p:text>Provjeriti</p:text></p:cm></p:cmLst>"
        ),
    },
    {"layout": 5, "tree": tree(holder(2, "title", None, "", body(para(run("Kraj")))))},
]


def powerpoint_file() -> bytes:
    """A presentation as PowerPoint saves one, in sections, over a master that draws behind
    its layouts, a layout of them taken by no slide."""
    return presentation(
        MASTER,
        STYLES,
        LAYOUTS,
        SLIDES,
        [("Uvod", [1]), ("Glavno", [2, 3, 4, 5]), ("Kraj", [6])],
        notes_master=NOTES_MASTER,
    )
