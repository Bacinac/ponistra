from django.db import migrations


def folders_again(apps, schema_editor):
    """An ActiveSync account connected before its calendars were taken reads its folders once
    more, to learn its folders of calendars: HCL Traveler keeps the state of those it synced."""
    apps.get_model("mail", "Account").objects.filter(protocol="activesync").update(folder_key="")


class Migration(migrations.Migration):
    dependencies = [
        ("calendar", "0001_calendars"),
        ("mail", "0011_correspondents"),
    ]

    operations = [
        migrations.RunPython(folders_again, migrations.RunPython.noop),
    ]
