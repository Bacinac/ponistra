from apps.actions.tests.test_actions import priced
from apps.ai.reading import changes_of, whole_of
from apps.content.blocks import Block, Note, Run


def paragraph(id: str, text: str, **attrs) -> Block:
    return Block("paragraph", id, attrs, runs=[Run(text)])


def test_changes_are_what_was_added_removed_moved_or_changed_word_by_word():
    noted = paragraph("n", "Plaća se mjesečno.")
    noted.runs.append(Note(id="f"))
    noted.runs[1].runs = [Run("Do petog u mjesecu.")]
    old = [
        Block("title", "t0", runs=[Run("Ugovor")]),
        paragraph("a", "Najam stana na godinu dana."),
        paragraph("b", "Cijena"),
        paragraph("c", "Kaucija se vraća."),
        noted,
        paragraph("d", "Potpisi"),
        priced(("Vijak", "3", "1,5"), ("Matica", "2", "0,5")),
    ]
    renoted = paragraph("n", "Plaća se mjesečno.")
    renoted.runs.append(Note(id="f"))
    renoted.runs[1].runs = [Run("Do desetog u mjesecu.")]
    new = [
        Block("title", "t0", runs=[Run("Ugovor")]),
        paragraph("a", "Najam kuće na dvije godine."),
        paragraph("b", "Cijena", list="bullet"),
        paragraph("d", "Potpisi"),
        renoted,
        paragraph("e", "Ugovor stupa na snagu potpisom."),
        priced(("Vijak", "4", "1,5")),
    ]

    assert changes_of(old, new) == [
        "[a] paragraph changed: Najam [-stana-]{+kuće+} na [-godinu dana-]{+dvije godine+}.",
        "[b] paragraph → bullet item changed: Cijena",
        "[c] paragraph removed: Kaucija se vraća.",
        "[d] paragraph moved: Potpisi",
        "[f] footnote changed: Do [-petog-]{+desetog+} u mjesecu.",
        "[e] paragraph added: Ugovor stupa na snagu potpisom.",
        "[t r2] table row changed: | Vijak | [-3-]{+4+} | 1,5 |",
        "[t r3] table row removed: | Matica | 2 | 0,5 |",
    ]
    assert changes_of(new, new) == []
    assert changes_of([], new[:2]) == [
        "[t0] title added: Ugovor",
        "[a] paragraph added: Najam kuće na dvije godine.",
    ]


def test_the_whole_tab_reads_with_its_attributes_tags_proposals_cells_and_styles():
    proposal = {"id": "p1", "author": "Ana Horvat", "date": "2026-10-19T10:00:00Z"}
    noted = paragraph("a", "Najam ", align="center")
    noted.runs += [Run("stana", {"strong": {}, "insertion": proposal}), Note(id="f")]
    noted.runs[2].runs = [Run("Do petog.", {"em": {}})]
    table = priced(("Vijak", "3", "1,5"))
    table.grid.formulas["r2:a"] = ["pieces"]
    table.grid.values["r2:a"] = {"text": "4,50", "kind": "number"}
    table.attrs |= {"name": "Cjenik", "proposedRows": {"r2": {"deletion": proposal}}}
    theme = {"headings": "Inter", "text": "Lora"}
    looks = {
        "text": {"kind": "text", "name": "", "font": "text", "size": 12},
        "naslov": {"kind": "h1", "name": "Naslov", "font": "Arial", "size": 20.5},
    }
    lines = whole_of(
        [
            Block("heading", "h", {"level": 2}, runs=[Run("Ugovor")]),
            noted,
            Block("pageBreak", "k", {"deletion": proposal}),
            table,
        ],
        {"t": {"r2:a": "=B2*C2"}},
        theme,
        looks,
    )
    assert lines == [
        '[h] heading {"level":2}: Ugovor',
        '[a] paragraph {"align":"center"}: Najam <1>stana</1><2/>',
        "    tags: <1> strong, proposed inserted by Ana Horvat (p1) · <2> footnote f",
        "[f] footnote: <1>Do petog.</1>",
        "    tags: <1> em",
        "[k] pageBreak",
        "    block: proposed deleted by Ana Horvat (p1)",
        '[t] table {"designs":[{"name":"grid"}],"name":"Cjenik"}',
        "    rows: r1=1 r2=2",
        "    columns: a=A b=B c=C",
        "    rows proposed: r2 proposed deleted by Ana Horvat (p1)",
        '[t r1 a] Artikl {"marks":{"strong":{}}}',
        '[t r1 b] Količina {"marks":{"strong":{}}}',
        '[t r1 c] Cijena {"marks":{"strong":{}}}',
        "[t r2 a] =B2*C2 → 4,50",
        "[t r2 b] 3",
        '[t r2 c] 1,5 format "#,##0.00 \\"€\\""',
        "styles:",
        "[text] text: font text (Lora), 12 pt",
        '[naslov] "Naslov" h1: font Arial, 20.5 pt',
    ]
