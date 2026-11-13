import pytest

from apps.access.tests.test_access import create
from apps.actions.models import ActionRun
from apps.ai import installation, model
from apps.ai.models import SpeechConsent
from apps.ai.spoken import ACTION, MODEL
from apps.ai.tests.recorded import Recorded, message, used
from apps.contacts.models import Contact
from apps.documents.tests.test_links import made, place
from apps.help.tests.test_help import shelf  # noqa: F401
from apps.mail.models import Account

pytestmark = pytest.mark.django_db

JSON = "application/json"
SAID = "sastanak s Anom sutra u deset u uredu"


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(installation, "enabled", lambda: True)


def answered(monkeypatch, *answers) -> Recorded:
    recorded = Recorded(*answers)
    monkeypatch.setattr(model, "answer", recorded)
    return recorded


def chosen(tool, **fields):
    return message(
        "tool_use",
        used("u1", tool, fields),
        model=MODEL,
        usage={"input_tokens": 700, "output_tokens": 40},
    )


def understand(client, text=SAID, zone="Europe/Zagreb"):
    return client.post("/api/speech/understand", {"text": text, "zone": zone}, content_type=JSON)


def test_what_was_said_is_read_as_an_event_under_the_speech_consent(api, ai, monkeypatch):
    event = {"summary": "Sastanak s Anom", "day": "2026-11-03", "time": "10:00", "location": "Ured"}
    recorded = answered(monkeypatch, chosen("event", **event))
    response = understand(api)
    assert (response.status_code, response.json()["error"]) == (403, "speech_consent")
    assert recorded.asked == []

    SpeechConsent.objects.create(user=api.user)
    response = understand(api)
    assert response.status_code == 200, response.json()
    assert response.json() == {"intent": "event", **event}
    (request,) = recorded.asked
    assert request["model"] == MODEL
    assert request["messages"][0]["content"].startswith("Now is ")
    assert request["messages"][0]["content"].endswith(f"\n\n{SAID}")
    assert {tool["name"] for tool in request["tools"]} == {
        "open",
        "search",
        "link",
        "person",
        "mail",
        "document",
        "event",
        "task",
        "help",
        "note",
    }
    run = ActionRun.objects.get()
    assert (run.action, run.state, run.consent, run.consented_by) == (
        ACTION,
        "done",
        "user",
        api.user,
    )


def test_a_task_and_a_note_are_read_as_they_are(api, ai, monkeypatch):
    SpeechConsent.objects.create(user=api.user)
    answered(monkeypatch, chosen("task", text="Nazvati servis"), chosen("note"))
    assert understand(api, "podsjeti me da nazovem servis").json() == {
        "intent": "task",
        "text": "Nazvati servis",
    }
    assert understand(api, "ideja za novi logo").json() == {"intent": "note"}


@pytest.mark.usefixtures("shelf")
def test_a_question_about_the_suite_offers_the_articles_of_its_help(api, ai, monkeypatch):
    SpeechConsent.objects.create(user=api.user)
    answered(monkeypatch, chosen("help", text="odgoda"), chosen("help", text="teleport"))
    found = understand(api, "kako se odgađa poruka?").json()
    assert found["intent"] == "help"
    assert "mail/snoozing" in [each["id"] for each in found["articles"]]
    assert "admin/users" not in [each["id"] for each in found["articles"]]
    assert understand(api, "ima li teleport?").json() == {
        "intent": "help",
        "text": "teleport",
        "articles": [],
    }


def test_nothing_is_read_while_the_installation_has_no_model(api, monkeypatch):
    SpeechConsent.objects.create(user=api.user)
    monkeypatch.setattr(installation, "enabled", lambda: False)
    response = understand(api)
    assert (response.status_code, response.json()["error"]) == (409, "ai_off")


def test_a_dictated_page_is_not_read(api, ai):
    SpeechConsent.objects.create(user=api.user)
    response = understand(api, "riječ " * 400)
    assert (response.status_code, response.json()["error"]) == (400, "invalid_text")


def test_a_message_a_search_and_a_place_are_read_as_they_are(api, ai, monkeypatch):
    SpeechConsent.objects.create(user=api.user)
    message = {"to": ["Eva"], "subject": "Kašnjenje", "text": "Kasnim deset minuta."}
    found = {"text": "", "kind": "mail", "from": "Eva"}
    answered(
        monkeypatch,
        chosen("mail", **message),
        chosen("search", **found),
        chosen("open", place="mail"),
    )
    assert understand(api, "napiši Evi da kasnim deset minuta").json() == {
        "intent": "mail",
        **message,
    }
    assert understand(api, "odgovori Evi na mail").json() == {"intent": "search", **found}
    assert understand(api, "otvori poštu").json() == {"intent": "open", "place": "mail"}


def test_a_message_goes_from_the_account_said_among_the_users(api, ai, monkeypatch):
    SpeechConsent.objects.create(user=api.user)
    for address, label in [("ivo@firma.test", "Posao"), ("ime@gmail.com", "")]:
        Account.objects.create(owner=api.user, address=address, label=label, username=address)
    message = {
        "to": ["Eva"],
        "subject": "Ručak",
        "text": "Stižem u jedan.",
        "account": "ime@gmail.com",
    }
    recorded = answered(monkeypatch, chosen("mail", **message))
    assert understand(api, "napiši Evi s Gmaila da stižem u jedan").json() == {
        "intent": "mail",
        **message,
    }
    (request,) = recorded.asked
    assert (
        "\nTheir mail accounts: ivo@firma.test, Posao; ime@gmail.com\n"
        in request["messages"][0]["content"]
    )
    (mail,) = [tool for tool in request["tools"] if tool["name"] == "mail"]
    assert mail["input_schema"]["properties"]["account"] == {
        "enum": ["ivo@firma.test", "ime@gmail.com"]
    }


def test_a_person_is_found_among_the_contacts_by_how_their_name_sounds(api, ai, monkeypatch):
    SpeechConsent.objects.create(user=api.user)
    for name in ["Dino Vrančić", "Boro Vrančić", "Ana Kovač"]:
        Contact.objects.create(owner=api.user, name=name, uid=name, href=f"{name}.vcf")
    dino, boro = Contact.objects.filter(name__endswith="Vrančić").order_by("name").reverse()
    answered(monkeypatch, chosen("person", name="Dino Vrančec"), chosen("person", name="Vrančić"))
    assert understand(api, "kad je rođendan Dina Vrančeca").json() == {
        "intent": "person",
        "name": "Dino Vrančec",
        "people": [{"id": dino.pk, "name": "Dino Vrančić"}],
    }
    assert understand(api, "Vrančićev broj").json()["people"] == [
        {"id": boro.pk, "name": "Boro Vrančić"},
        {"id": dino.pk, "name": "Dino Vrančić"},
    ]


def test_a_link_is_found_on_the_page_of_links_by_its_name(api, ai, monkeypatch):
    SpeechConsent.objects.create(user=api.user)
    own = place(api)
    grafana = made(api, href="https://grafana.example", title="Grafana", parent=own)
    dcm = made(api, href="https://dcm.example", title="Proxmox DCM", parent=own)
    backup = made(api, href="https://pbs.example", title="Proxmox Backup Server", parent=own)
    made(api, href="https://drugdje.example", title="Grafana", parent=create(api, "folder", "Mapa"))
    answered(
        monkeypatch,
        chosen("link", name="Grafana"),
        chosen("link", name="Proxmox"),
        chosen("link", name="Porezna"),
    )
    assert understand(api, "idi na Grafanu").json() == {
        "intent": "link",
        "name": "Grafana",
        "links": [{"id": grafana["id"], "title": "Grafana", "href": grafana["href"]}],
    }
    assert [each["id"] for each in understand(api, "otvori Proxmox").json()["links"]] == [
        backup["id"],
        dcm["id"],
    ]
    assert understand(api, "otvori Poreznu").json()["links"] == []


def test_the_page_of_links_is_a_place_to_open(api, ai, monkeypatch):
    SpeechConsent.objects.create(user=api.user)
    recorded = answered(monkeypatch, chosen("open", place="links"))
    assert understand(api, "pokaži mi poveznice").json() == {"intent": "open", "place": "links"}
    (request,) = recorded.asked
    (opening,) = [tool for tool in request["tools"] if tool["name"] == "open"]
    assert "links" in opening["input_schema"]["properties"]["place"]["enum"]


def test_a_user_over_the_month_s_bound_is_not_heard_and_the_run_says_why(api, ai, monkeypatch):
    SpeechConsent.objects.create(user=api.user)
    recorded = answered(monkeypatch)
    ActionRun.objects.create(user=api.user, action=ACTION, target={}, cost=5)
    installation.bound(api.user, 5)

    response = understand(api)

    assert response.json()["error"] == "limit_reached"
    assert recorded.asked == []
    failed = ActionRun.objects.filter(state=ActionRun.State.FAILED).get()
    assert failed.error == "limit_reached"
