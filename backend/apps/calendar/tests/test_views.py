import json

import pytest

from apps.calendar import events
from apps.calendar.ical import Found
from apps.calendar.models import Calendar, Event, Feed, Taken
from apps.calendar.tests.test_recurrence import at
from apps.contacts.models import Contact

pytestmark = pytest.mark.django_db


def sent(client, method, where, **data):
    return getattr(client, method)(where, json.dumps(data), content_type="application/json")


def listed(client, first, last, **more):
    query = "&".join(f"{k}={v}" for k, v in {"from": first, "to": last, **more}.items())
    return client.get(f"/api/calendar/events?{query}").json()


def weekly(client, own):
    made = sent(
        client,
        "post",
        "/api/calendar/events",
        calendar=own.pk,
        summary="Sastanak",
        start="2026-11-02T09:00",
        end="2026-11-02T10:00",
        rrule="FREQ=WEEKLY;COUNT=6",
        reminders=[15],
    )
    assert made.status_code == 201
    return made.json()


def test_calendars_are_made_renamed_recoloured_and_deleted(signed_in, owner):
    assert signed_in.get("/api/calendar").json()["next_color"] == 0
    made = sent(signed_in, "post", "/api/calendar", name="Posao", color=2)
    assert made.status_code == 201 and made.json()["color"] == 2
    pk = made.json()["id"]
    assert sent(signed_in, "patch", f"/api/calendar/{pk}", name="Firma").json()["name"] == "Firma"
    assert sent(signed_in, "patch", f"/api/calendar/{pk}", name=" ").status_code == 400
    listed = signed_in.get("/api/calendar").json()
    assert listed["zone"] == "Europe/Zagreb" and listed["next_color"] == 1
    assert signed_in.delete(f"/api/calendar/{pk}").status_code == 204
    assert not Calendar.objects.filter(pk=pk).exists()


def test_an_organisations_calendar_is_only_recoloured(signed_in, owner, account):
    held = Calendar.objects.create(
        owner=owner, kind=Calendar.Kind.ORGANISATION, name="Brezik", account=account
    )
    assert sent(signed_in, "patch", f"/api/calendar/{held.pk}", name="X").status_code == 403
    assert sent(signed_in, "patch", f"/api/calendar/{held.pk}", color=4).json()["color"] == 4
    assert signed_in.delete(f"/api/calendar/{held.pk}").status_code == 403
    event = events.made(
        held, Found(summary="Kolegij", starts=at("2026-11-02T08:00Z"), ends=at("2026-11-02T09:00Z"))
    )
    assert (
        sent(signed_in, "patch", f"/api/calendar/events/{event.pk}", summary="X").status_code == 403
    )
    shown = listed(signed_in, "2026-11-01", "2026-11-30")["events"]
    assert [each["summary"] for each in shown] == ["Kolegij"]


def test_the_series_is_expanded_here_with_holidays_and_birthdays(signed_in, owner, own):
    made = weekly(signed_in, own)
    assert made["start"] == "2026-11-02T09:00:00+01:00" and made["zone"] == "Europe/Zagreb"
    Contact.objects.create(owner=owner, given="Ana", family="Horvat", birthday="1974-11-18")
    shown = listed(signed_in, "2026-11-01", "2026-12-31")
    assert [each["start"][:16] for each in shown["events"]] == [
        "2026-11-02T09:00",
        "2026-11-09T09:00",
        "2026-11-16T09:00",
        "2026-11-23T09:00",
        "2026-11-30T09:00",
        "2026-12-07T09:00",
    ]
    assert (
        shown["events"][0]["recurring"] and shown["events"][0]["end"] == "2026-11-02T10:00:00+01:00"
    )
    assert [each["date"] for each in shown["holidays"]] == [
        "2026-11-01",
        "2026-11-18",
        "2026-12-25",
        "2026-12-26",
    ]
    assert shown["days_off"][:4] == ["2026-11-01", "2026-11-07", "2026-11-08", "2026-11-14"]
    assert "2026-11-18" in shown["days_off"] and "2026-11-17" not in shown["days_off"]
    assert shown["birthdays"] == [
        {"date": "2026-11-18", "contact": Contact.objects.get().pk, "name": "Ana Horvat", "age": 52}
    ]
    assert listed(signed_in, "2026-11-01", "2026-12-31", calendars="0")["events"] == []
    assert signed_in.get("/api/calendar/events?from=2026-11-01&to=2025-01-01").status_code == 400


def test_one_occurrence_changed_or_removed_leaves_the_series_whole(signed_in, own):
    pk = weekly(signed_in, own)["id"]
    moved = sent(
        signed_in,
        "patch",
        f"/api/calendar/events/{pk}?scope=this",
        recurrence_id="2026-11-09T09:00:00+01:00",
        start="2026-11-09T14:00",
        end="2026-11-09T15:00",
        summary="Pomaknut",
    )
    assert moved.status_code == 200 and moved.json()["master"] == pk
    gone = signed_in.delete(
        f"/api/calendar/events/{pk}?scope=this&recurrence_id=2026-11-16T09:00:00%2B01:00"
    )
    assert gone.status_code == 204
    shown = listed(signed_in, "2026-11-01", "2026-12-31")["events"]
    assert [(each["start"][:16], each["summary"], each["moved"]) for each in shown] == [
        ("2026-11-02T09:00", "Sastanak", False),
        ("2026-11-09T14:00", "Pomaknut", True),
        ("2026-11-23T09:00", "Sastanak", False),
        ("2026-11-30T09:00", "Sastanak", False),
        ("2026-12-07T09:00", "Sastanak", False),
    ]
    # The moved one is changed again by its own row; deleting it puts the series' one back.
    override = moved.json()["id"]
    assert (
        sent(signed_in, "patch", f"/api/calendar/events/{override}", summary="Opet").status_code
        == 200
    )
    assert signed_in.delete(f"/api/calendar/events/{override}").status_code == 204
    shown = listed(signed_in, "2026-11-08", "2026-11-10")["events"]
    assert [(each["start"][:16], each["summary"]) for each in shown] == [
        ("2026-11-09T09:00", "Sastanak")
    ]


@pytest.mark.parametrize("rule", [{}, {"rrule": "FREQ=WEEKLY;COUNT=6"}])
def test_this_and_following_cuts_the_series_and_the_rest_goes_on_anew(signed_in, own, rule):
    pk = weekly(signed_in, own)["id"]
    sent(
        signed_in,
        "patch",
        f"/api/calendar/events/{pk}?scope=this",
        recurrence_id="2026-12-07T09:00:00+01:00",
        summary="Zadnji",
    )
    rest = sent(
        signed_in,
        "patch",
        f"/api/calendar/events/{pk}?scope=following",
        recurrence_id="2026-11-30T09:00:00+01:00",
        start="2026-11-30T11:00",
        end="2026-11-30T12:00",
        summary="Novi termin",
        **rule,
    )
    assert rest.status_code == 200
    assert rest.json()["rrule"] == "FREQ=WEEKLY;COUNT=2"
    assert Event.objects.get(pk=pk).rrule == "FREQ=WEEKLY;UNTIL=20261130T075959Z"
    shown = listed(signed_in, "2026-11-01", "2026-12-31")["events"]
    assert [(each["start"][:16], each["summary"]) for each in shown] == [
        ("2026-11-02T09:00", "Sastanak"),
        ("2026-11-09T09:00", "Sastanak"),
        ("2026-11-16T09:00", "Sastanak"),
        ("2026-11-23T09:00", "Sastanak"),
        ("2026-11-30T11:00", "Novi termin"),
        ("2026-12-07T11:00", "Zadnji"),
    ]
    assert Event.objects.get(summary="Zadnji").master_id == rest.json()["id"]
    gone = signed_in.delete(
        f"/api/calendar/events/{rest.json()['id']}?scope=following&recurrence_id=2026-12-07T11:00:00%2B01:00"
    )
    assert gone.status_code == 204
    shown = listed(signed_in, "2026-12-01", "2026-12-31")["events"]
    assert shown == []


def test_the_whole_series_moved_takes_its_exceptions_along(signed_in, own):
    pk = weekly(signed_in, own)["id"]
    sent(
        signed_in,
        "patch",
        f"/api/calendar/events/{pk}?scope=this",
        recurrence_id="2026-11-09T09:00:00+01:00",
        summary="Poseban",
    )
    signed_in.delete(
        f"/api/calendar/events/{pk}?scope=this&recurrence_id=2026-11-16T09:00:00%2B01:00"
    )
    moved = sent(
        signed_in,
        "patch",
        f"/api/calendar/events/{pk}?scope=all",
        recurrence_id="2026-11-23T09:00:00+01:00",
        start="2026-11-24T08:30",
        end="2026-11-24T09:30",
    )
    assert moved.status_code == 200 and moved.json()["start"] == "2026-11-03T08:30:00+01:00"
    shown = listed(signed_in, "2026-11-01", "2026-12-31")["events"]
    assert [(each["start"][:16], each["summary"]) for each in shown] == [
        ("2026-11-03T08:30", "Sastanak"),
        ("2026-11-10T08:30", "Poseban"),
        ("2026-11-24T08:30", "Sastanak"),
        ("2026-12-01T08:30", "Sastanak"),
        ("2026-12-08T08:30", "Sastanak"),
    ]


def test_an_all_day_event_is_given_by_its_days_and_moved_between_calendars(signed_in, owner, own):
    made = sent(
        signed_in,
        "post",
        "/api/calendar/events",
        calendar=own.pk,
        summary="Godišnji",
        all_day=True,
        start="2026-12-21",
        end="2026-12-23",
    )
    assert made.status_code == 201
    assert (made.json()["start"], made.json()["end"]) == ("2026-12-21", "2026-12-23")
    assert Event.objects.get().ends == at("2026-12-24T00:00Z")
    other = sent(signed_in, "post", "/api/calendar", name="Drugi").json()["id"]
    moved = sent(signed_in, "patch", f"/api/calendar/events/{made.json()['id']}", calendar=other)
    assert moved.status_code == 200 and moved.json()["calendar"] == other
    shown = listed(signed_in, "2026-12-20", "2026-12-25")["events"]
    assert [(each["start"], each["end"], each["calendar"]) for each in shown] == [
        ("2026-12-21", "2026-12-23", other)
    ]
    assert (
        sent(
            signed_in,
            "post",
            "/api/calendar/events",
            calendar=own.pk,
            summary="x",
            start="2026-12-21T10:00",
            end="2026-12-21T09:00",
        ).status_code
        == 400
    )
    assert (
        sent(
            signed_in,
            "post",
            "/api/calendar/events",
            calendar=own.pk,
            summary="x",
            start="2026-12-21T10:00",
            end="2026-12-21T11:00",
            rrule="FREQ=NEVER",
        ).status_code
        == 400
    )


def test_the_window_is_read_on_the_users_clock(signed_in, own):
    events.made(
        own,
        Found(
            summary="Kasno", starts=at("2026-11-01T23:30+01:00"), ends=at("2026-11-02T00:30+01:00")
        ),
    )
    assert listed(signed_in, "2026-11-01", "2026-11-01")["events"][0]["summary"] == "Kasno"
    assert listed(signed_in, "2026-11-01", "2026-11-01", zone="Asia/Tokyo")["events"] == []


def test_a_calendar_is_listed_by_the_word_for_its_mailbox(signed_in, owner, account):
    kept = Calendar.objects.create(owner=owner, name="Ana Anić - My Calendar", account=account)
    primary = Calendar.objects.create(owner=owner, name="ana@example.com")
    Feed.objects.create(account=account, calendar=primary, server_id="1")
    shown = {each["id"]: each for each in signed_in.get("/api/calendar").json()["calendars"]}
    assert shown[kept.pk]["name"] == "Ana Anić - My Calendar"
    assert shown[kept.pk]["account"] == "Example"
    assert shown[primary.pk] | {"id": 0} == {
        "id": 0,
        "name": "Example",
        "color": primary.color,
        "kind": "own",
        "read_only": False,
        "account": "Example",
    }
    account.label = "Posao"
    account.save(update_fields=["label"])
    shown = {each["id"]: each for each in signed_in.get("/api/calendar").json()["calendars"]}
    assert [shown[each.pk]["name"] for each in (kept, primary)] == [kept.name, "Posao"]


def test_a_calendar_of_an_account_is_dropped_by_unfollowing_its_feed(signed_in, owner, account):
    fed = Calendar.objects.create(owner=owner, name="Family")
    feed = Feed.objects.create(account=account, calendar=fed, server_id="family", name="Family")
    event = events.made(
        fed, Found(summary="Rođendan", starts=at("2026-11-02T08:00Z"), ends=at("2026-11-02T09:00Z"))
    )
    Taken.objects.create(
        owner=owner, account=account, kind="google", source="x", item="a.ics", feed=feed
    )
    Taken.objects.create(owner=owner, account=account, kind="google", source="x", item="b.ics")
    assert signed_in.delete(f"/api/calendar/{fed.pk}").status_code == 204
    feed.refresh_from_db()
    assert (feed.calendar_id, feed.followed, feed.key) == (None, False, "")
    assert not Event.objects.filter(pk=event.pk).exists()
    assert list(Taken.objects.values_list("item", flat=True)) == ["b.ics"]
    listed_now = signed_in.get("/api/calendar").json()
    assert listed_now["unfollowed"] == [{"id": feed.pk, "name": "Family", "account": "Example"}]
    assert signed_in.post(f"/api/calendar/feeds/{feed.pk}").status_code == 201
    feed.refresh_from_db()
    assert feed.followed and feed.calendar.name == "Family"
    assert signed_in.get("/api/calendar").json()["unfollowed"] == []
    assert signed_in.post("/api/calendar/feeds/999").status_code == 404


def test_a_series_says_what_it_does_on_days_off(signed_in, own):
    made = sent(
        signed_in,
        "post",
        "/api/calendar/events",
        calendar=own.pk,
        summary="Kolegij",
        start="2026-01-01T09:00",
        end="2026-01-01T10:00",
        rrule="FREQ=MONTHLY;COUNT=6",
        day_off="after",
    )
    assert made.status_code == 201 and made.json()["day_off"] == "after"
    shown = listed(signed_in, "2026-04-01", "2026-05-31")["events"]
    assert [each["start"][:10] for each in shown] == ["2026-04-01", "2026-05-04"]
    assert [each["recurrence_id"][:10] for each in shown] == ["2026-04-01", "2026-05-01"]
    pk = made.json()["id"]
    refused = sent(signed_in, "patch", f"/api/calendar/events/{pk}?scope=all", day_off="sunday")
    assert refused.status_code == 400 and refused.json()["error"] == "invalid_day_off"
    skipped = sent(signed_in, "patch", f"/api/calendar/events/{pk}?scope=all", day_off="skip")
    assert skipped.json()["day_off"] == "skip"
    shown = listed(signed_in, "2026-04-01", "2026-05-31")["events"]
    assert [each["start"][:10] for each in shown] == ["2026-04-01"]


def test_a_series_moved_from_an_occurrence_days_off_moved_moves_by_what_the_user_changed(
    signed_in, own
):
    pk = sent(
        signed_in,
        "post",
        "/api/calendar/events",
        calendar=own.pk,
        summary="Kolegij",
        start="2026-01-01T09:00",
        end="2026-01-01T10:00",
        rrule="FREQ=MONTHLY;COUNT=6",
        day_off="after",
    ).json()["id"]
    moved = sent(
        signed_in,
        "patch",
        f"/api/calendar/events/{pk}?scope=all",
        recurrence_id="2026-05-01T09:00:00+02:00",
        start="2026-05-04T10:00",
        end="2026-05-04T11:00",
    )
    assert moved.status_code == 200
    shown = listed(signed_in, "2026-04-01", "2026-05-31")["events"]
    assert [each["start"][:16] for each in shown] == ["2026-04-01T10:00", "2026-05-04T10:00"]
    rest = sent(
        signed_in,
        "patch",
        f"/api/calendar/events/{pk}?scope=following",
        recurrence_id="2026-05-01T10:00:00+02:00",
        summary="Novi kolegij",
    )
    assert rest.status_code == 200 and rest.json()["start"][:16] == "2026-05-01T10:00"
    shown = listed(signed_in, "2026-04-01", "2026-06-30")["events"]
    assert [(each["start"][:10], each["summary"]) for each in shown] == [
        ("2026-04-01", "Kolegij"),
        ("2026-05-04", "Novi kolegij"),
        ("2026-06-01", "Novi kolegij"),
    ]
