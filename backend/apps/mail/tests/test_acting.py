import pytest

from apps.actions.models import ActionRun
from apps.actions.registry import ACTIONS
from apps.ai import installation, model
from apps.ai.tests.recorded import Recorded, message, used
from apps.mail import acting, taking
from apps.mail.models import Account, Folder, Message, Role
from apps.users.models import User

from .test_sorting import mail, numbered, source

pytestmark = pytest.mark.django_db

JSON = "application/json"


@pytest.fixture
def account(client):
    user = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    client.force_login(user)
    return Account.objects.create(owner=user, address="ivo@example.com", username="ivo")


def sorted_as(*moves) -> dict:
    return message(
        "tool_use",
        used("u1", "sorted", {"sorted": [{"message": m, "folder": f} for m, f in moves]}),
        model=acting.TRIAGE_MODEL,
        usage={"input_tokens": 900, "output_tokens": 60},
    )


def test_the_chosen_messages_are_acted_on_by_the_registrys_action(account, client):
    inbox = source(account, "inbox")
    for number in (1, 2):
        taking.took(inbox, mail(number, "promo@shop.test"), {})
    url = f"/api/mail/folders/{inbox.folder.pk}/chosen"
    seen = client.post(url, {"action": "seen", "where": {"messages": [numbered(1)]}}, JSON)
    assert seen.json() == {"changed": 1}
    assert list(Message.objects.order_by("subject").values_list("seen", flat=True)) == [
        True,
        False,
    ]
    for wrong in ("translate", "triage", "rules"):
        refused = client.post(url, {"action": wrong, "where": {}}, JSON)
        assert refused.json() == {"error": "invalid_action"}
    moved = client.post(url, {"action": "move", "to": "nowhere", "where": {}}, JSON)
    assert moved.json() == {"error": "invalid_to"}
    assert client.post(url, {"action": "move", "to": "archive", "where": {}}, JSON).json() == {
        "changed": 2
    }
    assert set(Message.objects.values_list("folder__role", flat=True)) == {Role.ARCHIVE}


def test_every_mail_action_is_one_of_the_registry_on_messages():
    on_messages = {name for name, action in ACTIONS.items() if action.target == "messages"}
    assert {name for name in on_messages if ACTIONS[name].model} == {acting.TRIAGE}
    assert {"mail.move", "mail.block", "mail.always", "mail.delete"} <= on_messages


def test_triage_proposes_where_each_message_goes_once_the_user_lets_it_out(
    account, client, monkeypatch
):
    monkeypatch.setattr(installation, "enabled", lambda: True)
    inbox = source(account, "inbox")
    news = Folder.objects.create(owner=account.owner, name="Novosti")
    for number, sender in enumerate(("promo@shop.test", "ana@example.test", "win@lottery.test"), 1):
        taking.took(inbox, mail(number, sender), {})
    one, two, three = (numbered(each) for each in (1, 2, 3))
    url = "/api/mail/actions/mail.triage"
    given = {"target": {"messages": [one, two, three]}}
    asked = client.post(url, given, JSON)
    assert (asked.status_code, asked.json()) == (428, {"error": "consent_needed"})
    recorded = Recorded(sorted_as((one, str(news.pk)), (one, "junk"), (two, None), (three, "junk")))
    monkeypatch.setattr(model, "answer", recorded)
    answered = client.post(url, given | {"consent": "once"}, JSON).json()
    assert answered["proposals"] == [
        {"message": one, "to": news.pk},
        {"message": three, "to": "junk"},
    ]
    run = ActionRun.objects.get(pk=answered["run"])
    assert (run.action, run.state, run.consent) == (acting.TRIAGE, "done", "once")
    asked_of = str(recorded.asked[0]["messages"])
    assert f"{news.pk}: Novosti" in asked_of and "archive: archive" in asked_of
    assert set(Message.objects.values_list("folder__role", flat=True)) == {Role.INBOX}
    moved = client.post(
        "/api/mail/actions/mail.move",
        {"target": {"messages": [three]}, "parameters": {"to": "junk"}},
        JSON,
    )
    assert moved.json() == {"changed": 1}
