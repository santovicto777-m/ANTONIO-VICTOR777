import os
from pathlib import Path

from flask import Flask, current_app
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text

from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
login_manager.login_view = "auth.login"
login_manager.login_message = "Inicie sessão para continuar."


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    if app.config.get("REQUIRE_PERSISTENT_DATABASE") and app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        raise RuntimeError("Configure DATABASE_URL com uma base PostgreSQL persistente antes de iniciar em produção.")
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

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
    columns = {column["name"] for column in inspect(db.engine).get_columns("students")}
    statements = []
    if "profile_photo" not in columns:
        statements.append("ALTER TABLE students ADD COLUMN profile_photo VARCHAR(255)")
    if "profile_photo_data" not in columns:
        photo_type = "BYTEA" if db.engine.dialect.name == "postgresql" else "BLOB"
        statements.append(f"ALTER TABLE students ADD COLUMN profile_photo_data {photo_type}")
    if "profile_photo_mimetype" not in columns:
        statements.append("ALTER TABLE students ADD COLUMN profile_photo_mimetype VARCHAR(100)")
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
