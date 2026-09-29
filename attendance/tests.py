import json

from django.db import transaction
from django.test import TestCase

from .models import (
    Student,
    Teacher,
    Subject,
    Classroom,
    Attendance,
    TeachingAssignment,
)


class ClassroomEditTests(TestCase):
    """Covers Edit (update in place) vs Remove (drop assignment only)."""

    def setUp(self):
        self.student = Student.objects.create(
            name="Deepa Pandey", email="deepa@gmail.com", phone="9800000001",
            password="password123",
        )
        self.teacher = Teacher.objects.create(
            name="Rahul Shakya", email="rahul@gmail.com", phone="9851042262",
            password="password123",
        )
        self.subject = Subject.objects.create(name="Operating System")

        self.classroom = Classroom.objects.create(name="BCA-1")
        self.classroom.students.add(self.student)
        self.classroom.teachers.add(self.teacher)
        self.classroom.subjects.add(self.subject)

        self.attendance = Attendance.objects.create(
            teacher=self.teacher,
            student=self.student,
            subject=self.subject,
            date="2026-01-05",
            present=True,
        )

    def put(self, path, body):
        return self.client.put(path, json.dumps(body), content_type="application/json")

    def post(self, path, body):
        return self.client.post(path, json.dumps(body), content_type="application/json")

    def delete(self, path, body):
        return self.client.delete(path, json.dumps(body), content_type="application/json")

    def classroom_payload(self):
        return json.loads(self.client.get(f"/classrooms/{self.classroom.id}/").content)

    # Student ---------------------------------------------------------

    def test_edit_student_updates_record_without_creating_duplicate(self):
        response = self.put(
            "/students/",
            {
                "id": self.student.id,
                "name": "Deepa S. Pandey",
                "email": "deepa.new@gmail.com",
                "phone": "98XXXXXXXX",
            },
        )
        self.assertEqual(response.status_code, 200)

        self.assertEqual(Student.objects.count(), 1)
        self.student.refresh_from_db()
        self.assertEqual(self.student.name, "Deepa S. Pandey")
        self.assertEqual(self.student.email, "deepa.new@gmail.com")
        self.assertEqual(self.student.phone, "98XXXXXXXX")

        # Membership, counts and the refreshed page show the new values.
        payload = self.classroom_payload()
        self.assertEqual(payload["student_count"], 1)
        self.assertEqual(payload["students"][0]["name"], "Deepa S. Pandey")
        self.assertEqual(payload["students"][0]["phone"], "98XXXXXXXX")

        # The same shared record is updated everywhere it is listed.
        listed = json.loads(self.client.get("/students/").content)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["email"], "deepa.new@gmail.com")

        # Attendance history is untouched.
        self.attendance.refresh_from_db()
        self.assertEqual(Attendance.objects.count(), 1)
        self.assertEqual(self.attendance.student_id, self.student.id)
        self.assertTrue(self.attendance.present)

    def test_edit_student_password_left_blank_keeps_current(self):
        self.put(
            "/students/",
            {"id": self.student.id, "name": "Deepa Pandey",
             "email": "deepa@gmail.com", "phone": "9800000001"},
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.password, "password123")

    def test_edit_student_validates_name_and_email(self):
        missing_name = self.put(
            "/students/", {"id": self.student.id, "name": "  ", "email": "d@gmail.com"}
        )
        self.assertEqual(missing_name.status_code, 400)

        missing_email = self.put(
            "/students/", {"id": self.student.id, "name": "Deepa", "email": ""}
        )
        self.assertEqual(missing_email.status_code, 400)

        self.student.refresh_from_db()
        self.assertEqual(self.student.name, "Deepa Pandey")
        self.assertEqual(Student.objects.count(), 1)

    def test_edit_student_duplicate_email_is_rejected(self):
        Student.objects.create(name="Other", email="other@gmail.com", password="password123")
        # The view catches the IntegrityError, so the savepoint keeps the test
        # transaction usable for the assertions below.
        with transaction.atomic():
            response = self.put(
                "/students/",
                {"id": self.student.id, "name": "Deepa", "email": "other@gmail.com"},
            )
        self.assertEqual(response.status_code, 400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "deepa@gmail.com")
        self.assertEqual(Student.objects.count(), 2)

    def test_remove_student_drops_assignment_but_keeps_record(self):
        response = self.delete(
            f"/classrooms/{self.classroom.id}/students/", {"student_id": self.student.id}
        )
        self.assertEqual(response.status_code, 200)

        self.assertTrue(Student.objects.filter(id=self.student.id).exists())
        self.assertEqual(Student.objects.count(), 1)
        self.assertFalse(
            self.classroom.students.filter(id=self.student.id).exists()
        )
        self.assertEqual(self.classroom_payload()["student_count"], 0)
        # The record keeps its own details after being unassigned.
        self.student.refresh_from_db()
        self.assertEqual(self.student.name, "Deepa Pandey")

    # Teacher ---------------------------------------------------------

    def test_edit_teacher_updates_record_without_creating_duplicate(self):
        response = self.put(
            "/teachers/",
            {
                "id": self.teacher.id,
                "name": "Rahul S. Shakya",
                "email": "rahul.new@gmail.com",
                "phone": "9999999999",
            },
        )
        self.assertEqual(response.status_code, 200)

        self.assertEqual(Teacher.objects.count(), 1)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.name, "Rahul S. Shakya")
        self.assertEqual(self.teacher.email, "rahul.new@gmail.com")
        self.assertEqual(self.teacher.phone, "9999999999")

        payload = self.classroom_payload()
        self.assertEqual(payload["teacher_count"], 1)
        self.assertEqual(payload["teachers"][0]["phone"], "9999999999")

        listed = json.loads(self.client.get("/teachers/").content)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["name"], "Rahul S. Shakya")

        self.attendance.refresh_from_db()
        self.assertEqual(Attendance.objects.count(), 1)
        self.assertEqual(self.attendance.teacher_id, self.teacher.id)

    def test_remove_teacher_drops_assignment_but_keeps_record(self):
        response = self.delete(
            f"/classrooms/{self.classroom.id}/teachers/", {"teacher_id": self.teacher.id}
        )
        self.assertEqual(response.status_code, 200)

        self.assertTrue(Teacher.objects.filter(id=self.teacher.id).exists())
        self.assertFalse(
            self.classroom.teachers.filter(id=self.teacher.id).exists()
        )
        self.assertEqual(self.classroom_payload()["teacher_count"], 0)

    # Subject ---------------------------------------------------------

    def test_edit_subject_updates_record_without_creating_duplicate(self):
        response = self.put(
            "/subjects/", {"id": self.subject.id, "name": "Operating Systems"}
        )
        self.assertEqual(response.status_code, 200)

        self.assertEqual(Subject.objects.count(), 1)
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.name, "Operating Systems")

        payload = self.classroom_payload()
        self.assertEqual(payload["subject_count"], 1)
        self.assertEqual(payload["subjects"][0]["name"], "Operating Systems")

        listed = json.loads(self.client.get("/subjects/").content)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["name"], "Operating Systems")

        self.attendance.refresh_from_db()
        self.assertEqual(Attendance.objects.count(), 1)
        self.assertEqual(self.attendance.subject_id, self.subject.id)

    def test_edit_subject_validates_name_and_duplicates(self):
        empty = self.put("/subjects/", {"id": self.subject.id, "name": "  "})
        self.assertEqual(empty.status_code, 400)

        Subject.objects.create(name="DBMS")
        clash = self.put("/subjects/", {"id": self.subject.id, "name": "dbms"})
        self.assertEqual(clash.status_code, 400)

        self.subject.refresh_from_db()
        self.assertEqual(self.subject.name, "Operating System")

        # Keeping its own name is not a duplicate.
        same = self.put(
            "/subjects/", {"id": self.subject.id, "name": "Operating System"}
        )
        self.assertEqual(same.status_code, 200)

    def test_remove_subject_drops_assignment_but_keeps_record(self):
        response = self.delete(
            f"/classrooms/{self.classroom.id}/subjects/", {"subject_id": self.subject.id}
        )
        self.assertEqual(response.status_code, 200)

        self.assertTrue(Subject.objects.filter(id=self.subject.id).exists())
        self.assertFalse(
            self.classroom.subjects.filter(id=self.subject.id).exists()
        )
        self.assertEqual(self.classroom_payload()["subject_count"], 0)

    # Edit then Remove stay independent -------------------------------

    def test_edit_then_remove_keeps_the_edited_record(self):
        self.put(
            "/teachers/",
            {"id": self.teacher.id, "name": "Rahul Shakya",
             "email": "rahul@gmail.com", "phone": "9123456780"},
        )
        self.delete(
            f"/classrooms/{self.classroom.id}/teachers/", {"teacher_id": self.teacher.id}
        )

        teacher = Teacher.objects.get(id=self.teacher.id)
        self.assertEqual(Teacher.objects.count(), 1)
        self.assertEqual(teacher.phone, "9123456780")
        self.assertEqual(teacher.classrooms.count(), 0)

        # Re-assigning brings back the same record with the edited details.
        self.post(
            f"/classrooms/{self.classroom.id}/teachers/", {"teacher_id": teacher.id}
        )
        self.assertEqual(self.classroom_payload()["teachers"][0]["phone"], "9123456780")
        self.assertEqual(Teacher.objects.count(), 1)


class ClassroomTeachingTests(TestCase):
    """One teacher record, different subjects per classroom, no leakage."""

    def setUp(self):
        self.bca2 = Classroom.objects.create(name="BCA 2nd Sem")
        self.bca4 = Classroom.objects.create(name="BCA 4th Sem")
        self.web = Subject.objects.create(name="Web Technology")
        self.scripting = Subject.objects.create(name="Scripting Language")
        self.os = Subject.objects.create(name="Operating System")

    def get(self, path):
        return self.client.get(path)

    def post(self, path, body):
        return self.client.post(path, json.dumps(body), content_type="application/json")

    def delete(self, path, body):
        return self.client.delete(
            path, json.dumps(body), content_type="application/json"
        )

    def create_teacher(self, name, email):
        return json.loads(self.post("/teachers/", {
            "name": name,
            "email": email,
            "phone": "9851042262",
            "password": "teacher@248",
        }).content)["id"]

    def add_teacher_to(self, classroom, teacher_id):
        response = self.post(
            f"/classrooms/{classroom.id}/teachers/", {"teacher_id": teacher_id}
        )
        self.assertEqual(response.status_code, 200)

    def add_subject_to(self, classroom, subject):
        response = self.post(
            f"/classrooms/{classroom.id}/subjects/", {"subject_id": subject.id}
        )
        self.assertEqual(response.status_code, 200)

    def teaching_path(self, classroom, teacher_id):
        return f"/classrooms/{classroom.id}/teachers/{teacher_id}/subjects/"

    def teaching(self, classroom, teacher_id):
        response = self.get(self.teaching_path(classroom, teacher_id))
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def set_up_bishnu(self):
        """The reported case: Bishnu teaches Web Tech in BCA 2 and Scripting in BCA 4."""
        bishnu = self.create_teacher(
            "Bishnu Prasadh Chaudhary", "bishnu@gmail.com"
        )
        for classroom, subject in ((self.bca2, self.web), (self.bca4, self.scripting)):
            self.add_teacher_to(classroom, bishnu)
            self.add_subject_to(classroom, subject)
        self.post(self.teaching_path(self.bca2, bishnu), {"subject_id": self.web.id})
        self.post(
            self.teaching_path(self.bca4, bishnu), {"subject_id": self.scripting.id}
        )
        return bishnu

    def test_same_teacher_teaches_different_subjects_per_classroom(self):
        bishnu = self.set_up_bishnu()

        # One account, present in both classrooms.
        self.assertEqual(Teacher.objects.count(), 1)
        self.assertEqual(
            sorted(Teacher.objects.get(id=bishnu).classrooms.values_list(
                "name", flat=True
            )),
            ["BCA 2nd Sem", "BCA 4th Sem"],
        )

        # Each classroom exposes only its own subject for him.
        self.assertEqual(
            [s["name"] for s in self.teaching(self.bca2, bishnu)["subjects"]],
            ["Web Technology"],
        )
        self.assertEqual(
            [s["name"] for s in self.teaching(self.bca4, bishnu)["subjects"]],
            ["Scripting Language"],
        )

        # The other classroom's subject is not even offered in BCA 2.
        offered = [s["name"] for s in self.teaching(self.bca2, bishnu)["available_subjects"]]
        self.assertEqual(offered, [])

        self.assertEqual(TeachingAssignment.objects.count(), 2)

    def test_classroom_detail_does_not_leak_across_classrooms(self):
        bishnu = self.set_up_bishnu()

        detail_2 = json.loads(self.get(f"/classrooms/{self.bca2.id}/").content)
        by_id_2 = {t["id"]: t for t in detail_2["teachers"]}
        self.assertEqual(
            [s["name"] for s in by_id_2[bishnu]["subjects"]], ["Web Technology"]
        )
        self.assertNotIn("all_subjects", detail_2)

        detail_4 = json.loads(self.get(f"/classrooms/{self.bca4.id}/").content)
        by_id_4 = {t["id"]: t for t in detail_4["teachers"]}
        self.assertEqual(
            [s["name"] for s in by_id_4[bishnu]["subjects"]], ["Scripting Language"]
        )

    def test_teacher_list_has_no_global_subject_field(self):
        bishnu = self.set_up_bishnu()
        listed = json.loads(self.get("/teachers/").content)
        self.assertEqual(len(listed), 1)
        self.assertNotIn("subject_ids", listed[0])
        self.assertFalse(hasattr(Teacher, "subjects"))

        rooms = json.loads(self.get(f"/teachers/{bishnu}/classrooms/").content)
        self.assertEqual(
            sorted(c["name"] for c in rooms["classrooms"]),
            ["BCA 2nd Sem", "BCA 4th Sem"],
        )

    def test_subject_must_belong_to_the_classroom(self):
        bishnu = self.set_up_bishnu()

        # Operating System is not a BCA 2 subject, so it cannot be assigned.
        refused = self.post(
            self.teaching_path(self.bca2, bishnu), {"subject_id": self.os.id}
        )
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(TeachingAssignment.objects.count(), 2)

    def test_duplicate_assignment_is_refused(self):
        bishnu = self.set_up_bishnu()
        again = self.post(
            self.teaching_path(self.bca2, bishnu), {"subject_id": self.web.id}
        )
        self.assertEqual(again.status_code, 400)
        self.assertEqual(TeachingAssignment.objects.count(), 2)

    def test_unassign_only_touches_one_classroom(self):
        bishnu = self.set_up_bishnu()
        student = Student.objects.create(
            name="Deepa Pandey", email="deepa@gmail.com", password="password123"
        )
        self.bca2.students.add(student)
        self.post("/attendance/", {
            "teacher_id": bishnu,
            "student_id": student.id,
            "subject_id": self.web.id,
            "classroom_id": self.bca2.id,
            "date": "2026-01-05",
            "present": True,
        })

        removed = self.delete(
            self.teaching_path(self.bca2, bishnu), {"subject_id": self.web.id}
        )
        self.assertEqual(removed.status_code, 200)

        # BCA 2 loses the subject, BCA 4 keeps its own, records survive.
        self.assertEqual(
            [s["name"] for s in self.teaching(self.bca2, bishnu)["subjects"]], []
        )
        self.assertEqual(
            [s["name"] for s in self.teaching(self.bca4, bishnu)["subjects"]],
            ["Scripting Language"],
        )
        self.assertEqual(Teacher.objects.count(), 1)
        self.assertTrue(Subject.objects.filter(id=self.web.id).exists())
        self.assertEqual(Attendance.objects.count(), 1)

    def test_attendance_is_scoped_by_classroom(self):
        bishnu = self.set_up_bishnu()
        student = Student.objects.create(
            name="Deepa Pandey", email="deepa@gmail.com", password="password123"
        )
        for classroom, subject in ((self.bca2, self.web), (self.bca4, self.scripting)):
            classroom.students.add(student)
            self.post("/attendance/", {
                "teacher_id": bishnu,
                "student_id": student.id,
                "subject_id": subject.id,
                "classroom_id": classroom.id,
                "date": "2026-01-05",
                "present": True,
            })

        in_bca2 = json.loads(
            self.get(f"/attendance/?teacher_id={bishnu}&classroom_id={self.bca2.id}").content
        )
        self.assertEqual(len(in_bca2), 1)
        self.assertEqual(in_bca2[0]["subject_id"], self.web.id)
        self.assertEqual(in_bca2[0]["classroom_id"], self.bca2.id)

        all_rows = json.loads(self.get(f"/attendance/?teacher_id={bishnu}").content)
        self.assertEqual(len(all_rows), 2)

    def test_deleting_classroom_keeps_attendance(self):
        bishnu = self.set_up_bishnu()
        student = Student.objects.create(
            name="Deepa Pandey", email="deepa@gmail.com", password="password123"
        )
        self.bca2.students.add(student)
        self.post("/attendance/", {
            "teacher_id": bishnu,
            "student_id": student.id,
            "subject_id": self.web.id,
            "classroom_id": self.bca2.id,
            "date": "2026-01-05",
            "present": True,
        })

        with transaction.atomic():
            self.bca2.delete()

        record = Attendance.objects.get()
        self.assertIsNone(record.classroom_id)
        self.assertEqual(record.subject_id, self.web.id)
        self.assertEqual(Teacher.objects.count(), 1)
        self.assertEqual(Subject.objects.count(), 3)

    def test_duplicate_email_points_at_the_existing_teacher(self):
        bishnu = self.set_up_bishnu()
        duplicate = self.post("/teachers/", {
            "name": "Bishnu Prasadh Chaudhary",
            "email": "bishnu@gmail.com",
            "phone": "9851042262",
            "password": "teacher@248",
        })
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(
            json.loads(duplicate.content)["existing_teacher_id"], bishnu
        )
        self.assertEqual(Teacher.objects.count(), 1)

        # The single account still logs in and still holds both assignments.
        login = self.post("/login/", {
            "email": "bishnu@gmail.com",
            "password": "teacher@248",
            "user_type": "teacher",
        })
        self.assertEqual(login.status_code, 200)
        self.assertEqual(json.loads(login.content)["user_id"], bishnu)
        self.assertEqual(TeachingAssignment.objects.count(), 2)


class StudentDashboardScopeTests(TestCase):
    """A student only ever sees their own classroom's teachers and subjects.

    Mirrors the reported case: the same teacher holds different subjects in
    different classrooms, and a student must not see the other semesters.
    """

    def setUp(self):
        # BCA 2nd Sem
        self.bca2 = Classroom.objects.create(name="BCA 2nd Sem")
        # BCA 4th Sem
        self.bca4 = Classroom.objects.create(name="BCA 4th Sem")
        # BCA 3rd Sem, used to prove the logic is not tied to a fixed pair.
        self.bca3 = Classroom.objects.create(name="BCA 3rd Sem")

        self.web = Subject.objects.create(name="Web Technology")
        self.dsa = Subject.objects.create(name="DSA")
        self.scripting = Subject.objects.create(name="Scripting Language")
        self.os = Subject.objects.create(name="Operating System")
        self.dbms = Subject.objects.create(name="DBMS")
        self.numerical = Subject.objects.create(name="Numerical Method")

        self.bishnu = Teacher.objects.create(
            name="Bishnu Prasadh Chaudhary", email="bishnu@gmail.com",
            phone="9849085314", password="teacher@248",
        )
        self.rahul = Teacher.objects.create(
            name="Rahul Shakya", email="rahul@gmail.com",
            phone="9851042262", password="teacher@248",
        )
        self.sujan = Teacher.objects.create(
            name="Sujan Dhakal", email="sujan@gmail.com",
            phone="9862163839", password="teacher@248",
        )
        self.dipa = Teacher.objects.create(
            name="Dipa Gurung", email="dipa@gmail.com",
            phone="9812345678", password="teacher@248",
        )

        # Bishnu: Web Technology in BCA 2, Scripting Language in BCA 4.
        for classroom, subject in ((self.bca2, self.web), (self.bca4, self.scripting)):
            classroom.teachers.add(self.bishnu)
            classroom.subjects.add(subject)
            TeachingAssignment.objects.create(
                classroom=classroom, teacher=self.bishnu, subject=subject
            )

        # BCA 4th Sem only.
        self.bca4.teachers.add(self.rahul, self.sujan)
        self.bca4.subjects.add(self.os, self.dbms, self.numerical)
        TeachingAssignment.objects.create(
            classroom=self.bca4, teacher=self.rahul, subject=self.os
        )
        TeachingAssignment.objects.create(
            classroom=self.bca4, teacher=self.sujan, subject=self.dbms
        )

        # BCA 3rd Sem only.
        self.bca3.teachers.add(self.dipa)
        self.bca3.subjects.add(self.dsa)
        TeachingAssignment.objects.create(
            classroom=self.bca3, teacher=self.dipa, subject=self.dsa
        )

        self.rachana = Student.objects.create(
            name="Rachana Bhurtel", email="rachana@gmail.com", password="rachana@248"
        )
        self.deepa = Student.objects.create(
            name="Deepa Pandey", email="deepa@gmail.com", password="deepa@248"
        )
        self.asha = Student.objects.create(
            name="Asha Rai", email="asha@gmail.com", password="asha@248"
        )
        self.bca2.students.add(self.rachana)
        self.bca4.students.add(self.deepa)

        # Attendance for both students across every classroom, plus a legacy
        # row with no classroom, to prove nothing leaks either way.
        self.rows = {}
        for student, classroom, subject, present in (
            (self.rachana, self.bca2, self.web, True),
            (self.rachana, self.bca4, self.os, False),
            (self.rachana, self.bca3, self.dsa, True),
            (self.deepa, self.bca4, self.os, True),
            (self.deepa, self.bca2, self.web, False),
        ):
            record = Attendance.objects.create(
                teacher=self.bishnu, student=student, subject=subject,
                classroom=classroom, date="2026-01-05", present=present,
            )
            self.rows.setdefault(student.id, []).append(record)
        self.legacy = Attendance.objects.create(
            teacher=self.bishnu, student=self.deepa, subject=self.os,
            date="2026-01-06", present=True,
        )

    def dashboard(self, student):
        response = self.client.get(f"/students/{student.id}/dashboard/")
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def teacher_names(self, payload):
        return sorted(t["name"] for t in payload["teachers"])

    def subject_names(self, payload):
        return sorted(s["name"] for s in payload["subjects"])

    def test_rachana_sees_only_bca2_teachers_and_subjects(self):
        payload = self.dashboard(self.rachana)

        self.assertEqual(payload["classroom"]["name"], "BCA 2nd Sem")
        self.assertEqual(
            self.teacher_names(payload), ["Bishnu Prasadh Chaudhary"]
        )
        self.assertEqual(self.subject_names(payload), ["Web Technology"])

        # Teachers who belong only to another classroom never appear.
        self.assertNotIn("Rahul Shakya", self.teacher_names(payload))
        self.assertNotIn("Sujan Dhakal", self.teacher_names(payload))
        self.assertNotIn("Dipa Gurung", self.teacher_names(payload))
        self.assertNotIn("Numerical Method", self.subject_names(payload))
        self.assertNotIn("Scripting Language", self.subject_names(payload))
        self.assertNotIn("DSA", self.subject_names(payload))

    def test_bishnu_carries_only_his_bca2_subject_for_rachana(self):
        payload = self.dashboard(self.rachana)
        bishnu = payload["teachers"][0]

        self.assertEqual(bishnu["name"], "Bishnu Prasadh Chaudhary")
        self.assertEqual([s["name"] for s in bishnu["subjects"]], ["Web Technology"])
        # Scripting Language is his BCA 4th Sem assignment, so it must not
        # reach a BCA 2nd Sem student.
        self.assertNotIn(
            "Scripting Language", [s["name"] for s in bishnu["subjects"]]
        )

    def test_bca4_student_sees_only_bca4_teachers_and_subjects(self):
        payload = self.dashboard(self.deepa)

        self.assertEqual(payload["classroom"]["name"], "BCA 4th Sem")
        self.assertEqual(
            self.teacher_names(payload),
            ["Bishnu Prasadh Chaudhary", "Rahul Shakya", "Sujan Dhakal"],
        )
        self.assertEqual(
            self.subject_names(payload),
            ["DBMS", "Numerical Method", "Operating System", "Scripting Language"],
        )
        # Bishnu's BCA 2nd Sem subject does not leak into BCA 4th Sem.
        bishnu = next(
            t for t in payload["teachers"] if t["name"] == "Bishnu Prasadh Chaudhary"
        )
        self.assertEqual([s["name"] for s in bishnu["subjects"]], ["Scripting Language"])

    def test_attendance_is_limited_to_own_classroom_and_own_records(self):
        rachana = self.dashboard(self.rachana)
        ids = [r["id"] for r in rachana["records"]]

        self.assertEqual(ids, [self.rows[self.rachana.id][0].id])
        self.assertTrue(all(r["classroom_id"] == self.bca2.id for r in rachana["records"]))
        self.assertTrue(all(r["student_id"] == self.rachana.id for r in rachana["records"]))
        self.assertEqual({r["subject_name"] for r in rachana["records"]}, {"Web Technology"})

        # Deepa's own classroom rows plus the legacy row for her own subject.
        deepa = self.dashboard(self.deepa)
        deepa_ids = [r["id"] for r in deepa["records"]]
        self.assertIn(self.rows[self.deepa.id][0].id, deepa_ids)
        self.assertIn(self.legacy.id, deepa_ids)
        self.assertNotIn(self.rows[self.deepa.id][1].id, deepa_ids)
        self.assertTrue(all(r["student_id"] == self.deepa.id for r in deepa["records"]))

    def test_attendance_endpoint_is_scoped_for_a_student(self):
        rows = json.loads(
            self.client.get(f"/attendance/?student_id={self.rachana.id}").content
        )

        self.assertEqual([r["id"] for r in rows], [self.rows[self.rachana.id][0].id])
        self.assertTrue(all(r["classroom_id"] == self.bca2.id for r in rows))

    def test_teacher_and_admin_reads_keep_their_explicit_scope(self):
        # An explicit classroom filter is still honoured as asked.
        explicit = json.loads(
            self.client.get(
                f"/attendance/?student_id={self.rachana.id}&classroom_id={self.bca4.id}"
            ).content
        )
        self.assertEqual([r["id"] for r in explicit], [self.rows[self.rachana.id][1].id])

        # Teacher reads require both a valid teaching assignment and enrollment.
        by_teacher = json.loads(
            self.client.get(f"/attendance/?teacher_id={self.bishnu.id}").content
        )
        self.assertEqual([r["id"] for r in by_teacher], [self.rows[self.rachana.id][0].id])

    def test_no_duplicate_teachers_or_subjects(self):
        for student in (self.rachana, self.deepa):
            payload = self.dashboard(student)
            teacher_ids = [t["id"] for t in payload["teachers"]]
            subject_ids = [s["id"] for s in payload["subjects"]]
            self.assertEqual(len(teacher_ids), len(set(teacher_ids)))
            self.assertEqual(len(subject_ids), len(set(subject_ids)))

        self.assertEqual(Teacher.objects.count(), 4)
        self.assertEqual(Student.objects.count(), 3)
        self.assertEqual(Subject.objects.count(), 6)

    def test_student_enrolled_later_automatically_gets_that_classroom(self):
        # Asha has no classroom yet: nothing is invented for her.
        payload = self.dashboard(self.asha)
        self.assertIsNone(payload["classroom"])
        self.assertEqual(payload["classrooms"], [])
        self.assertEqual(payload["teachers"], [])
        self.assertEqual(payload["subjects"], [])
        self.assertEqual(payload["records"], [])

        # Enrolling her changes the answer with no code change.
        self.bca3.students.add(self.asha)
        payload = self.dashboard(self.asha)
        self.assertEqual(payload["classroom"]["name"], "BCA 3rd Sem")
        self.assertEqual(self.teacher_names(payload), ["Dipa Gurung"])
        self.assertEqual(self.subject_names(payload), ["DSA"])

    def test_moving_a_student_switches_the_whole_dashboard(self):
        self.bca2.students.remove(self.rachana)
        self.bca4.students.add(self.rachana)

        payload = self.dashboard(self.rachana)
        self.assertEqual(payload["classroom"]["name"], "BCA 4th Sem")
        self.assertIn("Rahul Shakya", self.teacher_names(payload))
        self.assertIn("Scripting Language", self.subject_names(payload))
        self.assertEqual(
            [r["id"] for r in payload["records"]], [self.rows[self.rachana.id][1].id]
        )

    def test_unknown_student_is_not_found(self):
        self.assertEqual(
            self.client.get("/students/999999/dashboard/").status_code, 404
        )

    def test_dashboard_rejects_writes(self):
        response = self.client.post(
            f"/students/{self.rachana.id}/dashboard/", "{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 405)

