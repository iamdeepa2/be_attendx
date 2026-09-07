from django.contrib import admin
from .models import Student, Teacher, Admin, Subject, Classroom, Attendance

admin.site.register(Student)
admin.site.register(Teacher)
admin.site.register(Admin)
admin.site.register(Subject)
admin.site.register(Classroom)
admin.site.register(Attendance)