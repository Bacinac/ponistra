import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("access", "0004_outside_links"),
        ("blobs", "0005_pages"),
        ("chat", "0007_threads"),
        ("documents", "0029_favourites"),
        ("meetings", "0005_guest_read"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="meeting",
            field=models.ForeignKey(
                null=True,
                on_delete=models.DB_SET_NULL,
                related_name="+",
                to="meetings.meeting",
            ),
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
                ("position", models.PositiveSmallIntegerField()),
                ("name", models.CharField(max_length=255)),
                (
                    "blob",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="chat_attachments",
                        to="blobs.blob",
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        on_delete=models.DB_CASCADE,
                        related_name="attachments",
                        to="chat.message",
                    ),
                ),
                (
                    "node",
                    models.ForeignKey(
                        null=True,
                        on_delete=models.DB_SET_NULL,
                        related_name="+",
                        to="documents.node",
                    ),
                ),
            ],
            options={
                "ordering": ["position"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("message", "position"), name="one_attachment_a_place"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("blob__isnull", True), ("node__isnull", True), _connector="OR"),
                        name="attachment_of_one_source",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Given",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "conversation",
                    models.ForeignKey(
                        on_delete=models.DB_CASCADE,
                        related_name="given",
                        to="chat.conversation",
                    ),
                ),
                (
                    "grant",
                    models.ForeignKey(
                        on_delete=models.DB_CASCADE, related_name="+", to="access.grant"
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("conversation", "grant"), name="given_once")
                ],
            },
        ),
    ]
