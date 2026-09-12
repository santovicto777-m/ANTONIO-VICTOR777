from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.security import generate_password_hash

from app.models import EnrollmentApplication, User
from app import db, limiter

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/inscricao", methods=["GET", "POST"])
def enrollment():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        identity_number = request.form.get("identity_number", "").strip()
        residence = request.form.get("residence", "").strip()
        birth_date_value = request.form.get("birth_date", "").strip()
        course = request.form.get("course", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            birth_date = datetime.strptime(birth_date_value, "%Y-%m-%d").date() if birth_date_value else None
        except ValueError:
            birth_date = None
        if not full_name or not email or not phone or not identity_number or not residence or not birth_date or not course or not username or len(password) < 8:
            flash("Preencha todos os campos obrigatórios e use uma password com pelo menos 8 caracteres.", "error")
        elif User.query.filter_by(username=username).first() or EnrollmentApplication.query.filter_by(username=username, status="PENDENTE").first():
            flash("Este nome de utilizador já está em uso.", "error")
        else:
            application = EnrollmentApplication(full_name=full_name, email=email, phone=phone,
                                                birth_date=birth_date, identity_number=identity_number,
                                                residence=residence, gender=request.form.get("gender") or None,
                                                course=course, username=username)
            application.password_hash = generate_password_hash(password)
            db.session.add(application)
            db.session.commit()
            flash("Inscrição enviada. Aguarde a análise da administração.", "success")
            return redirect(url_for("auth.login"))
    return render_template("enrollment.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if not user or not user.active or not user.check_password(password):
            flash("Credenciais inválidas ou conta inativa.", "error")
        else:
            login_user(user, remember=False)
            return redirect(url_for("main.index"))
    return render_template("login.html")


@auth_bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/alterar-password", methods=["GET", "POST"])
def change_password():
    from flask_login import login_required
    from werkzeug.security import generate_password_hash

    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        if not current_user.check_password(current) or len(new_password) < 8:
            flash("Password atual inválida ou a nova password tem menos de 8 caracteres.", "error")
        else:
            current_user.password_hash = generate_password_hash(new_password)
            db.session.commit()
            flash("Password alterada com sucesso.", "success")
            return redirect(url_for("main.index"))
    return render_template("change_password.html")
