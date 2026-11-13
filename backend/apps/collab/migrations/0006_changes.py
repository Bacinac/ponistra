from django.db import migrations

from apps.collab.changes import followed

FOLLOWED = {
    "contacts_contact": ("contacts", "u:owner_id"),
    "contacts_gone": ("contacts", "u:owner_id"),
    "calendar_calendar": ("calendar", "u:owner_id"),
    "calendar_event": ("calendar", "k:calendar_id"),
    "calendar_gone": ("calendar", "u:owner_id"),
    "calendar_invitation": ("calendar", "u:owner_id"),
    "calendar_workdays": ("calendar", "*"),
    "calendar_closure": ("calendar", "*"),
    "tasks_task": ("tasks", "u:owner_id"),
    "documents_node": ("nodes", "n:id", "n:parent_id"),
    "versions_version": ("nodes", "n:document_id"),
    "versions_fileversion": ("nodes", "n:node_id"),
    "access_grant": ("nodes", "n:node_id", "u:user_id", "g:group_id"),
    "access_access": ("nodes", "u:user_id"),
    "shares_share": ("nodes", "n:folder_id"),
    "vault_vault": ("vault", "u:user_id"),
    "vault_collection": ("vault", "c:id"),
    "vault_member": ("vault", "c:collection_id", "u:user_id", "g:group_id"),
    "vault_key": ("vault", "c:collection_id"),
    "vault_folder": ("vault", "c:collection_id"),
    "vault_item": ("vault", "c:collection_id"),
    "mail_account": ("mail", "u:owner_id"),
    "mail_folder": ("mail", "u:owner_id"),
    "mail_message": ("mail", "u:owner_id"),
    "mail_draft": ("mail", "u:owner_id"),
    "mail_unsent": ("mail", "u:owner_id"),
    "mail_signature": ("mail", "u:owner_id"),
    "mail_rule": ("mail", "u:owner_id"),
    "users_apppassword": ("account", "u:user_id"),
    "users_passkey": ("account", "u:user_id"),
    "users_user": ("users", "*"),
    "users_policy": ("users", "*"),
}


class Migration(migrations.Migration):
    dependencies = [
        ("collab", "0005_references_kept_by_the_database"),
        ("contacts", "0004_favourites"),
        ("calendar", "0011_worded_conference"),
        ("tasks", "0002_words"),
        ("documents", "0024_copied"),
        ("versions", "0008_file_version"),
        ("access", "0003_access_log"),
        ("shares", "0001_initial"),
        ("vault", "0002_folders"),
        ("mail", "0020_translation"),
        ("users", "0005_passkeys_for_everyone"),
    ]

    operations = [followed(table, *targets) for table, targets in FOLLOWED.items()]
