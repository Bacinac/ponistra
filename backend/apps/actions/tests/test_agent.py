import json

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model

from apps.actions.agent import ROWS, analyse, ask, turns_of
from apps.actions.models import ActionRun, RunChange
from apps.actions.tests.test_actions import priced
from apps.actions.tests.test_language import CONTENT, JSON, ran, summarising, texts
from apps.ai import model
from apps.ai.model import Choice, Reading
from apps.ai.tests.recorded import message, used
from apps.collab import server
from apps.content.operations import OPERATIONS
from apps.content.sheets import Refused
from apps.content.tests.helpers import fill
from apps.content.tests.test_elements import first_tab
from apps.documents.models import Tab
from apps.engine.parse import quote_sheet

THREAD = "0b6f5a0e-8a77-4c39-9b9e-2d1f3c4e5a6b"


def _long() -> list:
    return [*CONTENT, priced(*[(f"Vijak {at}", str(at), "1,5") for at in range(1, 151)])]


@pytest.mark.django_db
def test_a_request_reads_the_whole_tab_the_blocks_chosen_and_may_call_every_operation(api):
    tab = first_tab(api)
    user = get_user_model().objects.get()
    table = priced(("Vijak", "3", "1,5"), ("Ukupno", "", ""))
    table.grid.formulas["r3:c"] = ["SUM(", {"from": {"row": "r2", "col": "c"}}, ")"]
    fill(tab, [*CONTENT, table])
    prompt = ask(tab, {"blocks": ["b"]}, {"request": "Podebljaj cijenu."}, user)
    lines = prompt.content.splitlines()
    assert lines[:5] == [
        "[t0] title: Ugovor",
        "[a] paragraph: Najam stana",
        '[b] paragraph {"list":"bullet"}: Cijena',
        "[c] paragraph",
        '[t] table {"designs":[{"name":"grid"}]}',
    ]
    assert '[t r3 c] =SUM(C2) → 1,50 € format "#,##0.00 \\"€\\""' in lines
    assert not any(line.lstrip().startswith("shown:") for line in lines)
    assert lines[lines.index("styles:") + 1 : lines.index("styles:") + 3] == [
        "[text] text: font text (Inter), 12 pt",
        "[title] title: font headings (Inter), 27 pt",
    ]
    assert lines[-3:] == ["", "chosen: b", "request: Podebljaj cijenu."]
    operations = {name: fixed for name, fixed in prompt.tools.items() if isinstance(fixed, dict)}
    assert operations == {name: {} for name in [*OPERATIONS, "style"]}
    assert isinstance(prompt.tools["offer"], Choice)
    assert {name for name, fixed in prompt.tools.items() if isinstance(fixed, Reading)} == {
        "profile",
        "read",
    }
    assert (prompt.effort, prompt.replies) == ("high", True)
    assert "language (hr)" in prompt.instruction
    assert ask(tab, {}, {"request": "Sredi."}, user).content.splitlines()[-1] == "request: Sredi."
    with pytest.raises(Refused) as refused:
        ask(tab, {"blocks": ["b", "z"]}, {"request": "Sredi."}, user)
    assert refused.value.code == "not_found"
    for given in (
        {},
        {"request": ""},
        {"request": "x" * 4001},
        {"request": "Sredi.", "thread": "nije-id"},
    ):
        response = api.post(
            f"/api/tabs/{tab.pk}/runs",
            {"action": "text.ask", "target": {}, "parameters": given},
            content_type=JSON,
        )
        assert (response.status_code, response.json()["error"]) == (400, "invalid_parameters")


@pytest.mark.django_db
def test_a_long_table_is_read_in_part_and_whole_through_the_profile_and_its_rows(api):
    tab = first_tab(api)
    user = get_user_model().objects.get()
    fill(tab, _long())
    prompt = ask(tab, {}, {"request": "Što je najskuplje?"}, user)
    lines = prompt.content.splitlines()
    assert (
        "    shown: rows 1–100 of 151; the read tool reads others, the profile tool the whole "
        "table" in lines
    )
    assert f"[t r{ROWS} a] Vijak {ROWS - 1}" in lines
    assert not any(line.startswith(f"[t r{ROWS + 1} ") for line in lines)
    profiled = prompt.tools["profile"].read({"table": "t"})
    assert (profiled["rows"], profiled["data"]) == (151, {"first": 2, "last": 151, "rows": 150})
    amount, price = profiled["columns"][1:]
    assert (amount["header"], amount["kinds"], amount["distinct"]) == (
        "Količina",
        {"number": 150},
        150,
    )
    assert (amount["least"], amount["greatest"]) == ("1", "150")
    assert price["commonest"] == [{"value": "1,50 €", "rows": 150}]
    assert "data" not in price
    assert len(profiled["sample"]) == 12
    stretch = prompt.tools["read"].read({"table": "t", "first": 150, "count": 5})
    assert [row["cells"] for row in stretch["stretch"]] == [
        ["Vijak 149", "149", "1,50 €"],
        ["Vijak 150", "150", "1,50 €"],
    ]
    with pytest.raises(Refused):
        prompt.tools["read"].read({"table": "t", "first": 152, "count": 1})


@pytest.mark.django_db
def test_a_conversation_reads_its_earlier_turns_and_the_user_finds_it_again(api):
    tab = first_tab(api)
    user = get_user_model().objects.get()
    fill(tab, CONTENT)

    def turn(request: str, **kept) -> ActionRun:
        return ActionRun.objects.create(
            document=tab.document,
            user=user,
            action="text.ask",
            target={},
            parameters={"request": request, "thread": THREAD},
            **kept,
        )

    turn("Graf prodaje po mjesecima.", calls=["insert", "cells", "cells"], state="done")
    turn("Koju godinu?", reply="Za koju godinu?", offers=["2024.", "2025."], state="done")
    turn("Sad kao pita.", calls=["set"], state="undone")
    assert turns_of(tab, user, None) == []
    assert turns_of(tab, user, THREAD) == [
        "turn: Graf prodaje po mjesecima.",
        "    called: insert, cells ×2",
        "turn: Koju godinu?",
        "    said: Za koju godinu?",
        "    offered: 2024. | 2025.",
        "turn: Sad kao pita.",
        "    called: set",
        "    undone",
        "",
    ]
    content = ask(tab, {}, {"request": "Makni 2023.", "thread": THREAD}, user).content
    assert content.startswith("turn: Graf prodaje po mjesecima.\n")
    found = api.get(f"/api/tabs/{tab.pk}/runs").json()
    assert found["thread"] == THREAD
    assert [each["request"] for each in found["turns"]] == [
        "Graf prodaje po mjesecima.",
        "Koju godinu?",
        "Sad kao pita.",
    ]
    assert found["turns"][1]["offers"] == ["2024.", "2025."]
    other = "11111111-2222-4333-8444-555555555555"
    assert api.get(f"/api/tabs/{tab.pk}/runs?thread={other}").json() == {
        "thread": other,
        "turns": [],
    }


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_turn_that_cannot_tell_what_is_meant_offers_answers_and_changes_nothing(
    live, monkeypatch
):
    offer = {"question": "Za koju godinu?", "options": ["2024.", "2025."]}
    browser, tab = await summarising(
        monkeypatch,
        message("tool_use", used("u1", "offer", offer)),
        message("tool_use", used("u1", "mark", {"range": {"block": "a"}, "mark": "strong"})),
        message("end_turn"),
    )
    recorded = model.answer
    asked = {"request": "Podebljaj prodaju.", "thread": THREAD}
    run = await ran(browser, tab, "text.ask", consent="once", parameters=asked)
    assert (run.state, run.reply, run.offers, run.calls) == ("done", *offer.values(), [])
    assert not await RunChange.objects.filter(run=run).aexists()
    asked = {"request": "2025.", "thread": THREAD}
    run = await ran(browser, tab, "text.ask", consent="once", parameters=asked)
    assert (run.state, run.reply, run.offers, run.calls) == ("done", "", [], ["mark"])
    assert recorded.asked[1]["messages"][0]["content"].splitlines()[:4] == [
        "turn: Podebljaj prodaju.",
        "    said: Za koju godinu?",
        "    offered: 2024. | 2025.",
        "",
    ]
    assert (await texts(tab))[1] == ("Najam stana", {"strong"})


@pytest.mark.django_db
def test_an_analysis_names_the_table_formulas_read_it_by_and_opens_an_empty_tab(api):
    tab = first_tab(api)
    fill(tab, [*CONTENT, priced(("Vijak", "3", "1,5"), ("Matica", "5", "0,5"))])
    prompt = analyse(tab, {"table": "t"}, {"title": "Analiza"})
    name = prompt.before[0]["name"]
    assert prompt.before == [{"op": "grid", "table": "t", "name": name}]
    assert name and len(name) <= 31
    assert prompt.opens.title == " – ".join(filter(None, ["Analiza", tab.title]))
    assert (prompt.opens.grids, prompt.opens.blocks) == ([], [])
    profiled = json.loads(prompt.content)
    assert profiled["name"] == name
    assert profiled["columns"][2]["data"] == f"{quote_sheet(name)}!C2:C3"
    operations = {each for each, fixed in prompt.tools.items() if isinstance(fixed, dict)}
    assert operations == set(OPERATIONS)
    assert {"profile", "read"} <= set(prompt.tools)
    assert "offer" not in prompt.tools
    with pytest.raises(Refused):
        analyse(tab, {"table": "z"}, {"title": "Analiza"})


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_an_analysis_writes_formulas_reads_what_they_compute_and_is_taken_back_whole(
    live, monkeypatch
):
    browser, tab = await summarising(monkeypatch)
    await sync_to_async(fill)(
        tab, [*CONTENT, priced(("Vijak", "3", "1,5"), ("Matica", "5", "2,5"))]
    )
    prompt = await sync_to_async(analyse)(tab, {"table": "t"}, {"title": "Analiza"})
    name = prompt.before[0]["name"]
    average = {
        "at": {"end": "body"},
        "id": "s",
        "rows": [["Prosječna cijena", {"formula": f"AVERAGE({quote_sheet(name)}!C2:C3)"}]],
    }
    recorded = model.answer
    recorded.answers += [
        message("tool_use", used("u1", "table", average)),
        message("tool_use", used("u2", "read", {"table": "s", "first": 1, "count": 1})),
        message("end_turn"),
    ]
    run = await ran(
        browser,
        tab,
        "table.analyse",
        consent="once",
        target={"table": "t"},
        parameters={"title": "Analiza"},
    )
    assert (run.state, run.error, run.calls) == ("done", "", ["table"])
    read = recorded.asked[2]["messages"][-1]["content"][0]
    assert json.loads(read["content"])["stretch"][0]["cells"] == ["Prosječna cijena", "2,00 €"]

    def named() -> str:
        return server.read_grids(tab.room, lambda doc, held: held.peek("t").name)

    assert await sync_to_async(named)() == name
    assert await Tab.objects.filter(document=tab.document_id).acount() == 2
    response = await browser.post(f"/api/runs/{run.pk}/undo")
    assert response.status_code == 200
    assert await sync_to_async(named)() == ""
    assert await Tab.objects.filter(document=tab.document_id).acount() == 1
