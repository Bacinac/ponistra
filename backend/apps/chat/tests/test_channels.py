import pytest

from apps.chat import conversations
from apps.chat.models import Conversation, Follower, Member, Mention, Message
from apps.collab import live
from apps.meetings.models import Ring
from apps.push import notices as push
from apps.push.models import Notice

from .test_conversations import person, posted, signed

pytestmark = pytest.mark.django_db


def founded(client, title: str, **more) -> dict:
    response = posted(client, "/api/channels", title=title, **more)
    assert response.status_code == 201
    return response.json()


def test_an_open_channel_is_listed_read_and_joined_by_any_colleague(owner, ana):
    mine, hers = signed(owner), signed(ana)
    made = founded(mine, "Nabava")
    at = f"/api/conversations/{made['id']}"
    posted(mine, f"{at}/messages", body="Dobro jutro")

    listed = hers.get("/api/channels").json()["channels"]
    assert listed == [{"id": made["id"], "title": "Nabava", "count": 1, "joined": False}]
    assert hers.get(at).json()["joined"] is False
    assert [each["text"] for each in hers.get(f"{at}/messages").json()["messages"]] == [
        "Dobro jutro"
    ]
    assert posted(hers, f"{at}/messages", body="Ja").status_code == 404
    assert conversations.summaries(ana.pk) == []

    assert posted(hers, f"{at}/join").json()["joined"] is True
    assert posted(hers, f"{at}/messages", body="Ja").status_code == 201
    assert [each["id"] for each in conversations.summaries(ana.pk)] == [made["id"]]


def test_a_private_channel_exists_only_for_its_members(owner, ana):
    mine, hers = signed(owner), signed(ana)
    made = founded(mine, "Uprava", private=True)
    at = f"/api/conversations/{made['id']}"

    assert hers.get("/api/channels").json()["channels"] == []
    assert hers.get(at).json() is None
    assert hers.get(f"{at}/messages").status_code == 404
    assert posted(hers, f"{at}/join").status_code == 404

    assert posted(mine, f"{at}/members", people=[{"address": ana.email}]).status_code == 200
    assert hers.get(at).json()["joined"] is True


def test_an_open_channels_name_is_the_installations_alone(owner):
    mine = signed(owner)
    founded(mine, "Nabava")
    assert posted(mine, "/api/channels", title="nabava").status_code == 409
    assert posted(mine, "/api/channels", title="  ").status_code == 400
    founded(mine, "nabava", private=True)


def test_the_last_one_out_leaves_an_open_channel_but_takes_a_private_one(owner):
    mine = signed(owner)
    kept = founded(mine, "Nabava")
    gone = founded(mine, "Uprava", private=True)
    for each in (kept, gone):
        assert mine.delete(f"/api/conversations/{each['id']}/members").status_code == 204
    assert list(Conversation.objects.values_list("title", flat=True)) == ["Nabava"]


def test_an_open_channel_is_deleted_by_its_founder_or_an_administrator(owner, ana):
    made = founded(signed(owner), "Nabava")
    at = f"/api/conversations/{made['id']}"
    assert signed(ana).delete(at).status_code == 403
    admin = person("admin@example.com", "Ad", "Min")
    admin.is_staff = True
    admin.save()
    assert signed(admin).get(at).json()["removable"] is True
    assert signed(owner).delete(at).status_code == 204
    assert not Conversation.objects.exists()


def test_a_change_to_a_conversation_concerns_whoever_may_see_it(owner, ana):
    mine = signed(owner)
    opened = founded(mine, "Nabava")
    closed = founded(mine, "Uprava", private=True)
    assert conversations.concerned(opened["id"]) is None
    assert conversations.concerned(closed["id"]) == [owner.pk]
    Conversation.objects.filter(pk=closed["id"]).delete()
    assert conversations.concerned(closed["id"]) is None
    assert live.AUDIENCES["o"] is conversations.concerned
    assert not Member.objects.filter(conversation_id=closed["id"]).exists()


def test_a_meeting_opened_in_a_channel_is_a_message_and_rings_nobody(owner, ana):
    mine = signed(owner)
    made = founded(mine, "Nabava", people=[{"address": ana.email}])
    response = posted(mine, "/api/meetings", conversation=made["id"])
    assert response.status_code == 201
    message = mine.get(f"/api/conversations/{made['id']}/messages").json()["messages"][0]
    assert message["meeting"] == response.json()["id"]
    assert not Ring.objects.exists()


@pytest.fixture
def told(monkeypatch):
    heard = []

    def tell(users, kind, data, **more):
        if kind == Notice.Kind.MESSAGE:
            heard.append(sorted(users))

    monkeypatch.setattr(push, "tell", tell)
    return heard


def in_channel(owner, ana):
    mine = signed(owner)
    made = founded(mine, "Nabava")
    at = f"/api/conversations/{made['id']}"
    assert posted(signed(ana), f"{at}/join").status_code == 200
    return mine, at


def test_a_channel_tells_only_those_a_message_names(owner, ana, told):
    mine, at = in_channel(owner, ana)
    posted(mine, f"{at}/messages", body="Dobro jutro")
    posted(mine, f"{at}/messages", body="@Ana Kovač pogledaj", mentions=[ana.pk])
    assert told == [[], [ana.pk]]
    assert conversations.unread(ana.pk) == 1
    summary = conversations.summaries(ana.pk)[0]
    assert (summary["unread"], summary["mentions"]) == (2, 1)
    last = Message.objects.order_by("-id").first().pk
    conversations.read(Member.objects.get(user=ana), last)
    assert conversations.unread(ana.pk) == 0


def test_naming_everyone_tells_every_other_member(owner, ana, told):
    mine, at = in_channel(owner, ana)
    message = posted(mine, f"{at}/messages", body="@svi sastanak u 10", everyone=True).json()
    assert told == [[ana.pk]]
    assert message["everyone"] is True
    assert ana.pk in Mention.objects.values_list("user_id", flat=True)


def test_a_name_must_stand_in_the_text_and_be_a_member(owner, ana, told):
    mine, at = in_channel(owner, ana)
    outsider = person("bruno@example.com", "Bruno", "Babić")
    posted(mine, f"{at}/messages", body="bez imena", mentions=[ana.pk, outsider.pk])
    posted(mine, f"{at}/messages", body="@Bruno Babić", mentions=[outsider.pk])
    assert not Mention.objects.exists()


def test_editing_tells_only_the_newly_named(owner, ana, told):
    mine, at = in_channel(owner, ana)
    mid = posted(mine, f"{at}/messages", body="@Ana Kovač", mentions=[ana.pk]).json()["id"]
    told.clear()
    edit = {"body": "@Ana Kovač opet", "mentions": [ana.pk]}
    mine.patch(f"{at}/messages/{mid}", edit, content_type="application/json")
    assert told == []
    mine.patch(f"{at}/messages/{mid}", {"body": "nitko"}, content_type="application/json")
    assert not Mention.objects.exists()


def test_a_group_still_tells_everyone_with_one_notice(owner, ana, told):
    mine = signed(owner)
    made = posted(mine, "/api/conversations", people=[{"address": ana.email}], title="Ekipa").json()
    at = f"/api/conversations/{made['id']}"
    posted(mine, f"{at}/messages", body="@Ana Kovač", mentions=[ana.pk])
    assert told == [[ana.pk]]
    assert conversations.unread(ana.pk) == 1


def test_a_reply_goes_to_the_thread_and_tells_only_those_it_concerns(owner, ana, told):
    mine, at = in_channel(owner, ana)
    hers = signed(ana)
    root = posted(mine, f"{at}/messages", body="Pitanje").json()["id"]
    bruno = person("bruno@example.com", "Bruno", "Babić")
    posted(signed(bruno), f"{at}/join")
    told.clear()

    reply = posted(hers, f"{at}/messages", body="Odgovor", parent=root).json()
    assert told == [[owner.pk]]
    assert [each["id"] for each in mine.get(f"{at}/messages").json()["messages"]] == [root]
    assert mine.get(f"{at}/messages").json()["messages"][0]["thread"] == {"replies": 1, "unread": 1}
    assert [
        each["id"] for each in mine.get(f"{at}/messages/{root}/replies").json()["messages"]
    ] == [reply["id"]]
    assert conversations.unread(owner.pk) == 1
    summary = conversations.summaries(owner.pk)[0]
    assert (summary["last"]["id"], summary["threads"]) == (root, 1)
    assert conversations.unread(bruno.pk) == 0

    assert posted(mine, f"{at}/messages/{root}/read", message=reply["id"]).status_code == 204
    assert conversations.unread(owner.pk) == 0


def test_a_name_in_a_reply_brings_them_into_the_thread(owner, ana, told):
    mine, at = in_channel(owner, ana)
    root = posted(mine, f"{at}/messages", body="Pitanje").json()["id"]
    told.clear()
    posted(mine, f"{at}/messages", body="@Ana Kovač vidi", parent=root, mentions=[ana.pk])
    assert told == [[ana.pk]]
    assert set(Follower.objects.values_list("user_id", flat=True)) == {owner.pk, ana.pk}
    assert conversations.unread(ana.pk) == 1
    assert conversations.summaries(ana.pk)[0]["mentions"] == 0


def test_a_thread_has_one_level_and_only_a_channel_has_threads(owner, ana):
    mine, at = in_channel(owner, ana)
    root = posted(mine, f"{at}/messages", body="Pitanje").json()["id"]
    reply = posted(mine, f"{at}/messages", body="Odgovor", parent=root).json()["id"]
    assert posted(mine, f"{at}/messages", body="Dublje", parent=reply).status_code == 404

    group = posted(mine, "/api/conversations", people=[{"address": ana.email}], title="E").json()
    there = f"/api/conversations/{group['id']}"
    said = posted(mine, f"{there}/messages", body="x").json()["id"]
    response = posted(mine, f"{there}/messages", body="y", parent=said)
    assert (response.status_code, response.json()["error"]) == (400, "no_threads_here")


def test_taking_back_a_message_takes_its_thread(owner, ana):
    mine, at = in_channel(owner, ana)
    root = posted(mine, f"{at}/messages", body="Pitanje").json()["id"]
    posted(signed(ana), f"{at}/messages", body="Odgovor", parent=root)
    assert mine.delete(f"{at}/messages/{root}").status_code == 204
    assert not Message.objects.exists()
