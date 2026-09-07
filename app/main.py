from flask import Blueprint, redirect, url_for
from flask_login import current_user

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(url_for("admin.dashboard" if current_user.is_admin else "student.dashboard"))
