import json
from datetime import timedelta

import anyio
import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.test import Client
from django.utils import timezone

from apps.chat import conversations
from apps.chat.models import Member
from apps.mail import taking
from apps.mail.models import Source
from apps.mail.tests.test_views import kept
from apps.meetings import rings
from apps.meetings.models import Meeting
from apps.push import notices, webpush
from apps.push.models import Keys, Notice, Subscription
from apps.users.models import User

pytestmark = pytest.mark.django_db

ENDPOINT = "https://push.example/send/"
# RFC 8291, appendix A: the subscription's keys, the sender's, the salt and what they encrypt.
UA_PRIVATE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
UA_PUBLIC = (
    "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
)
AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
SALT = "DGv6ra1nlYgDCS1FRnbzlw"
PLAINTEXT = b"When I grow up, I want to be a watermelon"
CIPHERTEXT = (
    "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8w"
    "EqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
)


def person(email: str, first: str, admin: bool = False) -> User:
    return User.objects.create_user(
        email, "Kamen-Most-Rijeka-71", first_name=first, last_name="K.", is_staff=admin
    )


@pytest.fixture
def owner():
    return person("ivo@example.com", "Ivo", admin=True)


@pytest.fixture
def ana():
    return person("ana@example.com", "Ana")


def signed(user) -> Client:
    client = Client(HTTP_USER_AGENT="Mozilla/5.0 (Android) Chrome/142")
    client.force_login(user)
    return client


def subscribed(user, endpoint=ENDPOINT, language="hr") -> Subscription:
    return Subscription.objects.create(
        user=user,
        endpoint=endpoint,
        p256dh=webpush.unb64(UA_PUBLIC),
        auth=webpush.unb64(AUTH),
        language=language,
    )


def test_a_notice_is_encrypted_as_the_rfc_shows():
    found = webpush.encrypted(
        webpush.unb64(UA_PUBLIC),
        webpush.unb64(AUTH),
        PLAINTEXT,
        sender=webpush.unb64(AS_PRIVATE),
        salt=webpush.unb64(SALT),
    )
    assert webpush.b64(found) == CIPHERTEXT
    # Without the vector's sender and salt each encryption is new, and the header still says so.
    other = webpush.encrypted(webpush.unb64(UA_PUBLIC), webpush.unb64(AUTH), PLAINTEXT)
    assert other != found and other[16:21] == bytes([0, 0, 16, 0, 65])


def test_the_installation_signs_with_one_key_pair_made_once(owner):
    keys = webpush.keys()
    assert keys == webpush.keys() and Keys.objects.count() == 1
    header = webpush.authorization(ENDPOINT, keys, webpush.contact(), now=1_700_000_000)
    assert header.startswith("vapid t=") and f", k={webpush.b64(bytes(keys.public))}" in header
    token = header[len("vapid t=") : header.index(",")]
    public = ec.EllipticCurvePublicKey.from_encoded_point(webpush.CURVE, bytes(keys.public))
    pem = public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    claims = jwt.decode(
        token,
        pem,
        algorithms=["ES256"],
        audience="https://push.example",
        options={"verify_exp": False},
    )
    assert claims == {
        "aud": "https://push.example",
        "exp": 1_700_000_000 + webpush.SIGNED,
        "sub": "mailto:ivo@example.com",
    }


def test_a_browser_subscribes_sees_its_own_among_the_users_and_leaves(owner, ana):
    mine = signed(owner)
    asked = mine.get("/api/push")
    assert asked.status_code == 200
    assert asked.json()["on"] is True and asked.json()["subscriptions"] == []
    assert webpush.unb64(asked.json()["key"]) == bytes(webpush.keys().public)

    made = mine.post(
        "/api/push/subscriptions",
        json.dumps({"endpoint": ENDPOINT, "keys": {"p256dh": UA_PUBLIC, "auth": AUTH}}),
        content_type="application/json",
    )
    assert made.status_code == 201
    subscription = Subscription.objects.get()
    assert (subscription.user, subscription.language) == (owner, "hr")
    assert subscription.agent == "Mozilla/5.0 (Android) Chrome/142"
    again = mine.post(
        "/api/push/subscriptions",
        json.dumps(
            {"endpoint": ENDPOINT, "keys": {"p256dh": UA_PUBLIC, "auth": AUTH}, "language": "en"}
        ),
        content_type="application/json",
    )
    assert (again.status_code, Subscription.objects.count()) == (200, 1)
    assert Subscription.objects.get().language == "en"

    listed = mine.get("/api/push", {"endpoint": ENDPOINT}).json()["subscriptions"]
    assert [(each["id"], each["current"], each["language"]) for each in listed] == [
        (subscription.pk, True, "en")
    ]
    assert signed(ana).get("/api/push").json()["subscriptions"] == []
    assert signed(ana).delete(f"/api/push/subscriptions/{subscription.pk}").status_code == 404
    assert mine.delete(f"/api/push/subscriptions/{subscription.pk}").status_code == 204
    assert not Subscription.objects.exists()

    for given, error in [
        ({"endpoint": "http://push.example/", "keys": {}}, "invalid_endpoint"),
        ({"endpoint": ENDPOINT, "keys": {"p256dh": "AAAA", "auth": AUTH}}, "invalid_p256dh"),
        ({"endpoint": ENDPOINT, "keys": {"p256dh": UA_PUBLIC, "auth": "AA"}}, "invalid_auth"),
        (
            {"endpoint": ENDPOINT, "keys": {"p256dh": UA_PUBLIC, "auth": AUTH}, "language": "de"},
            "invalid_language",
        ),
    ]:
        refused = mine.post(
            "/api/push/subscriptions", json.dumps(given), content_type="application/json"
        )
        assert (refused.status_code, refused.json()["error"]) == (400, error)


def test_an_administrator_turns_sending_off_for_the_installation(owner, ana):
    subscribed(ana)
    assert signed(ana).get("/api/push/setting").status_code == 403
    mine = signed(owner)
    assert mine.get("/api/push/setting").json()["on"] is True
    notices.tell([ana.pk], Notice.Kind.MAIL, {})
    assert Notice.objects.filter(kind=Notice.Kind.MAIL).count() == 1
    off = mine.patch(
        "/api/push/setting", json.dumps({"on": False}), content_type="application/json"
    )
    assert off.json()["on"] is False and off.json()["changed_by"]["id"] == owner.pk
    assert not Notice.objects.exists()
    notices.tell([ana.pk], Notice.Kind.MAIL, {})
    assert not Notice.objects.exists()
    assert signed(ana).get("/api/push").json()["on"] is False
    bad = mine.patch("/api/push/setting", json.dumps({"on": "da"}), content_type="application/json")
    assert bad.json() == {"error": "invalid_on"}


def test_only_users_with_a_browser_subscribed_get_a_notice(owner, ana):
    notices.tell([owner.pk, ana.pk], Notice.Kind.MAIL, {"x": 1})
    assert not Notice.objects.exists()
    subscribed(ana)
    notices.tell([owner.pk, ana.pk], Notice.Kind.MAIL, {"x": 1}, tag="mail-1")
    notice = Notice.objects.get()
    assert (notice.user, notice.kind, notice.data, notice.tag) == (ana, "mail", {"x": 1}, "mail-1")
    assert (notice.urgency, notice.ttl, notice.tried) == ("normal", 86400, 0)


def test_each_kind_is_worded_in_the_browsers_language(ana):
    mail = Notice(
        user=ana,
        kind=Notice.Kind.MAIL,
        data={"name": "", "address": "ana@x.test", "subject": "", "folder": 3, "message": 7},
        tag="mail-7",
    )
    assert notices.worded(mail, "hr", 0) == {
        "kind": "mail",
        "title": "ana@x.test",
        "body": "(bez predmeta)",
        "url": "/mail/3/7",
        "tag": "mail-7",
        "unread": 0,
    }
    assert notices.worded(mail, "en", 0)["body"] == "(no subject)"
    message = Notice(
        user=ana,
        kind=Notice.Kind.MESSAGE,
        data={"by": "Ivo", "text": "Dobar  dan", "title": "", "conversation": "c1"},
    )
    assert notices.worded(message, "hr", 0) == {
        "kind": "message",
        "title": "Ivo",
        "body": "Dobar dan",
        "url": "/chat/c1",
        "tag": "",
        "unread": 0,
    }
    message.data["title"] = "Kolegij"
    assert notices.worded(message, "hr", 0)["title"] == "Kolegij"
    assert notices.worded(message, "hr", 0)["body"] == "Ivo: Dobar dan"
    ring = Notice(
        user=ana, kind=Notice.Kind.RING, data={"by": "Ivo K.", "title": "", "meeting": "m1"}
    )
    assert notices.worded(ring, "hr", 0) == {
        "kind": "ring",
        "title": "Ivo K. vas zove",
        "body": "Sastanak",
        "url": "/meet/m1",
        "tag": "",
        "unread": 0,
    }
    assert notices.worded(ring, "en", 0)["title"] == "Ivo K. is calling"
    signed_in = Notice(
        user=ana, kind=Notice.Kind.SECURITY, data={"event": "sign_in", "address": "203.0.113.9"}
    )
    assert notices.worded(signed_in, "hr", 0) == {
        "kind": "security",
        "title": "Nova prijava u Ponistru",
        "body": "203.0.113.9",
        "url": "/settings/devices",
        "tag": "",
        "unread": 0,
    }
    passkey = Notice(
        user=ana, kind=Notice.Kind.SECURITY, data={"event": "passkey", "name": "Laptop"}
    )
    assert notices.worded(passkey, "en", 0)["title"] == "A passkey was added"
    assert notices.worded(passkey, "en", 0)["body"] == "Laptop"
    assert notices.worded(passkey, "en", 0)["url"] == "/settings/passkeys"
    long = Notice(
        user=ana,
        kind=Notice.Kind.RING,
        data={"by": "Ivo", "title": "x" * 500, "meeting": "m1"},
    )
    assert len(notices.worded(long, "hr", 0)["body"]) == notices.TEXT


def test_a_notice_carries_what_waits_unread_in_the_inboxes_and_the_conversations(owner, ana):
    source = inbox(kept(ana, "ana@firma.test"))
    taking.took(source, mail("Message-ID: <1@x>", "From: ivo@x.test", "Subject: Ponuda"), {})
    taking.took(source, mail("Message-ID: <2@x>", "From: ivo@x.test"), {"seen": True})
    meeting = Meeting.objects.made("Kolegij", owner)
    conversations.added(meeting.conversation, [ana])
    conversations.written(Member.objects.get(conversation=meeting.conversation, user=owner), "Bok")
    assert (notices.unread(ana.pk), notices.unread(owner.pk)) == (2, 0)
    ring = Notice(user=ana, kind=Notice.Kind.RING, data={"by": "Ivo", "title": "", "meeting": "m"})
    assert notices.worded(ring, "hr", 2)["unread"] == 2


def delivered(answer):
    """Runs one sending step against a push service answering as `answer` says; the requests."""
    asked = []

    def handler(request):
        asked.append(request)
        return httpx2.Response(answer(request))

    anyio.run(notices._step, httpx2.MockTransport(handler))
    return asked


@pytest.mark.django_db(transaction=True)
def test_a_notice_reaches_every_browser_of_the_user_and_a_gone_one_is_forgotten(owner, ana):
    chrome = subscribed(ana, "https://push.example/chrome")
    firefox = subscribed(ana, "https://push.example/firefox", language="en")
    subscribed(owner, "https://push.example/ivo")
    notices.tell(
        [ana.pk],
        Notice.Kind.RING,
        {"by": "Ivo", "title": "Kolegij", "meeting": "m1"},
        tag="ring-m1",
        urgency="high",
        ttl=45,
    )
    asked = delivered(lambda request: 410 if request.url.path == "/firefox" else 201)
    assert [str(each.url) for each in asked] == [chrome.endpoint, firefox.endpoint]
    sent = asked[0]
    assert sent.headers["Content-Encoding"] == "aes128gcm"
    assert (sent.headers["TTL"], sent.headers["Urgency"], sent.headers["Topic"]) == (
        "45",
        "high",
        "ring-m1",
    )
    assert sent.headers["Authorization"].startswith("vapid t=")
    assert len(sent.content) > 86 + len(b'{"kind": "ring"')
    assert not Notice.objects.exists()
    assert [each.endpoint for each in Subscription.objects.filter(user=ana)] == [chrome.endpoint]
    assert Subscription.objects.get(pk=chrome.pk).used_at is not None
    assert not delivered(lambda request: 201)


@pytest.mark.django_db(transaction=True)
def test_a_failed_send_is_tried_again_and_given_up_after_its_tries_or_its_time(owner, ana):
    subscribed(ana)
    notices.tell(
        [ana.pk],
        Notice.Kind.MAIL,
        {"name": "", "address": "", "subject": "", "folder": 1, "message": 1},
    )
    assert len(delivered(lambda request: 503)) == 1
    notice = Notice.objects.get()
    assert notice.tried == 1 and notice.due_at > timezone.now() + timedelta(seconds=30)
    assert not delivered(lambda request: 201)
    Notice.objects.update(due_at=timezone.now(), tried=notices.TRIES)
    assert not delivered(lambda request: 201)
    assert not Notice.objects.exists()
    notices.tell([ana.pk], Notice.Kind.MAIL, {}, ttl=45)
    Notice.objects.update(created_at=timezone.now() - timedelta(minutes=1))
    assert not delivered(lambda request: 201)
    assert not Notice.objects.exists()


def test_a_conversations_message_reaches_the_others_browsers_not_the_writers(owner, ana):
    subscribed(owner, "https://push.example/ivo")
    subscribed(ana, "https://push.example/ana")
    meeting = Meeting.objects.made("Kolegij", owner)
    conversations.added(meeting.conversation, [ana])
    member = Member.objects.get(conversation=meeting.conversation, user=owner)
    conversations.written(member, "Počinjemo  u 9")
    notice = Notice.objects.get()
    assert notice.user == ana and notice.kind == "message"
    assert notice.data == {
        "by": "Ivo K.",
        "text": "Počinjemo u 9",
        "title": "Kolegij",
        "conversation": str(meeting.conversation_id),
    }
    assert notice.tag == notices.topic("chat", meeting.conversation_id) and len(notice.tag) <= 32


def test_a_ring_reaches_the_rung_at_once_for_as_long_as_it_rings(owner, ana):
    subscribed(ana)
    meeting = Meeting.objects.made("Kolegij", owner)
    rings.ring(owner, meeting, [ana])
    notice = Notice.objects.get()
    assert (notice.user, notice.kind, notice.urgency, notice.ttl) == (ana, "ring", "high", 45)
    assert notice.data == {"by": "Ivo K.", "title": "Kolegij", "meeting": str(meeting.id)}


def inbox(account) -> Source:
    return Source.objects.create(
        account=account,
        name="INBOX",
        kind=Source.Kind.INBOX,
        folder=taking.folder(account, Source.Kind.INBOX, ["INBOX"]),
    )


def mail(*headers: str) -> bytes:
    return ("\r\n".join(headers) + "\r\n\r\nx").encode()


def test_mail_that_arrives_unread_in_the_inbox_reaches_the_browsers_what_was_there_does_not(ana):
    subscribed(ana)
    account = kept(ana, "ana@firma.test")
    source = inbox(account)
    sent = Source.objects.create(
        account=account,
        name="Sent",
        kind=Source.Kind.SENT,
        folder=taking.folder(account, Source.Kind.SENT, ["Sent"]),
    )
    held = taking.took(
        source, mail("Message-ID: <1@x>", "From: Ivo <ivo@x.test>", "Subject: Stara"), {}
    )
    assert held and not Notice.objects.exists()
    seen = taking.took(
        source,
        mail("Message-ID: <2@x>", "From: ivo@x.test", "Subject: Viđena"),
        {"seen": True},
        fresh=True,
    )
    assert seen and not Notice.objects.exists()
    taking.took(
        sent, mail("Message-ID: <3@x>", "From: ana@firma.test", "Subject: Moja"), {}, fresh=True
    )
    assert not Notice.objects.exists()
    new = taking.took(
        source,
        mail("Message-ID: <4@x>", "From: Ivo <ivo@x.test>", "Subject: Ponuda"),
        {},
        fresh=True,
    )
    notice = Notice.objects.get()
    assert notice.user == ana and notice.kind == "mail" and notice.tag == f"mail-{new.pk}"
    assert notice.data == {
        "name": "Ivo",
        "address": "ivo@x.test",
        "subject": "Ponuda",
        "folder": new.folder_id,
        "message": new.pk,
    }
    # Taken again from the provider, the same message is not news.
    Notice.objects.all().delete()
    taking.took(
        source,
        mail("Message-ID: <4@x>", "From: Ivo <ivo@x.test>", "Subject: Ponuda"),
        {},
        fresh=True,
    )
    assert not Notice.objects.exists()
