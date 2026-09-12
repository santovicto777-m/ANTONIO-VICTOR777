import os
from pathlib import Path

from flask import Flask, current_app, request
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text

from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
login_manager.login_view = "auth.login"
login_manager.login_message = "Inicie sessão para continuar."


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    if app.config.get("REQUIRE_PERSISTENT_DATABASE") and app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        raise RuntimeError("Configure DATABASE_URL com uma base PostgreSQL persistente antes de iniciar em produção.")
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if app.config.get("REQUIRE_PERSISTENT_DATABASE") or app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.before_request
    def restore_requested_profile_photo():
        prefix = "/static/uploads/profile/"
        if request.path.startswith(prefix):
            filename = request.path[len(prefix):]
            _restore_profile_photo_file(filename)

    from app.auth import auth_bp
    from app.main import main_bp
    from app.admin import admin_bp
    from app.student import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(student_bp, url_prefix="/aluno")
    from app.cli import register_commands
    register_commands(app)

    with app.app_context():
        from app import models  # noqa: F401
        db.create_all()
        _ensure_schema()
        _restore_profile_photos()
        _seed_modules()
        _bootstrap_admin()

    return app


def _ensure_schema():
    table_columns = {
        "students": {column["name"] for column in inspect(db.engine).get_columns("students")},
        "enrollment_applications": {column["name"] for column in inspect(db.engine).get_columns("enrollment_applications")},
    }
    statements = []
    if "profile_photo" not in table_columns["students"]:
        statements.append("ALTER TABLE students ADD COLUMN profile_photo VARCHAR(255)")
    if "profile_photo_data" not in table_columns["students"]:
        photo_type = "BYTEA" if db.engine.dialect.name == "postgresql" else "BLOB"
        statements.append(f"ALTER TABLE students ADD COLUMN profile_photo_data {photo_type}")
    if "profile_photo_mimetype" not in table_columns["students"]:
        statements.append("ALTER TABLE students ADD COLUMN profile_photo_mimetype VARCHAR(100)")
    if "identity_number" not in table_columns["students"]:
        statements.append("ALTER TABLE students ADD COLUMN identity_number VARCHAR(50)")
    if "residence" not in table_columns["students"]:
        statements.append("ALTER TABLE students ADD COLUMN residence VARCHAR(255)")
    if "identity_number" not in table_columns["enrollment_applications"]:
        statements.append("ALTER TABLE enrollment_applications ADD COLUMN identity_number VARCHAR(50)")
    if "residence" not in table_columns["enrollment_applications"]:
        statements.append("ALTER TABLE enrollment_applications ADD COLUMN residence VARCHAR(255)")
    if statements:
        with db.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))


def _restore_profile_photos():
    from app.models import Student

    upload_folder = Path(current_app.config.get("PROFILE_UPLOAD_FOLDER", Path(current_app.instance_path) / "profile_uploads"))
    upload_folder.mkdir(parents=True, exist_ok=True)
    for student in Student.query.filter(Student.profile_photo.is_not(None), Student.profile_photo_data.is_not(None)):
        photo_path = upload_folder / student.profile_photo
        if not photo_path.exists():
            photo_path.write_bytes(student.profile_photo_data)


def _restore_profile_photo_file(filename):
    from app.models import Student

    if not filename or "/" in filename or "\\" in filename:
        return
    student = Student.query.filter_by(profile_photo=filename).first()
    if not student or not student.profile_photo_data:
        return
    folders = {
        Path(current_app.config.get("PROFILE_UPLOAD_FOLDER", Path(current_app.instance_path) / "profile_uploads")),
        Path(current_app.static_folder) / "uploads" / "profile",
    }
    for upload_folder in folders:
        upload_folder.mkdir(parents=True, exist_ok=True)
        photo_path = upload_folder / filename
        if not photo_path.exists():
            photo_path.write_bytes(student.profile_photo_data)


def _seed_modules():
    from app.models import Module
    from app.services import ensure_assessments

    if Module.query.count() == 0:
        modules = [Module(name=name) for name in [
            "Word", "Excel", "PowerPoint", "Internet", "Hardware e Periféricos"
        ]]
        db.session.add_all(modules)
        db.session.flush()
        for module in modules:
            ensure_assessments(module)
        db.session.commit()


def _bootstrap_admin():
    from app.models import User

    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")
    if not username or not password or User.query.filter_by(username=username).first():
        return
    if len(password) < 8:
        raise ValueError("ADMIN_PASSWORD deve ter pelo menos 8 caracteres.")
    admin = User(username=username, role="admin")
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
