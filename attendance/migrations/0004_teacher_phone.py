from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0003_attendance_teacher'),
    ]

    operations = [
        migrations.AddField(
            model_name='teacher',
            name='phone',
            field=models.CharField(default='', max_length=15),
        ),
    ]
