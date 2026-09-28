# One teacher can teach many subjects. This only adds the join table, so no
# existing teacher, subject, classroom, login or attendance row is touched.
#
# The data step backfills teacher/subject pairs that attendance already
# implies, so teachers who were marking attendance keep the subjects they were
# actually teaching. It only inserts missing links and never removes any.

from django.db import migrations, models


def backfill_from_attendance(apps, schema_editor):
    Teacher = apps.get_model("attendance", "Teacher")
    Subject = apps.get_model("attendance", "Subject")
    Attendance = apps.get_model("attendance", "Attendance")

    pairs = (
        Attendance.objects.exclude(teacher_id=None)
        .values_list("teacher_id", "subject_id")
        .distinct()
    )
    for teacher_id, subject_id in pairs:
        if not (Teacher.objects.filter(id=teacher_id).exists()
                and Subject.objects.filter(id=subject_id).exists()):
            continue
        teacher = Teacher.objects.get(id=teacher_id)
        if not teacher.subjects.filter(id=subject_id).exists():
            teacher.subjects.add(subject_id)


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0008_add_missing_attendance_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacher",
            name="subjects",
            field=models.ManyToManyField(
                blank=True, related_name="teachers", to="attendance.subject"
            ),
        ),
        migrations.RunPython(backfill_from_attendance, migrations.RunPython.noop),
    ]
