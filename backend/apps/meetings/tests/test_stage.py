import uuid

import pytest

from apps.blobs.tests.test_blobs import content
from apps.documents import boards
from apps.documents.models import BoardEntry, Node
from apps.documents.printing import compact
from apps.documents.tests.test_boards import PAGE
from apps.documents.tests.test_views import create, to_trash
from apps.meetings import livekit
from apps.meetings.models import Guest, Meeting
from apps.users.models import User

from .test_recordings import sent, signed

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def staged(monkeypatch):
    told: list[dict] = []
    monkeypatch.setattr(livekit, "staged", lambda room, state: told.append(state))
    return told


def made_board(user) -> str:
    return create(signed(user), "file", "Prodaja", blob=boards.page(PAGE).sha256, extension="html")


def test_a_member_in_the_call_shows_a_board_of_theirs_to_everyone_guests_too(
    owner, ana, meeting, present, staged
):
    board = made_board(owner)
    guest = Guest.objects.create(meeting=meeting, name="Eva", state=Guest.State.ADMITTED)
    at = f"/api/meetings/{meeting.id}/board"
    away = sent(signed(owner), "post", at, board=board)
    assert (away.status_code, away.json()) == (403, {"error": "not_in_call"})
    present[:] = [f"{owner.pk}.a1", f"{ana.pk}.b2", f"{livekit.guest_identity(guest.pk)}.c3"]
    hers = sent(signed(ana), "post", at, board=board)
    assert (hers.status_code, hers.json()) == (404, {"error": "not_found"})
    assert sent(signed(owner), "post", at, board=board).status_code == 204
    [state] = staged
    assert state["recording"] is False
    assert state["board"] | {"data": None} == {
        "id": board,
        "title": "Prodaja",
        "by": "Ivo Bošković",
        "user": owner.pk,
        "page": Node.objects.get(pk=board).blob_id,
        "data": None,
    }

    for client, base in (
        (signed(ana), f"/api/meetings/{meeting.id}/stage"),
        (signed(User.objects.create_user("eva@example.com", "x")), None),
        (signed(owner), f"/api/meetings/{meeting.id}/guests/{guest.key}/stage"),
    ):
        if base is None:
            assert client.get(f"/api/meetings/{meeting.id}/stage").status_code == 404
            continue
        frame = client.get(base)
        assert frame.status_code == 200
        assert "data-reads" in frame.content.decode()
        assert f'src="{base}/page"' in frame.content.decode()
        page = client.get(f"{base}/page")
        assert page.status_code == 200
        assert content(page) == PAGE.encode()
        assert "sandbox" in page["Content-Security-Policy"]
        assert client.get(f"{base}/data").json() == {"collections": []}
        written = client.put(
            f"{base}/data?collection=a&key=b", "{}", content_type="application/json"
        )
        assert written.status_code == 405

    present.remove(f"{ana.pk}.b2")
    away = signed(ana).get(f"/api/meetings/{meeting.id}/stage/data")
    assert (away.status_code, away.json()) == (403, {"error": "not_in_call"})
    present.remove(f"{owner.pk}.a1")
    left = signed(ana).get(f"/api/meetings/{meeting.id}/guests/{guest.key}/stage/data")
    assert (left.status_code, left.json()) == (404, {"error": "no_board"})
    present.append(f"{owner.pk}.a1")

    BoardEntry.objects.create(node_id=board, collection="prodaja", key="1", data={"n": 12})
    assert signed(ana).post(f"/api/meetings/{meeting.id}/board/changed").status_code == 204
    assert len(staged) == 1
    assert signed(owner).post(f"/api/meetings/{meeting.id}/board/changed").status_code == 204
    assert staged[-1]["board"]["data"].startswith("1:")

    assert signed(ana).delete(at).status_code == 204
    assert staged[-1] == {"recording": False, "board": None}
    gone = signed(owner).get(f"/api/meetings/{meeting.id}/guests/{guest.key}/stage/page")
    assert (gone.status_code, gone.json()) == (404, {"error": "no_board"})


def test_a_board_trashed_or_a_guest_turned_away_leaves_the_stage_empty(
    owner, meeting, present, staged
):
    board = made_board(owner)
    guest = Guest.objects.create(meeting=meeting, name="Eva", state=Guest.State.ADMITTED)
    present[:] = [f"{owner.pk}.a1", f"{livekit.guest_identity(guest.pk)}.c3"]
    sent(signed(owner), "post", f"/api/meetings/{meeting.id}/board", board=board)
    Guest.objects.filter(pk=guest.pk).update(state=Guest.State.REFUSED)
    away = signed(owner).get(f"/api/meetings/{meeting.id}/guests/{guest.key}/stage")
    assert away.status_code == 403
    assert to_trash(signed(owner), board).status_code == 204
    assert Meeting.objects.get().board_id is not None
    gone = signed(owner).get(f"/api/meetings/{meeting.id}/stage")
    assert (gone.status_code, gone.json()) == (404, {"error": "no_board"})


def test_only_a_board_goes_on_the_stage(owner, meeting, present, staged):
    present[:] = [f"{owner.pk}.a1"]
    document = create(signed(owner), "document", "Ugovor")
    shown = sent(signed(owner), "post", f"/api/meetings/{meeting.id}/board", board=document)
    assert (shown.status_code, shown.json()) == (404, {"error": "not_found"})
    assert staged == []


def test_the_tabs_prepared_are_named_for_whoever_reads_them_and_a_board_marked(owner, ana, meeting):
    board = made_board(owner)
    plan = create(signed(owner), "document", "Plan rada")
    hers = create(signed(ana), "document", "Njezin")
    link = sent(
        signed(owner), "post", "/api/nodes", kind="link", href="https://e.hr/k", title="Katalog"
    )
    assert link.status_code == 201
    here = "https://ured.example.com/p/"
    tabs = [
        f"{here}prodaja-{compact(uuid.UUID(board))}",
        f"https://ured.example.com/d/plan-rada-{compact(uuid.UUID(plan))}",
        f"{here}njezin-{compact(uuid.UUID(hers))}",
        f"https://drugi.example.com/p/{compact(uuid.uuid4())}",
        "https://e.hr/k",
        "https://e.hr/x",
    ]
    shown = sent(signed(owner), "patch", f"/api/meetings/{meeting.id}", tabs=tabs)
    assert [(each["title"], each["board"]) for each in shown.json()["tabs"]] == [
        ("Prodaja", board),
        ("Plan rada", None),
        (None, None),
        (None, None),
        ("Katalog", None),
        (None, None),
    ]
    assert [each["address"] for each in shown.json()["tabs"]] == tabs
    theirs = signed(ana).get(f"/api/meetings/{meeting.id}").json()["tabs"]
    assert [each["title"] for each in theirs] == [None, None, "Njezin", None, None, None]
