from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for, send_file
from flask_login import current_user
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from app import db
from app.decorators import admin_required
from app.models import AuditLog, Assessment, Complaint, EnrollmentApplication, FinalResult, Grade, Module, Student, User
from app.services import ensure_assessments, module_average, refresh_result

admin_bp = Blueprint("admin", __name__)


def _save_profile_photo(file):
    if not file or not file.filename:
        return None
    extension = Path(file.filename).suffix.lower().lstrip(".")
    if extension not in current_app.config.get("PROFILE_ALLOWED_EXTENSIONS", {"jpg", "jpeg", "png", "webp"}):
        return None
    filename = f"{uuid4().hex}.{extension}"
    upload_folder = Path(current_app.config.get("PROFILE_UPLOAD_FOLDER", Path(current_app.instance_path) / "profile_uploads"))
    upload_folder.mkdir(parents=True, exist_ok=True)
    file.save(upload_folder / secure_filename(filename))
    file.stream.seek(0)
    return filename, file.stream.read(), file.mimetype


def _remove_profile_photo(filename):
    if filename:
        upload_folder = current_app.config.get("PROFILE_UPLOAD_FOLDER", Path(current_app.instance_path) / "profile_uploads")
        path = Path(upload_folder) / filename
        path.unlink(missing_ok=True)


def _number(value):
    try:
        number = Decimal(value.replace(",", "."))
        if number < 0 or number > 20:
            raise ValueError
        return number
    except (AttributeError, InvalidOperation, ValueError):
        return None


def _weight(value):
    try:
        number = Decimal(value.replace(",", "."))
        if number < 0 or number > 100:
            raise ValueError
        return number
    except (AttributeError, InvalidOperation, ValueError):
        return None


@admin_bp.get("/")
@admin_required
def dashboard():
    students = Student.query.count()
    modules = Module.query.filter_by(active=True).count()
    grades = Grade.query.filter(Grade.value.is_not(None)).count()
    results = FinalResult.query.all()
    approved = sum(result.status == "APROVADO" for result in results)
    failed = sum(result.status == "REPROVADO" for result in results)
    pending = max(len(results) - approved - failed, 0)
    applications = EnrollmentApplication.query.filter_by(status="PENDENTE").count()
    return render_template("admin/dashboard.html", students=students, modules=modules, grades=grades,
                           approved=approved, failed=failed, pending=pending,
                           result_total=len(results), applications=applications)


@admin_bp.route("/alunos", methods=["GET", "POST"])
@admin_required
def students():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        code = request.form.get("code", "").strip()
        name = request.form.get("full_name", "").strip()
        photo = request.files.get("profile_photo")
        if not username or not password or len(password) < 8 or not code or not name:
            flash("Preencha nome, código, utilizador e uma password com 8 caracteres.", "error")
        elif photo and photo.filename and Path(photo.filename).suffix.lower().lstrip(".") not in current_app.config.get("PROFILE_ALLOWED_EXTENSIONS", {"jpg", "jpeg", "png", "webp"}):
            flash("A foto deve estar no formato JPG, PNG ou WEBP.", "error")
        elif User.query.filter_by(username=username).first() or Student.query.filter_by(code=code).first():
            flash("O utilizador ou código já existe.", "error")
        else:
            user = User(username=username, role="student")
            user.set_password(password)
            photo_data = _save_profile_photo(photo)
            student = Student(code=code, full_name=name, birth_date=None, gender=request.form.get("gender"),
                              phone=request.form.get("phone"), email=request.form.get("email"), user=user)
            if photo_data:
                student.profile_photo, student.profile_photo_data, student.profile_photo_mimetype = photo_data
            db.session.add(student)
            db.session.commit()
            flash("Aluno criado com sucesso.", "success")
            return redirect(url_for("admin.students"))
    query = request.args.get("q", "").strip()
    students = Student.query.filter(or_(Student.full_name.ilike(f"%{query}%"), Student.code.ilike(f"%{query}%"))).order_by(Student.full_name).all() if query else Student.query.order_by(Student.full_name).all()
    return render_template("admin/students.html", students=students)


@admin_bp.post("/alunos/<int:student_id>/estado")
@admin_required
def toggle_student(student_id):
    student = db.get_or_404(Student, student_id)
    student.user.active = not student.user.active
    db.session.commit()
    return redirect(url_for("admin.students"))


@admin_bp.route("/alunos/<int:student_id>/editar", methods=["GET", "POST"])
@admin_required
def edit_student(student_id):
    student = db.get_or_404(Student, student_id)
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        code = request.form.get("code", "").strip()
        name = request.form.get("full_name", "").strip()
        duplicate_user = User.query.filter(User.username == username, User.id != student.user_id).first()
        duplicate_code = Student.query.filter(Student.code == code, Student.id != student.id).first()
        photo = request.files.get("profile_photo")
        if not username or not code or not name:
            flash("Preencha nome, código e utilizador.", "error")
        elif duplicate_user or duplicate_code:
            flash("O utilizador ou código já existe.", "error")
        elif photo and photo.filename and Path(photo.filename).suffix.lower().lstrip(".") not in current_app.config.get("PROFILE_ALLOWED_EXTENSIONS", {"jpg", "jpeg", "png", "webp"}):
            flash("A foto deve estar no formato JPG, PNG ou WEBP.", "error")
        else:
            new_photo = _save_profile_photo(photo)
            if new_photo:
                _remove_profile_photo(student.profile_photo)
                student.profile_photo, student.profile_photo_data, student.profile_photo_mimetype = new_photo
            student.full_name = name
            student.code = code
            student.email = request.form.get("email", "").strip() or None
            student.phone = request.form.get("phone", "").strip() or None
            student.gender = request.form.get("gender", "").strip() or None
            student.user.username = username
            password = request.form.get("password", "")
            if password:
                if len(password) < 8:
                    flash("A password deve ter pelo menos 8 caracteres.", "error")
                    return render_template("admin/edit_student.html", student=student)
                student.user.set_password(password)
            db.session.commit()
            flash("Dados do aluno atualizados.", "success")
            return redirect(url_for("admin.students"))
    return render_template("admin/edit_student.html", student=student)


@admin_bp.post("/alunos/<int:student_id>/eliminar")
@admin_required
def delete_student(student_id):
    student = db.get_or_404(Student, student_id)
    _remove_profile_photo(student.profile_photo)
    FinalResult.query.filter_by(student_id=student.id).delete(synchronize_session=False)
    db.session.delete(student)
    db.session.commit()
    flash("Aluno eliminado.", "success")
    return redirect(url_for("admin.students"))


@admin_bp.route("/modulos", methods=["GET", "POST"])
@admin_required
def modules():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name or Module.query.filter_by(name=name).first():
            flash("Indique um nome único para o módulo.", "error")
        else:
            module = Module(name=name)
            db.session.add(module)
            db.session.flush()
            ensure_assessments(module)
            db.session.commit()
            flash("Módulo criado com avaliações padrão.", "success")
            return redirect(url_for("admin.modules"))
    return render_template("admin/modules.html", modules=Module.query.order_by(Module.name).all())


@admin_bp.post("/modulos/<int:module_id>/eliminar")
@admin_required
def delete_module(module_id):
    module = db.get_or_404(Module, module_id)
    db.session.delete(module)
    db.session.commit()
    flash("Módulo eliminado.", "success")
    return redirect(url_for("admin.modules"))


@admin_bp.post("/modulos/<int:module_id>/pesos")
@admin_required
def update_weights(module_id):
    module = db.get_or_404(Module, module_id)
    weights = []
    for assessment in module.assessments:
        value = _weight(request.form.get(f"weight_{assessment.id}", ""))
        if value is None:
            flash("Cada peso deve ser um valor entre 0 e 20.", "error")
            return redirect(url_for("admin.modules"))
        weights.append((assessment, value))
    if sum(value for _, value in weights) != Decimal("100"):
        flash("A soma dos pesos deve ser 100%.", "error")
    else:
        for assessment, value in weights:
            assessment.weight = value
        db.session.commit()
        flash("Pesos atualizados.", "success")
    return redirect(url_for("admin.modules"))


@admin_bp.route("/notas", methods=["GET", "POST"])
@admin_required
def grades():
    students = Student.query.order_by(Student.full_name).all()
    modules = Module.query.filter_by(active=True).order_by(Module.name).all()
    if request.method == "POST":
        student = db.get_or_404(Student, int(request.form.get("student_id", 0)))
        module = db.get_or_404(Module, int(request.form.get("module_id", 0)))
        ensure_assessments(module)
        db.session.flush()
        value = _number(request.form.get("value", ""))
        assessment = db.get_or_404(Assessment, int(request.form.get("assessment_id", 0)))
        if assessment.module_id != module.id or value is None:
            flash("Nota inválida: utilize um valor entre 0 e 20.", "error")
        else:
            grade = Grade.query.filter_by(student_id=student.id, assessment_id=assessment.id).first()
            previous = grade.value if grade else None
            if not grade:
                grade = Grade(student=student, module=module, assessment=assessment)
                db.session.add(grade)
            grade.value = value
            grade.published = False
            db.session.flush()
            db.session.add(AuditLog(actor_id=current_user.id, grade_id=grade.id, action="CRIAR" if previous is None else "ALTERAR", previous_value=previous, new_value=value))
            refresh_result(student)
            db.session.commit()
            flash("Nota guardada e ficou não publicada até revisão.", "success")
            return redirect(url_for("admin.grades"))
    return render_template("admin/grades.html", students=students, modules=modules, assessments=Assessment.query.order_by(Assessment.module_id, Assessment.id).all(), grades=Grade.query.order_by(Grade.updated_at.desc()).limit(30).all())


@admin_bp.post("/notas/<int:grade_id>/publicacao")
@admin_required
def toggle_publication(grade_id):
    grade = db.get_or_404(Grade, grade_id)
    grade.published = not grade.published
    db.session.add(AuditLog(actor_id=current_user.id, grade_id=grade.id, action="PUBLICAR" if grade.published else "RETIRAR_PUBLICACAO", previous_value=grade.value, new_value=grade.value))
    db.session.commit()
    return redirect(url_for("admin.grades"))


@admin_bp.get("/classificacoes")
@admin_required
def rankings():
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    students_query = Student.query.join(User).order_by(Student.full_name)
    if query:
        students_query = students_query.filter(or_(Student.full_name.ilike(f"%{query}%"), Student.code.ilike(f"%{query}%")))
    students = students_query.all()
    rows = [(student, FinalResult.query.filter_by(student_id=student.id).first()) for student in students]
    if status:
        rows = [(student, result) for student, result in rows if result and result.status == status]
    rows.sort(key=lambda row: row[1].average or Decimal("-1"), reverse=True)
    return render_template("admin/rankings.html", rows=rows)


@admin_bp.get("/relatorios/exportar.csv")
@admin_required
def export_csv():
    import csv
    from io import StringIO, BytesIO
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Código", "Aluno", "Média geral", "Estado"])
    for student in Student.query.order_by(Student.full_name):
        result = FinalResult.query.filter_by(student_id=student.id).first()
        writer.writerow([student.code, student.full_name, result.average if result else "", result.status if result else "PENDENTE"])
    return send_file(BytesIO(output.getvalue().encode("utf-8-sig")), mimetype="text/csv", as_attachment=True, download_name="classificacoes.csv")


@admin_bp.get("/relatorios")
@admin_required
def reports():
    return render_template("admin/reports.html")


@admin_bp.get("/relatorios/exportar.xlsx")
@admin_required
def export_xlsx():
    from io import BytesIO
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Classificações"
    sheet.append(["Código", "Aluno", "Média geral", "Estado"])
    for student in Student.query.order_by(Student.full_name):
        result = FinalResult.query.filter_by(student_id=student.id).first()
        sheet.append([student.code, student.full_name, float(result.average) if result and result.average is not None else "", result.status if result else "PENDENTE"])
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return send_file(stream, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name="classificacoes.xlsx")


@admin_bp.get("/relatorios/exportar.pdf")
@admin_required
def export_pdf():
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    stream = BytesIO()
    document = canvas.Canvas(stream, pagesize=A4)
    document.setTitle("Classificações")
    document.drawString(48, 800, "NOTA | Classificações gerais")
    y = 770
    for student in Student.query.order_by(Student.full_name):
        result = FinalResult.query.filter_by(student_id=student.id).first()
        average = result.average if result and result.average is not None else "Pendente"
        document.drawString(48, y, f"{student.code}  {student.full_name}  {average}  {result.status if result else 'PENDENTE'}")
        y -= 18
        if y < 48:
            document.showPage()
            y = 800
    document.save()
    stream.seek(0)
    return send_file(stream, mimetype="application/pdf", as_attachment=True, download_name="classificacoes.pdf")


@admin_bp.get("/auditoria")
@admin_required
def audit():
    return render_template("admin/audit.html", logs=AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all())


@admin_bp.get("/inscricoes")
@admin_required
def enrollment_applications():
    applications = EnrollmentApplication.query.order_by(EnrollmentApplication.created_at.desc()).all()
    return render_template("admin/enrollment_applications.html", applications=applications)


@admin_bp.post("/inscricoes/<int:application_id>/estado")
@admin_required
def update_enrollment(application_id):
    application = db.get_or_404(EnrollmentApplication, application_id)
    status = request.form.get("status", "").strip()
    note = request.form.get("admin_note", "").strip()
    if status not in {"PENDENTE", "APROVADA", "REJEITADA"}:
        flash("Estado de inscrição inválido.", "error")
    elif status == "APROVADA":
        if User.query.filter_by(username=application.username).first():
            flash("O nome de utilizador desta inscrição já está em uso.", "error")
        else:
            code = f"AL{application.id:05d}"
            user = User(username=application.username, password_hash=application.password_hash, role="student")
            student = Student(code=code, full_name=application.full_name, birth_date=application.birth_date,
                              gender=application.gender, phone=application.phone, email=application.email, user=user)
            db.session.add(student)
            application.status = "APROVADA"
            application.admin_note = note or None
            application.reviewed_at = datetime.utcnow()
            db.session.commit()
            flash(f"Inscrição aprovada. Código do aluno: {code}.", "success")
    else:
        application.status = status
        application.admin_note = note or None
        application.reviewed_at = datetime.utcnow() if status == "REJEITADA" else None
        db.session.commit()
        flash("Inscrição atualizada.", "success")
    return redirect(url_for("admin.enrollment_applications"))


@admin_bp.get("/reclamacoes")
@admin_required
def complaints():
    complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    return render_template("admin/complaints.html", complaints=complaints)


@admin_bp.post("/reclamacoes/<int:complaint_id>")
@admin_required
def update_complaint(complaint_id):
    complaint = db.get_or_404(Complaint, complaint_id)
    status = request.form.get("status", "").strip()
    response = request.form.get("admin_response", "").strip()
    if status not in {"ABERTA", "EM_ANALISE", "RESPONDIDA", "ENCERRADA"}:
        flash("Estado de reclamação inválido.", "error")
    elif not response and status in {"RESPONDIDA", "ENCERRADA"}:
        flash("Escreva uma resposta antes de concluir a reclamação.", "error")
    else:
        complaint.status = status
        complaint.admin_response = response or None
        db.session.commit()
        flash("Reclamação atualizada.", "success")
    return redirect(url_for("admin.complaints"))
