import json
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import (
    Student,
    Teacher,
    Admin,
    Subject,
    Classroom,
    TeachingAssignment,
    Attendance,
)


def conflict_response(message):
    return JsonResponse({"success": False, "message": message}, status=400)


def not_found_response(message):
    return JsonResponse({"success": False, "message": message}, status=404)


def method_not_allowed():
    return JsonResponse(
        {"success": False, "message": "Method not allowed."}, status=405
    )


def read_body(request):
    try:
        return json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return {}


def required_id(data, key):
    value = data.get(key)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def serialize_person(person):
    return {
        "id": person.id,
        "name": person.name,
        "email": person.email,
        "phone": person.phone,
    }


def serialize_attendance(record):
    return {
        "id": record.id,
        "teacher_id": record.teacher_id,
        "student_id": record.student_id,
        "subject_id": record.subject_id,
        "subject_name": record.subject.name,
        "teacher_name": record.teacher.name if record.teacher_id else None,
        "classroom_id": record.classroom_id,
        "date": record.date,
        "present": record.present,
    }


def get_student_or_none(student_id):
    try:
        return Student.objects.get(id=student_id)
    except (ObjectDoesNotExist, ValueError, TypeError):
        return None


def student_classrooms(student):
    """The classroom(s) a student is enrolled in.

    This is the single place the logged-in student's classroom is resolved,
    so every student facing read is scoped the same way.
    """
    return list(student.classrooms.all().order_by("name"))


def classroom_scoped_attendance(student, classrooms):
    """Attendance a student is allowed to see.

    A student only ever sees their own rows, and only the ones belonging to
    their own classroom. Rows recorded for a classroom the student is not
    enrolled in are dropped, so no other semester leaks into the dashboard.

    Rows written before the classroom column existed carry no classroom, so
    they are kept only when the subject itself belongs to one of the
    student's classrooms. Everything else stays out.
    """
    if student is None or not classrooms:
        return Attendance.objects.none()

    return (
        Attendance.objects.filter(student=student)
        .filter(
            Q(classroom__in=classrooms)
            | Q(classroom__isnull=True, subject__classrooms__in=classrooms)
        )
        .select_related("subject", "teacher")
        .distinct()
    )


@csrf_exempt
def login(request):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Method not allowed."}, status=405
        )

    data = json.loads(request.body)

    email = data["email"]
    password = data["password"]
    user_type = data["user_type"]

    if user_type == "student":
        user = Student.objects.filter(email=email, password=password).first()
    elif user_type == "teacher":
        user = Teacher.objects.filter(email=email, password=password).first()
    else:
        user = Admin.objects.filter(email=email, password=password).first()

    if user:
        return JsonResponse({
            "success": True,
            "user_id": user.id,
            "name": user.name,
            "user_type": user_type,
        })

    return JsonResponse({
        "success": False,
        "message": "Invalid email or password",
    })


@csrf_exempt
def student_register(request):
    data = json.loads(request.body)

    try:
        Student.objects.create(
            name=data["name"],
            email=data["email"],
            password=data["password"],
        )
    except IntegrityError:
        return conflict_response("A student with this email already exists.")

    return JsonResponse({"success": True})


def assign_to_classroom(obj, field, classroom_id):
    """Optionally assign a freshly created record to a classroom.

    Returns (classroom, warning). The record is always created first, so an
    unusable classroom id never silently drops the new record.
    """
    if classroom_id in (None, ""):
        return None, ""
    classroom = get_classroom_or_none(classroom_id)
    if classroom is None:
        return None, "Classroom not found. Record saved without a classroom."
    getattr(classroom, field).add(obj)
    return classroom, ""


@csrf_exempt
def students(request):
    if request.method == "POST":
        data = json.loads(request.body)
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        if not name:
            return conflict_response("Enter a name.")
        if not email:
            return conflict_response("Enter an email.")
        try:
            student = Student.objects.create(
                name=name,
                email=email,
                phone=data.get("phone", ""),
                password=data["password"],
            )
        except IntegrityError:
            return conflict_response("A student with this email already exists.")

        classroom, warning = assign_to_classroom(
            student, "students", data.get("classroom_id")
        )
        message = warning or (
            f"{student.name} created and added to {classroom.name}"
            if classroom else "Student added"
        )
        return JsonResponse({"success": True, "message": message, "id": student.id})

    if request.method == "PUT":
        data = json.loads(request.body)
        try:
            student = Student.objects.get(id=data["id"])
        except (ObjectDoesNotExist, KeyError, ValueError, TypeError):
            return not_found_response("Student not found.")
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        if not name:
            return conflict_response("Enter a name.")
        if not email:
            return conflict_response("Enter an email.")
        student.name = name
        student.email = email
        student.phone = data.get("phone", student.phone)

        if data.get("password"):
            student.password = data["password"]

        try:
            student.save()
        except IntegrityError:
            return conflict_response("A student with this email already exists.")
        return JsonResponse({"success": True, "message": "Student updated"})

    if request.method == "DELETE":
        data = json.loads(request.body)
        deleted, _ = Student.objects.filter(id=data["id"]).delete()
        if not deleted:
            return not_found_response("Student not found.")
        return JsonResponse({"success": True, "message": "Student deleted"})

    return JsonResponse([
        {"id": s.id, "name": s.name, "email": s.email, "phone": s.phone}
        for s in Student.objects.all()
    ], safe=False)


@csrf_exempt
def teachers(request):
    if request.method == "POST":
        data = json.loads(request.body)
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        if not name:
            return conflict_response("Enter a name.")
        if not email:
            return conflict_response("Enter an email.")
        # The email identifies one teacher account, so an existing teacher is
        # reported with the id the caller has to assign instead of creating a
        # second account for the same person.
        existing = Teacher.objects.filter(email__iexact=email).first()
        if existing is not None:
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        f"{existing.name} ({existing.email}) already exists. "
                        "Assign this teacher to the classroom instead of "
                        "creating a new one."
                    ),
                    "existing_teacher_id": existing.id,
                    "existing_teacher_name": existing.name,
                },
                status=400,
            )
        try:
            teacher = Teacher.objects.create(
                name=name,
                email=email,
                phone=data.get("phone", ""),
                password=data["password"],
            )
        except IntegrityError:
            return conflict_response("A teacher with this email already exists.")

        classroom, warning = assign_to_classroom(
            teacher, "teachers", data.get("classroom_id")
        )
        message = warning or (
            f"{teacher.name} created and added to {classroom.name}"
            if classroom else "Teacher added"
        )
        return JsonResponse({"success": True, "message": message, "id": teacher.id})

    if request.method == "PUT":
        data = json.loads(request.body)
        try:
            teacher = Teacher.objects.get(id=data["id"])
        except (ObjectDoesNotExist, KeyError, ValueError, TypeError):
            return not_found_response("Teacher not found.")

        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        if not name:
            return conflict_response("Enter a name.")
        if not email:
            return conflict_response("Enter an email.")

        teacher.name = name
        teacher.email = email
        teacher.phone = data.get("phone", teacher.phone)

        if data.get("password"):
            teacher.password = data["password"]

        try:
            teacher.save()
        except IntegrityError:
            return conflict_response("A teacher with this email already exists.")
        return JsonResponse({"success": True, "message": "Teacher updated"})

    if request.method == "DELETE":
        data = json.loads(request.body)
        deleted, _ = Teacher.objects.filter(id=data["id"]).delete()
        if not deleted:
            return not_found_response("Teacher not found.")
        return JsonResponse({"success": True, "message": "Teacher deleted"})

    return JsonResponse([
        serialize_person(t)
        for t in Teacher.objects.order_by("name")
    ], safe=False)


@csrf_exempt
def subjects(request):
    if request.method == "POST":
        data = json.loads(request.body)
        name = (data.get("name") or "").strip()
        if not name:
            return conflict_response("Enter a subject name.")
        if Subject.objects.filter(name__iexact=name).exists():
            return conflict_response("A subject with this name already exists.")
        subject = Subject.objects.create(name=name)

        classroom, warning = assign_to_classroom(
            subject, "subjects", data.get("classroom_id")
        )
        message = warning or (
            f"{subject.name} created and added to {classroom.name}"
            if classroom else "Subject added"
        )
        return JsonResponse({"success": True, "message": message, "id": subject.id})

    if request.method == "PUT":
        data = json.loads(request.body)
        try:
            subject = Subject.objects.get(id=data["id"])
        except (ObjectDoesNotExist, KeyError, ValueError, TypeError):
            return not_found_response("Subject not found.")
        name = (data.get("name") or "").strip()
        if not name:
            return conflict_response("Enter a subject name.")
        if Subject.objects.filter(name__iexact=name).exclude(id=subject.id).exists():
            return conflict_response("A subject with this name already exists.")
        subject.name = name
        subject.save()
        return JsonResponse({"success": True, "message": "Subject updated"})

    if request.method == "DELETE":
        data = json.loads(request.body)
        deleted, _ = Subject.objects.filter(id=data["id"]).delete()
        if not deleted:
            return not_found_response("Subject not found.")
        return JsonResponse({"success": True, "message": "Subject deleted"})

    return JsonResponse([
        {"id": s.id, "name": s.name}
        for s in Subject.objects.all()
    ], safe=False)


@csrf_exempt
def classrooms(request):
    if request.method == "POST":
        data = json.loads(request.body)
        name = (data.get("name") or "").strip()
        if not name:
            return conflict_response("Enter a classroom name.")
        if Classroom.objects.filter(name__iexact=name).exists():
            return conflict_response("A classroom with this name already exists.")
        Classroom.objects.create(name=name)
        return JsonResponse({"success": True, "message": "Classroom added"})

    if request.method == "PUT":
        data = json.loads(request.body)
        try:
            classroom = Classroom.objects.get(id=data["id"])
        except (ObjectDoesNotExist, KeyError, ValueError, TypeError):
            return not_found_response("Classroom not found.")
        name = (data.get("name") or "").strip()
        if not name:
            return conflict_response("Enter a classroom name.")
        classroom.name = name
        classroom.save()
        return JsonResponse({"success": True, "message": "Classroom updated"})

    if request.method == "DELETE":
        data = json.loads(request.body)
        try:
            classroom = Classroom.objects.get(id=data["id"])
        except (ObjectDoesNotExist, KeyError, ValueError, TypeError):
            return not_found_response("Classroom not found.")
        # Only the classroom and its student/teacher/subject assignments are
        # removed. Students, teachers, subjects and attendance stay intact.
        classroom.delete()
        return JsonResponse({"success": True, "message": "Classroom deleted"})

    if request.method != "GET":
        return method_not_allowed()

    return JsonResponse([
        {
            "id": c.id,
            "name": c.name,
            "student_count": c.student_count,
            "teacher_count": c.teacher_count,
            "subject_count": c.subject_count,
        }
        for c in Classroom.objects.annotate(
            student_count=Count("students", distinct=True),
            teacher_count=Count("teachers", distinct=True),
            subject_count=Count("subjects", distinct=True),
        ).order_by("id")
    ], safe=False)


def get_classroom_or_none(classroom_id):
    try:
        return Classroom.objects.get(id=classroom_id)
    except (ObjectDoesNotExist, ValueError, TypeError):
        return None


def teaching_for(classroom, teacher, classroom_subjects):
    """(assigned, available) subject rows for one teacher in one classroom.

    Only this classroom's subjects are considered, so a subject the same
    teacher teaches in another classroom never leaks in here.
    """
    assigned_ids = set(
        TeachingAssignment.objects.filter(
            classroom=classroom, teacher=teacher
        ).values_list("subject_id", flat=True)
    )
    assigned = [row for row in classroom_subjects if row["id"] in assigned_ids]
    available = [row for row in classroom_subjects if row["id"] not in assigned_ids]
    return assigned, available


@csrf_exempt
def classroom_detail(request, classroom_id):
    if request.method != "GET":
        return method_not_allowed()

    classroom = get_classroom_or_none(classroom_id)
    if classroom is None:
        return not_found_response("Classroom not found.")

    students = classroom.students.all().order_by("name")
    teachers = classroom.teachers.all().order_by("name")
    subjects = classroom.subjects.all().order_by("name")
    subject_rows = [{"id": s.id, "name": s.name} for s in subjects]
    teacher_rows = []
    for teacher in teachers:
        assigned, available = teaching_for(classroom, teacher, subject_rows)
        teacher_rows.append(
            {**serialize_person(teacher), "subjects": assigned,
             "available_subjects": available}
        )

    return JsonResponse({
        "id": classroom.id,
        "name": classroom.name,
        "student_count": students.count(),
        "teacher_count": teachers.count(),
        "subject_count": subjects.count(),
        "students": [serialize_person(s) for s in students],
        # Each teacher only carries the subjects they teach *here*. The same
        # teacher can teach other subjects in other classrooms.
        "teachers": teacher_rows,
        "subjects": subject_rows,
        "available_students": [
            {"id": s.id, "name": s.name, "email": s.email}
            for s in Student.objects.exclude(
                id__in=classroom.students.values_list("id", flat=True)
            ).order_by("name")
        ],
        "available_teachers": [
            {"id": t.id, "name": t.name, "email": t.email}
            for t in Teacher.objects.exclude(
                id__in=classroom.teachers.values_list("id", flat=True)
            ).order_by("name")
        ],
        "available_subjects": [
            {"id": s.id, "name": s.name}
            for s in Subject.objects.exclude(
                id__in=classroom.subjects.values_list("id", flat=True)
            ).order_by("name")
        ],
    })


def _membership(request, classroom_id, model, field, id_key, label):
    """Shared GET/POST/DELETE handler for a classroom membership list.

    GET    -> records currently assigned to the classroom
    POST   -> assign an existing record (never creates a new one)
    DELETE -> remove only the assignment; the record itself is kept
    """
    classroom = get_classroom_or_none(classroom_id)
    if classroom is None:
        return not_found_response("Classroom not found.")

    if request.method == "GET":
        assigned = getattr(classroom, field).all().order_by("name")
        if model is Subject:
            rows = [{"id": o.id, "name": o.name} for o in assigned]
        else:
            rows = [serialize_person(o) for o in assigned]
        return JsonResponse({
            "success": True,
            "classroom_id": classroom.id,
            "classroom_name": classroom.name,
            "count": len(rows),
            id_key.replace("_id", "s"): rows,
        })

    if request.method not in ("POST", "DELETE"):
        return method_not_allowed()

    data = read_body(request)
    object_id = required_id(data, id_key)
    if object_id is None:
        return conflict_response(f"Provide a valid {label} id.")

    try:
        obj = model.objects.get(id=object_id)
    except ObjectDoesNotExist:
        return not_found_response(f"{label} not found.")

    relation = getattr(classroom, field)

    if request.method == "POST":
        if relation.filter(id=obj.id).exists():
            return conflict_response(
                f"{obj.name} is already assigned to {classroom.name}."
            )
        relation.add(obj)
        return JsonResponse({
            "success": True,
            "message": f"{obj.name} added to {classroom.name}.",
        })

    if not relation.filter(id=obj.id).exists():
        return not_found_response(
            f"{obj.name} is not assigned to {classroom.name}."
        )

    relation.remove(obj)
    return JsonResponse({
        "success": True,
        "message": f"{obj.name} removed from {classroom.name}.",
    })


@csrf_exempt
def classroom_students(request, classroom_id):
    return _membership(
        request, classroom_id, Student, "students", "student_id", "Student"
    )


@csrf_exempt
def classroom_teachers(request, classroom_id):
    return _membership(
        request, classroom_id, Teacher, "teachers", "teacher_id", "Teacher"
    )


@csrf_exempt
def classroom_subjects(request, classroom_id):
    return _membership(
        request, classroom_id, Subject, "subjects", "subject_id", "Subject"
    )


@csrf_exempt
def classroom_teacher_subjects(request, classroom_id, teacher_id):
    """GET/POST/DELETE for one teacher's teaching inside one classroom.

    The classroom, the teacher and the subject together are the assignment, so
    the same teacher can hold different subjects in different classrooms.

    GET    -> the subjects this teacher teaches in this classroom, plus the
             classroom subjects not yet assigned to them
    POST   -> assign a subject of this classroom to this teacher
    DELETE -> drop that one assignment; teacher, subject and attendance stay
    """
    classroom = get_classroom_or_none(classroom_id)
    if classroom is None:
        return not_found_response("Classroom not found.")

    try:
        teacher = Teacher.objects.get(id=teacher_id)
    except (ObjectDoesNotExist, ValueError, TypeError):
        return not_found_response("Teacher not found.")

    classroom_subject_rows = [
        {"id": s.id, "name": s.name}
        for s in classroom.subjects.all().order_by("name")
    ]
    assigned, available = teaching_for(classroom, teacher, classroom_subject_rows)

    if request.method == "GET":
        return JsonResponse({
            "success": True,
            "classroom_id": classroom.id,
            "classroom_name": classroom.name,
            "teacher_id": teacher.id,
            "teacher_name": teacher.name,
            "count": len(assigned),
            "subjects": assigned,
            "available_subjects": available,
        })

    if request.method not in ("POST", "DELETE"):
        return method_not_allowed()

    data = read_body(request)
    subject_id = required_id(data, "subject_id")
    if subject_id is None:
        return conflict_response("Provide a valid subject id.")

    try:
        subject = Subject.objects.get(id=subject_id)
    except ObjectDoesNotExist:
        return not_found_response("Subject not found.")

    if request.method == "POST":
        # The subject has to belong to this classroom, otherwise the
        # assignment would not describe what is taught here.
        if not classroom.subjects.filter(id=subject.id).exists():
            return conflict_response(
                f"Add {subject.name} to {classroom.name} before assigning it."
            )
        if not classroom.teachers.filter(id=teacher.id).exists():
            return conflict_response(
                f"Add {teacher.name} to {classroom.name} before assigning subjects."
            )
        _, created = TeachingAssignment.objects.get_or_create(
            classroom=classroom, teacher=teacher, subject=subject
        )
        if not created:
            return conflict_response(
                f"{teacher.name} already teaches {subject.name} in {classroom.name}."
            )
        return JsonResponse({
            "success": True,
            "message": (
                f"{subject.name} assigned to {teacher.name} in {classroom.name}."
            ),
        })

    deleted, _ = TeachingAssignment.objects.filter(
        classroom=classroom, teacher=teacher, subject=subject
    ).delete()
    if not deleted:
        return not_found_response(
            f"{teacher.name} does not teach {subject.name} in {classroom.name}."
        )
    return JsonResponse({
        "success": True,
        "message": (
            f"{subject.name} removed from {teacher.name} in {classroom.name}."
        ),
    })


@csrf_exempt
def teacher_classrooms(request, teacher_id):
    """Classrooms this teacher is assigned to, for the teacher's own picker."""
    try:
        teacher = Teacher.objects.get(id=teacher_id)
    except (ObjectDoesNotExist, ValueError, TypeError):
        return not_found_response("Teacher not found.")

    rooms = teacher.classrooms.order_by("name")
    return JsonResponse({
        "success": True,
        "teacher_id": teacher.id,
        "teacher_name": teacher.name,
        "classrooms": [{"id": c.id, "name": c.name} for c in rooms],
    })


@csrf_exempt
def student_dashboard(request, student_id):
    """Dashboard payload for one student, scoped to that student's classroom.

    The classroom is resolved from the student record, never from the request
    and never from a classroom name. Everything returned below it is read
    through that classroom, so a teacher or subject belonging only to another
    semester can never appear here.
    """
    if request.method != "GET":
        return method_not_allowed()

    student = get_student_or_none(student_id)
    if student is None:
        return not_found_response("Student not found.")

    classrooms = student_classrooms(student)

    # Teaching is classroom specific, so the pairs are grouped per classroom
    # and the same teacher keeps a different subject list in each one.
    assignments = (
        TeachingAssignment.objects.filter(classroom__in=classrooms)
        .select_related("subject")
        .order_by("teacher__name", "subject__name")
    )
    subjects_by_teacher = {}
    for assignment in assignments:
        subjects_by_teacher.setdefault(assignment.teacher_id, []).append(
            {"id": assignment.subject_id, "name": assignment.subject.name}
        )

    teacher_rows, seen_teachers = [], set()
    subject_rows, seen_subjects = [], set()
    for classroom in classrooms:
        for teacher in classroom.teachers.all().order_by("name"):
            if teacher.id in seen_teachers:
                continue
            seen_teachers.add(teacher.id)
            teacher_rows.append({
                **serialize_person(teacher),
                "subjects": subjects_by_teacher.get(teacher.id, []),
            })
        for subject in classroom.subjects.all().order_by("name"):
            if subject.id in seen_subjects:
                continue
            seen_subjects.add(subject.id)
            subject_rows.append({"id": subject.id, "name": subject.name})

    records = classroom_scoped_attendance(student, classrooms).order_by("date", "id")

    return JsonResponse({
        "success": True,
        "student": serialize_person(student),
        "classrooms": [{"id": c.id, "name": c.name} for c in classrooms],
        "classroom": (
            {"id": classrooms[0].id, "name": classrooms[0].name}
            if len(classrooms) == 1 else None
        ),
        "teachers": teacher_rows,
        "subjects": subject_rows,
        "records": [serialize_attendance(a) for a in records],
    })


@csrf_exempt
def records(request):
    if request.method == "POST":
        data = json.loads(request.body)

        Attendance.objects.create(
            teacher_id=data["teacher_id"],
            student_id=data["student_id"],
            subject_id=data["subject_id"],
            classroom_id=data.get("classroom_id") or None,
            date=data["date"],
            present=data["present"],
        )

        return JsonResponse({"success": True})

    teacher = request.GET.get("teacher_id")
    student = request.GET.get("student_id")
    classroom = request.GET.get("classroom_id")

    if student and not classroom:
        # A student scoped read is locked to that student's own classrooms.
        # The classroom comes from the student record, so another semester's
        # rows are dropped by the query rather than filtered out downstream.
        student_row = get_student_or_none(student)
        rows = classroom_scoped_attendance(
            student_row, student_classrooms(student_row) if student_row else []
        )
        if teacher:
            rows = rows.filter(teacher_id=teacher)
        return JsonResponse([serialize_attendance(a) for a in rows], safe=False)

    rows = Attendance.objects.all()

    if teacher:
        rows = rows.filter(teacher_id=teacher)

    if student:
        rows = rows.filter(student_id=student)

    if classroom:
        rows = rows.filter(classroom_id=classroom)

    return JsonResponse([serialize_attendance(a) for a in rows], safe=False)
