# The columns `method` and `session_id` already exist on the
# attendance_attendance table (added outside Django's migration history),
# so this migration only syncs Django's model state with the real schema.
# No DDL is run and no existing rows are touched.
# `method` is given the same "manual" default the existing rows already use,
# which satisfies its NOT NULL constraint on insert.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0005_classroom_students_classroom_subjects_student_phone'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='attendance',
                    name='method',
                    field=models.CharField(default='manual', max_length=10),
                ),
                migrations.AddField(
                    model_name='attendance',
                    name='session_id',
                    field=models.BigIntegerField(blank=True, null=True),
                ),
            ],
            database_operations=[],
        ),
    ]
