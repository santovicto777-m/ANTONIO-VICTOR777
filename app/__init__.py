from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
login_manager.login_view = "auth.login"
login_manager.login_message = "Inicie sessão para continuar."


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
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
        _seed_modules()

    return app


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
