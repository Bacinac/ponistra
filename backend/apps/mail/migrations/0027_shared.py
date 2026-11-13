import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from apps.collab.changes import followed

# The tables the interface shows mail from, told about as their owner's: a colleague's own, or a
# shared mailbox's, which `sharing.concerned` resolves to those it is shared with.
OWNED = [
    "mail_account",
    "mail_folder",
    "mail_message",
    "mail_draft",
    "mail_unsent",
    "mail_signature",
    "mail_rule",
    "mail_key",
]


def _unfollowed(table: str) -> migrations.RunSQL:
    before = followed(table, "mail", "u:owner_id")
    return migrations.RunSQL(before.reverse_sql, before.sql)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("collab", "0006_changes"),
        ("mail", "0026_sealed"),
        ("users", "0011_mailbox"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Grant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[("read", "Read"), ("edit", "Edit"), ("own", "Own")], max_length=8
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.DB_SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="mail_grants",
                        to="auth.group",
                    ),
                ),
                (
                    "mailbox",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="mail_shared",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="mail_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("user__isnull", True), ("group__isnull", True), _connector="OR"
                        ),
                        name="mail_grant_has_one_grantee",
                    ),
                    models.UniqueConstraint(
                        fields=("mailbox", "user", "group"),
                        name="mail_grant_once",
                        nulls_distinct=False,
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name='Opening',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('at', models.DateTimeField()),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.DB_CASCADE, related_name='openings', to='mail.message')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.DB_CASCADE, related_name='mail_openings', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('message', 'user'), name='mail_opening_once')],
            },
        ),
        *[_unfollowed(table) for table in OWNED],
        *[followed(table, "mail", "m:owner_id") for table in OWNED],
        followed("mail_grant", "mail", "m:mailbox_id", "u:user_id", "g:group_id"),
    ]
