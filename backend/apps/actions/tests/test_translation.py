import pytest
from asgiref.sync import sync_to_async
from django.test import Client

from apps.actions import batches, translation
from apps.actions.models import ActionRun
from apps.actions.tests.test_gathering import drained, gathering, made
from apps.ai.reading import text_of
from apps.ai.tests.recorded import message, used
from apps.content.tests.helpers import Room
from apps.documents.models import Node, Tab
from apps.search.tests.test_search import extract_all, pdf_bytes, upload_file
from apps.users.models import User

JSON = "application/json"


def page(continues: bool, *blocks: dict) -> dict:
    return message("tool_use", used("u1", "page", {"continues": continues, "blocks": list(blocks)}))


def test_a_paragraph_a_page_break_cut_is_joined_and_a_table_keeps_its_rows_even():
    found = [
        {"continues": False, "blocks": [{"kind": "heading1", "text": "Ponuda"}]},
        {"continues": False, "blocks": [{"kind": "bullet", "text": "Rok:\n 30   dana"}]},
        {
            "continues": True,
            "blocks": [
                {"kind": "paragraph", "text": "od narudžbe."},
                {"kind": "table", "rows": [["Cijena", "100 EUR"], ["Ukupno"], [" "]]},
                {"kind": "paragraph", "text": " "},
                {"kind": "number", "text": "Prvo"},
            ],
        },
    ]
    assert translation.written(found) == [
        {
            "op": "insert",
            "at": {"end": "body"},
            "blocks": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "Ponuda"}],
                },
                {
                    "type": "paragraph",
                    "attrs": {"list": "bullet"},
                    "content": [{"type": "text", "text": "Rok: 30 dana od narudžbe."}],
                },
            ],
        },
        {"op": "table", "at": {"end": "body"}, "rows": [["Cijena", "100 EUR"], ["Ukupno", None]]},
        {
            "op": "insert",
            "at": {"end": "body"},
            "blocks": [
                {
                    "type": "paragraph",
                    "attrs": {"list": "number"},
                    "content": [{"type": "text", "text": "Prvo"}],
                }
            ],
        },
    ]


def uploaded_pdf(*pages: str) -> str:
    client = Client()
    client.force_login(User.objects.get(email="ivo@example.com"))
    node = upload_file(client, "Angebot", pdf_bytes(*pages))
    extract_all()
    return node


async def translated(browser, nodes: list[str], language: str = "hr"):
    return await browser.post(
        "/api/runs",
        {
            "action": translation.ACTION,
            "target": {"nodes": nodes},
            "parameters": {"language": language},
            "consent": "once",
        },
        content_type=JSON,
    )


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_pdf_is_translated_page_by_page_into_a_new_document_in_the_language_chosen(
    live, monkeypatch
):
    browser, recorded = await gathering(
        monkeypatch,
        page(
            False,
            {"kind": "heading1", "text": "Ponuda"},
            {"kind": "paragraph", "text": "Poštovane dame i gospodo, nudimo"},
        ),
        page(
            True,
            {"kind": "paragraph", "text": "održavanje."},
            {"kind": "table", "rows": [["Cijena", "100 EUR"]]},
        ),
    )
    file = await sync_to_async(uploaded_pdf)(
        "Sehr geehrte Damen und Herren, wir bieten", "", "die Wartung an. Preis 100 EUR"
    )
    response = await translated(browser, [file])
    assert response.status_code == 202, response.json()
    run, document = response.json()["run"], response.json()["document"]
    assert (document["title"], document["kind"]) == ("Angebot – Hrvatski", "document")
    assert (await Node.objects.aget(pk=document["id"])).locale == "hr"
    assert run["items"] == {"of": 2, "through": 0, "missed": []}
    await drained()

    finished = await ActionRun.objects.aget(pk=run["id"])
    assert (finished.state, finished.error, finished.model) == ("done", "", "claude-sonnet-5-5")
    assert finished.parameters == {"language": "hr"}
    first, second = recorded.asked
    assert first["messages"][0]["content"].strip() == "Sehr geehrte Damen und Herren, wir bieten"
    assert "into Croatian" in first["system"][0]["text"]
    assert "ended with" not in first["system"][0]["text"]
    assert second["messages"][0]["content"].strip() == "die Wartung an. Preis 100 EUR"
    assert (
        'The page before it ended with: "Sehr geehrte Damen und Herren, wir bieten"'
        in second["system"][0]["text"]
    )
    tab = await Tab.objects.aget(document_id=document["id"])
    read = text_of((await sync_to_async(Room.of)(tab)).read())
    assert read.index("Ponuda") < read.index("Poštovane dame i gospodo, nudimo održavanje.")
    assert "| Cijena | 100 EUR |" in read


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_only_one_pdf_is_translated_at_a_time(live, monkeypatch):
    browser, recorded = await gathering(monkeypatch)
    file = await sync_to_async(uploaded_pdf)("Angebot", "Preis")
    monkeypatch.setattr(batches, "ITEMS", 1)
    response = await translated(browser, [file])
    assert (response.status_code, response.json()["error"]) == (422, "too_many_pages")
    monkeypatch.setattr(batches, "ITEMS", 2)
    document = await made(browser, "document", "Ponuda")
    for nodes in ([document], [file, document]):
        response = await translated(browser, nodes)
        assert (response.status_code, response.json()["error"]) == (400, "not_a_pdf")
    response = await translated(browser, [file], "xx")
    assert response.status_code == 400
    assert recorded.asked == []
