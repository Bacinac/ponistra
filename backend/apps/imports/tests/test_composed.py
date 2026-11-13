import io

import pikepdf
import pytest
from pikepdf import Array, Dictionary, Name, OutlineItem, String
from pycrdt import Map

from apps.access.models import Grant, Role
from apps.access.tests.test_access import create, person, share
from apps.blobs import store
from apps.blobs.tests.test_blobs import content
from apps.collab import server
from apps.comments.models import Thread
from apps.documents.models import Node
from apps.exports.tests.test_noted import AT, comment, draw, encrypted, fill, noted
from apps.jobs.tests.handed import done, refused
from apps.search.tests.test_search import pdf_bytes, upload_file

pytestmark = pytest.mark.django_db


def compose(client, beside, pages, title="Složeno", status=None) -> dict:
    asked = {"title": title, "beside": beside, "pages": pages}
    if status is None:
        return done(client, "compose", **asked)
    found, error = refused(client, "compose", **asked)
    assert found == status, error
    return {"error": error}


def opened(client, node) -> pikepdf.Pdf:
    response = client.get(f"/api/nodes/{node}/file")
    assert response.status_code == 200
    pdf = pikepdf.open(io.BytesIO(content(response)))
    assert pdf.check_pdf_syntax() == []
    assert pdf.check_linearization()
    return pdf


def said(pdf) -> list[str]:
    """The line each page shows."""
    return [
        page.obj.Contents.read_bytes().decode().partition("(")[2].partition(")")[0]
        for page in pdf.pages
    ]


def room(node, name):
    return server.read(Node.objects.get(pk=node).room, lambda doc: doc.get(name, type=Map).to_py())


def saved(pdf) -> bytes:
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def bookmarked(data: bytes, links=False) -> bytes:
    """Three pages with a bookmark to each, the second by a named destination, and on the first
    page links to the third and, by that name, to the second."""
    pdf = pikepdf.open(io.BytesIO(data))
    pages = pdf.pages
    pdf.Root.Names = Dictionary(
        Dests=Dictionary(Names=Array([String("druga"), Array([pages[1].obj, Name.Fit])]))
    )
    with pdf.open_outline() as outline:
        outline.root.append(OutlineItem("Prva", 0))
        outline.root.append(OutlineItem("Druga", String("druga")))
        third = OutlineItem("Treća", Array([pages[2].obj, Name.XYZ, 0, 700, 0]))
        third.children.append(OutlineItem("Treća, dalje", Array([pages[2].obj, Name.Fit])))
        outline.root.append(third)
    if links:
        to_third = pdf.make_indirect(
            Dictionary(
                Type=Name.Annot,
                Subtype=Name.Link,
                Rect=[72, 600, 200, 620],
                Dest=Array([pages[2].obj, Name.Fit]),
            )
        )
        to_second = pdf.make_indirect(
            Dictionary(
                Type=Name.Annot,
                Subtype=Name.Link,
                Rect=[72, 560, 200, 580],
                A=Dictionary(S=Name.GoTo, D=String("druga")),
            )
        )
        web = pdf.make_indirect(
            Dictionary(
                Type=Name.Annot,
                Subtype=Name.Link,
                Rect=[72, 520, 200, 540],
                A=Dictionary(S=Name.URI, URI=String("https://example.com")),
            )
        )
        pages[0].obj.Annots = Array([to_third, to_second, web])
    return saved(pdf)


def form(*fields: tuple[str, list[int]], pages: int = 2) -> bytes:
    """Text fields by name on the pages given, a field on several pages through its kids."""
    pdf = pikepdf.open(io.BytesIO(pdf_bytes(*[f"Stranica {n}" for n in range(1, pages + 1)])))
    tops = Array()
    da = String("/Helv 0 Tf 0 g")
    for name, on in fields:

        def widget(page, **more):
            annotation = pdf.make_indirect(
                Dictionary(
                    Type=Name.Annot,
                    Subtype=Name.Widget,
                    Rect=[72, 700, 272, 720],
                    P=pdf.pages[page].obj,
                    **more,
                )
            )
            annots = pdf.pages[page].obj.get("/Annots")
            if annots is None:
                pdf.pages[page].obj.Annots = Array([annotation])
            else:
                annots.append(annotation)
            return annotation

        if len(on) == 1:
            tops.append(widget(on[0], FT=Name.Tx, T=String(name), DA=da))
            continue
        field = pdf.make_indirect(Dictionary(FT=Name.Tx, T=String(name), DA=da, Kids=Array()))
        for page in on:
            field.Kids.append(widget(page, Parent=field))
        tops.append(field)
    helv = Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)
    pdf.Root.AcroForm = Dictionary(
        Fields=tops, DR=Dictionary(Font=Dictionary(Helv=helv)), DA=da, NeedAppearances=True
    )
    return saved(pdf)


def field_names(pdf) -> dict[str, list[int]]:
    """Each field's full name and the pages its widgets lie on."""
    found = {}
    pages = {page.obj.objgen: index for index, page in enumerate(pdf.pages)}
    for field in pdf.Root.AcroForm.Fields:
        kids = field.get("/Kids") or [field]
        found[str(field.T)] = sorted(pages[kid.P.objgen] for kid in kids)
    return found


def test_pages_are_taken_in_the_order_given_turned_and_beside_the_file(api):
    folder = create(api, "folder", "Ugovori")
    data = pdf_bytes("Jedan", "Dva", "Tri")
    file = upload_file(api, "Ugovor", data, parent=folder)
    made = compose(
        api, file, [{"file": file, "page": 3, "turn": 1}, {"file": file, "page": 1}], "Izvadak"
    )
    assert (made["kind"], made["title"], made["parent"]) == ("file", "Izvadak", folder)
    with opened(api, made["id"]) as pdf:
        assert said(pdf) == ["Tri", "Jedan"]
        assert [page.obj.get("/Rotate") for page in pdf.pages] == [90, None]
    original = Node.objects.get(pk=file).blob_id
    assert store.path_of(original).read_bytes() == data


def test_turns_add_to_a_page_already_turned(api):
    pdf = pikepdf.open(io.BytesIO(pdf_bytes("Prva")))
    pdf.pages[0].obj.Rotate = 270
    file = upload_file(api, "Skenirano", saved(pdf))
    made = compose(api, file, [{"file": file, "page": 1, "turn": 1}])
    with opened(api, made["id"]) as composed:
        assert composed.pages[0].obj.Rotate == 0


def test_files_are_joined_whole_with_their_bookmarks_under_their_names(api):
    first = upload_file(api, "Ponuda", bookmarked(pdf_bytes("Jedan", "Dva", "Tri")))
    second = upload_file(api, "Prilog", pdf_bytes("Jedan", "Dva"))
    made = compose(api, first, [{"file": first}, {"file": second}])
    with opened(api, made["id"]) as pdf:
        assert len(pdf.pages) == 5
        pages = {page.obj.objgen: index for index, page in enumerate(pdf.pages)}
        with pdf.open_outline() as outline:
            tops = [(item.title, pages[item.destination[0].objgen]) for item in outline.root]
            inner = [
                (item.title, pages[item.destination[0].objgen]) for item in outline.root[0].children
            ]
        assert tops == [("Ponuda", 0), ("Prilog", 3)]
        assert inner == [("Prva", 0), ("Druga", 1), ("Treća", 2)]


def test_bookmarks_and_links_follow_the_pages_kept(api):
    file = upload_file(api, "Ponuda", bookmarked(pdf_bytes("Jedan", "Dva", "Tri"), links=True))
    made = compose(api, file, [{"file": file, "page": 3}, {"file": file, "page": 1}])
    with opened(api, made["id"]) as pdf:
        pages = {page.obj.objgen: index for index, page in enumerate(pdf.pages)}
        with pdf.open_outline() as outline:
            items = [
                (item.title, pages[item.destination[0].objgen], list(item.destination)[1:])
                for item in outline.root
            ]
            assert [child.title for child in outline.root[1].children] == ["Treća, dalje"]
        assert [(title, page) for title, page, _ in items] == [("Prva", 1), ("Treća", 0)]
        assert items[1][2] == [Name.XYZ, 0, 700, 0]
        links = pdf.pages[1].obj.Annots
        assert len(links) == 2
        assert pages[links[0].Dest[0].objgen] == 0
        assert "/A" not in links[0]
        assert links[1].A.S == Name.URI
        assert "/Names" not in pdf.Root


def test_a_form_keeps_its_fields_and_values_and_two_files_fields_of_one_name_are_told_apart(api):
    first = upload_file(api, "Prijava", form(("Ime", [0]), ("Datum", [0, 1])))
    second = upload_file(api, "Dodatak", form(("Ime", [0]), pages=1))
    fill(first, {"Ime": {"value": "Ana"}, "Datum": {"value": "1.1.2026.", "shown": "1. 1. 2026."}})
    fill(second, {"Ime": {"value": "Iva"}})
    pages = [
        {"file": first, "page": 2},
        {"file": first, "page": 1},
        {"file": second, "page": 1},
        {"file": first, "page": 1},
    ]
    made = compose(api, first, pages)
    with opened(api, made["id"]) as pdf:
        assert field_names(pdf) == {
            "Datum": [0, 1],
            "Ime": [1],
            "Ime+1": [2],
            "Ime+2": [3],
            "Datum+1": [3],
        }
        assert pdf.Root.AcroForm.NeedAppearances
        assert "/Helv" in pdf.Root.AcroForm.DR.Font
    assert room(made["id"], "fields") == {
        "Ime": {"value": "Ana"},
        "Datum": {"value": "1.1.2026.", "shown": "1. 1. 2026."},
        "Ime+1": {"value": "Iva"},
        "Ime+2": {"value": "Ana"},
        "Datum+1": {"value": "1.1.2026.", "shown": "1. 1. 2026."},
    }
    with pikepdf.open(io.BytesIO(noted(api, made["id"]))) as written:
        values = {str(field.T): str(field.get("/V", "")) for field in written.Root.AcroForm.Fields}
        assert values["Ime+1"] == "Iva"


def test_a_field_left_behind_takes_its_value_with_it(api):
    file = upload_file(api, "Prijava", form(("Ime", [0]), ("Grad", [1])))
    fill(file, {"Ime": {"value": "Ana"}, "Grad": {"value": "Split"}})
    made = compose(api, file, [{"file": file, "page": 2}])
    with opened(api, made["id"]) as pdf:
        assert field_names(pdf) == {"Grad": [0]}
    assert room(made["id"], "fields") == {"Grad": {"value": "Split"}}


def test_notes_go_with_their_pages_and_threads_stay_with_the_file(api):
    file = upload_file(api, "Ugovor", pdf_bytes("Jedan", "Dva", "Tri"))
    stroke = {"kind": "stroke", "color": "red", "width": 2, "points": [1, 2, 3, 4], "by": None}
    draw(file, a={**stroke, "page": 1, "at": AT}, b={**stroke, "page": 3, "at": AT})
    comment(api, file, {"page": 3, "at": [72, 760]}, "", "Provjeriti?")
    made = compose(api, file, [{"file": file, "page": 3}, {"file": file, "page": 2}])
    marks = list(room(made["id"], "marks").values())
    assert marks == [{**stroke, "page": 1, "at": AT}]
    assert not Thread.objects.filter(file_id=made["id"]).exists()
    assert Thread.objects.filter(file_id=file).count() == 1


def test_hidden_layers_stay_hidden(api):
    pdf = pikepdf.open(io.BytesIO(pdf_bytes("Prva")))
    shown = pdf.make_indirect(Dictionary(Type=Name.OCG, Name=String("Tekst")))
    hidden = pdf.make_indirect(Dictionary(Type=Name.OCG, Name=String("Bilješke")))
    pdf.Root.OCProperties = Dictionary(
        OCGs=Array([shown, hidden]), D=Dictionary(BaseState=Name.OFF, ON=Array([shown]))
    )
    file = upload_file(api, "Nacrt", saved(pdf))
    made = compose(api, file, [{"file": file}])
    with opened(api, made["id"]) as composed:
        layers = composed.Root.OCProperties
        assert [str(group.Name) for group in layers.OCGs] == ["Tekst", "Bilješke"]
        assert [str(group.Name) for group in layers.D.OFF] == ["Bilješke"]


@pytest.mark.parametrize(
    "entries",
    [
        [],
        [{"file": "nije-id", "page": 1}],
        [{"page": 1}],
        [{"file": "@", "page": 0}],
        [{"file": "@", "page": 4}],
        [{"file": "@", "page": True}],
        [{"file": "@", "page": 1, "turn": 4}],
        [{"file": "@", "page": 1, "turn": -1}],
        [{"file": "@", "page": 1, "zoom": 2}],
    ],
)
def test_pages_not_as_given_are_refused(api, entries):
    file = upload_file(api, "Ugovor", pdf_bytes("Jedan", "Dva", "Tri"))
    pages = [{**entry, "file": file} if entry.get("file") == "@" else entry for entry in entries]
    assert compose(api, file, pages, status=400)["error"] in {"invalid_pages", "invalid_id"}


def test_only_files_one_may_read_give_pages(api):
    file = upload_file(api, "Ugovor", pdf_bytes("Prva"))
    document = create(api, "document", "Bilješka")
    other = person("ana@example.com")
    theirs = upload_file(other, "Tuđe", pdf_bytes("Tude"))
    assert compose(api, file, [{"file": document}], status=400)["error"] == "not_a_file"
    assert compose(api, file, [{"file": theirs}], status=404)["error"] == "not_found"
    assert compose(api, theirs, [{"file": file}], status=404)["error"] == "not_found"


def test_files_that_cannot_be_put_together_anew_say_why(api):
    locked = upload_file(api, "Zaključano", encrypted(owner="tajna", user="tajna"))
    out = io.BytesIO()
    with pikepdf.open(io.BytesIO(pdf_bytes("Izvod"))) as pdf:
        permissions = pikepdf.Permissions(modify_assembly=False)
        pdf.save(out, encryption=pikepdf.Encryption(owner="banka", user="", allow=permissions))
    fixed = upload_file(api, "Izvod", out.getvalue())
    assert compose(api, locked, [{"file": locked}], status=409)["error"] == "locked"
    assert compose(api, fixed, [{"file": fixed}], status=409)["error"] == "assembly_forbidden"


def test_a_file_composed_where_one_may_not_add_lands_among_ones_own(api):
    folder = create(api, "folder", "Arhiva")
    file = upload_file(api, "Ugovor", pdf_bytes("Prva"), parent=folder)
    ana = person("ana@example.com")
    share(api, folder, "read", id=ana.user.pk)
    made = compose(ana, file, [{"file": file}])
    assert made["parent"] is None
    assert Grant.objects.filter(node_id=made["id"], user=ana.user, role=Role.OWN).exists()
