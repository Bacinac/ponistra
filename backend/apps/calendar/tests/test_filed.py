import pytest

from apps.calendar.models import Calendar, Event
from apps.reader.tests.test_shown import EVENTS
from apps.search.tests.test_search import upload_file

JSON = "application/json"


@pytest.mark.django_db
def test_the_events_of_a_calendar_file_come_into_a_calendar_once(api):
    file = upload_file(api, "Raspored", EVENTS)
    mine = api.post("/api/calendar", {"name": "Moj"}, JSON).json()["id"]
    added = api.post(f"/api/nodes/{file}/events", {"calendar": mine}, JSON).json()
    assert added == {"calendar": mine, "made": 2, "changed": 0}
    again = api.post(f"/api/nodes/{file}/events", {"calendar": mine}, JSON).json()
    assert again == {"calendar": mine, "made": 0, "changed": 2}
    weekly = Event.objects.get(calendar_id=mine, uid="1")
    assert (weekly.summary, weekly.location, weekly.rrule) == ("Sastanak", "Zagreb", "FREQ=WEEKLY")
    assert Event.objects.get(calendar_id=mine, uid="2").all_day


@pytest.mark.django_db
def test_a_calendar_file_comes_into_a_new_calendar_of_its_name(api):
    file = upload_file(api, "Raspored", EVENTS)
    added = api.post(f"/api/nodes/{file}/events", {}, JSON).json()
    assert Calendar.objects.get(pk=added["calendar"], owner=api.user).name == "Projekt"
    assert added["made"] == 2
