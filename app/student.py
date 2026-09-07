from flask import Blueprint, render_template
from flask_login import current_user

from app.decorators import student_required
from app.models import FinalResult, Module
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
    return render_template("student/dashboard.html", student=student, rows=rows, result=result,
                           completed=sum(average is not None for _, _, average in rows), pending=sum(average is None for _, _, average in rows))
