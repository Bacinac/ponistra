import base64

import pytest

from apps.contacts import vcard

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
IPHONE = "\r\n".join(
    [
        "BEGIN:VCARD",
        "VERSION:3.0",
        "PRODID:-//Apple Inc.//iPhone OS 26.0//EN",
        "N:Horvat;Ana;Marija;dr.;",
        "FN:dr. Ana Marija Horvat",
        "ORG:Firma d.o.o.;Prodaja;",
        "TITLE:Voditeljica",
        "item1.EMAIL;type=INTERNET;type=pref:ana@firma.test",
        "item1.X-ABLabel:_$!<Other>!$_",
        "TEL;type=CELL;type=VOICE;type=pref:091 234 5678",
        "item2.TEL:01 2345 678",
        "item2.X-ABLabel:Ured Zagreb",
        "item3.ADR;type=WORK:;;Ilica 1;Zagreb;;10000;Hrvatska",
        "BDAY;X-APPLE-OMIT-YEAR=1604:1604-03-15",
        "NOTE:Prvi red\\nDrugi\\, treći",
        "PHOTO;ENCODING=b;TYPE=PNG:" + base64.b64encode(PNG).decode(),
        "X-SOCIALPROFILE;type=linkedin:http://linkedin.com/in/ana",
        "UID:7C1E6F2A-1111-4C3B-9A60-6A1C2D3E4F50",
        "END:VCARD",
        "",
    ]
)


def test_an_iphones_card_is_read_with_its_labels_birthday_without_a_year_and_photo():
    card = vcard.parsed(IPHONE)
    assert card.uid == "7C1E6F2A-1111-4C3B-9A60-6A1C2D3E4F50"
    assert card.fields == {
        "name": "dr. Ana Marija Horvat",
        "given": "Ana",
        "family": "Horvat",
        "middle": "Marija",
        "prefix": "dr.",
        "suffix": "",
        "nickname": "",
        "organisation": "Firma d.o.o.",
        "department": "Prodaja",
        "title": "Voditeljica",
        "birthday": "--03-15",
        "note": "Prvi red\nDrugi, treći",
    }
    assert [(each["kind"], each["label"], each["value"]) for each in card.points] == [
        ("email", "other", "ana@firma.test"),
        ("phone", "mobile", "091 234 5678"),
        ("phone", "Ured Zagreb", "01 2345 678"),
        ("address", "work", "Ilica 1\n10000 Zagreb\nHrvatska"),
    ]
    assert card.photo == PNG
    assert card.extra == ["X-SOCIALPROFILE;type=linkedin:http://linkedin.com/in/ana"]


def test_a_card_written_reads_back_as_it_was_and_keeps_what_ponistra_does_not_show():
    card = vcard.parsed(IPHONE)
    written = vcard.written(card)
    assert written.endswith("END:VCARD\r\n")
    assert "BDAY;X-APPLE-OMIT-YEAR=1604:1604-03-15\r\n" in written
    assert "X-ABLabel:Ured Zagreb" in written
    again = vcard.parsed(written)
    assert (again.fields, again.points, again.photo, again.extra, again.uid) == (
        card.fields,
        card.points,
        card.photo,
        card.extra,
        card.uid,
    )


def test_long_lines_are_folded_at_75_octets_without_splitting_a_letter():
    card = vcard.Card(uid="u")
    card.fields["note"] = "šđčćž" * 40
    written = vcard.written(card)
    assert all(len(line.encode()) <= 75 for line in written.split("\r\n"))
    assert vcard.parsed(written).fields["note"] == "šđčćž" * 40


def test_vcard_4_and_2_1_cards_are_read_too():
    four = vcard.parsed(
        "BEGIN:VCARD\nVERSION:4.0\nFN:Marko\nTEL;VALUE=uri;TYPE=work:tel:+385-1-234-5678\n"
        f"PHOTO:data:image/png;base64,{base64.b64encode(PNG).decode()}\nKIND:group\nEND:VCARD\n"
    )
    assert four.points == [
        {"kind": "phone", "label": "work", "value": "+385-1-234-5678", "parts": []}
    ]
    assert (four.photo, four.group, four.extra) == (PNG, True, ["KIND:group"])
    old = vcard.parsed(
        "BEGIN:VCARD\nVERSION:2.1\nN;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:=C5=A0imi=C4=87;Ana\n"
        "TEL;CELL:0912345678\nEND:VCARD\n"
    )
    assert (old.fields["family"], old.fields["given"]) == ("Šimić", "Ana")
    assert old.points[0]["label"] == "mobile"


@pytest.mark.parametrize("text", ["", "FN:Ana\n", "BEGIN:VCARD\nFN:Ana\n"])
def test_what_is_not_a_card_is_refused(text):
    with pytest.raises(vcard.Malformed):
        vcard.parsed(text)
