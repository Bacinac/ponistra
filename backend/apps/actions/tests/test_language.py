from decimal import Decimal

import pytest
from asgiref.sync import sync_to_async
from django.utils import timezone

from apps.actions import runs
from apps.actions.language import compare, extract, rewrite, summarise, translate
from apps.actions.models import ActionRun, RunChange
from apps.actions.tests.test_actions import priced, signed_in, values_in
from apps.ai import installation, model
from apps.ai.model import Among
from apps.ai.models import Consent
from apps.ai.reading import text_of
from apps.ai.tests.recorded import Recorded, message, said, used
from apps.collab import server
from apps.collab.tests.test_server import until
from apps.content import styles
from apps.content.blocks import Block, Note, Run, key_of
from apps.content.sheets import Refused
from apps.content.tests.helpers import Room, fill
from apps.content.tests.test_elements import first_tab
from apps.documents.models import Tab
from apps.versions import history
from apps.versions.models import Version

JSON = "application/json"
PROPOSAL = {"id": "p", "author": "Ana Horvat", "date": "2026-10-19T10:00:00Z"}
SUMMARY = [{"type": "paragraph", "content": [{"type": "text", "text": "Najam na godinu."}]}]
PROPOSED_BY_ANA = {
    "type": "text",
    "text": "Ana",
    "marks": [
        {"type": "insertion", "attrs": {"id": "p", "author": "Ana", "date": "2026-10-22T09:00:00Z"}}
    ],
}
CONTENT = [
    Block("title", "t0", runs=[Run("Ugovor")]),
    Block("paragraph", "a", runs=[Run("Najam stana")]),
    Block("paragraph", "b", {"list": "bullet"}, runs=[Run("Cijena")]),
    Block("paragraph", "c"),
]


@pytest.mark.django_db
def test_a_summary_reads_the_blocks_chosen_and_goes_after_them_or_after_the_title(api):
    tab = first_tab(api)
    fill(tab, [*CONTENT, priced(("Vijak", "3", "1,5"))])
    prompt = summarise(tab, {}, {})
    assert prompt.content.splitlines() == [
        "[t0] title: Ugovor",
        "[a] paragraph: Najam stana",
        "[b] bullet item: Cijena",
        "[t] table:",
        "| Artikl | Količina | Cijena |",
        "| Vijak | 3 | 1,5 |",
    ]
    assert prompt.tools == {"insert": {"at": {"after": "t0"}}}
    chosen = summarise(tab, {"blocks": ["b", "a"]}, {})
    assert chosen.content == "[a] paragraph: Najam stana\n[b] bullet item: Cijena"
    assert chosen.tools == {"insert": {"at": {"after": "b"}}}
    fill(tab, CONTENT[1:])
    assert summarise(tab, {}, {}).tools == {"insert": {"at": {"start": "body"}}}
    for target, code in [({"blocks": ["a", "z"]}, "not_found"), ({"blocks": ["c"]}, "empty")]:
        with pytest.raises(Refused) as refused:
            summarise(tab, target, {})
        assert refused.value.code == code


@pytest.mark.django_db
def test_an_extraction_reads_what_a_summary_does_and_its_table_goes_where_a_summary_does(api):
    tab = first_tab(api)
    fill(tab, CONTENT)
    prompt = extract(tab, {"blocks": ["a", "b"]}, {})
    assert prompt.content == "[a] paragraph: Najam stana\n[b] bullet item: Cijena"
    assert prompt.tools == {"table": {"at": {"after": "b"}}}
    assert "language (hr)" in prompt.instruction
    assert extract(tab, {}, {}).tools == {"table": {"at": {"after": "t0"}}}
    with pytest.raises(Refused) as refused:
        extract(tab, {"blocks": ["c"]}, {})
    assert refused.value.code == "empty"


@pytest.mark.django_db
def test_a_rewrite_reads_the_text_blocks_chosen_and_may_write_only_those(api):
    tab = first_tab(api)
    fill(tab, [*CONTENT, priced(("Vijak", "3", "1,5"))])
    prompt = rewrite(tab, {}, {"way": "formal"})
    assert prompt.content.splitlines() == [
        "[t0] title: Ugovor",
        "[a] paragraph: Najam stana",
        "[b] bullet item: Cijena",
    ]
    assert prompt.tools == {"rewrite": {"block": Among(("t0", "a", "b"))}}
    assert "more formal register" in prompt.instruction and prompt.effort == "medium"
    corrected = rewrite(tab, {"blocks": ["b"]}, {"way": "correct"})
    assert corrected.tools == {"rewrite": {"block": Among(("b",))}} and corrected.effort == "low"
    fill(
        tab,
        [Block("paragraph", "a", runs=[Run("Najam "), Run("kuće", {"insertion": PROPOSAL})])],
    )
    for target, code in [({"blocks": ["a"]}, "proposed"), ({"blocks": ["z"]}, "not_found")]:
        with pytest.raises(Refused) as refused:
            rewrite(tab, target, {"way": "short"})
        assert refused.value.code == code
    fill(tab, [priced(("Vijak", "3", "1,5"))])
    with pytest.raises(Refused) as refused:
        rewrite(tab, {}, {"way": "short"})
    assert refused.value.code == "empty"
    response = api.post(
        f"/api/tabs/{tab.pk}/runs",
        {"action": "text.rewrite", "target": {}, "parameters": {"way": "poetic"}},
        content_type=JSON,
    )
    assert (response.status_code, response.json()["error"]) == (400, "invalid_parameters")


@pytest.mark.django_db
def test_a_translation_reads_a_copy_of_the_tab_tagged_and_may_write_only_its_words(api):
    tab = first_tab(api)
    tab.title = "Ugovor"
    tab.save()
    noted = Block(
        "paragraph", "n", runs=[Run("Plaća se "), Run("mjesečno", {"strong": {}}), Note(id="f")]
    )
    noted.runs[2].runs = [Run("Do petog.")]
    over = {"table": "t", "from": {"row": "r1", "col": "c"}, "to": {"row": "r2", "col": "c"}}
    chart = Block("chart", "g", {"range": over, "kind": "column", "title": "Cijene"})
    table = priced(("Vijak", "3", "1,5"))
    table.attrs["name"] = "Cjenik"
    fill(tab, [*CONTENT, noted, table, chart])
    prompt = translate(tab, {}, {"language": "de"})
    copy = prompt.opens
    assert (copy.tab, copy.title) == (tab, "Ugovor – Deutsch")
    (table,) = [block for block in copy.blocks if block.type == "table"]
    assert table.id != "t" and copy.blocks[-1].attrs["range"]["table"] == table.id
    (laid,) = copy.grids
    assert (laid.table, laid.name) == (table.id, "Cjenik (2)")
    assert prompt.content.splitlines() == [
        "[t0] title: Ugovor",
        "[a] paragraph: Najam stana",
        "[b] bullet item: Cijena",
        "[n] paragraph: Plaća se <1>mjesečno</1><2/>",
        "[f] footnote: Do petog.",
        f"[{table.id}] table",
        *(
            f"[{table.id} r{y} {col}] cell: {text}"
            for y, line in enumerate([("Artikl", "Količina", "Cijena"), ("Vijak", "3", "1,5")], 1)
            for col, text in zip("abc", line, strict=True)
        ),
        "[g] chart title: Cijene",
    ]
    assert prompt.tools == {
        "replace": {"block": Among(("t0", "a", "b", "n", "f"))},
        "cells": {"table": Among((table.id,))},
        "set": {"block": Among(("g",))},
    }
    assert "into German" in prompt.instruction and prompt.steps == model.STEPS
    assert not Tab.objects.exclude(pk=tab.pk).exists()
    for content, code in [
        ([Block("paragraph", "a", runs=[Run("Najam", {"deletion": PROPOSAL})])], "proposed"),
        ([Block("paragraph", "c")], "empty"),
    ]:
        fill(tab, content)
        with pytest.raises(Refused) as refused:
            translate(tab, {}, {"language": "en"})
        assert refused.value.code == code


@pytest.mark.django_db
def test_a_comparison_reads_what_code_found_changed_since_the_version_and_goes_after_the_title(
    api,
):
    tab = first_tab(api)
    fill(tab, [*CONTENT, priced(("Vijak", "3", "1,5"))])
    saved = history.take(tab.document)
    Version.objects.filter(pk=saved.pk).update(title="Ponuda")
    with pytest.raises(Refused) as refused:
        compare(tab, {}, {"version": str(saved.pk)})
    assert refused.value.code == "same"
    fill(
        tab,
        [
            CONTENT[0],
            Block("paragraph", "a", runs=[Run("Najam kuće")]),
            priced(("Vijak", "4", "1,5")),
        ],
    )

    prompt = compare(tab, {}, {"version": str(saved.pk)})

    assert prompt.content.splitlines() == [
        "[a] paragraph changed: Najam [-stana-]{+kuće+}",
        "[b] bullet item removed: Cijena",
        "[t r2] table row changed: | Vijak | [-3-]{+4+} | 1,5 |",
    ]
    shown = timezone.localtime(saved.created_at).strftime("%Y-%m-%d %H:%M")
    assert f'since its version 1 "Ponuda" of {shown}.' in prompt.instruction
    assert prompt.tools == {"insert": {"at": {"after": "t0"}}}
    other = first_tab(api)
    for version, code in [(history.take(other.document), "not_found"), (saved, "same")]:
        fill(tab, [*CONTENT, priced(("Vijak", "3", "1,5"))])
        with pytest.raises(Refused) as refused:
            compare(tab, {}, {"version": str(version.pk)})
        assert refused.value.code == code


@pytest.mark.django_db
def test_a_model_s_action_waits_for_the_installation_s_ai_and_the_document_s_consent(
    api, monkeypatch
):
    tab = first_tab(api)
    url = f"/api/tabs/{tab.pk}/runs"
    asked = {"action": "text.summarise", "target": {}}
    listed = api.get("/api/actions").json()
    assert listed["ai"] is False
    assert {"id": "text.summarise", "review": "propose", "model": "claude-sonnet-5-5"}.items() <= (
        next(each for each in listed["actions"] if each["id"] == "text.summarise").items()
    )
    response = api.post(url, asked, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (409, "ai_off")
    monkeypatch.setattr(installation, "enabled", lambda: True)
    response = api.post(url, asked, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (422, "empty")
    assert ActionRun.objects.get().state == "failed"
    fill(tab, CONTENT)
    response = api.post(url, asked, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (428, "consent_needed")
    for wrong in ("always", "none", "uvijek"):
        response = api.post(url, asked | {"consent": wrong}, content_type=JSON)
        assert (response.status_code, response.json()["error"]) == (400, "invalid_consent")
    assert ActionRun.objects.count() == 1 and not Consent.objects.exists()


@pytest.mark.django_db
def test_a_run_a_restart_cut_off_is_marked_interrupted(api):
    tab = first_tab(api)
    made = {
        state: ActionRun.objects.create(
            document=tab.document, user=api.user, action="text.summarise", target={}, state=state
        )
        for state in ("running", "stopping", "done")
    }
    runs.interrupted()
    for state, run in made.items():
        run.refresh_from_db()
        assert run.state == ("done" if state == "done" else "interrupted")
        assert (run.finished_at is None) == (state == "done")


async def summarising(monkeypatch, *answers) -> tuple:
    browser, tab = await signed_in()
    await sync_to_async(fill)(tab, CONTENT)
    monkeypatch.setattr(installation, "enabled", lambda: True)
    monkeypatch.setattr(model, "answer", Recorded(*answers))
    return browser, tab


async def ran(browser, tab, action: str = "text.summarise", **given) -> ActionRun:
    response = await browser.post(
        f"/api/tabs/{tab.pk}/runs",
        {"action": action, "target": {}, **given},
        content_type=JSON,
    )
    assert response.status_code == 202, response.json()
    described = response.json()["run"]
    final = {"done", "stopped", "failed"}

    async def finished() -> bool:
        return (await ActionRun.objects.aget(pk=described["id"])).state in final

    await until(finished)
    return await ActionRun.objects.aget(pk=described["id"])


async def texts(tab) -> list[tuple[str, set[str]]]:
    found = (await sync_to_async(Room.of)(tab)).read()
    return [(block.text, {mark for run in block.runs for mark in run.marks}) for block in found]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_summary_is_written_in_the_background_as_a_proposal_undo_takes_back(
    live, monkeypatch
):
    browser, tab = await summarising(
        monkeypatch,
        message("tool_use", used("u1", "insert", {"blocks": SUMMARY})),
        message("end_turn", said("Gotovo.")),
        message("end_turn", said("Nema što dodati.")),
    )
    run = await ran(browser, tab, consent="once")
    assert (run.state, run.error) == ("done", "")
    assert not await Consent.objects.aexists()
    assert (run.model, run.input_tokens, run.output_tokens, run.cost) == (
        "claude-sonnet-5-5",
        2,
        2,
        Decimal("0.000024"),
    )
    assert (run.consent, run.consented_by_id) == ("once", run.user_id)
    assert await texts(tab) == [
        ("Ugovor", set()),
        ("Najam na godinu.", {"insertion"}),
        ("Najam stana", set()),
        ("Cijena", set()),
        ("", set()),
    ]
    described = (await browser.get(f"/api/runs/{run.pk}")).json()["run"]
    assert (described["state"], described["action"]) == ("done", "text.summarise")
    response = await browser.post(f"/api/runs/{run.pk}/stop")
    assert (response.status_code, response.json()["error"]) == (422, "not_running")
    response = await browser.post(f"/api/runs/{run.pk}/undo")
    assert response.status_code == 200 and response.json()["run"]["state"] == "undone"
    assert [text for text, _ in await texts(tab)] == ["Ugovor", "Najam stana", "Cijena", ""]
    response = await browser.post(f"/api/runs/{run.pk}/undo")
    assert (response.status_code, response.json()["error"]) == (422, "not_done")
    assert (await browser.post(f"/api/nodes/{tab.document_id}/ai")).status_code == 200
    run = await ran(browser, tab)
    assert (run.state, run.consent, run.consented_by_id) == ("done", "document", run.user_id)


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_run_whose_model_fails_takes_back_what_it_wrote(live, monkeypatch, caplog):
    browser, tab = await summarising(
        monkeypatch,
        message("tool_use", used("u1", "insert", {"blocks": SUMMARY})),
        model.Failed("rate_limited", "429 Too many requests"),
    )
    run = await ran(browser, tab, consent="once")
    assert (run.state, run.error) == ("failed", "rate_limited")
    assert f"run {run.pk} failed: rate_limited: 429 Too many requests" in caplog.text
    assert [text for text, _ in await texts(tab)] == ["Ugovor", "Najam stana", "Cijena", ""]
    assert not await RunChange.objects.aexists()


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_stopped_run_keeps_what_it_wrote_for_undo(live, monkeypatch):
    def stopped():
        runs.stop(ActionRun.objects.get())
        return message("tool_use", used("u2", "insert", {"blocks": SUMMARY}))

    browser, tab = await summarising(
        monkeypatch, message("tool_use", used("u1", "insert", {"blocks": SUMMARY})), stopped
    )
    run = await ran(browser, tab, consent="once")
    assert run.state == "stopped"
    assert [text for text, _ in await texts(tab)].count("Najam na godinu.") == 1
    response = await browser.post(f"/api/runs/{run.pk}/undo")
    assert response.status_code == 200
    assert [text for text, _ in await texts(tab)] == ["Ugovor", "Najam stana", "Cijena", ""]
    response = await browser.post(
        f"/api/tabs/{tab.pk}/runs",
        {"action": "table.totals", "target": {"table": "t"}},
        content_type=JSON,
    )
    other = await ActionRun.objects.exclude(pk=run.pk).aget()
    response = await browser.post(f"/api/runs/{other.pk}/stop")
    assert (response.status_code, response.json()["error"]) == (409, "not_stoppable")


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_rewrite_proposes_only_the_words_that_differ_and_undo_takes_them_back(
    live, monkeypatch
):
    browser, tab = await summarising(
        monkeypatch,
        message("tool_use", used("u1", "rewrite", {"block": "a", "text": "Najam kuće"})),
        message("end_turn", said("Gotovo.")),
    )
    run = await ran(browser, tab, "text.rewrite", parameters={"way": "formal"}, consent="once")
    assert (run.state, run.error) == ("done", "")
    assert await texts(tab) == [
        ("Ugovor", set()),
        ("Najam stanakuće", {"deletion", "insertion"}),
        ("Cijena", set()),
        ("", set()),
    ]
    response = await browser.post(f"/api/runs/{run.pk}/undo")
    assert response.status_code == 200
    assert await texts(tab) == [
        ("Ugovor", set()),
        ("Najam stana", set()),
        ("Cijena", set()),
        ("", set()),
    ]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_an_extraction_proposes_a_table_that_computes_and_undo_takes_it_back(
    live, monkeypatch
):
    rows = [
        ["Stavka", "Iznos"],
        ["Najam", "750,5"],
        ["Režije", "100"],
        ["Ukupno", {"formula": "SUM(B2:B3)"}],
    ]
    browser, tab = await summarising(
        monkeypatch,
        message("tool_use", used("u1", "table", {"rows": rows})),
        message("end_turn", said("Gotovo.")),
    )
    run = await ran(browser, tab, "text.extract", consent="once")
    assert (run.state, run.error) == ("done", "")
    room = await sync_to_async(Room.of)(tab)
    lines = text_of(room.read()).splitlines()
    assert lines[1].endswith(" table:") and lines[2:5] == [
        "| Stavka | Iznos |",
        "| Najam | 750,5 |",
        "| Režije | 100 |",
    ]
    (table,) = [block for block in room.read() if block.type == "table"]
    assert len(table.attrs["proposedRows"]) == 4
    computed = await sync_to_async(values_in)(room, table.id)
    assert sorted(each["text"] for each in computed.values()) == ["100", "750,5", "850,5"]
    response = await browser.post(f"/api/runs/{run.pk}/undo")
    assert response.status_code == 200
    assert [text for text, _ in await texts(tab)] == ["Ugovor", "Najam stana", "Cijena", ""]


def translated(answered) -> callable:
    def answer():
        opened = ActionRun.objects.get().opened
        (table,) = [block for block in Room.of(opened).read() if block.type == "table"]
        return message("tool_use", *answered(table.id))

    return answer


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_translation_goes_into_a_new_tab_as_it_is_and_undo_closes_it(live, monkeypatch):
    def answered(table: str) -> list:
        cells = [
            {"row": "r1", "col": "a", "value": "Item"},
            {"row": "r2", "col": "a", "value": "Bolt"},
        ]
        return [
            used("u1", "replace", {"block": "t0", "text": "Contract"}),
            used("u2", "replace", {"block": "a", "text": "Rent of the flat"}),
            used("u3", "replace", {"block": "b", "text": "Price"}),
            used("u4", "cells", {"table": table, "cells": cells}),
        ]

    browser, tab = await summarising(
        monkeypatch,
        translated(answered),
        message("end_turn", said("Gotovo.")),
    )
    await sync_to_async(fill)(tab, [*CONTENT, priced(("Vijak", "3", "1,5"))])
    run = await ran(
        browser, tab, "document.translate", parameters={"language": "en-GB"}, consent="once"
    )
    assert (run.state, run.error) == ("done", "")
    opened = await Tab.objects.aget(pk=run.opened_id)
    assert (opened.title, opened.parent_id) == ("British English", None)
    assert [text for text, _ in await texts(opened)] == [
        "Contract",
        "Rent of the flat",
        "Price",
        "",
        "",
    ]
    found = (await sync_to_async(Room.of)(opened)).read()
    assert found[2].attrs["list"] == "bullet"
    source = {
        key_of(cell.row, cell.col): cell
        for cell in (await sync_to_async(Room.of)(tab)).read()[4].cells
    }
    copied = {key_of(cell.row, cell.col): cell for cell in found[4].cells}
    assert [copied[key].text for key in ("r1:a", "r1:b", "r2:a", "r2:c")] == [
        "Item",
        "Količina",
        "Bolt",
        "1,5",
    ]
    assert copied["r1:a"].blocks[0].runs[0].marks == source["r1:a"].blocks[0].runs[0].marks
    assert [text for text, _ in await texts(tab)] == ["Ugovor", "Najam stana", "Cijena", "", ""]
    response = await browser.post(f"/api/runs/{run.pk}/undo")
    assert response.status_code == 200 and response.json()["run"]["state"] == "undone"
    assert not await Tab.objects.filter(pk=opened.pk).aexists()
    assert await Version.objects.filter(document=tab.document_id).aexists()
    assert [text for text, _ in await texts(tab)] == ["Ugovor", "Najam stana", "Cijena", "", ""]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_translation_whose_model_fails_closes_its_tab_without_a_trace(live, monkeypatch):
    browser, tab = await summarising(
        monkeypatch,
        message("tool_use", used("u1", "replace", {"block": "a", "text": "Rent"})),
        model.Failed("rate_limited"),
    )
    run = await ran(
        browser, tab, "document.translate", parameters={"language": "de"}, consent="once"
    )
    assert (run.state, run.error, run.opened_id) == ("failed", "rate_limited", None)
    assert await Tab.objects.filter(document=tab.document_id).acount() == 1
    assert not await Version.objects.filter(document=tab.document_id).aexists()
    assert not await RunChange.objects.aexists()


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_request_is_carried_out_with_any_operation_and_what_the_model_says_is_kept(
    live, monkeypatch
):
    browser, tab = await summarising(
        monkeypatch,
        message(
            "tool_use",
            used("u1", "mark", {"range": {"block": "a", "words": "stana"}, "mark": "strong"}),
            used("u2", "rewrite", {"block": "b", "text": "Cijena najma"}),
            used("u3", "style", {"style": "text", "size": 11}),
            used("u4", "text", {"range": {"block": "c"}, "content": [PROPOSED_BY_ANA]}),
        ),
        message("end_turn"),
        message("end_turn", said("Dokument nema tablica pa nemam što zbrojiti.")),
    )
    recorded = model.answer
    request = {"request": "Podebljaj stan, dopuni cijenu i smanji tekst."}
    run = await ran(browser, tab, "text.ask", consent="once", parameters=request)
    assert (run.state, run.error, run.reply) == ("done", "", "")
    results = recorded.asked[1]["messages"][-1]["content"]
    assert [result.get("is_error", False) for result in results] == [False, False, False, True]
    assert results[3]["content"] == "proposal: insertion is written by a proposer, never given"
    assert await texts(tab) == [
        ("Ugovor", set()),
        ("Najam stana", {"strong"}),
        ("Cijena najma", {"insertion"}),
        ("", set()),
    ]

    def size() -> float:
        return server.read(tab.document.room, styles.read)[1]["text"]["size"]

    assert await sync_to_async(size)() == 11
    assert await RunChange.objects.filter(run=run, tab=None).aexists()
    response = await browser.post(f"/api/runs/{run.pk}/undo")
    assert response.status_code == 200
    assert await texts(tab) == [
        ("Ugovor", set()),
        ("Najam stana", set()),
        ("Cijena", set()),
        ("", set()),
    ]
    assert await sync_to_async(size)() == 12
    run = await ran(browser, tab, "text.ask", consent="once", parameters={"request": "Zbroji."})
    assert (run.state, run.reply) == ("done", "Dokument nema tablica pa nemam što zbrojiti.")
    assert not await RunChange.objects.filter(run=run).aexists()
    described = (await browser.get(f"/api/runs/{run.pk}")).json()["run"]
    assert (described["reply"], described["changed"]) == (run.reply, False)
