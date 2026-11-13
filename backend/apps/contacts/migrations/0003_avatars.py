from django.db import migrations, models

from apps.blobs import store
from apps.contacts.cards import avatar


def drawn(apps, schema_editor):
    Contact = apps.get_model("contacts", "Contact")
    pictured = list(Contact.objects.exclude(photo=None).select_related("photo"))
    for each in pictured:
        each.avatar = avatar(store.path_of(each.photo.sha256))
    Contact.objects.bulk_update(pictured, ["avatar"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("contacts", "0002_addresses_in_lower_case")]

    operations = [
        migrations.AddField(
            model_name="contact", name="avatar", field=models.BinaryField(null=True)
        ),
        migrations.RunPython(drawn, migrations.RunPython.noop),
    ]
