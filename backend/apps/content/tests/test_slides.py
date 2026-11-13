from apps.content.blocks import Block, Run
from apps.content.slides import slides_of


def text(type: str, value: str = "", **attrs) -> Block:
    return Block(type, attrs=attrs, runs=[Run(value)] if value else [])


def test_slides_start_where_the_editors_start_them():
    content = [
        text("paragraph"),
        text("title", "Ponuda"),
        text("subtitle", "Listopad"),
        text("heading", "Cijene", level=1),
        text("heading", "Detalji", level=2),
        Block("slideBreak"),
        text("paragraph", "Kraj"),
    ]
    assert [[block.text or block.type for block in run] for run in slides_of(content)] == [
        ["Ponuda", "Listopad"],
        ["Cijene", "Detalji"],
        ["slideBreak", "Kraj"],
    ]


def test_text_before_the_first_slide_is_one_when_it_holds_anything():
    assert len(slides_of([text("paragraph", "Uvod"), text("heading", "A", level=1)])) == 2
    assert len(slides_of([Block("image"), text("heading", "A", level=1)])) == 2
    assert len(slides_of([text("paragraph")])) == 1
