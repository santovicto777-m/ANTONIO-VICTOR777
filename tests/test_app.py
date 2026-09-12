from decimal import Decimal
from io import BytesIO

from app import db
from app.models import Assessment, Complaint, Grade, Module, Student, User
from app.services import module_average
from app import create_app


def login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)


def test_admin_can_create_student_and_student_cannot_access_admin(client, app):
    security_response = client.get('/login')
    assert security_response.headers['X-Content-Type-Options'] == 'nosniff'
    assert security_response.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert security_response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    login(client, 'admin', 'adminpass123')
    response = client.post('/admin/alunos', data={'full_name': 'Ana Silva', 'code': 'A001', 'username': 'ana', 'password': 'studentpass'})
    assert response.status_code == 302
    assert client.get('/admin/').status_code == 200
    client.post('/logout')
    login(client, 'ana', 'studentpass')
    assert client.get('/admin/').status_code == 403
    assert client.get('/aluno/').status_code == 200


def test_weighted_average_and_unpublished_visibility(client, app):
    with app.app_context():
        user = User(username='bruno', role='student'); user.set_password('studentpass')
        student = Student(code='B001', full_name='Bruno Costa', user=user)
        module = Module(name='Teste')
        db.session.add_all([user, student, module]); db.session.flush()
        assessments = [Assessment(module=module, name=name, weight=weight) for name, weight in [('Avaliação 1', 20), ('Avaliação 2', 20), ('Avaliação 3', 20), ('Prova Final', 40)]]
        db.session.add_all(assessments); db.session.flush()
        db.session.add_all([Grade(student=student, module=module, assessment=a, value=value, published=True) for a, value in zip(assessments, [15, 14, 16, 17])])
        db.session.commit()
        assert module_average(student.id, module.id) == Decimal('15.80')
    login(client, 'bruno', 'studentpass')
    assert b'15.80' in client.get('/aluno/').data


def test_admin_can_upload_edit_and_delete_student(client, app, tmp_path):
    app.config['PROFILE_UPLOAD_FOLDER'] = str(tmp_path / 'profiles')
    login(client, 'admin', 'adminpass123')
    response = client.post('/admin/alunos', data={
        'full_name': 'Carla Lima', 'code': 'C001', 'username': 'carla',
        'password': 'studentpass', 'email': 'carla@example.com',
        'profile_photo': (BytesIO(b'fake image'), 'carla.png'),
    }, content_type='multipart/form-data')
    assert response.status_code == 302
    with app.app_context():
        student = Student.query.filter_by(code='C001').one()
        photo_name = student.profile_photo
        assert photo_name and (tmp_path / 'profiles' / photo_name).exists()
        student_id = student.id
        (tmp_path / 'profiles' / photo_name).unlink()

    restored_response = client.get(f'/static/uploads/profile/{photo_name}')
    assert restored_response.status_code == 200
    assert restored_response.data == b'fake image'

    client.post('/logout')
    login(client, 'carla', 'studentpass')
    assert f'/aluno/foto/{student_id}'.encode() in client.get('/aluno/').data
    client.post('/logout')
    login(client, 'admin', 'adminpass123')

    response = client.post(f'/admin/alunos/{student_id}/editar', data={
        'full_name': 'Carla Oliveira', 'code': 'C002', 'username': 'carla.oliveira',
        'email': 'carla.oliveira@example.com', 'phone': '999999999', 'gender': 'F',
    })
    assert response.status_code == 302
    with app.app_context():
        student = db.session.get(Student, student_id)
        assert student.full_name == 'Carla Oliveira'
        assert student.code == 'C002'
        assert student.user.username == 'carla.oliveira'

    response = client.post(f'/admin/alunos/{student_id}/eliminar')
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Student, student_id) is None
        assert not (tmp_path / 'profiles' / photo_name).exists()


def test_student_can_complain_about_published_grade_and_admin_can_respond(client, app):
    with app.app_context():
        user = User(username='diana', role='student'); user.set_password('studentpass')
        student = Student(code='D001', full_name='Diana Alves', user=user)
        module = Module(name='Reclamações')
        db.session.add_all([user, student, module]); db.session.flush()
        assessment = Assessment(module=module, name='Avaliação 1', weight=100)
        db.session.add(assessment); db.session.flush()
        grade = Grade(student=student, module=module, assessment=assessment, value=8, published=False)
        db.session.add(grade); db.session.commit()
        grade_id = grade.id

    login(client, 'diana', 'studentpass')
    response = client.post('/aluno/reclamacoes', data={'grade_id': grade_id, 'message': 'A nota não foi publicada.'})
    assert response.status_code == 302
    with app.app_context():
        assert Complaint.query.count() == 0
        grade = db.session.get(Grade, grade_id)
        grade.published = True
        db.session.commit()

    response = client.post('/aluno/reclamacoes', data={'grade_id': grade_id, 'message': 'Peço a revisão desta nota.'})
    assert response.status_code == 302
    with app.app_context():
        complaint = Complaint.query.one()
        complaint_id = complaint.id
        assert complaint.status == 'ABERTA'

    client.post('/logout')
    login(client, 'admin', 'adminpass123')
    response = client.post(f'/admin/reclamacoes/{complaint_id}', data={
        'status': 'RESPONDIDA', 'admin_response': 'A nota foi revista e mantém-se.'
    })
    assert response.status_code == 302
    client.post('/logout')
    login(client, 'diana', 'studentpass')
    assert b'A nota foi revista e mant' in client.get('/aluno/').data


def test_production_rejects_sqlite_database():
    class ProductionConfig:
        TESTING = True
        SECRET_KEY = 'test'
        SQLALCHEMY_DATABASE_URI = 'sqlite:///production.db'
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        REQUIRE_PERSISTENT_DATABASE = True

    import pytest
    with pytest.raises(RuntimeError, match='PostgreSQL persistente'):
        create_app(ProductionConfig)
