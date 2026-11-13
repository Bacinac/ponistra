"""A collection's months, by the date its messages came in the installation's time, the moment
each is sent on, and the folders its files go into."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from apps.documents.models import Node
from apps.documents.views import created

from .models import Collection, Month

ZONE = ZoneInfo(settings.TIME_ZONE)


def first_of(moment: datetime) -> date:
    return moment.astimezone(ZONE).date().replace(day=1)


def following(month: date) -> date:
    return (month + timedelta(days=32)).replace(day=1)


def moment_of(collection: Collection, month: date) -> datetime:
    """When the month's files go: on the collection's day and hour of the month after it."""
    after = following(month)
    return datetime(after.year, after.month, collection.day, collection.hour, tzinfo=ZONE)


def started(given: date) -> datetime:
    return datetime(given.year, given.month, given.day, tzinfo=ZONE)


def month_for(collection: Collection, moment: datetime) -> Month:
    """The month the moment falls in; one whose day came before the collection was made waits
    for its owner to send it."""
    month = first_of(moment)
    return Month.objects.get_or_create(
        collection=collection,
        month=month,
        defaults={"past": moment_of(collection, month) <= collection.created_at},
    )[0]


def touched(collection_id: int) -> None:
    """Tells the owner's pages that what the collection shows changed."""
    Collection.objects.filter(pk=collection_id).update(changed_at=timezone.now())


def _live(node: Node | None) -> bool:
    return node is not None and node.is_live()


def folder_of(collection: Collection) -> Node:
    """The folder the collection keeps its months in, made again at the top of the owner's
    documents when it is gone."""
    if not _live(collection.folder):
        collection.folder = created(
            None, Node.Kind.FOLDER, collection.name[:200], None, collection.owner
        )
        Collection.objects.filter(pk=collection.pk).update(folder=collection.folder)
    return collection.folder


def folder_for(month: Month) -> Node:
    """The month's folder in the collection's, made again when it is gone."""
    if not _live(month.folder):
        parent = folder_of(month.collection)
        month.folder = created(
            parent, Node.Kind.FOLDER, f"{month.month:%Y-%m}", None, month.collection.owner
        )
        Month.objects.filter(pk=month.pk).update(folder=month.folder)
    return month.folder
