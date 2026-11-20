import pytest

from apps.chat import conversations
from apps.meetings import livekit
from apps.meetings.models import Meeting
from apps.users.models import User


@pytest.fixture
def owner():
    return User.objects.create_user(
        "ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo", last_name="Bošković"
    )


@pytest.fixture
def ana():
    return User.objects.create_user(
        "ana@example.com", "Kamen-Most-Rijeka-72", first_name="Ana", last_name="Horvat"
    )


@pytest.fixture
def meeting(owner, ana):
    made = Meeting.objects.made("Kolegij", owner)
    conversations.added(made.conversation, [ana])
    return made


@pytest.fixture
def present(monkeypatch):
    there: list[str] = []

    async def inside(room):
        return there

    monkeypatch.setattr(livekit, "inside", inside)
    return there
