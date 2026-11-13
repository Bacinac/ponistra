from datetime import timedelta

import pytest
from django.utils import timezone

from apps.health import watch
from apps.health.models import Problem
from apps.identity.models import Provider
from apps.jobs.models import Job
from apps.journal.models import Entry
from apps.push import notices
from apps.push.models import Notice
from apps.users.models import User

pytestmark = pytest.mark.django_db

DISK = {"holds": ["files"], "free": 50, "total": 100}


@pytest.fixture
def installation(monkeypatch):
    """An installation whose services, snapshots and disk the test sets, and the notices it
    hands its administrators."""
    state = {
        "services": {"database": True, "converter": True},
        "late": False,
        "archive": {"at": None, "error": "", "late": False},
        "disk": DISK,
    }
    told: list[tuple[list[int], str, dict]] = []
    monkeypatch.setattr(watch.views, "services", lambda: dict(state["services"]))
    monkeypatch.setattr(
        watch.views, "snapshots", lambda: {"late": state["late"], "newest": None, "count": 0}
    )
    monkeypatch.setattr(watch.views, "archive", lambda: state["archive"])
    monkeypatch.setattr(watch.views, "disks", lambda: [state["disk"]])
    monkeypatch.setattr(watch.offsite, "offsite", lambda: None)
    monkeypatch.setattr(
        watch.notices, "tell", lambda users, kind, data: told.append((sorted(users), kind, data))
    )
    state["told"] = told
    return state


def aged(key: str, by: timedelta) -> None:
    Problem.objects.filter(key=key).update(since=timezone.now() - by)


def test_a_silent_service_is_raised_only_after_its_grace(installation):
    admin = User.objects.create_superuser("ivo@example.com", "x")
    User.objects.create_user("ana@example.com", "x")
    installation["services"]["converter"] = False
    watch.checked()
    assert Problem.objects.get().raised_at is None
    assert not Entry.objects.exists() and not installation["told"]
    aged("service:converter", watch.GRACE["service"])
    watch.checked()
    watch.checked()
    entry = Entry.objects.get()
    assert (entry.kind, entry.detail) == (Entry.Kind.PROBLEM, {"problem": "service:converter"})
    assert installation["told"] == [
        ([admin.pk], Notice.Kind.HEALTH, {"problem": "service:converter"})
    ]


def test_a_problem_over_is_written_as_resolved_and_one_never_raised_goes_quietly(installation):
    installation["late"] = True
    installation["services"]["converter"] = False
    watch.checked()
    aged("snapshots", watch.GRACE["snapshots"])
    watch.checked()
    installation["late"] = False
    installation["services"]["converter"] = True
    watch.checked()
    assert list(Entry.objects.order_by("pk").values_list("kind", "detail")) == [
        (Entry.Kind.PROBLEM, {"problem": "snapshots", "error": ""}),
        (Entry.Kind.RESOLVED, {"problem": "snapshots"}),
    ]
    assert not Problem.objects.exists()


def test_archiving_that_stops_or_falls_behind_is_a_problem(installation):
    installation["archive"] = {"at": None, "error": "Postgres cannot archive 0001", "late": True}
    assert watch.found() == {"archive": {"error": "Postgres cannot archive 0001"}}


def test_a_disk_almost_full_is_a_problem(installation):
    installation["disk"] = {"holds": ["files", "snapshots"], "free": 9, "total": 100}
    assert watch.found() == {"disk:files+snapshots": {"free": 9, "total": 100}}


def test_a_queue_stalls_when_work_waits_and_none_finished_within_the_hour(installation):
    user = User.objects.create_user("ana@example.com", "x")
    Job.objects.create(user=user, kind="export")
    assert watch.found() == {"queue:jobs": {}}
    Job.objects.create(
        user=user,
        kind="export",
        state=Job.State.DONE,
        finished_at=timezone.now() - timedelta(minutes=5),
    )
    assert watch.found() == {}


def test_the_health_page_lists_the_problems_raised(installation, client):
    client.force_login(User.objects.create_superuser("ivo@example.com", "x"))
    Problem.objects.create(key="queue:text", since=timezone.now(), raised_at=timezone.now())
    Problem.objects.create(key="service:ocr", since=timezone.now())
    problems = client.get("/api/health").json()["problems"]
    assert [(problem["key"], problem["detail"]) for problem in problems] == [("queue:text", {})]


def test_a_problem_is_worded_for_the_administrators_browser():
    notice = Notice(kind=Notice.Kind.HEALTH, data={"problem": "queue:text"})
    assert notices.worded(notice, "hr", 0) | {"unread": 0} == {
        "kind": "health",
        "title": "Ponistra traži pažnju administratora",
        "body": "Red stoji: čitanje teksta datoteka",
        "url": "/health",
        "tag": "",
        "unread": 0,
    }
    assert (
        notices.worded(Notice(kind=Notice.Kind.HEALTH, data={"problem": "disk:files"}), "en", 0)[
            "body"
        ]
        == "A disk is almost full"
    )


def test_a_user_source_that_cannot_be_read_is_raised_after_its_grace_and_resolved(installation):
    source = Provider.objects.create(name="AD", kind=Provider.Kind.LDAP, error="directory_refused")
    Provider.objects.create(name="Off", kind=Provider.Kind.LDAP, enabled=False, error="x")
    watch.checked()
    assert Problem.objects.get().raised_at is None
    aged("source:AD", watch.GRACE["source"])
    watch.checked()
    source.error = ""
    source.save()
    watch.checked()
    assert list(Entry.objects.order_by("pk").values_list("kind", "detail")) == [
        (Entry.Kind.PROBLEM, {"problem": "source:AD", "error": "directory_refused"}),
        (Entry.Kind.RESOLVED, {"problem": "source:AD"}),
    ]
    notice = Notice(kind=Notice.Kind.HEALTH, data={"problem": "source:AD"})
    assert notices.worded(notice, "hr", 0)["body"] == "Izvor korisnika se ne može pročitati: AD"
