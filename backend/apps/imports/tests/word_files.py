"""Small Word files for the tests, written part by part as Word lays them out."""

import io
import zipfile

NAMESPACES = " ".join(
    f'xmlns:{prefix}="{uri}"'
    for prefix, uri in (
        ("w", "http://schemas.openxmlformats.org/wordprocessingml/2006/main"),
        ("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships"),
        ("wp", "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"),
        ("a", "http://schemas.openxmlformats.org/drawingml/2006/main"),
        ("pic", "http://schemas.openxmlformats.org/drawingml/2006/picture"),
        ("w14", "http://schemas.microsoft.com/office/word/2010/wordml"),
        ("w15", "http://schemas.microsoft.com/office/word/2012/wordml"),
    )
)
RELATIONSHIPS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml"
# Each optional part: its root element, file, content type and relationship type.
PARTS = {
    "styles": ("w:styles", "styles.xml", f"{WORD}.styles+xml", f"{RELATIONSHIPS}/styles"),
    "numbering": (
        "w:numbering",
        "numbering.xml",
        f"{WORD}.numbering+xml",
        f"{RELATIONSHIPS}/numbering",
    ),
    "footnotes": (
        "w:footnotes",
        "footnotes.xml",
        f"{WORD}.footnotes+xml",
        f"{RELATIONSHIPS}/footnotes",
    ),
    "endnotes": ("w:endnotes", "endnotes.xml", f"{WORD}.endnotes+xml", f"{RELATIONSHIPS}/endnotes"),
    "comments": ("w:comments", "comments.xml", f"{WORD}.comments+xml", f"{RELATIONSHIPS}/comments"),
    "extended": (
        "w15:commentsEx",
        "commentsExtended.xml",
        f"{WORD}.commentsExtended+xml",
        "http://schemas.microsoft.com/office/2011/relationships/commentsExtended",
    ),
    "header": ("w:hdr", "header1.xml", f"{WORD}.header+xml", f"{RELATIONSHIPS}/header"),
    "header2": ("w:hdr", "header2.xml", f"{WORD}.header+xml", f"{RELATIONSHIPS}/header"),
    "footer": ("w:ftr", "footer1.xml", f"{WORD}.footer+xml", f"{RELATIONSHIPS}/footer"),
    "settings": (
        "w:settings",
        "settings.xml",
        f"{WORD}.settings+xml",
        f"{RELATIONSHIPS}/settings",
    ),
    "theme": (
        "a:theme",
        "theme/theme1.xml",
        "application/vnd.openxmlformats-officedocument.theme+xml",
        f"{RELATIONSHIPS}/theme",
    ),
}
MEDIA = {
    "png": "image/png",
    "emf": "image/x-emf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
CHART = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"
# A text column of 16 cm: an A4 page less 2.5 cm margins.
SECTION = (
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1418" w:right="1418" w:bottom="1418" w:left="1418"/></w:sectPr>'
)


def theme(major: str, minor: str) -> str:
    return (
        '<a:themeElements><a:fontScheme name="Office">'
        f'<a:majorFont><a:latin typeface="{major}"/></a:majorFont>'
        f'<a:minorFont><a:latin typeface="{minor}"/></a:minorFont>'
        "</a:fontScheme></a:themeElements>"
    )


def p(text: str = "", style: str | None = None, props: str = "") -> str:
    styled = f'<w:pStyle w:val="{style}"/>' if style else ""
    run = f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>' if text else ""
    return f"<w:p><w:pPr>{styled}{props}</w:pPr>{run}</w:p>"


def numbered(text: str, num: int, level: int = 0) -> str:
    return p(text, props=f'<w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="{num}"/></w:numPr>')


def word_file(
    body: str,
    media: dict[str, tuple[str, bytes]] | None = None,
    links: dict[str, str] | None = None,
    section: str = SECTION,
    charts: dict[str, tuple[str, bytes | None]] | None = None,
    **parts: str,
) -> bytes:
    """A docx of the body's paragraphs and tables ending in its last section, the parts
    named under the relationship id rId and their name, the media, the external links and
    the charts, each with the workbook it embeds if any, under their relationship ids."""
    document = f"<w:document {NAMESPACES}><w:body>{body}{section}</w:body></w:document>"
    files: dict[str, str | bytes] = {"word/document.xml": document}
    main = f"{WORD}.document.main+xml"
    overrides = [f'<Override PartName="/word/document.xml" ContentType="{main}"/>']
    related = []
    for key, content in parts.items():
        root, name, content_type, relationship = PARTS[key]
        files[f"word/{name}"] = f"<{root} {NAMESPACES}>{content}</{root}>"
        overrides.append(f'<Override PartName="/word/{name}" ContentType="{content_type}"/>')
        related.append(f'<Relationship Id="rId{key}" Type="{relationship}" Target="{name}"/>')
    for id, (name, data) in (media or {}).items():
        files[f"word/media/{name}"] = data
        related.append(
            f'<Relationship Id="{id}" Type="{RELATIONSHIPS}/image" Target="media/{name}"/>'
        )
    for id, href in (links or {}).items():
        related.append(
            f'<Relationship Id="{id}" Type="{RELATIONSHIPS}/hyperlink" Target="{href}" '
            'TargetMode="External"/>'
        )
    package = "http://schemas.openxmlformats.org/package/2006"
    for index, (id, (chart, workbook)) in enumerate((charts or {}).items(), 1):
        files[f"word/charts/chart{index}.xml"] = chart
        overrides.append(
            f'<Override PartName="/word/charts/chart{index}.xml" ContentType="{CHART}"/>'
        )
        target = f"charts/chart{index}.xml"
        related.append(f'<Relationship Id="{id}" Type="{RELATIONSHIPS}/chart" Target="{target}"/>')
        if workbook is not None:
            files[f"word/embeddings/book{index}.xlsx"] = workbook
            files[f"word/charts/_rels/chart{index}.xml.rels"] = (
                f'<Relationships xmlns="{package}/relationships">'
                f'<Relationship Id="rId1" Type="{RELATIONSHIPS}/package" '
                f'Target="../embeddings/book{index}.xlsx"/></Relationships>'
            )
    defaults = "".join(
        f'<Default Extension="{extension}" ContentType="{content_type}"/>'
        for extension, content_type in (
            ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
            ("xml", "application/xml"),
            *MEDIA.items(),
        )
    )
    files["[Content_Types].xml"] = (
        f'<Types xmlns="{package}/content-types">{defaults}{"".join(overrides)}</Types>'
    )
    files["_rels/.rels"] = (
        f'<Relationships xmlns="{package}/relationships">'
        f'<Relationship Id="rId1" Type="{RELATIONSHIPS}/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    files["word/_rels/document.xml.rels"] = (
        f'<Relationships xmlns="{package}/relationships">{"".join(related)}</Relationships>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
