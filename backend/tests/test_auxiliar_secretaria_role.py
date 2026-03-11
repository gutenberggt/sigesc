"""
Test suite for validating auxiliar_secretaria role permissions
The auxiliar_secretaria role should have identical permissions to coordenador (read-only access)

Test Coverage:
- Login with auxiliar_secretaria credentials
- API access (GET requests should work)
- Edit restrictions (auxiliar_secretaria should NOT be able to edit)
- Same menus and data access as coordenador
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
AUXILIAR_CREDENTIALS = {
    "email": "auxiliar_teste@sigesc.com",
    "password": "auxiliar123"
}

ADMIN_CREDENTIALS = {
    "email": "gutenberg@sigesc.com",
    "password": "@Celta2007"
}

SECRETARIO_CREDENTIALS = {
    "email": "secretario@sigesc.com",
    "password": "secretario123"
}

class TestAuxiliarSecretariaLogin:
    """Test auxiliar_secretaria login functionality"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create a session for all tests"""
        return requests.Session()
    
    def test_auxiliar_login_success(self, session):
        """Test that auxiliar_secretaria can login successfully"""
        response = session.post(f"{BASE_URL}/api/auth/login", json=AUXILIAR_CREDENTIALS)
        print(f"Login response status: {response.status_code}")
        print(f"Login response: {response.text[:500]}")
        
        # Should return 200 for successful login
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "access_token" in data, "Missing access_token in response"
        assert "user" in data, "Missing user in response"
        
        # Verify role is auxiliar_secretaria
        user = data["user"]
        assert user.get("role") == "auxiliar_secretaria" or user.get("email") == AUXILIAR_CREDENTIALS["email"], f"Unexpected user data: {user}"
        print(f"Login successful - User role: {user.get('role')}")
        
    def test_admin_login_success(self, session):
        """Test admin login for comparison"""
        response = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS)
        print(f"Admin login response status: {response.status_code}")
        
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        print(f"Admin role: {data['user'].get('role')}")


class TestAuxiliarSecretariaAPIAccess:
    """Test auxiliar_secretaria API access (read-only)"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for auxiliar_secretaria"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=AUXILIAR_CREDENTIALS)
        if response.status_code != 200:
            pytest.skip(f"Login failed for auxiliar_secretaria: {response.text}")
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_get_classes_returns_200(self, auth_headers):
        """Test GET /api/classes works for auxiliar_secretaria"""
        response = requests.get(f"{BASE_URL}/api/classes", headers=auth_headers)
        print(f"GET /api/classes - Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"Classes count: {len(response.json()) if isinstance(response.json(), list) else 'paginated'}")
    
    def test_get_students_returns_200(self, auth_headers):
        """Test GET /api/students works for auxiliar_secretaria"""
        response = requests.get(f"{BASE_URL}/api/students", headers=auth_headers)
        print(f"GET /api/students - Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        # Students endpoint returns paginated data
        if isinstance(data, dict):
            print(f"Students total: {data.get('total', 'unknown')}")
        else:
            print(f"Students count: {len(data)}")
    
    def test_get_announcements_returns_200(self, auth_headers):
        """Test GET /api/announcements works for auxiliar_secretaria"""
        response = requests.get(f"{BASE_URL}/api/announcements", headers=auth_headers)
        print(f"GET /api/announcements - Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_get_analytics_overview_returns_200(self, auth_headers):
        """Test GET /api/analytics/overview works for auxiliar_secretaria"""
        response = requests.get(f"{BASE_URL}/api/analytics/overview", headers=auth_headers)
        print(f"GET /api/analytics/overview - Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_get_grades_returns_200(self, auth_headers):
        """Test GET /api/grades works for auxiliar_secretaria"""
        response = requests.get(f"{BASE_URL}/api/grades", headers=auth_headers)
        print(f"GET /api/grades - Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_get_schools_returns_200(self, auth_headers):
        """Test GET /api/schools works for auxiliar_secretaria"""
        response = requests.get(f"{BASE_URL}/api/schools", headers=auth_headers)
        print(f"GET /api/schools - Status: {response.status_code}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


class TestAuxiliarSecretariaPermissions:
    """Test auxiliar_secretaria permissions (should be read-only like coordenador)"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for auxiliar_secretaria"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=AUXILIAR_CREDENTIALS)
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_get_permissions_endpoint(self, auth_headers):
        """Test GET /api/auth/permissions returns correct permissions for auxiliar_secretaria"""
        response = requests.get(f"{BASE_URL}/api/auth/permissions", headers=auth_headers)
        print(f"GET /api/auth/permissions - Status: {response.status_code}")
        print(f"Permissions: {response.text[:500]}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        perms = response.json()
        
        # Verify auxiliar_secretaria has read-only permissions (like coordenador)
        assert perms.get("can_edit_grades") == False, f"auxiliar_secretaria should NOT be able to edit grades: {perms}"
        assert perms.get("can_edit_classes") == False, f"auxiliar_secretaria should NOT be able to edit classes: {perms}"
        assert perms.get("can_edit_students") == False, f"auxiliar_secretaria should NOT be able to edit students: {perms}"
        assert perms.get("can_view_all_school_data") == True, f"auxiliar_secretaria should be able to view school data: {perms}"
        assert perms.get("is_read_only_except_diary") == True, f"auxiliar_secretaria should be read-only: {perms}"
        
        print("Permissions verified: auxiliar_secretaria has correct read-only access")
        
    def test_diary_dashboard_access(self, auth_headers):
        """Test auxiliar_secretaria can access diary dashboard"""
        response = requests.get(f"{BASE_URL}/api/diary/dashboard", headers=auth_headers)
        print(f"GET /api/diary/dashboard - Status: {response.status_code}")
        
        # Diary dashboard should be accessible (for viewing)
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"


class TestCompareWithAdmin:
    """Compare auxiliar_secretaria API access with admin"""
    
    @pytest.fixture(scope="class")
    def auxiliar_token(self):
        """Get auth token for auxiliar_secretaria"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=AUXILIAR_CREDENTIALS)
        if response.status_code != 200:
            pytest.skip(f"Auxiliar login failed: {response.text}")
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get auth token for admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDENTIALS)
        if response.status_code != 200:
            pytest.skip(f"Admin login failed: {response.text}")
        return response.json()["access_token"]
    
    def test_both_can_view_classes(self, auxiliar_token, admin_token):
        """Both admin and auxiliar_secretaria can view classes"""
        aux_headers = {"Authorization": f"Bearer {auxiliar_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        aux_resp = requests.get(f"{BASE_URL}/api/classes", headers=aux_headers)
        admin_resp = requests.get(f"{BASE_URL}/api/classes", headers=admin_headers)
        
        print(f"auxiliar_secretaria GET classes: {aux_resp.status_code}")
        print(f"admin GET classes: {admin_resp.status_code}")
        
        assert aux_resp.status_code == 200, f"auxiliar_secretaria should see classes: {aux_resp.text}"
        assert admin_resp.status_code == 200, f"admin should see classes: {admin_resp.text}"
        
    def test_both_can_view_students(self, auxiliar_token, admin_token):
        """Both admin and auxiliar_secretaria can view students"""
        aux_headers = {"Authorization": f"Bearer {auxiliar_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        aux_resp = requests.get(f"{BASE_URL}/api/students", headers=aux_headers)
        admin_resp = requests.get(f"{BASE_URL}/api/students", headers=admin_headers)
        
        print(f"auxiliar_secretaria GET students: {aux_resp.status_code}")
        print(f"admin GET students: {admin_resp.status_code}")
        
        assert aux_resp.status_code == 200, f"auxiliar_secretaria should see students: {aux_resp.text}"
        assert admin_resp.status_code == 200, f"admin should see students: {admin_resp.text}"
        
    def test_both_can_view_grades(self, auxiliar_token, admin_token):
        """Both admin and auxiliar_secretaria can view grades"""
        aux_headers = {"Authorization": f"Bearer {auxiliar_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        aux_resp = requests.get(f"{BASE_URL}/api/grades", headers=aux_headers)
        admin_resp = requests.get(f"{BASE_URL}/api/grades", headers=admin_headers)
        
        print(f"auxiliar_secretaria GET grades: {aux_resp.status_code}")
        print(f"admin GET grades: {admin_resp.status_code}")
        
        assert aux_resp.status_code == 200, f"auxiliar_secretaria should see grades: {aux_resp.text}"
        assert admin_resp.status_code == 200, f"admin should see grades: {admin_resp.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
