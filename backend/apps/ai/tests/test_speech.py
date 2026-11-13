import httpx2
import pytest
from django.utils import timezone

from apps.ai import speech
from apps.ai.models import Speech, SpeechConsent
from apps.ai.vocabulary import named
from apps.mail.models import Correspondent

pytestmark = pytest.mark.django_db

JSON = "application/json"
KEY = "sk-proj-proba-5678"


@pytest.fixture
def openai(monkeypatch):
    """OpenAI as a transport answering each request with the next of its answers."""
    asked: list[httpx2.Request] = []
    answers: list[httpx2.Response] = []

    def answer(request):
        asked.append(request)
        return answers.pop(0)

    def client(key):
        return httpx2.Client(
            base_url=speech.API,
            headers={"Authorization": f"Bearer {key}"},
            transport=httpx2.MockTransport(answer),
        )

    monkeypatch.setattr(speech, "_client", client)
    return asked, answers


@pytest.fixture
def admin(api):
    api.user.is_staff = True
    api.user.save()
    return api


def turned_on(admin, openai):
    openai[1].append(httpx2.Response(200, json={"id": speech.MODEL}))
    return admin.patch("/api/ai/speech", {"enabled": True, "key": KEY}, content_type=JSON)


def said(api, data=b"\x1aE\xdf\xa3 govor", media_type="audio/webm;codecs=opus"):
    return api.post("/api/speech", data, content_type=media_type)


def test_the_key_is_checked_kept_sealed_and_only_its_end_shown(admin, openai):
    response = turned_on(admin, openai)
    assert response.json() == {
        "enabled": True,
        "hint": "5678",
        "lost": False,
        "changed_at": response.json()["changed_at"],
    }
    asked, _ = openai
    assert asked[0].url.path == f"/v1/models/{speech.MODEL}"
    assert asked[0].headers["Authorization"] == f"Bearer {KEY}"
    assert KEY.encode() not in bytes(Speech.objects.get().key)


def test_a_refused_key_is_not_kept(admin, openai):
    openai[1].append(httpx2.Response(401))
    response = admin.patch("/api/ai/speech", {"enabled": True, "key": KEY}, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (422, "speech_key_refused")
    assert not Speech.objects.exists()


def test_only_an_administrator_sets_it(api):
    assert api.get("/api/ai/speech").status_code == 403


def test_speech_is_written_once_the_user_agreed(admin, openai):
    turned_on(admin, openai)
    assert admin.get("/api/speech/consent").json() == {
        "enabled": True,
        "understands": False,
        "given_at": None,
    }
    assert said(admin).json()["error"] == "speech_consent"

    admin.put("/api/speech/consent")
    assert SpeechConsent.objects.filter(user=admin.user).exists()
    openai[1].append(httpx2.Response(200, json={"text": " Kupiti papir za pisač. "}))
    assert said(admin).json() == {"text": "Kupiti papir za pisač."}

    request = openai[0][-1]
    assert request.url.path == "/v1/audio/transcriptions"
    sent = request.read()
    assert b'name="model"\r\n\r\ngpt-transcribe' in sent
    assert b'name="language"' not in sent
    assert b'filename="speech.webm"\r\nContent-Type: audio/webm' in sent


def test_speech_is_refused_while_it_is_off(api):
    api.put("/api/speech/consent")
    response = said(api)
    assert (response.status_code, response.json()["error"]) == (422, "speech_off")


def test_only_audio_is_sent(admin, openai):
    turned_on(admin, openai)
    admin.put("/api/speech/consent")
    response = said(admin, b"%PDF-1.7", "application/pdf")
    assert (response.status_code, response.json()["error"]) == (400, "invalid_audio")
    assert len(openai[0]) == 1


def test_croatian_written_in_cyrillic_comes_back_in_latin(admin, openai):
    turned_on(admin, openai)
    admin.put("/api/speech/consent")
    openai[1].append(
        httpx2.Response(200, json={"text": "Састанак с Аном у Ђакову, Љубица ће доћи."})
    )
    assert said(admin).json() == {"text": "Sastanak s Anom u Đakovu, Ljubica će doći."}


def test_russian_keeps_its_letters(admin, openai):
    turned_on(admin, openai)
    admin.put("/api/speech/consent")
    openai[1].append(httpx2.Response(200, json={"text": "Купить бумагу и позвонить в сервис."}))
    assert said(admin).json() == {"text": "Купить бумагу и позвонить в сервис."}


def test_the_names_the_user_uses_are_told_beforehand(admin, openai):
    turned_on(admin, openai)
    admin.put("/api/speech/consent")
    for kind, title in [
        ("folder", "Projekti TaskStreamer"),
        ("document", "Ponuda za Končar"),
        ("file", "Snimka ZaslonaX.png"),
    ]:
        admin.post("/api/nodes", {"kind": kind, "title": title}, content_type=JSON)
    now = timezone.now()
    for address, name, written in [
        ("eva@firma.test", "Eva Kovač", 3),
        ("noreply@firma.test", "Obavijesti Sustava", 9),
        ("ana@firma.test", "Ana Kovač", 0),
    ]:
        Correspondent.objects.create(
            owner=admin.user, address=address, name=name, written=written, last=now
        )
    openai[1].append(httpx2.Response(200, json={"text": "Otvori TaskStreamer."}))
    said(admin)
    prompt = openai[0][-1].read().split(b'name="prompt"\r\n\r\n')[1].split(b"\r\n")[0].decode()
    assert prompt == "Names and words the user uses: Eva Kovač, Končar, TaskStreamer."


def test_a_title_gives_only_its_names():
    assert named("Ponuda za Končar i MRO") == ["Končar", "MRO"]
    assert named("TaskStreamer upute") == ["TaskStreamer"]
    assert named("Zapisnik 2026") == []
