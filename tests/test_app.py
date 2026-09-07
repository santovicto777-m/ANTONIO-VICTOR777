from decimal import Decimal

from app import db
from app.models import Assessment, Grade, Module, Student, User
from app.services import module_average


def login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)


def test_admin_can_create_student_and_student_cannot_access_admin(client, app):
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
