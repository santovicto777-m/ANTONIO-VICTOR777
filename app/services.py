from decimal import Decimal

from app import db
from app.models import Assessment, FinalResult, Grade, Module


def module_average(student_id, module_id):
    assessments = Assessment.query.filter_by(module_id=module_id).all()
    grades = {grade.assessment_id: grade for grade in Grade.query.filter_by(student_id=student_id, module_id=module_id).all()}
    if not assessments or any(assessment.id not in grades or grades[assessment.id].value is None for assessment in assessments):
        return None
    total = sum((Decimal(grades[assessment.id].value) * Decimal(assessment.weight) / Decimal(100)) for assessment in assessments)
    return total.quantize(Decimal("0.01"))


def refresh_result(student):
    module_ids = [module.id for module in Module.query.filter_by(active=True).all()]
    averages = [module_average(student.id, module_id) for module_id in module_ids]
    complete = bool(averages) and all(average is not None for average in averages)
    result = FinalResult.query.filter_by(student_id=student.id).first()
    if not result:
        result = FinalResult(student_id=student.id)
        db.session.add(result)
    result.average = (sum(averages) / len(averages)).quantize(Decimal("0.01")) if complete else None
    result.status = "APROVADO" if result.average is not None and result.average >= 10 else ("REPROVADO" if result.average is not None else "PENDENTE")
    return result


def ensure_assessments(module):
    defaults = [("Avaliação 1", Decimal("20")), ("Avaliação 2", Decimal("20")), ("Avaliação 3", Decimal("20")), ("Prova Final", Decimal("40"))]
    existing = {assessment.name for assessment in module.assessments}
    for name, weight in defaults:
        if name not in existing:
            db.session.add(Assessment(module=module, name=name, weight=weight))
