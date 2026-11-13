"""What the text of a document's tab holds of its tables (D16): the ids of those that stand in
it, in its order, the text of each of their cells that has a node in the text, and the charts
drawn in it. A table whose block was taken out of the text keeps its grid, so bringing the
block back brings its cells, but it is computed no more and its name is free for another.

A live tab's text is followed as it changes; an idle tab's is read from its store."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from pycrdt import Doc, XmlElement, XmlFragment

from apps.collab.models import Update
from apps.documents.models import Tab

from . import blocks, charts
from .charts import Chart

TABLE = "table"


@dataclass(frozen=True)
class Placing:
    tables: list[str] = field(default_factory=list)
    nodes: dict[str, dict[str, str]] = field(default_factory=dict)
    charts: dict[str, Chart | None] = field(default_factory=dict)


def of(doc: Doc) -> Placing:
    return _held(blocks.body_of(doc))


def _held(body: XmlFragment) -> Placing:
    tables, nodes = [], {}
    for element in body.children:
        if isinstance(element, XmlElement) and element.tag == TABLE:
            id = element.attributes.get("id")
            if isinstance(id, str):
                tables.append(id)
                nodes[id] = blocks.node_texts(element)
    return Placing(tables, nodes, charts.charts_in(body))


def of_document(document) -> dict[str, Placing]:
    """What the text of each of the document's tabs that has tables holds, by tab, in the
    tabs' order, read from their stores."""
    found = {}
    tabs = (
        Tab.objects.filter(document=document, grids__isnull=False)
        .distinct()
        .order_by("position", "pk")
    )
    for tab, room in tabs.values_list("pk", "room"):
        state = Doc()
        for data in Update.objects.filter(room=room).order_by("id").values_list("data", flat=True):
            state.apply_update(bytes(data))
        found[str(tab)] = of(state)
    return found


def nodes_of(placings: dict[str, Placing]) -> dict[str, dict[str, str]]:
    """The tables standing in the tabs' texts, each with the text of its cells that have a
    node, in the tabs' order and each text's."""
    return {
        table: placing.nodes[table] for placing in placings.values() for table in placing.tables
    }


class Follower:
    """Follows a live tab's text: tells `told` what it holds as that changes, with the cells
    whose text changed, by table, and whether its tables or charts did."""

    def __init__(self, doc: Doc, told: Callable[[Placing, dict[str, set[str]], bool], None]):
        self.doc = doc
        self.told = told
        self.body = blocks.body_of(doc)
        self.placing = _held(self.body)
        self.subscription = self.body.observe_deep(self._changed)

    def _changed(self, events) -> None:
        before = self.placing
        # Within the observer the body is read as it is held: getting it from the doc again
        # would write to a transaction that only reads.
        if any(not event.path for event in events):
            self.placing = _held(self.body)
        else:
            nodes = dict(before.nodes)
            drawn = dict(before.charts)
            for event in events:
                element = self.body.children[event.path[0]]
                if not isinstance(element, XmlElement):
                    continue
                id = element.attributes.get("id")
                if element.tag == TABLE and id in nodes:
                    nodes[id] = blocks.node_texts(element)
                elif element.tag == charts.TAG and isinstance(id, str):
                    drawn[id] = charts.chart_of(dict(element.attributes))
            self.placing = replace(before, nodes=nodes, charts=drawn)
        texts, moved = compared(before, self.placing)
        if texts or moved:
            self.told(self.placing, texts, moved)

    def close(self) -> None:
        # A subscription may only be dropped on the thread that made it; kept past closing, it
        # would go with the follower wherever the collector happens to run.
        if self.subscription is not None:
            self.body.unobserve(self.subscription)
            self.subscription = None


def compared(before: Placing, now: Placing) -> tuple[dict[str, set[str]], bool]:
    """The cells whose text changed, by table standing before and now, and whether the tables
    standing or the charts did."""
    texts = {
        table: keys
        for table, nodes in now.nodes.items()
        if table in before.nodes
        and before.nodes[table] is not nodes
        and (keys := _changed(before.nodes[table], nodes))
    }
    return texts, before.tables != now.tables or before.charts != now.charts


def _changed(before: dict[str, str], now: dict[str, str]) -> set[str]:
    return {key for key in before.keys() | now.keys() if before.get(key) != now.get(key)}
