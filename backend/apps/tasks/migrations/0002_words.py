import django.contrib.postgres.indexes
import django.contrib.postgres.search
from django.db import migrations, models

import apps.search.text

WORDS = """
CREATE FUNCTION tasks_words(text text, label text)
RETURNS tsvector
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
RETURN setweight(to_tsvector('hr'::regconfig, text), 'A')
    || setweight(to_tsvector('hr'::regconfig, label), 'B')
"""


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0001_initial"),
        ("search", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(WORDS, "DROP FUNCTION tasks_words(text, text)"),
        migrations.AddField(
            model_name="task",
            name="words",
            field=models.GeneratedField(
                db_persist=True,
                expression=apps.search.text.TaskWords("text", "source_label"),
                output_field=django.contrib.postgres.search.SearchVectorField(),
            ),
        ),
        migrations.AddIndex(
            model_name="task",
            index=django.contrib.postgres.indexes.GinIndex(fields=["words"], name="tasks_task_words"),
        ),
        migrations.AddIndex(
            model_name="task",
            index=django.contrib.postgres.indexes.GinIndex(
                django.contrib.postgres.indexes.OpClass(
                    apps.search.text.Folded("text"), name="gin_trgm_ops"
                ),
                name="tasks_text_trigrams",
            ),
        ),
    ]
