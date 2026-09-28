# Teacher <-> subject is now classroom specific: TeachingAssignment holds
# (classroom, teacher, subject). The old global Teacher.subjects link is
# removed after its rows are converted.
#
# Conversion rule: a legacy (teacher, subject) pair becomes one assignment
# only when exactly one classroom contains both the teacher and the subject.
# Anything else would be a guess, so it is left out and reported instead.

from django.db import migrations, models
import django.db.models.deletion


def convert_global_links(apps, schema_editor):
    Teacher = apps.get_model("attendance", "Teacher")
    TeachingAssignment = apps.get_model("attendance", "TeachingAssignment")

    ambiguous = []
    converted = 0

    for teacher in Teacher.objects.prefetch_related("subjects", "classrooms"):
        for subject in teacher.subjects.all():
            shared = [
                classroom
                for classroom in teacher.classrooms.all()
                if classroom.subjects.filter(id=subject.id).exists()
            ]
            if len(shared) == 1:
                TeachingAssignment.objects.get_or_create(
                    classroom=shared[0], teacher=teacher, subject=subject
                )
                converted += 1
            else:
                ambiguous.append(
                    {
                        "teacher": teacher.name,
                        "teacher_email": teacher.email,
                        "subject": subject.name,
                        "classrooms_with_both": [c.name for c in shared],
                    }
                )

    print(f"Converted {converted} teacher/subject link(s) into classroom assignments.")
    if ambiguous:
        print(
            "NOT converted (kept out on purpose, needs manual assignment): "
            + "; ".join(
                f"{item['teacher']} -> {item['subject']} "
                f"(classrooms with both: {item['classrooms_with_both'] or 'none'})"
                for item in ambiguous
            )
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0009_teacher_subjects"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeachingAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "classroom",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teaching_assignments",
                        to="attendance.classroom",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teaching_assignments",
                        to="attendance.teacher",
                    ),
                ),
                (
                    "subject",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teaching_assignments",
                        to="attendance.subject",
                    ),
                ),
            ],
            options={
                "ordering": ["teacher__name", "subject__name"],
                "unique_together": {("classroom", "teacher", "subject")},
            },
        ),
        migrations.RunPython(convert_global_links, noop),
        migrations.RemoveField(
            model_name="teacher",
            name="subjects",
        ),
        migrations.AddField(
            model_name="attendance",
            name="classroom",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="attendance",
                to="attendance.classroom",
            ),
        ),
    ]
