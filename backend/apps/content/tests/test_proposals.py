import pytest

from apps.content.blocks import PROPOSED, Block, Cell, Field, Grid, Note, Run, tagged
from apps.content.operations import Proposer, Refused

from .helpers import Room


def change(id: str, author: str = "Ana Horvat") -> dict:
    return {"id": id, "author": author, "date": "2026-10-19T10:00:00Z"}


def tab(*content: Block) -> Room:
    return Room(*content)


def run(room: Room, *operations: dict):
    return room.run(*operations)


def accept(room: Room, *ids: str):
    return run(room, {"op": "accept", **({"ids": list(ids)} if ids else {})})


def reject(room: Room, *ids: str):
    return run(room, {"op": "reject", **({"ids": list(ids)} if ids else {})})


def paragraph(id: str, *runs: Run | Note | Field, type: str = "paragraph", **attrs) -> Block:
    return Block(type, id, attrs, list(runs))


def joined(runs: list) -> list[tuple]:
    """The runs as ProseMirror holds them: neighbours with the same marks as one."""
    found: list[tuple] = []
    for run in runs:
        if found and run.marks == found[-1][1]:
            found[-1] = (found[-1][0] + run.text, run.marks)
        elif run.text:
            found.append((run.text, run.marks))
    return found


def shown(room: Room) -> list[tuple]:
    return [(block.type, block.id, block.attrs, joined(block.runs)) for block in room.read()]


def proposal_text() -> Room:
    return tab(
        paragraph(
            "a",
            Run("Najam "),
            Run("stana", {"insertion": change("p1")}),
            Run("kuće", {"deletion": change("p1")}),
            Run(" i ", {"strong": {}}),
            Run("garaže", {"deletion": change("p2", "Ivo")}),
        )
    )


def test_an_accepted_insertion_stays_and_an_accepted_deletion_goes():
    room = proposal_text()
    accept(room)
    assert shown(room) == [("paragraph", "a", {}, [("Najam stana", {}), (" i ", {"strong": {}})])]


def test_a_rejected_insertion_goes_and_a_rejected_deletion_stays():
    room = proposal_text()
    reject(room)
    assert shown(room) == [
        ("paragraph", "a", {}, [("Najam kuće", {}), (" i ", {"strong": {}}), ("garaže", {})])
    ]


def test_only_the_proposals_named_are_settled_with_all_their_parts():
    room = proposal_text()
    accept(room, "p1")
    assert shown(room)[0][3] == [
        ("Najam stana", {}),
        (" i ", {"strong": {}}),
        ("garaže", {"deletion": change("p2", "Ivo")}),
    ]


def test_a_proposal_that_is_not_there_changes_nothing():
    room = proposal_text()
    state = room.doc.get_state()
    with pytest.raises(Refused) as found:
        accept(room, "p1", "gone")
    assert (found.value.code, found.value.detail) == ("no_proposal", "gone")
    assert room.doc.get_state() == state
    plain = tab(paragraph("a", Run("Tekst")))
    with pytest.raises(Refused) as found:
        reject(plain)
    assert found.value.code == "no_proposal"


def test_a_formatting_change_keeps_the_new_formatting_or_puts_back_the_old():
    formatting = {**change("f"), "before": {"em": {}, "size": {"pt": 14}}}
    text = [Run("Važno", {"strong": {}, "formatting": formatting}), Run(" je")]
    room = tab(paragraph("a", *text))
    accept(room)
    assert shown(room)[0][3] == [("Važno", {"strong": {}}), (" je", {})]
    room = tab(paragraph("a", *text))
    reject(room)
    assert shown(room)[0][3] == [("Važno", {"em": {}, "size": {"pt": 14}}), (" je", {})]


def test_a_paragraph_whose_end_goes_joins_the_next_which_keeps_its_type_and_attributes():
    def split() -> Room:
        return tab(
            paragraph("a", Run("Članak "), type="heading", level=2, insertion=change("p")),
            paragraph("b", Run("prvi", {"strong": {}}), align="center"),
        )

    room = split()
    reject(room)
    assert shown(room) == [
        ("paragraph", "a", {"align": "center"}, [("Članak ", {}), ("prvi", {"strong": {}})])
    ]
    room = split()
    accept(room)
    assert [block.attrs for block in room.read()] == [{"level": 2}, {"align": "center"}]


def test_a_whole_paragraph_proposed_comes_or_goes_with_its_end():
    inserted = change("p")
    room = tab(
        paragraph("a", Run("Novi stavak", {"insertion": inserted}), insertion=inserted),
        paragraph("b", Run("Stari"), deletion=change("q")),
        paragraph("c", Run("Kraj"), type="heading", level=1),
    )
    reject(room, "p")
    accept(room, "q")
    assert shown(room) == [("heading", "b", {"level": 1}, [("StariKraj", {})])]


def test_the_last_paragraph_keeps_its_end_and_a_lone_empty_one_stays():
    room = tab(paragraph("a", Run("Zadnji"), deletion=change("p")))
    accept(room)
    assert shown(room) == [("paragraph", "a", {}, [("Zadnji", {})])]
    room = tab(paragraph("a", Run("Sam", {"insertion": change("p")}), insertion=change("p")))
    reject(room)
    assert shown(room) == [("paragraph", "a", {}, [])]


def test_a_rejected_formatting_of_a_block_puts_back_its_type_and_attributes():
    before = {"type": "paragraph", "attrs": {"align": "center", "list": "bullet"}}
    formatting = {**change("f"), "before": before}
    room = tab(paragraph("a", Run("Naslov"), type="heading", level=1, formatting=formatting))
    reject(room)
    assert shown(room) == [
        ("paragraph", "a", {"align": "center", "list": "bullet"}, [("Naslov", {})])
    ]
    room = tab(paragraph("a", Run("Naslov"), align="right", formatting=formatting))
    reject(room)
    assert room.read()[0].attrs == {"align": "center", "list": "bullet"}
    room = tab(paragraph("a", Run("Naslov"), type="heading", level=1, formatting=formatting))
    accept(room)
    assert room.read()[0].attrs == {"level": 1}


def test_a_block_proposed_comes_or_goes_and_the_text_keeps_a_block():
    image = {"blob": "ab" * 32}
    room = tab(
        Block("image", "i", {**image, "insertion": change("p")}),
        Block("pageBreak", "b", {"deletion": change("q")}),
        paragraph("a", Run("Tekst")),
    )
    accept(room, "p", "q")
    assert [(block.type, block.attrs) for block in room.read()] == [
        ("image", image),
        ("paragraph", {}),
    ]
    room = tab(Block("image", "i", {**image, "insertion": change("p")}))
    reject(room)
    assert [(block.type, block.runs) for block in room.read()] == [("paragraph", [])]


def test_a_note_or_a_field_proposed_comes_or_goes_and_a_notes_text_is_settled():
    note = Note("foot", "n", [Run("izvor", {"insertion": change("t")})], {"insertion": change("n")})
    room = tab(paragraph("a", Run("Vidi"), note, Field("page", {"deletion": change("f")})))
    accept(room, "t", "f")
    assert room.read()[0].runs == [
        Run("Vidi"),
        Note("foot", "n", [Run("izvor")], {"insertion": change("n")}),
    ]
    reject(room, "n")
    assert room.read()[0].runs == [Run("Vidi")]


def test_rows_proposed_come_or_go_and_a_table_all_of_whose_rows_go_goes():
    def grid(proposed: dict) -> Room:
        cells = [
            Cell("r1", "c1", [paragraph("x", Run("Stari", {"deletion": change("t")}))]),
            Cell("r2", "c1", [paragraph("y", Run("Novi"))]),
        ]
        attrs = {"proposedRows": proposed}
        table = Block("table", "t", attrs, grid=Grid(["r1", "r2"], ["c1"]), cells=cells)
        return tab(table, paragraph("a", Run("Kraj")))

    room = grid({"r2": {"insertion": change("p")}})
    reject(room, "p")
    assert room.grids["t"].row_ids() == ["r1"]
    assert "proposedRows" not in room.read()[0].attrs
    room = grid({"r2": {"insertion": change("p")}})
    accept(room, "p", "t")
    (table, _) = room.read()
    assert room.grids["t"].row_ids() == ["r1", "r2"]
    assert "proposedRows" not in table.attrs
    assert joined(table.cells[0].blocks[0].runs) == []
    room = grid({"r1": {"insertion": change("p")}, "r2": {"insertion": change("p")}})
    reject(room, "p")
    assert [block.id for block in room.read()] == ["a"]


def test_a_review_is_taken_back_as_any_run():
    room = proposal_text()
    before = shown(room)
    performed = accept(room)
    room.take_back(performed.change)
    assert shown(room) == before


ANA = Proposer("Ana Horvat", 7, "2026-10-19T11:00:00Z")


def words(text: str) -> dict:
    return {"type": "text", "text": text}


def proposed(room: Room, *operations: dict):
    return room.run(*operations, propose=ANA)


def by_whom(runs: list) -> list[tuple]:
    """The runs' text with the proposals on it, as the kind and the account of each, which
    Yjs keeps as a number of JavaScript's."""
    return [
        (text, sorted(f"{name}:{marks[name]['user']:g}" for name in PROPOSED if name in marks))
        for text, marks in joined(runs)
    ]


def test_text_written_under_a_proposer_follows_the_text_it_replaces_proposed_deleted():
    mine, ivos = {**change("m"), "user": 7}, {**change("i", "Ivo"), "user": 3}
    room = tab(
        paragraph(
            "a",
            Run("Rok je 30 dana"),
            Run(" točno", {"insertion": mine}),
            Run(" i "),
            Run("odmah", {"insertion": ivos}),
        )
    )
    proposed(
        room,
        {"op": "text", "range": {"block": "a", "from": 7, "to": 9}, "content": [words("15")]},
        {"op": "text", "range": {"block": "a", "from": 14, "to": 20}, "content": []},
        {"op": "text", "range": {"block": "a", "from": 23, "to": 28}, "content": [words("sutra")]},
    )
    (block,) = room.read()
    assert by_whom(block.runs) == [
        ("Rok je ", []),
        ("30", ["deletion:7"]),
        ("15", ["insertion:7"]),
        (" dana i ", []),
        ("odmah", ["deletion:7", "insertion:3"]),
        ("sutra", ["insertion:7"]),
    ]
    ids = {
        text: {marks[name]["id"] for name in PROPOSED if name in marks}
        for text, marks in joined(block.runs)
    }
    assert ids["30"] == ids["15"] and ids["15"].isdisjoint(ids["sutra"])
    assert ids["sutra"] < ids["odmah"]
    (written,) = [marks for text, marks in joined(block.runs) if text == "15"]
    assert written["insertion"] | {"id": "x"} == {
        "id": "x",
        "author": "Ana Horvat",
        "user": 7,
        "date": "2026-10-19T11:00:00Z",
    }
    accept(room)
    assert room.read()[0].text == "Rok je 15 dana i sutra"


def rented() -> Room:
    return tab(
        paragraph("a", Run("Najam "), Run("stana", {"strong": {}}), Run(" traje godinu dana."))
    )


def test_a_block_written_anew_changes_only_its_words_that_differ_in_the_formatting_they_had():
    room = rented()
    run(room, {"op": "rewrite", "block": "a", "text": "Najam kuće traje dvije godine, od sutra."})
    (block,) = room.read()
    assert joined(block.runs) == [
        ("Najam ", {}),
        ("kuće", {"strong": {}}),
        (" traje dvije godine, od sutra.", {}),
    ]
    room = rented()
    proposed(room, {"op": "rewrite", "block": "a", "text": "Najam stana traje dvije godine."})
    (block,) = room.read()
    assert by_whom(block.runs) == [
        ("Najam ", []),
        ("stana", []),
        (" traje ", []),
        ("godinu dana", ["deletion:7"]),
        ("dvije godine", ["insertion:7"]),
        (".", []),
    ]
    accept(room)
    assert room.read()[0].text == "Najam stana traje dvije godine."


def test_a_block_replaced_keeps_the_formatting_its_tags_name_and_its_notes_where_they_stand():
    def noted() -> Room:
        note = Note("foot", "n", [Run("Vidi prilog.")])
        return tab(
            paragraph(
                "a",
                Run("Najam "),
                Run("stana", {"strong": {}}),
                note,
                Run(" traje\ngodinu."),
                Field("page"),
            )
        )

    assert tagged(noted().read()[0].runs) == "Najam <1>stana</1><2/> traje<br/>godinu.<3/>"
    room = noted()
    text = "Rent of <1>the flat</1><2/> lasts a<br/>year, <1>signed</1><3/>"
    run(room, {"op": "replace", "block": "a", "text": text})
    run(room, {"op": "replace", "block": "n", "text": "See the annex."})
    (block,) = room.read()
    assert [
        (run.text, run.marks) if isinstance(run, Run) else type(run).__name__ for run in block.runs
    ] == [
        ("Rent of ", {}),
        ("the flat", {"strong": {}}),
        "Note",
        (" lasts a\nyear, ", {}),
        ("signed", {"strong": {}}),
        "Field",
    ]
    assert block.notes[0].text == "See the annex."
    room = tab(paragraph("a", Field("page"), Run("Stranica")))
    run(room, {"op": "replace", "block": "a", "text": "<1/> is the page"})
    assert [getattr(run, "text", "") for run in room.read()[0].runs] == ["", " is the page"]
    room = rented()
    proposed(room, {"op": "replace", "block": "a", "text": "Rent of <1>the flat</1>."})
    assert by_whom(room.read()[0].runs) == [
        ("Najam ", ["deletion:7"]),
        ("stana", ["deletion:7"]),
        (" traje godinu dana.", ["deletion:7"]),
        ("Rent of ", ["insertion:7"]),
        ("the flat", ["insertion:7"]),
        (".", ["insertion:7"]),
    ]
    for room, text, code in [
        (noted(), "Rent <2/>", "tags"),
        (noted(), "<3/>Rent<2/>", "tags"),
        (noted(), "<1>Rent<2/><3/>", "tags"),
        (noted(), "</1>Rent<2/><3/>", "tags"),
        (noted(), "<4>Rent</4><2/><3/>", "tags"),
        (noted(), "<2>Rent</2><2/><3/>", "tags"),
        (proposal_text(), "Najam", "proposed"),
    ]:
        with pytest.raises(Refused) as refused:
            run(room, {"op": "replace", "block": "a", "text": text})
        assert refused.value.code == code, text


def test_a_block_with_proposals_or_text_on_more_lines_is_not_written_anew():
    for room, text, code in [
        (proposal_text(), "Najam kuće", "proposed"),
        (rented(), "Najam\nstana", "invalid"),
    ]:
        with pytest.raises(Refused) as refused:
            run(room, {"op": "rewrite", "block": "a", "text": text})
        assert refused.value.code == code


def test_blocks_and_a_table_written_under_a_proposer_are_proposed_inserted_whole():
    room = tab(paragraph("a", Run("Uvod")))
    new = {
        "type": "paragraph",
        "attrs": {"id": "b"},
        "content": [words("Stranica "), {"type": "field", "attrs": {"kind": "page"}}],
    }
    proposed(
        room,
        {"op": "insert", "at": {"after": "a"}, "blocks": [new, {"type": "pageBreak"}]},
        {"op": "table", "at": {"end": "body"}, "id": "t", "rows": [["1", "2"], ["3", "4"]]},
    )
    a, b, page, table = room.read()
    insertion = b.attrs["insertion"]
    assert (insertion["author"], insertion["user"]) == ("Ana Horvat", 7)
    assert by_whom(b.runs[:1]) == [("Stranica ", ["insertion:7"])]
    assert b.runs[1].proposed == {"insertion": insertion}
    assert page.attrs["insertion"] == insertion
    rows = table.attrs["proposedRows"]
    assert (
        set(rows) == set(table.grid.rows)
        and len({row["insertion"]["id"] for row in rows.values()}) == 1
    )
    assert rows[table.grid.rows[0]]["insertion"]["id"] != insertion["id"]
    assert "insertion" not in a.attrs
    reject(room)
    assert [(block.id, block.text) for block in room.read()] == [("a", "Uvod")]


def test_blocks_taken_out_under_a_proposer_stay_proposed_deleted_but_the_proposers_own():
    mine, ivos = {**change("m"), "user": 7}, {**change("i", "Ivo"), "user": 3}
    cells = [Cell(row, "c1", [paragraph(f"x{row}", Run(row))]) for row in ("r1", "r2")]
    grid = Grid(["r1", "r2"], ["c1"])
    room = tab(
        paragraph("a", Run("Prvi")),
        paragraph("b", Run("Drugi "), Run("dio", {"insertion": mine})),
        paragraph("c", Run("Moj", {"insertion": mine}), insertion=mine),
        Block("pageBreak", "k"),
        Block("table", "t", {"proposedRows": {"r1": {"deletion": ivos}}}, grid=grid, cells=cells),
        paragraph("d", Run("Kraj")),
    )
    proposed(room, {"op": "delete", "from": "b", "to": "t"})
    a, b, page, table, d = room.read()
    assert [block.id for block in (a, b, page, table, d)] == ["a", "b", "k", "t", "d"]
    deletion = b.attrs["deletion"]
    assert by_whom(b.runs) == [("Drugi ", ["deletion:7"])]
    assert page.attrs["deletion"] == deletion
    assert table.attrs["proposedRows"] == {"r1": {"deletion": ivos}, "r2": {"deletion": deletion}}
    assert "deletion" not in a.attrs and "deletion" not in d.attrs
    accept(room)
    assert [(block.id, block.text) for block in room.read()] == [("a", "Prvi"), ("d", "Kraj")]


def test_formatting_and_structure_apply_at_once_under_a_proposer():
    room = tab(paragraph("a", Run("Uvod")))
    proposed(
        room,
        {"op": "mark", "range": {"block": "a"}, "mark": "strong"},
        {"op": "set", "block": "a", "type": "heading", "attrs": {"level": 2}},
    )
    assert shown(room) == [("heading", "a", {"level": 2}, [("Uvod", {"strong": {}})])]
