from apps.mail.safe import cleaned


def test_only_links_out_and_images_of_its_own_are_kept():
    markup = (
        '<a href="https://example.com">a</a><a href="mailto:ana@example.com">b</a>'
        '<a href="data:text/html,x">c</a><a href="#top">d</a>'
        '<img src="data:image/png;base64,AAAA"><img src="data:image/svg+xml,x">'
        '<img src="cid:unknown">'
        '<table background="/api/blobs/x"><tr><td>e</td></tr></table>'
    )
    shown, remote = cleaned(markup, {}, None)
    assert 'href="https://example.com" rel="noopener noreferrer"' in shown
    assert 'href="mailto:ana@example.com"' in shown
    assert shown.count("href=") == 2
    assert 'src="data:image/png;base64,AAAA"' in shown and shown.count("src=") == 1
    assert "/api/blobs" not in shown and not remote


def test_styles_stay_and_their_images_from_elsewhere_are_noticed():
    shown, remote = cleaned(
        '<style>@import "https://fonts.example/a.css"; p { color: red }</style>'
        '<p style="color: blue">x</p>',
        {},
        None,
    )
    assert "<style>" in shown and 'style="color: blue"' in shown and remote


def test_images_from_elsewhere_once_let_in_point_at_ponistra_in_tags_and_styles():
    shown, remote = cleaned(
        '<img src="https://cdn.example/a.png"><table background="//cdn.example/b.png"></table>'
        '<style>td { background: url( "https://cdn.example/c.png" ) }</style>'
        '<p style="background-image: url(http://cdn.example/d.png)">x</p>'
        '<a href="https://example.com">e</a>',
        {},
        lambda address: f"/served/{address.rpartition('/')[2]}",
    )
    assert remote
    assert 'src="/served/a.png"' in shown and 'background="/served/b.png"' in shown
    assert "url('/served/c.png')" in shown and "url('/served/d.png')" in shown
    assert 'href="https://example.com"' in shown and "cdn.example" not in shown
