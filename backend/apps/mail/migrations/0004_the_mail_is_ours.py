import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def taken_again(apps, schema_editor):
    """Every account's mail is taken again, whole: what was kept before held only what the
    provider has, most of it without the Message-ID that tells a message delivered twice."""
    apps.get_model("mail", "Account").objects.update(folder_key="", state="syncing", error="")


class Migration(migrations.Migration):
    dependencies = [
        ("blobs", "0001_initial"),
        ("mail", "0003_threads_and_colors"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(name="Copy"),
        migrations.DeleteModel(name="Message"),
        migrations.DeleteModel(name="Folder"),
        migrations.CreateModel(
            name="Folder",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=1000)),
                (
                    "role",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("inbox", "Inbox"),
                            ("sent", "Sent"),
                            ("drafts", "Drafts"),
                            ("archive", "Archive"),
                            ("junk", "Junk"),
                            ("trash", "Trash"),
                        ],
                        max_length=7,
                    ),
                ),
                (
                    "account",
                    models.OneToOneField(
                        null=True,
                        on_delete=django.db.models.deletion.DB_SET_NULL,
                        related_name="node",
                        to="mail.account",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="mail_folders",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="children",
                        to="mail.folder",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("owner", "parent", "name"),
                        name="mail_folder_once",
                        nulls_distinct=False,
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("role", ""), _negated=True),
                        fields=("owner", "role"),
                        name="mail_role_once",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Source",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=1000)),
                ("delimiter", models.CharField(blank=True, max_length=1)),
                (
                    "kind",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("inbox", "Inbox"),
                            ("sent", "Sent"),
                            ("drafts", "Drafts"),
                            ("archive", "Archive"),
                            ("junk", "Junk"),
                            ("trash", "Trash"),
                            ("all", "All"),
                        ],
                        max_length=7,
                    ),
                ),
                ("uidvalidity", models.PositiveBigIntegerField(null=True)),
                ("low", models.PositiveBigIntegerField(null=True)),
                ("high", models.PositiveBigIntegerField(null=True)),
                ("server_id", models.CharField(blank=True, max_length=64)),
                ("parent", models.CharField(blank=True, max_length=64)),
                ("sync_key", models.CharField(blank=True, max_length=64)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="sources",
                        to="mail.account",
                    ),
                ),
                (
                    "folder",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="sources",
                        to="mail.folder",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        deferrable=models.Deferrable["DEFERRED"],
                        fields=("account", "name"),
                        name="mail_source_once",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Message",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("key", models.CharField(max_length=64)),
                ("message_id", models.CharField(blank=True, max_length=998)),
                ("in_reply_to", models.CharField(blank=True, max_length=998)),
                ("references", models.TextField(blank=True)),
                ("subject", models.TextField(blank=True)),
                ("sender", models.JSONField(default=dict)),
                ("to", models.JSONField(default=list)),
                ("cc", models.JSONField(default=list)),
                ("reply_to", models.JSONField(default=list)),
                ("date", models.DateTimeField()),
                ("size", models.PositiveIntegerField(default=0)),
                ("attachments", models.BooleanField(default=False)),
                ("text", models.TextField(blank=True)),
                ("preview", models.CharField(blank=True, max_length=200)),
                ("seen", models.BooleanField(default=False)),
                ("flagged", models.BooleanField(default=False)),
                ("answered", models.BooleanField(default=False)),
                (
                    "account",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DB_SET_NULL,
                        related_name="messages",
                        to="mail.account",
                    ),
                ),
                (
                    "folder",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="messages",
                        to="mail.folder",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="mail_messages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "raw",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="mail",
                        to="blobs.blob",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["folder", "-date", "-id"], name="mail_message_newest"),
                    models.Index(
                        condition=models.Q(("seen", False)), fields=["folder"], name="mail_unseen"
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("owner", "key"), name="mail_message_once")
                ],
            },
        ),
        migrations.CreateModel(
            name="Arrival",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("uid", models.PositiveBigIntegerField(null=True)),
                ("item", models.CharField(blank=True, max_length=64)),
                (
                    "message",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="arrivals",
                        to="mail.message",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="arrivals",
                        to="mail.source",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("source", "uid"), name="mail_arrival_once"),
                    models.UniqueConstraint(
                        condition=models.Q(("item", ""), _negated=True),
                        fields=("source", "item"),
                        name="mail_item_once",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Attachment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("part", models.CharField(max_length=100)),
                ("name", models.CharField(blank=True, max_length=255)),
                ("type", models.CharField(max_length=255)),
                ("cid", models.CharField(blank=True, max_length=998)),
                ("inline", models.BooleanField(default=False)),
                ("offset", models.PositiveBigIntegerField(null=True)),
                ("line", models.PositiveIntegerField(null=True)),
                ("newline", models.CharField(blank=True, max_length=2)),
                ("ended", models.BooleanField(default=False)),
                (
                    "blob",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="mailed",
                        to="blobs.blob",
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="files",
                        to="mail.message",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("message", "part"), name="mail_attachment_once")
                ],
            },
        ),
        migrations.CreateModel(
            name="Deleted",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("key", models.CharField(max_length=64)),
                ("deleted_at", models.DateTimeField(auto_now_add=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="mail_deleted",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("owner", "key"), name="mail_deleted_once")
                ],
            },
        ),
        migrations.RunPython(taken_again, migrations.RunPython.noop),
    ]
