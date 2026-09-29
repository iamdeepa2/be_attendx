import json

from django.test import TestCase

from .models import Attendance, Classroom, Student, Subject, Teacher, TeachingAssignment


class TeacherScopeTests(TestCase):
    def setUp(self):
        self.teacher = Teacher.objects.create(name="Teacher A", email="a@example.test", password="test")
        self.other = Teacher.objects.create(name="Teacher B", email="b@example.test", password="test")
        self.students = [Student.objects.create(name=f"Student {i}", email=f"s{i}@example.test", password="test") for i in range(3)]
        self.rooms = [Classroom.objects.create(name=f"Class {i}") for i in range(3)]
        self.subjects = [Subject.objects.create(name=f"Subject {i}") for i in range(3)]
        for room, student in zip(self.rooms, self.students):
            room.students.add(student)
            room.subjects.add(*self.subjects)
        for i, room in enumerate(self.rooms):
            owner = self.teacher if i < 2 else self.other
            room.teachers.add(owner)
            TeachingAssignment.objects.create(classroom=room, teacher=owner, subject=self.subjects[i])
        self.rooms[0].teachers.add(self.other)
        TeachingAssignment.objects.create(classroom=self.rooms[0], teacher=self.other, subject=self.subjects[2])

    def context(self, room, teacher=None):
        return self.client.get(f"/teachers/{(teacher or self.teacher).id}/classrooms/{room.id}/")

    def payload(self, **changes):
        return {"teacher_id": self.teacher.id, "classroom_id": self.rooms[0].id,
                "subject_id": self.subjects[0].id, "student_id": self.students[0].id,
                "date": "2026-09-29", "present": True, **changes}

    def mark(self, **changes):
        return self.client.post("/attendance/", json.dumps(self.payload(**changes)), content_type="application/json")

    def test_picker_is_dynamic_for_each_teacher_and_classroom(self):
        for teacher, indices in [(self.teacher, [0, 1]), (self.other, [0, 2])]:
            response = self.client.get(f"/teachers/{teacher.id}/classrooms/").json()
            self.assertEqual([r["id"] for r in response["classrooms"]], [self.rooms[i].id for i in indices])
        for i in (0, 1):
            data = self.context(self.rooms[i]).json()
            self.assertEqual([s["id"] for s in data["subjects"]], [self.subjects[i].id])
            self.assertEqual([s["id"] for s in data["students"]], [self.students[i].id])
            self.assertNotIn("available_subjects", data)
        self.assertEqual(self.context(self.rooms[2]).status_code, 403)
        self.assertEqual(self.context(self.rooms[0], self.other).json()["subjects"][0]["id"], self.subjects[2].id)

    def test_membership_without_subject_assignment_has_no_fallback(self):
        TeachingAssignment.objects.filter(teacher=self.teacher).delete()
        self.assertEqual(self.client.get(f"/teachers/{self.teacher.id}/classrooms/").json()["classrooms"], [])
        self.assertEqual(self.context(self.rooms[0]).status_code, 403)
        self.assertEqual(self.mark().status_code, 403)

    def test_valid_mark_saves_exact_relationship(self):
        self.assertEqual(self.mark().status_code, 200)
        record = Attendance.objects.get()
        self.assertEqual((record.teacher_id, record.classroom_id, record.subject_id, record.student_id),
                         (self.teacher.id, self.rooms[0].id, self.subjects[0].id, self.students[0].id))

    def test_invalid_combinations_never_create_records(self):
        for changes in [
            {"student_id": self.students[1].id},
            {"subject_id": self.subjects[1].id},
            {"subject_id": self.subjects[2].id},
            {"classroom_id": self.rooms[2].id},
            {"classroom_id": None},
            {"teacher_id": 999999},
            {"date": "invalid"},
            {"present": "false"},
        ]:
            with self.subTest(changes=changes):
                self.assertIn(self.mark(**changes).status_code, (400, 403))
        self.assertEqual(Attendance.objects.count(), 0)

    def test_admin_removal_invalidates_loaded_selection(self):
        self.rooms[0].teachers.remove(self.teacher)
        self.assertEqual(self.context(self.rooms[0]).status_code, 403)
        self.assertEqual(self.mark().status_code, 403)
        self.rooms[0].teachers.add(self.teacher)
        self.rooms[0].subjects.remove(self.subjects[0])
        self.assertEqual(self.context(self.rooms[0]).status_code, 403)
        self.assertEqual(self.mark().status_code, 403)

    def test_saved_records_exclude_unrelated_and_legacy_rows(self):
        self.assertEqual(self.mark().status_code, 200)
        valid_id = Attendance.objects.get().id
        for changes in [{"student_id": self.students[1].id}, {"subject_id": self.subjects[2].id}, {"classroom_id": None}]:
            Attendance.objects.create(**self.payload(**changes))
        rows = self.client.get(f"/attendance/?teacher_id={self.teacher.id}").json()
        self.assertEqual([r["id"] for r in rows], [valid_id])
        self.assertEqual(rows[0]["student_name"], self.students[0].name)
        self.assertEqual(self.client.get(f"/attendance/?teacher_id={self.teacher.id}&classroom_id={self.rooms[2].id}").json(), [])
        self.rooms[0].students.remove(self.students[0])
        self.assertEqual(self.client.get(f"/attendance/?teacher_id={self.teacher.id}").json(), [])
        self.assertEqual(Attendance.objects.count(), 4)
