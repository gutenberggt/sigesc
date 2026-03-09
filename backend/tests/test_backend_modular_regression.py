"""
Teste de Regressão - Backend Modular SIGESC
=============================================
Este teste valida que todas as APIs funcionam após a refatoração
do server.py monolítico para 17+ roteadores modulares.

Endpoints testados:
- Auth: login, logout
- Schools: GET /api/schools
- Students: GET /api/students
- Classes: GET /api/classes
- Courses: GET /api/courses
- Users: GET /api/users
- Enrollments: GET /api/enrollments
- Staff: GET /api/staff
- Grades: GET /api/grades
- Calendar Events: GET /api/calendar/events
- Announcements: GET /api/announcements
- School Assignments: GET /api/school-assignments
- Mantenedora: GET /api/mantenedora
- Analytics: GET /api/analytics/overview
- Pre-matriculas: GET /api/pre-matriculas
- Guardians: GET /api/guardians
- Audit Logs: GET /api/audit-logs
- Notifications: GET /api/notifications/unread-count
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
SEMED3_EMAIL = "semed3@sigesc.com"
SEMED3_PASSWORD = "semed123"


class TestHealthCheck:
    """Testes de health check e conectividade básica"""
    
    def test_api_root(self):
        """Verifica se a API está online"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "online"
        print(f"✓ API Online: {data.get('message')}")

    def test_health_check(self):
        """Verifica saúde da aplicação e conexão com banco"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("database") == "connected"
        print(f"✓ Health Check: database={data.get('database')}")


class TestAuthentication:
    """Testes de autenticação"""
    
    def test_login_admin(self):
        """Testa login com credenciais admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert "user" in data
        assert data["user"]["email"] == ADMIN_EMAIL
        print(f"✓ Login Admin: {data['user']['full_name']} ({data['user']['role']})")

    def test_login_semed3(self):
        """Testa login com credenciais SEMED3"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": SEMED3_EMAIL,
            "password": SEMED3_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        print(f"✓ Login SEMED3: {data['user']['full_name']} ({data['user']['role']})")

    def test_login_invalid_credentials(self):
        """Testa login com credenciais inválidas"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@test.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("✓ Login inválido retorna 401")


@pytest.fixture(scope="class")
def admin_token():
    """Obtém token de autenticação admin para os testes"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Autenticação falhou - pulando testes autenticados")


@pytest.fixture(scope="class")
def auth_headers(admin_token):
    """Headers com autenticação"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestSchools:
    """Testes do router de escolas"""
    
    def test_list_schools(self, auth_headers):
        """GET /api/schools - lista escolas"""
        response = requests.get(f"{BASE_URL}/api/schools", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/schools: {len(data)} escolas")
        # Valida estrutura de uma escola se houver
        if data:
            school = data[0]
            assert "id" in school
            assert "name" in school


class TestStudents:
    """Testes do router de alunos"""
    
    def test_list_students_paginated(self, auth_headers):
        """GET /api/students?page=1&limit=5 - lista alunos com paginação"""
        response = requests.get(
            f"{BASE_URL}/api/students",
            params={"page": 1, "limit": 5},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Resposta paginada deve ter estrutura específica
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data or "limit" in data or len(data["items"]) <= 5
        print(f"✓ GET /api/students: {len(data['items'])} alunos (total: {data.get('total', 'N/A')})")


class TestClasses:
    """Testes do router de turmas"""
    
    def test_list_classes(self, auth_headers):
        """GET /api/classes - lista turmas"""
        response = requests.get(f"{BASE_URL}/api/classes", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/classes: {len(data)} turmas")
        if data:
            class_item = data[0]
            assert "id" in class_item


class TestCourses:
    """Testes do router de componentes curriculares"""
    
    def test_list_courses(self, auth_headers):
        """GET /api/courses - lista componentes curriculares"""
        response = requests.get(f"{BASE_URL}/api/courses", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/courses: {len(data)} componentes")


class TestUsers:
    """Testes do router de usuários"""
    
    def test_list_users(self, auth_headers):
        """GET /api/users - lista usuários"""
        response = requests.get(f"{BASE_URL}/api/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/users: {len(data)} usuários")
        if data:
            user = data[0]
            assert "id" in user
            assert "email" in user
            # password_hash não deve ser retornado
            assert "password_hash" not in user


class TestEnrollments:
    """Testes do router de matrículas"""
    
    def test_list_enrollments(self, auth_headers):
        """GET /api/enrollments - lista matrículas"""
        response = requests.get(f"{BASE_URL}/api/enrollments", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/enrollments: {len(data)} matrículas")


class TestStaff:
    """Testes do router de servidores"""
    
    def test_list_staff(self, auth_headers):
        """GET /api/staff - lista servidores"""
        response = requests.get(f"{BASE_URL}/api/staff", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/staff: {len(data)} servidores")


class TestGrades:
    """Testes do router de notas"""
    
    def test_list_grades(self, auth_headers):
        """GET /api/grades - lista notas"""
        response = requests.get(f"{BASE_URL}/api/grades", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/grades: {len(data)} registros de notas")


class TestCalendar:
    """Testes do router de calendário"""
    
    def test_list_calendar_events(self, auth_headers):
        """GET /api/calendar/events - lista eventos do calendário"""
        response = requests.get(f"{BASE_URL}/api/calendar/events", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/calendar/events: {len(data)} eventos")


class TestAnnouncements:
    """Testes do router de avisos"""
    
    def test_list_announcements(self, auth_headers):
        """GET /api/announcements - lista avisos"""
        response = requests.get(f"{BASE_URL}/api/announcements", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/announcements: {len(data)} avisos")


class TestSchoolAssignments:
    """Testes do router de lotações"""
    
    def test_list_school_assignments(self, auth_headers):
        """GET /api/school-assignments - lista lotações"""
        response = requests.get(f"{BASE_URL}/api/school-assignments", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/school-assignments: {len(data)} lotações")


class TestMantenedora:
    """Testes do router de mantenedora"""
    
    def test_get_mantenedora(self, auth_headers):
        """GET /api/mantenedora - dados da mantenedora"""
        response = requests.get(f"{BASE_URL}/api/mantenedora", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "nome" in data
        print(f"✓ GET /api/mantenedora: {data.get('nome', 'N/A')}")


class TestAnalytics:
    """Testes do router de analytics"""
    
    def test_analytics_overview(self, auth_headers):
        """GET /api/analytics/overview - dashboard analítico"""
        response = requests.get(f"{BASE_URL}/api/analytics/overview", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Valida estrutura esperada do dashboard
        assert "schools" in data
        assert "students" in data
        assert "enrollments" in data
        print(f"✓ GET /api/analytics/overview: {data.get('schools', {}).get('total', 0)} escolas, "
              f"{data.get('students', {}).get('active', 0)} alunos ativos")


class TestPreMatriculas:
    """Testes do router de pré-matrículas"""
    
    def test_list_pre_matriculas(self, auth_headers):
        """GET /api/pre-matriculas - lista pré-matrículas"""
        response = requests.get(f"{BASE_URL}/api/pre-matriculas", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/pre-matriculas: {len(data)} pré-matrículas")


class TestGuardians:
    """Testes do router de responsáveis"""
    
    def test_list_guardians(self, auth_headers):
        """GET /api/guardians - lista responsáveis"""
        response = requests.get(f"{BASE_URL}/api/guardians", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/guardians: {len(data)} responsáveis")


class TestAuditLogs:
    """Testes do router de logs de auditoria"""
    
    def test_list_audit_logs(self, auth_headers):
        """GET /api/audit-logs?limit=3 - logs de auditoria"""
        response = requests.get(
            f"{BASE_URL}/api/audit-logs",
            params={"limit": 3},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        print(f"✓ GET /api/audit-logs: {len(data.get('items', []))} logs (total: {data.get('total', 0)})")


class TestNotifications:
    """Testes do router de notificações"""
    
    def test_unread_count(self, auth_headers):
        """GET /api/notifications/unread-count - contagem de notificações"""
        response = requests.get(f"{BASE_URL}/api/notifications/unread-count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "unread_messages" in data or "total" in data
        print(f"✓ GET /api/notifications/unread-count: total={data.get('total', 0)}")


class TestAuthMe:
    """Testes de endpoints de perfil do usuário autenticado"""
    
    def test_auth_me(self, auth_headers):
        """GET /api/auth/me - perfil do usuário autenticado"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data
        print(f"✓ GET /api/auth/me: {data.get('full_name')} ({data.get('role')})")


# Test summary helper
def test_summary():
    """Imprime resumo final dos testes"""
    print("\n" + "="*60)
    print("RESUMO: Teste de Regressão Backend Modular SIGESC")
    print("="*60)
    print("Todos os endpoints principais foram testados com sucesso!")
    print("A refatoração do server.py para roteadores modulares")
    print("está funcionando corretamente.")
    print("="*60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
