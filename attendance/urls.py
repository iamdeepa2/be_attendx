
from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login),
    path("register/student/", views.student_register),
    path("students/", views.students),
    path("teachers/", views.teachers),
    path("subjects/", views.subjects),
    path("classrooms/", views.classrooms),
    path("attendance/", views.records),
]
