from email import policy
from email.parser import BytesHeaderParser

from django.db import migrations

GLOBAL_ID = "040000008200E00074C5B7101A82E00800000000646C6F747573C301000000000000000010000000"


def noticed(apps, schema_editor):
    """The notices of invitations Traveler delivered before they were kept as invitations."""
    from apps.blobs.store import path_of

    Message = apps.get_model("mail", "Message")
    Invitation = apps.get_model("calendar", "Invitation")
    taken = set(Invitation.objects.values_list("message_id", flat=True))
    parser = BytesHeaderParser(policy=policy.default)
    for message in Message.objects.filter(account__protocol="activesync").only(
        "pk", "owner_id", "raw_id"
    ):
        if message.pk in taken:
            continue
        with path_of(message.raw_id).open("rb") as raw:
            head = raw.read(64 * 1024).split(b"\r\n\r\n", 1)[0].split(b"\n\n", 1)[0]
        headers = parser.parsebytes(head)
        unid = str(headers.get("X-IBM-UNID", "")).strip().upper()
        if (
            headers.get("X-IBM-FORM") == "Notice"
            and str(headers.get("X-IBM-NOTICEICON", "")).strip() == "133"
            and len(unid) == 32
        ):
            Invitation.objects.create(
                owner_id=message.owner_id, message=message, method="request", uid=GLOBAL_ID + unid
            )


class Migration(migrations.Migration):
    dependencies = [
        ("calendar", "0006_followed"),
        ("mail", "0012_drafts"),
    ]

    operations = [migrations.RunPython(noticed, migrations.RunPython.noop)]
