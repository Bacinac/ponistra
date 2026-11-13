import django.contrib.postgres.indexes
from django.db import migrations

import apps.search.text


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0005_node_updated_by'),
        ('search', '0001_initial'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='node',
            index=django.contrib.postgres.indexes.GinIndex(apps.search.text.Words('title'), name='node_title_words'),
        ),
        migrations.AddIndex(
            model_name='node',
            index=django.contrib.postgres.indexes.GinIndex(django.contrib.postgres.indexes.OpClass(apps.search.text.Folded('title'), name='gin_trgm_ops'), name='node_title_trigrams'),
        ),
        migrations.AddIndex(
            model_name='tab',
            index=django.contrib.postgres.indexes.GinIndex(apps.search.text.Words('title'), name='tab_title_words'),
        ),
        migrations.AddIndex(
            model_name='tab',
            index=django.contrib.postgres.indexes.GinIndex(django.contrib.postgres.indexes.OpClass(apps.search.text.Folded('title'), name='gin_trgm_ops'), name='tab_title_trigrams'),
        ),
    ]
