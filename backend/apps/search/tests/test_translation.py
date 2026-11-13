from decimal import Decimal

import pytest

from apps.actions.models import ActionRun
from apps.ai import installation, model
from apps.ai.tests.recorded import Recorded, message, said, used
from apps.search.translation import ACTION, MODEL

pytestmark = pytest.mark.django_db

JSON = "application/json"
ASKED = "ponude koje mi je Ana poslala prošli mjesec s privitkom"
FILTERS = {
    "text": "ponude",
    "kind": "mail",
    "from": "Ana",
    "since": "2026-09-01",
    "until": "2026-09-30",
    "attachment": True,
}


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(installation, "enabled", lambda: True)


def answered(monkeypatch, *answers) -> Recorded:
    recorded = Recorded(*answers)
    monkeypatch.setattr(model, "answer", recorded)
    return recorded


def translate(client, sentence=ASKED, **fields):
    return client.post("/api/search/translate", {"sentence": sentence, **fields}, content_type=JSON)


def chosen(**filters):
    return message(
        "tool_use",
        used("u1", "filters", filters),
        model=MODEL,
        usage={"input_tokens": 900, "output_tokens": 60},
    )


def test_a_sentence_becomes_words_and_filters_once_the_user_lets_it_out(api, ai, monkeypatch):
    recorded = answered(monkeypatch, chosen(**FILTERS))
    response = translate(api)
    assert (response.status_code, response.json()["error"]) == (428, "consent_needed")
    assert recorded.asked == []

    response = translate(api, consent="once")
    assert response.status_code == 200, response.json()
    assert response.json() == {"translated": FILTERS}
    (request,) = recorded.asked
    assert (request["model"], request["output_config"]) == (MODEL, {"effort": "low"})
    assert request["messages"][0]["content"].endswith(f"\n\n{ASKED}")
    assert request["messages"][0]["content"].startswith("Today is ")
    run = ActionRun.objects.get()
    assert (run.document, run.action, run.state, run.user) == (None, ACTION, "done", api.user)
    assert (run.consent, run.consented_by, run.parameters) == ("once", api.user, {})
    assert (run.model, run.input_tokens, run.output_tokens) == (MODEL, 900, 60)
    assert run.cost > Decimal(0)
    assert api.get(f"/api/runs/{run.pk}").status_code == 404


def test_a_user_answers_once_for_all_of_their_searches(api, ai, monkeypatch):
    answered(monkeypatch, chosen(text="ugovor"))
    response = api.get("/api/search/ai")
    assert response.json() == {"translate": None}
    response = api.put("/api/search/ai", {"translate": False}, content_type=JSON)
    assert response.json() == {"translate": False}
    assert translate(api).status_code == 428

    response = api.put("/api/search/ai", {"translate": True}, content_type=JSON)
    assert response.json() == {"translate": True}
    response = translate(api, "ugovor za Rijeku")
    assert response.json() == {"translated": {"text": "ugovor"}}
    assert ActionRun.objects.get().consent == "user"

    assert api.delete("/api/search/ai").json() == {"translate": None}
    assert translate(api).status_code == 428


def test_a_wrong_answer_goes_back_to_the_model_to_put_right(api, ai, monkeypatch):
    recorded = answered(monkeypatch, chosen(text="ponude", kind="e-mail"), chosen(**FILTERS))
    response = translate(api, consent="once")
    assert response.json() == {"translated": FILTERS}
    assert len(recorded.asked) == 2


@pytest.mark.parametrize(
    "answer, code",
    [
        (model.Failed("rate_limited"), "rate_limited"),
        (message("end_turn", said("Ne razumijem."), model=MODEL), "no_answer"),
    ],
)
def test_a_sentence_the_model_does_not_translate_fails_loudly(api, ai, monkeypatch, answer, code):
    answered(monkeypatch, answer)
    response = translate(api, consent="once")
    assert (response.status_code, response.json()["error"]) == (502, code)
    run = ActionRun.objects.get()
    assert (run.state, run.error) == ("failed", code)


def test_with_the_ai_off_nothing_goes_out(api, monkeypatch):
    recorded = answered(monkeypatch)
    response = translate(api, consent="once")
    assert (response.status_code, response.json()["error"]) == (409, "ai_off")
    assert recorded.asked == [] and not ActionRun.objects.exists()


@pytest.mark.parametrize(
    "fields, code",
    [
        ({"sentence": " "}, "invalid_sentence"),
        ({"sentence": 3}, "invalid_sentence"),
        ({"sentence": "x" * 201}, "query_too_long"),
        ({"sentence": "ugovor", "consent": "always"}, "invalid_consent"),
    ],
)
def test_what_it_cannot_take_is_refused(api, ai, fields, code):
    response = api.post("/api/search/translate", fields, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (400, code)


def test_a_consent_is_a_yes_or_a_no(api):
    response = api.put("/api/search/ai", {"translate": "da"}, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (400, "invalid_translate")


def test_the_usage_counts_the_translations(api, ai, monkeypatch):
    answered(monkeypatch, chosen(**FILTERS))
    translate(api, consent="once")
    api.user.is_staff = True
    api.user.save()
    response = api.get("/api/runs/usage")
    assert [(row["action"], row["runs"]) for row in response.json()["spent"]] == [(ACTION, 1)]
