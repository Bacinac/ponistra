import uuid

import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncClient

from apps.actions import batches, runs
from apps.actions.gathering import extract, row_of, table, text_in
from apps.actions.models import ActionRun, RunItem
from apps.actions.tests.test_actions import signed_in
from apps.ai import installation, model
from apps.ai.reading import text_of
from apps.ai.tests.recorded import Recorded, message, said, used
from apps.content.blocks import Block, Run
from apps.content.operations import Refused
from apps.content.tests.helpers import Room, fill
from apps.core.asyncdb import database
from apps.documents.models import Node, Tab
from apps.documents.printing import compact
from apps.search.tests.test_search import extract_all, pdf_bytes, upload_file
from apps.users.models import User

JSON = "application/json"
LEASE = [
    Block("title", "t0", runs=[Run("Ugovor o najmu")]),
    Block("paragraph", "a", runs=[Run("Najmoprimac: Ana Horvat")]),
    Block("paragraph", "b", runs=[Run("Najamnina: 750,50 EUR mjesečno")]),
]
CHOSEN = [
    {"column": "Najmoprimac", "value": "Ana Horvat"},
    {"column": "Najamnina (EUR)", "value": "750,5"},
]


def test_a_row_is_asked_under_the_columns_given_or_those_the_first_document_chooses():
    fixed = extract("[a] paragraph: Najam", ["Najmoprimac", "Najamnina (EUR)"], "hr")
    assert "Its cells are, in this order: Najmoprimac; Najamnina (EUR)." in fixed.instruction
    assert "(hr)" in fixed.instruction and fixed.content == "[a] paragraph: Najam"
    cells = fixed.tools["row"].schema["properties"]["cells"]
    assert (cells["items"], cells["minItems"], cells["maxItems"]) == ({"type": "string"}, 2, 2)
    chosen = extract("[a] paragraph: Najam", [], "en")
    assert "Choose the table's columns" in chosen.instruction and "(en)" in chosen.instruction
    assert chosen.tools["row"].schema["properties"]["cells"]["maxItems"] == 12
    assert row_of({"cells": CHOSEN}, []) == (
        ["Najmoprimac", "Najamnina (EUR)"],
        ["Ana Horvat", "750,5"],
    )
    assert row_of({"cells": ["Ivo", ""]}, ["A", "B"]) == (["A", "B"], ["Ivo", ""])


def test_the_table_heads_its_columns_after_the_source_whose_cells_link_to_each_document():
    document = Node(pk=uuid.uuid4(), kind=Node.Kind.DOCUMENT)
    file = Node(pk=uuid.uuid4(), kind=Node.Kind.FILE)
    rows = [(document, "Ugovor A", ["Ana", "750,5"]), (file, "Ponuda.pdf", ["", "10"])]
    rows.append((None, "Obrisan", ["Ivo", "1"]))
    made = table(rows, ["Najmoprimac", "Najamnina (EUR)"], "hr")
    assert (made["op"], made["at"]) == ("table", {"start": "body"})
    header, *body = made["rows"]
    assert header == ["Dokument", "Najmoprimac", "Najamnina (EUR)"]
    links = [cell["blocks"][0]["content"][0].get("marks") for cell, *_ in body]
    assert links == [
        [{"type": "link", "attrs": {"href": f"/d/{compact(document.pk)}"}}],
        [{"type": "link", "attrs": {"href": f"/p/{compact(file.pk)}"}}],
        None,
    ]
    assert [values for _, *values in body] == [["Ana", "750,5"], [None, "10"], ["Ivo", "1"]]
    assert table(rows, ["A", "B"], "en")["rows"][0][0] == "Document"


@pytest.mark.django_db
def test_what_is_read_of_a_document_goes_tab_by_tab_and_of_a_pdf_page_by_page(api):
    folder = Node.objects.get(pk=create(api, "folder", "Ugovori"))
    document = Node.objects.get(pk=create(api, "document", "Najam", folder.pk))
    fill(document.tabs.get(), LEASE)
    assert text_in(document, api.user) == text_of(Room.of(document.tabs.get()).read())
    second = api.post(f"/api/nodes/{document.pk}/tabs", {"title": "Prilog"}, content_type=JSON)
    fill(Tab.objects.get(pk=second.json()["id"]), [Block("paragraph", "p", runs=[Run("Ključ")])])
    read = text_in(document, api.user)
    assert read.startswith("[tab 1]\n[t0] title: Ugovor o najmu")
    assert read.endswith("\n\n[tab Prilog]\n[p] paragraph: Ključ")
    file = Node.objects.get(pk=upload_file(api, "Ponuda", pdf_bytes("Predmet", "", "Cijena 10")))
    extract_all()
    assert text_in(file, api.user) == "[page 1]\nPredmet\n\n[page 3]\nCijena 10"
    empty = Node.objects.get(pk=create(api, "document", "Prazan", folder.pk))
    for node, code in [(empty, "empty"), (None, "not_found")]:
        with pytest.raises(Refused) as refused:
            text_in(node, api.user)
        assert refused.value.code == code
    stranger = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-71")
    with pytest.raises(Refused) as refused:
        text_in(document, stranger)
    assert refused.value.code == "not_found"


@pytest.mark.django_db
def test_a_run_over_a_folder_takes_its_documents_and_pdfs_but_no_image(api, upload):
    folder = create(api, "folder", "Ponude")
    document = create(api, "document", "Ponuda", folder)
    files = {}
    for title, data in [("Cjenik", pdf_bytes("Cijena")), ("Logo", b"\x89PNG\r\n\x1a\n")]:
        fields = {"kind": "file", "title": title, "parent": folder}
        fields["blob"] = upload(data)["sha256"]
        files[title] = api.post("/api/nodes", fields, content_type=JSON).json()["id"]
    nodes = Node.objects.filter(pk__in=[folder, files["Logo"]])
    taken = [str(node.pk) for node in batches.items_of(list(nodes))]
    assert taken == [files["Cjenik"], document]


def create(api, kind: str, title: str, parent=None) -> str:
    response = api.post(
        "/api/nodes",
        {"kind": kind, "title": title, "parent": parent and str(parent)},
        content_type=JSON,
    )
    assert response.status_code == 201, response.json()
    return response.json()["id"]


async def made(browser: AsyncClient, kind: str, title: str, parent=None, content=None) -> str:
    response = await browser.post(
        "/api/nodes", {"kind": kind, "title": title, "parent": parent}, content_type=JSON
    )
    assert response.status_code == 201, response.json()
    node = response.json()["id"]
    if content is not None:
        await sync_to_async(fill)(await Tab.objects.aget(document_id=node), content)
    return node


async def gathering(monkeypatch, *answers) -> tuple[AsyncClient, Recorded]:
    browser, _ = await signed_in()
    monkeypatch.setattr(installation, "enabled", lambda: True)
    recorded = Recorded(*answers)
    monkeypatch.setattr(model, "answer", recorded)
    return browser, recorded


async def gathered(browser: AsyncClient, nodes: list[str], **parameters) -> dict:
    response = await browser.post(
        "/api/runs",
        {
            "action": "nodes.extract",
            "target": {"nodes": nodes},
            "parameters": {"title": "Pregled", **parameters},
            "consent": "once",
        },
        content_type=JSON,
    )
    assert response.status_code == 202, response.json()
    return response.json()


async def drained() -> None:
    while await database(batches.step, own_thread=True)():
        pass


def lease(tenant: str, rent: str) -> list[Block]:
    return [
        Block("title", "t0", runs=[Run("Ugovor o najmu")]),
        Block("paragraph", "a", runs=[Run(f"Najmoprimac: {tenant}")]),
        Block("paragraph", "b", runs=[Run(f"Najamnina: {rent} EUR")]),
    ]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_run_over_a_folder_gathers_a_row_of_each_document_into_a_new_one_beside_them(
    live, monkeypatch
):
    browser, recorded = await gathering(
        monkeypatch,
        message("tool_use", used("u1", "row", {"cells": CHOSEN})),
        message("tool_use", used("u2", "row", {"cells": ["Ivo Bošković", ""]})),
        message("refusal", details={"type": "refusal", "category": "cyber"}),
    )
    folder = await made(browser, "folder", "Ugovori")
    first = await made(browser, "document", "Ugovor A", folder, lease("Ana Horvat", "750,50"))
    second = await made(browser, "document", "Ugovor B", folder, lease("Ivo Bošković", "?"))
    empty = await made(browser, "document", "Prazan", folder)
    older = await made(browser, "folder", "Stari", folder)
    await made(browser, "document", "Ugovor C", older, lease("Marko", "500"))
    started = await gathered(browser, [first, second, empty, older])
    run, document = started["run"], started["document"]
    assert (document["title"], document["parent"], document["kind"]) == (
        "Pregled",
        folder,
        "document",
    )
    assert (run["state"], run["items"]) == ("running", {"of": 4, "through": 0, "missed": []})
    await drained()
    finished = await ActionRun.objects.aget(pk=run["id"])
    assert (finished.state, finished.error, finished.model) == ("done", "", "claude-sonnet-5-5")
    assert (finished.consent, finished.consented_by_id) == ("once", finished.user_id)
    assert (finished.input_tokens, finished.output_tokens) == (3, 3)
    assert finished.parameters == {
        "title": "Pregled",
        "columns": ["Najmoprimac", "Najamnina (EUR)"],
    }
    assert len(recorded.asked) == 3
    assert "Najmoprimac: Ana Horvat" in recorded.asked[0]["messages"][0]["content"]
    assert "Choose the table's columns" in recorded.asked[0]["system"][0]["text"]
    assert "in this order: Najmoprimac; Najamnina (EUR)." in recorded.asked[1]["system"][0]["text"]
    assert "Marko" in recorded.asked[2]["messages"][0]["content"]
    tab = await Tab.objects.aget(document_id=document["id"])
    lines = text_of((await sync_to_async(Room.of)(tab)).read()).splitlines()
    assert lines[1:4] == [
        "| Dokument | Najmoprimac | Najamnina (EUR) |",
        "| Ugovor A | Ana Horvat | 750,5 |",
        "| Ugovor B | Ivo Bošković |  |",
    ]
    described = (await browser.get(f"/api/runs/{run['id']}")).json()["run"]
    assert (described["state"], described["changed"]) == ("done", True)
    assert described["items"] == {
        "of": 4,
        "through": 4,
        "missed": [
            {"title": "Prazan", "error": "empty"},
            {"title": "Ugovor C", "error": "refused"},
        ],
    }
    response = await browser.post(f"/api/runs/{run['id']}/undo")
    assert response.status_code == 200 and response.json()["run"]["state"] == "undone"
    assert (await Node.objects.aget(pk=document["id"])).trashed_at is not None
    assert (await Node.objects.aget(pk=first)).trashed_at is None


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_stopped_run_writes_what_it_found_and_a_failing_model_misses_the_rest(
    live, monkeypatch
):
    browser, recorded = await gathering(
        monkeypatch,
        message("tool_use", used("u1", "row", {"cells": ["Ana Horvat"]})),
        model.Failed("rate_limited", "429 Too many requests"),
    )
    folder = await made(browser, "folder", "Ugovori")
    documents = [
        await made(browser, "document", f"Ugovor {each}", folder, lease(each, "1"))
        for each in "ABC"
    ]
    run = (await gathered(browser, documents, columns=["Najmoprimac"]))["run"]
    assert await database(batches.step, own_thread=True)()
    assert (await browser.post(f"/api/runs/{run['id']}/stop")).status_code == 200
    await drained()
    stopped = await ActionRun.objects.aget(pk=run["id"])
    assert stopped.state == "stopped" and len(recorded.asked) == 1
    states = [item.state async for item in RunItem.objects.filter(run=stopped).order_by("position")]
    assert states == ["done", "skipped", "skipped"]
    described = (await browser.get(f"/api/runs/{run['id']}")).json()["run"]
    assert described["items"] == {"of": 3, "through": 3, "missed": []}
    tab = await Tab.objects.select_related("document").aget(document_id=stopped.document_id)
    lines = text_of((await sync_to_async(Room.of)(tab)).read()).splitlines()
    assert lines[1:3] == ["| Dokument | Najmoprimac |", "| Ugovor A | Ana Horvat |"]
    failing = (await gathered(browser, documents, columns=["Najmoprimac"]))["run"]
    await drained()
    failed = await ActionRun.objects.aget(pk=failing["id"])
    assert (failed.state, failed.error) == ("failed", "rate_limited")
    described = (await browser.get(f"/api/runs/{failing['id']}")).json()["run"]
    assert [each["error"] for each in described["items"]["missed"]] == ["rate_limited"] * 3
    assert (await browser.post(f"/api/runs/{failing['id']}/undo")).status_code == 404
    assert (await Node.objects.aget(pk=failed.document_id)).trashed_at is not None
    assert (await Node.objects.aget(pk=stopped.document_id)).trashed_at is None


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_model_s_answer_without_a_row_misses_the_document_and_a_restart_carries_on(
    live, monkeypatch
):
    browser, recorded = await gathering(
        monkeypatch,
        message("end_turn", said("Ne mogu.")),
        message("tool_use", used("u1", "row", {"cells": ["Ivo"]})),
    )
    folder = await made(browser, "folder", "Ugovori")
    documents = [
        await made(browser, "document", f"Ugovor {each}", folder, lease(each, "1")) for each in "AB"
    ]
    run = (await gathered(browser, documents, columns=["Najmoprimac"]))["run"]
    claimed = await database(batches.claim)()
    assert claimed.position == 0 and await database(batches.claim)() is not None
    await database(runs.interrupted)()
    assert (await ActionRun.objects.aget(pk=run["id"])).state == "running"
    assert not await RunItem.objects.exclude(started_at=None).aexists()
    await drained()
    done = await ActionRun.objects.aget(pk=run["id"])
    assert done.state == "done" and len(recorded.asked) == 2
    described = (await browser.get(f"/api/runs/{run['id']}")).json()["run"]
    assert described["items"]["missed"] == [{"title": "Ugovor A", "error": "no_answer"}]


@pytest.mark.django_db
def test_a_run_over_documents_waits_for_ai_and_consent_and_writes_beside_them(api, monkeypatch):
    folder = create(api, "folder", "Ugovori")
    document = create(api, "document", "Ugovor", folder)
    empty = create(api, "folder", "Prazna", folder)
    elsewhere = create(api, "document", "Drugdje")
    asked = {
        "action": "nodes.extract",
        "target": {"nodes": [document]},
        "parameters": {"title": "Pregled"},
        "consent": "once",
    }

    def refused(**changed) -> tuple[int, str]:
        response = api.post("/api/runs", asked | changed, content_type=JSON)
        return response.status_code, response.json()["error"]

    assert refused() == (409, "ai_off")
    monkeypatch.setattr(installation, "enabled", lambda: True)
    assert refused(action="text.summarise") == (404, "unknown_action")
    assert refused(consent=None) == (428, "consent_needed")
    assert refused(target={"nodes": []}) == (400, "invalid_target")
    assert refused(parameters={"title": "Pregled", "columns": []}) == (400, "invalid_parameters")
    assert refused(parameters={"title": "   "}) == (400, "invalid_title")
    assert refused(target={"nodes": [empty]}) == (422, "empty")
    assert refused(target={"nodes": [str(uuid.uuid4())]}) == (404, "not_found")
    tab = Tab.objects.get(document_id=document)
    response = api.post(
        f"/api/tabs/{tab.pk}/runs", {k: asked[k] for k in ("action", "target")}, content_type=JSON
    )
    assert (response.status_code, response.json()["error"]) == (404, "unknown_action")
    assert not ActionRun.objects.exists()
    assert Node.objects.filter(title="Pregled").count() == 0
    response = api.post(
        "/api/runs", asked | {"target": {"nodes": [document, elsewhere]}}, content_type=JSON
    )
    assert response.status_code == 202
    assert response.json()["document"]["parent"] is None
    response = api.post("/api/runs", asked, content_type=JSON)
    assert response.json()["document"]["parent"] == folder
