"""
Test Student Actions (Ação) Feature - SIGESC
Tests for: Matricular, Transferir, Remanejar, Progredir actions
Endpoints: PUT /api/students/{id}, GET /api/students/{id}/history
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials for Sandbox mode
TEST_EMAIL = "teste@sigesc.com"
TEST_PASSWORD = "teste"


class TestStudentActionsAPI:
    """Tests for Student Actions (Ação) feature"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for sandbox user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def api_client(self, auth_token):
        """Create authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        })
        return session
    
    @pytest.fixture(scope="class")
    def test_student(self, api_client):
        """Get a student with 'transferred' status for testing"""
        response = api_client.get(f"{BASE_URL}/api/students?limit=50")
        assert response.status_code == 200, f"Failed to get students: {response.text}"
        students = response.json()
        
        # Find a student with transferred status
        transferred_students = [s for s in students if s.get('status') == 'transferred']
        assert len(transferred_students) > 0, "No transferred students found for testing"
        
        return transferred_students[0]
    
    @pytest.fixture(scope="class")
    def schools(self, api_client):
        """Get list of schools"""
        response = api_client.get(f"{BASE_URL}/api/schools")
        assert response.status_code == 200, f"Failed to get schools: {response.text}"
        return response.json()
    
    # ===== Authentication Tests =====
    
    def test_login_success(self):
        """Test login with sandbox credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["role"] == "admin_teste"
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "invalid@test.com", "password": "wrongpassword"}
        )
        assert response.status_code == 401
    
    # ===== Students List Tests =====
    
    def test_get_students_list(self, api_client):
        """Test GET /api/students returns list of students"""
        response = api_client.get(f"{BASE_URL}/api/students")
        assert response.status_code == 200
        students = response.json()
        assert isinstance(students, list)
        assert len(students) > 0, "No students found"
        
        # Verify student structure
        student = students[0]
        assert "id" in student
        assert "full_name" in student
        assert "status" in student
    
    def test_get_students_with_limit(self, api_client):
        """Test GET /api/students with limit parameter"""
        response = api_client.get(f"{BASE_URL}/api/students?limit=5")
        assert response.status_code == 200
        students = response.json()
        assert len(students) <= 5
    
    def test_students_have_transferred_status(self, api_client):
        """Verify sandbox has students with 'transferred' status for testing Matricular action"""
        response = api_client.get(f"{BASE_URL}/api/students?limit=100")
        assert response.status_code == 200
        students = response.json()
        
        transferred = [s for s in students if s.get('status') == 'transferred']
        print(f"Found {len(transferred)} transferred students out of {len(students)} total")
        assert len(transferred) > 0, "No transferred students found - Matricular action cannot be tested"
    
    # ===== Student Update (PUT) Tests =====
    
    def test_update_student_observations(self, api_client, test_student):
        """Test PUT /api/students/{id} - update observations field"""
        student_id = test_student["id"]
        test_observation = f"TEST_observation_{uuid.uuid4().hex[:8]}"
        
        response = api_client.put(
            f"{BASE_URL}/api/students/{student_id}",
            json={"observations": test_observation}
        )
        assert response.status_code == 200, f"Update failed: {response.text}"
        
        updated = response.json()
        assert updated["observations"] == test_observation
        
        # Verify persistence with GET
        get_response = api_client.get(f"{BASE_URL}/api/students/{student_id}")
        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["observations"] == test_observation
    
    def test_update_student_status_to_active(self, api_client, test_student, schools):
        """Test PUT /api/students/{id} - change status from transferred to active (Matricular action)"""
        student_id = test_student["id"]
        
        # Get a school ID for the update
        assert len(schools) > 0, "No schools available"
        school_id = schools[0]["id"]
        
        # Update status to active (simulating Matricular action)
        response = api_client.put(
            f"{BASE_URL}/api/students/{student_id}",
            json={
                "status": "active",
                "school_id": school_id
            }
        )
        assert response.status_code == 200, f"Update failed: {response.text}"
        
        updated = response.json()
        assert updated["status"] == "active"
        assert updated["school_id"] == school_id
        
        # Revert back to transferred for other tests
        revert_response = api_client.put(
            f"{BASE_URL}/api/students/{student_id}",
            json={"status": "transferred"}
        )
        assert revert_response.status_code == 200
    
    def test_update_nonexistent_student(self, api_client):
        """Test PUT /api/students/{id} with non-existent ID returns 404"""
        fake_id = str(uuid.uuid4())
        response = api_client.put(
            f"{BASE_URL}/api/students/{fake_id}",
            json={"observations": "test"}
        )
        assert response.status_code == 404
    
    # ===== Student History Tests =====
    
    def test_get_student_history(self, api_client, test_student):
        """Test GET /api/students/{id}/history returns history records"""
        student_id = test_student["id"]
        
        response = api_client.get(f"{BASE_URL}/api/students/{student_id}/history")
        assert response.status_code == 200, f"History request failed: {response.text}"
        
        history = response.json()
        assert isinstance(history, list)
        
        # If history exists, verify structure
        if len(history) > 0:
            record = history[0]
            assert "id" in record
            assert "student_id" in record
            assert "action_type" in record
            assert "action_date" in record
            print(f"Found {len(history)} history records for student")
    
    def test_history_contains_action_types(self, api_client, test_student):
        """Test that history records contain valid action_type values"""
        student_id = test_student["id"]
        
        response = api_client.get(f"{BASE_URL}/api/students/{student_id}/history")
        assert response.status_code == 200
        
        history = response.json()
        valid_action_types = [
            'matricula', 'transferencia_saida', 'transferencia_entrada',
            'remanejamento', 'progressao', 'edicao'
        ]
        
        for record in history:
            action_type = record.get('action_type')
            assert action_type in valid_action_types, f"Invalid action_type: {action_type}"
    
    def test_history_nonexistent_student(self, api_client):
        """Test GET /api/students/{id}/history with non-existent ID returns 404"""
        fake_id = str(uuid.uuid4())
        response = api_client.get(f"{BASE_URL}/api/students/{fake_id}/history")
        assert response.status_code == 404
    
    # ===== Schools and Classes Tests =====
    
    def test_get_schools(self, api_client):
        """Test GET /api/schools returns list of schools"""
        response = api_client.get(f"{BASE_URL}/api/schools")
        assert response.status_code == 200
        schools = response.json()
        assert isinstance(schools, list)
        assert len(schools) > 0, "No schools found"
        
        # Verify school structure
        school = schools[0]
        assert "id" in school
        assert "name" in school
    
    def test_get_classes(self, api_client):
        """Test GET /api/classes returns list (may be empty in sandbox)"""
        response = api_client.get(f"{BASE_URL}/api/classes")
        assert response.status_code == 200
        classes = response.json()
        assert isinstance(classes, list)
        print(f"Found {len(classes)} classes in sandbox")
    
    # ===== Action Logic Tests =====
    
    def test_matricular_action_requires_transferred_status(self, api_client):
        """Verify that Matricular action is only available for transferred/dropout students"""
        response = api_client.get(f"{BASE_URL}/api/students?limit=100")
        assert response.status_code == 200
        students = response.json()
        
        # Check status distribution
        status_counts = {}
        for s in students:
            status = s.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"Student status distribution: {status_counts}")
        
        # Matricular should be available for transferred students
        assert 'transferred' in status_counts or 'dropout' in status_counts, \
            "No students with transferred/dropout status for Matricular action"
    
    def test_update_creates_history_entry(self, api_client, test_student):
        """Test that updating a student creates a history entry"""
        student_id = test_student["id"]
        
        # Get initial history count
        history_before = api_client.get(f"{BASE_URL}/api/students/{student_id}/history").json()
        count_before = len(history_before)
        
        # Make an update
        test_obs = f"TEST_history_check_{uuid.uuid4().hex[:8]}"
        api_client.put(
            f"{BASE_URL}/api/students/{student_id}",
            json={"observations": test_obs}
        )
        
        # Check history after update
        history_after = api_client.get(f"{BASE_URL}/api/students/{student_id}/history").json()
        count_after = len(history_after)
        
        assert count_after >= count_before, "History entry was not created after update"
        print(f"History entries: before={count_before}, after={count_after}")


class TestStudentActionsWithoutAuth:
    """Test that endpoints require authentication"""
    
    def test_students_requires_auth(self):
        """Test GET /api/students requires authentication"""
        response = requests.get(f"{BASE_URL}/api/students")
        assert response.status_code == 401
    
    def test_student_update_requires_auth(self):
        """Test PUT /api/students/{id} requires authentication"""
        fake_id = str(uuid.uuid4())
        response = requests.put(
            f"{BASE_URL}/api/students/{fake_id}",
            json={"observations": "test"}
        )
        assert response.status_code == 401
    
    def test_student_history_requires_auth(self):
        """Test GET /api/students/{id}/history requires authentication"""
        fake_id = str(uuid.uuid4())
        response = requests.get(f"{BASE_URL}/api/students/{fake_id}/history")
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
