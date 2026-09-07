from decimal import Decimal

from app import db
from app.models import Assessment, FinalResult, Grade


def module_average(student_id, module_id):
    grades = Grade.query.filter_by(student_id=student_id, module_id=module_id).all()
    if not grades or any(grade.value is None for grade in grades):
        return None
    total = sum((Decimal(grade.value) * Decimal(grade.assessment.weight) / Decimal(100)) for grade in grades)
    return total.quantize(Decimal("0.01"))


def refresh_result(student):
    module_ids = {grade.module_id for grade in student.grades}
    averages = [module_average(student.id, module_id) for module_id in module_ids]
    averages = [average for average in averages if average is not None]
    result = FinalResult.query.filter_by(student_id=student.id).first()
    if not result:
        result = FinalResult(student_id=student.id)
        db.session.add(result)
    result.average = (sum(averages) / len(averages)).quantize(Decimal("0.01")) if averages else None
    result.status = "APROVADO" if result.average is not None and result.average >= 10 else ("REPROVADO" if result.average is not None else "PENDENTE")
    return result


def ensure_assessments(module):
    defaults = [("Avaliação 1", Decimal("20")), ("Avaliação 2", Decimal("20")), ("Avaliação 3", Decimal("20")), ("Prova Final", Decimal("40"))]
    existing = {assessment.name for assessment in module.assessments}
    for name, weight in defaults:
        if name not in existing:
            db.session.add(Assessment(module=module, name=name, weight=weight))
