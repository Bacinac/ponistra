import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Exists, OuterRef, Q

from apps.collab.changes import followed

SIGNATURES = [
    "application/pkcs7-signature",
    "application/x-pkcs7-signature",
    "application/pgp-signature",
]
CARRIED = ["application/pkcs7-mime", "application/x-pkcs7-mime", "application/pgp-encrypted"]


def sealed(apps, schema_editor):
    """Messages taken before seals were known: their seal's parts were cut as files, which stay
    where `whole` puts them back but are no longer offered, and the message is marked sealed."""
    Message = apps.get_model("mail", "Message")
    Attachment = apps.get_model("mail", "Attachment")
    pgp = Attachment.objects.filter(type="application/pgp-encrypted").values("message")
    seals = Attachment.objects.filter(
        Q(type__in=SIGNATURES + CARRIED)
        | Q(type="application/octet-stream", name="encrypted.asc", message__in=pgp)
    )
    encrypted = Attachment.objects.filter(message=OuterRef("pk"), type__in=CARRIED)
    signed = Attachment.objects.filter(message=OuterRef("pk"), type__in=SIGNATURES)
    Message.objects.filter(Exists(encrypted)).update(sealed="encrypted")
    Message.objects.filter(Exists(signed), sealed="").update(sealed="signed")
    seals.update(inline=True)
    offered = Attachment.objects.filter(message=OuterRef("pk"), inline=False)
    Message.objects.exclude(sealed="").update(attachments=Exists(offered))


class Migration(migrations.Migration):
    dependencies = [
        ("mail", "0025_away"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="sealed",
            field=models.CharField(
                blank=True,
                choices=[("signed", "Signed"), ("encrypted", "Encrypted")],
                max_length=9,
            ),
        ),
        migrations.CreateModel(
            name="Key",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "kind",
                    models.CharField(choices=[("smime", "Smime"), ("pgp", "Pgp")], max_length=5),
                ),
                ("address", models.CharField(max_length=320)),
                ("fingerprint", models.CharField(max_length=64)),
                ("data", models.BinaryField()),
                ("own", models.BooleanField(default=False)),
                ("expires_at", models.DateTimeField(null=True)),
                ("seen_at", models.DateTimeField()),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        related_name="mail_keys",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["address", "kind"], name="mail_key_address")],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("owner", "kind", "address", "fingerprint"), name="mail_key_once"
                    )
                ],
            },
        ),
        followed("mail_key", "mail", "u:owner_id"),
        migrations.RunPython(sealed, migrations.RunPython.noop),
    ]
