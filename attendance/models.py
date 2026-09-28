from django.db import models


class Student(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, default="")
    password = models.CharField(max_length=100)


class Teacher(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, default="")
    password = models.CharField(max_length=100)


class Admin(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=100)


class Subject(models.Model):
    name = models.CharField(max_length=100)


class Classroom(models.Model):
    name = models.CharField(max_length=100)
    students = models.ManyToManyField(Student, blank=True, related_name="classrooms")
    teachers = models.ManyToManyField(Teacher, blank=True, related_name="classrooms")
    subjects = models.ManyToManyField(Subject, blank=True, related_name="classrooms")


class TeachingAssignment(models.Model):
    """One teaching assignment: this teacher teaches this subject in this classroom.

    The pair lives on the assignment, not on the teacher, because the same
    teacher can teach different subjects in different classrooms.
    """

    classroom = models.ForeignKey(
        Classroom, on_delete=models.CASCADE, related_name="teaching_assignments"
    )
    teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name="teaching_assignments"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="teaching_assignments"
    )

    class Meta:
        unique_together = [("classroom", "teacher", "subject")]
        ordering = ["teacher__name", "subject__name"]


class Attendance(models.Model):
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    # Which classroom the lesson belongs to. Null for records marked before
    # classroom-scoped teaching existed, so old attendance is never lost and
    # deleting a classroom never deletes attendance.
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance"
    )
    date = models.DateField()
    present = models.BooleanField()
    method = models.CharField(max_length=10, default="manual")
    session_id = models.BigIntegerField(null=True, blank=True)
