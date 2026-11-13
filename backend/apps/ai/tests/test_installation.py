from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from django.test import Client
from django.utils import timezone

from apps.access.models import Role
from apps.actions.models import ActionRun
from apps.ai import installation
from apps.ai.installation import Unavailable
from apps.ai.models import Consent, Setting
from apps.documents.models import Node
from apps.users.models import User

JSON = "application/json"
KEY = "sk-ant-api03-proba-1234"


@pytest.fixture
def checked(monkeypatch):
    found = []
    monkeypatch.setattr(installation, "check", found.append)
    return found


@pytest.fixture
def admin(api):
    api.user.is_staff = True
    api.user.save()
    return api


@pytest.mark.django_db
def test_the_key_is_kept_sealed_and_only_its_last_characters_shown(checked):
    user = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    found = installation.change(user, True, KEY)
    assert checked == [KEY]
    stored = Setting.objects.get()
    assert KEY.encode() not in bytes(stored.key) and stored.hint == "1234"
    assert installation.opened(stored) == KEY and installation.enabled()
    described = installation.describe(found)
    assert {**described, "changed_at": None} == {
        "enabled": True,
        "hint": "1234",
        "lost": False,
        "changed_at": None,
        "monthly": None,
    }
    assert installation.client().api_key == KEY
    installation.change(user, False, None)
    assert checked == [KEY] and not installation.enabled()
    with pytest.raises(Unavailable) as off:
        installation.client()
    assert off.value.code == "ai_off"


@pytest.mark.django_db
def test_a_key_the_installation_s_secret_no_longer_opens_is_asked_for_again(checked, settings):
    user = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    with pytest.raises(Unavailable) as needed:
        installation.change(user, True, None)
    assert needed.value.code == "key_needed"
    installation.change(user, True, KEY)
    settings.SECRET_KEY = "a-new-secret-for-the-installation"
    found = installation.setting()
    assert installation.describe(found)["lost"] and not installation.enabled()
    with pytest.raises(Unavailable) as lost:
        installation.client()
    assert lost.value.code == "key_lost"
    with pytest.raises(Unavailable) as needed:
        installation.change(user, True, None)
    assert needed.value.code == "key_needed"


def test_a_key_is_checked_with_anthropic_before_it_is_kept(monkeypatch):
    request = httpx2.Request("GET", "https://api.anthropic.com/v1/models/claude-haiku-5-5")
    refused = httpx2.Response(401, request=request)
    for error, code in [
        (anthropic.AuthenticationError("no", response=refused, body=None), "key_refused"),
        (anthropic.APIConnectionError(request=request), "ai_unreachable"),
    ]:

        def retrieve(model: str, error=error):
            raise error

        def made(**given):
            assert given["api_key"] == KEY
            return SimpleNamespace(models=SimpleNamespace(retrieve=retrieve))

        monkeypatch.setattr(installation.anthropic, "Anthropic", made)
        with pytest.raises(Unavailable) as failed:
            installation.check(KEY)
        assert failed.value.code == code


@pytest.mark.django_db
def test_only_an_administrator_sees_or_changes_the_installation_s_ai(api, checked):
    assert api.get("/api/ai").status_code == 403
    assert api.patch("/api/ai", {"enabled": True}, content_type=JSON).status_code == 403
    api.user.is_staff = True
    api.user.save()
    assert api.get("/api/ai").json()["enabled"] is False
    response = api.patch("/api/ai", {"enabled": True}, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (422, "key_needed")
    for wrong in [{"enabled": "da"}, {"enabled": True, "key": " "}, {"enabled": True, "key": 7}]:
        assert api.patch("/api/ai", wrong, content_type=JSON).status_code == 400
    response = api.patch("/api/ai", {"enabled": True, "key": f" {KEY} "}, content_type=JSON)
    assert response.status_code == 200 and KEY.encode() not in response.content
    assert response.json()["hint"] == "1234" and checked == [KEY]
    assert api.get("/api/actions").json()["ai"] is True


@pytest.mark.django_db
def test_a_refused_key_is_not_kept(admin, monkeypatch):
    def check(key: str):
        raise Unavailable("key_refused")

    monkeypatch.setattr(installation, "check", check)
    response = admin.patch("/api/ai", {"enabled": True, "key": KEY}, content_type=JSON)
    assert (response.status_code, response.json()["error"]) == (422, "key_refused")
    assert not Setting.objects.exists()


@pytest.mark.django_db
def test_an_editor_lets_a_document_s_ai_actions_run_without_asking_and_withdraws_it(api):
    created = api.post("/api/nodes", {"kind": "document", "title": "Ugovor"}, content_type=JSON)
    url = f"/api/nodes/{created.json()['id']}/ai"
    assert api.get(url).json() == {"consent": None}
    given = api.post(url).json()["consent"]
    assert given["given_by"]["email"] == "ivo@example.com" and given["given_at"]
    assert api.post(url).json()["consent"]["given_at"] == given["given_at"]
    reader = User.objects.create_user("ana@example.com", "Kamen-Most-Rijeka-72")
    document = Node.objects.get(pk=created.json()["id"])
    document.grants.create(user=reader, role=Role.READ)
    client = Client()
    client.force_login(reader)
    assert client.get(url).json()["consent"]["given_at"] == given["given_at"]
    assert client.delete(url).status_code == 403
    assert api.delete(url).json() == {"consent": None}
    assert not Consent.objects.exists()


@pytest.mark.django_db
def test_a_user_s_runs_stop_at_what_a_month_allows_them_where_the_administrator_bounds_it(admin):
    for wrong in [{"monthly": -1}, {"monthly": "10"}, {"monthly": True}, {"monthly": 10**8}]:
        assert admin.patch("/api/ai", wrong, content_type=JSON).status_code == 400
    other = User.objects.create_user("eva@example.com", "Kamen-Most-Rijeka-72")
    now = timezone.now()
    last_month = timezone.localtime().replace(day=1) - timedelta(days=1)
    for user, cost, at in [
        (admin.user, Decimal("6.5"), now),
        (admin.user, Decimal("4"), now),
        (admin.user, None, now),
        (admin.user, Decimal("90"), last_month),
        (other, Decimal("50"), now),
    ]:
        run = ActionRun.objects.create(user=user, action="text.ask", target={}, cost=cost)
        ActionRun.objects.filter(pk=run.pk).update(started_at=at)
    assert installation.spent(admin.user.pk) == Decimal("10.5")
    installation.allowed(admin.user.pk)

    response = admin.patch("/api/ai", {"monthly": 10.5}, content_type=JSON)

    assert (response.status_code, response.json()["monthly"]) == (200, 10.5)
    assert admin.get("/api/ai").json()["monthly"] == 10.5
    for user in (admin.user, other):
        with pytest.raises(Unavailable) as failed:
            installation.allowed(user.pk)
        assert failed.value.code == "limit_reached"
    assert admin.patch("/api/ai", {"monthly": None}, content_type=JSON).json()["monthly"] is None
    installation.allowed(other.pk)
