from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0006_attendance_method_attendance_session_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='classroom',
            name='teachers',
            field=models.ManyToManyField(blank=True, related_name='classrooms', to='attendance.teacher'),
        ),
    ]
