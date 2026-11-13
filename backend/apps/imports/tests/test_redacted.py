import io
import zlib

import pikepdf
import pypdfium2 as pdfium
import pytest
from pikepdf import Array, Dictionary, Name, OutlineItem, String
from PIL import Image

from apps.access.models import Grant, Role
from apps.access.tests.test_access import create, person, share
from apps.blobs.tests.test_blobs import content
from apps.comments.models import Thread
from apps.documents.models import Node
from apps.exports.tests.test_noted import AT, comment, draw, encrypted, fill, keep
from apps.imports import redacted
from apps.imports.redaction.content import Removed
from apps.imports.tests.test_composed import form, room, saved
from apps.jobs.tests.handed import done, refused
from apps.search.tests.test_ocr import READ, SCANNED, recognise
from apps.search.tests.test_search import extract_all, pdf_bytes, upload_file

pytestmark = pytest.mark.django_db

LINE = "Ugovor potpisuje Ana Horvat iz Zagreba."


def mark(file, page, *rects, key="a") -> None:
    keep(
        file,
        "redactions",
        {
            key: {
                "kind": "redaction",
                "page": page,
                "rects": [list(each) for each in rects],
                "by": None,
                "at": AT,
            }
        },
    )


def found(client, file, q) -> list[dict]:
    response = client.get(f"/api/nodes/{file}/found", {"q": q})
    assert response.status_code == 200, response.json()
    return response.json()["hits"]


def mark_found(client, file, q) -> None:
    hits = found(client, file, q)
    keep(
        file,
        "redactions",
        {
            f"h{index}": {"kind": "redaction", **hit, "by": None, "at": AT}
            for index, hit in enumerate(hits)
        },
    )


def redact(client, file, title="Ugovor (zacrnjeno)", status=None) -> dict:
    if status is None:
        return done(client, "redact", file=file, title=title)
    found, error = refused(client, "redact", file=file, title=title)
    assert found == status, error
    return {"error": error}


def bytes_of(client, node) -> bytes:
    response = client.get(f"/api/nodes/{node}/file")
    assert response.status_code == 200
    return content(response)


def opened(data: bytes) -> pikepdf.Pdf:
    pdf = pikepdf.open(io.BytesIO(data))
    assert pdf.check_pdf_syntax() == []
    return pdf


def plain(data: bytes) -> bytes:
    """The file with every stream it can decode decoded, to look for what must be gone."""
    with pikepdf.open(io.BytesIO(data)) as pdf:
        out = io.BytesIO()
        pdf.save(out, qdf=True, stream_decode_level=pikepdf.StreamDecodeLevel.generalized)
        return out.getvalue()


def chars(data: bytes, page: int = 1) -> list[tuple[str, tuple[float, ...]]]:
    document = pdfium.PdfDocument(data)
    text = document[page - 1].get_textpage()
    read = [
        (text.get_text_range(index, 1), tuple(round(value, 2) for value in text.get_charbox(index)))
        for index in range(text.count_chars())
    ]
    document.close()
    return [(char, box) for char, box in read if char.strip()]


def rendered(data: bytes, page: int = 1) -> Image.Image:
    document = pdfium.PdfDocument(data)
    picture = document[page - 1].render(scale=1).to_pil().convert("RGB")
    document.close()
    return picture


def built(content_stream: bytes, resources: dict, pages: int = 1, **root) -> bytes:
    pdf = pikepdf.new()
    for _ in range(pages):
        page = pdf.add_blank_page(page_size=(595, 842))
        page.obj.Resources = Dictionary(resources)
        page.obj.Contents = pdf.make_stream(content_stream)
    for key, value in root.items():
        pdf.Root[Name("/" + key)] = value
    return saved(pdf)


HELVETICA = Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)


def test_text_under_the_boxes_is_taken_out_and_the_rest_of_the_line_stays_in_place(api):
    original = pdf_bytes(LINE, "Druga stranica")
    folder = create(api, "folder", "Ugovori")
    file = upload_file(api, "Ugovor", original, parent=folder)
    [hit] = found(api, file, "ana horvat")
    mark_found(api, file, "ana horvat")
    made = redact(api, file)
    assert (made["title"], made["parent"], made["kind"]) == ("Ugovor (zacrnjeno)", folder, "file")
    data = bytes_of(api, made["id"])
    after = chars(data)
    assert "".join(char for char, _ in after) == "UgovorpotpisujeizZagreba."
    assert set(after) <= set(chars(original))
    assert chars(data, 2) == chars(original, 2)
    assert b"Horvat" not in plain(data)
    left, bottom, right, top = hit["rects"][0]
    middle = (round((left + right) / 2), round(842 - (bottom + top) / 2))
    assert rendered(data).getpixel(middle) == (0, 0, 0)
    assert bytes_of(api, file) == original
    assert list(room(file, "redactions")) == ["h0"]


@pytest.mark.django_db(transaction=True)
def test_a_read_copy_is_redacted_its_invisible_text_with_it(api, service):
    file = upload_file(api, "Sken", SCANNED)
    extract_all()
    service.append((200, READ))
    assert recognise()
    mark_found(api, file, "rukom")
    made = redact(api, file)
    data = bytes_of(api, made["id"])
    assert "".join(char for char, _ in chars(data, 2)) == "Procitano"
    assert b"rukom" not in plain(data)


def glyphless(pdf: pikepdf.Pdf) -> Dictionary:
    """A composite font as Tesseract writes its invisible text in: two bytes a character, the
    code its Unicode value, and no glyphs."""
    to_unicode = pdf.make_stream(
        b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
        b"/CMapName /Adobe-Identity-UCS def /CMapType 2 def\n"
        b"1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
        b"1 beginbfrange <0000> <FFFF> <0000> endbfrange\n"
        b"endcmap CMapName currentdict /CMap defineresource pop end end"
    )
    descriptor = Dictionary(
        Type=Name.FontDescriptor,
        FontName=Name("/GlyphLessFont"),
        Flags=5,
        FontBBox=[0, 0, 500, 1000],
        ItalicAngle=0,
        Ascent=1000,
        Descent=0,
        CapHeight=1000,
        StemV=80,
    )
    cid = Dictionary(
        Type=Name.Font,
        Subtype=Name.CIDFontType2,
        BaseFont=Name("/GlyphLessFont"),
        CIDSystemInfo=Dictionary(
            Registry=String("Adobe"), Ordering=String("Identity"), Supplement=0
        ),
        FontDescriptor=descriptor,
        DW=500,
        CIDToGIDMap=Name.Identity,
    )
    return Dictionary(
        Type=Name.Font,
        Subtype=Name.Type0,
        BaseFont=Name("/GlyphLessFont"),
        Encoding=Name("/Identity-H"),
        DescendantFonts=[cid],
        ToUnicode=to_unicode,
    )


def utf16(text: str) -> bytes:
    return text.encode("utf-16-be").hex().encode()


def test_invisible_text_of_a_composite_font_in_a_form_is_taken_out(api):
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(595, 842))
    layer = pdf.make_stream(
        b"BT 3 Tr /G 10 Tf 80 Tz 1 0 0 1 72 700 Tm <%s> Tj ET" % utf16("OIB 12345678901 kraj"),
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=[0, 0, 595, 842],
        Resources=Dictionary(Font=Dictionary(G=glyphless(pdf))),
    )
    page.obj.Resources = Dictionary(XObject=Dictionary(OCR=layer))
    page.obj.Contents = pdf.make_stream(b"q /OCR Do Q")
    file = upload_file(api, "Sken", saved(pdf))
    before = chars(bytes_of(api, file))
    mark_found(api, file, "12345678901")
    data = bytes_of(api, redact(api, file)["id"])
    after = chars(data)
    assert "".join(char for char, _ in after) == "OIBkraj"
    assert set(after) <= set(before)
    assert utf16("12345678901") not in plain(data)


def image(pixels: Image.Image, **given) -> tuple[bytes, dict]:
    if given.get("Filter") == Name.DCTDecode:
        written = io.BytesIO()
        pixels.save(written, "JPEG", quality=95)
        return written.getvalue(), given
    return zlib.compress(pixels.tobytes()), {"Filter": Name.FlateDecode, **given}


def drawn_image(data: bytes, page: int = 1) -> Image.Image:
    with pikepdf.open(io.BytesIO(data)) as pdf:
        [found] = pdf.pages[page - 1].get_images().values()
        return pikepdf.PdfImage(found).as_pil_image().convert("L")


@pytest.mark.parametrize("encoding", ["flate", "dct"])
def test_the_pixels_under_a_box_are_cleared_and_the_rest_of_the_image_kept(api, encoding):
    grey = Image.new("L", (100, 50), 200)
    data, given = image(grey, **({"Filter": Name.DCTDecode} if encoding == "dct" else {}))
    pdf = pikepdf.new()
    picture = pdf.make_stream(
        data,
        Type=Name.XObject,
        Subtype=Name.Image,
        Width=100,
        Height=50,
        BitsPerComponent=8,
        ColorSpace=Name.DeviceGray,
        **given,
    )
    for _ in range(2):
        page = pdf.add_blank_page(page_size=(595, 842))
        page.obj.Resources = Dictionary(XObject=Dictionary(Im0=picture))
        page.obj.Contents = pdf.make_stream(b"q 200 0 0 100 72 400 cm /Im0 Do Q")
    file = upload_file(api, "Slika", saved(pdf))
    mark(file, 1, (72, 400, 172, 500))
    made = bytes_of(api, redact(api, file)["id"])
    cleared = drawn_image(made)
    assert cleared.getpixel((10, 25)) < 10
    assert abs(cleared.getpixel((90, 25)) - 200) < 6
    assert drawn_image(made, 2).getpixel((10, 25)) == pytest.approx(200, abs=3)
    with pikepdf.open(io.BytesIO(made)) as copy:
        [first] = copy.pages[0].get_images().values()
        assert first.get("/Filter") == (Name.DCTDecode if encoding == "dct" else Name.FlateDecode)


def test_a_fax_image_is_cleared_and_encoded_again_as_a_fax(api):
    white = Image.new("1", (64, 32), 1)
    written = io.BytesIO()
    white.save(written, "TIFF", compression="group4")
    tiff = Image.open(io.BytesIO(written.getvalue()))
    start, length = tiff.tag_v2[273][0], tiff.tag_v2[279][0]
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(595, 842))
    picture = pdf.make_stream(
        written.getvalue()[start : start + length],
        Type=Name.XObject,
        Subtype=Name.Image,
        Width=64,
        Height=32,
        BitsPerComponent=1,
        ColorSpace=Name.DeviceGray,
        Filter=Name.CCITTFaxDecode,
        DecodeParms=Dictionary(K=-1, Columns=64, Rows=32, BlackIs1=tiff.tag_v2[262] == 1),
    )
    page.obj.Resources = Dictionary(XObject=Dictionary(Im0=picture))
    page.obj.Contents = pdf.make_stream(b"q 64 0 0 32 0 0 cm /Im0 Do Q")
    file = upload_file(api, "Faks", saved(pdf))
    mark(file, 1, (0, 0, 32, 32))
    made = bytes_of(api, redact(api, file)["id"])
    document = pdfium.PdfDocument(made)
    [found] = [each for each in document[0].get_objects() if isinstance(each, pdfium.PdfImage)]
    pixels = found.get_bitmap(render=False).to_pil().convert("L")
    assert (pixels.getpixel((5, 5)), pixels.getpixel((50, 5))) == (0, 255)
    document.close()
    with pikepdf.open(io.BytesIO(made)) as copy:
        [first] = copy.pages[0].get_images().values()
        assert first.Filter == Name.CCITTFaxDecode


def test_drawings_are_cut_where_a_box_lies_and_kept_around_it(api):
    stream = b"0 0 1 RG 4 w 50 300 m 550 300 l S 1 0 0 rg 100 250 50 100 re f 250 290 100 20 re f"
    file = upload_file(api, "Crtež", built(stream, {}))
    mark(file, 1, (200, 280, 400, 320))
    data = bytes_of(api, redact(api, file)["id"])
    with pikepdf.open(io.BytesIO(data)) as pdf:
        points = [
            (float(operands[index]), float(operands[index + 1]))
            for operands, operator in pikepdf.parse_content_stream(pdf.pages[0])
            if str(operator) in ("m", "l")
            for index in range(0, len(operands), 2)
        ]
    assert not [(x, y) for x, y in points if 200 < x < 400 and 280 < y < 320]
    picture = rendered(data)
    assert picture.getpixel((125, 842 - 300)) == (255, 0, 0)
    assert picture.getpixel((60, 842 - 300)) == (0, 0, 255)
    assert picture.getpixel((500, 842 - 300)) == (0, 0, 255)
    assert picture.getpixel((300, 842 - 300)) == (0, 0, 0)


def test_links_notes_fields_and_attachments_the_boxes_touch_go_with_their_values(api):
    pdf = pikepdf.open(io.BytesIO(form(("Tajno", [0]), ("Javno", [1]))))
    first, second = pdf.pages[0].obj, pdf.pages[1].obj
    pdf.Root.AcroForm.Fields[0].V = String("Tajna vrijednost")
    pdf.Root.AcroForm.Fields[1].V = String("Javna vrijednost")

    def annotation(page, **given):
        made = pdf.make_indirect(Dictionary(Type=Name.Annot, **given))
        page.Annots.append(made)
        return made

    annotation(
        first,
        Subtype=Name.Link,
        Rect=[72, 650, 200, 670],
        A=Dictionary(S=Name.URI, URI=String("https://tajno.example")),
    )
    annotation(
        first,
        Subtype=Name.Link,
        Rect=[72, 100, 200, 120],
        A=Dictionary(S=Name.URI, URI=String("https://javno.example")),
    )
    note = annotation(
        first, Subtype=Name.Text, Rect=[80, 640, 100, 660], Contents=String("Tajna bilješka")
    )
    note.Popup = annotation(first, Subtype=Name.Popup, Rect=[300, 300, 400, 400], Parent=note)
    annotation(
        first,
        Subtype=Name.Text,
        Rect=[400, 100, 420, 120],
        IRT=note,
        Contents=String("Odgovor na tajnu"),
    )
    attached = pdf.make_stream(b"tajni prilog", Type=Name.EmbeddedFile)
    annotation(
        second,
        Subtype=Name.FileAttachment,
        Rect=[400, 400, 420, 420],
        FS=Dictionary(Type=Name.Filespec, F=String("prilog.txt"), EF=Dictionary(F=attached)),
    )
    file = upload_file(api, "Obrazac", saved(pdf))
    mark(file, 1, (60, 630, 300, 725))
    data = bytes_of(api, redact(api, file)["id"])
    with opened(data) as copy:
        assert [str(field.T) for field in copy.Root.AcroForm.Fields] == ["Javno"]
        assert [str(each.get("/Subtype")) for each in copy.pages[0].obj.Annots] == ["/Link"]
        assert [str(each.get("/Subtype")) for each in copy.pages[1].obj.Annots] == ["/Widget"]
    text = plain(data)
    for gone in (
        b"Tajna vrijednost",
        b"tajno.example",
        b"Tajna bil",
        b"Odgovor na tajnu",
        b"tajni prilog",
    ):
        assert gone not in text
    assert b"Javna vrijednost" in text and b"javno.example" in text


def test_notes_and_values_the_boxes_do_not_touch_go_with_the_copy_and_threads_stay(api):
    file = upload_file(api, "Obrazac", form(("Tajno", [0]), ("Javno", [1])))
    highlight = {"kind": "highlight", "color": "yellow", "by": None, "at": AT}
    stroke = {
        "kind": "stroke",
        "color": "red",
        "width": 2,
        "points": [400, 100, 450, 150],
        "by": None,
        "at": AT,
    }
    draw(
        file,
        a={**highlight, "page": 1, "rects": [[72, 700, 200, 715]]},
        b={**highlight, "page": 2, "rects": [[72, 700, 200, 715]]},
        c={**stroke, "page": 1},
    )
    fill(file, {"Tajno": {"value": "tajna"}, "Javno": {"value": "javna"}})
    comment(api, file, {"page": 1, "at": [72, 760]}, "", "Provjeriti?")
    mark(file, 1, (60, 690, 300, 725))
    made = redact(api, file)
    assert sorted((mark["page"], mark["kind"]) for mark in room(made["id"], "marks").values()) == [
        (1, "stroke"),
        (2, "highlight"),
    ]
    assert room(made["id"], "fields") == {"Javno": {"value": "javna"}}
    assert room(made["id"], "redactions") == {}
    assert not Thread.objects.filter(file_id=made["id"]).exists()
    assert Thread.objects.filter(file_id=file).count() == 1


def test_the_copy_keeps_its_bookmarks_and_loses_what_a_reader_does_not_see(api):
    pdf = pikepdf.open(io.BytesIO(pdf_bytes(LINE)))
    with pdf.open_metadata() as meta:
        meta["dc:creator"] = ["Tajni Autor"]
    pdf.docinfo["/Author"] = "Tajni Autor"
    pdf.Root.OpenAction = Dictionary(S=Name.JavaScript, JS=String("app.alert('tajno')"))
    attached = pdf.make_stream(b"tajni prilog", Type=Name.EmbeddedFile)
    pdf.Root.Names = Dictionary(
        EmbeddedFiles=Dictionary(
            Names=Array(
                [
                    String("prilog.txt"),
                    Dictionary(
                        Type=Name.Filespec, F=String("prilog.txt"), EF=Dictionary(F=attached)
                    ),
                ]
            )
        )
    )
    page = pdf.pages[0].obj
    page.PieceInfo = Dictionary(
        Editor=Dictionary(Private=String("tajni podaci"), LastModified=String("D:2026"))
    )
    page.Thumb = pdf.make_stream(
        b"\x00" * 16, Width=4, Height=4, BitsPerComponent=8, ColorSpace=Name.DeviceGray
    )
    with pdf.open_outline() as outline:
        outline.root.append(OutlineItem("Sadržaj", 0))
    file = upload_file(api, "Ugovor", saved(pdf))
    mark_found(api, file, "Horvat")
    data = bytes_of(api, redact(api, file)["id"])
    text = plain(data)
    for gone in (
        b"Tajni Autor",
        b"app.alert",
        b"tajni prilog",
        b"tajni podaci",
        b"/Thumb",
        b"/PieceInfo",
    ):
        assert gone not in text
    with opened(data) as copy:
        assert "/Info" not in copy.trailer and "/Metadata" not in copy.Root
        with copy.open_outline() as outline:
            assert [item.title for item in outline.root] == ["Sadržaj"]


def test_a_signed_file_is_redacted_without_its_signature(api):
    pdf = pikepdf.open(io.BytesIO(pdf_bytes(LINE)))
    shown = pdf.make_stream(
        b"BT /F1 8 Tf 0 2 Td (Ana Horvat) Tj ET",
        Type=Name.XObject,
        Subtype=Name.Form,
        BBox=[0, 0, 100, 20],
    )
    signature = pdf.make_indirect(
        Dictionary(
            Type=Name.Sig,
            Filter=Name("/Adobe.PPKLite"),
            Name=String("Ana Horvat potpisnica"),
            Contents=String(b"\x00" * 8),
        )
    )
    widget = pdf.make_indirect(
        Dictionary(
            Type=Name.Annot,
            Subtype=Name.Widget,
            FT=Name.Sig,
            T=String("Potpis"),
            Rect=[400, 100, 500, 120],
            V=signature,
            AP=Dictionary(N=shown),
            P=pdf.pages[0].obj,
        )
    )
    pdf.pages[0].obj.Annots = Array([widget])
    pdf.Root.AcroForm = Dictionary(Fields=Array([widget]), SigFlags=3)
    pdf.Root.Perms = Dictionary(DocMDP=signature)
    file = upload_file(api, "Potpisano", saved(pdf))
    mark_found(api, file, "Horvat")
    data = bytes_of(api, redact(api, file)["id"])
    with opened(data) as copy:
        [field] = copy.Root.AcroForm.Fields
        assert "/V" not in field and "/AP" not in field
        assert "/SigFlags" not in copy.Root.AcroForm and "/Perms" not in copy.Root
    assert b"potpisnica" not in plain(data)


def test_alternate_texts_of_what_is_taken_out_go_with_it(api):
    stream = (
        b"/Span <</ActualText (Ana Horvat) /MCID 0>> BDC"
        b" BT /F1 12 Tf 72 720 Td (Ana Horvat) Tj ET EMC"
    )
    pdf = pikepdf.open(io.BytesIO(built(stream, {"/Font": Dictionary(F1=HELVETICA)})))
    root = pdf.make_indirect(Dictionary(Type=Name.StructTreeRoot))
    element = pdf.make_indirect(
        Dictionary(
            Type=Name.StructElem,
            S=Name.Span,
            P=root,
            Pg=pdf.pages[0].obj,
            K=0,
            Alt=String("Ime osobe Ana Horvat"),
        )
    )
    root.K = Array([element])
    root.ParentTree = Dictionary(Nums=Array([0, Array([element])]))
    pdf.pages[0].obj.StructParents = 0
    pdf.Root.StructTreeRoot = root
    file = upload_file(api, "Označeno", saved(pdf))
    mark(file, 1, (60, 700, 300, 740))
    data = bytes_of(api, redact(api, file)["id"])
    assert b"Horvat" not in plain(data)
    with opened(data) as copy:
        assert "/Alt" not in copy.Root.StructTreeRoot.K[0]


def test_files_that_cannot_be_redacted_say_why(api):
    locked = upload_file(api, "Zaključano", encrypted(owner="tajna", user="tajna"))
    mark(locked, 1, (60, 700, 300, 740))
    assert redact(api, locked, status=409)["error"] == "locked"
    out = io.BytesIO()
    with pikepdf.open(io.BytesIO(pdf_bytes(LINE))) as pdf:
        allowed = pikepdf.Permissions(modify_other=False)
        pdf.save(out, encryption=pikepdf.Encryption(owner="banka", user="", allow=allowed))
    fixed = upload_file(api, "Izvod", out.getvalue())
    mark(fixed, 1, (60, 700, 300, 740))
    assert redact(api, fixed, status=409)["error"] == "modify_forbidden"
    unmarked = upload_file(api, "Ugovor", pdf_bytes(LINE))
    assert redact(api, unmarked, status=400)["error"] == "nothing_marked"
    document = create(api, "document", "Bilješka")
    assert redact(api, document, status=400)["error"] == "not_a_file"


def test_text_in_a_font_that_cannot_be_measured_is_refused_only_under_a_box(api):
    odd = Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name("/Neobican"))
    stream = b"BT /F1 12 Tf 72 720 Td (Ana Horvat) Tj ET BT /F2 12 Tf 72 400 Td (Javno) Tj ET"
    file = upload_file(api, "Čudno", built(stream, {"/Font": Dictionary(F1=HELVETICA, F2=odd)}))
    mark(file, 1, (60, 700, 300, 740))
    redact(api, file)
    mark(file, 1, (60, 390, 300, 420), key="b")
    assert redact(api, file, status=422)["error"] == "unredactable"


def test_a_copy_that_still_holds_text_under_a_box_is_not_made(api, monkeypatch, caplog):
    file = upload_file(api, "Ugovor", pdf_bytes(LINE))
    mark_found(api, file, "Horvat")
    monkeypatch.setattr(redacted, "redact_page", lambda *args: Removed())
    assert redact(api, file, status=422)["error"] == "not_removed"
    assert Node.objects.filter(kind=Node.Kind.FILE).count() == 1
    assert "characters under the boxes" in caplog.text


@pytest.mark.parametrize(
    "entry",
    [
        {"kind": "redaction", "page": 1, "rects": [], "by": None, "at": AT},
        {"kind": "redaction", "page": 1, "rects": [[10, 10, 5, 20]], "by": None, "at": AT},
        {"kind": "redaction", "page": 0, "rects": [[1, 2, 3, 4]], "by": None, "at": AT},
        {"kind": "redaction", "page": 2, "rects": [[1, 2, 3, 4]], "by": None, "at": AT},
        {"kind": "redaction", "page": 1, "rects": [[1, 2, 3, 4]], "by": None, "at": "jučer"},
        {"kind": "highlight", "page": 1, "rects": [[1, 2, 3, 4]], "by": None, "at": AT},
    ],
)
def test_a_redaction_the_viewer_would_not_write_fails_loudly(api, entry, caplog):
    file = upload_file(api, "Ugovor", pdf_bytes(LINE))
    keep(file, "redactions", {"a": entry})
    assert redact(api, file, status=422)["error"] == "unreadable_notes"
    assert "redaction" in caplog.text


def test_only_editors_redact_and_a_copy_made_where_one_may_not_add_lands_among_ones_own(api):
    folder = create(api, "folder", "Arhiva")
    file = upload_file(api, "Ugovor", pdf_bytes(LINE), parent=folder)
    mark_found(api, file, "Horvat")
    ana, ivan = person("ana@example.com"), person("ivan@example.com")
    share(api, folder, "read", id=ana.user.pk)
    share(api, file, "edit", id=ivan.user.pk)
    assert redact(ana, file, status=403)["error"] == "forbidden"
    made = redact(ivan, file)
    assert made["parent"] is None
    assert Grant.objects.filter(node_id=made["id"], user=ivan.user, role=Role.OWN).exists()
