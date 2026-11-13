from apps.imports import colors


def test_a_colour_comes_over_as_the_file_s_own_and_the_text_s_dark_ones_as_the_text_s():
    found = ("12A9B0", "6B6B70", "FFFFFF", "C00000", "000000", "404040", "1F1F1F", "auto", None)
    assert [colors.text_color(value) for value in found] == [
        "#12a9b0",
        "gray",
        "#ffffff",
        "#c00000",
        None,
        None,
        None,
        None,
        None,
    ]


def test_a_highlight_comes_over_as_word_draws_it_and_a_fill_as_its_own():
    assert colors.highlight("yellow") == "#ffff00"
    assert colors.highlight("darkCyan", "C00000") == "#008080"
    assert colors.highlight("none") is None
    assert colors.highlight(None, "D9E2F3") == "#d9e2f3"
    assert colors.highlight(None, "FDE68A") == "yellow"
    assert colors.highlight(None, "FFFFFF") is None
    assert colors.highlight(None, None) is None
