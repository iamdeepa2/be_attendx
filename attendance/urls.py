
from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login),
    path("register/student/", views.student_register),
    path("students/", views.students),
    path("students/<int:student_id>/dashboard/", views.student_dashboard),
    path("teachers/", views.teachers),
    path("teachers/<int:teacher_id>/classrooms/", views.teacher_classrooms),
    path(
        "classrooms/<int:classroom_id>/teachers/<int:teacher_id>/subjects/",
        views.classroom_teacher_subjects,
    ),
    path("subjects/", views.subjects),
    path("classrooms/", views.classrooms),
    path("classrooms/<int:classroom_id>/", views.classroom_detail),
    path("classrooms/<int:classroom_id>/students/", views.classroom_students),
    path("classrooms/<int:classroom_id>/teachers/", views.classroom_teachers),
    path("classrooms/<int:classroom_id>/subjects/", views.classroom_subjects),
    path("attendance/", views.records),
]
