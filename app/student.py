from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.decorators import student_required
from app.models import Complaint, FinalResult, Grade, Module
from app.services import module_average

student_bp = Blueprint("student", __name__)


@student_bp.get("/")
@student_required
def dashboard():
    student = current_user.student
    modules = Module.query.filter_by(active=True).order_by(Module.name).all()
    rows = []
    for module in modules:
        grades = [grade for grade in student.grades if grade.module_id == module.id and grade.published]
        by_assessment = {grade.assessment.name: grade.display_value for grade in grades}
        complete = len(grades) == 4 and all(grade.value is not None for grade in grades)
        average = module_average(student.id, module.id) if complete else None
        rows.append((module, by_assessment, average))
    result = FinalResult.query.filter_by(student_id=student.id).first()
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
