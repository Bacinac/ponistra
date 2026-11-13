from django.db import migrations


def worded(apps, schema_editor):
    """The way in online of the events that gave it only in their words."""
    from apps.calendar.ical import meeting_in
    from apps.calendar.models import revised

    Event = apps.get_model("calendar", "Event")
    changed = set()
    for event in Event.objects.filter(conference="").only(
        "pk", "master_id", "location", "description"
    ):
        if link := meeting_in(event.location, event.description):
            Event.objects.filter(pk=event.pk).update(conference=link)
            changed |= {event.pk, event.master_id or event.pk}
    Event.objects.filter(pk__in=changed).update(revision=revised())


class Migration(migrations.Migration):
    dependencies = [("calendar", "0010_workdays")]

    operations = [migrations.RunPython(worded, migrations.RunPython.noop)]
