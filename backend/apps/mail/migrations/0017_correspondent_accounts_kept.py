from django.db import migrations

# The accounts of the mail kept so far, as `correspondents.noted` keeps them from now on.
SENT_FROM = """
UPDATE mail_correspondent c SET sent_from_id = latest.account_id
FROM (
    SELECT DISTINCT ON (m.owner_id, lower(person->>'address'))
        m.owner_id, lower(person->>'address') AS address, a.id AS account_id
    FROM mail_message m
    JOIN mail_folder f ON f.id = m.folder_id
    JOIN mail_account a
        ON a.owner_id = m.owner_id AND lower(a.address) = lower(m.sender->>'address')
    CROSS JOIN LATERAL jsonb_array_elements(m."to" || m.cc) AS person
    WHERE f.role NOT IN ('drafts', 'junk')
    ORDER BY m.owner_id, lower(person->>'address'), m.date DESC
) latest
WHERE c.owner_id = latest.owner_id AND c.address = latest.address
"""
REACHED = """
UPDATE mail_correspondent c SET reached_id = latest.account_id
FROM (
    SELECT DISTINCT ON (m.owner_id, lower(person->>'address'))
        m.owner_id, lower(person->>'address') AS address, m.account_id
    FROM mail_message m
    JOIN mail_folder f ON f.id = m.folder_id
    CROSS JOIN LATERAL jsonb_array_elements(jsonb_build_array(m.sender) || m.reply_to) AS person
    WHERE f.role NOT IN ('drafts', 'junk') AND m.account_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM mail_account a
            WHERE a.owner_id = m.owner_id AND lower(a.address) = lower(m.sender->>'address')
        )
    ORDER BY m.owner_id, lower(person->>'address'), m.date DESC
) latest
WHERE c.owner_id = latest.owner_id AND c.address = latest.address
"""


class Migration(migrations.Migration):
    dependencies = [("mail", "0016_correspondent_accounts")]

    operations = [
        migrations.RunSQL(SENT_FROM, migrations.RunSQL.noop),
        migrations.RunSQL(REACHED, migrations.RunSQL.noop),
    ]
