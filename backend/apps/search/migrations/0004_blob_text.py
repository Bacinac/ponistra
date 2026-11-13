import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("blobs", "0001_initial"),
        ("search", "0003_ocr"),
    ]

    operations = [
        migrations.RenameModel("PdfText", "BlobText"),
        migrations.RenameModel("PdfPage", "BlobPage"),
        migrations.RemoveConstraint(model_name="blobpage", name="one_text_per_page"),
        migrations.RenameField("blobpage", "pdf", "source"),
        migrations.AddConstraint(
            model_name="blobpage",
            constraint=models.UniqueConstraint(
                fields=("source", "number"), name="one_text_per_page"
            ),
        ),
        migrations.RenameIndex("blobpage", new_name="blob_page_words", old_name="pdf_page_words"),
        migrations.AlterField(
            model_name="blobtext",
            name="blob",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.DB_CASCADE,
                primary_key=True,
                related_name="text",
                serialize=False,
                to="blobs.blob",
            ),
        ),
    ]
