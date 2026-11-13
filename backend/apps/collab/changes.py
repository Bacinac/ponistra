"""The triggers that tell `/api/live` a followed table changed: each row inserted, updated or
deleted notifies the `changed` channel with its area and whom it concerns, which `live._changed`
resolves to users. A table the interface shows from is followed by a migration of its own:

    operations = [followed("contacts_contact", "contacts", "u:owner_id")]

A target is `kind:column` (`u` a user, `n` a node, `g` a group, `c` a vault collection, `k` a
calendar, each with a resolver in `live.AUDIENCES`) or `*` for everyone; the area is one of the
keys of `AREAS` in `frontend/src/followed.ts`.
"""

from django.db import migrations


def _told(area: str, target: str, row: str) -> str:
    if target == "*":
        return f"PERFORM pg_notify('changed', '{area} *');"
    kind, column = target.split(":")
    return (
        f"IF {row}.{column} IS NOT NULL THEN "
        f"PERFORM pg_notify('changed', '{area} {kind}' || {row}.{column}); END IF;"
    )


def followed(table: str, area: str, *targets: str) -> migrations.RunSQL:
    old = "\n        ".join(_told(area, each, "OLD") for each in targets)
    new = "\n        ".join(_told(area, each, "NEW") for each in targets)
    return migrations.RunSQL(
        f"""
CREATE FUNCTION live_{table}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD IS NOT DISTINCT FROM NEW THEN
        RETURN NULL;
    END IF;
    IF TG_OP <> 'INSERT' THEN
        {old}
    END IF;
    IF TG_OP <> 'DELETE' THEN
        {new}
    END IF;
    RETURN NULL;
END $$;
CREATE TRIGGER live AFTER INSERT OR UPDATE OR DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION live_{table}();
""",
        f"DROP TRIGGER live ON {table}; DROP FUNCTION live_{table}();",
    )
