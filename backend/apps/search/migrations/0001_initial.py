import django.contrib.postgres.indexes
import django.contrib.postgres.search
import django.db.models.deletion
from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations, models

import apps.search.text

# unaccent() alone is only stable, since it looks its dictionary up on the search
# path; naming the dictionary makes it safe to index.
FOLD = """
CREATE FUNCTION search_fold(text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
RETURN lower(public.unaccent('public.unaccent'::regdictionary, $1))
"""

# Postgres has no Croatian stemmer; the Serbian one reads Latin script, and folding
# accents first gives text typed without č, ć, đ, š, ž the same stems.
CONFIG = [
    "CREATE TEXT SEARCH CONFIGURATION hr (COPY = pg_catalog.serbian)",
    "ALTER TEXT SEARCH CONFIGURATION hr"
    " ALTER MAPPING FOR word, hword, hword_part WITH unaccent, serbian_stem",
]


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("blobs", "0001_initial"),
    ]

    operations = [
        UnaccentExtension(),
        TrigramExtension(),
        migrations.RunSQL(FOLD, "DROP FUNCTION search_fold(text)"),
        migrations.RunSQL(CONFIG, "DROP TEXT SEARCH CONFIGURATION hr"),
        migrations.CreateModel(
            name="PdfText",
            fields=[
                (
                    "blob",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="pdf_text",
                        serialize=False,
                        to="blobs.blob",
                    ),
                ),
                ("page_count", models.PositiveIntegerField()),
                ("failed", models.TextField(blank=True)),
                ("extracted_at", models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="PdfPage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("number", models.PositiveIntegerField()),
                ("text", models.TextField()),
                (
                    "words",
                    models.GeneratedField(
                        db_persist=True,
                        expression=apps.search.text.Words("text"),
                        output_field=django.contrib.postgres.search.SearchVectorField(),
                    ),
                ),
                (
                    "pdf",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pages",
                        to="search.pdftext",
                    ),
                ),
            ],
            options={
                "indexes": [
                    django.contrib.postgres.indexes.GinIndex(
                        fields=["words"], name="pdf_page_words"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("pdf", "number"), name="one_text_per_page")
                ],
            },
        ),
    ]
