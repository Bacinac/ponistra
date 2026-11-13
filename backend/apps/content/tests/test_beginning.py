import pytest

from apps.content import calculation, elements
from apps.content.blocks import Block, Grid, Run

from .helpers import fill
from .test_elements import first_tab

pytestmark = pytest.mark.django_db


def test_a_document_is_glanced_at_by_the_first_blocks_of_its_first_tab(api):
    tab = first_tab(api)
    table = Grid(
        ["r1", "r2"],
        ["a", "b"],
        texts={"r1:a": "Šifra", "r1:b": "Cijena", "r2:a": "'0042", "r2:b": "12,50"},
    )
    fill(
        tab,
        [
            Block("title", runs=[Run("Ponuda")]),
            Block("heading", attrs={"level": 2}, runs=[Run("Uvjeti")]),
            Block("paragraph", runs=[Run("Rok isporuke je 30 dana.")]),
            Block("table", "t", grid=table),
            Block("image", attrs={"blob": "ab" * 32, "alt": "Shema"}),
        ],
    )
    calculation.calculate(tab.document, {"t"}, {})
    elements.derive(tab.pk)
    assert api.get(f"/api/nodes/{tab.document_id}/beginning").json() == {
        "blocks": [
            {"type": "title", "text": "Ponuda", "level": None},
            {"type": "heading", "text": "Uvjeti", "level": 2},
            {"type": "paragraph", "text": "Rok isporuke je 30 dana.", "level": None},
            {"type": "table", "rows": [["Šifra", "Cijena"], ["0042", "12,5"]]},
            {"type": "image", "blob": "ab" * 32, "alt": "Shema"},
        ],
        "more": False,
    }


def test_a_long_document_says_there_is_more(api):
    tab = first_tab(api)
    fill(tab, [Block("paragraph", runs=[Run(f"Stavka {n}")]) for n in range(20)])
    elements.derive(tab.pk)
    beginning = api.get(f"/api/nodes/{tab.document_id}/beginning").json()
    assert [block["text"] for block in beginning["blocks"]] == [f"Stavka {n}" for n in range(12)]
    assert beginning["more"]
