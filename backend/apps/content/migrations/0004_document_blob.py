import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0003_references_kept_by_the_database'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='documentimage',
            name='one_link_per_image',
        ),
        migrations.RenameModel(
            old_name='DocumentImage',
            new_name='DocumentBlob',
        ),
        migrations.AlterField(
            model_name='documentblob',
            name='blob',
            field=models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, related_name='shown_in', to='blobs.blob'),
        ),
        migrations.AlterField(
            model_name='documentblob',
            name='document',
            field=models.ForeignKey(on_delete=django.db.models.deletion.DB_CASCADE, related_name='shown', to='documents.node'),
        ),
        migrations.AddConstraint(
            model_name='documentblob',
            constraint=models.UniqueConstraint(fields=('document', 'blob'), name='one_link_per_blob'),
        ),
    ]
