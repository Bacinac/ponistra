import hashlib
import io

import pikepdf
import pytest
from pikepdf import Array, Dictionary, Name, String
from pycrdt import Map

from apps.access.tests.test_access import JSON, person, share
from apps.blobs import store
from apps.blobs.tests.test_blobs import content
from apps.collab.models import Update
from apps.documents.models import Node
from apps.exports.xlsx import doc_of
from apps.search.tests.test_search import pdf_bytes, upload_file

pytestmark = pytest.mark.django_db

AT = "2026-10-19T08:30:00.000Z"


def noted(client, file, **params) -> bytes:
    response = client.get(f"/api/nodes/{file}/noted", params)
    assert response.status_code == 200, response
    return content(response)


def keep(file, name: str, entries: dict) -> None:
    """The entries written over what the file's notes hold: a key written apart from its
    earlier value would be a concurrent edit, which Yjs settles by its writers' random ids."""
    node = Node.objects.get(pk=file)
    doc = doc_of(node.room)
    before = doc.get_state()
    held = doc.get(name, type=Map)
    for key, entry in entries.items():
        held[key] = entry
    Update.objects.create(document=node, room=node.room, data=doc.get_update(before))


def draw(file, **marks) -> None:
    keep(file, "marks", marks)


def fill(file, fields: dict) -> None:
    keep(file, "fields", fields)


def form_bytes() -> bytes:
    """A page of fields as a form editor makes them, which also carries an XFA form."""
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(595, 842))
    helv = Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)
    on = pdf.make_stream(
        b"0 0 12 12 re f", Type=Name.XObject, Subtype=Name.Form, BBox=[0, 0, 12, 12]
    )
    off = pdf.make_stream(b"", Type=Name.XObject, Subtype=Name.Form, BBox=[0, 0, 12, 12])

    def widget(rect, **more) -> Dictionary:
        return pdf.make_indirect(
            Dictionary(Type=Name.Annot, Subtype=Name.Widget, Rect=rect, P=page.obj, F=4, **more)
        )

    da = String("/Helv 0 Tf 0 g")
    name = widget([72, 760, 272, 780], FT=Name.Tx, T=String("Ime"), DA=da)
    amount = widget([72, 720, 272, 740], FT=Name.Tx, T=String("Iznos"), DA=da)
    note = widget([72, 620, 272, 700], FT=Name.Tx, T=String("Napomena"), Ff=4096, DA=da)
    furnished = widget(
        [72, 580, 84, 592],
        FT=Name.Btn,
        T=String("Opremljen"),
        V=Name.Off,
        AS=Name.Off,
        AP=Dictionary(N=Dictionary(Da=on, Off=off)),
    )
    paying = pdf.make_indirect(
        Dictionary(FT=Name.Btn, Ff=49152, T=String("Plaćanje"), V=Name.Off, Kids=Array())
    )
    buttons = [
        widget(
            [72 + 40 * index, 540, 84 + 40 * index, 552],
            Parent=paying,
            AS=Name.Off,
            AP=Dictionary(N=Dictionary({f"/{state}": on, "/Off": off})),
        )
        for index, state in enumerate(["Gotovina", "Kartica"])
    ]
    paying.Kids = Array(buttons)
    city = widget(
        [72, 500, 272, 520],
        FT=Name.Ch,
        Ff=131072,
        T=String("Grad"),
        Opt=Array([String("Zagreb"), String("Split")]),
        DA=da,
    )
    languages = widget(
        [72, 420, 272, 480],
        FT=Name.Ch,
        Ff=2097152,
        T=String("Jezici"),
        Opt=Array([Array([String("hr"), String("Hrvatski")]), String("en"), String("de")]),
        DA=da,
        AP=Dictionary(N=off),
    )
    page.obj.Annots = Array([name, amount, note, furnished, *buttons, city, languages])
    pdf.Root.AcroForm = Dictionary(
        Fields=Array([name, amount, note, furnished, paying, city, languages]),
        DR=Dictionary(Font=Dictionary(Helv=helv)),
        DA=da,
        XFA=pdf.make_stream(b"<xdp:xdp xmlns:xdp='http://ns.adobe.com/xdp/'/>"),
    )
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def comment(client, file, anchor, quote, body) -> dict:
    data = {"anchor": anchor, "quote": quote, "body": body}
    response = client.post(f"/api/nodes/{file}/threads", data, content_type=JSON)
    assert response.status_code == 201, response.json()
    return response.json()


def encrypted(owner: str, user: str) -> bytes:
    out = io.BytesIO()
    with pikepdf.open(io.BytesIO(pdf_bytes("Povjerljivo"))) as pdf:
        pdf.save(out, encryption=pikepdf.Encryption(owner=owner, user=user))
    return out.getvalue()


def test_a_file_without_notes_is_given_as_it_came(api):
    data = pdf_bytes("Uvod")
    file = upload_file(api, "Najam", data)
    assert noted(api, file) == data
    response = api.get(f"/api/nodes/{file}/noted", headers={"Range": "bytes=0-7"})
    assert (response.status_code, content(response)) == (206, data[:8])


def test_highlights_strokes_and_threads_are_written_into_a_copy_of_the_file(api):
    ana = person("ana@example.com", first_name="Ana", last_name="Kovač")
    data = pdf_bytes("Cijena najma", "Potpis")
    file = upload_file(api, "Najam", data)
    share(api, file, "edit", id=ana.user.pk)
    draw(
        file,
        green={
            "kind": "highlight",
            "page": 1,
            "color": "green",
            "rects": [[72, 716, 140.5, 731]],
            "by": ana.user.pk,
            "at": AT,
        },
        line={
            "kind": "stroke",
            "page": 2,
            "color": "red",
            "width": 2,
            "points": [100, 600, 120, 610.25, 140, 600],
            "by": ana.user.pk,
            "at": AT,
        },
    )
    passage = comment(api, file, {"page": 1, "rects": [[72, 700, 98, 714]]}, "najma", "Iznos?")
    ana.post(f"/api/threads/{passage['id']}/comments", {"body": "Može"}, content_type=JSON)
    api.patch(f"/api/threads/{passage['id']}", {"resolved": True}, content_type=JSON)
    comment(ana, file, {"page": 2, "at": [480, 760]}, "", "Potpis?")

    response = api.get(f"/api/nodes/{file}/noted", {"download": "1"})
    assert response["Content-Disposition"].startswith("attachment;")
    me = api.user.get_full_name() or api.user.email
    with pikepdf.open(io.BytesIO(content(response))) as pdf:
        first, second = (list(page.obj.Annots) for page in pdf.pages)
        highlight, opening, reply, state = first
        assert (highlight.Subtype, str(highlight.T), str(highlight.NM)) == (
            "/Highlight",
            "Ana Kovač",
            "green",
        )
        assert list(highlight.QuadPoints) == [72, 731, 140.5, 731, 72, 716, 140.5, 716]
        assert [float(part) for part in highlight.C] == [0.7333, 0.9686, 0.8157]
        assert highlight.AP.N.read_bytes().startswith(b"/M gs 0.733 0.969 0.816 rg 72 716")
        assert str(highlight.M).startswith("D:20261019103000")
        assert (opening.Subtype, str(opening.Contents), str(opening.T)) == (
            "/Highlight",
            "Iznos?",
            me,
        )
        assert (reply.Subtype, str(reply.Contents), str(reply.T), int(reply.F)) == (
            "/Text",
            "Može",
            "Ana Kovač",
            32,
        )
        assert reply.IRT.objgen == opening.objgen == state.IRT.objgen
        assert (str(state.StateModel), str(state.State), str(state.T)) == (
            "Review",
            "Completed",
            me,
        )
        ink, point = second
        assert (ink.Subtype, [list(line) for line in ink.InkList], int(ink.BS.W)) == (
            "/Ink",
            [[100, 600, 120, 610.25, 140, 600]],
            2,
        )
        assert ink.AP.N.read_bytes().endswith(b"RG 100 600 m 120 610.25 l 140 600 l S")
        assert (point.Subtype, point.Name, list(point.Rect), str(point.Contents)) == (
            "/Text",
            "/Comment",
            [480, 740, 500, 760],
            "Potpis?",
        )
        assert all(annotation.P.objgen == pdf.pages[1].obj.objgen for annotation in second)
    sha256 = Node.objects.get(pk=file).blob_id
    assert store.path_of(sha256).read_bytes() == data
    assert hashlib.sha256(data).hexdigest() == sha256


def test_a_file_locked_by_its_password_is_given_as_it_came_its_notes_left_beside_it(api):
    data = encrypted(owner="tajna", user="tajna")
    file = upload_file(api, "Zaključano", data)
    comment(api, file, {"page": 1, "at": [72, 760]}, "", "Otključati?")
    assert noted(api, file) == data


def test_a_file_its_owner_protected_keeps_its_protection_with_its_notes(api):
    file = upload_file(api, "Zaštićeno", encrypted(owner="vlasnik", user=""))
    comment(api, file, {"page": 1, "at": [72, 760]}, "", "Ispisati?")
    with pikepdf.open(io.BytesIO(noted(api, file))) as pdf:
        assert pdf.is_encrypted
        assert str(pdf.pages[0].obj.Annots[0].Contents) == "Ispisati?"


def test_a_filled_form_is_written_into_a_copy_its_fields_still_fields(api):
    data = form_bytes()
    file = upload_file(api, "Prijava", data)
    fill(
        file,
        {
            "Ime": {"value": "Ana Kovač"},
            "Iznos": {"value": "1234.5", "shown": "1.234,50"},
            "Napomena": {"value": "Prvi red\nDrugi red"},
            "Opremljen": {"value": "Da"},
            "Plaćanje": {"value": "Kartica"},
            "Grad": {"value": "Split"},
            "Jezici": {"value": ["hr", "de"]},
        },
    )
    with pikepdf.open(io.BytesIO(noted(api, file))) as pdf:
        form = pdf.Root.AcroForm
        assert bool(form.NeedAppearances) and Name.XFA not in form
        name, amount, note, furnished, cash, card, city, languages = pdf.pages[0].Annots
        assert str(name.V) == "Ana Kovač"
        assert (str(amount.V), b"(1.234,50) Tj" in amount.AP.N.read_bytes()) == ("1234.5", True)
        assert (str(note.V), Name.AP in note) == ("Prvi red\nDrugi red", False)
        assert (furnished.V, furnished.AS) == (Name("/Da"), Name("/Da"))
        assert (cash.Parent.V, cash.AS, card.AS) == (Name("/Kartica"), Name.Off, Name("/Kartica"))
        assert (str(city.V), b"(Split) Tj" in city.AP.N.read_bytes()) == ("Split", True)
        assert [str(each) for each in languages.V] == ["hr", "de"]
        assert (list(languages.I), Name.AP in languages) == ([0, 2], False)
    assert store.path_of(Node.objects.get(pk=file).blob_id).read_bytes() == data


@pytest.mark.parametrize(
    "fields",
    [
        {"Prezime": {"value": "Kovač"}},
        {"Ime": {"value": "Ana", "by": 1}},
        {"Ime": {"value": 7}},
        {"Opremljen": {"value": "Ne"}},
        {"Plaćanje": {"value": ["Kartica"]}},
        {"Grad": {"value": "Rijeka"}},
        {"Grad": {"value": ["Split"]}},
        {"Jezici": {"value": "hr"}},
    ],
)
def test_a_value_the_viewer_would_not_write_fails_loudly(api, fields):
    file = upload_file(api, "Prijava", form_bytes())
    fill(file, fields)
    response = api.get(f"/api/nodes/{file}/noted")
    assert (response.status_code, response.json()["error"]) == (422, "unreadable_notes")


@pytest.mark.parametrize(
    "mark",
    [
        {"kind": "circle", "page": 1},
        {"kind": "stroke", "page": 2, "color": "red", "width": 2, "points": [1, 2], "by": None},
        {
            "kind": "stroke",
            "page": 2,
            "color": "red",
            "width": 2,
            "points": [1, 2],
            "by": None,
            "at": AT,
        },
        {
            "kind": "highlight",
            "page": 1,
            "color": "teal",
            "rects": [[1, 2, 3, 4]],
            "by": None,
            "at": AT,
        },
    ],
)
def test_a_note_the_viewer_would_not_write_fails_loudly(api, mark):
    file = upload_file(api, "Najam", pdf_bytes("Uvod"))
    draw(file, wrong=mark)
    response = api.get(f"/api/nodes/{file}/noted")
    assert (response.status_code, response.json()["error"]) == (422, "unreadable_notes")
