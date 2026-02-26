"""
Test suite for SEMED 3 (semed3) role implementation in SIGESC
Tests the read-only access permissions for the semed3 role across all endpoints

SEMED 3 Role Requirements:
- VIEW ACCESS: Dashboard, Schools, Classes, Students, Staff, Users, Courses, Analytics, Calendar, Announcements, DiarioAEE, Attendance, Grades, Online Users
- NO ACCESS: Log de Conversas (MessageLogs), Ferramentas (AdminTools), Mantenedora
- NO WRITE: Cannot create, edit, or delete any resources
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

# Test credentials
ADMIN_CREDENTIALS = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}
SEMED3_CREDENTIALS = {"email": "semed3test@sigesc.com", "password": "Semed3Test123"}


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS)
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def semed3_token():
    """Get semed3 authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=SEMED3_CREDENTIALS)
    assert response.status_code == 200, f"SEMED3 login failed: {response.text}"
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def semed3_headers(semed3_token):
    """Headers for semed3 authenticated requests"""
    return {"Authorization": f"Bearer {semed3_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers for admin authenticated requests"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ============================================================================
# SEMED3 READ ACCESS TESTS - Should return 200
# ============================================================================

class TestSemed3ReadAccess:
    """Tests that semed3 can READ (GET) all allowed resources"""
    
    def test_get_schools(self, semed3_headers):
        """SEMED3 can GET /api/schools (list all schools)"""
        response = requests.get(f"{BASE_URL}/api/schools", headers=semed3_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/schools - Status: {response.status_code}, Schools count: {len(response.json())}")
    
    def test_get_classes(self, semed3_headers):
        """SEMED3 can GET /api/classes (list all classes)"""
        response = requests.get(f"{BASE_URL}/api/classes", headers=semed3_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/classes - Status: {response.status_code}, Classes count: {len(response.json())}")
    
    def test_get_students(self, semed3_headers):
        """SEMED3 can GET /api/students (list all students)"""
        response = requests.get(f"{BASE_URL}/api/students", headers=semed3_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/students - Status: {response.status_code}, Students count: {len(response.json())}")
    
    def test_get_users(self, semed3_headers):
        """SEMED3 can GET /api/users (list all users)"""
        response = requests.get(f"{BASE_URL}/api/users", headers=semed3_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/users - Status: {response.status_code}, Users count: {len(response.json())}")
    
    def test_get_staff(self, semed3_headers):
        """SEMED3 can GET /api/staff (list all staff/servidores)"""
        response = requests.get(f"{BASE_URL}/api/staff", headers=semed3_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/staff - Status: {response.status_code}, Staff count: {len(response.json())}")
    
    def test_get_courses(self, semed3_headers):
        """SEMED3 can GET /api/courses (list all courses/componentes curriculares)"""
        response = requests.get(f"{BASE_URL}/api/courses", headers=semed3_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/courses - Status: {response.status_code}, Courses count: {len(response.json())}")
    
    def test_get_analytics_overview(self, semed3_headers):
        """SEMED3 can GET /api/analytics/overview"""
        response = requests.get(f"{BASE_URL}/api/analytics/overview", headers=semed3_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/analytics/overview - Status: {response.status_code}")
    
    def test_get_calendar_events(self, semed3_headers):
        """SEMED3 can GET /api/calendar/events"""
        response = requests.get(f"{BASE_URL}/api/calendar/events", headers=semed3_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/calendar/events - Status: {response.status_code}")
    
    def test_get_announcements(self, semed3_headers):
        """SEMED3 can GET /api/announcements"""
        response = requests.get(f"{BASE_URL}/api/announcements", headers=semed3_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✅ GET /api/announcements - Status: {response.status_code}")


# ============================================================================
# SEMED3 WRITE ACCESS DENIAL TESTS - Should return 403
# ============================================================================

class TestSemed3WriteAccessDenied:
    """Tests that semed3 CANNOT write (POST, PUT, DELETE) resources"""
    
    def test_cannot_create_school(self, semed3_headers):
        """SEMED3 cannot POST /api/schools (create school)"""
        payload = {"name": "Test School", "status": "active"}
        response = requests.post(f"{BASE_URL}/api/schools", json=payload, headers=semed3_headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✅ POST /api/schools DENIED - Status: {response.status_code}")
    
    def test_cannot_create_class(self, semed3_headers, admin_headers):
        """SEMED3 cannot POST /api/classes (create class)"""
        # First get a valid school_id
        schools_resp = requests.get(f"{BASE_URL}/api/schools", headers=admin_headers)
        if schools_resp.status_code == 200 and len(schools_resp.json()) > 0:
            school_id = schools_resp.json()[0]['id']
            payload = {
                "name": "Test Class SEMED3",
                "school_id": school_id,
                "academic_year": 2025,
                "shift": "morning",
                "education_level": "fundamental_anos_iniciais",
                "grade_level": "1º Ano"
            }
            response = requests.post(f"{BASE_URL}/api/classes", json=payload, headers=semed3_headers)
            # Can get 403 (forbidden) or 422 (validation error where auth middleware runs after pydantic)
            # Key is that semed3 is NOT in allowed roles, so 403 should occur with valid payload
            assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
            print(f"✅ POST /api/classes DENIED - Status: {response.status_code}")
        else:
            pytest.skip("No schools available for test")
    
    def test_cannot_create_student(self, semed3_headers, admin_headers):
        """SEMED3 cannot POST /api/students (create student)"""
        # First get a valid school_id
        schools_resp = requests.get(f"{BASE_URL}/api/schools", headers=admin_headers)
        if schools_resp.status_code == 200 and len(schools_resp.json()) > 0:
            school_id = schools_resp.json()[0]['id']
            payload = {
                "full_name": "Test Student",
                "school_id": school_id,
                "status": "active"
            }
            response = requests.post(f"{BASE_URL}/api/students", json=payload, headers=semed3_headers)
            assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
            print(f"✅ POST /api/students DENIED - Status: {response.status_code}")
        else:
            pytest.skip("No schools available for test")
    
    def test_cannot_delete_user(self, semed3_headers, admin_headers):
        """SEMED3 cannot DELETE /api/users/{id}"""
        # Get a user to attempt deletion (we'll use any user id)
        users_resp = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        if users_resp.status_code == 200 and len(users_resp.json()) > 0:
            user_id = users_resp.json()[0]['id']
            response = requests.delete(f"{BASE_URL}/api/users/{user_id}", headers=semed3_headers)
            assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
            print(f"✅ DELETE /api/users/{user_id} DENIED - Status: {response.status_code}")
        else:
            pytest.skip("No users available for test")
    
    def test_cannot_update_school(self, semed3_headers, admin_headers):
        """SEMED3 cannot PUT /api/schools/{id}"""
        schools_resp = requests.get(f"{BASE_URL}/api/schools", headers=admin_headers)
        if schools_resp.status_code == 200 and len(schools_resp.json()) > 0:
            school_id = schools_resp.json()[0]['id']
            payload = {"name": "Updated School Name"}
            response = requests.put(f"{BASE_URL}/api/schools/{school_id}", json=payload, headers=semed3_headers)
            assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
            print(f"✅ PUT /api/schools/{school_id} DENIED - Status: {response.status_code}")
        else:
            pytest.skip("No schools available for test")
    
    def test_cannot_update_user(self, semed3_headers, admin_headers):
        """SEMED3 cannot PUT /api/users/{id}"""
        users_resp = requests.get(f"{BASE_URL}/api/users", headers=admin_headers)
        if users_resp.status_code == 200 and len(users_resp.json()) > 0:
            user_id = users_resp.json()[0]['id']
            payload = {"full_name": "Updated Name"}
            response = requests.put(f"{BASE_URL}/api/users/{user_id}", json=payload, headers=semed3_headers)
            assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
            print(f"✅ PUT /api/users/{user_id} DENIED - Status: {response.status_code}")
        else:
            pytest.skip("No users available for test")
    
    def test_cannot_delete_school(self, semed3_headers, admin_headers):
        """SEMED3 cannot DELETE /api/schools/{id}"""
        schools_resp = requests.get(f"{BASE_URL}/api/schools", headers=admin_headers)
        if schools_resp.status_code == 200 and len(schools_resp.json()) > 0:
            school_id = schools_resp.json()[0]['id']
            response = requests.delete(f"{BASE_URL}/api/schools/{school_id}", headers=semed3_headers)
            assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
            print(f"✅ DELETE /api/schools/{school_id} DENIED - Status: {response.status_code}")
        else:
            pytest.skip("No schools available for test")
    
    def test_cannot_create_staff(self, semed3_headers):
        """SEMED3 cannot POST /api/staff (create staff)"""
        payload = {"nome": "Test Staff", "cargo": "professor", "cpf": "12345678900"}
        response = requests.post(f"{BASE_URL}/api/staff", json=payload, headers=semed3_headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✅ POST /api/staff DENIED - Status: {response.status_code}")


# ============================================================================
# SEMED3 USER VERIFICATION
# ============================================================================

class TestSemed3UserProperties:
    """Tests that semed3 user has correct role and permissions"""
    
    def test_semed3_login_returns_correct_role(self):
        """Verify semed3 user login returns role='semed3'"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=SEMED3_CREDENTIALS)
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # User data may be in data['user'] or directly in data
        user = data.get('user', data)
        assert user.get('role') == 'semed3', f"Expected role='semed3', got '{user.get('role')}'"
        print(f"✅ SEMED3 login - Role: {user.get('role')}, Name: {user.get('full_name')}")
    
    def test_semed3_me_endpoint(self, semed3_headers):
        """Verify /api/auth/me returns correct semed3 user data"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=semed3_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        user = response.json()
        assert user.get('role') == 'semed3', f"Expected role='semed3', got '{user.get('role')}'"
        print(f"✅ GET /api/auth/me - Role: {user.get('role')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
