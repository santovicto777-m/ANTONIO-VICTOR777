from io import BytesIO

from flask import abort, Blueprint, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app import db
from app.decorators import student_required
from app.models import Complaint, FinalResult, Grade, Module, Student
from app.services import module_average, refresh_result

student_bp = Blueprint("student", __name__)


@student_bp.get("/foto/<int:student_id>")
@login_required
def profile_photo(student_id):
    student = db.get_or_404(Student, student_id)
    if not current_user.is_admin and current_user.student.id != student.id:
        abort(403)
    if not student.profile_photo_data:
        abort(404)
    return send_file(BytesIO(student.profile_photo_data), mimetype=student.profile_photo_mimetype or "application/octet-stream")


@student_bp.get("/")
@student_required
def dashboard():
    student = current_user.student
    result = refresh_result(student)
    db.session.commit()
    modules = Module.query.filter_by(active=True).order_by(Module.name).all()
    rows = []
    for module in modules:
        grades = [grade for grade in student.grades if grade.module_id == module.id and grade.published]
        by_assessment = {grade.assessment.name: grade for grade in grades}
        complete = len(grades) == 4 and all(grade.value is not None for grade in grades)
        average = module_average(student.id, module.id) if complete else None
        rows.append((module, by_assessment, average))
    published_grades = Grade.query.filter_by(student_id=student.id, published=True).order_by(Grade.updated_at.desc()).all()
    complaints = Complaint.query.filter_by(student_id=student.id).order_by(Complaint.created_at.desc()).all()
    return render_template("student/dashboard.html", student=student, rows=rows, result=result,
                           published_grades=published_grades, complaints=complaints,
                           completed=sum(average is not None for _, _, average in rows), pending=sum(average is None for _, _, average in rows))


@student_bp.post("/reclamacoes")
@student_required
def create_complaint():
    student = current_user.student
    grade = db.session.get(Grade, request.form.get("grade_id", type=int))
    message = request.form.get("message", "").strip()
    if not grade or grade.student_id != student.id or not grade.published:
        flash("Só é possível reclamar de uma nota publicada sua.", "error")
    elif not message or len(message) > 2000:
        flash("Escreva uma reclamação com até 2000 caracteres.", "error")
    else:
        db.session.add(Complaint(student=student, grade=grade, message=message))
        db.session.commit()
        flash("Reclamação enviada para análise.", "success")
    return redirect(url_for("student.dashboard"))
