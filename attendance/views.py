import json
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Student, Teacher, Admin, Subject, Classroom, Attendance


def conflict_response(message):
    return JsonResponse({"success": False, "message": message}, status=400)


def not_found_response(message):
    return JsonResponse({"success": False, "message": message}, status=404)


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


@csrf_exempt
def students(request):
    if request.method == "POST":
        data = json.loads(request.body)
        try:
            Student.objects.create(
                name=data["name"],
                email=data["email"],
                password=data["password"],
            )
        except IntegrityError:
            return conflict_response("A student with this email already exists.")
        return JsonResponse({"success": True, "message": "Student added"})

    if request.method == "PUT":
        data = json.loads(request.body)
        try:
            student = Student.objects.get(id=data["id"])
        except ObjectDoesNotExist:
            return not_found_response("Student not found.")
        student.name = data["name"]
        student.email = data["email"]

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
        {"id": s.id, "name": s.name, "email": s.email}
        for s in Student.objects.all()
    ], safe=False)


@csrf_exempt
def teachers(request):
    if request.method == "POST":
        data = json.loads(request.body)
        try:
            Teacher.objects.create(
                name=data["name"],
                email=data["email"],
                phone=data.get("phone", ""),
                password=data["password"],
            )
        except IntegrityError:
            return conflict_response("A teacher with this email already exists.")
        return JsonResponse({"success": True, "message": "Teacher added"})

    if request.method == "PUT":
        data = json.loads(request.body)
        try:
            teacher = Teacher.objects.get(id=data["id"])
        except ObjectDoesNotExist:
            return not_found_response("Teacher not found.")

        teacher.name = data["name"]
        teacher.email = data["email"]
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
        {
            "id": t.id,
            "name": t.name,
            "email": t.email,
            "phone": t.phone,
        }
        for t in Teacher.objects.all()
    ], safe=False)


@csrf_exempt
def subjects(request):
    if request.method == "POST":
        data = json.loads(request.body)
        Subject.objects.create(name=data["name"])
        return JsonResponse({"success": True, "message": "Subject added"})

    if request.method == "PUT":
        data = json.loads(request.body)
        try:
            subject = Subject.objects.get(id=data["id"])
        except ObjectDoesNotExist:
            return not_found_response("Subject not found.")
        subject.name = data["name"]
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
        Classroom.objects.create(name=data["name"])
        return JsonResponse({"success": True, "message": "Classroom added"})

    if request.method == "PUT":
        data = json.loads(request.body)
        try:
            classroom = Classroom.objects.get(id=data["id"])
        except ObjectDoesNotExist:
            return not_found_response("Classroom not found.")
        classroom.name = data["name"]
        classroom.save()
        return JsonResponse({"success": True, "message": "Classroom updated"})

    if request.method == "DELETE":
        data = json.loads(request.body)
        deleted, _ = Classroom.objects.filter(id=data["id"]).delete()
        if not deleted:
            return not_found_response("Classroom not found.")
        return JsonResponse({"success": True, "message": "Classroom deleted"})

    return JsonResponse([
        {"id": c.id, "name": c.name}
        for c in Classroom.objects.all()
    ], safe=False)


@csrf_exempt
def records(request):
    if request.method == "POST":
        data = json.loads(request.body)

        Attendance.objects.create(
            teacher_id=data["teacher_id"],
            student_id=data["student_id"],
            subject_id=data["subject_id"],
            date=data["date"],
            present=data["present"],
        )

        return JsonResponse({"success": True})

    teacher = request.GET.get("teacher_id")
    student = request.GET.get("student_id")

    rows = Attendance.objects.all()

    if teacher:
        rows = rows.filter(teacher_id=teacher)

    if student:
        rows = rows.filter(student_id=student)

    return JsonResponse([
        {
            "id": a.id,
            "teacher_id": a.teacher_id,
            "student_id": a.student_id,
            "subject_id": a.subject_id,
            "date": a.date,
            "present": a.present,
        }
        for a in rows
    ], safe=False)