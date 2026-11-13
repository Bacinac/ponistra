import pytest

from apps.content import calculation, filtering
from apps.content import rows as stored
from apps.content.blocks import Block, Grid, light_cell
from apps.content.filtering import Invalid, View
from apps.content.models import Grid as StoredGrid
from apps.documents.models import Node, Tab

from .helpers import fill

pytestmark = pytest.mark.django_db

TEXTS = {"r1": "Kava", "r2": "sok", "r3": "kava", "r4": "'007", "r5": "", "r6": "kava"}
NUMBERS = {"r1": "12", "r2": "3,5", "r3": "", "r4": "100", "r5": "x", "r6": "1"}


def grid() -> int:
    """A table whose first column holds texts, one kept a text by its apostrophe, and whose
    second numbers as typed in Croatian, its last row hidden."""
    document = Node.objects.create(kind=Node.Kind.DOCUMENT, title="Filtar")
    tab = Tab.objects.create(document=document, position=0)
    cells = [light_cell(f"{row}:a", text) for row, text in TEXTS.items() if text]
    cells += [light_cell(f"{row}:b", text) for row, text in NUMBERS.items() if text]
    table = Block(
        "table", "t", {"hidden": {"rows": ["r6"]}}, grid=Grid(list(TEXTS), ["a", "b"]), cells=cells
    )
    fill(tab, [table])
    calculation.calculate(document, {"t"}, {})
    return StoredGrid.objects.get(document=document, table="t").pk


def shown(grid: int, *conditions: dict) -> list[str]:
    return stored.ids_in(grid, 0, 99, View(conditions))


def test_a_view_shows_the_rows_not_hidden_that_meet_every_condition_and_counts_among_them():
    found = grid()
    kava = {"col": "a", "values": ["kava"]}
    assert shown(found) == ["r1", "r2", "r3", "r4", "r5"]
    assert shown(found, kava) == ["r1", "r3"]
    assert stored.count(found, View((kava,))) == 2
    assert stored.places_of(found, ["r3", "r2", "r6"], View((kava,))) == {"r3": 1}
    assert stored.ids_at(found, [1, 2], View((kava,))) == {1: "r3"}
    assert View((kava,)).passing(found, ["r1", "r2", "r6"]) == {"r1"}
    assert shown(found, {"col": "a", "values": [""]}) == ["r5"]
    assert shown(found, {"col": "a", "op": "equals", "value": "007"}) == ["r4"]
    assert shown(found, {"col": "a", "op": "begins", "value": "KA"}) == ["r1", "r3"]
    assert shown(found, {"col": "a", "op": "notContains", "value": "a"}) == ["r2", "r4", "r5"]
    assert shown(found, {"col": "a", "op": "contains", "value": "%"}) == []
    assert shown(found, {"col": "b", "op": "greater", "value": "3"}) == ["r1", "r2", "r4"]
    assert shown(found, {"col": "b", "op": "lessEqual", "value": "3,5"}) == ["r2"]
    assert shown(found, kava, {"col": "b", "op": "greater", "value": "3"}) == ["r1"]


def test_a_column_offers_the_texts_the_other_conditions_let_through_with_their_counts():
    found = grid()
    texts, more = filtering.texts(found, View(({"col": "a", "values": ["sok"]},)), "a")
    assert not more
    assert texts[0] == ("007", 1)
    assert texts[1][0].lower() == "kava" and texts[1][1] == 2
    assert texts[2:] == [("sok", 1), ("", 1)]
    numbers = View(({"col": "b", "op": "greater", "value": "3"},))
    assert [count for _, count in filtering.texts(found, numbers, "a")[0]] == [1, 1, 1]


def test_conditions_are_checked_against_the_columns_and_kept_in_one_form():
    cols = ["a", "b"]
    given = [{"col": "a", "values": ["b", "a", "b"]}, {"col": "b", "op": "less", "value": "1,5"}]
    assert filtering.checked(given, cols, "hr") == [
        {"col": "a", "values": ["a", "b"]},
        {"col": "b", "op": "less", "value": "1,5"},
    ]
    assert filtering.checked([], cols, "hr") == []
    for wrong in [
        {"col": "c", "values": ["x"]},
        [{"col": "a", "values": ["x"]}, {"col": "a", "values": ["y"]}],
        {"col": "a", "values": []},
        {"col": "a", "values": [1]},
        {"col": "a", "op": "greater", "value": "dva"},
        {"col": "a", "op": "like", "value": "x"},
        {"col": "a", "values": ["x"], "op": "equals", "value": "x"},
        "a",
    ]:
        with pytest.raises(Invalid):
            filtering.checked(wrong if isinstance(wrong, list) else [wrong], cols, "hr")
