import json
import uuid
from urllib.parse import quote

import pytest
from anyio import create_task_group
from django.test import Client

from apps.chat import conversations
from apps.chat.models import Conversation, Member, Message
from apps.collab import live
from apps.core.asyncdb import database
from apps.meetings.models import Meeting, Ring
from apps.meetings.tests.test_rings import Tab, colleague_cookie
from apps.users.models import User

pytestmark = pytest.mark.django_db


def person(email: str, first: str, last: str) -> User:
    return User.objects.create_user(email, "Kamen-Most-Rijeka-71", first_name=first, last_name=last)


def signed(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def posted(client, path: str, **data):
    return client.post(path, json.dumps(data), content_type="application/json")


def written(client, conversation, text: str):
    return posted(client, f"/api/conversations/{conversation}/messages", body=text)


def test_a_meeting_brings_its_organizer_those_who_join_and_those_rung_into_its_conversation(
    owner, ana, monkeypatch
):
    mine = signed(owner)
    made = posted(mine, "/api/meetings", title="Dogovor").json()
    conversation = made["conversation"]
    shown = mine.get(f"/api/conversations/{conversation}").json()
    assert shown == {
        "id": conversation,
        "kind": "meeting",
        "title": "Dogovor",
        "private": False,
        "people": ["Ivo Bošković"],
        "joined": True,
        "removable": False,
        "meeting": made["id"],
    }
    theirs = signed(ana)
    outside = theirs.get(f"/api/conversations/{conversation}")
    assert (outside.status_code, outside.json()) == (200, None)
    assert written(theirs, conversation, "Ja sam tu").status_code == 404

    theirs.post(f"/api/meetings/{made['id']}/join")
    assert theirs.get(f"/api/conversations/{conversation}").json()["people"] == [
        "Ana Kovač",
        "Ivo Bošković",
    ]

    marko = person("marko@example.com", "Marko", "Horvat")
    asked = posted(
        mine,
        f"/api/meetings/{made['id']}/invite",
        people=[{"name": "", "address": "marko@example.com"}],
        language="hr",
    )
    assert asked.json()["rung"] == ["Marko Horvat"]
    assert Member.objects.filter(conversation_id=conversation, user=marko).exists()


def test_messages_are_written_counted_unread_and_read_up_to_the_last_one(owner, ana):
    meeting = Meeting.objects.made("Kolegij", owner)
    conversations.added(meeting.conversation, [ana])
    mine, theirs = signed(owner), signed(ana)
    first = written(mine, meeting.conversation_id, "  Dobro jutro\nkolege  ")
    assert first.status_code == 201
    assert first.json() | {"at": None} == {
        "id": first.json()["id"],
        "by": "Ivo Bošković",
        "guest": False,
        "mine": True,
        "text": "Dobro jutro\nkolege",
        "at": None,
        "edited": False,
        "meeting": None,
        "kept": None,
        "files": [],
        "items": [],
        "reactions": [],
        "mentions": [],
        "everyone": False,
        "thread": {"replies": 0, "unread": 0},
    }
    written(mine, meeting.conversation_id, "Počinjemo u 9")

    (row,) = conversations.summaries(ana.pk)
    assert (row["title"], row["people"], row["unread"]) == ("Kolegij", ["Ivo Bošković"], 2)
    assert (row["last"]["by"], row["last"]["text"]) == ("Ivo Bošković", "Počinjemo u 9")
    assert conversations.summaries(owner.pk)[0]["unread"] == 0

    listed = theirs.get(f"/api/conversations/{meeting.conversation_id}/messages").json()
    assert [(each["text"], each["mine"]) for each in listed["messages"]] == [
        ("Dobro jutro\nkolege", False),
        ("Počinjemo u 9", False),
    ]
    assert listed["more"] is False

    read = f"/api/conversations/{meeting.conversation_id}/read"
    assert posted(theirs, read, message=first.json()["id"]).status_code == 204
    assert conversations.summaries(ana.pk)[0]["unread"] == 1
    posted(theirs, read, message=first.json()["id"] + 10_000)
    assert conversations.summaries(ana.pk)[0]["unread"] == 0
    posted(theirs, read, message=first.json()["id"])
    assert conversations.summaries(ana.pk)[0]["unread"] == 0

    answered = written(theirs, meeting.conversation_id, "Stižem")
    assert answered.json()["mine"] is True
    assert conversations.summaries(owner.pk)[0]["unread"] == 1
    assert conversations.summaries(ana.pk)[0]["unread"] == 0


def test_a_conversation_lists_its_messages_a_page_at_a_time_and_refuses_what_is_not_a_message(
    owner,
):
    meeting = Meeting.objects.made("Kolegij", owner)
    Message.objects.bulk_create(
        Message(conversation=meeting.conversation, author=owner, body=f"Poruka {each}")
        for each in range(55)
    )
    mine = signed(owner)
    path = f"/api/conversations/{meeting.conversation_id}/messages"
    latest = mine.get(path).json()
    assert len(latest["messages"]) == 50
    assert (latest["messages"][0]["text"], latest["messages"][-1]["text"]) == (
        "Poruka 5",
        "Poruka 54",
    )
    assert latest["more"] is True
    earlier = mine.get(f"{path}?before={latest['messages'][0]['id']}").json()
    assert [each["text"] for each in earlier["messages"]] == [f"Poruka {each}" for each in range(5)]
    assert earlier["more"] is False

    assert mine.get(f"{path}?before=x").json() == {"error": "invalid_before"}
    assert written(mine, meeting.conversation_id, "   ").json() == {"error": "invalid_body"}
    assert written(mine, meeting.conversation_id, "a" * 10_001).json() == {"error": "invalid_body"}
    refused = posted(mine, f"/api/conversations/{meeting.conversation_id}/read", message="5")
    assert refused.json() == {"error": "invalid_message"}


def test_only_conversations_written_to_are_listed_the_latest_first(owner, ana):
    older = Meeting.objects.made("Prvi", owner)
    newer = Meeting.objects.made("", owner)
    conversations.added(newer.conversation, [ana])
    assert conversations.summaries(owner.pk) == []
    mine = signed(owner)
    written(mine, newer.conversation_id, "Javljam se")
    written(mine, older.conversation_id, "I ovdje")
    listed = conversations.summaries(owner.pk)
    assert [(each["title"], each["people"]) for each in listed] == [
        ("Prvi", []),
        ("", ["Ana Kovač"]),
    ]


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_message_reaches_every_open_tab_of_the_conversations_people():
    cookie, owner, ana = await colleague_cookie()
    meeting = await database(Meeting.objects.made)("Sastanak", owner)
    await database(conversations.added)(meeting.conversation, [ana])
    member = await Member.objects.aget(conversation=meeting.conversation, user=owner)
    async with create_task_group() as tg:
        tg.start_soon(live.listen)
        tabs = [Tab(cookie, tg), Tab(cookie, tg)]
        for each in tabs:
            assert (await each.state())["conversations"] == []
        await database(conversations.written)(member, "Dobar dan")
        for each in tabs:
            (row,) = (await each.state())["conversations"]
            shown = (row["title"], row["unread"], row["last"]["text"])
            assert shown == ("Sastanak", 1, "Dobar dan")
            await each.leave()
        tg.cancel_scope.cancel()
    assert live._sockets == {}


def test_two_people_have_one_conversation_started_once_and_a_group_takes_more(owner, ana):
    mine, theirs = signed(owner), signed(ana)
    marko = person("marko@example.com", "Marko", "Horvat")
    started = posted(mine, "/api/conversations", people=[{"address": "ANA@example.com"}])
    assert started.status_code == 201
    direct = started.json()
    assert (direct["kind"], direct["title"], direct["people"]) == (
        "direct",
        "",
        ["Ana Kovač", "Ivo Bošković"],
    )
    again = posted(theirs, "/api/conversations", people=[{"address": "ivo@example.com"}])
    assert (again.status_code, again.json()["id"]) == (200, direct["id"])

    (row,) = conversations.summaries(ana.pk)
    assert (row["kind"], row["people"], row["last"], row["unread"]) == (
        "direct",
        ["Ivo Bošković"],
        None,
        0,
    )
    written(mine, direct["id"], "Bok")
    assert conversations.summaries(ana.pk)[0]["unread"] == 1

    refused = posted(mine, "/api/conversations", people=[{"address": "nobody@example.com"}])
    assert (refused.status_code, refused.json()) == (400, {"error": "no_colleague"})
    assert posted(mine, "/api/conversations", people=[]).json() == {"error": "invalid_recipient"}
    assert posted(mine, f"/api/conversations/{direct['id']}/members", people=[]).json() == {
        "error": "not_group"
    }
    assert mine.delete(f"/api/conversations/{direct['id']}/members").status_code == 400
    assert mine.patch(f"/api/conversations/{direct['id']}", "{}").status_code == 400

    group = posted(
        mine,
        "/api/conversations",
        people=[{"address": "ana@example.com"}, {"address": "marko@example.com"}],
        title="  Projekt   X ",
    ).json()
    assert (group["kind"], group["title"], len(group["people"])) == ("group", "Projekt X", 3)
    assert [each["id"] for each in conversations.summaries(owner.pk)] == [direct["id"], group["id"]]

    renamed = mine.patch(
        f"/api/conversations/{group['id']}", json.dumps({"title": "Projekt Y"}), "application/json"
    )
    assert renamed.json()["title"] == "Projekt Y"
    dora = person("dora@example.com", "Dora", "Novak")
    brought = posted(
        mine, f"/api/conversations/{group['id']}/members", people=[{"address": "dora@example.com"}]
    )
    assert "Dora Novak" in brought.json()["people"]
    assert signed(dora).get(f"/api/conversations/{group['id']}").status_code == 200

    assert theirs.delete(f"/api/conversations/{group['id']}/members").status_code == 204
    assert theirs.get(f"/api/conversations/{group['id']}").json() is None
    assert Member.objects.filter(conversation_id=group["id"]).count() == 3
    for each in (mine, signed(marko), signed(dora)):
        assert each.delete(f"/api/conversations/{group['id']}/members").status_code == 204
    assert not Conversation.objects.filter(pk=group["id"]).exists()


def test_ones_own_message_is_edited_or_taken_back_and_nobody_elses(owner, ana):
    mine, theirs = signed(owner), signed(ana)
    direct = posted(mine, "/api/conversations", people=[{"address": "ana@example.com"}]).json()
    said = written(mine, direct["id"], "Dolazim u 8").json()
    path = f"/api/conversations/{direct['id']}/messages/{said['id']}"
    before = Conversation.objects.get(pk=direct["id"]).changed_at

    edited = mine.patch(path, json.dumps({"body": "Dolazim u 9"}), "application/json")
    assert (edited.json()["text"], edited.json()["edited"]) == ("Dolazim u 9", True)
    assert Conversation.objects.get(pk=direct["id"]).changed_at > before
    listed = theirs.get(f"/api/conversations/{direct['id']}/messages").json()["messages"]
    assert [(each["text"], each["edited"]) for each in listed] == [("Dolazim u 9", True)]
    assert conversations.summaries(ana.pk)[0]["last"]["text"] == "Dolazim u 9"

    refused = theirs.patch(path, json.dumps({"body": "Ne dolazi"}), "application/json")
    assert (refused.status_code, refused.json()) == (403, {"error": "not_yours"})
    assert theirs.delete(path).status_code == 403
    assert mine.delete(f"/api/conversations/{direct['id']}/messages/{said['id'] + 1}").json() == {
        "error": "no_message"
    }

    assert mine.delete(path).status_code == 204
    assert not Message.objects.filter(pk=said["id"]).exists()
    assert conversations.summaries(ana.pk)[0]["last"] is None


def test_everyone_in_a_conversation_reacts_with_an_emoji_once_and_takes_it_back(owner, ana):
    mine, theirs = signed(owner), signed(ana)
    direct = posted(mine, "/api/conversations", people=[{"address": "ana@example.com"}]).json()
    said = written(mine, direct["id"], "Dolazim u 8").json()
    path = f"/api/conversations/{direct['id']}/messages/{said['id']}/reactions"
    before = Conversation.objects.get(pk=direct["id"]).changed_at
    for client in (theirs, theirs, mine):
        assert client.put(f"{path}/{quote('👍')}").status_code == 204
    assert theirs.put(f"{path}/{quote('🎉')}").status_code == 204
    assert Conversation.objects.get(pk=direct["id"]).changed_at > before

    def reactions(client):
        listed = client.get(f"/api/conversations/{direct['id']}/messages").json()["messages"]
        return listed[0]["reactions"]

    assert reactions(mine) == [
        {"emoji": "👍", "people": ["Ana Kovač", "Ivo Bošković"], "mine": True},
        {"emoji": "🎉", "people": ["Ana Kovač"], "mine": False},
    ]
    assert theirs.delete(f"{path}/{quote('👍')}").status_code == 204
    assert reactions(theirs) == [
        {"emoji": "👍", "people": ["Ivo Bošković"], "mine": False},
        {"emoji": "🎉", "people": ["Ana Kovač"], "mine": True},
    ]
    for wrong in ("👍👍", "a"):
        refused = mine.put(f"{path}/{quote(wrong)}")
        assert (refused.status_code, refused.json()) == (400, {"error": "invalid_emoji"})
    outsider = signed(person("marko@example.com", "Marko", "Horvat"))
    assert outsider.put(f"{path}/{quote('👍')}").json() == {"error": "no_conversation"}
    missing = f"/api/conversations/{direct['id']}/messages/{said['id'] + 1}/reactions/{quote('👍')}"
    assert mine.put(missing).json() == {"error": "no_message"}


def test_a_meeting_made_in_a_conversation_rings_everyone_else_in_it(owner, ana):
    mine = signed(owner)
    marko = person("marko@example.com", "Marko", "Horvat")
    group = posted(
        mine,
        "/api/conversations",
        people=[{"address": "ana@example.com"}, {"address": "marko@example.com"}],
        title="Projekt",
    ).json()
    made = posted(mine, "/api/meetings", conversation=group["id"])
    assert made.status_code == 201
    assert (made.json()["title"], made.json()["conversation"]) == ("Projekt", group["id"])
    assert sorted(Ring.objects.values_list("user__first_name", flat=True)) == ["Ana", "Marko"]
    assert mine.get(f"/api/conversations/{group['id']}").json()["meeting"] == made.json()["id"]
    assert Member.objects.filter(conversation_id=group["id"]).count() == 3

    elsewhere = posted(signed(marko), "/api/meetings", conversation=str(uuid.uuid4()))
    assert (elsewhere.status_code, elsewhere.json()) == (404, {"error": "no_conversation"})


def test_the_colleagues_a_conversation_may_start_with_are_found_by_name_or_address(owner, ana):
    person("marko@example.com", "Marko", "Horvat")
    mine = signed(owner)
    found = mine.get("/api/conversations/people?q=ko").json()
    assert found == {
        "people": [{"name": "Ana Kovač", "address": "ana@example.com"}],
        "unanswered": [],
    }
    assert mine.get("/api/conversations/people?q=ivo").json()["people"] == []
    assert mine.get("/api/conversations/people").json()["people"] == []
