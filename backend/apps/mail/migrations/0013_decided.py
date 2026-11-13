import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mail', '0012_drafts'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(model_name='trusted', name='mail_trusted_once'),
        migrations.RenameModel(old_name='Trusted', new_name='Decided'),
        migrations.AlterField(
            model_name='decided',
            name='owner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.DB_CASCADE, related_name='mail_decided', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='decided',
            name='shown',
            field=models.BooleanField(default=True),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name='decided',
            constraint=models.UniqueConstraint(fields=('owner', 'domain'), name='mail_decided_once'),
        ),
    ]
