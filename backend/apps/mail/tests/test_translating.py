import secrets

import pytest

from apps.actions.models import ActionRun
from apps.ai import installation, model
from apps.ai.tests.recorded import Recorded, message, used
from apps.mail import sync, translating
from apps.mail.imap import imap
from apps.mail.models import Message, Role, Translation

from .mox import LOGIN, SERVER, kept_in_sent, letter, put, synced

pytestmark = [pytest.mark.django_db, pytest.mark.xdist_group("mox")]

JSON = "application/json"
GERMAN = (
    "Sehr geehrte Damen und Herren, anbei sende ich Ihnen das Angebot für die Wartung der "
    "Anlagen im kommenden Jahr."
)
CROATIAN = "Poštovane dame i gospodo, u privitku vam šaljem ponudu za održavanje postrojenja."


@pytest.fixture
def reader(client, account):
    client.force_login(account.owner)
    return client


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(installation, "enabled", lambda: True)


def answered(monkeypatch, *answers) -> Recorded:
    recorded = Recorded(*answers)
    monkeypatch.setattr(model, "answer", recorded)
    return recorded


def written(subject: str, *blocks: str) -> dict:
    return message(
        "tool_use",
        used(
            "u1",
            "translation",
            {
                "subject": subject,
                "blocks": [{"id": number, "text": text} for number, text in enumerate(blocks, 1)],
            },
        ),
        model=translating.MODEL,
        usage={"input_tokens": 700, "output_tokens": 90},
    )


def opened(account, folder, subject: str, text: str) -> Message:
    put(folder, letter(subject, text))
    synced(account, folder)
    return Message.objects.get(subject=subject)


@pytest.mark.parametrize(
    ("subject", "text", "language"),
    [
        ("Angebot", GERMAN, "de"),
        (
            "Ponuda",
            "Poštovani, u prilogu vam šaljem ponudu za održavanje opreme za narednu godinu.",
            "hr",
        ),
        (
            "Angebot",
            f"[Hier klicken](https://example.com/{'x' * 40}) {GERMAN} https://x.com/{'y' * 30}",
            "de",
        ),
        ("", "12345 — 678", None),
    ],
)
def test_code_knows_the_language_a_message_is_written_in(subject, text, language):
    assert translating.language_of(Message(subject=subject, text=text)) == language


def test_a_block_keeps_its_links_formatting_images_and_line_breaks():
    markup = (
        '<p>Sehr geehrte <b>Frau Kovač</b>,<br style="x">anbei das '
        '<a href="https://example.com/o">Angebot</a>.<img src="data:image/png;base64,AA" alt="l">'
        "</p><style>p{color:red}</style><table><tr><td>Preis: 100 €</td><td>42</td></tr></table>"
    )
    cut = translating.body(markup, None)
    assert list(cut.blocks.values()) == [
        "Sehr geehrte <1>Frau Kovač</1>,<br/>anbei das <2>Angebot</2>.<3/>",
        "Preis: 100 €",
    ]
    first, price = cut.blocks
    translated = {
        first: "Poštovana <1>gospođo Kovač</1>,<br/>u privitku je <2>ponuda</2> & više.<3/>",
        price: "Cijena: 100 €",
    }
    assert translating.put_back(cut, translated) == (
        '<p>Poštovana <b>gospođo Kovač</b>,<br style="x">u privitku je '
        '<a href="https://example.com/o">ponuda</a> &amp; više.'
        '<img src="data:image/png;base64,AA" alt="l">'
        "</p><style>p{color:red}</style><table><tr><td>Cijena: 100 €</td><td>42</td></tr></table>"
    )


def test_a_block_is_one_line_however_its_html_breaks_and_a_preformatted_one_keeps_its_lines():
    cut = translating.body(
        "<p>Danke\n  für\tIhre\r\nNachricht</p><pre>Zeile 1\n  Zeile 2</pre>", None
    )
    assert list(cut.blocks.values()) == ["Danke für Ihre Nachricht", "Zeile 1<br/>  Zeile 2"]
    thanks, lines = cut.blocks
    translated = {thanks: "Hvala na poruci", lines: "Redak 1<br/>  Redak 2"}
    assert translating.put_back(cut, translated) == (
        "<p>Hvala na poruci</p><pre>Redak 1\n  Redak 2</pre>"
    )


def test_a_block_whose_marks_the_model_lost_keeps_its_text_and_images():
    cut = translating.body('<p>Siehe <a href="https://example.com">hier</a><img src="x"></p>', None)
    (key,) = cut.blocks
    assert translating.put_back(cut, {key: "Vidi ovdje"}) == '<p>Vidi ovdje<img src="x"></p>'


def test_a_closing_tag_opened_in_an_earlier_block_stays_where_it_was():
    cut = translating.body('<span style="color:red"><div>Erste</div>Zweite</span> und mehr', None)
    assert list(cut.blocks.values()) == ["Erste", "Zweite", "und mehr"]
    translated = dict(zip(cut.blocks, ["Prvi", "Drugi", "i više"], strict=True))
    assert translating.put_back(cut, translated) == (
        '<span style="color:red"><div>Prvi</div>Drugi</span> i više'
    )


def test_a_plain_message_is_translated_paragraph_by_paragraph():
    cut = translating.body(None, "Hallo Ana,\nanbei das Angebot.\n\n> Alt\n\nGrüße\n")
    assert list(cut.blocks.values()) == ["Hallo Ana,<br/>anbei das Angebot.", "> Alt", "Grüße"]
    hello, _, regards = cut.blocks
    translated = {hello: "Bok Ana,<br/>u privitku je ponuda & cijena.", regards: "Pozdrav"}
    assert translating.put_back(cut, translated) == (
        "Bok Ana,\nu privitku je ponuda & cijena.\n\n> Alt\n\nPozdrav\n"
    )


def test_the_languages_a_user_reads_and_whether_their_mail_is_translated_as_it_opens(reader):
    found = reader.get("/api/translation").json()
    assert (found["languages"], found["automatic"]) == (None, False)
    assert {"hr", "en", "de"} <= set(found["known"])
    assert not {"bs", "sr"} & set(found["known"])
    chosen = {"languages": ["hr", "de", "hr"], "automatic": True}
    found = reader.put("/api/translation", chosen, content_type=JSON).json()
    assert (found["languages"], found["automatic"]) == (["hr", "de"], True)
    for wrong in ({"languages": ["xx"], "automatic": True}, {"languages": [], "automatic": True}):
        assert reader.put("/api/translation", wrong, content_type=JSON).status_code == 400
    found = reader.put("/api/translation", {"automatic": False}, content_type=JSON).json()
    assert (found["languages"], found["automatic"]) == (None, False)


def test_a_message_is_translated_once_the_user_lets_it_out_and_kept_for_its_language(
    reader, account, folder, ai, monkeypatch
):
    kept = opened(account, folder, "Angebot für die Wartung", GERMAN)
    url = f"/api/mail/messages/{kept.pk}/translation"
    shown = reader.get(f"/api/mail/messages/{kept.pk}").json()
    assert (shown["language"], shown["translated"]) == ("de", None)
    recorded = answered(monkeypatch, written("Ponuda za održavanje", CROATIAN))
    response = reader.post(url, {"language": "hr"}, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (428, "consent_needed")
    assert recorded.asked == []

    response = reader.post(url, {"language": "hr", "consent": "once"}, content_type=JSON)
    assert response.json() == {"translated": "hr"}
    (request,) = recorded.asked
    assert (request["model"], request["output_config"]) == (translating.MODEL, {"effort": "low"})
    assert request["messages"][0]["content"] == f"[subject] Angebot für die Wartung\n[1] {GERMAN}"
    run = ActionRun.objects.get()
    assert (run.action, run.target, run.parameters) == (
        translating.ACTION,
        {"message": kept.pk},
        {"language": "hr"},
    )
    assert (run.state, run.consent, run.consented_by) == ("done", "once", account.owner)

    shown = reader.get(f"/api/mail/messages/{kept.pk}?into=hr").json()
    assert (shown["subject"], shown["language"], shown["translated"]) == (
        "Ponuda za održavanje",
        "de",
        "hr",
    )
    assert shown["text"] == f"{CROATIAN}\r\n"
    assert reader.get(f"/api/mail/messages/{kept.pk}?into=en").json()["translated"] is None
    assert reader.post(url, {"language": "hr"}, content_type=JSON).json() == {"translated": "hr"}
    assert len(recorded.asked) == 1
    found = reader.get("/api/search", {"q": "postrojenja"}).json()["mail"]
    assert [each["id"] for each in found] == [kept.pk]


def test_mail_is_translated_without_asking_once_the_user_agrees_for_all_of_it(
    reader, account, folder, ai, monkeypatch
):
    kept = opened(account, folder, "Angebot", GERMAN)
    reader.put("/api/translation", {"automatic": True}, content_type=JSON)
    answered(monkeypatch, written("Ponuda", CROATIAN))
    url = f"/api/mail/messages/{kept.pk}/translation"
    assert reader.post(url, {"language": "hr"}, content_type=JSON).json() == {"translated": "hr"}
    assert ActionRun.objects.get().consent == "user"
    assert Translation.objects.get().text == CROATIAN


def test_nothing_is_translated_with_the_installations_ai_off_or_into_an_unknown_language(
    reader, account, folder, monkeypatch
):
    monkeypatch.setattr(installation, "enabled", lambda: False)
    kept = opened(account, folder, "Angebot", GERMAN)
    url = f"/api/mail/messages/{kept.pk}/translation"
    response = reader.post(url, {"language": "hr", "consent": "once"}, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (409, "ai_off")
    response = reader.post(url, {"language": "xx", "consent": "once"}, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (400, "invalid_language")


@pytest.mark.django_db(transaction=True)
def test_a_reply_goes_in_the_language_of_the_message_it_answers_and_keeps_what_the_user_wrote(
    reader, account, folder, ai, monkeypatch
):
    with imap(*SERVER, LOGIN) as connection:
        sync.sources(connection, account)
    kept = opened(account, folder, "Angebot", GERMAN)
    url = f"/api/mail/messages/{kept.pk}/translated-reply"
    wrote = "<p>Poštovani, <strong>hvala</strong> na ponudi.</p>"
    given = {
        "language": "hr",
        "subject": "Re: Angebot",
        "html": wrote,
        "heading": ["Ana Kovač <ana@example.com> je napisala:"],
    }
    recorded = answered(
        monkeypatch,
        written("Ponuda", CROATIAN),
        written(
            "Re: Angebot",
            "Sehr geehrte Damen und Herren, <1>danke</1> für das Angebot.",
            "Ana Kovač <ana@example.com> schrieb:",
        ),
    )
    reading = f"/api/mail/messages/{kept.pk}/translation"
    reader.post(reading, {"language": "hr", "consent": "once"}, content_type=JSON)
    response = reader.post(url, given, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (428, "consent_needed")

    translated = reader.post(url, given | {"consent": "once"}, content_type=JSON).json()
    request = recorded.asked[1]
    assert request["messages"][0]["content"] == (
        f"[answered] {GERMAN}\n[subject] Re: Angebot\n[1] Poštovani, <1>hvala</1> na ponudi.\n"
        "[2] Ana Kovač <ana@example.com> je napisala:"
    )
    assert "German" in request["system"][0]["text"]
    assert (translated["language"], translated["subject"], translated["heading"]) == (
        "de",
        "Re: Angebot",
        ["Ana Kovač <ana@example.com> schrieb:"],
    )
    assert translated["html"] == (
        "<p>Sehr geehrte Damen und Herren, <strong>danke</strong> für das Angebot.</p>"
    )
    source = translated["source"]
    assert (source["language"], source["subject"]) == ("hr", "Re: Angebot")
    run = ActionRun.objects.get(pk=source["run"])
    assert (run.action, run.target, run.parameters, run.consent) == (
        translating.REPLY,
        {"message": kept.pk},
        {"language": "de"},
        "once",
    )

    subject = f"Re: Angebot {secrets.token_hex(4)}"
    sending = {
        "account": account.pk,
        "to": [{"name": "Ana Kovač", "address": "ana@example.com"}],
        "subject": subject,
        "html": translated["html"],
        "heading": translated["heading"],
        "original": kept.pk,
        "as": "reply",
    }
    for wrong in ({**source, "run": str(kept.pk)}, {**source, "language": "xx"}):
        response = reader.post("/api/mail/send", sending | {"source": wrong}, content_type=JSON)
        assert (response.status_code, response.json()["error"]) == (400, "invalid_reply_source")
    response = reader.post("/api/mail/send", sending | {"source": source}, content_type=JSON)
    assert response.json() == {"refused": [], "kept": True}
    out = kept_in_sent(subject).get_body(("html",)).get_content()
    assert "<strong>danke</strong>" in out
    assert "Ana Kovač &lt;ana@example.com&gt; schrieb:" in out
    assert "hvala" not in out

    mine = Message.objects.get(folder__role=Role.SENT)
    shown = reader.get(f"/api/mail/messages/{mine.pk}?into=hr").json()
    assert (shown["language"], shown["translated"], shown["subject"]) == ("de", "hr", "Re: Angebot")
    assert "Poštovani, <strong>hvala</strong> na ponudi." in shown["html"]
    assert "Ana Kovač &lt;ana@example.com&gt; je napisala:" in shown["html"]
    assert CROATIAN in shown["html"]
    assert len(recorded.asked) == 2
    found = reader.get("/api/search", {"q": "hvala"}).json()["mail"]
    assert [each["id"] for each in found] == [mine.pk]
