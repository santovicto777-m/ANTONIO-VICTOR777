from decimal import Decimal
from io import BytesIO

from app import db
from app.models import Assessment, Complaint, EnrollmentApplication, FinalResult, Grade, Module, Student, User
from app.services import module_average, refresh_result
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


def test_result_stays_pending_until_all_active_modules_are_complete(app):
    with app.app_context():
        user = User(username='eva', role='student'); user.set_password('studentpass')
        student = Student(code='E001', full_name='Eva Silva', user=user)
        first = Module(name='Primeiro')
        second = Module(name='Segundo')
        db.session.add_all([user, student, first, second]); db.session.flush()
        first_assessments = [Assessment(module=first, name=name, weight=weight) for name, weight in [('Avaliação 1', 20), ('Avaliação 2', 20), ('Avaliação 3', 20), ('Prova Final', 40)]]
        second_assessments = [Assessment(module=second, name=name, weight=weight) for name, weight in [('Avaliação 1', 20), ('Avaliação 2', 20), ('Avaliação 3', 20), ('Prova Final', 40)]]
        db.session.add_all(first_assessments + second_assessments); db.session.flush()
        db.session.add_all([Grade(student=student, module=first, assessment=assessment, value=5) for assessment in first_assessments])
        result = refresh_result(student)
        db.session.commit()
        assert result.status == 'PENDENTE'
        assert result.average is None


def test_student_dashboard_repairs_old_reproved_result(client, app):
    with app.app_context():
        user = User(username='filipe', role='student'); user.set_password('studentpass')
        student = Student(code='F001', full_name='Filipe Costa', user=user)
        module = Module(name='Módulo incompleto')
        db.session.add_all([user, student, module]); db.session.flush()
        db.session.add(FinalResult(student_id=student.id, average=8, status='REPROVADO'))
        db.session.commit()

    login(client, 'filipe', 'studentpass')
    response = client.get('/aluno/')
    assert response.status_code == 200
    assert b'class="status-text">PENDENTE' in response.data


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


def test_online_enrollment_is_pending_until_admin_approves(client, app):
    response = client.post('/inscricao', data={
        'full_name': 'Guilherme Mendes', 'email': 'guilherme@example.com',
        'phone': '935730700', 'course': 'Informática', 'username': 'guilherme',
        'password': 'candidatepass', 'gender': 'Masculino', 'identity_number': 'BI12345',
        'residence': 'Luanda', 'birth_date': '2000-05-20',
    })
    assert response.status_code == 302
    assert '/inscricao/estado?application_id=' in response.location
    assert 'email=guilherme@example.com' in response.location
    with app.app_context():
        application = EnrollmentApplication.query.one()
        application_id = application.id
        assert application.status == 'PENDENTE'
        assert Student.query.count() == 0

    status_response = client.post('/inscricao/estado', data={
        'application_id': application_id, 'email': 'guilherme@example.com'
    })
    assert b'PENDENTE' in status_response.data
    assert b'Ainda n' in status_response.data

    login(client, 'admin', 'adminpass123')
    dashboard = client.get('/admin/')
    assert b'Ver inscri' in dashboard.data
    response = client.post(f'/admin/inscricoes/{application_id}/estado', data={
        'status': 'APROVADA', 'admin_note': 'Inscrição aprovada.'
    })
    assert response.status_code == 302
    status_response = client.post('/inscricao/estado', data={
        'application_id': application_id, 'email': 'guilherme@example.com'
    })
    assert b'APROVADA' in status_response.data
    assert b'Inscri' in status_response.data
    with app.app_context():
        application = db.session.get(EnrollmentApplication, application_id)
        student = Student.query.one()
        assert application.status == 'APROVADA'
        assert student.code == f'AL{application_id:05d}'
        assert student.user.username == 'guilherme'
        assert student.identity_number == 'BI12345'
        assert student.residence == 'Luanda'
        assert student.birth_date.strftime('%Y-%m-%d') == '2000-05-20'

    client.post('/logout')
    login(client, 'guilherme', 'candidatepass')
    assert client.get('/aluno/').status_code == 200
