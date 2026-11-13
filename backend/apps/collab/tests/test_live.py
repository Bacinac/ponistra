from datetime import timedelta

import pytest
from anyio import create_task_group, move_on_after
from django.contrib.auth.models import Group
from django.utils import timezone

from apps.access.models import Grant, Role
from apps.calendar.models import Calendar, Event
from apps.collab import live
from apps.collab.server import REFUSED
from apps.contacts.models import Contact
from apps.core.asyncdb import database
from apps.core.views import shipped
from apps.documents.models import Node
from apps.meetings.tests.test_rings import Tab, colleague_cookie
from apps.tasks.models import Task
from apps.vault.models import Collection, Item, Member


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_tab_hears_which_of_its_users_data_changed_however_it_changed():
    cookie, owner, ana = await colleague_cookie()
    async with create_task_group() as tg:
        tg.start_soon(live.listen)
        tab = Tab(cookie, tg)
        first = await tab.state()
        assert first["type"] == "state"
        assert first["release"] == shipped()

        async def heard(change=None) -> list[str]:
            """The areas of what the change sent, in one message or a few close after."""
            if change:
                await database(change)()
            areas = set((await tab.state())["areas"])
            while True:
                with move_on_after(0.5):
                    areas.update((await tab.state())["areas"])
                    continue
                return sorted(areas)

        def contacts():
            Contact.objects.create(owner=owner, uid="a", href="a.vcf")
            Contact.objects.create(owner=ana, uid="b", href="b.vcf")

        assert await heard(contacts) == ["contacts"]

        def shared():
            group = Group.objects.create(name="Nabava")
            ana.groups.add(group)
            folder = Node.objects.create(kind=Node.Kind.FOLDER, title="Nabava", company=True)
            Grant.objects.create(node=folder, group=group, role=Role.READ)
            return folder

        folder = await database(shared)()
        assert await heard() == ["nodes"]

        def elsewhere():
            private = Node.objects.create(kind=Node.Kind.FOLDER, title="Moje")
            Grant.objects.create(node=private, user=owner, role=Role.OWN)
            Node.objects.create(kind=Node.Kind.FOLDER, title="Ponuda", parent=private)
            Task.objects.create(owner=ana, text="Nazvati dobavljača")

        assert await heard(elsewhere) == ["tasks"]

        def inside():
            Node.objects.create(kind=Node.Kind.FOLDER, title="Ponude", parent=folder)

        assert await heard(inside) == ["nodes"]

        def calendar():
            mine = Calendar.objects.create(owner=ana, name="Ana")
            Calendar.objects.create(owner=owner, name="Ivo")
            starts = timezone.now()
            Event.objects.create(
                calendar=mine,
                uid="e",
                href="e.ics",
                starts=starts,
                ends=starts + timedelta(hours=1),
            )

        assert await heard(calendar) == ["calendar"]

        def vault():
            team = Collection.objects.create(kind=Collection.Kind.SHARED, name="Tim")
            Member.objects.create(collection=team, group=Group.objects.get(), role=Role.READ)
            Item.objects.create(collection=team, key=b"k", data=b"d")

        assert await heard(vault) == ["vault"]
        await tab.leave()
        tg.cancel_scope.cancel()


def test_a_socket_closing_does_not_stop_the_others_hearing():
    held = live._Held()
    held.wakes.close()
    held.wake("mail")
    assert held.areas == {"mail"}


@pytest.mark.anyio
@pytest.mark.django_db(transaction=True)
async def test_a_tab_nobody_signed_in_is_refused_as_reached_not_as_lost():
    async with create_task_group() as tg:
        tab = Tab("", tg)
        assert await tab.from_server.receive() == {"type": "websocket.accept"}
        assert await tab.from_server.receive() == {"type": "websocket.close", "code": REFUSED}
