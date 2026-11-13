import django.contrib.postgres.indexes
import django.contrib.postgres.search
import django.db.models.deletion
from django.db import migrations, models

COPY = """
INSERT INTO content_gridrowwords (grid_row_id, words) SELECT id, words FROM content_gridrow
"""

# Statement triggers with the rows they wrote, as a column of values is written in one
# statement. Every row written is queued, its cells changed or not: comparing them with the
# rows before costs the write more than reading the words again costs the background, which
# writes no index for words that came out the same.
STALE = """
CREATE FUNCTION grid_row_stale() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO content_stalegridrow (grid_row_id) SELECT id FROM fresh ON CONFLICT DO NOTHING;
    PERFORM pg_notify('grid_words', '');
    RETURN NULL;
END
$$;
CREATE TRIGGER grid_row_inserted AFTER INSERT ON content_gridrow
    REFERENCING NEW TABLE AS fresh FOR EACH STATEMENT EXECUTE FUNCTION grid_row_stale();
CREATE TRIGGER grid_row_updated AFTER UPDATE ON content_gridrow
    REFERENCING NEW TABLE AS fresh FOR EACH STATEMENT EXECUTE FUNCTION grid_row_stale();
"""

UNSTALE = """
DROP TRIGGER grid_row_updated ON content_gridrow;
DROP TRIGGER grid_row_inserted ON content_gridrow;
DROP FUNCTION grid_row_stale();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0008_shared"),
    ]

    operations = [
        migrations.RemoveIndex(model_name="gridrow", name="grid_row_words"),
        migrations.CreateModel(
            name="GridRowWords",
            fields=[
                (
                    "grid_row",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        primary_key=True,
                        related_name="+",
                        serialize=False,
                        to="content.gridrow",
                    ),
                ),
                ("words", django.contrib.postgres.search.SearchVectorField()),
            ],
            options={
                "indexes": [
                    django.contrib.postgres.indexes.GinIndex(
                        fields=["words"], name="grid_row_words"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="StaleGridRow",
            fields=[
                (
                    "grid_row",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.DB_CASCADE,
                        primary_key=True,
                        related_name="+",
                        serialize=False,
                        to="content.gridrow",
                    ),
                ),
            ],
        ),
        migrations.RunSQL(COPY, migrations.RunSQL.noop),
        migrations.RemoveField(model_name="gridrow", name="words"),
        migrations.RunSQL(STALE, UNSTALE),
    ]
