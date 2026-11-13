import pytest
from django.utils import timezone
from pycrdt import Doc

from apps.blobs import store
from apps.blobs.models import Blob
from apps.collab.models import Update
from apps.content import elements, slides
from apps.content.blocks import Block, Grid, Run
from apps.content.models import DocumentBlob
from apps.documents.models import Node
from apps.versions.history import state_of

from .helpers import fill
from .test_elements import first_tab

pytestmark = pytest.mark.django_db

TABLE = Grid(["r1", "r2"], ["a", "b"], texts={"r1:a": "Šifra", "r1:b": "Cijena", "r2:a": "0042"})


def measured(document_id) -> tuple[int, str]:
    node = Node.objects.get(pk=document_id)
    return node.content_size, node.holds


def test_a_document_takes_its_state_its_rows_and_what_it_shows(api, upload):
    tab = first_tab(api)
    fill(tab, [Block("paragraph", runs=[Run("Rok isporuke je 30 dana.")])])
    elements.derive(tab.pk)
    text, holds = measured(tab.document_id)
    assert holds == Node.Holds.TEXT

    fill(
        tab,
        [
            Block("paragraph", runs=[Run("Rok isporuke je 30 dana.")]),
            Block("table", "t", grid=TABLE),
        ],
    )
    elements.derive(tab.pk)
    tabled, _ = measured(tab.document_id)
    assert tabled > text

    shown = Blob.objects.get(pk=upload(b"%PDF-1.4 ponuda")["sha256"])
    DocumentBlob.objects.create(document_id=tab.document_id, blob=shown)
    elements.derive(tab.pk)
    assert measured(tab.document_id) == (tabled + shown.size, Node.Holds.TEXT)


def test_a_first_tab_of_tables_alone_holds_a_table(api):
    tab = first_tab(api)
    fill(tab, [Block("table", "t", grid=TABLE)])
    elements.derive(tab.pk)
    assert measured(tab.document_id)[1] == Node.Holds.TABLE


def test_a_document_with_slide_layouts_of_its_own_holds_slides(api):
    tab = first_tab(api)
    fill(tab, [Block("table", "t", grid=TABLE)])
    document = tab.document
    own = Doc()
    own.apply_update(state_of(document.room))
    before = own.get_state()
    width, height = slides.BUILT_IN["size"]["width"], slides.BUILT_IN["size"]["height"]
    slides.write(own, {"width": width, "height": height, "layouts": slides.built_in(width, height)})
    Update.objects.create(document=document, room=document.room, data=own.get_update(before))
    elements.derive(tab.pk)
    assert measured(document.pk)[1] == Node.Holds.SLIDES


def test_a_document_is_described_by_what_it_holds_and_the_file_it_came_from(api):
    tab = first_tab(api)
    fill(tab, [Block("table", "t", grid=TABLE)])
    elements.derive(tab.pk)
    source = Blob.objects.create(
        sha256="cd" * 32, size=14_600, media_type=store.XLSX, uploaded_at=timezone.now()
    )
    Node.objects.filter(pk=tab.document_id).update(source=source)
    node = api.get(f"/api/nodes/{tab.document_id}").json()["node"]
    assert (node["size"], node["holds"]) == measured(tab.document_id)
    assert node["origin"] == {"extension": "xlsx", "size": 14_600}
