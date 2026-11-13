import django.contrib.postgres.indexes
import django.contrib.postgres.search
from django.db import migrations, models

import apps.search.text

# Each person as a name and an address, the address also in its parts, which the parser
# otherwise keeps as one word.
PEOPLE = """
CREATE FUNCTION calendar_people(people jsonb) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
RETURN (
    SELECT coalesce(string_agg(concat_ws(' ',
        person ->> 'name', person ->> 'email', translate(person ->> 'email', '@.', '  ')
    ), ' '), '')
    FROM jsonb_array_elements(
        CASE jsonb_typeof(people) WHEN 'array' THEN people ELSE jsonb_build_array(people) END
    ) AS found(person)
)
"""

WORDS = """
CREATE FUNCTION calendar_words(
    summary text, location text, organizer jsonb, attendees jsonb, description text
)
RETURNS tsvector
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
RETURN setweight(to_tsvector('hr'::regconfig, summary), 'A')
    || setweight(to_tsvector('hr'::regconfig,
        concat_ws(' ', location, calendar_people(organizer), calendar_people(attendees))), 'B')
    || setweight(to_tsvector('hr'::regconfig, left(description, 131072)), 'D')
"""


class Migration(migrations.Migration):

    dependencies = [
        ("calendar", "0004_resources"),
        ("search", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(PEOPLE, "DROP FUNCTION calendar_people(jsonb)"),
        migrations.RunSQL(
            WORDS, "DROP FUNCTION calendar_words(text, text, jsonb, jsonb, text)"
        ),
        migrations.AddField(
            model_name="event",
            name="words",
            field=models.GeneratedField(
                db_persist=True,
                expression=apps.search.text.EventWords(
                    "summary", "location", "organizer", "attendees", "description"
                ),
                output_field=django.contrib.postgres.search.SearchVectorField(),
            ),
        ),
        migrations.AddIndex(
            model_name="event",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["words"], name="calendar_event_words"
            ),
        ),
        migrations.AddIndex(
            model_name="event",
            index=django.contrib.postgres.indexes.GinIndex(
                django.contrib.postgres.indexes.OpClass(
                    apps.search.text.Folded("summary"), name="gin_trgm_ops"
                ),
                name="calendar_summary_trigrams",
            ),
        ),
    ]
