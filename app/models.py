from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    student = db.relationship("Student", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    birth_date = db.Column(db.Date)
    gender = db.Column(db.String(30))
    phone = db.Column(db.String(40))
    email = db.Column(db.String(150))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    user = db.relationship("User", back_populates="student")
    grades = db.relationship("Grade", back_populates="student", cascade="all, delete-orphan")


class Module(db.Model):
    __tablename__ = "modules"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    assessments = db.relationship("Assessment", back_populates="module", cascade="all, delete-orphan")
    grades = db.relationship("Grade", back_populates="module", cascade="all, delete-orphan")


class Assessment(db.Model):
    __tablename__ = "assessments"
    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id"), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    weight = db.Column(db.Numeric(5, 2), nullable=False)
    module = db.relationship("Module", back_populates="assessments")
    grades = db.relationship("Grade", back_populates="assessment", cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint("module_id", "name"),)


class Grade(db.Model):
    __tablename__ = "grades"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey("modules.id"), nullable=False)
    assessment_id = db.Column(db.Integer, db.ForeignKey("assessments.id"), nullable=False)
    value = db.Column(db.Numeric(4, 2), nullable=True)
    published = db.Column(db.Boolean, default=False, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    student = db.relationship("Student", back_populates="grades")
    module = db.relationship("Module", back_populates="grades")
    assessment = db.relationship("Assessment", back_populates="grades")
    __table_args__ = (db.UniqueConstraint("student_id", "assessment_id"),)

    @property
    def display_value(self):
        return "Pendente" if self.value is None else f"{Decimal(self.value):.1f}"


class FinalResult(db.Model):
    __tablename__ = "final_results"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), unique=True, nullable=False)
    average = db.Column(db.Numeric(4, 2))
    status = db.Column(db.String(20), default="PENDENTE", nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    grade_id = db.Column(db.Integer, db.ForeignKey("grades.id"))
    action = db.Column(db.String(30), nullable=False)
    previous_value = db.Column(db.Numeric(4, 2))
    new_value = db.Column(db.Numeric(4, 2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    actor = db.relationship("User")
    grade = db.relationship("Grade")
