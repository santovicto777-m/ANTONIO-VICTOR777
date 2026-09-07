import pytest

from app import create_app, db
from app.models import User


@pytest.fixture
def app(tmp_path):
    class TestConfig:
        TESTING = True
        SECRET_KEY = "test"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        WTF_CSRF_ENABLED = False
    app = create_app(TestConfig)
    with app.app_context():
        admin = User(username="admin", role="admin")
        admin.set_password("adminpass123")
        db.session.add(admin)
        db.session.commit()
    yield app
    with app.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
