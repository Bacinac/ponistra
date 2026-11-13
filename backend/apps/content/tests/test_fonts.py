from apps.content import fonts


def test_only_a_face_of_other_widths_is_reported():
    named = {"Aptos", "Arial", "Calibri", "Calibri Light", "Cambria", "Inter", "Wingdings"}
    assert fonts.substituted(named) == [
        {"from": "Calibri Light", "to": "Carlito"},
        {"from": "Cambria", "to": "Caladea"},
        {"from": "Wingdings", "to": None},
    ]


def test_office_gets_the_font_ours_stands_for():
    named = ("Liberation Sans", "Carlito", "Intos", "Gelasio", "Inter", "Arial")
    assert [fonts.office(name) for name in named] == [
        "Arial",
        "Calibri",
        "Aptos",
        "Georgia",
        "Inter",
        "Arial",
    ]
