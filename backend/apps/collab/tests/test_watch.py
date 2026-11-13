import json
from dataclasses import replace
from math import inf

import pytest
from anyio import create_memory_object_stream, create_task_group, fail_after

from apps.access.models import Grant, Role
from apps.collab.server import REFUSED
from apps.collab.watch import watch
from apps.content import grids
from apps.content.blocks import Block, Grid, light_cell
from apps.content.tests.helpers import afill
from apps.core.asyncdb import database
from apps.documents.models import Node, Tab
from apps.users.models import User

from .test_server import session_cookie

pytestmark = [pytest.mark.anyio, pytest.mark.django_db(transaction=True)]

ORIGIN = "https://ponistra.example"


class Browser:
    """A browser on a document's grids socket: what it says, and what it has heard and not
    yet looked at, by type."""

    def __init__(self, document: Node, cookie: str, task_group, origin: str = ORIGIN):
        self.to_server, received = create_memory_object_stream[dict](inf)
        sent, self.from_server = create_memory_object_stream[dict](inf)
        headers = [
            (b"host", b"ponistra.example"),
            (b"origin", origin.encode()),
            (b"cookie", cookie.encode()),
        ]
        scope = {"type": "websocket", "path": f"/api/grids/{document.pk}", "headers": headers}
        self.to_server.send_nowait({"type": "websocket.connect"})
        task_group.start_soon(watch, scope, received.receive, sent.send)
        self.log: list[dict] = []

    async def answer(self) -> dict:
        with fail_after(5):
            return await self.from_server.receive()

    async def say(self, message: dict) -> None:
        await self.to_server.send({"type": "websocket.receive", "text": json.dumps(message)})

    async def heard(self, type: str) -> dict:
        with fail_after(5):
            while True:
                for at, each in enumerate(self.log):
                    if each["type"] == type:
                        return self.log.pop(at)
                message = await self.from_server.receive()
                assert message["type"] == "websocket.send", message
                self.log.append(json.loads(message["text"]))

    async def leave(self) -> None:
        await self.to_server.send({"type": "websocket.disconnect", "code": 1000})
        with fail_after(5):
            while (await self.from_server.receive())["type"] != "websocket.close":
                pass


async def priced(role: Role) -> tuple[Node, Tab]:
    """A document whose first tab holds a table of a number and an empty cell below it, with
    the signed-in user's role on it."""
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Cijene")
    tab = await Tab.objects.acreate(document=document, position=0)
    grid = Grid(["r1", "r2"], ["a"])
    await afill(tab, [Block("table", "t", grid=grid, cells=[light_cell("r1:a", "1.250,5")])])
    user = await User.objects.aget(email="ivo@example.com")
    await Grant.objects.acreate(node=document, user=user, role=role)
    return document, tab


async def test_a_browser_is_sent_the_rows_it_shows_its_edits_and_what_they_compute(live):
    cookie = await session_cookie()
    document, tab = await priced(Role.OWN)
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg)
        assert await browser.answer() == {"type": "websocket.accept"}
        await browser.say({"type": "watch", "tab": str(tab.pk)})
        outline = {"table": "t", "name": "", "cols": [["a", None]], "rows": 2}
        outline |= {"at": {"r1": 0, "r2": 1}}
        assert await browser.heard("grids") == {
            "type": "grids",
            "tab": str(tab.pk),
            "grids": [
                {**outline, "heights": {}, "looks": {}, "hidden": {}, "merges": {}, "frozen": None}
            ],
        }
        await browser.say({"type": "rows", "table": "t", "spans": [[0, 2]]})
        told = await browser.heard("rows")
        assert told["at"] == {"r1": 0, "r2": 1}
        assert told["rows"] == {
            "r1": {
                "cells": {"a": {"text": "1.250,5"}},
                "values": {"a": {"text": "1250,5", "kind": "number"}},
            },
            "r2": {"cells": {}, "values": {}},
        }
        asked = {"type": "standing", "table": "t", "places": [1, 5], "rows": ["r1", "gone"]}
        await browser.say(asked)
        assert await browser.heard("standing") == asked | {
            "numbered": [],
            "at": {"r2": 1, "r1": 0},
            "named": {},
        }
        cells = {
            "op": "cells",
            "table": "t",
            "cells": [{"row": "r2", "col": "a", "formula": "A1*2"}],
        }
        await browser.say({"type": "do", "token": "k1", "tab": str(tab.pk), "operations": [cells]})
        assert await browser.heard("patch") == {
            "type": "patch",
            "by": "k1",
            "patches": [{"table": "t", "cells": {"r2": {"a": {"formula": "=A1*2"}}}}],
        }
        assert await browser.heard("done") == {"type": "done", "token": "k1"}
        computed = {"text": "2501", "kind": "number"}
        assert (await browser.heard("patch"))["patches"] == [
            {"table": "t", "values": {"r2": {"a": computed}}}
        ]
        document.locale = Node.Locale.EN
        await document.asave()
        await live.recompute(document.pk, document.locale)
        error = {"text": "#VALUE!", "kind": "error"}
        assert (await browser.heard("patch"))["patches"] == [
            {"table": "t", "values": {"r1": {}, "r2": {"a": error}}}
        ]
        await browser.say({"type": "undo", "token": "k1", "as": "k2"})
        assert await browser.heard("patch") == {
            "type": "patch",
            "by": "k2",
            "patches": [{"table": "t", "cells": {"r2": {"a": None}}}],
        }
        assert await browser.heard("done") == {"type": "done", "token": "k1"}
        assert (await browser.heard("patch"))["patches"] == [{"table": "t", "values": {"r2": {}}}]
        await browser.say({"type": "undo", "token": "k1", "as": "k3"})
        assert (await browser.heard("refused"))["code"] == "forgotten"
        await browser.leave()
    assert not live.books


async def test_a_row_put_into_a_calculated_column_computes_what_is_typed_beside_it(live):
    cookie = await session_cookie()
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Iznosi")
    tab = await Tab.objects.acreate(document=document, position=0)
    grid = Grid(["r1", "r2", "r3"], ["a", "b", "c"])
    cells = [light_cell("r2:a", "3"), light_cell("r2:b", "1,5"), light_cell("r3:a", "2")]
    await afill(tab, [Block("table", "t", grid=grid, cells=cells)])
    user = await User.objects.aget(email="ivo@example.com")
    await Grant.objects.acreate(node=document, user=user, role=Role.OWN)
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg)
        assert await browser.answer() == {"type": "websocket.accept"}
        await browser.say({"type": "watch", "tab": str(tab.pk)})
        await browser.heard("grids")
        await browser.say({"type": "rows", "table": "t", "spans": [[0, 2]]})
        await browser.heard("rows")

        async def done(token: str, *operations: dict) -> dict:
            """The values the browser hears computed once the operations are done."""
            message = {"type": "do", "token": token, "tab": str(tab.pk), "operations": operations}
            await browser.say({**message, "operations": list(operations)})
            await browser.heard("patch")
            assert await browser.heard("done") == {"type": "done", "token": token}
            while "values" not in (patch := (await browser.heard("patch"))["patches"][0]):
                pass
            return patch["values"]

        def number(text: str) -> dict:
            return {"text": text, "kind": "number"}

        formulas = [
            {"row": row, "col": "c", "formula": f"A{y}*B{y}"} for y, row in ((2, "r2"), (3, "r3"))
        ]
        values = await done("k1", {"op": "cells", "table": "t", "cells": formulas})
        assert values["r2"]["c"] == number("4,5")
        lines = {"op": "lines", "table": "t", "axis": "rows", "ids": ["n1"]}
        await browser.say({"type": "do", "token": "k2", "tab": str(tab.pk), "operations": [lines]})
        put = (await browser.heard("patch"))["patches"][0]["rows"]["put"]
        assert put == [["n1", 3, None, None]]
        assert await browser.heard("done") == {"type": "done", "token": "k2"}
        await browser.say({"type": "rows", "table": "t", "spans": [[0, 3]]})
        told = await browser.heard("rows")
        assert told["rows"].keys() == {"n1"} and told["at"]["n1"] == 3
        held = told["rows"]["n1"]
        assert held["cells"] == {"c": {"formula": "=A4*B4"}}
        # The row computed by then is told with its cells, else by the patch that follows.
        if not held["values"]:
            while "values" not in (patch := (await browser.heard("patch"))["patches"][0]):
                pass
            held = patch["values"]["n1"]
        assert held["values" if "values" in held else "c"] in (number("0"), {"c": number("0")})
        typed = {"op": "cells", "table": "t", "cells": [{"row": "n1", "col": "a", "value": "4"}]}
        assert (await done("k3", typed))["n1"] == {"a": number("4"), "c": number("0")}
        typed = {"op": "cells", "table": "t", "cells": [{"row": "n1", "col": "b", "value": "2"}]}
        values = await done("k4", typed)
        assert values["n1"] == {"a": number("4"), "b": number("2"), "c": number("8")}
        await browser.leave()


async def test_lines_put_in_and_reordered_are_told_by_where_they_stand(live):
    cookie = await session_cookie()
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Redovi")
    tab = await Tab.objects.acreate(document=document, position=0)
    grid = Grid(["r1", "r2", "r3"], ["a"])
    await afill(tab, [Block("table", "t", grid=grid, cells=[light_cell("r3:a", "3")])])
    user = await User.objects.aget(email="ivo@example.com")
    await Grant.objects.acreate(node=document, user=user, role=Role.OWN)
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg)
        assert await browser.answer() == {"type": "websocket.accept"}
        await browser.say({"type": "watch", "tab": str(tab.pk)})
        await browser.heard("grids")
        await browser.say({"type": "rows", "table": "t", "spans": [[0, 2]]})
        await browser.heard("rows")
        operations = [
            {"op": "lines", "table": "t", "axis": "rows", "ids": ["n1"], "before": "r1"},
            {"op": "order", "table": "t", "col": "a", "from": "r2", "to": "r3"},
        ]
        message = {"type": "do", "token": "k1", "tab": str(tab.pk), "operations": operations}
        await browser.say(message)
        patches = (await browser.heard("patch"))["patches"]
        assert [patch["rows"] for patch in patches if "rows" in patch] == [
            {"put": [["n1", 0, None, None]]},
            {"order": [2, ["r3", "r2"]]},
        ]
        assert patches[-1]["at"] == {"n1": 0, "r2": 3}
        assert await browser.heard("done") == {"type": "done", "token": "k1"}
        await browser.say({"type": "undo", "token": "k1", "as": "k2"})
        patches = (await browser.heard("patch"))["patches"]
        assert [patch["rows"] for patch in patches if "rows" in patch] == [
            {"order": [2, ["r2", "r3"]]},
            {"out": [0]},
        ]
        await browser.leave()


async def relaid(browser: Browser) -> list[dict]:
    """The patches of the next patch that lays the table out anew, past those of values."""
    while "laid" not in (patches := (await browser.heard("patch"))["patches"])[0]:
        pass
    return patches


async def test_a_user_sees_the_rows_their_filter_shows_in_each_browser_and_edits_only_those(
    live,
):
    cookie = await session_cookie()
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Pića")
    tab = await Tab.objects.acreate(document=document, position=0)
    texts = {"r1": "kava", "r2": "sok", "r3": "kava", "r4": "kava", "r5": "čaj", "r6": "kava"}
    cells = [light_cell(f"{row}:a", text) for row, text in texts.items()]
    table = Block("table", "t", {"hidden": {"rows": ["r4"]}}, grid=Grid(list(texts), ["a"]))
    await afill(tab, [replace(table, cells=cells)])
    user = await User.objects.aget(email="ivo@example.com")
    await Grant.objects.acreate(node=document, user=user, role=Role.OWN)
    async with create_task_group() as tg:
        browser, other = Browser(document, cookie, tg), Browser(document, cookie, tg)
        for each in (browser, other):
            assert await each.answer() == {"type": "websocket.accept"}
            await each.say({"type": "watch", "tab": str(tab.pk)})
            [laid] = (await each.heard("grids"))["grids"]
            assert "rows" not in laid["hidden"]
            assert (laid["rows"], laid["at"], laid["numbers"]) == (
                5,
                {"r1": 0, "r6": 4},
                {"r1": 0, "r6": 5},
            )
        await browser.say({"type": "values", "table": "t", "col": "a"})
        assert await browser.heard("values") == {
            "type": "values",
            "table": "t",
            "col": "a",
            "values": [["čaj", 1], ["kava", 3], ["sok", 1]],
            "more": False,
        }
        kava = [{"col": "a", "values": ["kava"]}]
        await browser.say({"type": "filter", "table": "t", "conditions": kava})
        for each in (browser, other):
            [laid] = (await each.heard("patch"))["patches"]
            assert (laid["laid"]["rows"], laid["laid"]["numbers"]) == (3, {"r1": 0, "r6": 5})
        await browser.say({"type": "filter", "table": "t", "conditions": [{"col": "x"}]})
        assert (await browser.heard("unfiltered"))["code"] == "col"
        await browser.say({"type": "rows", "table": "t", "spans": [[0, 9]]})
        told = await browser.heard("rows")
        assert told["at"] == {"r1": 0, "r3": 1, "r6": 2}
        assert told["numbers"] == {"r1": 0, "r3": 2, "r6": 5}
        asked = {"type": "standing", "table": "t", "places": [2], "rows": [], "numbered": [1, 2]}
        await browser.say(asked)
        assert await browser.heard("standing") == asked | {
            "at": {"r3": 1, "r6": 2},
            "numbers": {"r3": 2, "r6": 5},
            "named": {"1": "r2", "2": "r3"},
        }
        typed = {"op": "cells", "table": "t", "cells": [{"row": "r3", "col": "a", "value": "voda"}]}
        message = {"type": "do", "tab": str(tab.pk)}
        await browser.say(message | {"token": "k1", "operations": [typed]})
        patches = await relaid(browser)
        assert patches[0]["laid"]["rows"] == 2
        assert patches[1]["cells"] == {"r3": {"a": {"text": "voda"}}}
        assert await browser.heard("done") == {"type": "done", "token": "k1"}
        hide = {"op": "lines", "table": "t", "axis": "rows", "from": "r1", "to": "r2"}
        await browser.say(message | {"token": "k2", "operations": [hide | {"hidden": True}]})
        assert (await relaid(browser))[0]["laid"]["rows"] == 1
        await browser.heard("done")
        taken = hide | {"from": "r2", "to": "r6", "remove": True}
        await browser.say(message | {"token": "k3", "operations": [taken]})
        assert (await relaid(browser))[0]["laid"]["rows"] == 0
        await browser.heard("done")
        await browser.say({"type": "filter", "table": "t", "conditions": []})
        laid = (await relaid(browser))[0]["laid"]
        assert (laid["rows"], laid["numbers"]) == (3, {"r2": 1, "r5": 4})
        await other.leave()
        await browser.leave()


async def test_a_browser_is_sent_each_look_once_before_what_names_it_by_key(live):
    cookie = await session_cookie()
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Cijene")
    tab = await Tab.objects.acreate(document=document, position=0)
    bold, centred = {"marks": {"strong": {}}}, {"attrs": {"align": "center"}}
    grid = Grid(["r1", "r2"], ["a", "b"], col_looks={"b": bold})
    cells = [light_cell("r1:a", "x", centred), light_cell("r1:b", "y", bold)]
    await afill(tab, [Block("table", "t", grid=grid, cells=cells)])
    user = await User.objects.aget(email="ivo@example.com")
    await Grant.objects.acreate(node=document, user=user, role=Role.OWN)
    keys = {name: grids.look(each).key for name, each in (("bold", bold), ("centred", centred))}
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg)
        assert await browser.answer() == {"type": "websocket.accept"}
        await browser.say({"type": "watch", "tab": str(tab.pk)})
        assert await browser.heard("looks") == {"type": "looks", "looks": {keys["bold"]: bold}}
        [outline] = (await browser.heard("grids"))["grids"]
        assert outline["looks"] == {"cols": {"b": keys["bold"]}}
        await browser.say({"type": "rows", "table": "t", "spans": [[0, 0]]})
        assert await browser.heard("looks") == {
            "type": "looks",
            "looks": {keys["centred"]: centred},
        }
        assert (await browser.heard("rows"))["rows"]["r1"]["cells"] == {
            "a": {"text": "x", "look": keys["centred"]},
            "b": {"text": "y"},
        }
        await browser.say({"type": "rows", "table": "t", "spans": [[1, 1]]})
        await browser.heard("rows")
        await browser.say({"type": "watch", "tab": str(tab.pk)})
        await browser.heard("grids")
        assert not [each for each in browser.log if each["type"] == "looks"]
        await browser.leave()


async def test_a_merge_is_told_to_every_watcher_of_the_tab_and_its_undo_too(live):
    cookie = await session_cookie()
    document, tab = await priced(Role.OWN)
    async with create_task_group() as tg:
        browser, other = Browser(document, cookie, tg), Browser(document, cookie, tg)
        for each in (browser, other):
            assert await each.answer() == {"type": "websocket.accept"}
            await each.say({"type": "watch", "tab": str(tab.pk)})
            await each.heard("grids")
        await browser.say({"type": "rows", "table": "t", "spans": [[0, 1]]})
        await browser.heard("rows")
        span = {"row": "r1", "col": "a", "span": {"rows": 2}}
        cells = {"op": "cells", "table": "t", "cells": [span]}
        await browser.say({"type": "do", "token": "k1", "tab": str(tab.pk), "operations": [cells]})
        told = (await browser.heard("patch"))["patches"]
        assert told == [
            {
                "table": "t",
                "cells": {"r1": {"a": {"text": "1.250,5", "to": "r2:a"}}},
                "merges": {"r1:a": "r2:a"},
                "at": {"r1": 0, "r2": 1},
            }
        ]
        assert (await other.heard("patch"))["patches"] == [
            {"table": "t", "merges": {"r1:a": "r2:a"}, "at": {"r1": 0, "r2": 1}}
        ]
        await browser.heard("done")
        await other.say({"type": "watch", "tab": str(tab.pk)})
        [grid] = (await other.heard("grids"))["grids"]
        assert grid["merges"] == {"r1:a": "r2:a"}
        await browser.say({"type": "undo", "token": "k1", "as": "k2"})
        merges = {"r1:a": None}
        assert (await other.heard("patch"))["patches"] == [
            {"table": "t", "merges": merges, "at": {"r1": 0}}
        ]
        await browser.leave()
        await other.leave()


async def test_rows_frozen_are_told_to_every_watcher_and_freed_by_the_undo(live):
    cookie = await session_cookie()
    document, tab = await priced(Role.OWN)
    async with create_task_group() as tg:
        browser, other = Browser(document, cookie, tg), Browser(document, cookie, tg)
        for each in (browser, other):
            assert await each.answer() == {"type": "websocket.accept"}
            await each.say({"type": "watch", "tab": str(tab.pk)})
            await each.heard("grids")
        frozen = {"op": "grid", "table": "t", "frozen": "r1"}
        await browser.say({"type": "do", "token": "k1", "tab": str(tab.pk), "operations": [frozen]})
        frozen = {"table": "t", "frozen": "r1", "at": {"r1": 0}}
        assert (await browser.heard("patch"))["patches"] == [frozen]
        assert (await other.heard("patch"))["patches"] == [frozen]
        await browser.heard("done")
        await other.say({"type": "watch", "tab": str(tab.pk)})
        [grid] = (await other.heard("grids"))["grids"]
        assert grid["frozen"] == "r1"
        await browser.say({"type": "undo", "token": "k1", "as": "k2"})
        assert (await other.heard("patch"))["patches"] == [{"table": "t", "frozen": None}]
        await browser.leave()
        await other.leave()


async def test_an_edit_sent_again_is_done_once_and_one_behind_the_room_is_refused(
    live, monkeypatch
):
    cookie = await session_cookie()
    document, tab = await priced(Role.OWN)
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg)
        assert await browser.answer() == {"type": "websocket.accept"}
        await browser.say({"type": "watch", "tab": str(tab.pk)})
        await browser.heard("grids")
        await browser.say({"type": "rows", "table": "t", "spans": [[1, 1]]})
        await browser.heard("rows")
        cells = {"op": "cells", "table": "t", "cells": [{"row": "r2", "col": "a", "value": 3}]}
        do = {"type": "do", "token": "k1", "tab": str(tab.pk), "operations": [cells]}
        await browser.say(do)
        assert (await browser.heard("patch"))["by"] == "k1"
        assert await browser.heard("done") == {"type": "done", "token": "k1"}
        await browser.say(do)
        assert await browser.heard("done") == {"type": "done", "token": "k1"}
        undo = {"type": "undo", "token": "k1", "as": "k2"}
        await browser.say(undo)
        assert await browser.heard("done") == {"type": "done", "token": "k1"}
        await browser.say(undo)
        assert await browser.heard("done") == {"type": "done", "token": "k1"}
        assert [each["by"] for each in browser.log if each["type"] == "patch" and "by" in each] == [
            "k2"
        ]
        monkeypatch.setattr("apps.collab.server.BEHIND", 0.05)
        for after, code in (([12345, 1], "behind"), (["x", 1], "invalid")):
            await browser.say({**do, "token": "k3", "after": after})
            refused = await browser.heard("refused")
            assert (refused["token"], refused["code"]) == ("k3", code)
        await browser.leave()
    assert await Tab.objects.filter(pk=tab.pk, grids__table="t").aexists()


async def test_a_table_made_while_a_browser_watches_is_its_tabs_and_takes_edits_at_once(live):
    cookie = await session_cookie()
    document, tab = await priced(Role.OWN)
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg)
        assert await browser.answer() == {"type": "websocket.accept"}
        await browser.say({"type": "watch", "tab": str(tab.pk)})
        await browser.heard("grids")
        table = {"op": "table", "at": {"end": "body"}, "id": "u", "rows": [["1"]]}
        await browser.say({"type": "do", "token": "k1", "tab": str(tab.pk), "operations": [table]})
        [made] = (await browser.heard("patch"))["patches"]
        assert (made["table"], made["made"]["name"], made["made"]["rows"]) == ("u", "", 1)
        assert made["tab"] == str(tab.pk)
        assert await browser.heard("done") == {"type": "done", "token": "k1"}
        await browser.say({"type": "rows", "table": "u", "spans": [[0, 0]]})
        [row] = (await browser.heard("rows"))["at"]
        [col] = [id for id, _ in made["made"]["cols"]]
        cells = {"op": "cells", "table": "u", "cells": [{"row": row, "col": col, "value": 2}]}
        await browser.say({"type": "do", "token": "k2", "tab": str(tab.pk), "operations": [cells]})
        assert await browser.heard("done") == {"type": "done", "token": "k2"}
        await browser.leave()
    assert await Tab.objects.filter(pk=tab.pk, grids__table="u").aexists()


async def test_a_browser_asks_whether_a_table_is_referred_to_by_its_name(live):
    cookie = await session_cookie()
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Cijene")
    tab = await Tab.objects.acreate(document=document, position=0)
    pointed = {"table": "t", "from": {"row": "r", "col": "c"}}
    await afill(
        tab,
        [
            Block("table", "t", {"name": "Iznosi"}, grid=Grid(["r"], ["c"])),
            Block("table", "s", grid=Grid(["r"], ["c"], formulas={"r:c": ["2*", pointed]})),
        ],
    )
    user = await User.objects.aget(email="ivo@example.com")
    await Grant.objects.acreate(node=document, user=user, role=Role.OWN)
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg)
        assert await browser.answer() == {"type": "websocket.accept"}
        await browser.say({"type": "watch", "tab": str(tab.pk)})
        await browser.heard("grids")
        for table, referred in [("t", True), ("s", False)]:
            await browser.say({"type": "referred", "table": table})
            assert await browser.heard("referred") == {
                "type": "referred",
                "table": table,
                "referred": referred,
            }
        await browser.leave()


async def test_a_formula_names_a_table_of_another_tab_and_follows_it_renamed(live):
    cookie = await session_cookie()
    document = await Node.objects.acreate(kind=Node.Kind.DOCUMENT, title="Cijene")
    first = await Tab.objects.acreate(document=document, position=0)
    second = await Tab.objects.acreate(document=document, position=1)
    await afill(first, [Block("table", "t1", grid=Grid(["r1"], ["a"]))])
    entry = Block(
        "table", "t2", {"name": "Ulaz"}, grid=Grid(["r1"], ["a"]), cells=[light_cell("r1:a", "4")]
    )
    await afill(second, [entry])
    user = await User.objects.aget(email="ivo@example.com")
    await Grant.objects.acreate(node=document, user=user, role=Role.OWN)
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg)
        assert await browser.answer() == {"type": "websocket.accept"}
        await browser.say({"type": "watch", "tab": str(first.pk)})
        assert await browser.heard("tables") == {
            "type": "tables",
            "tables": [["t2", "Ulaz", 1, 1, str(second.pk)]],
        }
        assert await browser.heard("names") == {"type": "names", "names": []}
        await browser.say({"type": "where", "name": "Ulaz", "table": "t1"})
        assert await browser.heard("where") == {
            "type": "where",
            "name": "Ulaz",
            "table": "t1",
            "at": None,
        }
        assert [each["table"] for each in (await browser.heard("grids"))["grids"]] == ["t1"]
        await browser.say({"type": "rows", "table": "t1", "spans": [[0, 0]]})
        await browser.heard("rows")

        async def do(token: str, tab: Tab, operation: dict) -> dict:
            await browser.say(
                {"type": "do", "token": token, "tab": str(tab.pk), "operations": [operation]}
            )
            return await browser.heard("refused" if operation["op"] == "grid" else "done")

        formula = {"row": "r1", "col": "a", "formula": "ulaz!A1*2"}
        await do("k1", first, {"op": "cells", "table": "t1", "cells": [formula]})
        patch = await browser.heard("patch")
        while not any("values" in each for each in patch["patches"]):
            patch = await browser.heard("patch")
        eight = {"text": "8", "kind": "number"}
        assert patch["patches"] == [{"table": "t1", "values": {"r1": {"a": eight}}}]
        renamed = await do("k2", first, {"op": "grid", "table": "t1", "name": "ULAZ"})
        assert (renamed["token"], renamed["code"]) == ("k2", "name_taken")
        await browser.say(
            {
                "type": "do",
                "token": "k3",
                "tab": str(second.pk),
                "operations": [{"op": "grid", "table": "t2", "name": "Izlaz"}],
            }
        )
        assert await browser.heard("done") == {"type": "done", "token": "k3"}
        assert await browser.heard("tables") == {
            "type": "tables",
            "tables": [["t2", "Izlaz", 1, 1, str(second.pk)]],
        }
        while (patch := await browser.heard("patch")).get("by") != "k3":
            pass
        assert patch["patches"] == [
            {"table": "t1", "cells": {"r1": {"a": {"formula": "=Izlaz!A1*2"}}}}
        ]
        await browser.leave()
    row = (await database(grids.of_document)(document))["t1"].row("r1")
    pointed = {"table": "t2", "from": {"row": "r1", "col": "a"}}
    assert (row.cells, row.values) == ({"a": {"formula": [pointed, "*2"]}}, {"a": 8.0})


async def test_a_reader_watches_but_its_edits_are_refused(live):
    cookie = await session_cookie()
    document, tab = await priced(Role.READ)
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg)
        assert await browser.answer() == {"type": "websocket.accept"}
        await browser.say({"type": "watch", "tab": str(tab.pk)})
        assert [grid["table"] for grid in (await browser.heard("grids"))["grids"]] == ["t"]
        cells = {"op": "cells", "table": "t", "cells": [{"row": "r2", "col": "a", "value": 1}]}
        await browser.say({"type": "do", "token": "k1", "tab": str(tab.pk), "operations": [cells]})
        refused = await browser.heard("refused")
        assert (refused["token"], refused["code"]) == ("k1", "read_only")
        await browser.leave()


async def test_a_browser_without_a_grant_is_closed_once_accepted(live):
    cookie = await session_cookie()
    document, _ = await priced(Role.OWN)
    await Grant.objects.filter(node=document).adelete()
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg)
        assert await browser.answer() == {"type": "websocket.accept"}
        assert await browser.answer() == {"type": "websocket.close", "code": REFUSED}


async def test_a_browser_from_elsewhere_is_refused(live):
    cookie = await session_cookie()
    document, _ = await priced(Role.OWN)
    async with create_task_group() as tg:
        browser = Browser(document, cookie, tg, "https://elsewhere.example")
        assert await browser.answer() == {"type": "websocket.close"}
