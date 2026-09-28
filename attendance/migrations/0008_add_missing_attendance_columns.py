# `method` and `session_id` were added to attendance_attendance outside
# Django's migration history (see 0006, which only syncs model state).
# Existing databases already have both columns, so this migration adds each
# column only when introspection shows it is missing. That makes a freshly
# built database (and the test database) match the Attendance model without
# touching databases that are already correct.

from django.db import migrations

FIELDS = ("method", "session_id")


def add_missing_columns(apps, schema_editor):
    Attendance = apps.get_model("attendance", "Attendance")
    table = Attendance._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        existing = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table
            )
        }
    for name in FIELDS:
        field = Attendance._meta.get_field(name)
        if field.column not in existing:
            schema_editor.add_field(Attendance, field)


def keep_existing_columns(apps, schema_editor):
    """Reverse is a no-op: the columns may predate this migration."""


class Migration(migrations.Migration):

    # MySQL cannot roll back DDL, so this ALTER TABLE runs in autocommit.
    atomic = False

    dependencies = [
        ("attendance", "0007_classroom_teachers"),
    ]

    operations = [
        migrations.RunPython(add_missing_columns, keep_existing_columns),
    ]
