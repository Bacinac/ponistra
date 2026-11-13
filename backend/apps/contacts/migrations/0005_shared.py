from django.db import migrations

from apps.collab.changes import followed

# Told about as their owner's: a colleague's own, or a shared mailbox's, which
# `sharing.concerned` resolves to those it is shared with.
OWNED = ["contacts_contact", "contacts_gone"]


def _unfollowed(table: str) -> migrations.RunSQL:
    before = followed(table, "contacts", "u:owner_id")
    return migrations.RunSQL(before.reverse_sql, before.sql)


class Migration(migrations.Migration):
    dependencies = [
        ("contacts", "0004_favourites"),
        ("collab", "0006_changes"),
        ("mail", "0027_shared"),
    ]

    operations = [
        *[_unfollowed(table) for table in OWNED],
        *[followed(table, "contacts", "m:owner_id") for table in OWNED],
    ]
