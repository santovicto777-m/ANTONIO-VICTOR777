from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.models import User
from app import db, limiter

auth_bp = Blueprint("auth", __name__)


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
