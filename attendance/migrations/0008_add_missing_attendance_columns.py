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
    pass


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("attendance", "0007_classroom_teachers"),
    ]

    operations = [
        migrations.RunPython(add_missing_columns, keep_existing_columns),
    ]
