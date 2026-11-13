import io

import pytest
from asgiref.sync import sync_to_async
from django.test import Client

from apps.actions.tests.test_actions import signed_in
from apps.blobs import store
from apps.content import blocks
from apps.content.blocks import Block, Run
from apps.content.sheets import Refused
from apps.content.tests.helpers import Room, fill
from apps.content.tests.test_elements import first_tab
from apps.documents.tests.test_views import create
from apps.imports.tests.word_files import p, word_file
from apps.users.models import User
from apps.versions.compared import operations

JSON = "application/json"
TABLE = '<w:tbl><w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid>{rows}</w:tbl>'
CONTENT = [
    Block("title", "t0", runs=[Run("Ugovor o najmu")]),
    Block("paragraph", "a", runs=[Run("Najam stana traje godinu dana.")]),
    Block("paragraph", "e"),
    Block("paragraph", "b", runs=[Run("Cijena je 500 eura mjesečno.")]),
    Block("paragraph", "c", runs=[Run("Ugovor se može raskinuti uz otkazni rok.")]),
]


def said(*texts: str) -> list[Block]:
    return [Block("paragraph", runs=[Run(text)]) for text in texts]


def test_the_same_text_proposes_nothing_whatever_its_spaces_and_empty_paragraphs():
    other = said(
        "Ugovor o najmu",
        "Najam  stana traje godinu dana. ",
        "Cijena je 500 eura mjesečno.",
        "",
        "Ugovor se može raskinuti uz otkazni rok.",
    )
    assert operations(CONTENT, other) == []


def test_a_changed_block_is_rewritten_a_missing_one_deleted_and_a_new_one_put_where_it_stands():
    other = said(
        "Ugovor o najmu",
        "Najam stana traje dvije godine.",
        "Ugovor se može raskinuti uz otkazni rok.",
        "Sporove rješava sud u Zagrebu.",
    )
    other.insert(0, Block("heading", attrs={"level": 2, "style": "Their"}, runs=[Run("Stranke")]))

    planned = operations(CONTENT, other)

    inserted = planned[0]["blocks"][0]
    assert planned[0] == {"op": "insert", "at": {"before": "t0"}, "blocks": [inserted]}
    assert inserted["type"] == "heading"
    assert inserted["attrs"] == {"level": 2, "id": inserted["attrs"]["id"]}
    assert planned[1:3] == [
        {"op": "rewrite", "block": "a", "text": "Najam stana traje dvije godine."},
        {"op": "delete", "from": "b"},
    ]
    assert planned[3]["at"] == {"after": "c"}
    assert planned[3]["blocks"][0]["content"] == [
        {"type": "text", "text": "Sporove rješava sud u Zagrebu."}
    ]
    assert len(planned) == 4


def test_new_blocks_in_a_row_are_one_proposal_and_keep_only_their_emphasis():
    bold = Run("Jamčevina", {"strong": {}, "color": {"value": "#ff0000"}})
    other = [
        *said("Ugovor o najmu", "Najam stana traje godinu dana."),
        Block("paragraph", attrs={"list": "bullet", "format": "f9"}, runs=[bold]),
        *said("Jamčevina se vraća.", "Cijena je 500 eura mjesečno."),
        *said("Ugovor se može raskinuti uz otkazni rok."),
    ]

    (planned,) = operations(CONTENT, other)

    assert planned["at"] == {"after": "a"}
    first, second = planned["blocks"]
    assert first["attrs"] == {"list": "bullet", "id": first["attrs"]["id"]}
    assert first["content"] == [
        {"type": "text", "text": "Jamčevina", "marks": [{"type": "strong", "attrs": {}}]}
    ]
    assert second["content"] == [{"type": "text", "text": "Jamčevina se vraća."}]


def test_a_changed_table_goes_out_and_its_new_rows_come_in_after_it():
    def table(price: str) -> Block:
        texts = {"r1:c1": "Stavka", "r1:c2": "Iznos", "r2:c1": "Najam", "r2:c2": price}
        cells = [blocks.light_cell(key, text) for key, text in texts.items()]
        return Block("table", "t", grid=blocks.Grid(["r1", "r2"], ["c1", "c2"]), cells=cells)

    planned = operations([*CONTENT[:2], table("500")], [*CONTENT[:2], table("600")])

    assert planned[0] == {"op": "delete", "from": "t"}
    assert planned[1]["op"] == "table"
    assert planned[1]["at"] == {"after": "t"}
    assert planned[1]["rows"] == [["Stavka", "Iznos"], ["Najam", "600"]]


def test_a_tab_with_proposals_is_reviewed_before_it_is_compared():
    proposed = Run(
        "stana", {"insertion": {"id": "x", "author": "Ana", "date": "2026-11-10T10:00:00Z"}}
    )
    with pytest.raises(Refused) as refused:
        operations([Block("paragraph", "a", runs=[Run("Najam "), proposed])], said("Najam"))
    assert (refused.value.code, refused.value.detail) == ("proposed", "a")


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_word_file_beside_the_document_comes_in_as_proposals_under_its_name(live):
    browser, tab = await signed_in()
    await sync_to_async(fill)(tab, CONTENT)
    data = word_file(
        p("Ugovor o najmu")
        + p("Najam stana traje dvije godine.")
        + p("Cijena je 500 eura mjesečno.")
        + p("Ugovor se može raskinuti uz otkazni rok.")
        + p("Sporove rješava sud u Zagrebu.")
    )
    blob = await sync_to_async(store.put)(io.BytesIO(data))
    fields = {"kind": "file", "title": "Ugovor partnera", "blob": blob.sha256, "extension": "docx"}
    file = (await browser.post("/api/nodes", fields, content_type=JSON)).json()["id"]
    run = {"action": "file.compare", "target": {}, "parameters": {"file": file}}

    response = await browser.post(f"/api/tabs/{tab.pk}/runs", run, content_type=JSON)

    assert response.status_code == 201, response.json()
    found = (await sync_to_async(Room.of)(tab)).read()
    authors = {
        each.marks[name]["author"]
        for block in found
        for each in block.runs
        for name in ("insertion", "deletion")
        if name in each.marks
    }
    assert authors == {"Ugovor partnera.docx"}
    accept = {"action": "document.accept", "target": {}}
    accepted = await browser.post(f"/api/tabs/{tab.pk}/runs", accept, content_type=JSON)
    assert accepted.status_code == 201, accepted.json()
    found = (await sync_to_async(Room.of)(tab)).read()
    assert [block.text for block in found if block.text] == [
        "Ugovor o najmu",
        "Najam stana traje dvije godine.",
        "Cijena je 500 eura mjesečno.",
        "Ugovor se može raskinuti uz otkazni rok.",
        "Sporove rješava sud u Zagrebu.",
    ]
    again = await browser.post(f"/api/tabs/{tab.pk}/runs", run, content_type=JSON)
    assert (again.status_code, again.json()["error"]) == (422, "same_as_file")


@pytest.mark.django_db
def test_only_a_text_the_user_reads_is_compared(api):
    tab = first_tab(api)
    fill(tab, CONTENT)
    sheet = create(api, "file", "Popis", blob=store.put(io.BytesIO(b"a;b\n1;2\n")).sha256)
    run = {"action": "file.compare", "target": {}, "parameters": {"file": sheet}}
    response = api.post(f"/api/tabs/{tab.pk}/runs", run, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (422, "not_comparable")
    stranger = User.objects.create_user("eva@example.com", "Kamen-Most-Rijeka-72")
    browser = Client()
    browser.force_login(stranger)
    theirs = create(browser, "document", "Tuđi")
    run["parameters"]["file"] = theirs
    assert api.post(f"/api/tabs/{tab.pk}/runs", run, content_type=JSON).status_code == 404
