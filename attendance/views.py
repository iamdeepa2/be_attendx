"""JSON API for the attendance app.

The frontend is a small SPA, so every endpoint here is a plain function view
that answers with JSON. Two ideas keep the file short:

* every response is built by ``ok`` / ``fail``, so the frontend can always read
  a single ``message`` field;
* students, teachers, subjects and classrooms only differ by a handful of
  details, so they share one CRUD handler described by the four short view
  functions in the "Simple records" section.
"""

import json

from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import Count, Exists, F, OuterRef, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_date

from .models import (
    Admin,
    Attendance,
    Classroom,
    Student,
    Subject,
    Teacher,
    TeachingAssignment,
)


# Responses -------------------------------------------------------------------

def ok(message="", **extra):
    return JsonResponse({"success": True, "message": message, **extra})


def fail(message, status=400, **extra):
    return JsonResponse({"success": False, "message": message, **extra}, status=status)


def not_found(message):
    return fail(message, 404)


def method_not_allowed():
    return fail("Method not allowed.", 405)


# Reading the request --------------------------------------------------------

def read_body(request):
    try:
        return json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return {}


def read_id(data, key):
    value = data.get(key)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def get_or_none(model, pk):
    try:
        return model.objects.get(id=pk)
    except (ObjectDoesNotExist, TypeError, ValueError):
        return None


# Serializing ----------------------------------------------------------------

def person_row(person):
    return {
        "id": person.id,
        "name": person.name,
        "email": person.email,
        "phone": person.phone,
    }


def name_row(obj):
    return {"id": obj.id, "name": obj.name}


def attendance_row(record):
    return {
        "id": record.id,
        "teacher_id": record.teacher_id,
        "student_id": record.student_id,
        "student_name": record.student.name,
        "subject_id": record.subject_id,
        "subject_name": record.subject.name,
        "teacher_name": record.teacher.name if record.teacher_id else None,
        "classroom_id": record.classroom_id,
        "date": record.date,
        "present": record.present,
    }


# Login ----------------------------------------------------------------------

LOGIN_MODELS = {
    "student": Student,
    "teacher": Teacher,
    "admin": Admin,
}


@csrf_exempt
def login(request):
    if request.method != "POST":
        return method_not_allowed()

    data = read_body(request)
    user_type = data.get("user_type")
    model = LOGIN_MODELS.get(user_type, Admin)
    user = model.objects.filter(
        email=data.get("email"), password=data.get("password")
    ).first()

    if user is None:
        return fail("Invalid email or password")

    return ok(user_id=user.id, name=user.name, user_type=user_type)


@csrf_exempt
def student_register(request):
    data = read_body(request)
    try:
        Student.objects.create(
            name=data["name"],
            email=data["email"],
            password=data["password"],
        )
    except IntegrityError:
        return fail("A student with this email already exists.")
    return ok()


# The shared CRUD handler ----------------------------------------------------
#
# `contact` marks the records that carry an email, a phone and a password;
# `unique_name` marks the records whose name has to stay unique; the rest of
# the behaviour is identical for all four.

def crud(request, model, *, label, name_label, contact=False,
         unique_name=False, classroom_field=None, order_by=None,
         list_rows=None, on_duplicate=None):
    """List, create, update and delete one kind of simple record."""

    if request.method == "GET":
        rows = model.objects.all()
        if order_by:
            rows = rows.order_by(order_by)
        if list_rows:
            return JsonResponse(list_rows(rows), safe=False)
        to_row = person_row if contact else name_row
        return JsonResponse([to_row(o) for o in rows], safe=False)

    data = read_body(request)

    if request.method == "POST":
        return create_record(
            model, data, label, name_label,
            contact=contact,
            unique_name=unique_name,
            classroom_field=classroom_field,
            on_duplicate=on_duplicate,
        )

    if request.method == "PUT":
        return update_record(
            model, data, label, name_label,
            contact=contact,
            unique_name=unique_name,
        )

    if request.method == "DELETE":
        deleted, _ = model.objects.filter(id=read_id(data, "id")).delete()
        if not deleted:
            return not_found(f"{label} not found.")
        return ok(f"{label} deleted")

    return method_not_allowed()


def create_record(model, data, label, name_label, *, contact, unique_name,
                  classroom_field, on_duplicate):
    name = (data.get("name") or "").strip()
    if not name:
        return fail(f"Enter a {name_label}.")

    email = (data.get("email") or "").strip() if contact else ""
    if contact and not email:
        return fail("Enter an email.")

    # A duplicate that is worth pointing at, rather than a plain rejection.
    if on_duplicate:
        reply = on_duplicate(model, email)
        if reply is not None:
            return reply

    if unique_name and model.objects.filter(name__iexact=name).exists():
        return fail(f"A {label.lower()} with this name already exists.")

    fields = {"name": name}
    if contact:
        fields.update(
            email=email,
            phone=data.get("phone", ""),
            password=data["password"],
        )
    try:
        obj = model.objects.create(**fields)
    except IntegrityError:
        return fail(f"A {label.lower()} with this email already exists.")

    # The record is created first, so an unusable classroom id never drops it.
    classroom, warning = add_to_classroom(obj, classroom_field, data.get("classroom_id"))
    if warning:
        return ok(warning, id=obj.id)
    if classroom:
        return ok(f"{obj.name} created and added to {classroom.name}", id=obj.id)
    return ok(f"{label} added", id=obj.id)


def update_record(model, data, label, name_label, *, contact, unique_name):
    obj = get_or_none(model, data.get("id"))
    if obj is None:
        return not_found(f"{label} not found.")

    name = (data.get("name") or "").strip()
    if not name:
        return fail(f"Enter a {name_label}.")

    if unique_name and model.objects.filter(name__iexact=name).exclude(id=obj.id).exists():
        return fail(f"A {label.lower()} with this name already exists.")

    if contact:
        email = (data.get("email") or "").strip()
        if not email:
            return fail("Enter an email.")
        obj.email = email
        obj.phone = data.get("phone", obj.phone)
        # A blank password field means "keep the current one".
        if data.get("password"):
            obj.password = data["password"]

    obj.name = name
    try:
        obj.save()
    except IntegrityError:
        return fail(f"A {label.lower()} with this email already exists.")
    return ok(f"{label} updated")


def add_to_classroom(obj, field, classroom_id):
    """Attach a freshly created record to a classroom.

    Returns (classroom, warning); the record is always created first, so an
    unusable classroom id never silently drops it.
    """
    if not field or classroom_id in (None, ""):
        return None, ""
    classroom = get_or_none(Classroom, classroom_id)
    if classroom is None:
        return None, "Classroom not found. Record saved without a classroom."
    getattr(classroom, field).add(obj)
    return classroom, ""


def existing_teacher_reply(model, email):
    """The email identifies one teacher account, so an existing teacher is
    reported with the id to assign instead of a second account for the same
    person."""
    existing = model.objects.filter(email__iexact=email).first()
    if existing is None:
        return None
    return fail(
        f"{existing.name} ({existing.email}) already exists. "
        "Assign this teacher to the classroom instead of creating a new one.",
        existing_teacher_id=existing.id,
        existing_teacher_name=existing.name,
    )


def classroom_rows(classrooms):
    return [
        {
            "id": c.id,
            "name": c.name,
            "student_count": c.student_count,
            "teacher_count": c.teacher_count,
            "subject_count": c.subject_count,
        }
        for c in classrooms.annotate(
            student_count=Count("students", distinct=True),
            teacher_count=Count("teachers", distinct=True),
            subject_count=Count("subjects", distinct=True),
        ).order_by("id")
    ]


# Simple records -------------------------------------------------------------

@csrf_exempt
def students(request):
    return crud(
        request, Student,
        label="Student", name_label="name",
        contact=True, classroom_field="students",
    )


@csrf_exempt
def teachers(request):
    return crud(
        request, Teacher,
        label="Teacher", name_label="name",
        contact=True, classroom_field="teachers",
        order_by="name", on_duplicate=existing_teacher_reply,
    )


@csrf_exempt
def subjects(request):
    return crud(
        request, Subject,
        label="Subject", name_label="subject name",
        unique_name=True, classroom_field="subjects",
    )


@csrf_exempt
def classrooms(request):
    return crud(
        request, Classroom,
        label="Classroom", name_label="classroom name",
        unique_name=True, list_rows=classroom_rows,
    )


# Classrooms -----------------------------------------------------------------

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

    classroom = get_or_none(Classroom, classroom_id)
    if classroom is None:
        return not_found("Classroom not found.")

    students = classroom.students.all().order_by("name")
    teachers = classroom.teachers.all().order_by("name")
    subjects = classroom.subjects.all().order_by("name")
    subject_rows = [name_row(s) for s in subjects]

    # Each teacher only carries the subjects they teach *here*: the same
    # teacher can teach other subjects in other classrooms.
    teacher_rows = []
    for teacher in teachers:
        assigned, available = teaching_for(classroom, teacher, subject_rows)
        teacher_rows.append(
            {**person_row(teacher), "subjects": assigned,
             "available_subjects": available}
        )

    return ok(
        id=classroom.id,
        name=classroom.name,
        student_count=students.count(),
        teacher_count=teachers.count(),
        subject_count=subjects.count(),
        students=[person_row(s) for s in students],
        teachers=teacher_rows,
        subjects=subject_rows,
        available_students=available_people(Student, classroom.students),
        available_teachers=available_people(Teacher, classroom.teachers),
        available_subjects=available_names(Subject, classroom.subjects),
    )


def available_people(model, assigned):
    """Everyone of this kind who is *not* already in the classroom."""
    return [
        {"id": o.id, "name": o.name, "email": o.email}
        for o in model.objects.exclude(
            id__in=assigned.values_list("id", flat=True)
        ).order_by("name")
    ]


def available_names(model, assigned):
    """The same list for records that only have a name."""
    return [
        name_row(o)
        for o in model.objects.exclude(
            id__in=assigned.values_list("id", flat=True)
        ).order_by("name")
    ]


def membership(request, classroom_id, model, field, id_key, label):
    """Shared GET/POST/DELETE handler for a classroom membership list.

    GET    -> records currently assigned to the classroom
    POST   -> assign an existing record (never creates a new one)
    DELETE -> remove only the assignment; the record itself is kept
    """
    classroom = get_or_none(Classroom, classroom_id)
    if classroom is None:
        return not_found("Classroom not found.")

    if request.method == "GET":
        assigned = getattr(classroom, field).all().order_by("name")
        to_row = name_row if model is Subject else person_row
        rows = [to_row(o) for o in assigned]
        return ok(
            classroom_id=classroom.id,
            classroom_name=classroom.name,
            count=len(rows),
            **{id_key.replace("_id", "s"): rows},
        )

    if request.method not in ("POST", "DELETE"):
        return method_not_allowed()

    data = read_body(request)
    object_id = read_id(data, id_key)
    if object_id is None:
        return fail(f"Provide a valid {label} id.")

    obj = get_or_none(model, object_id)
    if obj is None:
        return not_found(f"{label} not found.")

    relation = getattr(classroom, field)
    assigned = relation.filter(id=obj.id).exists()

    if request.method == "POST":
        if assigned:
            return fail(f"{obj.name} is already assigned to {classroom.name}.")
        relation.add(obj)
        return ok(f"{obj.name} added to {classroom.name}.")

    if not assigned:
        return not_found(f"{obj.name} is not assigned to {classroom.name}.")

    relation.remove(obj)
    return ok(f"{obj.name} removed from {classroom.name}.")


@csrf_exempt
def classroom_students(request, classroom_id):
    return membership(
        request, classroom_id, Student, "students", "student_id", "Student"
    )


@csrf_exempt
def classroom_teachers(request, classroom_id):
    return membership(
        request, classroom_id, Teacher, "teachers", "teacher_id", "Teacher"
    )


@csrf_exempt
def classroom_subjects(request, classroom_id):
    return membership(
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
    classroom = get_or_none(Classroom, classroom_id)
    if classroom is None:
        return not_found("Classroom not found.")

    teacher = get_or_none(Teacher, teacher_id)
    if teacher is None:
        return not_found("Teacher not found.")

    classroom_subjects = [name_row(s) for s in classroom.subjects.all().order_by("name")]
    assigned, available = teaching_for(classroom, teacher, classroom_subjects)

    if request.method == "GET":
        return ok(
            classroom_id=classroom.id,
            classroom_name=classroom.name,
            teacher_id=teacher.id,
            teacher_name=teacher.name,
            count=len(assigned),
            subjects=assigned,
            available_subjects=available,
        )

    if request.method not in ("POST", "DELETE"):
        return method_not_allowed()

    subject_id = read_id(read_body(request), "subject_id")
    if subject_id is None:
        return fail("Provide a valid subject id.")

    subject = get_or_none(Subject, subject_id)
    if subject is None:
        return not_found("Subject not found.")

    if request.method == "POST":
        return assign_subject(classroom, teacher, subject)

    deleted, _ = TeachingAssignment.objects.filter(
        classroom=classroom, teacher=teacher, subject=subject
    ).delete()
    if not deleted:
        return not_found(
            f"{teacher.name} does not teach {subject.name} in {classroom.name}."
        )
    return ok(f"{subject.name} removed from {teacher.name} in {classroom.name}.")


def assign_subject(classroom, teacher, subject):
    """Both ends have to be in the classroom, otherwise the assignment would
    not describe what is actually taught here."""
    if not classroom.subjects.filter(id=subject.id).exists():
        return fail(f"Add {subject.name} to {classroom.name} before assigning it.")
    if not classroom.teachers.filter(id=teacher.id).exists():
        return fail(f"Add {teacher.name} to {classroom.name} before assigning subjects.")

    _, created = TeachingAssignment.objects.get_or_create(
        classroom=classroom, teacher=teacher, subject=subject
    )
    if not created:
        return fail(f"{teacher.name} already teaches {subject.name} in {classroom.name}.")
    return ok(f"{subject.name} assigned to {teacher.name} in {classroom.name}.")


def active_teaching(teacher_id):
    """Assignments are valid only while both memberships still exist."""
    return TeachingAssignment.objects.filter(
        teacher_id=teacher_id,
        classroom__teachers__id=teacher_id,
        subject__classrooms__id=F("classroom_id"),
    )


@csrf_exempt
def teacher_classrooms(request, teacher_id):
    if request.method != "GET":
        return method_not_allowed()
    teacher = get_or_none(Teacher, teacher_id)
    if teacher is None:
        return not_found("Teacher not found.")
    rooms = Classroom.objects.filter(
        id__in=active_teaching(teacher_id).values("classroom_id")
    ).order_by("name")
    return ok(
        teacher_id=teacher.id,
        teacher_name=teacher.name,
        classrooms=[name_row(c) for c in rooms],
    )


@csrf_exempt
def teacher_classroom(request, teacher_id, classroom_id):
    if request.method != "GET":
        return method_not_allowed()
    assignments = active_teaching(teacher_id).filter(classroom_id=classroom_id)
    if not assignments.exists():
        return fail("No teaching assignment for this classroom.", 403)
    classroom = Classroom.objects.get(id=classroom_id)
    subjects = Subject.objects.filter(id__in=assignments.values("subject_id")).order_by("name")
    return ok(
        teacher_id=teacher_id,
        classroom_id=classroom.id,
        subjects=[name_row(s) for s in subjects],
        students=[person_row(s) for s in classroom.students.order_by("name")],
    )


# Students -------------------------------------------------------------------

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
        .select_related("subject", "teacher", "student")
        .distinct()
    )


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

    student = get_or_none(Student, student_id)
    if student is None:
        return not_found("Student not found.")

    classrooms = student_classrooms(student)

    # Teaching is classroom specific, so the same teacher keeps a different
    # subject list in each classroom.
    subjects_by_teacher = {}
    assignments = TeachingAssignment.objects.filter(
        classroom__in=classrooms
    ).select_related("subject")
    for a in assignments:
        subjects_by_teacher.setdefault(a.teacher_id, []).append(
            {"id": a.subject_id, "name": a.subject.name}
        )

    # A teacher or subject in two of the student's classrooms is listed once.
    teachers, teacher_ids = [], set()
    subjects, subject_ids = [], set()
    for classroom in classrooms:
        for teacher in classroom.teachers.all().order_by("name"):
            if teacher.id not in teacher_ids:
                teacher_ids.add(teacher.id)
                teachers.append(teacher)
        for subject in classroom.subjects.all().order_by("name"):
            if subject.id not in subject_ids:
                subject_ids.add(subject.id)
                subjects.append(subject)

    records = classroom_scoped_attendance(student, classrooms).order_by("date", "id")

    return ok(
        student=person_row(student),
        classrooms=[name_row(c) for c in classrooms],
        # A single classroom can be named outright; several cannot.
        classroom=name_row(classrooms[0]) if len(classrooms) == 1 else None,
        teachers=[
            {**person_row(t), "subjects": subjects_by_teacher.get(t.id, [])}
            for t in teachers
        ],
        subjects=[name_row(s) for s in subjects],
        records=[attendance_row(a) for a in records],
    )


# Attendance -----------------------------------------------------------------

@csrf_exempt
def records(request):
    if request.method == "POST":
        data = read_body(request)
        if not isinstance(data, dict):
            return fail("Provide an attendance record.")
        teacher_id = read_id(data, "teacher_id")
        classroom_id = read_id(data, "classroom_id")
        subject_id = read_id(data, "subject_id")
        student_id = read_id(data, "student_id")
        if None in (teacher_id, classroom_id, subject_id, student_id):
            return fail("Teacher, classroom, subject and student are required.")
        if not active_teaching(teacher_id).filter(
            classroom_id=classroom_id, subject_id=subject_id
        ).exists():
            return fail("You are not assigned to teach this subject in this classroom.", 403)
        if not Student.objects.filter(id=student_id, classrooms__id=classroom_id).exists():
            return fail("Student is not enrolled in the selected classroom.", 403)
        try:
            date = parse_date(data.get("date", ""))
        except (TypeError, ValueError):
            date = None
        if date is None or not isinstance(data.get("present"), bool):
            return fail("Provide a valid date and a boolean attendance status.")
        Attendance.objects.create(
            teacher_id=teacher_id,
            student_id=student_id,
            subject_id=subject_id,
            classroom_id=classroom_id,
            date=date,
            present=data["present"],
        )
        return ok()

    if request.method != "GET":
        return method_not_allowed()

    teacher = request.GET.get("teacher_id")
    student = request.GET.get("student_id")
    classroom = request.GET.get("classroom_id")

    if student and not classroom:
        # A student scoped read is locked to that student's own classrooms.
        # The classroom comes from the student record, so another semester's
        # rows are dropped by the query rather than filtered out downstream.
        student_row = get_or_none(Student, student)
        rows = classroom_scoped_attendance(
            student_row, student_classrooms(student_row) if student_row else []
        )
    else:
        rows = Attendance.objects.select_related("subject", "teacher", "student")

    if teacher:
        teacher_row = get_or_none(Teacher, teacher)
        if teacher_row is None:
            return not_found("Teacher not found.")
        assignments = active_teaching(teacher_row.id).filter(
            classroom_id=OuterRef("classroom_id"), subject_id=OuterRef("subject_id")
        )
        enrolled = Student.objects.filter(
            id=OuterRef("student_id"), classrooms__id=OuterRef("classroom_id")
        )
        rows = rows.filter(teacher_id=teacher_row.id).filter(
            Exists(assignments), Exists(enrolled)
        )
    if student:
        rows = rows.filter(student_id=student)
    if classroom:
        rows = rows.filter(classroom_id=classroom)

    return JsonResponse([attendance_row(a) for a in rows], safe=False)
